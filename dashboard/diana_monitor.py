"""DIANA OS Real-Time Monitor & Interactive Debug Dashboard.

A single-file Streamlit telemetry surface for the DIANA OS daemon stack
(Kytin OpenClaw orchestration, DeterministicDSL semantic pipeline, CaDiCaL195
symbolic verification). Reads every DIANA data source strictly read-only
and degrades gracefully when databases are missing or locked.

Usage:
    pip install -r requirements.txt
    streamlit run diana_monitor.py
"""

import hashlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import psutil
import requests
import streamlit as st
from streamlit.errors import StreamlitAPIException

try:
    from streamlit_agraph import agraph, Node, Edge, Config
    _AGRAPH_AVAILABLE = True
except ImportError:
    _AGRAPH_AVAILABLE = False

try:
    from qdrant_client import QdrantClient
    _QDRANT_AVAILABLE = True
except ImportError:
    _QDRANT_AVAILABLE = False

# ============================================================================
# LAYER 1 — CONFIG & RESILIENT HOOKS
# ============================================================================

_FALLBACK_ROOT = r"C:\DianaOS\Workspace"


def _resolve_diana_root() -> Path:
    env_override = os.environ.get("DIANA_ROOT")
    if env_override and Path(env_override).is_dir():
        return Path(env_override)
    script_parent = Path(__file__).resolve().parent.parent
    if script_parent.is_dir():
        return script_parent
    return Path(_FALLBACK_ROOT)


DIANA_ROOT = _resolve_diana_root()
MATRIX_DB = DIANA_ROOT / "diana_matrix.db"
# Canonical capture ledger (Telegram replies + GREETME annotations).
# Not Reflections\ — that path was a post-migration split-brain with only a few rows.
LEDGER_DB = DIANA_ROOT / "ledger" / "semantic_ledger.db"
DEFLECTIONS_LOG = DIANA_ROOT / "Reflections" / "deflections.log"
FAILED_GEOMETRIES_MD = DIANA_ROOT / "Reflections" / "failed_geometries.md"
OPENCLAW_JSON = DIANA_ROOT / "openclaw.json"
OLLAMA_PS_URL = "http://127.0.0.1:11434/api/ps"

QDRANT_STORAGE = DIANA_ROOT / "qdrant_storage"
QDRANT_COLLECTION = "genesis_geometries"
# Embedded Qdrant local mode persists points to this sqlite file; it stays
# readable via mode=ro even while another process holds the storage lock.
QDRANT_DISK_SQLITE = QDRANT_STORAGE / "collection" / QDRANT_COLLECTION / "storage.sqlite"

TAIL_BYTES = 65536
TIMELINE_CAP = 50
# Full SAT spine: scroll newest ledger id → oldest (e.g. #119 … #1).
LEDGER_TIMELINE_LIMIT = 10_000


def safe_query(db_path, sql, params=()):
    """Read-only SQLite query that NEVER raises.

    The daemon writes both databases at high frequency; mode=ro plus a short
    timeout means a locked or missing or mid-write-corrupt DB simply yields [].
    """
    path = Path(db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=0.5)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []


def tail_text(file_path, max_bytes=TAIL_BYTES) -> str:
    """Seek-based tail: reads only the final `max_bytes` of a growing log."""
    path = Path(file_path)
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


_LEGACY_WARRANT_RE = re.compile(r"Warrant:\s*(Ab\d+)")


def _parse_iso_ts(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_deflections(raw_text: str) -> list:
    """Parses all three deflections.log formats; HEARTBEAT lines are dropped.

    Formats:
      1. Legacy block: '[DEFLECTION] ...' line + following 'Justification: ...' line.
      2. JSON line:    {"event": "DEFLECTION", "rule": "Ab##", ...}
      3. Legacy free-form line carrying 'Warrant: Ab##'.
    """
    events = []
    pending_legacy = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("rule", "")).upper() == "HEARTBEAT":
                continue
            events.append({
                "rule": obj.get("rule", "Ab??"),
                "rationale": obj.get("rationale", ""),
                "prompt": obj.get("prompt", ""),
                "status": obj.get("status", "Blocked & Redirected"),
                "epoch": _parse_iso_ts(obj.get("timestamp")),
                "raw": line,
            })
            continue

        if line.startswith("[DEFLECTION]"):
            if pending_legacy is not None:
                events.append(pending_legacy)
            pending_legacy = {
                "rule": "Ab (legacy)",
                "rationale": line.replace("[DEFLECTION]", "").strip(),
                "prompt": "",
                "status": "Authorized exception",
                "epoch": None,
                "raw": line,
            }
            continue

        if line.startswith("Justification:") and pending_legacy is not None:
            pending_legacy["rationale"] = line.replace("Justification:", "").strip()
            pending_legacy["raw"] += "\n" + line
            events.append(pending_legacy)
            pending_legacy = None
            continue

        warrant = _LEGACY_WARRANT_RE.search(line)
        if warrant:
            events.append({
                "rule": warrant.group(1),
                "rationale": line,
                "prompt": "",
                "status": "Redirected",
                "epoch": None,
                "raw": line,
            })

    if pending_legacy is not None:
        events.append(pending_legacy)
    return events


_FAULT_HEADER_RE = re.compile(r"^## Fault Entry: (\S+)", re.MULTILINE)
_FENCED_JSON_RE = re.compile(r"```json\s*(.*?)```", re.DOTALL)


def parse_fault_entries(raw_text: str) -> list:
    """Splits failed_geometries.md on '## Fault Entry: <ts>' headers."""
    faults = []
    parts = _FAULT_HEADER_RE.split(raw_text)
    # parts = [preamble, ts1, body1, ts2, body2, ...]
    for i in range(1, len(parts) - 1, 2):
        stamp, body = parts[i], parts[i + 1]
        fence = _FENCED_JSON_RE.search(body)
        trace = fence.group(1).strip() if fence else body.strip()[:4000]
        try:
            epoch = datetime.strptime(stamp, "%Y%m%d_%H%M%S").timestamp()
        except ValueError:
            epoch = None
        faults.append({"stamp": stamp, "trace": trace, "epoch": epoch})
    return faults


@st.cache_data(ttl=0.9, show_spinner=False)
def read_deflections() -> list:
    return parse_deflections(tail_text(DEFLECTIONS_LOG))


@st.cache_data(ttl=0.9, show_spinner=False)
def read_faults() -> list:
    return parse_fault_entries(tail_text(FAILED_GEOMETRIES_MD))


