import os
import json
import logging
from cryptography.fernet import Fernet
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SecurityEnclave:
    def __init__(self):
        # Master key could be injected at build time, or read from a secured env block
        # For offline node-locked deployment, the key should ideally be derived from hardware lock
        self.master_key = os.environ.get("DIANA_MASTER_KEY", b"")
        self._fernet = Fernet(self.master_key) if self.master_key else None

    def load_encrypted_pack(self, pack_path: str) -> Dict[str, Any]:
        """Loads and decrypts a .enc pack strictly into system RAM."""
        if not self._fernet:
            logger.error("No DIANA_MASTER_KEY configured. Cannot decrypt axioms.")
            raise ValueError("Missing master decryption key.")
            
        if not os.path.exists(pack_path):
            raise FileNotFoundError(f"Secure pack not found: {pack_path}")
            
        try:
            with open(pack_path, "rb") as f:
                encrypted_data = f.read()
                
            # Decrypt payload strictly in memory
            decrypted_data = self._fernet.decrypt(encrypted_data)
            
            # Parse as JSON string without writing back to disk
            payload = json.loads(decrypted_data.decode("utf-8"))
            logger.info(f"Successfully decrypted and loaded pack: {os.path.basename(pack_path)}")
            return payload
            
        except Exception as e:
            logger.error(f"Failed to decrypt secure pack {pack_path}: {e}")
            raise RuntimeError(f"Cryptographic failure during pack loading: {e}")
