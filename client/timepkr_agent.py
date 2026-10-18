#!/usr/bin/env python3
import os
import json
import subprocess
import time
import datetime
import paho.mqtt.client as mqtt

# Read configuration from environment / config file
MQTT_BROKER = os.environ.get("MQTT_BROKER", "homeassistant.local")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")
TARGET_USER = os.environ.get("TARGET_USER", "child")
NODE_ID = os.environ.get("NODE_ID", f"{TARGET_USER}_pc")

weekly_budget_remaining = 300
last_pc_seconds = None
is_blocked = False


def get_daily_cap_seconds():
    """Mon-Fri (0-4) = 30 min (1800s); Sat-Sun (5-6) = 90 min (5400s)"""
    weekday = datetime.datetime.now().weekday()
    return 1800 if weekday < 5 else 5400


def get_timekpr_time_left():
    try:
        out = subprocess.check_output(
            ["timekpra", "--userinfo", TARGET_USER], text=True
        )
        for line in out.splitlines():
            if line.startswith("TIME_LEFT_DAY:"):
                return int(line.split()[1])
    except Exception:
        pass
    return None


def set_timekpr_seconds(secs):
    subprocess.run(
        ["timekpra", "--settimeleft", TARGET_USER, "=", str(max(0, int(secs)))]
    )


def restore_allowance():
    """Calculates min(today_cap, weekly_budget) and applies it"""
    daily_cap = get_daily_cap_seconds()
    weekly_secs = weekly_budget_remaining * 60
    allowance = min(daily_cap, weekly_secs)
    set_timekpr_seconds(allowance)


def send_discovery(client):
    dev_info = {
        "identifiers": [NODE_ID],
        "name": "Kid's PC Screen Time",
        "model": "Timekpr Controller",
    }

    # 1. Number entity (Weekly Budget display/sync)
    client.publish(
        f"homeassistant/number/{NODE_ID}/weekly_budget/config",
        json.dumps(
            {
                "name": "Weekly Time Left",
                "command_topic": f"{NODE_ID}/weekly_budget/set",
                "state_topic": f"{NODE_ID}/weekly_budget/state",
                "min": 0,
                "max": 300,
                "step": 1,
                "unit_of_measurement": "min",
                "unique_id": f"{NODE_ID}_weekly_budget",
                "device": dev_info,
            }
        ),
        retain=True,
    )

    # 2. Switch entity: Hard Block / Parental Lock
    client.publish(
        f"homeassistant/switch/{NODE_ID}/blocked/config",
        json.dumps(
            {
                "name": "Block PC Access",
                "command_topic": f"{NODE_ID}/blocked/set",
                "state_topic": f"{NODE_ID}/blocked/state",
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:shield-lock",
                "unique_id": f"{NODE_ID}_block_switch",
                "device": dev_info,
            }
        ),
        retain=True,
    )


def on_connect(client, userdata, flags, rc):
    send_discovery(client)
    client.subscribe(f"{NODE_ID}/+/set")
    client.publish(f"{NODE_ID}/blocked/state", "OFF", retain=True)


def on_message(client, userdata, msg):
    global weekly_budget_remaining, is_blocked
    topic = msg.topic
    payload = msg.payload.decode()

    # Handle Block Switch
    if topic.endswith("/blocked/set"):
        if payload == "ON":
            is_blocked = True
            set_timekpr_seconds(0)  # Immediately kick out / lock desktop
            client.publish(f"{NODE_ID}/blocked/state", "ON", retain=True)
            print("PC Access: BLOCKED")
        else:
            is_blocked = False
            restore_allowance()  # Restore allowed minutes
            client.publish(f"{NODE_ID}/blocked/state", "OFF", retain=True)
            print("PC Access: UNBLOCKED")

    # Handle Weekly Budget adjustments from HA
    elif topic.endswith("/weekly_budget/set"):
        weekly_budget_remaining = int(float(payload))
        if not is_blocked:
            current_pc_left = get_timekpr_time_left()
            weekly_secs = weekly_budget_remaining * 60
            if current_pc_left is not None and current_pc_left > weekly_secs:
                set_timekpr_seconds(weekly_secs)


client = mqtt.Client()
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASS)

client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

while True:
    if is_blocked:
        # Keep locked while blocked
        if get_timekpr_time_left() != 0:
            set_timekpr_seconds(0)
    else:
        # Normal accounting: track spent minutes and push to HA
        current_secs = get_timekpr_time_left()
        if current_secs is not None and last_pc_seconds is not None:
            consumed = last_pc_seconds - current_secs
            if consumed >= 60:
                mins_spent = consumed // 60
                client.publish(f"{NODE_ID}/deduct_pc_minutes", mins_spent)
                last_pc_seconds = current_secs
        else:
            last_pc_seconds = current_secs

    time.sleep(30)
