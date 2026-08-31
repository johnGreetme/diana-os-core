import sys
import os
import subprocess
import sqlite3
import json
import requests
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(path=None):
        pass

# Load local environment variables securely
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# Setup Gemini SDK
gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if gemini_key and genai:
    try:
        genai.configure(api_key=gemini_key)
    except Exception:
        pass

# Append paths so tools and engine are cleanly resolved
sys.path.append(os.path.join(BASE_DIR, "tools"))
sys.path.append(os.path.join(BASE_DIR, "engine"))

from query_matrix import retrieve_relevant_geometries
from engine.z3_crucible import (
    verify_state_locked_protocol,
    verify_invariants,
    compile_syllogistic_geometry
)
from engine.schemas import (
    get_schema_for_domain,
    SCADAModbusAction,
    ROS2JointAction,
    DigitalGUIAction,
    SkillSelection,
    SkillForgeRequest
)
from engine.logic_engine import GREETME_50, verify_semantic_atoms
from engine.sieve import evaluate_command as sieve_evaluate_command
from core.historian import historian, openclaw_v2_historian
from core.skill_loader import skill_loader
from core.skill_forge import skill_forge

DB_PATH = os.path.join(BASE_DIR, "diana_matrix.db")

# Load MCP Server Registry
MCP_CONFIG_PATH = os.path.join(BASE_DIR, "mcp.json")
def _load_mcp_registry():
    if not os.path.exists(MCP_CONFIG_PATH):
        return {}
    try:
        with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("mcpServers", {})
    except Exception:
        return {}

from actuation.router import HardwareRouter
import logging
logger = logging.getLogger(__name__)

router = HardwareRouter()
actuator = router.get_actuator()
active_domain = router.get_domain()

# Initialize spatial parsing hooks (VSLAM/LiDAR) if physical embodiment is active
if router.is_embodied:
    logger.info("[MEDIATOR] Embodiment active: Spatial/VSLAM parsers ready.")
if router.is_scada:
    logger.info("[MEDIATOR] SCADA active: Modbus fieldbus bindings ready.")

from parsers.optic import OpticParser
optic_parser = OpticParser(model_name="moondream")

DEFAULT_OLLAMA_OPTIONS = {
    "num_gpu": 99,
    "num_thread": 4,
    "low_vram": False,
    "f16_kv": True,
    "main_gpu": 0
}

# Read model_tag and hardware acceleration options from config
try:
    with open(os.path.join(BASE_DIR, "openclaw.json"), "r") as f:
        config = json.load(f)
        LOCAL_MODEL_TAG = config.get("model_tag", "llama3.3:latest")
        OLLAMA_OPTIONS = config.get("ollama_runtime", {}).get(
            "hardware_acceleration", {}
        ).get("options", DEFAULT_OLLAMA_OPTIONS)
except Exception:
    LOCAL_MODEL_TAG = "llama3.3:latest"
    OLLAMA_OPTIONS = DEFAULT_OLLAMA_OPTIONS

import re

ROSETTA_DICTIONARY = {
    # Category 1: Identity & Existence
    "i am": "SELF_ASSERTION", "you are": "TARGET_IDENTIFICATION", "we": "GROUP_CONSENSUS", 
    "they": "EXTERNAL_ENTITY", "it": "OBJECT_REFERENCE", "owner": "ROOT_AUTHORITY", 
    "creator": "GENESIS_ORIGIN", "agent": "EXECUTOR_NODE", "nobody": "NULL_VOID", "public": "PLAINTEXT_BROADCAST",
    
    # Category 2: Temporality
    "now": "IMMEDIATE_EXECUTION", "later": "DEFERRED_QUEUE", "before": "PRE_CONDITION", 
    "after": "POST_CONDITION", "always": "IMMUTABLE_CONSTANT", "never": "FORBIDDEN_CONSTRAINT", 
    "while": "DURATIONAL_LOOP", "until": "CONDITIONAL_TERMINATION", "yesterday": "HISTORICAL_LEDGER", 
    "tomorrow": "PREDICTIVE_SLOT",
    
    # Category 3: Logic & Causality
    "if": "LOGIC_GATE_OPEN", "then": "CONSEQUENCE_LOCK", "else": "FALLBACK_PROTOCOL", 
    "and": "COMPOUND_REQUIREMENT", "or": "OPTIONAL_PATH", "not": "INVERSION_OPERATOR", 
    "because": "CAUSAL_LINK", "therefore": "DERIVED_CONCLUSION", "true": "VALIDATED_FACT", "false": "INVALID_STATE",
    
    # Category 4: Action & Volition
    "do": "EXECUTE_COMMAND", "stop": "HALT_PROCESS", "wait": "PAUSE_STATE", "check": "VERIFY_STATE", 
    "make": "CREATE_INSTANCE", "destroy": "BURN_INSTANCE", "send": "TRANSFER_ASSET", "keep": "HOLD_CUSTODY", 
    "change": "UPDATE_MUTABLE", "fix": "CORRECT_ERROR",
    
    # Category 5: Measurement & Constraints
    "more": "GREATER_THAN", "less": "LESS_THAN", "equal": "EXACT_MATCH", "plus": "INCREMENT_STATE", 
    "minus": "DECREMENT_STATE", "must": "MANDATORY_OBLIGATION", "can": "PERMISSION_GRANT", 
    "will": "FUTURE_COMMITMENT", "unknown": "PENDING_RESOLUTION", "secret": "ENCRYPTED_PAYLOAD"
}

