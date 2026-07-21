import sys
import os
import subprocess
import sqlite3
import json
import requests
import google.generativeai as genai
from dotenv import load_dotenv

# Load local environment variables securely
load_dotenv(os.path.join(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace", ".env"))

# Setup Gemini SDK
gemini_key = os.environ.get("GEMINI_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)

# Append the scratch directory to sys.path so we can import query_matrix
sys.path.append(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\17 Pillars\scratch")

from query_matrix import retrieve_relevant_geometries

DB_PATH = os.path.join(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace", "diana_matrix.db")

from skills.diana_core.actuation.gui_driver import VisualActuator
actuator = VisualActuator()

# Read model_tag from config
try:
    with open(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\openclaw.json", "r") as f:
        config = json.load(f)
        LOCAL_MODEL_TAG = config.get("model_tag", "deepseek-r1:14b")
except Exception:
    LOCAL_MODEL_TAG = "deepseek-r1:14b"

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

# Pre-compile the regex by ordering keys by length descending to match longest phrases first
_sorted_keys = sorted(ROSETTA_DICTIONARY.keys(), key=len, reverse=True)
_rosetta_pattern = re.compile(r'\b(' + '|'.join(map(re.escape, _sorted_keys)) + r')\b', re.IGNORECASE)

def preprocess_semantic_atoms(query_text: str) -> str:
    """
    Translates fluid human words into explicit deterministic tags using Option B (Annotation).
    Example: 'Send' -> 'Send [TRANSFER_ASSET]'
    """
    def annotator(match):
        original_word = match.group(0)
        atom = ROSETTA_DICTIONARY[original_word.lower()]
        return f"{original_word} [{atom}]"
        
    return _rosetta_pattern.sub(annotator, query_text)

def _triage_local_deepseek(prompt: str, geometries: list, escalation_enabled: bool = True) -> str:
    """Triage request locally using top 5 geometries."""
    context_data = geometries[:5]
    context_str = json.dumps(context_data, indent=2)
    
    try:
        with open(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\openclaw.json", "r") as f:
            config = json.load(f)
            primary_prompt = config.get("primary_system_prompt", "")
            socratic_prompt = config.get("socratic_mediator_prompt", "")
    except Exception:
        primary_prompt = ""
        socratic_prompt = ""

    system_prompt = primary_prompt
    
    if escalation_enabled:
        system_prompt += "\n\n[CLOUD ROUTING GATEKEEPER]: If the user asks for a 'geometric proof', 'logic proof', 'mathematical model', requires internet access, or asks a highly complex question, you MUST NOT attempt to answer it. You must output exactly '<|ESCALATE|>' and nothing else."
        full_prompt = f"Context (17 Pillars Dataset):\n{context_str}\n\nUser Prompt: {prompt}\n\n[SYSTEM REMINDER]: Evaluate the user prompt. If they ask for a mathematical or geometric proof, or the task is highly complex, you MUST NOT write the answer. You must output EXACTLY '<|ESCALATE|>'."
    else:
        full_prompt = f"Context (17 Pillars Dataset):\n{context_str}\n\nUser Prompt: {prompt}\n\n[CRITICAL SYSTEM REMINDER]: If you need to perform local actions, YOU MUST THINK IN STEPS. Use <execute>command</execute>, <search_web>query</search_web>, <fetch_web>url</fetch_web>, <delegate role=\"role\">task</delegate>, <query_ledger>time bounds</query_ledger> to recall past interactions, <schedule>seconds | task prompt</schedule> to defer a task into the future, <forecast>target | days</forecast> to run a quantitative time-series forecast on a ticker or dataset, or <click>target_text</click> to autonomously find text on the screen using native OCR and physically click it with the mouse. IMPORTANT: When outputting forecast data from yfinance, you MUST synthesize the numbers as a mathematical baseline trendline based purely on historical momentum, and EXPLICITLY state that quantitative smoothing algorithms cannot account for market volatility or external catalyst events. Only when you have finished all steps should you output your final 'resin_dsl_payload' JSON geometry."
        
    try:
        response = requests.post("http://127.0.0.1:11434/api/generate", json={
            "model": LOCAL_MODEL_TAG,
            "system": system_prompt,
            "prompt": full_prompt,
            "stream": False
        }, timeout=120)
        if response.status_code == 200:
            raw_response = response.json().get("response", "")
            # DeepSeek-R1 CoT filter: prevent false positive routing triggers
            if "</think>" in raw_response:
                return raw_response.split("</think>")[-1].strip()
            return raw_response.strip()
        else:
            return f"<|ESCALATE|> (Local Ollama Error: {response.text})"
    except Exception as e:
        return f"<|ESCALATE|> (Local daemon unreachable: {str(e)})"

def _escalate_to_gemini(prompt: str, geometries: list) -> str:
    """Escalate complex requests to Gemini API with full 150 geometries."""
    if not gemini_key:
        return "⚠️ Gemini API key not found in environment (GEMINI_API_KEY). Cloud escalation failed."
    
    context_str = json.dumps(geometries, indent=2)
    full_prompt = f"Context:\n{context_str}\n\nUser Prompt: {prompt}\n\nPlease analyze this comprehensively. If the user is asking to perform a system action (like opening a website or running a script), you can execute Windows commands on their host machine by outputting exactly <execute>command here</execute>."
    
    try:
        # User API key does not have billing enabled for 3.1 preview (limit: 0)
        model = genai.GenerativeModel("gemini-2.5-pro")
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Cloud Escalation Error: {str(e)}"

def _expand_transitive_dependencies(seed_ids: list) -> list:
    """
    Executes a secondary SQLite query to pull any parent/child variable IDs
    transitively linked to the initial Top 150 seed set.
    Prevents orphaned variable dependencies from being silently dropped
    during CNF translation in the PySAT compiler.
    """
    if not seed_ids or not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if the transitive_links table exists; if not, return empty
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='transitive_links'
    """)
    if not cursor.fetchone():
        conn.close()
        return []

    placeholders = ",".join("?" for _ in seed_ids)
    cursor.execute(f"""
        SELECT DISTINCT child_logic_id FROM transitive_links
        WHERE parent_logic_id IN ({placeholders})
        UNION
        SELECT DISTINCT parent_logic_id FROM transitive_links
        WHERE child_logic_id IN ({placeholders})
    """, seed_ids + seed_ids)

    linked_ids = [row[0] for row in cursor.fetchall()]

    if not linked_ids:
        conn.close()
        return []

    # Fetch the full geometry rows for the linked IDs
    link_placeholders = ",".join("?" for _ in linked_ids)
    cursor.execute(f"""
        SELECT logic_id, domain_tag, source_url, raw_text
        FROM genesis_geometries
        WHERE logic_id IN ({link_placeholders})
    """, linked_ids)

    expanded = []
    for logic_id, domain_tag, source_url, raw_text in cursor.fetchall():
        expanded.append({
            "logic_id": logic_id,
            "domain_tag": domain_tag,
            "source_url": source_url,
            "raw_text": raw_text,
            "similarity_score": 1.0,  # Transitive link: max relevance
            "transitive_dependency": True
        })

    conn.close()
    return expanded

LEDGER_DB_PATH = os.path.join(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Reflections", "semantic_ledger.db")

def inject_temporal_anchor(user_prompt: str) -> str:
    """Injects the host OS clock into the neural shell context."""
    from datetime import datetime
    current_time = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    
    system_prefix = f"[SYSTEM: The current physical time is {current_time}. You must anchor all research and logic to this exact date.]\n\n"
    
    return system_prefix + user_prompt

def query_ledger(time_bounds: str) -> str:
    """
    Queries D.I.A.N.A.'s semantic ledger for historical interactions within a time window.
    
    Accepts natural-language-style time bounds that are parsed into SQL constraints:
      - "last 24 hours", "last 7 days", "last 1 hour"
      - "2026-07-20 to 2026-07-21" (explicit date range)
      - "today", "yesterday"
    """
    from datetime import datetime, timedelta
    import re as _re
    
    now = datetime.now()
    start_time = None
    end_time = now
    
    # Parse "last N hours/days/minutes"
    last_match = _re.search(r'last\s+(\d+)\s+(hour|day|minute|week)s?', time_bounds, _re.IGNORECASE)
    if last_match:
        amount = int(last_match.group(1))
        unit = last_match.group(2).lower()
        if unit == 'hour':
            start_time = now - timedelta(hours=amount)
        elif unit == 'day':
            start_time = now - timedelta(days=amount)
        elif unit == 'minute':
            start_time = now - timedelta(minutes=amount)
        elif unit == 'week':
            start_time = now - timedelta(weeks=amount)
    
    # Parse "today" / "yesterday"
    elif 'today' in time_bounds.lower():
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif 'yesterday' in time_bounds.lower():
        start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Parse explicit date range "YYYY-MM-DD to YYYY-MM-DD"
    else:
        range_match = _re.search(r'(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})', time_bounds)
        if range_match:
            start_time = datetime.strptime(range_match.group(1), '%Y-%m-%d')
            end_time = datetime.strptime(range_match.group(2), '%Y-%m-%d') + timedelta(days=1)
    
    if start_time is None:
        return f"[LEDGER ERROR] Could not parse time bounds: '{time_bounds}'. Use 'last N hours/days', 'today', 'yesterday', or 'YYYY-MM-DD to YYYY-MM-DD'."
    
    try:
        conn = sqlite3.connect(LEDGER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, raw_human_intent, annotated_machine_state FROM semantic_translations WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 50",
            (start_time.isoformat(), end_time.isoformat())
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return f"[LEDGER] No interactions found between {start_time.isoformat()} and {end_time.isoformat()}."
        
        ledger_output = f"[LEDGER] Found {len(rows)} interaction(s) between {start_time.strftime('%Y-%m-%d %H:%M')} and {end_time.strftime('%Y-%m-%d %H:%M')}:\n\n"
        for ts, raw, annotated in rows:
            ledger_output += f"  [{ts}] Human: {raw}\n"
        
        return ledger_output
    except Exception as e:
        return f"[LEDGER ERROR] Query failed: {str(e)}"

def schedule_task(raw_schedule: str) -> str:
    """
    Persists a deferred task into SQLite for autonomous execution by the heartbeat loop.
    
    Format: "<delay_in_seconds> | <task_prompt>"
    Example: "10800 | Check the server logs and report status"
    """
    from datetime import datetime, timedelta
    
    parts = raw_schedule.split("|", 1)
    if len(parts) != 2:
        return "[SCHEDULER ERROR] Invalid format. Use: <seconds> | <task_prompt>"
    
    try:
        delay_seconds = int(parts[0].strip())
    except ValueError:
        return f"[SCHEDULER ERROR] '{parts[0].strip()}' is not a valid integer for delay seconds."
    
    task_prompt = parts[1].strip()
    if not task_prompt:
        return "[SCHEDULER ERROR] Task prompt cannot be empty."
    
    execute_at = datetime.now() + timedelta(seconds=delay_seconds)
    
    try:
        conn = sqlite3.connect(LEDGER_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''CREATE TABLE IF NOT EXISTS scheduled_tasks
               (id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_prompt TEXT NOT NULL,
                execute_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','failed')))'''
        )
        cursor.execute(
            "INSERT INTO scheduled_tasks (task_prompt, execute_at, created_at) VALUES (?, ?, ?)",
            (task_prompt, execute_at.isoformat(), datetime.now().isoformat())
        )
        conn.commit()
        task_id = cursor.lastrowid
        conn.close()
        
        hours, remainder = divmod(delay_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        human_delay = f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"
        
        return f"[SCHEDULER] Task #{task_id} persisted. Will execute at {execute_at.strftime('%Y-%m-%d %H:%M:%S')} (in {human_delay}).\nPrompt: {task_prompt}"
    except Exception as e:
        return f"[SCHEDULER ERROR] Failed to persist task: {str(e)}"

def handle_tool_call(query_text):
    original_query = query_text
    # Option B Annotator: Ground human language into deterministic machine state
    query_text = preprocess_semantic_atoms(query_text)
    print(f"[SEMANTIC TRANSLATOR] Annotated Query: {query_text}")
    
    # --- Semantic Ledger Capture ---
    try:
        from datetime import datetime
        ledger_path = os.path.join(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Reflections", "semantic_ledger.db")
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        conn_ledger = sqlite3.connect(ledger_path)
        c_ledger = conn_ledger.cursor()
        c_ledger.execute('''CREATE TABLE IF NOT EXISTS semantic_translations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      timestamp TEXT,
                      raw_human_intent TEXT,
                      annotated_machine_state TEXT)''')
        c_ledger.execute("INSERT INTO semantic_translations (timestamp, raw_human_intent, annotated_machine_state) VALUES (?, ?, ?)",
                  (datetime.now().isoformat(), original_query, query_text))
        conn_ledger.commit()
        conn_ledger.close()
    except Exception as e:
        print(f"[LEDGER ERROR] Failed to write to semantic ledger: {e}")
    # -------------------------------
    # Vector-Space Pruning Sieve: fetches top 150 contextually relevant geometries
    relevant_data = retrieve_relevant_geometries(query_text, top_k=150)

    # Transitive Dependency Expansion: pull linked parent/child variables
    seed_ids = [g["logic_id"] for g in relevant_data if "logic_id" in g]
    transitive_deps = _expand_transitive_dependencies(seed_ids)

    # Deduplicate by logic_id before passing to compiler
    seen_ids = {g.get("logic_id") for g in relevant_data if "logic_id" in g}
    for dep in transitive_deps:
        if dep["logic_id"] not in seen_ids:
            relevant_data.append(dep)
            seen_ids.add(dep["logic_id"])

    try:
        with open(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\openclaw.json", "r") as f:
            config = json.load(f)
            escalation_enabled = config.get("escalation_enabled", True)
    except Exception:
        escalation_enabled = True

    # Multi-Step Execution Loop
    MAX_STEPS = 3
    final_response = ""
    current_prompt = inject_temporal_anchor(query_text)
    
    for step in range(MAX_STEPS):
        local_response = _triage_local_deepseek(current_prompt, relevant_data, escalation_enabled)
        
        if escalation_enabled and "<|ESCALATE|>" in local_response:
            print("[GATEKEEPER] Escalate flag detected. Routing to Gemini (Cloud)...")
            step_response = _escalate_to_gemini(current_prompt, relevant_data)
        else:
            print("[GATEKEEPER] Request handled locally by DeepSeek-R1-Distill-14B.")
            step_response = local_response
            
        ts_step = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_response += f"\n\n--- Step {step + 1} [{ts_step}] ---\n{step_response}"
        
        import re
        
        # 1. Check for Shell Execution
        execute_matches = re.findall(r"<execute>(.*?)(?:</execute>|$)", step_response, re.DOTALL)
        
        # 2. Check for Web Search
        search_matches = re.findall(r"<search_web>(.*?)(?:</search_web>|$)", step_response, re.DOTALL)
        
        # 3. Check for Web Fetch
        fetch_matches = re.findall(r"<fetch_web>(.*?)(?:</fetch_web>|$)", step_response, re.DOTALL)
        
        # 4. Check for Subagent Delegation
        delegate_matches = re.findall(r'<delegate role="(.*?)">(.*?)(?:</delegate>|$)', step_response, re.DOTALL)
        
        # 5. Check for Ledger Query (Temporal Memory)
        ledger_matches = re.findall(r"<query_ledger>(.*?)(?:</query_ledger>|$)", step_response, re.DOTALL)
        
        # 6. Check for Schedule (Temporal Future)
        schedule_matches = re.findall(r"<schedule>(.*?)(?:</schedule>|$)", step_response, re.DOTALL)
        
        # 7. Check for Temporal Forecast
        forecast_matches = re.findall(r"<forecast>(.*?)(?:</forecast>|$)", step_response, re.DOTALL)
        
        # 8. Check for GUI Click Automation
        click_matches = re.findall(r"<click>(.*?)(?:</click>|$)", step_response, re.DOTALL)
        
        if execute_matches or search_matches or fetch_matches or delegate_matches or ledger_matches or schedule_matches or forecast_matches or click_matches:
            try:
                execution_log = ""
                
                if execute_matches:
                    cmd = execute_matches[-1].strip()
                    print(f"[EXECUTOR] Running command: {cmd}", flush=True)
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as out_f, \
                         tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as err_f:
                        try:
                            result = subprocess.run(cmd, shell=True, stdout=out_f, stderr=err_f, timeout=10)
                        finally:
                            pass
                    
                    with open(out_f.name, 'r', encoding='utf-8') as f:
                        output = f.read().strip()
                    with open(err_f.name, 'r', encoding='utf-8') as f:
                        err = f.read().strip()
                    try: os.remove(out_f.name); os.remove(err_f.name)
                    except: pass
                    
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[System Execution - {ts_exec}]: `{cmd}`\n"
                    if output:
                        execution_log += f"Output:\n{output}\n"
                    if err:
                        execution_log += f"Error:\n{err}\n"
                    if not output and not err:
                        execution_log += "Status: Success (No output)\n"
                
                if search_matches:
                    query = search_matches[-1].strip()
                    print(f"[EXECUTOR] Searching Web for: {query}", flush=True)
                    from duckduckgo_search import DDGS
                    try:
                        results = DDGS().text(query, max_results=5)
                    except Exception as e:
                        results = [{"title": "Error", "href": "", "body": f"Search failed: {str(e)}"}]
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[Web Search Result for '{query}' - {ts_exec}]:\n"
                    for r in results:
                        execution_log += f"- Title: {r.get('title')}\n  URL: {r.get('href')}\n  Snippet: {r.get('body')}\n\n"
                
                if fetch_matches:
                    url = fetch_matches[-1].strip()
                    print(f"[EXECUTOR] Fetching URL: {url}", flush=True)
                    import requests
                    from bs4 import BeautifulSoup
                    resp = requests.get(url, timeout=10)
                    soup = BeautifulSoup(resp.content, "lxml")
                    text_content = soup.get_text(separator=' ', strip=True)
                    # Limit to ~2000 characters to avoid context overflow
                    text_content = text_content[:2000] + "...(truncated)" if len(text_content) > 2000 else text_content
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[Web Fetch Result for '{url}' - {ts_exec}]:\n{text_content}\n"
                
                if delegate_matches:
                    role, task = delegate_matches[-1]
                    role = role.strip()
                    task = task.strip()
                    print(f"[EXECUTOR] Spawning Subagent ({role})...", flush=True)
                    
                    subagent_prompt = f"You are a specialized subagent. Your role is: {role}.\n\nTASK:\n{task}\n\nPlease complete the task and provide your final response."
                    
                    try:
                        import requests
                        payload = {
                            "model": "deepseek-r1:14b",
                            "prompt": subagent_prompt,
                            "stream": False,
                            "options": {
                                "temperature": 0.2,
                                "num_ctx": 4096
                            }
                        }
                        
                        print(f"[EXECUTOR] Waiting for subagent '{role}' to complete...", flush=True)
                        resp = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=300)
                        subagent_result = resp.json().get("response", "Error: No response from subagent.")
                        
                        # Strip out thought blocks if present (so main agent just gets the output)
                        import re
                        subagent_result = re.sub(r'<think>.*?</think>', '', subagent_result, flags=re.DOTALL).strip()
                        
                        ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        execution_log += f"\n[Subagent '{role}' Response - {ts_exec}]:\n{subagent_result}\n"
                    except Exception as e:
                        execution_log += f"\n[Subagent '{role}' Error]:\n{str(e)}\n"
                
                # 5. Execute Ledger Query
                if ledger_matches:
                    time_bounds = ledger_matches[-1].strip()
                    print(f"[EXECUTOR] Querying Temporal Ledger: {time_bounds}", flush=True)
                    ledger_result = query_ledger(time_bounds)
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[Temporal Ledger Query - {ts_exec}]:\n{ledger_result}\n"
                
                # 6. Execute Schedule
                if schedule_matches:
                    raw_schedule = schedule_matches[-1].strip()
                    print(f"[EXECUTOR] Scheduling Deferred Task: {raw_schedule}", flush=True)
                    schedule_result = schedule_task(raw_schedule)
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[Task Scheduler - {ts_exec}]:\n{schedule_result}\n"
                
                # 7. Execute Temporal Forecast
                if forecast_matches:
                    forecast_arg = forecast_matches[-1].strip()
                    print(f"[EXECUTOR] Running temporal forecast for: {forecast_arg}", flush=True)
                    from skills.diana_core.temporal_forecasting import run_forecast
                    if "|" in forecast_arg:
                        target, days = forecast_arg.split("|")
                        forecast_result = run_forecast(target.strip(), int(days.strip()))
                    else:
                        forecast_result = run_forecast(forecast_arg.strip(), 30)
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[Temporal Forecast Result - {ts_exec}]:\n{forecast_result}\n"
                
                # 8. Execute GUI Automation
                if click_matches:
                    target = click_matches[-1].strip()
                    print(f"[EXECUTOR] Triggering GUI Actuation to click on: '{target}'", flush=True)
                    click_result = actuator.click_text_target(target)
                    ts_exec = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    execution_log += f"\n[GUI Actuation Result - {ts_exec}]:\n{click_result}\n"

                final_response += execution_log
                
                # If there are more steps available, feed the output back for the next iteration
                if step < MAX_STEPS - 1:
                    current_prompt += f"\n\n[PREVIOUS STEP EXECUTION OUTPUT]:\n{execution_log}\nPlease continue executing the necessary commands or provide your final answer."
                    continue
                else:
                    break
            except Exception as e:
                final_response += f"\n\n[System Execution Failed]: {str(e)}"
                break
        else:
            # No command generated, task is likely complete
            break
            
    # Check for Inventions (JSON Schema)
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", final_response, re.DOTALL)
    if not json_match:
        # Fallback raw search for resin_dsl_payload
        json_match = re.search(r"(\{\s*\"resin_dsl_payload\".*?\})", final_response, re.DOTALL)
        
    if json_match:
        try:
            invention_data = json.loads(json_match.group(1))
            inv_dir = r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Inventions"
            os.makedirs(inv_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            inv_path = os.path.join(inv_dir, f"genesis_geometries_{ts}.json")
            with open(inv_path, "w", encoding="utf-8") as f:
                json.dump(invention_data, f, indent=4)
            final_response += f"\n\n[Local Geometry Capture]: Valid schema detected. Invention written to `{inv_path}`."
        except Exception as e:
            pass
            
    # Check for Logic Failures (Fault Loop)
    if "Logical Inconsistency Detected" in final_response or "Syntax Fault" in final_response or "contradiction" in final_response.lower():
        try:
            ref_dir = r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Reflections"
            os.makedirs(ref_dir, exist_ok=True)
            with open(os.path.join(ref_dir, "failed_geometries.md"), "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                f.write(f"\n## Fault Entry: {ts}\n{final_response}\n---\n")
            final_response += f"\n\n[Fault Loop Intercept]: Logic contradiction isolated. Appended trace data to `failed_geometries.md` for negative constraint boundary."
        except Exception:
            pass
            
    master_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[Task Completed: {master_ts}]\n" + final_response.strip()

# This is called by your primary agent loop
