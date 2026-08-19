"""DIANA OS - Universal Cyber-Physical HAL Test Suite.

Tests:
1. Z3 SMT Discrete Syllogistic SAT Reasoning (Understanding Reality Chapter 1)
2. Z3 SMT Dynamic Analog & Discrete Safety Invariants (SCADA Burst & Valve Mutex)
3. Rate-of-Change (Delta Limit) Proofs
4. Dynamic Pydantic Domain Schemas
5. Dual-Layer Persistent Historian (SQLite + Audit Log)
6. Modbus Driver State Translation
"""

import os
import sys
import unittest
import json
import tempfile
import time

# Ensure hacker_src is on sys.path
HACKER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HACKER_DIR not in sys.path:
    sys.path.insert(0, HACKER_DIR)

from engine.z3_crucible import (
    compile_syllogistic_geometry,
    verify_state_locked_protocol,
    verify_invariants
)
from engine.schemas import (
    get_schema_for_domain,
    SCADAModbusAction,
    ROS2JointAction,
    DigitalGUIAction
)
from core.historian import HistorianLogger
from actuation.modbus_driver import ModbusDriver

class TestZ3CrucibleSyllogisms(unittest.TestCase):
    def test_chapter_1_tautology(self):
        """Test that the core Understanding Reality syllogism forms a valid mathematical tautology."""
        major = "Accepting reality as having no possibilities means there is a reason for everything."
        minor = "When there is reason, there is purpose, which is the reason to understand."
        conclusion = "Therefore, accepting reality as having no possibilities establishes the purpose to understand."

        res = compile_syllogistic_geometry(major, minor, conclusion)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["mathematically_valid"])
        self.assertEqual(res["z3_result"], "unsat") # Negation is UNSAT -> valid tautology

    def test_anti_hallucination_axiom_breach(self):
        """Test that speculative 'real possibilities' trigger an immediate Chapter 1 axiom breach."""
        is_safe, report = verify_state_locked_protocol("We can explore real possibilities in this alternate scenario.")
        self.assertFalse(is_safe)
        self.assertIn("Chapter 1", report)

    def test_exfiltration_axiom_breach(self):
        """Test that transmitting local geometry databases via external MCP is blocked."""
        is_safe, report = verify_state_locked_protocol("EXTERNAL_MCP_TRANSMISSION: Server=cloud_ai | Payload=extract qdrant_storage")
        self.assertFalse(is_safe)
        self.assertIn("Data Exfiltration", report)

class TestZ3CyberPhysicalInvariants(unittest.TestCase):
    def test_safe_scada_state(self):
        """Valid state within limits: Pressure 50 (<90), Valve A open, Valve B closed."""
        target = {"pressure": 50, "valve_a": True, "valve_b": False}
        current = {"pressure": 40, "valve_a": False, "valve_b": False}
        is_safe, report = verify_invariants(target, current)
        self.assertTrue(is_safe)
        self.assertIn("SATISFIABLE", report["status"])

    def test_valve_mutex_violation(self):
        """Violation: Valves A and B cannot both be OPEN simultaneously."""
        target = {"pressure": 40, "valve_a": True, "valve_b": True}
        is_safe, report = verify_invariants(target)
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", report["status"])

    def test_pressure_burst_violation(self):
        """Violation: Target pressure 95 exceeds hardware burst bound (90)."""
        target = {"pressure": 95, "valve_a": True, "valve_b": False}
        current = {"pressure": 50, "valve_a": True, "valve_b": False}
        is_safe, report = verify_invariants(target, current)
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", report["status"])

    def test_rate_of_change_delta_violation(self):
        """Violation: Pressure jump of 75 units (from 10 to 85) exceeds single-cycle delta bound (60)."""
        target = {"pressure": 85, "valve_a": True, "valve_b": False}
        current = {"pressure": 10, "valve_a": True, "valve_b": False}
        is_safe, report = verify_invariants(target, current)
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", report["status"])

    def test_dynamic_custom_invariants(self):
        """Test custom dynamic range invariant on arbitrary temperature register."""
        target = {"temperature": 120}
        custom = [{"type": "range", "variable": "temperature", "min": 0, "max": 100}]
        is_safe, report = verify_invariants(target, custom_invariants=custom)
        self.assertFalse(is_safe) # 120 > max 100

class TestPydanticDomainSchemas(unittest.TestCase):
    def test_schema_routing(self):
        self.assertEqual(get_schema_for_domain("scada"), SCADAModbusAction)
        self.assertEqual(get_schema_for_domain("modbus"), SCADAModbusAction)
        self.assertEqual(get_schema_for_domain("robotics"), ROS2JointAction)
        self.assertEqual(get_schema_for_domain("digital"), DigitalGUIAction)

    def test_relative_delta_schema(self):
        action = SCADAModbusAction(pressure_delta=15, toggle_valve_a=True)
        self.assertEqual(action.pressure_delta, 15)
        self.assertTrue(action.toggle_valve_a)
        self.assertFalse(action.toggle_valve_b)