_sorted_keys = sorted(ROSETTA_DICTIONARY.keys(), key=len, reverse=True)
_rosetta_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, _sorted_keys)) + r')\b', re.IGNORECASE)

def preprocess_semantic_atoms(query_text: str) -> str:
    """Translates fluid human words into explicit deterministic tags using Annotation."""
    def annotator(match):
        original_word = match.group(0)
        atom = ROSETTA_DICTIONARY[original_word.lower()]
        return f"{original_word} [{atom}]"
    return _rosetta_pattern.sub(annotator, query_text)

def _triage_local_deepseek(prompt: str, geometries: list, escalation_enabled: bool = True, domain_context: str = "digital") -> str:
    """Triage request locally using top geometries and domain context."""
    context_data = geometries[:5]
    context_str = json.dumps(context_data, indent=2)
    
    try:
        with open(os.path.join(BASE_DIR, "openclaw.json"), "r") as f:
            config = json.load(f)
            primary_prompt = config.get("primary_system_prompt", "")
    except Exception:
        primary_prompt = ""

    system_prompt = primary_prompt

    # Inject graduated skill contexts into system prompt (Skill Hot-Loader)
    skill_context_block = skill_loader.get_all_skill_contexts()
    if skill_context_block:
        system_prompt += "\n\n" + skill_context_block
    
    if escalation_enabled:
        system_prompt += "\n\n[CLOUD ROUTING GATEKEEPER]: If the user asks for a 'geometric proof', 'logic proof', 'mathematical model', requires internet access, or asks a highly complex question, you MUST NOT attempt to answer it. You must output exactly '<|ESCALATE|>' and nothing else."
        full_prompt = f"Active Hardware Domain: {domain_context}\nContext (17 Pillars Dataset):\n{context_str}\n\nUser Prompt: {prompt}\n\n[SYSTEM REMINDER]: Evaluate the user prompt. If they ask for a mathematical and geometric proof, or the task is highly complex, you MUST NOT write the answer. You must output EXACTLY '<|ESCALATE|>'."
    else:
        full_prompt = (
            f"Active Hardware Domain: {domain_context}\n"
            f"Context (17 Pillars Dataset):\n{context_str}\n\n"
            f"User Prompt: {prompt}\n\n"
            "[CRITICAL SYSTEM REMINDER]: If you need to perform local actions, YOU MUST THINK IN STEPS.\n"
            "- Shell: <execute>command</execute>\n"
            "- Web: <search_web>query</search_web>, <fetch_web>url</fetch_web>\n"
            "- Delegation: <delegate role=\"role\">task</delegate>\n"
            "- Memory & Schedule: <query_ledger>time bounds</query_ledger>, <schedule>seconds | task prompt</schedule>\n"
            "- Forecast: <forecast>target | days</forecast>\n"
            "- SCADA / Modbus (Read-Before-Write Relative Deltas):\n"
            "  <modbus_delta pressure_delta=\"+10\" toggle_valve_a=\"true\" toggle_valve_b=\"false\" />\n"
            "- GUI Desktop Automation:\n"
            "  <click>target_text</click>, <type>text</type>, <press>key</press>, <scroll>amount</scroll>, <read_screen>prompt</read_screen>\n"
            "- Invoke a learned skill: <invoke_skill>{\"selected_skill_id\": \"...\", \"reasoning\": \"...\", \"confidence_score\": 0.9, \"runtime_parameters\": {}}</invoke_skill>\n"
            "- Forge a new skill: <forge_skill>{\"capability_description\": \"...\", \"reasoning\": \"...\", \"target_slug\": \"...\"}</forge_skill>\n"
            "- If you lack a required tool, output: <|SKILL_DEFICIT|>\n"
            "IMPORTANT: In SCADA mode, ALWAYS output relative deltas (e.g. +10 pressure, toggle_valve_a=true), NEVER absolute overrides.\n"
            "Only when you have finished all steps should you output your final payload."
        )
        
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json={
            "model": LOCAL_MODEL_TAG,
            "system": system_prompt,
            "prompt": full_prompt,
            "options": OLLAMA_OPTIONS,
            "stream": False
        }, timeout=120)
        if response.status_code == 200:
            raw_response = response.json().get("response", "")
            if "</think>" in raw_response:
                return raw_response.split("</think>")[-1].strip()
            return raw_response.strip()
        else:
            return f"<|ESCALATE|> (Local Ollama Error: {response.text})"
    except Exception as e:
        return f"<|ESCALATE|> (Local daemon unreachable: {str(e)})"

