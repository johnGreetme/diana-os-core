import hashlib
import json
import os
from pathlib import Path

# Explicit allowlist of directories and files excluded from immutability locking
IGNORE_DIRS = {
    "skills", 
    "draft_skills", 
    "qdrant_storage", 
    "reflections", 
    "inventions", 
    "ledger", 
    "__pycache__", 
    ".git",
    "dist",
    "build",
    "draft_skills",
    "graduated",
    "revoked",
    "history"
}

IGNORE_FILES = {
    "mcp.json", 
    ".env", 
    "core_manifest.sha256", 
    "deflections.log",
    "semantic_ledger.db",
    "historian.db",
    "historian.log",
    "skills_registry.json",
    "skills_audit.log"
}

def generate_core_manifest(workspace_root: str, output_path: str):
    root_path = Path(workspace_root)
    manifest = {}

    for filepath in root_path.rglob("*"):
        # Skip directories and symlinks
        if not filepath.is_file():
            continue
            
        # Check against exclusion lists
        rel_path = filepath.relative_to(root_path)
        if any(part in IGNORE_DIRS for part in rel_path.parts):
            continue
        if filepath.name in IGNORE_FILES or filepath.suffix == ".pyc":
            continue

        # Calculate SHA-256 cryptographic hash
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
                
        # Store using POSIX forward-slash formatting for cross-platform compatibility
        posix_key = str(rel_path).replace("\\", "/")
        manifest[posix_key] = sha256.hexdigest()

    # Write the immutable manifest to disk
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        
    print(f"[SUCCESS] Core Integrity Manifest generated with {len(manifest)} immutable files.")
    print(f"Manifest written to: {output_path}")

if __name__ == "__main__":
    # Resolves workspace root relative to tools/generate_manifest.py
    base_workspace = Path(__file__).resolve().parent.parent
    manifest_file = os.path.join(base_workspace, "core_manifest.sha256")
    generate_core_manifest(str(base_workspace), manifest_file)
