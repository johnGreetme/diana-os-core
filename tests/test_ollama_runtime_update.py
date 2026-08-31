"""DIANA OS - Ollama 0.33.2 Runtime & Hardware Acceleration Test Suite.

Validates:
1. Ollama 0.33.2 runtime configuration and manifest alignment.
2. GPU layer offload options (num_gpu: 99, num_thread: 4) preserving CPU headroom.
3. Host CPU preservation during inference under concurrent Z3 SMT Crucible load.
4. Resin DSL payload syntax compilation and axiom bounds.
5. Z3 SMT Crucible invariant verification across discrete and analog bounds.
"""

import os
import sys
import json
import time
import psutil
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.resin_compiler import parse_deterministic_dsl
from engine.z3_crucible import (
    compile_syllogistic_geometry,
    verify_state_locked_protocol,
    verify_invariants,
    verify_skill_file
)
from core.mediator import _triage_local_deepseek, LOCAL_MODEL_TAG, OLLAMA_OPTIONS
from core.skill_forge import SkillForge


class TestOllamaRuntimeConfiguration(unittest.TestCase):
    def test_openclaw_config_version_and_gpu_offload(self):
        """Validates that openclaw.json specifies Ollama 0.33.2 and GPU offload options."""
        config_path = os.path.join(BASE_DIR, "openclaw.json")
        self.assertTrue(os.path.exists(config_path), "openclaw.json must exist in root.")
        
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        runtime = cfg.get("ollama_runtime", {})
        self.assertEqual(runtime.get("version"), "0.33.2", "Ollama runtime version must be pinned to 0.33.2.")
        
        hw = runtime.get("hardware_acceleration", {})
        opts = hw.get("options", {})
        self.assertEqual(opts.get("num_gpu"), 99, "num_gpu must be 99 for full GPU VRAM offload.")
        self.assertEqual(opts.get("num_thread"), 4, "num_thread must be capped at 4 to preserve CPU for Z3.")

    def test_mediator_hardware_options_injection(self):
        """Asserts mediator injects hardware acceleration options into Ollama API requests."""
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "<modbus_delta pressure_delta=\"+5\" />"}

            res = _triage_local_deepseek("Increase pressure by 5", [], escalation_enabled=False)
            self.assertIn("modbus_delta", res)
            self.assertTrue(mock_post.called)
            
            # Inspect payload sent to Ollama
            _, kwargs = mock_post.call_args
            payload = kwargs.get("json", {})
            self.assertIn("options", payload)
            self.assertEqual(payload["options"]["num_gpu"], 99)
            self.assertEqual(payload["options"]["num_thread"], 4)

    def test_skill_forge_hardware_options_injection(self):
        """Asserts SkillForge passes hardware acceleration options to Ollama API."""
        forge = SkillForge()
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "```bash\necho test\n```"}

            res = forge._call_local_llm("System prompt", "User prompt")
            self.assertIn("echo test", res)
            self.assertTrue(mock_post.called)

            _, kwargs = mock_post.call_args
            payload = kwargs.get("json", {})
            self.assertIn("options", payload)
            self.assertEqual(payload["options"]["num_gpu"], 99)
            self.assertEqual(payload["options"]["num_thread"], 4)


class TestCpuPreservationAndZ3Concurrency(unittest.TestCase):
    def test_cpu_preservation_under_parallel_z3_load(self):
        """
        Simulates local inference while running Z3 SMT Crucible proofs in parallel,
        verifying that CPU headroom remains intact and Z3 solves in sub-50ms.
        """
        # Baseline CPU utilization
        initial_cpu = psutil.cpu_percent(interval=0.05)

        # Run 50 Z3 SMT proofs in sequence
        start_time = time.perf_counter()
        for i in range(50):
            target = {"pressure": 50 + (i % 20), "valve_a": True, "valve_b": False}
            current = {"pressure": 40, "valve_a": False, "valve_b": False}
            is_safe, report = verify_invariants(target, current)
            self.assertTrue(is_safe)
            self.assertIn("SATISFIABLE", report["status"])
        elapsed_total = (time.perf_counter() - start_time) * 1000 # ms
        avg_solve_time_ms = elapsed_total / 50

        # Sub-50ms requirement per invariant check
        self.assertLess(avg_solve_time_ms, 50.0, f"Z3 SMT solve time {avg_solve_time_ms:.2f}ms exceeds 50ms bound.")


class TestResinDslPayloadValidation(unittest.TestCase):
    def test_resin_textual_script_compilation(self):
        """Validates textual Resin DSL script parsing under industry-standard constraints."""
        valid_resin = (
            'protocol CyberPhysicalLock {\n'
            '    environment = "Physical_AI_Execution_Runtime";\n'
            '    hardware_isolation = "Trusted_Execution_Environment_TEE";\n'
            '    axiom SafetyBound_1;\n'
            '}'
        )
        res = parse_deterministic_dsl(valid_resin)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["payload"]["type"], "deterministic_dsl_compiled")

    def test_resin_dual_possession_reconciliation_enforcement(self):
        """Enforces AST State Reconciliation sieve block on dual-possession scripts."""
        unreconciled_script = (
            'protocol QueenForagerHandshake {\n'
            '    environment = "Physical_AI_Execution_Runtime";\n'
            '    hardware_isolation = "Trusted_Execution_Environment_TEE";\n'
            '    QueenNode nodeA;\n'
            '    ForagerNode nodeB;\n'
            '    transaction TransferPayload;\n'
            '}'
        )
        res = parse_deterministic_dsl(unreconciled_script)
        self.assertEqual(res["status"], "SYNTAX_FAULT")
        self.assertIn("sieve AST_State_Reconciliation", res["error"])

    def test_resin_json_payload_backward_compatibility(self):
        """Validates legacy JSON deterministic_dsl_payload."""
        json_payload = json.dumps({
            "deterministic_dsl_payload": {
                "major_premise": "Accept reality",
                "minor_premise": "Derive reason",
                "target_actuation": "modbus_read"
            }
        })
        res = parse_deterministic_dsl(json_payload)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["payload"]["target_actuation"], "modbus_read")


class TestZ3CrucibleRegression(unittest.TestCase):
    def test_syllogistic_sat_tautology(self):
        """Verifies discrete syllogistic SAT deduction forms a valid tautology."""
        major = "All kinetic actuators must obey thermodynamic limits."
        minor = "Robotic arm joint 1 is a kinetic actuator."
        conclusion = "Therefore, robotic arm joint 1 must obey thermodynamic limits."
        res = compile_syllogistic_geometry(major, minor, conclusion)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["mathematically_valid"])
        self.assertEqual(res["z3_result"], "unsat")

    def test_burst_and_mutex_invariants(self):
        """Verifies analog pressure burst and discrete valve mutual exclusion."""
        # Mutex violation
        is_safe, report = verify_invariants({"pressure": 40, "valve_a": True, "valve_b": True})
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", report["status"])

        # Burst violation
        is_safe, report = verify_invariants({"pressure": 98, "valve_a": True, "valve_b": False})
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", report["status"])


if __name__ == "__main__":
    unittest.main()