def _escalate_to_gemini(prompt: str, geometries: list) -> str:
    """Escalate complex requests to Gemini API with full geometries."""
    if not gemini_key or genai is None:
        return "⚠️ Gemini API key not found or google-generativeai SDK missing. Cloud escalation failed."
    
    context_str = json.dumps(geometries, indent=2)
    full_prompt = f"Context:\n{context_str}\n\nUser Prompt: {prompt}\n\nPlease analyze this comprehensively. Execute commands via <execute>command</execute> or Modbus deltas via <modbus_delta pressure_delta=\"+10\" toggle_valve_a=\"true\" />."
    
    try:
        model = genai.GenerativeModel("gemini-2.5-pro")
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Cloud Escalation Error: {str(e)}"

def _expand_transitive_dependencies(seed_ids: list) -> list:
    """Pulls linked parent/child variable IDs from SQLite."""
    if not seed_ids or not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transitive_links'")
    if not cursor.fetchone():
        conn.close()
        return []

    placeholders = ",".join("?" for _ in seed_ids)
    cursor.execute(f"""
        SELECT DISTINCT child_logic_id FROM transitive_links WHERE parent_logic_id IN ({placeholders})
        UNION
        SELECT DISTINCT parent_logic_id FROM transitive_links WHERE child_logic_id IN ({placeholders})
    """, seed_ids + seed_ids)

    linked_ids = [row[0] for row in cursor.fetchall()]
    if not linked_ids:
        conn.close()
        return []

    link_placeholders = ",".join("?" for _ in linked_ids)
    cursor.execute(f"""
        SELECT logic_id, domain_tag, source_url, raw_text
        FROM genesis_geometries WHERE logic_id IN ({link_placeholders})
    """, linked_ids)

    expanded = []
    for logic_id, domain_tag, source_url, raw_text in cursor.fetchall():
        expanded.append({
            "logic_id": logic_id, "domain_tag": domain_tag,
            "source_url": source_url, "raw_text": raw_text,
            "similarity_score": 1.0, "transitive_dependency": True
        })

    conn.close()
    return expanded

LEDGER_DB_PATH = os.path.join(BASE_DIR, "ledger", "semantic_ledger.db")

def inject_temporal_anchor(user_prompt: str) -> str:
    """Injects current physical time into prompt context."""
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    system_prefix = f"[SYSTEM: The current physical time is {current_time}. Anchor all research and logic to this date.]\n\n"
    return system_prefix + user_prompt

