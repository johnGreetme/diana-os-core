#!/bin/bash
set -e

echo "Starting Pure Python Build Pipeline for D.I.A.N.A. OS Sovereign Hacker Edition"

# 1. Credential Sanitization Pre-Check (Zero Operational Data Leakage)
if grep -rE "(sk-[a-zA-Z0-9]{32}|AIza[0-9A-Za-z-_]{35}|eyJ[a-zA-Z0-9_-]{10,})" core/ parsers/ actuation/ engine/; then
    echo "ERROR: Hardcoded secrets found! Compilation aborted."
    exit 1
fi

# Require telemetry dashboard in the release tree (boot-critical)
if [ ! -f dashboard/diana_monitor.py ] || [ ! -f diana_desktop_launcher.py ]; then
    echo "ERROR: dashboard/diana_monitor.py and diana_desktop_launcher.py are required for boot."
    exit 1
fi

# 2. Hardcode 5-Axiom Limit in Resin Parser
sed -i 's/MAX_AXIOMS = .*/MAX_AXIOMS = 5/g' engine/resin_compiler.py

# 3. Generate SHA-256 Integrity Manifest
echo "Generating core integrity manifest..."
python3 tools/generate_manifest.py

# 4. Packaging (keep dashboard/requirements.txt — do not blanket-exclude *.txt)
echo "Packaging release..."
mkdir -p dist
rm -f dist/diana-os-hacker-v1.0.tar.gz
tar -czvf dist/diana-os-hacker-v1.0.tar.gz \
    --exclude="./dist" \
    --exclude="*.db" \
    --exclude="*.sqlite" \
    --exclude="*.sqlite3" \
    --exclude="*.log" \
    --exclude="*.tmp" \
    --exclude="*.yaml" \
    --exclude="__pycache__" \
    --exclude=".pytest_cache" \
    --exclude=".git" \
    --exclude=".cursor" \
    -C . .

echo "Build complete. Artifacts in dist/"