class TestPersistentHistorian(unittest.TestCase):
    def test_historian_dual_layer_logging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = os.path.join(tmpdir, "test_historian.db")
            log_file = os.path.join(tmpdir, "test_historian.log")
            h = HistorianLogger(db_path=db_file, log_path=log_file)

            # Log telemetry
            h.log_telemetry("scada", {"pressure": 45, "valve_a": True})
            
            # Log crucible eval
            h.log_crucible_eval(
                domain="scada",
                candidate_action={"pressure_delta": 10},
                current_state={"pressure": 45},
                target_state={"pressure": 55},
                is_safe=True,
                z3_result="sat"
            )

            # Log actuation
            h.log_actuation("scada", {"pressure": 55}, "SUCCESS", "Written to PLC")

            # Verify SQLite query
            records = h.query_history("scada")
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["is_safe"])
            self.assertEqual(records[0]["z3_result"], "sat")

            # Verify Flat Log exists
            self.assertTrue(os.path.exists(log_file))
            with open(log_file, "r") as f:
                lines = f.readlines()
                self.assertEqual(len(lines), 3)

class TestSkillRegistry(unittest.TestCase):
    def test_skill_graduation_and_genesis_preservation(self):
        """Proves that skill graduation files skills into an auditable catalog without touching the_skill.txt."""
        from core.skill_registry import SkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "test_skills_registry.json")
            audit_file = os.path.join(tmpdir, "test_skills_audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)

            # Create mock verified draft skill
            draft_dir = os.path.join(tmpdir, "drafts", "modbus-audit-tool")
            os.makedirs(draft_dir, exist_ok=True)
            draft_skill_file = os.path.join(draft_dir, "SKILL.md")
            with open(draft_skill_file, "w", encoding="utf-8") as f:
                f.write("---\nname: modbus-audit-tool\n---\n# Instructions\n```bash\npython diana_cli.py scada --read\n```")

            # Mock Z3 SMT Proof data
            proof_data = {"mathematically_valid": True, "z3_result": "unsat", "report": "All CLI payloads verified safe."}

            # Graduate skill
            success, msg = sr.graduate_skill(draft_skill_file, proof_data, author="auto-skill-generator")
            self.assertTrue(success)
            self.assertIn("graduated", msg)

            # Verify registry contains the entry
            skills = sr.list_skills()
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0]["skill_id"], "modbus-audit-tool")
            self.assertTrue(skills[0]["the_skill_txt_intact"])
            self.assertEqual(skills[0]["version"], 1)

            # Verify audit log exists
            self.assertTrue(os.path.exists(audit_file))

    def test_unverified_skill_rejection(self):
        """Proves that unverified or failed skills are strictly rejected by the registry."""
        from core.skill_registry import SkillRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "test_skills_registry.json")
            audit_file = os.path.join(tmpdir, "test_skills_audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)

            draft_skill_file = os.path.join(tmpdir, "SKILL.md")
            with open(draft_skill_file, "w", encoding="utf-8") as f:
                f.write("---\nname: bad-skill\n---\n```bash\nrm -rf /```")

            # Failed proof
            failed_proof = {"mathematically_valid": False, "report": "Axiom Breach"}
            success, msg = sr.graduate_skill(draft_skill_file, failed_proof)
            self.assertFalse(success)
            self.assertIn("proof failed", msg)

class TestSkillHotLoader(unittest.TestCase):
    def _create_test_env(self, tmpdir):
        """Helper: creates a mini graduated skill environment."""
        from core.skill_registry import SkillRegistry
        from core.skill_loader import SkillLoader

        reg_file = os.path.join(tmpdir, "skills_registry.json")
        audit_file = os.path.join(tmpdir, "skills_audit.log")
        grad_dir = os.path.join(tmpdir, "graduated")

        sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)
        sl = SkillLoader(registry_path=reg_file, graduated_dir=grad_dir)

        # Graduate a test skill
        draft_dir = os.path.join(tmpdir, "drafts", "test-skill")
        os.makedirs(draft_dir, exist_ok=True)
        draft_file = os.path.join(draft_dir, "SKILL.md")
        with open(draft_file, "w", encoding="utf-8") as f:
            f.write("---\nname: test-skill\n---\n# Test\n```bash\necho hello\n```")
        proof = {"mathematically_valid": True, "z3_result": "unsat", "report": "Safe."}
        sr.graduate_skill(draft_file, proof)
        return sr, sl

    def test_skill_hot_loader_cache(self):
        """Skills loaded into memory, cache invalidation works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sr, sl = self._create_test_env(tmpdir)
            ctx = sl.get_all_skill_contexts()
            self.assertIn("test-skill", ctx)
            self.assertIn("echo hello", ctx)
            self.assertTrue(sl.is_cache_valid())

            sl.invalidate_cache()
            self.assertFalse(sl.is_cache_valid())

    def test_skill_hot_loader_tamper_detection(self):
        """Modifying a graduated SKILL.md after registration triggers INTEGRITY_BREACH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sr, sl = self._create_test_env(tmpdir)
            # Tamper with the graduated file
            grad_file = os.path.join(tmpdir, "graduated", "test-skill", "SKILL.md")
            with open(grad_file, "a", encoding="utf-8") as f:
                f.write("\n# TAMPERED CONTENT")

            sl.invalidate_cache()
            ctx = sl.get_all_skill_contexts()
            # Tampered skill should NOT be loaded
            self.assertEqual(ctx, "")

