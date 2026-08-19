import os
import json
import logging
import hashlib
import sys

logger = logging.getLogger(__name__)

class SecurityEnclave:
    def __init__(self):
        pass

    def verify_kernel_integrity(self, manifest_path: str, base_dir: str) -> bool:
        """
        Verifies the SHA-256 integrity of the core files against the signed manifest.
        If any file is tampered with, it returns False and execution should halt.
        """
        if not os.path.exists(manifest_path):
            logger.error(f"Manifest file not found: {manifest_path}")
            return False

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                expected_hashes = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load manifest {manifest_path}: {e}")
            return False
            
        for rel_path, expected_hash in expected_hashes.items():
            full_path = os.path.join(base_dir, rel_path)
            
            if not os.path.exists(full_path):
                logger.error(f"[CRITICAL KERNEL PANIC] Missing Core File: {rel_path}")
                return False

            sha256_hash = hashlib.sha256()
            try:
                with open(full_path, "rb") as f:
                    for byte_block in iter(lambda: f.read(4096), b""):
                        sha256_hash.update(byte_block)
            except Exception as e:
                logger.error(f"Could not read {rel_path} for hash verification: {e}")
                return False
                    
            if sha256_hash.hexdigest() != expected_hash:
                logger.error(f"[CRITICAL KERNEL PANIC] Integrity Breach Detected in: {rel_path}")
                logger.error("The State-Locked Protocol kernel has been tampered with or modified.")
                logger.error("Halting all autonomous execution immediately.")
                return False
                
        logger.info("Kernel integrity verified successfully against SHA-256 manifest.")
        return True

def verify_kernel_integrity(base_dir: str, manifest_path: str) -> tuple[bool, str]:
    """Module-level helper returning (is_valid, report_str)."""
    enclave = SecurityEnclave()
    is_valid = enclave.verify_kernel_integrity(manifest_path, base_dir)
    return is_valid, "All core files matched manifest SHA-256 signatures." if is_valid else "Manifest mismatch detected."
