#!/usr/bin/env bash
# DIANA OS Installation & Service Deployment Script
# Targets: Ubuntu 22.04 LTS Bare-Metal (Hacker / Architect Tiers)
# Boots: Ollama + core daemon + telemetry dashboard (pywebview launcher)

set -e

echo "[+] Starting DIANA OS Deployment..."
APP_DIR="$(pwd)"
CURRENT_USER=$USER
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
if [ -z "$USER_HOME" ]; then USER_HOME="$HOME"; fi

# Resolve daemon entrypoint (packaged trees use core/daemon.py)
DAEMON_ENTRY="$APP_DIR/core/daemon.py"
if [ -f "$APP_DIR/openclaw_daemon.py" ]; then
    DAEMON_ENTRY="$APP_DIR/openclaw_daemon.py"
fi

if [ ! -f "$APP_DIR/dashboard/diana_monitor.py" ] || [ ! -f "$APP_DIR/diana_desktop_launcher.py" ]; then
    echo "ERROR: Telemetry dashboard missing. Refusing install without bootable dashboard."
    exit 1
fi

# 1. System Dependencies (PyWebView & General)
echo "[+] Installing System Dependencies..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-gi gir1.2-webkit2-4.0 xvfb curl

# 2. Ollama Native Auto-Boot (Pinned v0.33.2 with RTX GPU Layer Offloading)
echo "[+] Installing Ollama Native Engine (v0.33.2)..."
OLLAMA_VERSION="0.33.2"
curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION="$OLLAMA_VERSION" sh

# Configure Ollama Systemd override for GPU layer offload & CPU reservation for Z3 SMT
sudo mkdir -p /etc/systemd/system/ollama.service.d/
cat << EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null
[Service]
Environment="CUDA_VISIBLE_DEVICES=0"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_GPU_OVERHEAD=0"
EOF

# 3. OpenClaw Workspace Scaffolding (Two-Loop Architecture)
echo "[+] Scaffolding OpenClaw workspace directories..."
mkdir -p ~/.openclaw/workspace/skills/auto-skill-generator/
mkdir -p ~/.openclaw/workspace/draft_skills/
mkdir -p ~/.openclaw/workspace/reflections/
sudo mkdir -p /var/log/diana
sudo chown "$CURRENT_USER":"$CURRENT_USER" /var/log/diana

# Copy the Auto-Skill Generator Meta-Skill into the OpenClaw workspace
if [ -f "$APP_DIR/skills/auto-skill-generator/SKILL.md" ]; then
    cp "$APP_DIR/skills/auto-skill-generator/SKILL.md" ~/.openclaw/workspace/skills/auto-skill-generator/SKILL.md
    echo "[✓] Auto-Skill Generator Meta-Skill installed."
fi

# 4. Python Dependencies (core + dashboard telemetry)
echo "[+] Installing Python Environment..."
pip3 install pywebview streamlit qdrant-client httpx z3-solver pymodbus
if [ -f "$APP_DIR/dashboard/requirements.txt" ]; then
    pip3 install -r "$APP_DIR/dashboard/requirements.txt"
fi

# 5. Linux Desktop Integration
echo "[+] Generating .desktop shortcut for DIANA OS Telemetry..."
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

cat << EOF > "$DESKTOP_DIR/diana_os.desktop"
[Desktop Entry]
Name=D.I.A.N.A
Comment=DIANA OS Telemetry & Control Dashboard
Exec=python3 $APP_DIR/diana_desktop_launcher.py
Icon=$APP_DIR/diana_icon.png
Terminal=false
Type=Application
Categories=Development;System;
EOF

chmod +x "$DESKTOP_DIR/diana_os.desktop"
echo "[✓] DIANA OS Telemetry Desktop app installed."

# 6. Systemd Auto-Boot Services (daemon + telemetry dashboard)
echo "[+] Configuring systemd Auto-Boot Services..."

cat << EOF | sudo tee /etc/systemd/system/diana-daemon.service > /dev/null
[Unit]
Description=DIANA OS Core AI Daemon
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $DAEMON_ENTRY
Restart=always
RestartSec=5
Environment=PATH=$USER_HOME/.local/bin:/usr/bin:/bin
StandardOutput=append:/var/log/diana/daemon.log
StandardError=append:/var/log/diana/error.log

[Install]
WantedBy=multi-user.target
EOF

cat << EOF | sudo tee /etc/systemd/system/diana-telemetry.service > /dev/null
[Unit]
Description=DIANA OS Telemetry Dashboard (diana_desktop_launcher)
After=graphical.target network.target diana-daemon.service
Wants=graphical.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/python3 $APP_DIR/diana_desktop_launcher.py
Restart=always
RestartSec=5
Environment=PATH=$USER_HOME/.local/bin:/usr/bin:/bin
Environment=DISPLAY=:0
Environment=XAUTHORITY=$USER_HOME/.Xauthority
Environment=XDG_RUNTIME_DIR=/run/user/%U
StandardOutput=append:/var/log/diana/telemetry.log
StandardError=append:/var/log/diana/telemetry-error.log

[Install]
WantedBy=graphical.target
EOF

if [ -f "$APP_DIR/deploy/diana-telemetry.service" ]; then
    sudo cp "$APP_DIR/deploy/diana-telemetry.service" /etc/systemd/system/diana-telemetry.service.template
fi

echo "[+] Enabling and Starting DIANA OS Services..."
sudo systemctl daemon-reload
sudo systemctl enable diana-daemon.service
sudo systemctl enable diana-telemetry.service
sudo systemctl start diana-daemon.service
sudo systemctl start diana-telemetry.service || true

echo "[+] Applying Layer 1 Immutable Infrastructure Locks (POSIX)..."
chmod -R 555 "$APP_DIR/tools/"
chmod -R 555 "$APP_DIR/core/"
chmod -R 555 "$APP_DIR/engine/"
chmod 555 "$APP_DIR/diana_desktop_launcher.py"
chmod -R 555 "$APP_DIR/dashboard/"
if [ -d "$APP_DIR/core_geometries" ]; then
    chmod -R 444 "$APP_DIR/core_geometries/"
fi
if [ -d "$APP_DIR/skills/diana_core" ]; then
    chmod -R 444 "$APP_DIR/skills/diana_core/"
fi
if [ -f "$APP_DIR/The_Skill_Genesis.json" ]; then
    chmod 444 "$APP_DIR/The_Skill_Genesis.json"
fi

echo "[✓] Deployment completed. Boot stack: ollama + diana-daemon + diana-telemetry."
