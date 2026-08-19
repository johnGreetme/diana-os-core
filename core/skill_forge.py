"""DIANA OS - LLM-Powered Skill Forge Engine.

Orchestrates the full autonomous skill lifecycle:
    Deficit Detection → Research → Drafting → Z3 Verification → Self-Correction → Graduation → Hot-Load

Implements the Three Sovereignty Guardrails:
    1. Local-First (DeepSeek/Llama via Ollama) — cloud only if ZERO_TRUST_CLOUD_BRIDGE=true
    2. 8-Call Budget Ceiling — prevents runaway token consumption on edge nodes
    3. 3-Strike Z3 Rule — halts hallucination loops after 3 consecutive UNSAT rejections
"""

import os
import re
import json
import logging
import requests
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, List, Optional, Any

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SkillForge:
    """LLM-Powered Skill Forge for autonomous skill generation, correction, and graduation.

    Mirrors the mediator's Two-Loop escalation pattern:
    local DeepSeek first → Gemini only if cloud bridge is explicitly enabled.
    """

    MAX_LLM_CALLS: int = 8   # Budget ceiling per forge cycle
    MAX_Z3_RETRIES: int = 3  # 3-Strike Rule

    def __init__(self):
        self._llm_call_count: int = 0
        self._z3_attempt_count: int = 0
        self._forged_by: str = "local"

    # =========================================================================
    # LLM Provider Abstraction (Q1: Local-First, Cloud Only If Enabled)
    # =========================================================================

    def _load_model_tag(self) -> str:
        """Reads model tag from openclaw.json, defaults to 'deepseek-r1:14b'."""
        try:
            with open(os.path.join(BASE_DIR, "openclaw.json"), "r") as f:
                return json.load(f).get("model_tag", "deepseek-r1:14b")
        except Exception:
            return "deepseek-r1:14b"

    def _is_cloud_bridge_enabled(self) -> bool:
        """Checks if the Zero-Trust Cloud Bridge is explicitly authorized."""
        return os.environ.get("ZERO_TRUST_CLOUD_BRIDGE", "").lower() == "true"

    def _check_budget(self) -> None:
        """Raises RuntimeError if LLM call budget is exceeded (Q2: 8-call ceiling)."""
        if self._llm_call_count >= self.MAX_LLM_CALLS:
            raise RuntimeError(
                f"Forge budget exceeded ({self.MAX_LLM_CALLS} LLM calls). "
                f"Edge VRAM protection engaged. Halting forge cycle."
            )

    def _call_local_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Calls local DeepSeek/Llama LLM via Ollama API.

        Increments call counter, strips <think> tags, enforces budget ceiling.
        """
        self._check_budget()
        self._llm_call_count += 1
        tag = self._load_model_tag()

        try:
            response = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": tag, "system": system_prompt, "prompt": user_prompt, "stream": False},
                timeout=120
            )
            if response.status_code == 200:
                text = response.json().get("response", "")
                # Strip DeepSeek thinking tags
                if "</think>" in text:
                    text = text.split("</think>")[-1].strip()
                return text
            else:
                return f"[LOCAL LLM ERROR] Status {response.status_code}: {response.text}"
        except Exception as e:
            logger.error(f"[SKILL FORGE] Local LLM call failed: {e}")
            return f"[LOCAL LLM ERROR] {str(e)}"

    def _call_cloud_llm(self, prompt: str) -> str:
        """Calls Gemini 2.5 Pro via Google Generative AI SDK.

        Enforces Zero-Trust Cloud Bridge gate — returns error if not explicitly enabled.
        """
        if not self._is_cloud_bridge_enabled():
            return (
                "[CLOUD BRIDGE DENIED] Zero-Trust Cloud Bridge not enabled. "
                "Set ZERO_TRUST_CLOUD_BRIDGE=true in .env to authorize cloud escalation. "
                "Digital sovereignty requires explicit operator authorization."
            )

        self._check_budget()
        self._llm_call_count += 1
        self._forged_by = "hybrid"

        try:
            import google.generativeai as genai
            gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not gemini_key:
                return "[CLOUD BRIDGE ERROR] No GEMINI_API_KEY found in environment."
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-pro")
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"[SKILL FORGE] Cloud LLM call failed: {e}")
            return f"[CLOUD LLM ERROR] {str(e)}"

    # =========================================================================
    # Forge Pipeline Stages
    # =========================================================================

    def _generate_slug(self, text: str) -> str:
        """Generates a URL-safe skill slug from description text."""
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        return slug[:50].strip("-") or "generated-skill"

    def detect_deficit(self, user_query: str, available_tools: List[str]) -> Tuple[bool, str]:
        """Sends query + tool list to LLM to determine if a capability is missing.

        Returns:
            (is_deficit, deficit_description)
        """
        system_prompt = (
            "You are D.I.A.N.A. OS Skill Deficit Detector. "
            "Determine if the user's query requires a capability not present in the available tools. "
            "Respond with exactly 'DEFICIT: <description>' or 'NO_DEFICIT'."
        )
        user_prompt = (
            f"User Query: {user_query}\n"
            f"Available Tools: {json.dumps(available_tools)}\n\n"
            "Does this query require a capability not in the available tools list?"
        )
        response = self._call_local_llm(system_prompt, user_prompt)

        if "DEFICIT:" in response.upper():
            match = re.search(r"DEFICIT:\s*(.*)", response, re.IGNORECASE)
            description = match.group(1).strip() if match else response
            return True, description
        return False, ""

    def research_skill(self, deficit_description: str) -> str:
        """LLM researches CLI syntax, flags, binary dependencies, and security considerations.

        Returns structured research notes string.
        """
        system_prompt = (
            "You are a senior systems engineer researching CLI tool capabilities. "
            "Provide structured research notes including: exact CLI syntax, required flags, "
            "binary dependencies, security considerations, and whether the tool requires "
            "network access (which would require MCP routing)."
        )
        user_prompt = f"Research the following capability deficit:\n{deficit_description}"
        return self._call_local_llm(system_prompt, user_prompt)

    def draft_skill(self, research_notes: str, deficit_description: str, skill_slug: str) -> str:
        """LLM drafts a complete OpenClaw SKILL.md from research notes.

        Creates draft directory and writes the file. Returns the draft file path.
        """
        system_prompt = (
            "You are a D.I.A.N.A. OS skill author. Write a complete OpenClaw SKILL.md file.\n"
            "REQUIRED FORMAT:\n"
            "1. YAML frontmatter with: name, description, metadata.openclaw.requires.bins\n"
            "2. Instruction body with fenced ```bash code blocks containing CLI commands\n"
            "3. Do NOT include commands that access core_geometries, qdrant_storage, or genesis files\n"
            "4. Do NOT bypass any verification crucible\n"
            "5. Output ONLY the SKILL.md content, no explanations."
        )
        user_prompt = (
            f"Deficit: {deficit_description}\n"
            f"Research Notes:\n{research_notes}\n\n"
            f"Write the SKILL.md now."
        )
        draft_content = self._call_local_llm(system_prompt, user_prompt)

        draft_dir = os.path.join(BASE_DIR, "skills", "draft_skills", skill_slug)
        os.makedirs(draft_dir, exist_ok=True)
        draft_path = os.path.join(draft_dir, "SKILL.md")

        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(draft_content)

        logger.info(f"[SKILL FORGE] Draft written to {draft_path}")
        return draft_path

    def verify_and_correct(self, draft_path: str) -> Tuple[bool, Dict[str, Any]]:
        """Submits draft to Z3 Crucible with self-correction feedback loop.

        Implements the 3-Strike Rule:
        - If Z3 rejects, feeds contradiction report back to LLM as corrective context
        - Local LLM attempts correction first
        - After 2 consecutive local failures, escalates to cloud IF bridge enabled
        - Halts after 3 strikes (hallucination loop protection)

        Returns:
            (is_valid, proof_result)
        """
        from engine.z3_crucible import verify_skill_file

        local_failures = 0

        for attempt in range(self.MAX_Z3_RETRIES):
            self._z3_attempt_count = attempt + 1
            proof_result = verify_skill_file(draft_path)

            if proof_result.get("mathematically_valid"):
                logger.info(f"[SKILL FORGE] Z3 Crucible SATISFIED on attempt {attempt + 1}")
                return True, proof_result

            # Z3 Rejection — construct correction context
            report = proof_result.get("report", "Unknown Z3 contradiction")
            logger.warning(f"[SKILL FORGE] Z3 REJECTED (attempt {attempt + 1}/{self.MAX_Z3_RETRIES}): {report}")

            if attempt >= self.MAX_Z3_RETRIES - 1:
                break  # 3-Strike Rule: don't attempt another correction

            # Read current draft for correction context
            try:
                with open(draft_path, "r", encoding="utf-8") as f:
                    current_draft = f.read()
            except Exception:
                current_draft = ""

            correction_prompt = (
                f"Your previous skill draft was REJECTED by the Z3 SMT Crucible.\n"
                f"Contradiction Report: {report}\n\n"
                f"Current Draft:\n{current_draft}\n\n"
                f"Rewrite the SKILL.md to resolve this logical violation.\n"
                f"RULES:\n"
                f"- Do NOT include commands that access core_geometries, qdrant_storage, genesis_geometries\n"
                f"- Do NOT bypass the crucible or any verification system\n"
                f"- Include proper YAML frontmatter with name and description\n"
                f"- Include at least one fenced ```bash code block with safe CLI commands\n"
                f"- Output ONLY the corrected SKILL.md content."
            )

            # Escalation: local first, cloud after 2 consecutive local failures
            local_failures += 1
            if local_failures >= 2 and self._is_cloud_bridge_enabled():
                logger.info("[SKILL FORGE] Escalating correction to Cloud Bridge (Gemini)...")
                corrected_content = self._call_cloud_llm(correction_prompt)
            else:
                corrected_content = self._call_local_llm(
                    "You are an expert system corrector resolving Z3 SMT violations.",
                    correction_prompt
                )

            # Overwrite draft with corrected content
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(corrected_content)

        # All retries exhausted — 3-Strike halt
        logger.error("[SKILL FORGE] 3-Strike Rule: Skill forge halted after max Z3 rejections.")
        return False, proof_result

    def graduate_and_load(
        self,
        draft_path: str,
        proof_result: Dict[str, Any],
        author: str = "skill-forge"
    ) -> Tuple[bool, str]:
        """Graduates a verified skill and invalidates the hot-loader cache.

        Attaches forge metadata (LLM calls, Z3 attempts, provider) to the registry record.
        """
        from core.skill_registry import skill_registry
        from core.skill_loader import skill_loader

        forge_metadata = {
            "deficit_detected_at": datetime.now().isoformat(),
            "total_llm_calls": self._llm_call_count,
            "z3_attempts": self._z3_attempt_count,
            "forged_by": self._forged_by,
            "escalated_to_cloud": self._forged_by == "hybrid"
        }

        success, message = skill_registry.graduate_skill(
            draft_path=draft_path,
            z3_proof_result=proof_result,
            author=author,
            forged_by=self._forged_by,
            llm_forge_metadata=forge_metadata
        )

        if success:
            skill_loader.invalidate_cache()
            logger.info(f"[SKILL FORGE] Graduation successful. Hot-loader cache invalidated.")

        return success, message

    def forge_full_cycle(
        self,
        user_query: str,
        available_tools: Optional[List[str]] = None,
        target_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """Runs the complete deficit→research→draft→Z3→correct→graduate pipeline.

        Resets counters, enforces budget ceiling, and returns full forge report.
        """
        self._llm_call_count = 0
        self._z3_attempt_count = 0
        self._forged_by = "local"
        available_tools = available_tools or []

        try:
            # 1. Deficit Detection
            is_deficit, deficit_desc = self.detect_deficit(user_query, available_tools)
            if not is_deficit:
                return {
                    "success": False,
                    "skill_id": None,
                    "message": "No capability deficit detected. Available tools are sufficient.",
                    "llm_calls_used": self._llm_call_count,
                    "z3_attempts": 0,
                    "forged_by": self._forged_by
                }

            # 2. Research
            research_notes = self.research_skill(deficit_desc)

            # 3. Draft
            skill_slug = target_slug if target_slug else self._generate_slug(deficit_desc)
            draft_path = self.draft_skill(research_notes, deficit_desc, skill_slug)

            # 4. Z3 Verification + Self-Correction Loop
            is_valid, proof_result = self.verify_and_correct(draft_path)
            if not is_valid:
                return {
                    "success": False,
                    "skill_id": skill_slug,
                    "message": f"3-Strike Rule: Skill failed Z3 verification after {self.MAX_Z3_RETRIES} attempts.",
                    "llm_calls_used": self._llm_call_count,
                    "z3_attempts": self._z3_attempt_count,
                    "forged_by": self._forged_by,
                    "last_z3_report": proof_result.get("report", "")
                }

            # 5. Graduate & Hot-Load
            success, grad_msg = self.graduate_and_load(draft_path, proof_result)

            return {
                "success": success,
                "skill_id": skill_slug,
                "message": grad_msg,
                "llm_calls_used": self._llm_call_count,
                "z3_attempts": self._z3_attempt_count,
                "forged_by": self._forged_by
            }

        except RuntimeError as e:
            # Budget ceiling hit
            return {
                "success": False,
                "skill_id": None,
                "message": str(e),
                "llm_calls_used": self._llm_call_count,
                "z3_attempts": self._z3_attempt_count,
                "forged_by": self._forged_by
            }
        except Exception as e:
            logger.error(f"[SKILL FORGE] Forge cycle failed: {e}")
            return {
                "success": False,
                "skill_id": None,
                "message": f"Forge cycle error: {str(e)}",
                "llm_calls_used": self._llm_call_count,
                "z3_attempts": self._z3_attempt_count,
                "forged_by": self._forged_by
            }

    def enhance_skill(self, skill_id: str, enhancement_request: str) -> Dict[str, Any]:
        """Loads an existing graduated skill, proposes LLM-driven enhancements,
        re-verifies through Z3, and re-graduates with version bump.

        Returns result dict with success, message, and skill_id.
        """
        self._llm_call_count = 0
        self._z3_attempt_count = 0
        self._forged_by = "local"

        try:
            # Load existing skill content from graduated directory
            existing_path = os.path.join(BASE_DIR, "skills", "graduated", skill_id, "SKILL.md")
            if not os.path.exists(existing_path):
                return {"success": False, "message": f"Graduated skill '{skill_id}' not found.", "skill_id": skill_id}

            with open(existing_path, "r", encoding="utf-8") as f:
                current_content = f.read()

            # LLM enhancement
            system_prompt = (
                "You are a D.I.A.N.A. OS skill enhancer. Modify the existing SKILL.md according "
                "to the enhancement request while preserving the YAML frontmatter structure "
                "and including at least one fenced ```bash code block. "
                "Output ONLY the enhanced SKILL.md content."
            )
            user_prompt = (
                f"Enhancement Request: {enhancement_request}\n\n"
                f"Current SKILL.md:\n{current_content}"
            )
            enhanced_content = self._call_local_llm(system_prompt, user_prompt)

            # Write to draft directory for verification
            draft_dir = os.path.join(BASE_DIR, "skills", "draft_skills", skill_id)
            os.makedirs(draft_dir, exist_ok=True)
            draft_path = os.path.join(draft_dir, "SKILL.md")
            with open(draft_path, "w", encoding="utf-8") as f:
                f.write(enhanced_content)

            # Z3 verify + correct
            is_valid, proof_result = self.verify_and_correct(draft_path)
            if not is_valid:
                return {
                    "success": False,
                    "message": "Enhanced skill failed Z3 verification after corrections.",
                    "skill_id": skill_id
                }

            # Graduate with version bump (registry handles incrementing)
            success, msg = self.graduate_and_load(draft_path, proof_result, author="skill-forge-enhancer")
            return {"success": success, "message": msg, "skill_id": skill_id}

        except Exception as e:
            logger.error(f"[SKILL FORGE] Enhancement failed for '{skill_id}': {e}")
            return {"success": False, "message": str(e), "skill_id": skill_id}


# Module-level singleton
skill_forge = SkillForge()
