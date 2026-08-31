import json
import re

# Tier gate: Architect default is 100 custom axioms/geometries.
# Hacker build.sh sed-forces this constant to 5 before packaging.
MAX_AXIOMS = 5


def _count_custom_axioms(payload) -> int:
    """Return the custom axiom/geometry list length when that structure is present."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("axioms", "geometries", "custom_axioms", "axiom_list"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return 1
    return 0


def parse_deterministic_dsl(raw_string: str) -> dict:
    """
    Acts as the deterministic intermediate compiler inside the D.I.A.N.A. node.
    Validates the strict DeterministicDSL structure and blocks semantic anomalies and LLM hallucinations.
    """
    # Check if the payload is the new proprietary textual DeterministicDSL syntax
    if "protocol " in raw_string or "transaction " in raw_string:
        # 1. Enforce Industry Standard Terminology
        if 'environment = "Physical_AI_Execution_Runtime"' not in raw_string:
            return {"status": "SYNTAX_FAULT", "error": "Fatal: Missing or invalid environment constraint. Must specify 'Physical_AI_Execution_Runtime'."}
        
        if 'hardware_isolation = "Trusted_Execution_Environment_TEE"' not in raw_string:
            return {"status": "SYNTAX_FAULT", "error": "Fatal: Missing or invalid hardware isolation constraint. Must specify 'Trusted_Execution_Environment_TEE'."}
            
        # 2. Enforce Dual-Possession State-Reconciliation Sieve
        is_dual_possession = "QueenNode" in raw_string and "ForagerNode" in raw_string and "transaction" in raw_string
        
        if is_dual_possession:
            if "sieve AST_State_Reconciliation" not in raw_string:
                return {"status": "SYNTAX_FAULT", "error": "Fatal: Dual-possession transaction detected without the mandatory 'sieve AST_State_Reconciliation' block. Un-sieved physical execution is strictly prohibited."}

        # 3. OpenClaw 2.0 Multiplayer Presence Header Extraction
        presence_matches = re.findall(r"@presence\s*\(\s*node_id\s*=\s*\"([^\"]+)\"\s*,\s*role\s*=\s*\"([^\"]+)\"\s*\)", raw_string)
        collaborators = [
            {"node_id": m[0], "role": m[1]} for m in presence_matches
        ]

        session_match = re.search(r"@session\s*\(\s*id\s*=\s*\"([^\"]+)\"\s*\)", raw_string)
        session_id = session_match.group(1) if session_match else None

        # Count explicit axiom / geometry declarations in textual Resin scripts.
        textual_count = len(re.findall(r"\b(?:axiom|geometry)\s+\w+", raw_string, flags=re.IGNORECASE))
        if textual_count > MAX_AXIOMS:
            return {
                "status": "SYNTAX_FAULT",
                "error": f"Axiom limit exceeded: {textual_count} > MAX_AXIOMS ({MAX_AXIOMS}).",
            }
                
        compiled_payload = {
            "type": "deterministic_dsl_compiled",
            "raw_script": raw_string,
            "openclaw_v2": {
                "session_id": session_id,
                "collaborators": collaborators,
                "multiplayer_active": len(collaborators) > 0
            }
        }
        return {
            "status": "SUCCESS",
            "payload": compiled_payload
        }

    # Fallback to legacy JSON evaluation
    try:
        data = json.loads(raw_string)
    except json.JSONDecodeError as e:
        return {"status": "SYNTAX_FAULT", "error": f"Invalid JSON format. Hallucination detected: {e}"}

    if "deterministic_dsl_payload" not in data:
        return {"status": "SYNTAX_FAULT", "error": "Missing mandatory 'deterministic_dsl_payload' root key."}

    payload = data["deterministic_dsl_payload"]

    if not isinstance(payload, list) and not isinstance(payload, dict):
        return {"status": "SYNTAX_FAULT", "error": "'deterministic_dsl_payload' must contain a structured object or array."}

    axiom_count = _count_custom_axioms(payload)
    if axiom_count > MAX_AXIOMS:
        return {
            "status": "SYNTAX_FAULT",
            "error": f"Axiom limit exceeded: {axiom_count} > MAX_AXIOMS ({MAX_AXIOMS}).",
        }

    return {
        "status": "SUCCESS",
        "payload": payload
    }

if __name__ == "__main__":
    print("[*] Resin Compiler Diagnostics...")
    test_str = '{"deterministic_dsl_payload": {"major_premise": "A", "minor_premise": "B", "abnormality_warrant_requested": true}}'
    print(parse_deterministic_dsl(test_str))
