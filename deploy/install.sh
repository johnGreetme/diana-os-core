#!/bin/bash
set -e

echo "Installing D.I.A.N.A. OS - Sovereign Hacker Edition..."

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)"
  exit 1
fi

# 1. Install System Dependencies
echo "Installing dependencies..."
apt-get update
apt-get install -y build-essential patchelf python3-dev tesseract-ocr x11-utils libsm6 libxext6 libxrender-dev

# 2. Setup Directories
echo "Setting up directories..."
mkdir -p /opt/kytin/diana
mkdir -p /etc/diana
mkdir -p /var/log/diana

# 3. Move Binaries & Secure Packs
echo "Moving compiled binaries..."
if [ -f "../dist/diana_hacker_linux_amd64.tar.gz" ]; then
    tar -xzvf ../dist/diana_hacker_linux_amd64.tar.gz -C /opt/kytin/diana/
else
    echo "Warning: Release tarball not found. Make sure to run build.sh first."
fi

# 4. Permissions
chmod -R 755 /opt/kytin/diana
chown -R root:root /opt/kytin/diana
chmod 700 /etc/diana
chown -R root:root /var/log/diana

# 5. Systemd Service
echo "Installing systemd service..."
cp diana-hacker.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable diana-hacker.service

echo "Installation complete!"
echo "To activate your node, run: /opt/kytin/diana/diana_hacker activate <LICENSE_KEY>"
echo "To start the daemon, run: systemctl start diana-hacker.service"
