"""
The Greetme 50 Semantic State-Locks (Logical Lexicon)
Software-enforced Digital Physics for D.I.A.N.A.
"""

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

# The fields in Resin DSL JSON schemas that represent logic or actions, 
# which must be strictly bound to the 50 atoms.
INSTRUCTION_KEYS = {
    "action", "operator", "primitive", "condition", 
    "instruction", "state", "logical_operator", 
    "gate", "rule", "constraint", "command"
}

def verify_semantic_atoms(payload_obj):
    """
    Compiler Front-End (Semantic Sieve).
    Scans the JSON payload recursively. If an instruction field attempts 
    to use a semantic concept outside the GREETME_50 lexicon (like "Hope" or "Try"),
    it fails the semantic audit.
    Variables/Keys are permitted to be flexible for real-world interactions.
    """
    if isinstance(payload_obj, dict):
        for k, v in payload_obj.items():
            if k.lower() in INSTRUCTION_KEYS:
                if isinstance(v, str):
                    # Check if the string matches an exact primitive (case-insensitive)
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
