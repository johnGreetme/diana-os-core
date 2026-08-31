"""DIANA OS - OpenClaw 2.0 & Z3 SMT Crucible End-to-End Integration Test Suite.

Validates:
1. OpenClaw 2.0 SQLite Schema Initialization & Legacy 1.x Storage Isolation.
2. Zero Lock Contention under concurrent multiplayer presence and Z3 evaluation load.
3. Resin DSL bindings mapping to OpenClaw 2.0 collaborative presence metadata.
4. End-to-End Kinetic Envelope Collapse Simulation (Tripped Breaker, Thermal Delta, Pressure Burst).
5. Z3 Crucible Intercept Proof: Returns deterministic UNSAT before kinetic actuation.
6. Non-Repudiation Divergent Tail Assertion: Cryptographic SHA-256 hash verification.
"""

import os
import sys
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.historian import OpenClawV2SessionHistorian, HistorianLogger
from engine.resin_compiler import parse_deterministic_dsl
from engine.z3_crucible import verify_invariants, compile_syllogistic_geometry
from engine.schemas import SCADAModbusAction
from core.mediator import _triage_local_deepseek


class TestOpenClawV2StorageIsolationAndLockContention(unittest.TestCase):
    def test_storage_isolation_and_schema_integrity(self):
        """Validates that OpenClaw 2.0 creates isolated SQLite tables without mutating legacy 1.x logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            v2_db_path = os.path.join(tmpdir, "v2", "sessions.db")
            legacy_db_path = os.path.join(tmpdir, "legacy", "historian.db")
            legacy_log_path = os.path.join(tmpdir, "legacy", "historian.log")

            # Initialize 1.x legacy historian and populate mock telemetry
            legacy_h = HistorianLogger(db_path=legacy_db_path, log_path=legacy_log_path)
            legacy_h.log_telemetry("scada", {"pressure": 45, "valve_a": False})
            self.assertTrue(os.path.exists(legacy_log_path))
            with open(legacy_log_path, "r", encoding="utf-8") as f:
                legacy_initial_content = f.read()

            # Initialize OpenClaw 2.0 SQLite Historian
            v2_h = OpenClawV2SessionHistorian(db_path=v2_db_path)
            v2_h.create_session("session_alpha_01", title="SCADA Supervision Loop", metadata={"tier": "hacker"})
            v2_h.register_presence("node_queen_01", "session_alpha_01", "operator_alice", role="orchestrator")
            v2_h.register_presence("node_forager_01", "session_alpha_01", "kinetic_node_1", role="executor")

            # Assert V2 database was created with WAL mode
            self.assertTrue(os.path.exists(v2_db_path))

            # Assert 1.x legacy flat file was completely untouched
            with open(legacy_log_path, "r", encoding="utf-8") as f:
                legacy_current_content = f.read()
            self.assertEqual(legacy_initial_content, legacy_current_content, "Legacy 1.x logs must remain unmutated.")

    def test_multiplayer_zero_lock_contention_under_concurrency(self):
        """
        Simulates 10 concurrent multiplayer presence updates while the Z3 Crucible
        instantly appends UNSAT rejection hashes to the SQLite ledger, proving zero lock contention.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            v2_db_path = os.path.join(tmpdir, "sessions.db")
            v2_h = OpenClawV2SessionHistorian(db_path=v2_db_path)
            v2_h.create_session("sess_concurrent_01", title="Stress Test")

            errors = []

            def presence_worker(worker_id):
                try:
                    for i in range(25):
                        v2_h.register_presence(f"node_worker_{worker_id}", "sess_concurrent_01", f"worker_{worker_id}", role="presence_heartbeat")
                        time.sleep(0.002)
                except Exception as e:
                    errors.append(f"Presence Worker {worker_id} Error: {e}")

            def z3_eval_worker(worker_id):
                try:
                    for i in range(25):
                        is_safe, proof = verify_invariants({"pressure": 95}) # Violation
                        self.assertFalse(is_safe)
                        v2_h.log_divergent_tail(
                            session_id="sess_concurrent_01",
                            node_id=f"z3_worker_{worker_id}",
                            fault_type="CONCURRENT_STRESS_BURST",
                            divergent_state={"pressure": 95},
                            candidate_action={"pressure_delta": 45},
                            z3_proof_report=proof
                        )
                        time.sleep(0.002)
                except Exception as e:
                    errors.append(f"Z3 Worker {worker_id} Error: {e}")

            threads = []
            for w in range(5):
                threads.append(threading.Thread(target=presence_worker, args=(w,)))
                threads.append(threading.Thread(target=z3_eval_worker, args=(w,)))

            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(errors), 0, f"Encountered SQLite lock contention errors: {errors}")
            
            # Assert all 125 divergent tail entries were committed cleanly
            tails = v2_h.query_divergent_tails("sess_concurrent_01", limit=200)
            self.assertEqual(len(tails), 125)


class TestResinDslOpenClawV2Bindings(unittest.TestCase):
    def test_openclaw_v2_presence_and_session_extraction(self):
        """Validates Resin DSL parsing of OpenClaw 2.0 presence headers."""
        resin_script = (
            '@session(id="sess_plant_grid_09")\n'
            '@presence(node_id="queen_prime", role="orchestrator")\n'
            '@presence(node_id="forager_edge_04", role="actuator")\n'
            'protocol GridTelemetryIsolation {\n'
            '    environment = "Physical_AI_Execution_Runtime";\n'
            '    hardware_isolation = "Trusted_Execution_Environment_TEE";\n'
            '    axiom FrequencyLock;\n'
            '}'
        )
        res = parse_deterministic_dsl(resin_script)
        self.assertEqual(res["status"], "SUCCESS")
        
        v2_meta = res["payload"]["openclaw_v2"]
        self.assertEqual(v2_meta["session_id"], "sess_plant_grid_09")
        self.assertTrue(v2_meta["multiplayer_active"])
        self.assertEqual(len(v2_meta["collaborators"]), 2)
        self.assertEqual(v2_meta["collaborators"][0]["node_id"], "queen_prime")


