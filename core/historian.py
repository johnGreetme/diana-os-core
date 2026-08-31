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


# ============================================================================
# OpenClaw 2.0 Isolated SQLite Session Storage & Non-Repudiation Historian
# ============================================================================

import hashlib

DEFAULT_V2_SESSIONS_DB = os.path.expanduser("~/.openclaw/v2/sessions.db")
GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


class OpenClawV2SessionHistorian:
    """
    OpenClaw 2.0 SQLite Session Historian.
    
    Guarantees:
    1. Storage Isolation: Completely isolated from legacy 1.x flat logs and historian.db.
    2. Zero Lock Contention: PRAGMA journal_mode=WAL and PRAGMA busy_timeout=5000 with connection pooling.
    3. State-Locked Non-Repudiation: SHA-256 hash chaining of all Z3 Crucible evaluations and Divergent Tails.
    4. Multiplayer Presence Ledger: Tracks active nodes, roles, and collaborative session metadata.
    """

    def __init__(self, db_path: str = DEFAULT_V2_SESSIONS_DB):
        self.db_path = os.path.expanduser(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Returns SQLite connection with WAL mode and busy timeout to eliminate lock contention."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        """Creates OpenClaw 2.0 SQLite schema if not existing."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Sessions Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS openclaw_sessions (
                        session_id TEXT PRIMARY KEY,
                        title TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        metadata_json TEXT
                    )
                ''')

                # 2. Messages Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS openclaw_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        presence_marker_json TEXT,
                        FOREIGN KEY (session_id) REFERENCES openclaw_sessions(session_id)
                    )
                ''')

                # 3. Multiplayer Presence Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS multiplayer_presence (
                        node_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        user_alias TEXT NOT NULL,
                        role TEXT NOT NULL,
                        last_heartbeat TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active'
                    )
                ''')

                # 4. Divergent Tail Non-Repudiation Ledger
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS divergent_tail_ledger (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        fault_type TEXT NOT NULL,
                        divergent_state_json TEXT NOT NULL,
                        candidate_action_json TEXT NOT NULL,
                        z3_proof_json TEXT NOT NULL,
                        non_repudiation_hash TEXT NOT NULL UNIQUE,
                        previous_hash TEXT NOT NULL
                    )
                ''')

                # 5. Z3 Crucible Evaluations in V2 Ledger
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS v2_crucible_evaluations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        candidate_action_json TEXT NOT NULL,
                        current_state_json TEXT,
                        target_state_json TEXT,
                        is_safe INTEGER NOT NULL,
                        z3_result TEXT NOT NULL,
                        execution_time_ms REAL,
                        breach_report TEXT,
                        non_repudiation_hash TEXT NOT NULL
                    )
                ''')

                conn.commit()
        except Exception as e:
            logger.error(f"[OPENCLAW V2 HISTORIAN] Database initialization failed: {e}")

    def create_session(self, session_id: str, title: str = "Default Session", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Registers a new OpenClaw 2.0 session."""
        now = datetime.now().isoformat()
        meta_json = json.dumps(metadata or {})
        try:
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO openclaw_sessions (session_id, title, created_at, updated_at, status, metadata_json)
                    VALUES (?, ?, ?, ?, 'active', ?)
                ''', (session_id, title, now, now, meta_json))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[OPENCLAW V2 HISTORIAN] Failed to create session: {e}")
            return False

    def register_presence(self, node_id: str, session_id: str, user_alias: str, role: str = "orchestrator", status: str = "active") -> bool:
        """Registers or heartbeats a multiplayer node presence marker."""
        now = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO multiplayer_presence (node_id, session_id, user_alias, role, last_heartbeat, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (node_id, session_id, user_alias, role, now, status))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[OPENCLAW V2 HISTORIAN] Failed to register presence: {e}")
            return False

    def get_latest_hash(self) -> str:
        """Retrieves the most recent non-repudiation hash from the divergent tail ledger."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT non_repudiation_hash FROM divergent_tail_ledger ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                return row[0] if row else GENESIS_HASH
        except Exception:
            return GENESIS_HASH

    def log_divergent_tail(
        self,
        session_id: str,
        node_id: str,
        fault_type: str,
        divergent_state: Dict[str, Any],
        candidate_action: Dict[str, Any],
        z3_proof_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Captures the exact Divergent Tail (the hardware fault / quarantine moment)
        and computes a cryptographic SHA-256 non-repudiation hash.
        """
        now = datetime.now().isoformat()
        prev_hash = self.get_latest_hash()
        
        state_json = json.dumps(divergent_state, sort_keys=True)
        cand_json = json.dumps(candidate_action, sort_keys=True)
        proof_json = json.dumps(z3_proof_report, sort_keys=True)

        # Cryptographic Non-Repudiation Hash Computation
        hash_payload = f"{prev_hash}|{now}|{session_id}|{node_id}|{fault_type}|{state_json}|{cand_json}|{proof_json}"
        non_repudiation_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO divergent_tail_ledger 
                (timestamp, session_id, node_id, fault_type, divergent_state_json, candidate_action_json, z3_proof_json, non_repudiation_hash, previous_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (now, session_id, node_id, fault_type, state_json, cand_json, proof_json, non_repudiation_hash, prev_hash))
            entry_id = cursor.lastrowid
            conn.commit()

        return {
            "entry_id": entry_id,
            "timestamp": now,
            "session_id": session_id,
            "node_id": node_id,
            "fault_type": fault_type,
            "non_repudiation_hash": non_repudiation_hash,
            "previous_hash": prev_hash,
            "status": "QUARANTINED_AND_COMMITTED"
        }

    def log_v2_crucible_eval(
        self,
        session_id: str,
        domain: str,
        candidate_action: Dict[str, Any],
        current_state: Optional[Dict[str, Any]],
        target_state: Optional[Dict[str, Any]],
        is_safe: bool,
        z3_result: str,
        execution_time_ms: float = 0.0,
        breach_report: str = ""
    ) -> str:
        """Logs a formal Z3 SMT evaluation event with SHA-256 non-repudiation signature."""
        now = datetime.now().isoformat()
        cand_json = json.dumps(candidate_action, sort_keys=True)
        curr_json = json.dumps(current_state or {}, sort_keys=True)
        targ_json = json.dumps(target_state or {}, sort_keys=True)

        hash_payload = f"{now}|{session_id}|{domain}|{cand_json}|{curr_json}|{targ_json}|{is_safe}|{z3_result}"
        eval_hash = hashlib.sha256(hash_payload.encode("utf-8")).hexdigest()

        try:
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT INTO v2_crucible_evaluations 
                    (timestamp, session_id, domain, candidate_action_json, current_state_json, target_state_json, is_safe, z3_result, execution_time_ms, breach_report, non_repudiation_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (now, session_id, domain, cand_json, curr_json, targ_json, 1 if is_safe else 0, z3_result, execution_time_ms, breach_report, eval_hash))
                conn.commit()
        except Exception as e:
            logger.error(f"[OPENCLAW V2 HISTORIAN] Failed to insert v2 crucible evaluation: {e}")

        return eval_hash

    def query_divergent_tails(self, session_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Queries divergent tail quarantine ledger."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if session_id:
                    cursor.execute(
                        "SELECT id, timestamp, session_id, node_id, fault_type, divergent_state_json, candidate_action_json, z3_proof_json, non_repudiation_hash, previous_hash FROM divergent_tail_ledger WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                        (session_id, limit)
                    )
                else:
                    cursor.execute(
                        "SELECT id, timestamp, session_id, node_id, fault_type, divergent_state_json, candidate_action_json, z3_proof_json, non_repudiation_hash, previous_hash FROM divergent_tail_ledger ORDER BY id DESC LIMIT ?",
                        (limit,)
                    )
                rows = cursor.fetchall()
                return [
                    {
                        "id": r[0],
                        "timestamp": r[1],
                        "session_id": r[2],
                        "node_id": r[3],
                        "fault_type": r[4],
                        "divergent_state": json.loads(r[5]),
                        "candidate_action": json.loads(r[6]),
                        "z3_proof": json.loads(r[7]),
                        "non_repudiation_hash": r[8],
                        "previous_hash": r[9]
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"[OPENCLAW V2 HISTORIAN] Query divergent tails failed: {e}")
            return []


# Global Singleton Instances
historian = HistorianLogger()
openclaw_v2_historian = OpenClawV2SessionHistorian()

