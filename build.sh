#!/bin/bash
set -e

echo "Starting Nuitka C-Compilation Pipeline for D.I.A.N.A. OS Sovereign Hacker Edition"

# 1. Credential Sanitization Pre-Check (Zero Operational Data Leakage)
if grep -rE "(sk-[a-zA-Z0-9]{32}|AIza[0-9A-Za-z-_]{35}|eyJ[a-zA-Z0-9_-]{10,})" core/ parsers/ actuation/ engine/; then
    echo "ERROR: Hardcoded secrets found! Compilation aborted."
    exit 1
fi

# 2. Hardcode 5-Axiom Limit in Resin Parser
sed -i 's/MAX_AXIOMS = .*/MAX_AXIOMS = 5/g' engine/resin_compiler.py

# 3. Nuitka Compilation
python3 -m nuitka \
    --mode=standalone \
    --mode=onefile \
    --lto=yes \
    --python-flag=no_docstrings \
    --python-flag=no_asserts \
    --include-data-dir=secure_packs=secure_packs \
    --output-dir=build \
    --output-filename=diana_hacker \
    core/daemon.py

# 4. Packaging
echo "Packaging release..."
mkdir -p dist
tar -czvf dist/diana_hacker_linux_amd64.tar.gz -C build diana_hacker \
    --exclude="*.db" \
    --exclude="*.sqlite" \
    --exclude="*.sqlite3" \
    --exclude="*.log" \
    --exclude="*.tmp" \
    --exclude="*.txt" \
    --exclude="*.yaml" \
    --exclude="*.json" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    -C ../ .env.example

echo "Build complete. Artifacts in dist/"
