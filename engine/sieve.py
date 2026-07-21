import os
import sys
import time
import hmac
import hashlib
import struct
import base64
from dotenv import load_dotenv

load_dotenv(os.path.join(r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace", ".env"))

# --- CONFIGURATION INVARIANTS ---
TOTP_SECRET = os.environ.get("HOMER_TOTP_SECRET", "KYTIN_DEFAULT_SECRET_KEY_CHANGE_ME")
TOTP_INTERVAL = 30  # Standard 30-second TOTP window

# Protected paths requiring TOTP challenge for ANY access (read or write)
PROTECTED_PATHS = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Inventions",
    r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Reflections",
]

def _generate_totp(secret: str, time_step: int = None) -> str:
    """
    Generates a 6-digit TOTP token using HMAC-SHA1.
    Compliant with RFC 6238.
    """
    if time_step is None:
        time_step = int(time.time()) // TOTP_INTERVAL
        
    try:
        # Standard Google Authenticator uses Base32 encoded secrets
        # Padding is required for b32decode, so we add '=' if missing
        padded_secret = secret.ljust((len(secret) + 7) // 8 * 8, '=')
        key = base64.b32decode(padded_secret, casefold=True)
    except Exception:
        # Fallback to UTF-8 for legacy or default non-base32 secrets
        key = secret.encode("utf-8")
        
    msg = struct.pack(">Q", time_step)
    hmac_hash = hmac.new(key, msg, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    truncated = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % 1000000).zfill(6)

def _path_is_protected(target_path: str) -> bool:
    """
    Checks if the target path falls under any protected directory.
    Catches both read and write exfiltration vectors.
    """
    normalized = os.path.normpath(os.path.abspath(target_path))
    for protected in PROTECTED_PATHS:
        protected_norm = os.path.normpath(os.path.abspath(protected))
        if normalized.startswith(protected_norm):
            return True
    return False

def evaluate_command(command_payload: str, target_path: str, provided_token: str = None) -> dict:
    """
    The cryptographic TOTP gate for D.I.A.N.A.
    Every filesystem operation (read OR write) targeting a protected path
    must pass a 6-digit TOTP challenge before execution is authorized.

    Returns:
        dict with 'authorized' (bool), 'reason' (str), and optional 'challenge_required' (bool).
    """
    if not _path_is_protected(target_path):
        return {
            "authorized": True,
            "reason": "Path is outside protected boundaries. No TOTP required.",
            "challenge_required": False
        }

    # Path is protected — TOTP challenge is mandatory
    if provided_token is None:
        return {
            "authorized": False,
            "reason": f"TOTP CHALLENGE REQUIRED: Access to '{target_path}' is protected. Provide a 6-digit token.",
            "challenge_required": True
        }

    # Validate the provided token against current and previous time windows
    current_step = int(time.time()) // TOTP_INTERVAL
    valid_tokens = [
        _generate_totp(TOTP_SECRET, current_step),
        _generate_totp(TOTP_SECRET, current_step - 1),  # Allow 1-step clock skew
    ]

    if provided_token in valid_tokens:
        return {
            "authorized": True,
            "reason": f"TOTP VERIFIED. Access to '{target_path}' authorized.",
            "challenge_required": False
        }

    return {
        "authorized": False,
        "reason": "TOTP VERIFICATION FAILED. Invalid or expired token.",
        "challenge_required": True
    }

# --- STANDALONE DIAGNOSTIC ---
if __name__ == "__main__":
    print("[*] Secure Evaluator TOTP Gate Diagnostics")
    print(f"[*] Current TOTP: {_generate_totp(TOTP_SECRET)}")

    # Test 1: Unprotected path (should pass freely)
    result = evaluate_command("cat file.txt", r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\skills\diana_core\test.py")
    print(f"[TEST 1] Unprotected path: {result}")

    # Test 2: Protected Inventions path without token (should challenge)
    result = evaluate_command("read genesis.json", r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Inventions\genesis_geometries_001.json")
    print(f"[TEST 2] Protected read (no token): {result}")

    # Test 3: Protected Reflections path without token (should challenge)
    result = evaluate_command("read deflections.log", r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Reflections\deflections.log")
    print(f"[TEST 3] Protected read (no token): {result}")

    # Test 4: Protected path with valid TOTP
    valid_token = _generate_totp(TOTP_SECRET)
    result = evaluate_command("read genesis.json", r"C:\Users\adebo\.gemini\antigravity\scratch\DianaWorkspace\Inventions\genesis_geometries_001.json", valid_token)
    print(f"[TEST 4] Protected read (valid TOTP): {result}")
