"""DIANA OS - Skill Hot-Loader & Runtime Injection Engine.

Dynamically loads graduated skills from the Auditable Skill Registry into
the LLM's active system prompt context at runtime. Provides in-memory
caching with configurable TTL and SHA-256 tamper detection.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REGISTRY_PATH = os.path.join(BASE_DIR, "ledger", "skills_registry.json")
DEFAULT_GRADUATED_DIR = os.path.join(BASE_DIR, "skills", "graduated")
AUDIT_LOG_PATH = os.path.join(BASE_DIR, "reflections", "skills_audit.log")


class SkillLoader:
    """In-memory skill hot-loader with TTL cache and SHA-256 integrity verification.

    Loads all active graduated skills from the Auditable Skill Registry,
    verifies their cryptographic hashes against the registry ledger, and
    provides formatted instruction blocks for LLM system prompt injection.
    """

    CACHE_TTL: int = 60  # Cache auto-expires after 60 seconds

    def __init__(
        self,
        registry_path: str = DEFAULT_REGISTRY_PATH,
        graduated_dir: str = DEFAULT_GRADUATED_DIR
    ):
        self.registry_path = registry_path
        self.graduated_dir = graduated_dir
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded_at: float = 0.0

    def _hash_file(self, file_path: str) -> str:
        """Computes SHA-256 digest of a file using raw bytes (matches skill_registry)."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
        except FileNotFoundError:
            return ""
        return sha256.hexdigest()

    def _log_integrity_breach(self, skill_id: str, expected_hash: str, actual_hash: str) -> None:
        """Logs SHA-256 integrity breach to reflections/skills_audit.log (JSON-lines)."""
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "INTEGRITY_BREACH",
            "skill_id": skill_id,
            "expected_hash": expected_hash,
            "actual_hash": actual_hash,
            "action": "SKILL_QUARANTINED"
        }
        try:
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            logger.error(f"[SKILL LOADER] INTEGRITY_BREACH for skill '{skill_id}' — quarantined.")
        except Exception as e:
            logger.error(f"[SKILL LOADER] Failed to write audit log: {e}")

    def load_all(self) -> None:
        """Reads skills_registry.json and loads all active graduated skills into cache.

        For each skill:
        - Reads the graduated SKILL.md file
        - Computes live SHA-256 hash of the file (raw bytes)
        - Compares against sha256_hash in registry
        - If mismatch → logs INTEGRITY_BREACH, quarantines (skips) the skill
        - If match → stores in cache with content, metadata, and timestamp
        - Skips skills with status 'deprecated' or 'revoked'
        """
        if not os.path.exists(self.registry_path):
            logger.warning(f"[SKILL LOADER] Registry not found: {self.registry_path}")
            self._cache = {}
            self._cache_loaded_at = time.time()
            return

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception as e:
            logger.error(f"[SKILL LOADER] Failed to parse registry: {e}")
            self._cache = {}
            self._cache_loaded_at = time.time()
            return

        new_cache: Dict[str, Dict[str, Any]] = {}
        skills_dict = registry.get("skills", {})

        for skill_id, meta in skills_dict.items():
            # Filter by lifecycle status — only load active skills
            status = meta.get("status", "active")
            if status in ("deprecated", "revoked"):
                continue

            # Resolve graduated skill file path (skills/graduated/<slug>/SKILL.md)
            skill_file = os.path.join(self.graduated_dir, skill_id, "SKILL.md")
            if not os.path.exists(skill_file):
                # Fallback: check installed_path from registry
                alt_path = meta.get("installed_path", "")
                if os.path.exists(alt_path):
                    skill_file = alt_path
                else:
                    logger.warning(f"[SKILL LOADER] Skill file missing for '{skill_id}': {skill_file}")
                    continue

            # SHA-256 integrity verification (raw bytes, matches registry computation)
            actual_hash = self._hash_file(skill_file)
            expected_hash = meta.get("sha256_hash", "")

            if expected_hash and actual_hash != expected_hash:
                self._log_integrity_breach(skill_id, expected_hash, actual_hash)
                continue  # Quarantine — do not load tampered skill

            # Load skill content into cache
            try:
                with open(skill_file, "r", encoding="utf-8") as sf:
                    content = sf.read()

                new_cache[skill_id] = {
                    "content": content,
                    "metadata": meta,
                    "loaded_at": time.time()
                }
            except Exception as e:
                logger.error(f"[SKILL LOADER] Error loading skill '{skill_id}': {e}")

        self._cache = new_cache
        self._cache_loaded_at = time.time()
        logger.info(f"[SKILL LOADER] Loaded {len(new_cache)} active skill(s) into memory cache.")

    def is_cache_valid(self) -> bool:
        """Returns True if cache is loaded and TTL hasn't expired."""
        return self._cache_loaded_at > 0 and (time.time() - self._cache_loaded_at) < self.CACHE_TTL

    def invalidate_cache(self) -> None:
        """Clears in-memory cache, forcing full reload on next access."""
        self._cache = {}
        self._cache_loaded_at = 0.0
        logger.info("[SKILL LOADER] Cache invalidated — will reload on next access.")

    def get_skill_context(self, skill_id: str) -> Optional[str]:
        """Returns the instruction body of a single skill from cache.

        Auto-calls load_all() if cache is expired or empty.
        """
        if not self.is_cache_valid():
            self.load_all()

        entry = self._cache.get(skill_id)
        if entry:
            return entry.get("content")
        return None

    def get_all_skill_contexts(self) -> str:
        """Returns a formatted string block containing ALL active graduated skill
        instructions, suitable for injection into an LLM system prompt.

        Format:
            ## Available Learned Skills

            ### Skill: <name> (v<version>)
            <SKILL.md instruction body>

        Returns empty string if no skills are loaded.
        Auto-calls load_all() if cache is expired.
        """
        if not self.is_cache_valid():
            self.load_all()

        if not self._cache:
            return ""

        sections = ["## Available Learned Skills\n"]
        for skill_id, data in self._cache.items():
            meta = data["metadata"]
            name = meta.get("skill_id", skill_id)
            version = meta.get("version", 1)
            content = data["content"]
            sections.append(f"### Skill: {name} (v{version})\n{content}\n")

        return "\n".join(sections)

    def get_loaded_skill_ids(self) -> list:
        """Returns list of currently loaded active skill IDs."""
        if not self.is_cache_valid():
            self.load_all()
        return list(self._cache.keys())


# Module-level singleton
skill_loader = SkillLoader()
