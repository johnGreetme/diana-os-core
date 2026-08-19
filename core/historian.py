"""DIANA OS - Industrial SCADA & Cyber-Physical Historian.

Provides dual-layer persistent logging (SQLite + append-only audit log) tracking:
1. Live Hardware Telemetry Snapshots
2. Z3 Crucible SMT Formal Proof Evaluations
3. Atomic Actuation Event Trails
"""

import os
import time
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORIAN_DB_PATH = os.path.join(BASE_DIR, "ledger", "historian.db")
HISTORIAN_LOG_PATH = os.path.join(BASE_DIR, "reflections", "historian.log")

class HistorianLogger:
    """Persistent SCADA Historian tracking telemetry and formal Z3 SMT proofs."""

    def __init__(self, db_path: str = HISTORIAN_DB_PATH, log_path: str = HISTORIAN_LOG_PATH):
        self.db_path = db_path
        self.log_path = log_path
        self._init_storage()

    def _init_storage(self):
        """Initializes database schema and audit directories."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Telemetry Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    raw_state_json TEXT NOT NULL
                )
            ''')

            # Crucible SMT Evaluations Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crucible_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    candidate_action_json TEXT NOT NULL,
                    current_state_json TEXT,
                    target_state_json TEXT,
                    is_safe INTEGER NOT NULL,
                    z3_result TEXT NOT NULL,
                    execution_time_ms REAL,
                    breach_report TEXT
                )
            ''')

            # Actuation Execution Table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS actuation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    action_payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_message TEXT
                )
            ''')

            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HISTORIAN] Database initialization failed: {e}")

    def _append_flat_log(self, event_type: str, data: Dict[str, Any]):
        """Appends structured JSON-lines record to reflections/historian.log."""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "event_type": event_type,
                **data
            }
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"[HISTORIAN] Flat-file audit log write failed: {e}")

    def log_telemetry(self, domain: str, raw_state: Dict[str, Any]):
        """Logs a live hardware telemetry snapshot."""
        ts = datetime.now().isoformat()
        state_json = json.dumps(raw_state)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO telemetry_snapshots (timestamp, domain, raw_state_json) VALUES (?, ?, ?)",
                (ts, domain, state_json)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HISTORIAN] Failed to insert telemetry: {e}")

        self._append_flat_log("TELEMETRY_SNAPSHOT", {"domain": domain, "state": raw_state})

    def log_crucible_eval(
        self,
        domain: str,
        candidate_action: Dict[str, Any],
        current_state: Optional[Dict[str, Any]],
        target_state: Optional[Dict[str, Any]],
        is_safe: bool,
        z3_result: str,
        execution_time_ms: float = 0.0,
        breach_report: str = ""
    ):
        """Logs a formal Z3 SMT evaluation event."""
        ts = datetime.now().isoformat()
        cand_json = json.dumps(candidate_action)
        curr_json = json.dumps(current_state) if current_state else "{}"
        targ_json = json.dumps(target_state) if target_state else "{}"

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO crucible_evaluations 
                (timestamp, domain, candidate_action_json, current_state_json, target_state_json, is_safe, z3_result, execution_time_ms, breach_report)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (ts, domain, cand_json, curr_json, targ_json, 1 if is_safe else 0, z3_result, execution_time_ms, breach_report))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HISTORIAN] Failed to insert crucible evaluation: {e}")

        self._append_flat_log("CRUCIBLE_EVALUATION", {
            "domain": domain,
            "candidate": candidate_action,
            "target": target_state,
            "is_safe": is_safe,
            "z3_result": z3_result,
            "execution_time_ms": execution_time_ms,
            "breach_report": breach_report
        })

    def log_actuation(self, domain: str, action_payload: Dict[str, Any], status: str, response_message: str):
        """Logs a hardware or digital state execution event."""
        ts = datetime.now().isoformat()
        payload_json = json.dumps(action_payload)

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO actuation_logs (timestamp, domain, action_payload_json, status, response_message) VALUES (?, ?, ?, ?, ?)",
                (ts, domain, payload_json, status, response_message)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"[HISTORIAN] Failed to insert actuation log: {e}")

        self._append_flat_log("ACTUATION_EVENT", {
            "domain": domain,
            "payload": action_payload,
            "status": status,
            "response": response_message
        })

    def query_history(self, domain: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Queries recent evaluation history."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if domain:
                cursor.execute(
                    "SELECT timestamp, domain, candidate_action_json, is_safe, z3_result, breach_report FROM crucible_evaluations WHERE domain = ? ORDER BY id DESC LIMIT ?",
                    (domain, limit)
                )
            else:
                cursor.execute(
                    "SELECT timestamp, domain, candidate_action_json, is_safe, z3_result, breach_report FROM crucible_evaluations ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "timestamp": r[0],
                    "domain": r[1],
                    "action": json.loads(r[2]),
                    "is_safe": bool(r[3]),
                    "z3_result": r[4],
                    "report": r[5]
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"[HISTORIAN] Query history failed: {e}")
            return []

# Singleton Global Instance
historian = HistorianLogger()