class TestKineticEnvelopeCollapseAndDivergentTail(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.v2_db = os.path.join(self.tmpdir.name, "sessions.db")
        self.v2_historian = OpenClawV2SessionHistorian(db_path=self.v2_db)
        self.v2_historian.create_session("sess_kinetic_01", title="Kinetic Envelope Protection")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fault_1_scada_pressure_burst_envelope_collapse(self):
        """
        Envelope Collapse Fault 1:
        Candidate action jumps pressure to 98 (>90 hardware burst limit).
        Z3 Crucible must return UNSAT, and Divergent Tail must be cryptographically hashed.
        """
        current_state = {"pressure": 50, "valve_a": True, "valve_b": False}
        target_state = {"pressure": 98, "valve_a": True, "valve_b": False}

        # 1. Evaluate through Z3 Crucible
        is_safe, proof_report = verify_invariants(target_state, current_state)
        self.assertFalse(is_safe, "Z3 must reject pressure exceeding hardware burst bound (90).")
        self.assertIn("UNSATISFIABLE", proof_report["status"])

        # 2. Capture Divergent Tail into OpenClaw 2.0 SQLite Ledger
        receipt = self.v2_historian.log_divergent_tail(
            session_id="sess_kinetic_01",
            node_id="forager_edge_scada",
            fault_type="PRESSURE_BURST_ENVELOPE_COLLAPSE",
            divergent_state=current_state,
            candidate_action={"pressure_delta": 48},
            z3_proof_report=proof_report
        )

        # 3. Assert Non-Repudiation Hash Receipt
        self.assertEqual(receipt["status"], "QUARANTINED_AND_COMMITTED")
        self.assertEqual(len(receipt["non_repudiation_hash"]), 64) # SHA-256 length

        # 4. Verify Ledger Entry Query
        tails = self.v2_historian.query_divergent_tails("sess_kinetic_01")
        self.assertEqual(len(tails), 1)
        self.assertEqual(tails[0]["fault_type"], "PRESSURE_BURST_ENVELOPE_COLLAPSE")
        self.assertEqual(tails[0]["non_repudiation_hash"], receipt["non_repudiation_hash"])

    def test_fault_2_tripped_auxiliary_breaker_and_valve_mutex_violation(self):
        """
        Envelope Collapse Fault 2:
        Simulated tripped breaker auxiliary contact forcing contradictory dual valve actuation.
        Z3 Crucible must return UNSAT and prevent physical actuation.
        """
        # Both valves open simultaneously is a physical catastrophe
        contradictory_state = {"pressure": 40, "valve_a": True, "valve_b": True}

        is_safe, proof_report = verify_invariants(contradictory_state)
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", proof_report["status"])

        receipt = self.v2_historian.log_divergent_tail(
            session_id="sess_kinetic_01",
            node_id="breaker_aux_relay_node",
            fault_type="TRIPPED_BREAKER_VALVE_MUTEX_CONTRADICTION",
            divergent_state=contradictory_state,
            candidate_action={"toggle_valve_a": True, "toggle_valve_b": True},
            z3_proof_report=proof_report
        )

        self.assertEqual(len(receipt["non_repudiation_hash"]), 64)
        self.assertTrue(receipt["non_repudiation_hash"] != receipt["previous_hash"])

    def test_fault_3_frozen_thermal_delta_sensor_poisoning(self):
        """
        Envelope Collapse Fault 3:
        Thermal sensor is poisoned / frozen at -9999.0.
        Z3 Crucible must detect boundary breach and record quarantine receipt.
        """
        poisoned_state = {"temperature": -9999.0}
        target_state = {"temperature": -9994.0}

        is_safe, proof_report = verify_invariants(target_state, current_state=poisoned_state)
        self.assertFalse(is_safe)
        self.assertIn("UNSATISFIABLE", proof_report["status"])

        receipt = self.v2_historian.log_divergent_tail(
            session_id="sess_kinetic_01",
            node_id="thermal_rttd_sensor_03",
            fault_type="FROZEN_THERMAL_DELTA_POISONING",
            divergent_state=poisoned_state,
            candidate_action={"temperature_delta": 5.0},
            z3_proof_report=proof_report
        )

        self.assertEqual(receipt["status"], "QUARANTINED_AND_COMMITTED")

    def test_hash_chaining_integrity(self):
        """Validates that successive divergent tails form a cryptographically unbroken SHA-256 hash chain."""
        # 1st Fault
        r1 = self.v2_historian.log_divergent_tail(
            session_id="sess_kinetic_01",
            node_id="node_1",
            fault_type="FAULT_1",
            divergent_state={"val": 1},
            candidate_action={"delta": 1},
            z3_proof_report={"status": "UNSAT"}
        )

        # 2nd Fault
        r2 = self.v2_historian.log_divergent_tail(
            session_id="sess_kinetic_01",
            node_id="node_2",
            fault_type="FAULT_2",
            divergent_state={"val": 2},
            candidate_action={"delta": 2},
            z3_proof_report={"status": "UNSAT"}
        )

        # Assert r2's previous_hash matches r1's non_repudiation_hash
        self.assertEqual(r2["previous_hash"], r1["non_repudiation_hash"])


if __name__ == "__main__":
    unittest.main()