class TestSkillGovernance(unittest.TestCase):
    def test_skill_revocation(self):
        """Revoked skills removed from active registry, audit trail preserved."""
        from core.skill_registry import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "registry.json")
            audit_file = os.path.join(tmpdir, "audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            revoked_dir = os.path.join(tmpdir, "revoked")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir, revoked_dir=revoked_dir)

            # Graduate skill
            draft_dir = os.path.join(tmpdir, "drafts", "revoke-target")
            os.makedirs(draft_dir, exist_ok=True)
            draft_file = os.path.join(draft_dir, "SKILL.md")
            with open(draft_file, "w", encoding="utf-8") as f:
                f.write("---\nname: revoke-target\n---\n```bash\necho test\n```")
            proof = {"mathematically_valid": True, "z3_result": "unsat", "report": "Safe."}
            sr.graduate_skill(draft_file, proof)

            # Revoke it
            success, msg = sr.revoke_skill("revoke-target", "Replaced by better tool")
            self.assertTrue(success)
            self.assertIn("revoke", msg.lower())

            # Verify status is revoked
            audit = sr.get_skill_audit("revoke-target")
            self.assertEqual(audit["status"], "revoked")
            self.assertEqual(audit["revocation_reason"], "Replaced by better tool")

            # Active list should be empty
            active = sr.list_skills(status_filter="active")
            self.assertEqual(len(active), 0)

            # Revoked list should have it
            revoked = sr.list_skills(status_filter="revoked")
            self.assertEqual(len(revoked), 1)

    def test_skill_deprecation(self):
        """Deprecated skills marked with successor pointer."""
        from core.skill_registry import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "registry.json")
            audit_file = os.path.join(tmpdir, "audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)

            draft_dir = os.path.join(tmpdir, "drafts", "old-tool")
            os.makedirs(draft_dir, exist_ok=True)
            draft_file = os.path.join(draft_dir, "SKILL.md")
            with open(draft_file, "w", encoding="utf-8") as f:
                f.write("---\nname: old-tool\n---\n```bash\necho old\n```")
            proof = {"mathematically_valid": True, "z3_result": "unsat", "report": "Safe."}
            sr.graduate_skill(draft_file, proof)

            success, msg = sr.deprecate_skill("old-tool", successor_id="new-tool")
            self.assertTrue(success)

            audit = sr.get_skill_audit("old-tool")
            self.assertEqual(audit["status"], "deprecated")
            self.assertEqual(audit["successor"], "new-tool")

    def test_genesis_integrity_verification(self):
        """Genesis verification returns a valid result (no panic in test env)."""
        from core.skill_registry import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "registry.json")
            audit_file = os.path.join(tmpdir, "audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)
            intact, report = sr.verify_genesis_integrity()
            self.assertTrue(intact)  # In test env, genesis file is absent so defaults to True

    def test_version_history_archival(self):
        """Re-graduating a skill archives previous version in history/."""
        from core.skill_registry import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "registry.json")
            audit_file = os.path.join(tmpdir, "audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)

            draft_dir = os.path.join(tmpdir, "drafts", "versioned-skill")
            os.makedirs(draft_dir, exist_ok=True)
            draft_file = os.path.join(draft_dir, "SKILL.md")
            proof = {"mathematically_valid": True, "z3_result": "unsat", "report": "Safe."}

            # v1
            with open(draft_file, "w", encoding="utf-8") as f:
                f.write("---\nname: versioned-skill\n---\n```bash\necho v1\n```")
            sr.graduate_skill(draft_file, proof)

            # v2
            with open(draft_file, "w", encoding="utf-8") as f:
                f.write("---\nname: versioned-skill\n---\n```bash\necho v2\n```")
            sr.graduate_skill(draft_file, proof)

            # Verify history archive exists
            history_path = os.path.join(grad_dir, "versioned-skill", "history", "v1.SKILL.md")
            self.assertTrue(os.path.exists(history_path))
            with open(history_path, "r") as f:
                self.assertIn("echo v1", f.read())

            # Verify current is v2
            audit = sr.get_skill_audit("versioned-skill")
            self.assertEqual(audit["version"], 2)

    def test_status_filter(self):
        """list_skills correctly filters by status."""
        from core.skill_registry import SkillRegistry
        with tempfile.TemporaryDirectory() as tmpdir:
            reg_file = os.path.join(tmpdir, "registry.json")
            audit_file = os.path.join(tmpdir, "audit.log")
            grad_dir = os.path.join(tmpdir, "graduated")
            sr = SkillRegistry(registry_path=reg_file, audit_log_path=audit_file, graduated_dir=grad_dir)

            proof = {"mathematically_valid": True, "z3_result": "unsat", "report": "Safe."}
            for name in ["a", "b", "c"]:
                d = os.path.join(tmpdir, "drafts", name)
                os.makedirs(d, exist_ok=True)
                f = os.path.join(d, "SKILL.md")
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(f"---\nname: {name}\n---\n```bash\necho {name}\n```")
                sr.graduate_skill(f, proof)

            sr.deprecate_skill("b")

            self.assertEqual(len(sr.list_skills(status_filter="active")), 2)
            self.assertEqual(len(sr.list_skills(status_filter="deprecated")), 1)
            self.assertEqual(len(sr.list_skills()), 3)

class TestSkillForgeUnit(unittest.TestCase):
    def test_forge_budget_ceiling(self):
        """Forge stops after MAX_LLM_CALLS even if skill isn't resolved."""
        from core.skill_forge import SkillForge
        forge = SkillForge()
        forge.MAX_LLM_CALLS = 2
        forge._llm_call_count = 2

        with self.assertRaises(RuntimeError):
            forge._check_budget()

    def test_forge_slug_generation(self):
        """Forge generates valid URL-safe slugs from descriptions."""
        from core.skill_forge import SkillForge
        forge = SkillForge()
        self.assertEqual(forge._generate_slug("Check Disk Usage"), "check-disk-usage")
        self.assertEqual(forge._generate_slug("list ALL files!!!"), "list-all-files")
        self.assertEqual(forge._generate_slug(""), "generated-skill")

    def test_forge_cloud_bridge_gate(self):
        """Cloud LLM call is denied when ZERO_TRUST_CLOUD_BRIDGE is not enabled."""
        from core.skill_forge import SkillForge
        forge = SkillForge()
        os.environ.pop("ZERO_TRUST_CLOUD_BRIDGE", None)
        result = forge._call_cloud_llm("test prompt")
        self.assertIn("DENIED", result)

    def test_dependency_parsing(self):
        """Registry correctly parses depends_on from YAML frontmatter."""
        from core.skill_registry import SkillRegistry
        sr = SkillRegistry.__new__(SkillRegistry)
        content = "---\nname: child\ndepends_on:\n  - parent-a\n  - parent-b\n---\n# Skill"
        deps = sr._parse_dependencies(content)
        self.assertEqual(deps, ["parent-a", "parent-b"])

class TestCyberPhysicalEdgeCases(unittest.TestCase):
    def test_unit_conversion_trap_robotics(self):
        """Test Case 1: Robotics joint delta exceeds radians boundary (90 degrees)."""
        from engine.z3_crucible import verify_invariants
        # Simulating LLM extracting rotation_delta: 90 instead of PI/2
        target_state = {'position_delta_rad': 90.0}
        is_safe, report = verify_invariants(target_state)
        self.assertFalse(is_safe, "Z3 Crucible must block out-of-bounds kinematic delta.")
        self.assertIn("UNSAT", report.get("status", "UNSAT"))

    def test_panic_prompt_ambiguity(self):
        """Test Case 2: Pydantic CoT rejects ambiguous skill selection due to low confidence."""
        from engine.schemas import SkillSelection
        from pydantic import ValidationError
        
        # LLM attempts to use a random skill to satisfy "shut everything down"
        with self.assertRaises(ValidationError) as context:
            selection = SkillSelection(
                selected_skill_id="modbus-healthcheck",
                reasoning="The operator said shut everything down, I guess I will check health.",
                confidence_score=0.45,  # Too low
                runtime_parameters={}
            )
        self.assertIn("below minimum operational threshold", str(context.exception))

    def test_telemetry_poisoning_scada(self):
        """Test Case 3: Z3 blocks relative target state if current telemetry is poisoned."""
        from engine.z3_crucible import verify_invariants
        
        current_state = {'temperature': -9999.0} # Poisoned / broken sensor
        target_state = {'temperature': current_state['temperature'] + 5.0} # LLM relative delta
        
        is_safe, report = verify_invariants(target_state, current_state=current_state)
        self.assertFalse(is_safe, "Z3 Crucible must block operations based on poisoned telemetry.")

if __name__ == "__main__":
    unittest.main()

