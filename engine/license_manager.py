import os
import sys
import json
import uuid
import subprocess
import logging
import requests

logger = logging.getLogger(__name__)

LOCK_FILE_PATH = "/etc/diana/diana_hardware.lock"

class LicenseManager:
    def __init__(self, tier="hacker"):
        self.tier = tier.upper()
        self.server_url = os.environ.get("LICENSE_SERVER_URL", "https://api.kytin.io/v1/activate")

    def _get_hardware_uuid(self) -> str:
        """Fingerprints the host machine, preferencing NVIDIA GPU UUID."""
        try:
            # Try nvidia-smi first
            result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, check=True)
            output = result.stdout.strip()
            if output and "UUID" in output:
                # E.g. GPU 0: NVIDIA RTX 6000 Ada Generation (UUID: GPU-xxxxx-xxxx...)
                uuid_str = output.split("UUID:")[1].split(")")[0].strip()
                return uuid_str
        except Exception:
            pass
        
        # Fallback to MAC address
        return str(uuid.getnode())

    def activate(self, license_key: str):
        """Activates the software node against the remote server."""
        if not license_key.startswith(f"{self.tier}-"):
            print(f"Error: Invalid license key format. Expected prefix: {self.tier}-")
            sys.exit(1)
            
        hardware_uuid = self._get_hardware_uuid()
        print(f"Activating node with Hardware UUID: {hardware_uuid}")
        
        try:
            response = requests.post(
                self.server_url,
                json={"license_key": license_key, "hardware_uuid": hardware_uuid},
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            # Write the server HMAC signature to the lock file
            signature_data = {
                "license_key": license_key,
                "hardware_uuid": hardware_uuid,
                "server_hmac": data.get("server_hmac")
            }
            
            # Ensure directory exists (requires sudo)
            os.makedirs(os.path.dirname(LOCK_FILE_PATH), exist_ok=True)
            with open(LOCK_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(signature_data, f)
                
            print(f"Activation successful. Lock file generated at {LOCK_FILE_PATH}")
            
        except requests.exceptions.RequestException as e:
            print(f"Activation failed. Could not reach licensing server: {e}")
            sys.exit(1)
        except PermissionError:
            print(f"Activation failed. Run with sudo to write to {LOCK_FILE_PATH}")
            sys.exit(1)
            
    def verify_lock(self):
        """Verifies the lock file matches the current hardware UUID (used by daemon loop)."""
        if not os.path.exists(LOCK_FILE_PATH):
            logger.fatal("Software Unactivated. Missing lock file.")
            sys.exit(1)
            
        try:
            with open(LOCK_FILE_PATH, "r", encoding="utf-8") as f:
                lock_data = json.load(f)
                
            current_uuid = self._get_hardware_uuid()
            if lock_data.get("hardware_uuid") != current_uuid:
                logger.fatal(f"Hardware mismatch! License locked to {lock_data.get('hardware_uuid')} but current is {current_uuid}.")
                sys.exit(1)
                
            # Verify server HMAC format (a real implementation would verify the signature using a public key here)
            if not lock_data.get("server_hmac"):
                logger.fatal("Invalid lock file signature.")
                sys.exit(1)
                
            logger.info("Hardware lock verified successfully.")
            
        except Exception as e:
            logger.fatal(f"Failed to verify lock file: {e}")
            sys.exit(1)
