#!/usr/bin/env bash
set -e

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." 1>&2
  exit 1
fi

echo "=== Timekpr-HA Client Installer ==="

# 1. Collect Configuration
read -p "Enter Target Child Username: " TARGET_USER
read -p "Enter Home Assistant / MQTT IP: " MQTT_BROKER
read -p "Enter MQTT Username (leave blank if none): " MQTT_USER
read -s -p "Enter MQTT Password (leave blank if none): " MQTT_PASS
echo ""

# 2. Install dependencies
echo "Installing Python MQTT library..."
apt-get update -qq
apt-get install -y -qq python3-paho-mqtt

# 3. Deploy Python Agent
echo "Copying agent to /usr/local/bin..."
cp timekpr_agent.py /usr/local/bin/timekpr_agent.py
chmod +x /usr/local/bin/timekpr_agent.py

# 4. Write Configuration File
echo "Writing configuration to /etc/timekpr-agent.conf..."
cat <<EOF >/etc/timekpr-agent.conf
MQTT_BROKER=${MQTT_BROKER}
MQTT_PORT=1883
MQTT_USER=${MQTT_USER}
MQTT_PASS=${MQTT_PASS}
TARGET_USER=${TARGET_USER}
NODE_ID=${TARGET_USER}_pc
EOF
chmod 600 /etc/timekpr-agent.conf

# 5. Create and Start Systemd Service
echo "Creating systemd background service..."
cat <<EOF >/etc/systemd/system/timekpr-agent.service
[Unit]
Description=Timekpr Home Assistant Sync Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/timekpr-agent.conf
ExecStart=/usr/bin/python3 /usr/local/bin/timekpr_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now timekpr-agent.service

echo "=== Installation Complete! ==="
echo "The agent is running and syncing with Home Assistant."