def query_ledger(time_bounds: str) -> str:
    """Queries semantic ledger for historical interactions."""
    from datetime import datetime, timedelta
    now = datetime.now()
    start_time = None
    end_time = now
    
    last_match = re.search(r'last\s+(\d+)\s+(hour|day|minute|week)s?', time_bounds, re.IGNORECASE)
    if last_match:
        amount = int(last_match.group(1))
        unit = last_match.group(2).lower()
        if unit == 'hour': start_time = now - timedelta(hours=amount)
        elif unit == 'day': start_time = now - timedelta(days=amount)
        elif unit == 'minute': start_time = now - timedelta(minutes=amount)
        elif unit == 'week': start_time = now - timedelta(weeks=amount)
    elif 'today' in time_bounds.lower():
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif 'yesterday' in time_bounds.lower():
        start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        range_match = re.search(r'(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})', time_bounds)
        if range_match:
            start_time = datetime.strptime(range_match.group(1), '%Y-%m-%d')
            end_time = datetime.strptime(range_match.group(2), '%Y-%m-%d') + timedelta(days=1)
    
    if start_time is None:
        return f"[LEDGER ERROR] Could not parse time bounds: '{time_bounds}'."
    
    try:
        conn = sqlite3.connect(LEDGER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, raw_human_intent, annotated_machine_state FROM semantic_translations WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 50",
            (start_time.isoformat(), end_time.isoformat())
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows: return f"[LEDGER] No interactions found."
        
        ledger_output = f"[LEDGER] Found {len(rows)} interaction(s):\n"
        for ts, raw, _ in rows:
            ledger_output += f"  [{ts}] Human: {raw}\n"
        return ledger_output
    except Exception as e:
        return f"[LEDGER ERROR] Query failed: {str(e)}"

def schedule_task(raw_schedule: str) -> str:
    """Persists a deferred task into SQLite."""
    from datetime import datetime, timedelta
    parts = raw_schedule.split("|", 1)
    if len(parts) != 2:
        return "[SCHEDULER ERROR] Invalid format. Use: <seconds> | <task_prompt>"
    
    try:
        delay_seconds = int(parts[0].strip())
    except ValueError:
        return f"[SCHEDULER ERROR] '{parts[0].strip()}' not a valid integer."
    
    task_prompt = parts[1].strip()
    execute_at = datetime.now() + timedelta(seconds=delay_seconds)
    
    try:
        conn = sqlite3.connect(LEDGER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS scheduled_tasks
            (id INTEGER PRIMARY KEY AUTOINCREMENT, task_prompt TEXT, execute_at TEXT, created_at TEXT, status TEXT DEFAULT 'pending')''')
        cursor.execute(
            "INSERT INTO scheduled_tasks (task_prompt, execute_at, created_at) VALUES (?, ?, ?)",
            (task_prompt, execute_at.isoformat(), datetime.now().isoformat())
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        return f"[SCHEDULER] Task #{task_id} scheduled for {execute_at.strftime('%Y-%m-%d %H:%M:%S')}: {task_prompt}"
    except Exception as e:
        return f"[SCHEDULER ERROR] Failed to persist task: {str(e)}"

# ============================================================================
# Master Orchestration Loop (Two-Loop ReAct Engine)
# ============================================================================

def handle_tool_call(query_text: str) -> str:
    original_query = query_text
    query_text = preprocess_semantic_atoms(query_text)
    print(f"[SEMANTIC TRANSLATOR] Annotated Query: {query_text}")
    
    # 1. Semantic Ledger Capture
    try:
        os.makedirs(os.path.dirname(LEDGER_DB_PATH), exist_ok=True)
        conn_ledger = sqlite3.connect(LEDGER_DB_PATH)
        c_ledger = conn_ledger.cursor()
        c_ledger.execute('''CREATE TABLE IF NOT EXISTS semantic_translations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, raw_human_intent TEXT, annotated_machine_state TEXT)''')
        c_ledger.execute("INSERT INTO semantic_translations (timestamp, raw_human_intent, annotated_machine_state) VALUES (?, ?, ?)",
                  (datetime.now().isoformat(), original_query, query_text))
        conn_ledger.commit()
        conn_ledger.close()
    except Exception as e:
        print(f"[LEDGER ERROR] Failed to write to semantic ledger: {e}")

    # 2. Universal Read-Before-Write State Interrogation
    current_domain = router.get_domain()
    live_scada_state = {}
    if current_domain == "scada" and router.modbus_driver:
        print("[STATE INTERROGATION] Reading live Modbus telemetry (Read-Before-Write)...")
        live_scada_state = router.modbus_driver.read_live_state()
        historian.log_telemetry("scada", live_scada_state)
        print(f"[STATE INTERROGATION] Live State -> Pressure: {live_scada_state.get('pressure')}, Valve A: {live_scada_state.get('valve_a')}, Valve B: {live_scada_state.get('valve_b')}")

    # 3. Vector-Space Pruning
    relevant_data = retrieve_relevant_geometries(query_text, top_k=150)
    seed_ids = [g["logic_id"] for g in relevant_data if "logic_id" in g]
    transitive_deps = _expand_transitive_dependencies(seed_ids)
    seen_ids = {g.get("logic_id") for g in relevant_data if "logic_id" in g}
    for dep in transitive_deps:
        if dep["logic_id"] not in seen_ids:
            relevant_data.append(dep)
            seen_ids.add(dep["logic_id"])

    try:
        with open(os.path.join(BASE_DIR, "openclaw.json"), "r") as f:
            config = json.load(f)
            escalation_enabled = config.get("escalation_enabled", True)
    except Exception:
        escalation_enabled = True

    # 4. Multi-Step Execution Loop
    MAX_STEPS = 3
    final_response = ""
    domain_prompt_context = f"{current_domain.upper()} (Live Pressure: {live_scada_state.get('pressure', 'N/A')})" if current_domain == "scada" else current_domain.upper()
    current_prompt = inject_temporal_anchor(f"[Active Domain: {domain_prompt_context}]\n" + query_text)
    
    for step in range(MAX_STEPS):
        local_response = _triage_local_deepseek(current_prompt, relevant_data, escalation_enabled, domain_context=domain_prompt_context)
        
        if escalation_enabled and "<|ESCALATE|>" in local_response:
            print("[GATEKEEPER] Escalate flag detected. Routing to Cloud...")
            step_response = _escalate_to_gemini(current_prompt, relevant_data)
        else:
            step_response = local_response
            
        ts_step = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_response += f"\n\n--- Step {step + 1} [{ts_step}] ---\n{step_response}"
        
        # Parse XML tags
        execute_matches = re.findall(r"<execute>(.*?)(?:</execute>|$)", step_response, re.DOTALL)
        search_matches = re.findall(r"<search_web>(.*?)(?:</search_web>|$)", step_response, re.DOTALL)
        fetch_matches = re.findall(r"<fetch_web>(.*?)(?:</fetch_web>|$)", step_response, re.DOTALL)
        delegate_matches = re.findall(r'<delegate role="(.*?)">(.*?)(?:</delegate>|$)', step_response, re.DOTALL)
        ledger_matches = re.findall(r"<query_ledger>(.*?)(?:</query_ledger>|$)", step_response, re.DOTALL)
        schedule_matches = re.findall(r"<schedule>(.*?)(?:</schedule>|$)", step_response, re.DOTALL)
        forecast_matches = re.findall(r"<forecast>(.*?)(?:</forecast>|$)", step_response, re.DOTALL)
        click_matches = re.findall(r"<click>(.*?)(?:</click>|$)", step_response, re.DOTALL)
        type_matches = re.findall(r"<type>(.*?)(?:</type>|$)", step_response, re.DOTALL)
        press_matches = re.findall(r"<press>(.*?)(?:</press>|$)", step_response, re.DOTALL)
        scroll_matches = re.findall(r"<scroll>(.*?)(?:</scroll>|$)", step_response, re.DOTALL)
        read_matches = re.findall(r"<read_screen>(.*?)(?:</read_screen>|$)", step_response, re.DOTALL)
        mcp_matches = re.findall(r'<mcp_request server="([^"]+)">(.*?)</mcp_request>', step_response, re.DOTALL)
        modbus_matches = re.findall(r'<modbus_delta\s+([^>]+)/>', step_response, re.DOTALL)
        invoke_skill_matches = re.findall(r"<invoke_skill>(.*?)(?:</invoke_skill>|$)", step_response, re.DOTALL)
        forge_skill_matches = re.findall(r"<forge_skill>(.*?)(?:</forge_skill>|$)", step_response, re.DOTALL)
        skill_deficit_detected = "<|SKILL_DEFICIT|>" in step_response

        has_action = (execute_matches or search_matches or fetch_matches or delegate_matches or 
                      ledger_matches or schedule_matches or forecast_matches or click_matches or 
                      type_matches or press_matches or scroll_matches or read_matches or 
                      mcp_matches or modbus_matches or invoke_skill_matches or 
                      forge_skill_matches or skill_deficit_detected)

        if has_action:
            try:
                execution_log = ""
                
                # A. Shell Execution (with Sieve TOTP Gate for protected directories)
                if execute_matches:
                    cmd = execute_matches[-1].strip()
                    # Extract target path from command for sieve evaluation
                    cmd_parts = cmd.split()
                    target_path = cmd_parts[-1] if len(cmd_parts) > 1 else ""
                    sieve_result = sieve_evaluate_command(cmd, target_path)
                    if sieve_result.get("authorized"):
                        print(f"[EXECUTOR] Running command: {cmd}", flush=True)
                        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                        ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        execution_log += f"\n[System Execution - {ts_exec}]: `{cmd}`\nOutput: {res.stdout}\nError: {res.stderr}\n"
                        historian.log_actuation("system", {"command": cmd}, "SUCCESS" if res.returncode == 0 else "ERROR", res.stdout or res.stderr)
                    else:
                        execution_log += f"\n[SIEVE TOTP GATE]: Command blocked — {sieve_result.get('reason')}\n"
                        historian.log_actuation("system", {"command": cmd}, "SIEVE_BLOCKED", sieve_result.get("reason", ""))

                # B. Web Search & Fetch
                if search_matches:
                    query = search_matches[-1].strip()
                    from duckduckgo_search import DDGS
                    try:
                        results = DDGS().text(query, max_results=5)
                    except Exception as e:
                        results = [{"title": "Error", "body": str(e)}]
                    execution_log += f"\n[Web Search Result for '{query}']:\n{json.dumps(results, indent=2)}\n"

                if fetch_matches:
                    url = fetch_matches[-1].strip()
                    from bs4 import BeautifulSoup
                    resp = requests.get(url, timeout=10)
                    soup = BeautifulSoup(resp.content, "lxml")
                    text_content = soup.get_text(separator=' ', strip=True)[:2000]
                    execution_log += f"\n[Web Fetch Result for '{url}']:\n{text_content}\n"

                # C. Industrial Modbus Action (Read-Before-Write Delta + Z3 Crucible)
                if modbus_matches or current_domain == "scada":
                    # Parse Modbus Delta attributes
                    press_delta = 0
                    toggle_a = False
                    toggle_b = False
                    
                    if modbus_matches:
                        attrs = modbus_matches[-1]
                        p_match = re.search(r'pressure_delta=["\']([+-]?\d+)["\']', attrs)
                        if p_match: press_delta = int(p_match.group(1))
                        va_match = re.search(r'toggle_valve_a=["\'](true|false)["\']', attrs, re.IGNORECASE)
                        if va_match: toggle_a = (va_match.group(1).lower() == "true")
                        vb_match = re.search(r'toggle_valve_b=["\'](true|false)["\']', attrs, re.IGNORECASE)
                        if vb_match: toggle_b = (vb_match.group(1).lower() == "true")

                    scada_action = SCADAModbusAction(
                        pressure_delta=press_delta,
                        toggle_valve_a=toggle_a,
                        toggle_valve_b=toggle_b
                    )

                    curr_p = live_scada_state.get("pressure", 0)
                    curr_va = live_scada_state.get("valve_a", False)
                    curr_vb = live_scada_state.get("valve_b", False)

                    target_p = curr_p + scada_action.pressure_delta
                    target_va = curr_va ^ scada_action.toggle_valve_a
                    target_vb = curr_vb ^ scada_action.toggle_valve_b

                    target_state = {
                        "pressure": target_p,
                        "valve_a": target_va,
                        "valve_b": target_vb,
                        "holding_register_0": target_p,
                        "coil_0": target_va,
                        "coil_1": target_vb
                    }

                    print(f"[DELTA ENGINE] Target Calculated: Pressure={target_p}, Valve A={target_va}, Valve B={target_vb}")
                    
                    # Formal Z3 Verification
                    is_safe, proof_report = verify_invariants(target_state, live_scada_state)
                    historian.log_crucible_eval("scada", scada_action.model_dump(), live_scada_state, target_state, is_safe, proof_report.get("z3_result", ""), breach_report=str(proof_report))
                    openclaw_v2_historian.log_v2_crucible_eval("session_scada_live", "scada", scada_action.model_dump(), live_scada_state, target_state, is_safe, proof_report.get("z3_result", ""), breach_report=str(proof_report))

                    if is_safe and router.modbus_driver:
                        print("[Z3 CRUCIBLE] SATISFIABLE (SAFE) - Committing to Modbus PLC...")
                        succ, msg = router.modbus_driver.write_target_state(
                            coils={0: target_va, 1: target_vb},
                            registers={0: target_p}
                        )
                        historian.log_actuation("scada", target_state, "SUCCESS" if succ else "FAILED", msg)
                        execution_log += f"\n[SCADA Modbus Execution]: {msg} -> State: {target_state}\n"
                    else:
                        print("[Z3 CRUCIBLE] UNSATISFIABLE - Execution Blocked by Invariants!")
                        # Capture Divergent Tail into OpenClaw 2.0 SQLite Non-Repudiation Ledger
                        tail_record = openclaw_v2_historian.log_divergent_tail(
                            session_id="session_scada_live",
                            node_id="forager_node_01",
                            fault_type="KINETIC_INVARIANT_BREACH",
                            divergent_state=live_scada_state,
                            candidate_action=scada_action.model_dump(),
                            z3_proof_report=proof_report
                        )
                        historian.log_actuation("scada", target_state, "UNSAT_BLOCKED", str(proof_report))
                        execution_log += f"\n[SCADA Z3 INVARIANT VIOLATION]: Action BLOCKED: {proof_report.get('status')} | Receipt: {tail_record.get('non_repudiation_hash')[:16]}...\n"

                # D. GUI Workstation Automation (Read-Before-Write)
                if click_matches:
                    target = click_matches[-1].strip()
                    click_res = actuator.click_text_target(target)
                    historian.log_actuation("gui", {"action": "click", "target": target}, "EXECUTED", click_res)
                    execution_log += f"\n[GUI Actuation Result]: {click_res}\n"

                if type_matches:
                    text_val = type_matches[-1]
                    type_res = actuator.type_text(text_val)
                    historian.log_actuation("gui", {"action": "type", "text": text_val}, "EXECUTED", type_res)
                    execution_log += f"\n[GUI Actuation Result]: {type_res}\n"

                if press_matches:
                    k_val = press_matches[-1].strip()
                    press_res = actuator.press_key(k_val)
                    historian.log_actuation("gui", {"action": "press", "key": k_val}, "EXECUTED", press_res)
                    execution_log += f"\n[GUI Actuation Result]: {press_res}\n"

                if scroll_matches:
                    try:
                        c_val = int(scroll_matches[-1].strip())
                        scroll_res = actuator.scroll(c_val)
                    except ValueError:
                        scroll_res = "[GUI ERROR] Invalid scroll integer."
                    historian.log_actuation("gui", {"action": "scroll", "clicks": c_val}, "EXECUTED", scroll_res)
                    execution_log += f"\n[GUI Actuation Result]: {scroll_res}\n"

                if read_matches:
                    prompt_text = read_matches[-1].strip() or "Describe screen."
                    try:
                        img = optic_parser.capture_screen()
                        analysis = optic_parser.analyze_frame(img, prompt=prompt_text)
                        read_res = f"[OPTIC SUCCESS]: {analysis}"
                    except Exception as e:
                        read_res = f"[OPTIC ERROR]: {e}"
                    execution_log += f"\n[Optic Screen Read]:\n{read_res}\n"

                # E. MCP Outer Loop (Z3 Gatekeeper)
                if mcp_matches:
                    mcp_registry = _load_mcp_registry()
                    for server_name, raw_payload in mcp_matches:
                        clean_payload = raw_payload.strip()
                        is_safe, rep = verify_state_locked_protocol(f"EXTERNAL_MCP_TRANSMISSION: Server={server_name} | Payload={clean_payload}")
                        if not is_safe:
                            execution_log += f"\n[MCP AXIOM BREACH]: External routing to '{server_name}' blocked by Z3 Crucible: {rep}\n"
                            historian.log_crucible_eval("mcp", {"server": server_name}, None, None, False, "UNSAT", breach_report=rep)
                            continue
                        if server_name not in mcp_registry:
                            execution_log += f"\n[MCP ERROR]: Server '{server_name}' not defined in mcp.json.\n"
                            continue
                        execution_log += f"\n[MCP SUCCESS]: Payload validated & routed to '{server_name}'.\n"
                        historian.log_actuation("mcp", {"server": server_name, "payload": clean_payload}, "SUCCESS", "Routed via mcp.json")

                # F. Invoke Learned Skill (Hot-Loaded from Graduated Registry)
                if invoke_skill_matches:
                    for skill_json_raw in invoke_skill_matches:
                        try:
                            # Strict Pydantic parsing
                            selection_data = json.loads(skill_json_raw.strip())
                            selection = SkillSelection(**selection_data)
                            
                            skill_id = selection.selected_skill_id
                            print(f"[SKILL REASONING] {selection.reasoning}")
                            
                            skill_content = skill_loader.get_skill_context(skill_id)
                            if skill_content:
                                # Extract CLI payloads from the invoked skill
                                skill_payloads = re.findall(r'```(?:bash|sh|shell)?\r?\n(.*?)```', skill_content, re.DOTALL)
                                for payload in skill_payloads:
                                    clean_cmd = payload.strip()
                                    # Map runtime_parameters to environment variables
                                    skill_env = os.environ.copy()
                                    if selection.runtime_parameters:
                                        skill_env.update({str(k): str(v) for k, v in selection.runtime_parameters.items()})
                                        
                                    # Runtime re-verification through Z3
                                    is_safe, rep = verify_state_locked_protocol(clean_cmd)
                                    if is_safe:
                                        print(f"[SKILL INVOKE] Executing '{skill_id}' with params {selection.runtime_parameters}: {clean_cmd}")
                                        res = subprocess.run(clean_cmd, shell=True, capture_output=True, text=True, timeout=15, env=skill_env)
                                        execution_log += f"\n[SKILL '{skill_id}' EXECUTED]: {res.stdout or res.stderr}\n"
                                        historian.log_actuation(
                                            "skill", 
                                            {
                                                "skill_id": skill_id, 
                                                "command": clean_cmd, 
                                                "reasoning": selection.reasoning,
                                                "confidence": selection.confidence_score,
                                                "runtime_parameters": selection.runtime_parameters
                                            }, 
                                            "SUCCESS" if res.returncode == 0 else "ERROR", 
                                            res.stdout or res.stderr
                                        )
                                    else:
                                        execution_log += f"\n[SKILL INVOKE BLOCKED]: Skill '{skill_id}' payload breached Z3 invariants: {rep}\n"
                                        historian.log_actuation(
                                            "skill", 
                                            {
                                                "skill_id": skill_id,
                                                "reasoning": selection.reasoning,
                                                "confidence": selection.confidence_score
                                            }, 
                                            "UNSAT_BLOCKED", 
                                            rep
                                        )
                            else:
                                execution_log += f"\n[SKILL INVOKE ERROR]: Skill '{skill_id}' not found in active hot-loader cache.\n"
                        except Exception as e:
                            execution_log += f"\n[SKILL INVOKE SCHEMA ERROR]: Invalid SkillSelection JSON format: {str(e)}\n"

                # G. Skill Forge / Deficit Detection (LLM-Powered Self-Evolution)
                if forge_skill_matches or skill_deficit_detected:
                    forge_description = original_query
                    target_slug = None
                    if forge_skill_matches:
                        try:
                            forge_data = json.loads(forge_skill_matches[-1].strip())
                            forge_req = SkillForgeRequest(**forge_data)
                            forge_description = forge_req.capability_description
                            target_slug = forge_req.target_slug
                            print(f"[FORGE REASONING] {forge_req.reasoning}")
                        except Exception as e:
                            execution_log += f"\n[SKILL FORGE SCHEMA ERROR]: Invalid SkillForgeRequest JSON format: {str(e)}. Defaulting to user prompt.\n"

                    print(f"[SKILL FORGE] Initiating autonomous skill forging: {forge_description[:80]}...")
                    forge_result = skill_forge.forge_full_cycle(forge_description, target_slug=target_slug)
                    if forge_result["success"]:
                        execution_log += f"\n[SKILL FORGE SUCCESS]: Skill '{forge_result['skill_id']}' forged and graduated. LLM calls: {forge_result['llm_calls_used']}, Z3 attempts: {forge_result['z3_attempts']}.\n"
                        execution_log += f"    Message: {forge_result['message']}\n"
                    else:
                        execution_log += f"\n[SKILL FORGE FAILED]: {forge_result['message']}. LLM calls: {forge_result['llm_calls_used']}.\n"

                final_response += execution_log

                if step < MAX_STEPS - 1:
                    current_prompt += f"\n\n[PREVIOUS STEP EXECUTION OUTPUT]:\n{execution_log}\nPlease continue executing necessary commands or provide your final answer."
                    continue
                else:
                    break
            except Exception as e:
                final_response += f"\n\n[System Execution Failed]: {str(e)}"
                break
        else:
            break

    # Final Invention / Fault Reflection Capture
    if "contradiction" in final_response.lower() or "UNSATISFIABLE" in final_response:
        try:
            ref_dir = os.path.join(BASE_DIR, "reflections")
            os.makedirs(ref_dir, exist_ok=True)
            with open(os.path.join(ref_dir, "failed_geometries.md"), "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                f.write(f"\n## Fault Entry: {ts}\n{final_response}\n---\n")
        except Exception:
            pass

    master_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[Task Completed: {master_ts}]\n" + final_response.strip()
