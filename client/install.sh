#!/usr/bin/env bash
# Timekpr-HA client installer: deploys the Python agent + systemd service.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." 1>&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SRC="$SCRIPT_DIR/timepkr_agent.py"
AGENT_DEST="/usr/local/bin/timekpr_agent.py"
CONF_FILE="/etc/timekpr-agent.conf"
STATE_FILE="/etc/timekpr-agent.state"
SERVICE_FILE="/etc/systemd/system/timekpr-agent.service"

echo "=== Timekpr-HA Client Installer ==="

if [[ ! -f "$AGENT_SRC" ]]; then
  echo "ERROR: $AGENT_SRC not found. Run this installer from within the client/ directory." 1>&2
  exit 1
fi

# 1. Collect configuration
read -r -p "Enter Target Child Username: " TARGET_USER
read -r -p "Enter Home Assistant / MQTT IP: " MQTT_BROKER
read -r -p "Enter MQTT Port (default 1883): " MQTT_PORT
MQTT_PORT="${MQTT_PORT:-1883}"
read -r -p "Enter MQTT Username (leave blank if none): " MQTT_USER
read -r -s -p "Enter MQTT Password (leave blank if none): " MQTT_PASS
echo ""
read -r -p "Node ID (default: ${TARGET_USER}_pc): " NODE_ID
NODE_ID="${NODE_ID:-${TARGET_USER}_pc}"
read -r -p "Weekday cap in minutes, Mon-Fri (default 30): " WEEKDAY_CAP
WEEKDAY_CAP="${WEEKDAY_CAP:-30}"
read -r -p "Weekend cap in minutes, Sat-Sun (default 90): " WEEKEND_CAP
WEEKEND_CAP="${WEEKEND_CAP:-90}"

# 2. Locate timekpra (must exist to enforce anything)
TIMEKPRA_BIN="$(command -v timekpra || true)"
if [[ -z "$TIMEKPRA_BIN" ]]; then
  echo "ERROR: 'timekpra' not found. Install Timekpr-nExT first." 1>&2
  exit 1
fi

# 3. Install dependencies: the agent requires paho-mqtt >= 2.0
if ! python3 -c 'import sys, paho.mqtt as m; sys.exit(0 if int(m.__version__.split(".")[0]) >= 2 else 1)' 2>/dev/null; then
  echo "Installing paho-mqtt (>= 2.0)..."
  apt-get update -qq
  apt-get install -y -qq python3-paho-mqtt
  if ! python3 -c 'import sys, paho.mqtt as m; sys.exit(0 if int(m.__version__.split(".")[0]) >= 2 else 1)' 2>/dev/null; then
    echo "ERROR: the distro's python3-paho-mqtt is older than 2.0, which this agent requires." 1>&2
    echo "Install paho-mqtt>=2.0 into python3 (e.g. pip3 install 'paho-mqtt>=2.0') and re-run." 1>&2
    exit 1
  fi
else
  echo "paho-mqtt >= 2.0 already available."
fi

# 4. Deploy Python agent
echo "Copying agent to $AGENT_DEST..."
install -m 0755 "$AGENT_SRC" "$AGENT_DEST"

# 5. Write configuration. systemd EnvironmentFile supports double-quoted values
#    with \" and \\ escapes; it does not expand variables, so $ and ' are literal.
dq() { local v="${1//\\/\\\\}"; printf '"%s"' "${v//\"/\\\"}"; }
umask 177
cat >"$CONF_FILE" <<EOF
MQTT_BROKER=$(dq "$MQTT_BROKER")
MQTT_PORT=$(dq "$MQTT_PORT")
MQTT_USER=$(dq "$MQTT_USER")
MQTT_PASS=$(dq "$MQTT_PASS")
TARGET_USER=$(dq "$TARGET_USER")
NODE_ID=$(dq "$NODE_ID")
WEEKDAY_CAP=$(dq "$WEEKDAY_CAP")
WEEKEND_CAP=$(dq "$WEEKEND_CAP")
STATE_FILE=$(dq "$STATE_FILE")
TIMEKPR_BIN=$(dq "$TIMEKPRA_BIN")
EOF
chmod 600 "$CONF_FILE"
echo "Configuration written to $CONF_FILE"

# 6. Create and start systemd service
echo "Creating systemd background service..."
cat >"$SERVICE_FILE" <<EOF
[Unit]
Description=Timekpr Home Assistant Sync Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=$CONF_FILE
ExecStartPre=-$TIMEKPRA_BIN --userlist
ExecStart=/usr/bin/python3 $AGENT_DEST
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now timekpr-agent.service

echo ""
echo "=== Installation Complete! ==="
echo "The agent is running and syncing with Home Assistant."
echo "Follow logs with:  journalctl -u timekpr-agent -f"
echo "Verify timekpra with:  sudo timekpra --userinfort $TARGET_USER | grep TIME_LEFT_DAY"
