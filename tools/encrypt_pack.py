import os
import sys
import json
import argparse
from cryptography.fernet import Fernet

def main():
    parser = argparse.ArgumentParser(description="D.I.A.N.A. OS Secure Pack Generator")
    parser.add_argument("--source", required=True, help="Path to raw source file (e.g. axioms.json)")
    parser.add_argument("--output", required=True, help="Path to output .enc file")
    parser.add_argument("--key", required=False, help="Master encryption key (base64 Fernet key)")
    args = parser.parse_args()

    key = args.key or os.environ.get("DIANA_MASTER_KEY")
    if not key:
        print("Error: Must provide --key or set DIANA_MASTER_KEY env var.")
        sys.exit(1)

    fernet = Fernet(key.encode('utf-8'))

    if not os.path.exists(args.source):
        print(f"Error: Source file not found: {args.source}")
        sys.exit(1)

    try:
        # We assume the source is a valid JSON structure for now
        with open(args.source, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        payload = json.dumps(raw_data).encode("utf-8")
        encrypted_payload = fernet.encrypt(payload)

        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "wb") as f:
            f.write(encrypted_payload)

        print(f"Successfully encrypted {args.source} -> {args.output}")

    except Exception as e:
        print(f"Encryption failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