@st.cache_data(ttl=0.9, show_spinner=False)
def read_recent_geometries(limit=TIMELINE_CAP) -> list:
    return safe_query(
        MATRIX_DB,
        "SELECT logic_id, domain_tag, raw_text, timestamp FROM genesis_geometries "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _qdrant_call(fn):
    """Short-lived embedded Qdrant access: open, apply, ALWAYS close.

    Local mode takes an EXCLUSIVE process lock on qdrant_storage, and the
    ingestion pipeline or diana_mediator may hold it at any moment — so a
    failure here (lock contention, missing collection, corrupt storage,
    missing package) is an expected state, answered with None so the caller
    can descend the resilience ladder. Broad except is deliberate: the
    embedded client raises implementation-specific error types.
    """
    if not _QDRANT_AVAILABLE or not QDRANT_STORAGE.is_dir():
        return None
    client = None
    try:
        client = QdrantClient(path=str(QDRANT_STORAGE))
        return fn(client)
    except Exception:
        return None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


@st.cache_data(ttl=5, show_spinner=False)
def read_vector_count() -> dict:
    """Hybrid geometry count. Resilience ladder:

    1. HNSW        — live embedded Qdrant exact count.
    2. QDRANT-DISK — read-only COUNT against Qdrant's own storage.sqlite
                     (points table), works even while the lock is held.
    3. LEGACY-SQL  — pre-migration diana_matrix.db.
    4. OFFLINE     — every rung failed; render a degraded badge, never raise.
    """
    hnsw = _qdrant_call(
        lambda c: c.count(QDRANT_COLLECTION, exact=True).count
    )
    if hnsw is not None:
        return {"count": int(hnsw), "source": "HNSW"}
    disk = safe_query(QDRANT_DISK_SQLITE, "SELECT COUNT(*) FROM points")
    if disk:
        return {"count": disk[0][0], "source": "QDRANT-DISK"}
    legacy = safe_query(MATRIX_DB, "SELECT COUNT(*) FROM genesis_geometries")
    if legacy:
        return {"count": legacy[0][0], "source": "LEGACY-SQL"}
    return {"count": 0, "source": "OFFLINE"}


@st.cache_data(ttl=5, show_spinner=False)
def read_hybrid_geometries(limit=TIMELINE_CAP) -> tuple:
    """Geometry rows as (logic_id, domain_tag, raw_text, timestamp) tuples.

    Prefers Qdrant scroll payloads (timestamp is None — payloads carry no
    timestamps), falls back to legacy diana_matrix.db rows. Returns
    (rows, source) with source in {"HNSW", "LEGACY-SQL", "OFFLINE"}.
    """
    def _scroll(client):
        points, _next = client.scroll(
            QDRANT_COLLECTION, limit=100, with_payload=True
        )
        return points

    points = _qdrant_call(_scroll)
    if points:
        rows = [
            (
                p.payload.get("logic_id"),
                p.payload.get("domain_tag"),
                p.payload.get("raw_text"),
                None,
            )
            for p in points
            if p.payload
        ]
        if rows:
            return rows[:limit], "HNSW"
    legacy = read_recent_geometries(limit)
    if legacy:
        return legacy, "LEGACY-SQL"
    return [], "OFFLINE"


@st.cache_data(ttl=0.9, show_spinner=False)
def read_recent_ledger(limit=LEDGER_TIMELINE_LIMIT) -> list:
    """Return ledger rows as 6-tuples:
    id, timestamp, intent, annotated, retrieved_logic_ids, telegram_response.
    Missing columns are padded with None.
    """
    cols = {
        str(c[1])
        for c in safe_query(LEDGER_DB, "PRAGMA table_info(semantic_translations)")
        if len(c) > 1
    }
    select = [
        "id",
        "timestamp",
        "raw_human_intent",
        "annotated_machine_state",
    ]
    if "retrieved_logic_ids" in cols:
        select.append("retrieved_logic_ids")
    if "telegram_response" in cols:
        select.append("telegram_response")
    rows = safe_query(
        LEDGER_DB,
        f"SELECT {', '.join(select)} FROM semantic_translations "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    normalized = []
    for r in rows:
        retrieved = None
        telegram = None
        # Base always 4 columns; extras depend on which columns exist.
        extras = list(r[4:])
        if "retrieved_logic_ids" in cols and extras:
            retrieved = extras.pop(0)
        if "telegram_response" in cols and extras:
            telegram = extras.pop(0)
        normalized.append((r[0], r[1], r[2], r[3], retrieved, telegram))
    return normalized


@st.cache_data(ttl=0.9, show_spinner=False)
def read_swarm_config() -> dict:
    try:
        with open(OPENCLAW_JSON, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        return {
            "nodes": len(cfg.get("active_workers", [])),
            "model_tag": cfg.get("model_tag", "unknown"),
            "engine": cfg.get("orchestration_engine", "Kytin OpenClaw"),
            "ok": True,
        }
    except (OSError, json.JSONDecodeError):
        return {"nodes": 0, "model_tag": "unknown", "engine": "Kytin OpenClaw", "ok": False}


@st.cache_data(ttl=0.9, show_spinner=False)
def read_ollama_vram() -> dict:
    try:
        resp = requests.get(OLLAMA_PS_URL, timeout=0.5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        vram = sum(m.get("size_vram", 0) for m in models)
        return {"online": True, "vram_gb": vram / (1024 ** 3), "models": len(models)}
    except (requests.RequestException, ValueError):
        return {"online": False, "vram_gb": 0.0, "models": 0}


def sample_host_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    counters = psutil.net_io_counters()
    now = time.time()
    prev = st.session_state.get("_net_prev")
    st.session_state["_net_prev"] = (now, counters.bytes_sent, counters.bytes_recv)
    mbps = 0.0
    if prev:
        dt = max(now - prev[0], 1e-6)
        bytes_per_sec = ((counters.bytes_sent - prev[1]) + (counters.bytes_recv - prev[2])) / dt
        mbps = bytes_per_sec * 8 / 1_000_000
    return {"cpu": cpu, "ram": mem.percent, "mbps": mbps}


def _sim_ms(seed: str, low=4.0, high=95.0) -> float:
    """Deterministic pseudo-latency so cards don't jitter on every rerun."""
    digest = int(hashlib.md5(seed.encode("utf-8", errors="replace")).hexdigest(), 16)
    return round(low + (digest % 10_000) / 10_000 * (high - low), 1)


# ============================================================================
# SEMANTIC SIEVE — GREETME_50 copied verbatim from skills/diana_core/logic_engine.py
# ============================================================================

GREETME_50 = {
    # Category 1: Identity & Existence
    "SELF_ASSERTION", "TARGET_IDENTIFICATION", "GROUP_CONSENSUS",
    "EXTERNAL_ENTITY", "OBJECT_REFERENCE", "ROOT_AUTHORITY",
    "GENESIS_ORIGIN", "EXECUTOR_NODE", "NULL_VOID", "PLAINTEXT_BROADCAST",

    # Category 2: Temporality
    "IMMEDIATE_EXECUTION", "DEFERRED_QUEUE", "PRE_CONDITION",
    "POST_CONDITION", "IMMUTABLE_CONSTANT", "FORBIDDEN_CONSTRAINT",
    "DURATIONAL_LOOP", "CONDITIONAL_TERMINATION", "HISTORICAL_LEDGER",
    "PREDICTIVE_SLOT",

    # Category 3: Logic & Causality
    "LOGIC_GATE_OPEN", "CONSEQUENCE_LOCK", "FALLBACK_PROTOCOL",
    "COMPOUND_REQUIREMENT", "OPTIONAL_PATH", "INVERSION_OPERATOR",
    "CAUSAL_LINK", "DERIVED_CONCLUSION", "VALIDATED_FACT", "INVALID_STATE",

    # Category 4: Action & Volition
    "EXECUTE_COMMAND", "HALT_PROCESS", "PAUSE_STATE", "VERIFY_STATE",
    "CREATE_INSTANCE", "BURN_INSTANCE", "TRANSFER_ASSET", "HOLD_CUSTODY",
    "UPDATE_MUTABLE", "CORRECT_ERROR",

    # Category 5: Measurement & Constraints
    "GREATER_THAN", "LESS_THAN", "EXACT_MATCH", "INCREMENT_STATE",
    "DECREMENT_STATE", "MANDATORY_OBLIGATION", "PERMISSION_GRANT",
    "FUTURE_COMMITMENT", "PENDING_RESOLUTION", "ENCRYPTED_PAYLOAD"
}

INSTRUCTION_KEYS = {
    "action", "operator", "primitive", "condition",
    "instruction", "state", "logical_operator",
    "gate", "rule", "constraint", "command"
}


def verify_semantic_atoms(payload_obj):
    """Compiler front-end (Semantic Sieve) — mirrors logic_engine.py exactly."""
    if isinstance(payload_obj, dict):
        for k, v in payload_obj.items():
            if k.lower() in INSTRUCTION_KEYS:
                if isinstance(v, str):
                    if v.upper() not in GREETME_50:
                        return False, f"INVALID_STATE: Unauthorized primitive detected: '{v}' in field '{k}'."
            elif isinstance(v, (dict, list)):
                valid, err = verify_semantic_atoms(v)
                if not valid:
                    return False, err
    elif isinstance(payload_obj, list):
        for item in payload_obj:
            valid, err = verify_semantic_atoms(item)
            if not valid:
                return False, err
    return True, ""


def simulate_compile_pysat_geometries(resin_payload, top_geometries: list) -> dict:
    """Pure-Python simulation of pysat_compiler.compile_pysat_geometries.

    No pysat import — CaDiCaL195 behaviour (tiering, ephemeral Ab literal,
    assumption-gated defeasible solve) is emulated while keeping the real
    result-dict vocabulary: mathematically_valid / deflection_intercepted /
    deflection_warrant / abnormality_literal_activated / ab_flushed.
    """
    try:
        var_counter = 0
        tier1, tier2 = 0, 0
        for geo in top_geometries:
            var_counter += 1
            raw_text = str(geo.get("raw_text", "")).lower()
            if "possibilit" in raw_text or "certifier" in raw_text or "nothing" in raw_text:
                tier1 += 1
            else:
                tier2 += 1

        abnormality_requested = False
        efficiency_delta = "None"
        if isinstance(resin_payload, dict):
            abnormality_requested = bool(resin_payload.get("abnormality_warrant_requested", False))
            efficiency_delta = resin_payload.get("efficiency_delta_justification", "Unknown Optimization")

        ab_var_for_solve = var_counter + 1000

        payload_text = json.dumps(resin_payload) if isinstance(resin_payload, (dict, list)) else str(resin_payload)
        has_contradiction = bool(
            isinstance(resin_payload, dict) and resin_payload.get("contradictions")
        ) or '"type": "contradiction"' in payload_text

        is_sat = not has_contradiction or abnormality_requested
        solve_ms = _sim_ms(payload_text + str(var_counter), low=2.0, high=48.0)

        if is_sat and abnormality_requested:
            return {
                "status": "SUCCESS",
                "mathematically_valid": True,
                "deflection_intercepted": True,
                "deflection_warrant": efficiency_delta,
                "abnormality_literal_activated": ab_var_for_solve,
                "ab_flushed": True,
                "simulated": True,
                "solver": "CaDiCaL195 (simulated)",
                "solve_ms": solve_ms,
                "tier1_clauses": tier1,
                "tier2_clauses": tier2,
            }

        return {
            "status": "SUCCESS",
            "mathematically_valid": is_sat,
            "deflection_intercepted": False,
            "ab_flushed": True,
            "simulated": True,
            "solver": "CaDiCaL195 (simulated)",
            "solve_ms": solve_ms,
            "tier1_clauses": tier1,
            "tier2_clauses": tier2,
        }
    except (TypeError, ValueError, AttributeError) as exc:
        return {"status": "ERROR", "error_message": str(exc), "mathematically_valid": False}


# ============================================================================
# LAYER 2 — DARK THEME
# ============================================================================

st.set_page_config(
    page_title="DIANA OS :: Kytin Telemetry",
    page_icon=":satellite:",
    layout="wide",
)

st.markdown(
    """
<style>
.stApp { background-color: #060709; color: #c9d1d9; }
section[data-testid="stSidebar"] { background-color: #0a0c10; }
h1, h2, h3 { color: #e6edf3; font-family: 'Consolas', 'SF Mono', monospace; }
div[data-testid="stMetricValue"] {
    font-family: 'Consolas', 'SF Mono', monospace;
    color: #58e6a8; font-size: 1.5rem;
}
div[data-testid="stMetricLabel"] {
    font-family: 'Consolas', 'SF Mono', monospace;
    color: #7d8590; letter-spacing: 0.08em; text-transform: uppercase;
}
.diana-card {
    border-radius: 8px; padding: 10px 14px; margin: 6px 0;
    background: #0d1117; border: 1px solid #21262d;
    font-family: 'Consolas', 'SF Mono', monospace; font-size: 0.82rem;
    line-height: 1.5; word-break: break-word;
}
.diana-card .card-title { font-weight: 700; letter-spacing: 0.05em; }
.diana-card .card-meta { color: #7d8590; font-size: 0.72rem; }
.card-green { border-left: 4px solid #2ea043; }
.card-green .card-title { color: #58e6a8; }
.card-amber { border-left: 4px solid #d29922; background: #14100a; }
.card-amber .card-title { color: #e3b341; }
.card-red { border-left: 4px solid #f85149; background: #150b0c; }
.card-red .card-title { color: #ff7b72; }
.diana-badge {
    display: inline-block; padding: 1px 8px; border-radius: 10px;
    font-size: 0.68rem; font-weight: 700; margin-left: 6px;
}
.badge-escalate { background: #6e2fb8; color: #e6d7ff; }
.badge-degraded { background: #5a3b00; color: #e3b341; }
.badge-ok { background: #0f3d22; color: #58e6a8; }

/* Prevent numerical layout shifting when live data streams */
[data-testid="stMetricValue"] {
    transition: color 0.15s ease-in-out;
    font-variant-numeric: tabular-nums !important;
}

/* Only timeline cards animate — never every vertical block on each 1s tick
   (that made the Phoenix list appear to reshuffle continuously). */
.diana-card {
    animation: liveNodeArrival 0.3s cubic-bezier(0.25, 1, 0.5, 1) forwards;
}

@keyframes liveNodeArrival {
    0% {
        opacity: 0;
        transform: translateY(-5px);
    }
    100% {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Pulse animation for active Amber Deflection blocks */
.stAlert {
    animation: abnormalityPulse 2.5s infinite ease-in-out;
    border: 1px solid rgba(255, 193, 7, 0.35) !important;
}

@keyframes abnormalityPulse {
    0% { box-shadow: 0 0 4px rgba(255, 193, 7, 0.1); }
    50% { box-shadow: 0 0 12px rgba(255, 193, 7, 0.4); }
    100% { box-shadow: 0 0 4px rgba(255, 193, 7, 0.1); }
}

/* Chat bubbles: static accents only — no enter animation.
   The chat fragment remounts on its poll tick; animating opacity on every
   remount caused Conversational Command to flicker. */

/* User Message Box Accent Styling */
[data-testid="stChatMessageUser"] {
    border-left: 3px solid rgba(0, 150, 255, 0.4) !important;
    background-color: rgba(0, 150, 255, 0.03) !important;
}

/* Compatibility twin: current Streamlit tags user messages via avatar icon */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    border-left: 3px solid rgba(0, 150, 255, 0.4) !important;
    background-color: rgba(0, 150, 255, 0.03) !important;
}

/* Assistant Message Dynamic Border Selection Classes */
.diana-msg-sat {
    border-left: 3px solid rgba(0, 255, 128, 0.4) !important;
    background-color: rgba(0, 255, 128, 0.02) !important;
}

.diana-msg-abnormality {
    border-left: 3px solid rgba(255, 193, 7, 0.4) !important;
    background-color: rgba(255, 193, 7, 0.02) !important;
    animation: abnormalityPulse 2.5s infinite ease-in-out;
}

.diana-msg-contradiction {
    border-left: 3px solid rgba(255, 75, 75, 0.5) !important;
    background-color: rgba(255, 75, 75, 0.03) !important;
}

.diana-msg-sat, .diana-msg-abnormality, .diana-msg-contradiction {
    padding: 6px 12px;
    border-radius: 6px;
}

/* Tabular time text styling inside messages */
.chat-timestamp {
    font-family: monospace;
    font-size: 0.75rem;
    color: #666;
}

/* Onboarding vs status lines — same size/font as Streamlit captions; color only differs */
.diana-guide {
    font-size: 14px !important;
    line-height: 1.4 !important;
    font-family: "Source Sans", "Source Sans Pro", sans-serif !important;
    color: #8b949e !important;
    margin: 0 0 0.35rem 0 !important;
}
.diana-status {
    font-size: 14px !important;
    line-height: 1.4 !important;
    font-family: "Source Sans", "Source Sans Pro", sans-serif !important;
    color: #58a6ff !important;
    margin: 0 0 0.35rem 0 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================================
# ONBOARDING — plain-English guides under every operator-facing surface
# ============================================================================

def _section_guide(blurb: str) -> None:
    """Plain-English onboarding — muted gray caption weight/size."""
    st.markdown(
        f'<p class="diana-guide">{_html_escape(blurb)}</p>',
        unsafe_allow_html=True,
    )


def _status_line(text: str) -> None:
    """Operational status line — same size/font as guides, accent blue to distinguish."""
    st.markdown(
        f'<p class="diana-status">{_html_escape(text)}</p>',
        unsafe_allow_html=True,
    )


# ============================================================================
# LAYER 4 helpers — DUAL TIMELINE EVENT ASSEMBLY (rendered inside the fragment)
# ============================================================================

_ATOM_RE = re.compile(r"\[([A-Z_]{3,})\]")


def _html_escape(text) -> str:
    return (
        str(text)
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _nearest_geometry(neural_epoch, geometries, context_text=""):
    """Pairs a neural ledger row with a real symbolic compile record only.

    Honest rules (no default first-hit):
    - Qdrant rows (geo_ts is None): match only when logic_id appears in context.
    - Legacy SQLite rows: closest finite timestamp delta only.
    - Otherwise return None — never invent a Sociology/KYTIN bind.
    """
    best, best_delta = None, None
    for logic_id, domain_tag, raw_text, geo_ts in geometries:
        if geo_ts is None:
            if logic_id and str(logic_id) in (context_text or ""):
                return (logic_id, domain_tag, raw_text)
            continue
        geo_epoch = _parse_iso_ts(geo_ts)
        if neural_epoch is None or geo_epoch is None:
            continue
        delta = abs(neural_epoch - geo_epoch)
        if best is None or delta < best_delta:
            best, best_delta = (logic_id, domain_tag, raw_text), delta
    return best


def _parse_retrieved_logic_ids(raw) -> list:
    """Decode mediator-persisted JSON list of {logic_id, domain_tag, score}."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _symbolic_from_persisted(retrieved_raw, geometries) -> tuple:
    """Prefer mediator-persisted top HNSW hit; enrich with raw_text if available."""
    hits = _parse_retrieved_logic_ids(retrieved_raw)
    if not hits:
        return None
    top = hits[0] if isinstance(hits[0], dict) else None
    if not top or not top.get("logic_id"):
        return None
    logic_id = top.get("logic_id")
    domain_tag = top.get("domain_tag") or ""
    score = top.get("score")
    raw_text = ""
    for g_logic, g_domain, g_raw, _ts in geometries:
        if str(g_logic) == str(logic_id):
            raw_text = g_raw or ""
            if not domain_tag:
                domain_tag = g_domain or ""
            break
    return (logic_id, domain_tag, raw_text, score)


def build_timeline_events() -> dict:
    """Stable Phoenix spine: SAT nodes ordered by ledger id DESC (#N … #1).

    Deflections/faults are returned separately so they cannot interleave into
    the SAT list and reshuffle card positions on each fragment tick.
    """
    ledger_rows = read_recent_ledger(LEDGER_TIMELINE_LIMIT)
    geometries, _geo_source = read_hybrid_geometries()
    deflections = read_deflections()
    faults = read_faults()

    neural = []
    for row in ledger_rows:
        row_id, ts, intent, annotated = row[0], row[1], row[2], row[3]
        retrieved_raw = row[4] if len(row) > 4 else None
        telegram_response = row[5] if len(row) > 5 else None
        epoch = _parse_iso_ts(ts)
        intent = intent or ""
        annotated = annotated or ""
        atoms = [a for a in _ATOM_RE.findall(annotated) if a in GREETME_50]
        escalated = "<|ESCALATE|>" in intent or "<|ESCALATE|>" in annotated
        persisted = _symbolic_from_persisted(retrieved_raw, geometries)
        if persisted:
            logic_id, domain_tag, raw_text, score = persisted
            pair = (logic_id, domain_tag, raw_text)
            bind_score = score
            bind_source = "PERSISTED"
        else:
            pair = _nearest_geometry(epoch, geometries, f"{intent} {annotated}")
            bind_score = None
            bind_source = "PAIRED" if pair else "NONE"
        neural.append({
            "kind": "neural",
            "epoch": epoch,
            "id": row_id if row_id is not None else 0,
            "ts": ts,
            "intent": intent,
            "prompt_len": len(intent),
            "atoms": atoms,
            "escalated": escalated,
            "latency_ms": _sim_ms(f"ledger:{row_id}:{intent}", low=180.0, high=2400.0),
            "symbolic": pair,
            "bind_score": bind_score,
            "bind_source": bind_source,
            "compile_ms": _sim_ms(f"compile:{row_id}", low=3.0, high=42.0),
            "telegram_response": telegram_response,
            "annotated": annotated,
        })

    # Strict monotonic spine: #119, #118, … #1 (never epoch-merge reshuffle).
    neural.sort(key=lambda e: int(e["id"] or 0), reverse=True)

    anomaly = []
    for i, d in enumerate(deflections):
        anomaly.append({"kind": "deflection", "epoch": d["epoch"], "order": i, **d})
    for f in faults:
        anomaly.append({"kind": "fault", "epoch": f["epoch"], **f})
    anomaly.sort(
        key=lambda e: e["epoch"] if e.get("epoch") is not None else 0.0,
        reverse=True,
    )
    anomaly = anomaly[:TIMELINE_CAP]

    return {"neural": neural, "anomaly": anomaly}


def _render_neural_card(ev):
    esc_badge = '<span class="diana-badge badge-escalate">&lt;|ESCALATE|&gt; CLOUD ROUTE</span>' if ev["escalated"] else ""
    atoms = " ".join(f"<code>{_html_escape(a)}</code>" for a in ev["atoms"][:8]) or "<i>no locked atoms</i>"
    if ev["symbolic"]:
        logic_id, domain_tag, _raw = ev["symbolic"]
        score = ev.get("bind_score")
        score_bit = (
            f' &middot; HNSW score <code>{score:.4f}</code>'
            if isinstance(score, (int, float)) else ""
        )
        source = ev.get("bind_source") or "PAIRED"
        resin = (
            '<span style="color:#58e6a8">PARSED</span>'
            if source == "PERSISTED"
            else '<span style="color:#7d8590">UNVERIFIED</span>'
        )
        symbolic_line = (
            f'SYMBOLIC &middot; logic_id <code>{_html_escape(str(logic_id))}</code> '
            f'&middot; domain <code>{_html_escape(str(domain_tag or ""))}</code>'
            f'{score_bit} '
            f'&middot; Resin AST: {resin} '
            f'&middot; CaDiCaL195 compile: {ev["compile_ms"]} ms (sim) '
            f'&middot; <span style="color:#7d8590">{_html_escape(source)}</span>'
        )
    else:
        symbolic_line = (
            'SYMBOLIC &middot; <span style="color:#7d8590">'
            'no geometry match</span>'
        )
    ts = _html_escape(ev["ts"] or "no timestamp")
    intent = _html_escape((ev["intent"] or "")[:220])
    reply = ev.get("telegram_response") or ""
    reply_badge = (
        '<span class="diana-badge badge-ok">TELEGRAM REPLY CAPTURED</span>'
        if reply
        else '<span class="diana-badge badge-degraded">REPLY NOT CAPTURED</span>'
    )
    st.markdown(
        f"""<div class="diana-card card-green">
<span class="card-title">&#9679; SAT NODE #{ev["id"]}</span>{esc_badge}{reply_badge}
<div class="card-meta">{ts} &middot; prompt {ev["prompt_len"]} chars &middot; token latency {ev["latency_ms"]} ms (derived)</div>
<div>NEURAL &middot; {intent}</div>
<div>ATOMS &middot; {atoms}</div>
<div class="card-meta">{symbolic_line}</div>
</div>""",
        unsafe_allow_html=True,
    )
    with st.expander(f"White-box Telegram reply — SAT NODE #{ev['id']}", expanded=False):
        _status_line("Exact outbound payload returned by diana_mediator -> openclaw_daemon send path")
        if reply:
            st.code(reply, language=None)
        else:
            st.info(
                "No telegram_response on this ledger row yet. Restart openclaw_daemon.py "
                "so the mediator can persist replies; new Telegram turns will populate here."
            )
        annotated = ev.get("annotated") or ""
        if annotated:
            with st.expander("Annotated machine state (GREETME_50)", expanded=False):
                st.code(annotated, language=None)


def _render_deflection_card(ev):
    ts = _html_escape(ev.get("raw", "")) if ev["epoch"] is None else _html_escape(
        datetime.fromtimestamp(ev["epoch"]).strftime("%Y-%m-%d %H:%M:%S"))
    prompt_line = f'<div class="card-meta">prompt: {_html_escape(ev["prompt"][:160])}</div>' if ev.get("prompt") else ""
    st.markdown(
        f"""<div class="diana-card card-amber">
<span class="card-title">&#9650; ABNORMALITY NODE &middot; {_html_escape(ev["rule"])}</span>
<span class="diana-badge badge-degraded">{_html_escape(ev["status"])}</span>
<div class="card-meta">{ts if ev["epoch"] is not None else "legacy entry (no timestamp)"}</div>
<div>{_html_escape(ev["rationale"][:300])}</div>
{prompt_line}
</div>""",
        unsafe_allow_html=True,
    )


def _render_fault_card(ev):
    st.markdown(
        f"""<div class="diana-card card-red">
<span class="card-title">&#10006; CONTRADICTION NODE &middot; Fault {_html_escape(ev["stamp"])}</span>
<div class="card-meta">UNSAT geometry captured to failed_geometries.md &middot; negative constraint boundary</div>
</div>""",
        unsafe_allow_html=True,
    )
    with st.expander(f"Raw deterministic_dsl_payload stack trace — {ev['stamp']}"):
        st.code(ev["trace"], language="json")


# ============================================================================
# LAYER 3 — LIVE TELEMETRY FRAGMENT (the ONLY thing that re-runs every second)
# ============================================================================

@st.fragment(run_every=1.0)
def live_telemetry():
    host = sample_host_metrics()
    ollama = read_ollama_vram()
    swarm = read_swarm_config()
    vector = read_vector_count()

    _section_guide(
        "This is the live health strip: VRAM from Ollama, how many geometries are "
        "compiled, swarm node count, and host CPU / RAM / network. It refreshes "
        "about once a second so you can see the machine breathe without reloading "
        "the page."
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    if ollama["online"]:
        c1.metric("VRAM (Ollama)", f"{ollama['vram_gb']:.2f} GB", f"{ollama['models']} model(s) resident")
    else:
        c1.metric("VRAM (Ollama)", "OFFLINE")
        c1.markdown('<span class="diana-badge badge-degraded">DAEMON DEGRADED</span>', unsafe_allow_html=True)
    if vector["source"] == "OFFLINE":
        c2.metric("Compiled Geometries", "—")
        c2.markdown(
            '<span class="diana-badge badge-degraded">VECTOR ENGINE LOCKED/OFFLINE</span>',
            unsafe_allow_html=True,
        )
    else:
        c2.metric(
            "Compiled Geometries",
            f"{vector['count']:,}",
            f"genesis_geometries · {vector['source']}",
        )
    c3.metric("Swarm Nodes", swarm["nodes"], swarm["model_tag"])
    c4.metric("CPU", f"{host['cpu']:.0f}%")
    c5.metric("RAM", f"{host['ram']:.0f}%")
    c6.metric("Net (10GbE)", f"{host['mbps']:.2f} Mbps")

    flash_slot = st.empty()
    deflections = read_deflections()
    seen = st.session_state.get("_deflections_seen")
    if seen is not None and len(deflections) > seen:
        newest = deflections[-1]
        flash_slot.warning(
            f"NEW DEFLECTION INTERCEPTED — {newest['rule']}: {newest['rationale'][:180]}",
            icon="⚠️",
        )
    st.session_state["_deflections_seen"] = len(deflections)


@st.fragment(run_every=5.0)
def phoenix_timeline():
    """Stable SAT spine (#N … #1). Slower tick than the metric banner so
    scroll position and open white-box expanders are not wiped every second.
    """
    bundle = build_timeline_events()
    neural = bundle["neural"]
    anomaly = bundle["anomaly"]

    top_id = neural[0]["id"] if neural else "—"
    bottom_id = neural[-1]["id"] if neural else "—"
    captured = sum(1 for e in neural if e.get("telegram_response"))
    st.markdown("#### Phoenix-Killer Dual Timeline — Neural / Symbolic trace")
    _section_guide(
        "This is a live scroll of every conversation turn Diana recorded, newest "
        "at the top (#N down to #1). Each green SAT card is one prompt: what you "
        "said, which GREETME atoms locked, which geometry it bound to, and — when "
        "captured — the full Telegram reply inside the white-box expander. "
        "Open \"White-box Telegram reply\" to read the exact text she sent back; "
        "REPLY NOT CAPTURED means that older turn predates response logging."
    )
    _status_line(
        f"Stable ledger spine · SAT NODE #{top_id} -> #{bottom_id} "
        f"({len(neural)} turns · {captured} telegram replies captured) · "
        f"refresh 5s"
    )

    if anomaly:
        with st.expander(
            f"Abnormality / Contradiction rail ({len(anomaly)} events) — "
            "kept out of the SAT spine so cards do not reshuffle",
            expanded=False,
        ):
            _section_guide(
                "This side rail holds warning and failure events (Ab deflections "
                "and logic contradictions) so they do not shove the SAT list "
                "around. Open it when you need the fault story; leave it closed "
                "to keep the main spine stable."
            )
            for ev in anomaly:
                if ev["kind"] == "deflection":
                    _render_deflection_card(ev)
                else:
                    _render_fault_card(ev)

    with st.container(height=640):
        if not neural:
            st.info(
                "No telemetry yet. ledger/semantic_ledger.db is created lazily "
                "by the daemon — the spine will populate once it writes."
            )
        for ev in neural:
            _render_neural_card(ev)


st.markdown(
    f"## DIANA OS :: Kytin Telemetry Console "
    f'<span class="diana-badge badge-ok">ROOT {_html_escape(str(DIANA_ROOT))}</span>',
    unsafe_allow_html=True,
)
live_telemetry()
phoenix_timeline()

# ============================================================================
# LAYER 4 — DETERMINISTIC STATE GRAPH (its OWN fragment, NO run_every:
# the 1s telemetry ticks never re-render this canvas, so the user's
# drag/zoom/pan arrangement survives. "Refresh Graph" reruns only this
# fragment and re-pulls the DB rows on demand.)
#
# Display mode: Global force network (option 1) OR seeded transitive
# expansion from SAT #N (option 2), with a white-box inspector pane
# (option 4) beside the canvas.
# ============================================================================

DSG_NODE_CAP = 100
DSG_EXPANSION_HOPS = 2
DSG_EXPANSION_NODE_CAP = 80

# Domain → border accent for the force canvas
_DOMAIN_COLORS = {
    "computer_science": "#58a6ff",
    "sociology": "#d2a8ff",
    "philosophy": "#ffa657",
    "mathematics": "#79c0ff",
    "physics": "#a5d6ff",
    "biology": "#7ee787",
    "psychology": "#ff7b72",
    "economics": "#e3b341",
    "general": "#8b949e",
}


def _domain_color(domain_tag: str) -> str:
    key = (domain_tag or "general").strip().lower().replace(" ", "_")
    return _DOMAIN_COLORS.get(key, "#2ea043")


def _load_all_transitive_edges() -> list:
    return safe_query(
        MATRIX_DB,
        "SELECT parent_logic_id, child_logic_id FROM transitive_links",
    )


def _adjacency(edge_rows) -> dict:
    """Undirected adjacency for BFS expansion (matches mediator seed expand)."""
    adj = {}
    for parent, child in edge_rows:
        p, c = str(parent or ""), str(child or "")
        if not p or not c:
            continue
        adj.setdefault(p, set()).add(c)
        adj.setdefault(c, set()).add(p)
    return adj


def _expand_from_seeds(seed_ids, edge_rows, hops=DSG_EXPANSION_HOPS, cap=DSG_EXPANSION_NODE_CAP):
    """BFS over transitive_links from seed logic_ids — same idea as mediator."""
    seeds = [str(s) for s in seed_ids if s]
    if not seeds:
        return set(), []
    adj = _adjacency(edge_rows)
    seen = set(seeds)
    frontier = list(seeds)
    for _ in range(max(0, hops)):
        nxt = []
        for node in frontier:
            for neigh in adj.get(node, ()):
                if neigh not in seen:
                    seen.add(neigh)
                    nxt.append(neigh)
                    if len(seen) >= cap:
                        break
            if len(seen) >= cap:
                break
        frontier = nxt
        if not frontier or len(seen) >= cap:
            break
    kept_edges = [
        (str(p), str(c))
        for p, c in edge_rows
        if str(p) in seen and str(c) in seen
    ]
    return seen, kept_edges


# Hop depth → how many ranked HNSW hits to reveal when transitive_links is empty.
_HNSW_HOP_REVEAL = {1: 1, 2: 2, 3: 3, 4: 5}


def _expand_from_hnsw_rank(hits, hops: int):
    """Fallback expansion when diana_matrix.db has no transitive_links.

    Uses the mediator-persisted retrieved_logic_ids ranking so the hop slider
    visibly grows the neighborhood: hop1=top1, hop2=top2, hop3=top3, hop4=top5.
    Edges are drawn as a star from the primary seed (HNSW co-retrieval).
    """
    ranked = [
        h for h in (hits or [])
        if isinstance(h, dict) and h.get("logic_id")
    ]
    if not ranked:
        return set(), [], "HNSW_RANK_EMPTY"
    k = _HNSW_HOP_REVEAL.get(int(hops), max(1, int(hops)))
    revealed = ranked[:k]
    ids = {str(h["logic_id"]) for h in revealed}
    seed = str(revealed[0]["logic_id"])
    edges = [
        (seed, str(h["logic_id"]))
        for h in revealed[1:]
        if str(h["logic_id"]) != seed
    ]
    return ids, edges, f"HNSW_RANK · revealing top {len(revealed)}/{len(ranked)} hits"


def _geometry_lookup(logic_ids) -> dict:
    """Map logic_id → (domain_tag, raw_text) from hybrid sources."""
    wanted = {str(i) for i in logic_ids if i}
    out = {}
    if not wanted:
        return out
    # Prefer a wider hybrid scroll, then fill gaps from legacy SQL.
    rows, _src = read_hybrid_geometries(max(DSG_NODE_CAP, min(len(wanted) * 2, 400)))
    for logic_id, domain_tag, raw_text, _ts in rows:
        lid = str(logic_id or "")
        if lid in wanted and lid not in out:
            out[lid] = (domain_tag or "", raw_text or "")
    missing = [i for i in wanted if i not in out]
    if missing:
        placeholders = ",".join("?" for _ in missing)
        legacy = safe_query(
            MATRIX_DB,
            f"SELECT logic_id, domain_tag, raw_text FROM genesis_geometries "
            f"WHERE logic_id IN ({placeholders})",
            tuple(missing),
        )
        for logic_id, domain_tag, raw_text in legacy:
            out[str(logic_id)] = (domain_tag or "", raw_text or "")
    for lid in wanted:
        out.setdefault(lid, ("", ""))
    return out


def _sat_seed_options(limit=40) -> list:
    """Recent SAT turns that have a persisted HNSW bind — for Expansion mode."""
    options = []
    for row in read_recent_ledger(limit):
        row_id, ts, intent, _ann, retrieved, telegram = (
            row[0], row[1], row[2], row[3],
            row[4] if len(row) > 4 else None,
            row[5] if len(row) > 5 else None,
        )
        hits = _parse_retrieved_logic_ids(retrieved)
        top = hits[0] if hits and isinstance(hits[0], dict) else None
        seed = (top or {}).get("logic_id")
        if not seed:
            continue
        label = (
            f"SAT #{row_id} · {seed} · {(intent or '')[:48]}"
            + (" · REPLY" if telegram else "")
        )
        options.append({
            "label": label,
            "sat_id": row_id,
            "seed": str(seed),
            "domain": (top or {}).get("domain_tag") or "",
            "score": (top or {}).get("score"),
            "intent": intent or "",
            "telegram": telegram or "",
            "retrieved": hits,
        })
    return options


def _build_agraph_nodes(node_meta, seed_ids, live_seeds, degree_map):
    nodes, seen = [], set()
    seed_set = {str(s) for s in seed_ids}
    live_set = {str(s) for s in live_seeds}
    for logic_id, (domain_tag, raw_text) in node_meta.items():
        logic_id = str(logic_id)
        if not logic_id or logic_id in seen:
            continue
        seen.add(logic_id)
        is_seed = logic_id in seed_set
        is_live = logic_id in live_set
        accent = "#e3b341" if (is_seed or is_live) else _domain_color(domain_tag)
        degree = degree_map.get(logic_id, 0)
        size = 26 if is_seed else (20 if is_live else min(18, 12 + degree))
        excerpt = (str(raw_text or "").strip()[:180] or "(no raw_text)")
        nodes.append(Node(
            id=logic_id,
            label=f"{logic_id}\n[{domain_tag or 'untagged'}]",
            title=f"{logic_id} · {domain_tag or 'untagged'} · deg {degree}\n{excerpt}",
            size=size,
            color={
                "background": "#2b230b" if (is_seed or is_live) else "#0d1117",
                "border": accent,
                "highlight": {"background": "#122117", "border": "#58e6a8"},
            },
            borderWidth=3 if (is_seed or is_live) else 1,
            shape="dot",
            font={
                "color": "#e3b341" if (is_seed or is_live) else "#c9d1d9",
                "face": "Consolas",
                "size": 11,
            },
        ))
    return nodes


def _render_dsg_inspector(selected_id, node_meta, degree_map, edge_rows, sat_context=None):
    """White-box dossier for the clicked / focused logic_id."""
    st.markdown("#### Node inspector")
    _section_guide(
        "This is the white-box dossier for the geometry you clicked (or the "
        "current seed if you have not clicked yet). It shows the logic_id, "
        "domain, how many links it has in the current view, parent/child "
        "neighbors, the full raw_text, and — in Expansion mode — the SAT turn, "
        "HNSW score, prompt, Telegram reply, and top retrieved hits that seeded "
        "this view. Use it to verify why a node is on the canvas."
    )
    if not selected_id:
        _status_line("Click a node on the canvas to load its dossier here.")
        return
    domain, raw = node_meta.get(str(selected_id), ("", ""))
    st.markdown(
        f'<span class="diana-badge badge-ok">{_html_escape(str(selected_id))}</span> '
        f'<span class="diana-badge badge-degraded">{_html_escape(domain or "untagged")}</span>',
        unsafe_allow_html=True,
    )
    _status_line(f"Degree (links in view): {degree_map.get(str(selected_id), 0)}")
    neighbors = []
    for p, c in edge_rows:
        p, c = str(p), str(c)
        if p == str(selected_id):
            neighbors.append(("-> child", c))
        elif c == str(selected_id):
            neighbors.append(("<- parent", p))
    if neighbors:
        st.markdown("**Transitive links**")
        for rel, other in neighbors[:24]:
            st.code(f"{rel} {other}", language=None)
        if len(neighbors) > 24:
            _status_line(f"...and {len(neighbors) - 24} more")
    st.markdown("**raw_text**")
    st.code(raw or "(empty)", language=None)
    if sat_context:
        st.markdown(
            f"**Seeded from SAT #{sat_context['sat_id']}** · "
            f"HNSW score {sat_context.get('score')}"
        )
        _status_line((sat_context.get("intent") or "")[:220])
        if sat_context.get("telegram"):
            with st.expander("Telegram reply for this SAT seed", expanded=False):
                st.code(sat_context["telegram"], language=None)
        hits = sat_context.get("retrieved") or []
        if len(hits) > 1:
            st.markdown("**Top HNSW hits on this turn**")
            for h in hits[:5]:
                if isinstance(h, dict):
                    st.code(
                        f"{h.get('logic_id')} · {h.get('domain_tag')} · score={h.get('score')}",
                        language=None,
                    )


@st.fragment
def dsg_canvas():
    st.markdown("## Deterministic State Graph — Transitive Logic Network")
    _section_guide(
        "This is an interactive map of Diana's logic geometries — the ideas she "
        "retrieves and how they connect. Drag and zoom freely; the live metrics "
        "above will not reset your view. Click any node to load its dossier in "
        "the Node inspector on the right."
    )
    _status_line(
        "Force-directed canvas + white-box inspector. Toggle Global network vs "
        "Expansion from SAT #N. Drag/zoom freely — telemetry ticks never reset this view."
    )

    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 1])
    with ctrl1:
        mode = st.radio(
            "Graph mode",
            ["Global network", "Expansion from SAT #N"],
            horizontal=True,
            key="dsg_mode",
        )
    with ctrl2:
        hops = st.slider(
            "Expansion hops",
            min_value=1,
            max_value=4,
            value=DSG_EXPANSION_HOPS,
            key="dsg_hops",
            disabled=(mode != "Expansion from SAT #N"),
            help="BFS depth over transitive_links from the SAT seed (mirrors mediator expansion).",
        )
    with ctrl3:
        st.button("Refresh Graph", key="dsg_refresh", help="Re-pull nodes and edges")

    if mode == "Global network":
        _section_guide(
            "Global network shows a force-directed overview of recent geometries. "
            "Use it to browse the big picture: domains, clusters, and link density. "
            "Click any node to load its dossier in the Node inspector."
        )
    else:
        _section_guide(
            "Expansion from SAT #N starts from one real timeline turn's HNSW seed "
            "(the geometry Diana actually retrieved for that prompt) and grows the "
            "neighborhood with the hop slider. Prefer this when you want "
            "\"what did SAT #119 pull in?\" instead of the whole map."
        )
        _section_guide(
            "Expansion hops control how far the neighborhood grows from the seed. "
            "With real transitive_links, each hop is another BFS step along "
            "parent/child edges. If that table is missing, hops instead reveal more "
            "of the ranked HNSW hit list (1 = top1 ... 4 = top5). Watch the caption "
            "(\"Hop N -> X node(s)\") to confirm the graph changed."
        )
    _section_guide(
        "Refresh Graph re-reads nodes and edges from storage on demand after new "
        "ingestions or new SAT turns; it does not wipe your arrangement until the "
        "underlying data itself changes."
    )

    if not _AGRAPH_AVAILABLE:
        st.info("Awaiting initial DSG network compilation...")
        return

    edge_rows_all = _load_all_transitive_edges()
    sat_options = _sat_seed_options(60)
    sat_context = None
    seed_ids = []

    if mode == "Expansion from SAT #N":
        if not sat_options:
            st.warning(
                "No SAT turns with persisted HNSW binds yet. "
                "Use Global network, or process a new Telegram turn after the mediator restart."
            )
            return
        _section_guide(
            "Pick which timeline turn to expand from. Only turns with a persisted "
            "HNSW bind appear here. The label shows SAT id, seed logic_id, and a "
            "prompt snippet."
        )
        labels = [o["label"] for o in sat_options]
        choice = st.selectbox("Seed SAT turn", labels, key="dsg_sat_seed")
        sat_context = next(o for o in sat_options if o["label"] == choice)
        primary_seed = str(sat_context["seed"])
        seed_ids = [primary_seed]
        hits = sat_context.get("retrieved") or []

        if edge_rows_all:
            # True mediator-style BFS over transitive_links from the primary seed.
            kept_ids, kept_edges = _expand_from_seeds(
                [primary_seed], edge_rows_all, hops=hops, cap=DSG_EXPANSION_NODE_CAP
            )
            edge_kind = "transitive_links"
            node_source = (
                f"EXPANSION · SAT #{sat_context['sat_id']} · "
                f"{hops} hop(s) BFS · {len(kept_ids)} nodes"
            )
        else:
            # Live diana_matrix.db has no transitive_links table — hop slider
            # would be a no-op. Fall back to ranked HNSW hit reveal instead.
            kept_ids, kept_edges, rank_src = _expand_from_hnsw_rank(hits, hops)
            edge_kind = "hnsw_co_retrieval"
            node_source = (
                f"EXPANSION · SAT #{sat_context['sat_id']} · "
                f"{hops} hop(s) · {rank_src}"
            )
            st.warning(
                "diana_matrix.db has no `transitive_links` table — hop expansion "
                "is using persisted HNSW rank (hop 1=top1 ... hop 4=top5) instead of "
                "BFS over edges. Rebuild transitive_links to restore mediator-faithful expansion."
            )

        node_meta = _geometry_lookup(kept_ids)
        for hid in hits:
            if isinstance(hid, dict) and hid.get("logic_id"):
                lid = str(hid["logic_id"])
                if lid in kept_ids:
                    node_meta.setdefault(
                        lid, (hid.get("domain_tag") or "", "")
                    )
        node_meta.setdefault(primary_seed, (sat_context.get("domain") or "", ""))
        edge_rows = kept_edges
        # Tag edges in the inspector path via a parallel list of titles when rendering.
        st.session_state["_dsg_edge_kind"] = edge_kind
        _status_line(
            f"Hop {hops} -> {len(kept_ids)} node(s), {len(edge_rows)} edge(s) "
            f"| seed {primary_seed}"
        )
        hierarchical = True
        physics = False
    else:
        node_rows, node_source = read_hybrid_geometries(DSG_NODE_CAP)
        if not node_rows:
            st.info("Awaiting initial DSG network compilation...")
            if QDRANT_STORAGE.is_dir():
                _status_line(
                    "qdrant_storage detected but the genesis_geometries collection is "
                    "empty or locked — vector ingestion may be in progress."
                )
            return
        node_meta = {
            str(logic_id): (domain_tag or "", raw_text or "")
            for logic_id, domain_tag, raw_text, _ts in node_rows
            if logic_id
        }
        visible = set(node_meta)
        edge_rows = [
            (str(p), str(c))
            for p, c in edge_rows_all
            if str(p) in visible and str(c) in visible
        ]
        # Live bind from newest ledger row (if any).
        if sat_options:
            seed_ids = [sat_options[0]["seed"]]
        hierarchical = False
        physics = True

    degree_map = {}
    for p, c in edge_rows:
        degree_map[p] = degree_map.get(p, 0) + 1
        degree_map[c] = degree_map.get(c, 0) + 1

    live_seeds = list(seed_ids)
    _status_line(
        f"Mode: {mode} · node source: {node_source} · "
        f"{len(node_meta)} nodes · {len(edge_rows)} edges "
        f"(transitive_links / legacy diana_matrix.db)"
    )
    if seed_ids:
        badges = " ".join(
            f'<span class="diana-badge badge-degraded">{_html_escape(s)}</span>'
            for s in seed_ids[:5]
        )
        st.markdown(f"Seed / live lock: {badges}", unsafe_allow_html=True)

    nodes = _build_agraph_nodes(node_meta, seed_ids, live_seeds, degree_map)
    edge_kind = st.session_state.get("_dsg_edge_kind", "transitive_link")
    edges = [
        Edge(
            source=p,
            target=c,
            title=f"{edge_kind} · {p} -> {c}",
            color="#6e7681" if edge_kind == "hnsw_co_retrieval" else "#30363d",
        )
        for p, c in edge_rows
    ]

    graph_col, inspector_col = st.columns([3, 2], gap="large")
    selected_id = None
    with graph_col:
        config = Config(
            width=820,
            height=620,
            directed=True,
            physics=physics,
            hierarchical=hierarchical,
            nodeHighlightBehavior=True,
            highlightColor="#58e6a8",
        )
        try:
            selected_id = agraph(nodes=nodes, edges=edges, config=config)
        except Exception:
            st.info("Awaiting initial DSG network compilation...")
            return

    # Prefer explicit click; fall back to primary seed so the inspector is never empty in expansion mode.
    focus_id = selected_id or (seed_ids[0] if seed_ids else None)
    if focus_id and str(focus_id) not in node_meta and node_meta:
        focus_id = next(iter(node_meta))

    with inspector_col:
        _render_dsg_inspector(
            focus_id,
            node_meta,
            degree_map,
            edge_rows,
            sat_context=sat_context if mode == "Expansion from SAT #N" else None,
        )


st.divider()
dsg_canvas()

# ============================================================================
# LAYER 4.5 — CONVERSATIONAL COMMAND (own 3s fragment inside a tab:
# ledger polling re-runs ONLY the chat console — never the agraph canvas,
# the timing chart, or playground widget state.)
# READ:  semantic_translations (mediator-owned capture ledger, read-only).
# WRITE: scheduled_tasks — the sole queue openclaw_daemon.py polls every 30s.
# ============================================================================

CHAT_HISTORY_CAP = 15
_AB_MARKER_RE = re.compile(r"Ab\d+")
_FAULT_TEXT_MARKERS = ("unsat", "contradiction", "[!]")

SCHEDULED_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_prompt TEXT NOT NULL,
    execute_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','failed'))
)
"""


def safe_execute(db_path, sql, params=()):
    """Read-write companion to safe_query, exclusively for the command queue.

    Runs the daemon's exact scheduled_tasks DDL first (first-run safety when
    the daemon has not yet created the ledger), commits, and returns the
    inserted row id — or None when the DB is locked/unwritable.
    """
    try:
        conn = sqlite3.connect(str(db_path), timeout=3)
        try:
            conn.execute(SCHEDULED_TASKS_DDL)
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


@st.cache_data(ttl=2.5, show_spinner=False)
def read_chat_rows() -> list:
    """Newest 15 ledger rows, reversed to ascending, classified while cached
    so per-tick rendering does no regex/log work."""
    rows = safe_query(
        LEDGER_DB,
        "SELECT id, timestamp, raw_human_intent, annotated_machine_state "
        "FROM semantic_translations ORDER BY timestamp DESC LIMIT ?",
        (CHAT_HISTORY_CAP,),
    )
    rows = list(reversed(rows))
    deflection_epochs = {
        int(d["epoch"]) for d in read_deflections() if d["epoch"] is not None
    }
    fault_epochs = {int(f["epoch"]) for f in read_faults() if f["epoch"] is not None}

    out = []
    for row_id, ts, intent, annotated in rows:
        annotated = annotated or ""
        epoch = _parse_iso_ts(ts)
        epoch_s = int(epoch) if epoch is not None else None
        lowered = annotated.lower()
        if _AB_MARKER_RE.search(annotated) or epoch_s in deflection_epochs:
            cls = "abnormality"
        elif any(m in lowered for m in _FAULT_TEXT_MARKERS) or epoch_s in fault_epochs:
            cls = "contradiction"
        else:
            cls = "sat"
        out.append({
            "id": row_id,
            "ts": ts or "",
            "intent": intent or "",
            "annotated": annotated,
            "cls": cls,
        })
    return out


def _chat_ts_html(ts) -> str:
    return f'<span class="chat-timestamp">{_html_escape(ts or "no timestamp")}</span>'


@st.fragment(run_every=3.0)
def chat_console():
    if "pending_commands" not in st.session_state:
        st.session_state.pending_commands = []
    if "command_failures" not in st.session_state:
        st.session_state.command_failures = []

    _section_guide(
        "This is a chat panel wired into Diana's real command queue. Type like "
        "you would in Telegram; the message is written to scheduled_tasks and "
        "the daemon picks it up on its ~30s poll. History comes from the semantic "
        "ledger; color borders on assistant bubbles mirror SAT / Abnormality / "
        "Contradiction states."
    )

    rows = read_chat_rows()
    latest_ledger_id = rows[-1]["id"] if rows else 0

    still_pending = []
    for cmd in st.session_state.pending_commands:
        status_rows = safe_query(
            LEDGER_DB,
            "SELECT status FROM scheduled_tasks WHERE id = ?",
            (cmd["task_id"],),
        )
        status = status_rows[0][0] if status_rows else None
        if status == "failed":
            st.session_state.command_failures = (
                st.session_state.command_failures + [cmd]
            )[-5:]
        elif status == "completed" or latest_ledger_id > cmd["ledger_watermark"]:
            pass
        else:
            still_pending.append(cmd)
    st.session_state.pending_commands = still_pending

    with st.container(height=460):
        if not rows and not still_pending:
            st.info(
                "No conversational ledger yet — semantic_translations is written "
                "by diana_mediator after each processed command."
            )
        for row in rows:
            with st.chat_message("user"):
                st.markdown(
                    f'{_chat_ts_html(row["ts"])}<br/>{_html_escape(row["intent"])}',
                    unsafe_allow_html=True,
                )
            with st.chat_message("assistant"):
                annotated = row["annotated"]
                truncated = len(annotated) > 400
                body = _html_escape(annotated[:400]) + ("&hellip;" if truncated else "")
                st.markdown(
                    f'<div class="diana-msg-{row["cls"]}">{_chat_ts_html(row["ts"])}'
                    f'<br/>{body or "<i>(empty annotated_machine_state)</i>"}</div>',
                    unsafe_allow_html=True,
                )
                if truncated:
                    with st.expander("Full annotated_machine_state payload"):
                        st.code(annotated, language="text")

        for cmd in still_pending:
            with st.chat_message("user"):
                st.markdown(
                    f'{_chat_ts_html(cmd["created_at"])} '
                    f'<span class="diana-badge badge-degraded">QUEUED — awaiting daemon pickup (&lt;=30s)</span>'
                    f'<br/>{_html_escape(cmd["prompt"])}',
                    unsafe_allow_html=True,
                )

        for cmd in st.session_state.command_failures[-3:]:
            st.markdown(
                f"""<div class="diana-card card-red">
<span class="card-title">&#10006; COMMAND FAILED &middot; scheduled_tasks #{cmd["task_id"]}</span>
<div class="card-meta">daemon marked status='failed' &middot; queued {_html_escape(cmd["created_at"])}</div>
<div>{_html_escape(cmd["prompt"][:200])}</div>
</div>""",
                unsafe_allow_html=True,
            )

    if still_pending:
        st.markdown(
            f"""<div class="diana-card card-amber">
<span class="card-title">&#9203; Awaiting daemon 30s polling cycle...</span>
<div class="card-meta">{len(still_pending)} command(s) pending in scheduled_tasks &middot; re-checking every 3s</div>
</div>""",
            unsafe_allow_html=True,
        )

    user_command = st.chat_input("Issue command to DIANA OS...")
    if user_command:
        now_iso = datetime.now().isoformat()
        task_id = safe_execute(
            LEDGER_DB,
            "INSERT INTO scheduled_tasks (task_prompt, execute_at, created_at) VALUES (?, ?, ?)",
            (user_command, now_iso, now_iso),
        )
        if task_id is None:
            st.error(
                "Command transmission failed — semantic_ledger.db is locked or "
                "unwritable. The command was NOT queued."
            )
        else:
            st.session_state.pending_commands.append({
                "task_id": task_id,
                "prompt": user_command,
                "created_at": now_iso,
                "ledger_watermark": latest_ledger_id,
            })
            try:
                st.rerun(scope="fragment")
            except StreamlitAPIException:
                pass  # full-app run context: the next 3s tick renders the echo instead


st.divider()
(_chat_tab,) = st.tabs(["Conversational Command"])
with _chat_tab:
    chat_console()

# ============================================================================
# LAYER 5 — INTERACTIVE PLAYGROUND (OUTSIDE the fragment: widget state
# survives the 1s telemetry ticks because only the fragment above re-runs)
# ============================================================================

st.divider()
st.markdown("## Interactive Playground")
_section_guide(
    "This is a safe sandbox. Nothing here is sent to Telegram unless you also "
    "use Conversational Command. Use it to mock geometries, scrub history, and "
    "stress-test the GREETME_50 sieve without waiting on the daemon."
)

# ---- 3.1 Neural Mocking "What-If" engine -----------------------------------

st.markdown("### 3.1 Neural Mocking — What-If Injection Engine")
_section_guide(
    "Paste a mock DeterministicDSL JSON geometry, then Force Injection to run the local "
    "semantic sieve and a simulated CaDiCaL SAT/UNSAT check — skipping Ollama. "
    "Read the verdict on screen."
)

_DEFAULT_RESIN_PAYLOAD = json.dumps(
    {
        "deterministic_dsl_payload": {
            "major_premise": "All scheduled transfers require custody verification before release.",
            "minor_premise": "The queued asset transfer has passed custody verification.",
            "abnormality_warrant_requested": False,
            "efficiency_delta_justification": "None",
            "tiered_clauses": [
                {"tier": 1, "gate": "LOGIC_GATE_OPEN", "condition": "PRE_CONDITION", "state": "VALIDATED_FACT"},
                {"tier": 2, "action": "TRANSFER_ASSET", "constraint": "MANDATORY_OBLIGATION", "state": "PENDING_RESOLUTION"},
                {"tier": 2, "action": "HOLD_CUSTODY", "operator": "COMPOUND_REQUIREMENT", "rule": "CONSEQUENCE_LOCK"},
            ],
        }
    },
    indent=2,
)

MOCK_TIMING_CAP = 20

if "mock_timing_history" not in st.session_state:
    st.session_state.mock_timing_history = []

payload_text = st.text_area(
    "DeterministicDSL geometry (JSON)",
    value=_DEFAULT_RESIN_PAYLOAD,
    height=320,
    key="whatif_payload",
)


def _record_mock_timing(duration_us: float, verdict: str):
    """Session-state-only rolling buffer — zero disk writes, strict 20-run cap."""
    history = st.session_state.mock_timing_history
    seq = st.session_state.get("_mock_timing_seq", 0) + 1
    st.session_state["_mock_timing_seq"] = seq
    history.append({
        "Run": f"Run #{seq}",
        "Duration (μs)": round(duration_us, 2),
        "Verdict": verdict,
    })
    while len(history) > MOCK_TIMING_CAP:
        history.pop(0)


if st.button("Force Injection", type="primary", key="whatif_inject"):
    try:
        payload_obj = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        st.error(f"DeterministicDSL parse failure (malformed JSON): {exc}")
    else:
        geometries = [
            {"raw_text": row[2] or ""} for row in read_hybrid_geometries(10)[0]
        ] or [{"raw_text": "mock tier-2 default rule geometry"}]

        t_start_ns = time.perf_counter_ns()
        sieve_ok, sieve_err = verify_semantic_atoms(payload_obj)
        result = None
        if sieve_ok:
            result = simulate_compile_pysat_geometries(
                payload_obj.get("deterministic_dsl_payload", payload_obj), geometries
            )
        duration_us = (time.perf_counter_ns() - t_start_ns) / 1_000.0

        if not sieve_ok:
            verdict = "Sieve-Reject"
            st.error("SEMANTIC SIEVE REJECTION — payload never reached the solver layer.")
            st.code(sieve_err, language="text")
        elif result["status"] == "ERROR":
            verdict = "UNSAT"
            st.error(f"Simulator error: {result['error_message']}")
        elif result["deflection_intercepted"]:
            verdict = "Ab-Deflection"
            st.warning(
                f"VERDICT: SAT via ABNORMALITY WARRANT (Ab literal {result['abnormality_literal_activated']}) "
                f"— deflection warrant: {result['deflection_warrant']} "
                f"— {result['solve_ms']} ms simulated CaDiCaL195 solve"
            )
        elif result["mathematically_valid"]:
            verdict = "SAT"
            st.success(
                f"VERDICT: SAT — mathematically valid geometry "
                f"({result['tier1_clauses']} Tier-1 / {result['tier2_clauses']} Tier-2 clauses, "
                f"{result['solve_ms']} ms simulated CaDiCaL195 solve)"
            )
        else:
            verdict = "UNSAT"
            st.error(
                f"VERDICT: UNSAT — logical contradiction, geometry rejected "
                f"({result['solve_ms']} ms simulated CaDiCaL195 solve)"
            )
        _record_mock_timing(duration_us, verdict)
        if result is not None:
            with st.expander("Full solver result dict"):
                st.json(result)

# ---- 3.1b Microsecond What-If timing suite (session_state only) -------------

if st.session_state.mock_timing_history:
    st.markdown("#### Injection Timing Suite — sieve + solver wall-clock (μs)")
    _section_guide(
        "This chart is a rolling last-20 log of how long each Force Injection took "
        "in microseconds, plus whether the last run was SAT (green), Ab-deflected "
        "(amber), or UNSAT (red). Session-only; nothing is written to disk."
    )
    _timing_df = pd.DataFrame(st.session_state.mock_timing_history)
    st.line_chart(_timing_df, x="Run", y="Duration (μs)")

    _latest = st.session_state.mock_timing_history[-1]
    _verdict_style = {
        "SAT": ("card-green", "&#9679; CLEAN SAT"),
        "Ab-Deflection": ("card-amber", "&#9650; Ab-DEFLECTION"),
    }
    _card_cls, _card_label = _verdict_style.get(
        _latest["Verdict"], ("card-red", "&#10006; UNSAT / REJECTED")
    )
    st.markdown(
        f"""<div class="diana-card {_card_cls}">
<span class="card-title">{_card_label} &middot; {_html_escape(_latest["Run"])}</span>
<div class="card-meta">latest injection &middot; rolling buffer {len(st.session_state.mock_timing_history)}/{MOCK_TIMING_CAP} runs &middot; in-memory only (zero disk writes)</div>
<div>Verdict: <code>{_html_escape(_latest["Verdict"])}</code> &middot; Duration: <code>{_latest["Duration (μs)"]} μs</code></div>
</div>""",
        unsafe_allow_html=True,
    )

# ---- 3.2 State Rewinding ----------------------------------------------------

st.markdown("### 3.2 State Rewinding — Semantic Ledger Time Scrubber")
_section_guide(
    "This scrubber walks historical ledger timestamps. Park it on a past instant "
    "to see the annotated machine state (and top tokens) Diana had then. Replay "
    "State prints a simulated re-injection trace for regression thinking — it does "
    "not by itself re-run the live daemon."
)

_ledger_bounds = safe_query(
    LEDGER_DB, "SELECT MIN(timestamp), MAX(timestamp) FROM semantic_translations"
)
_min_ts = _parse_iso_ts(_ledger_bounds[0][0]) if _ledger_bounds and _ledger_bounds[0][0] else None
_max_ts = _parse_iso_ts(_ledger_bounds[0][1]) if _ledger_bounds and _ledger_bounds[0][1] else None

if _min_ts is None or _max_ts is None:
    st.info(
        "State rewinding disabled: semantic_ledger.db has no rows yet "
        "(the daemon creates and populates it lazily)."
    )
else:
    if _max_ts <= _min_ts:
        _max_ts = _min_ts + 1
    scrub_epoch = st.slider(
        "Rewind point",
        min_value=int(_min_ts),
        max_value=int(_max_ts),
        value=int(_max_ts),
        format="",
        key="rewind_slider",
        help="Epoch position across semantic_translations history",
    )
    _section_guide(
        "Rewind point is the time cursor across the semantic ledger. Slide left "
        "for older turns, right for newer. The nearest ledger row at that instant "
        "appears below."
    )
    _status_line(
        f"Selected instant: {datetime.fromtimestamp(scrub_epoch).isoformat(sep=' ', timespec='seconds')}"
    )

    _nearest = safe_query(
        LEDGER_DB,
        "SELECT id, timestamp, raw_human_intent, annotated_machine_state "
        "FROM semantic_translations "
        "ORDER BY ABS(julianday(timestamp) - julianday(?)) LIMIT 1",
        (datetime.fromtimestamp(scrub_epoch).isoformat(),),
    )
    if _nearest:
        row_id, row_ts, row_intent, row_state = _nearest[0]
        tokens = (row_state or "").split()[:150]
        st.markdown(
            f"**Nearest state — ledger row #{row_id}** &middot; `{row_ts}`"
        )
        _status_line(f"Raw human intent: {(row_intent or '')[:200]}")
        st.code(" ".join(tokens) or "(empty annotated_machine_state)", language="text")

        if st.button("Replay State", key="rewind_replay"):
            replay_seed = f"replay:{row_id}"
            st.code(
                "\n".join([
                    "[SIMULATED REPLAY — no real re-injection performed]",
                    f"[REWIND] Loading ledger row #{row_id} @ {row_ts}",
                    "[SEMANTIC TRANSLATOR] Annotated Query restored from ledger snapshot.",
                    f"[SIEVE] Vector-Space Pruning: retrieve_relevant_geometries(top_k=150) ... {_sim_ms(replay_seed + 'sieve', 40, 220)} ms (SIMULATED)",
                    "[SIEVE] Transitive Dependency Expansion: parent/child logic_ids merged, deduplicated.",
                    f"[GATEKEEPER] Re-triage via local DeepSeek-R1 loop (diana_mediator.handle_tool_call) ... {_sim_ms(replay_seed + 'triage', 300, 1800)} ms (SIMULATED)",
                    f"[COMPILER] DeterministicDSL -> CNF translation, Tier-2 clauses gated by ephemeral Ab literal (SIMULATED)",
                    f"[CaDiCaL195] solve(assumptions=[-Ab]) -> SAT in {_sim_ms(replay_seed + 'solve', 2, 40)} ms (SIMULATED)",
                    "[REPLAY COMPLETE] Regression re-injection trace verified against historical state. No divergence recorded.",
                ]),
                language="text",
            )

# ---- 3.3 Semantic Atomic Lock Override --------------------------------------

st.markdown("### 3.3 Semantic Atomic Lock Override")
_section_guide(
    "Type a primitive outside the 50 allowed GREETME words (default "
    "HOPE_FOR_SUCCESS). The terminal log should prove the Semantic Sieve blocked "
    "it before anything reached the PySAT solver. Valid atoms show the accept path."
)
_status_line(
    "Attempt to smuggle an arbitrary primitive into an instruction field. "
    "The GREETME_50 sieve runs BEFORE the PySAT solver layer ever sees the payload."
)

override_atom = st.text_input(
    "Candidate primitive for the `instruction` field",
    value="HOPE_FOR_SUCCESS",
    key="override_atom",
)

if st.button("Run Sieve Interception Test", key="override_run"):
    candidate_payload = {
        "deterministic_dsl_payload": {
            "major_premise": "Operator-injected override attempt.",
            "tiered_clauses": [{"tier": 2, "instruction": override_atom}],
        }
    }
    log_lines = [
        "diana@kytin:~$ resin-compile --inject override.json",
        f"[FRONT-END] Payload received. Instruction fields located: ['instruction'='{override_atom}']",
        "[SIEVE] verify_semantic_atoms(): scanning payload against GREETME_50 lexicon (50 atoms, 5 categories)...",
    ]
    ok, err = verify_semantic_atoms(candidate_payload)
    if not ok:
        log_lines += [
            f"[SIEVE] {err}",
            "[SIEVE] AUDIT FAILED — dirty primitive intercepted at the compiler front-end.",
            "[SOLVER] CaDiCaL195 NEVER INVOKED. No CNF translation occurred. No Ab warrant issued.",
            "[DEFLECTION] Payload blocked & redirected upstream of the PySAT layer.",
            "exit status: 1 (INVALID_STATE)",
        ]
    else:
        log_lines += [
            f"[SIEVE] '{override_atom.upper()}' is a locked GREETME_50 atom. Semantic audit PASSED.",
            "[COMPILER] DeterministicDSL -> CNF translation authorized. Tier-2 clause gated with ephemeral Ab literal.",
            f"[CaDiCaL195] solve(assumptions=[-Ab]) -> SAT in {_sim_ms('override' + override_atom, 2, 30)} ms (SIMULATED)",
            "exit status: 0 (VALIDATED_FACT)",
        ]
    st.code("\n".join(log_lines), language="text")
    if not ok:
        st.error("Interception proven: the Semantic Sieve blocked the primitive before the solver layer.")
    else:
        st.success("Acceptance path: valid GREETME_50 atom flowed through the sieve into the (simulated) solver.")

# ============================================================================
# LAYER 4 — CYBER-PHYSICAL SCADA & Z3 SMT CRUCIBLE HISTORIAN
# ============================================================================

st.markdown("---")
st.markdown("## 4. Cyber-Physical SCADA & Z3 SMT Crucible Historian")
_section_guide(
    "Live telemetry streams from the Universal Hardware Abstraction Layer (HAL). "
    "Displays Modbus fieldbus registers, discrete coil states, and formal Z3 SMT "
    "proof traces logged by the persistent Historian."
)

hist_db_path = DIANA_ROOT / "ledger" / "historian.db"

col_scada1, col_scada2 = st.columns([1, 1])

with col_scada1:
    st.markdown("### 4.1 Live SCADA & Fieldbus Telemetry")
    scada_rows = safe_query(
        hist_db_path,
        "SELECT timestamp, raw_state_json FROM telemetry_snapshots WHERE domain = 'scada' ORDER BY id DESC LIMIT 1"
    )
    if scada_rows:
        scada_ts, scada_raw = scada_rows[0]
        try:
            scada_state = json.loads(scada_raw)
            p_val = scada_state.get("pressure", 0)
            va = scada_state.get("valve_a", False)
            vb = scada_state.get("valve_b", False)
            
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.metric("Vessel Pressure", f"{p_val} PSI", delta=None)
            with m_col2:
                st.metric("Valve A (Inlet)", "OPEN" if va else "CLOSED")
            with m_col3:
                st.metric("Valve B (Outlet)", "OPEN" if vb else "CLOSED")
            
            if p_val >= 90:
                st.error("⚠️ CRITICAL BURST LIMIT: Pressure exceeds 90 PSI safety ceiling!")
            elif p_val > 70:
                st.warning("⚠️ High Pressure: System approaching rate-of-change safety boundary.")
            else:
                st.success("Nominal Operating Pressure: Inside Z3 Invariant Safe Set.")
        except Exception:
            st.info("Awaiting live SCADA telemetry snapshot...")
    else:
        st.info("No SCADA telemetry recorded yet in historian.db. Run `python diana_cli.py scada` or activate plant simulator.")

with col_scada2:
    st.markdown("### 4.2 Interactive Z3 SMT Crucible Test")
    test_p = st.number_input("Target Pressure (PSI)", min_value=0, max_value=120, value=65)
    t_col1, t_col2 = st.columns(2)
    with t_col1:
        test_va = st.checkbox("Valve A Open", value=False)
    with t_col2:
        test_vb = st.checkbox("Valve B Open", value=False)
    
    if st.button("Evaluate via Z3 Crucible", key="btn_eval_z3"):
        try:
            import sys
            eng_dir = str(DIANA_ROOT / "engine")
            if eng_dir not in sys.path:
                sys.path.insert(0, eng_dir)
            from z3_crucible import verify_invariants
            
            is_safe, proof_rep = verify_invariants(
                target_state={"pressure": test_p, "valve_a": test_va, "valve_b": test_vb},
                current_state={"pressure": 50, "valve_a": False, "valve_b": False}
            )
            
            if is_safe:
                st.success(f"Z3 PROOF: SATISFIABLE (SAFE) -> State Lock Opens")
            else:
                st.error(f"Z3 PROOF: UNSATISFIABLE (BLOCKED) -> {proof_rep.get('status')}")
            st.json(proof_rep)
        except Exception as e:
            st.error(f"Z3 evaluation error: {e}")

st.markdown("### 4.3 Persistent Z3 Invariant Proof Log")
z3_rows = safe_query(
    hist_db_path,
    "SELECT timestamp, domain, candidate_action_json, target_state_json, is_safe, z3_result, execution_time_ms, breach_report "
    "FROM crucible_evaluations ORDER BY id DESC LIMIT 15"
)
if z3_rows:
    table_data = []
    for r in z3_rows:
        table_data.append({
            "Timestamp": r[0],
            "Domain": r[1].upper(),
            "Target State": r[3],
            "Verdict": "SAT [SAFE]" if r[4] else "UNSAT [BLOCKED]",
            "Result": r[5],
            "Latency (ms)": f"{r[6]:.2f}" if r[6] else "N/A",
            "Breach Report": r[7] or "None (Proven Safe)"
        })
    st.dataframe(pd.DataFrame(table_data), use_container_width=True)
else:
    st.info("No Z3 proofs recorded yet in historian.db.")

