#!/usr/bin/env python3
"""Timekpr → Home Assistant sync agent.

Pure actuator + reporter for Home Assistant (the single source of truth). The agent:
- subscribes to the HA-published weekly budget and clamps today's PC allowance to it,
- subscribes to the emergency block command and locks/unlocks the desktop via ``timekpra``,
- periodically reports PC availability, live time left, and minutes spent on MQTT.

Configuration is read from environment variables (see the systemd EnvironmentFile).
"""

import datetime
import json
import logging
import os
import signal
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

# ---------------------------------------------------------------------------
# Configuration (environment)
# ---------------------------------------------------------------------------
_MQTT_BROKER = os.environ.get("MQTT_BROKER", "homeassistant.local")
_MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
_MQTT_USER = os.environ.get("MQTT_USER", "")
_MQTT_PASS = os.environ.get("MQTT_PASS", "")
_TARGET_USER = os.environ.get("TARGET_USER", "child")
_NODE_ID = os.environ.get("NODE_ID", f"{_TARGET_USER}_pc")

_WEEKDAY_CAP = int(os.environ.get("WEEKDAY_CAP", "30"))  # minutes, Mon-Fri
_WEEKEND_CAP = int(os.environ.get("WEEKEND_CAP", "90"))  # minutes, Sat-Sun
_POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
_STATE_FILE = os.environ.get("STATE_FILE", "/etc/timekpr-agent.state")

_LOG = logging.getLogger("timekpr-agent")

# ---------------------------------------------------------------------------
# MQTT topics (must match the HA integration's topic contract)
# ---------------------------------------------------------------------------
TOPIC_WEEKLY_BUDGET = f"timekpr/{_NODE_ID}/weekly_budget"  # HA -> PC (retained)
TOPIC_DEDUCT = f"timekpr/{_NODE_ID}/deduct"  # PC -> HA
TOPIC_BLOCK_SET = f"timekpr/{_NODE_ID}/blocked/set"  # HA -> PC
TOPIC_BLOCK_STATE = f"timekpr/{_NODE_ID}/blocked/state"  # PC -> HA (retained)
TOPIC_AVAILABLE = f"timekpr/{_NODE_ID}/available"  # PC -> HA (retained/LWT)
TOPIC_PC_TIME_LEFT = f"timekpr/{_NODE_ID}/pc_time_left"  # PC -> HA (retained)
TOPIC_CAPS = f"timekpr/{_NODE_ID}/caps"  # HA -> PC (retained)

# Runtime state
_weekly_budget_remaining = 300
_last_pc_seconds = None
_pending_seconds = 0
_is_blocked = False


# ---------------------------------------------------------------------------
# Timekpr helpers
# ---------------------------------------------------------------------------
def _timekpr_bin() -> str:
    return os.environ.get("TIMEKPR_BIN", "timekpra")


def get_daily_cap_seconds(now: datetime.datetime | None = None) -> int:
    """Mon-Fri (0-4) = WEEKDAY_CAP mins; Sat-Sun (5-6) = WEEKEND_CAP mins.

    ``now`` is injectable for testing; defaults to the current time.
    """
    if now is None:
        now = datetime.datetime.now()
    minutes = _WEEKDAY_CAP if now.weekday() < 5 else _WEEKEND_CAP
    return minutes * 60


def _parse_time_left_day(output: str):
    """Parse `TIME_LEFT_DAY: <seconds>` (and the real-time variant) from ``timekpra`` output."""
    if not output:
        return None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("TIME_LEFT_DAY:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except (IndexError, ValueError):
                return None
    return None


def get_timekpr_time_left():
    """Return today's remaining seconds via live info, falling back to stored info.

    Returns None if the value cannot be obtained (e.g. the user isn't configured yet).
    """
    # --userinfort returns real-time values while a session is logged in.
    for flag in ("--userinfort", "--userinfo"):
        try:
            out = subprocess.check_output(
                [_timekpr_bin(), flag, _TARGET_USER],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        parsed = _parse_time_left_day(out)
        if parsed is not None:
            return parsed
    return None


def set_timekpr_seconds(secs: int) -> bool:
    """Set today's remaining time to ``secs`` (clamped to >= 0)."""
    try:
        subprocess.run(
            [_timekpr_bin(), "--settimeleft", _TARGET_USER, "=", str(max(0, int(secs)))],
            check=False,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (FileNotFoundError, OSError):
        return False


def restore_allowance() -> None:
    """Apply min(daily_cap, weekly_budget) as the allowance for today."""
    daily_cap = get_daily_cap_seconds()
    weekly_secs = max(0, _weekly_budget_remaining) * 60
    allowance = min(daily_cap, weekly_secs)
    _LOG.debug("Restoring allowance to %s seconds", allowance)
    _agent_set(allowance)


def _clamp_to_allowance() -> None:
    """Lower today's remaining time to min(daily_cap, weekly_budget) if it is higher."""
    current = get_timekpr_time_left()
    allowance = min(get_daily_cap_seconds(), _weekly_budget_remaining * 60)
    if current is not None and current > allowance:
        _LOG.info("Clamping PC time left %ss -> %ss", current, allowance)
        _agent_set(allowance)


def _apply_caps(payload: str) -> None:
    """Update the daily caps from the retained HA `caps` JSON payload."""
    global _WEEKDAY_CAP, _WEEKEND_CAP
    try:
        data = json.loads(payload)
        weekday = int(data["weekday_cap_minutes"])
        weekend = int(data["weekend_cap_minutes"])
    except (ValueError, KeyError, TypeError):
        _LOG.warning("Invalid caps payload ignored: %r", payload)
        return
    if weekday < 0 or weekend < 0:
        _LOG.warning("Negative caps ignored: %r", payload)
        return
    _WEEKDAY_CAP, _WEEKEND_CAP = weekday, weekend
    _LOG.info("Daily caps set to %s/%s mins (weekday/weekend)", weekday, weekend)


def _agent_set(secs: int) -> None:
    """Set time left and mark it as agent-initiated so it is not reported as usage."""
    global _last_pc_seconds
    value = max(0, int(secs))
    set_timekpr_seconds(value)
    _last_pc_seconds = value



# ---------------------------------------------------------------------------
# Block-state persistence (survive restarts)
# ---------------------------------------------------------------------------
def _load_persisted_blocked() -> bool:
    try:
        with open(_STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh).get("blocked", False)
    except (OSError, ValueError):
        return False


def _persist_blocked(blocked: bool) -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump({"blocked": blocked}, fh)
    except OSError:
        _LOG.warning("Could not persist block state to %s", _STATE_FILE)


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def _on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        _LOG.error("MQTT connection failed: %s", reason_code)
        return
    _LOG.info("Connected to MQTT broker at %s", _MQTT_BROKER)
    client.subscribe([(TOPIC_WEEKLY_BUDGET, 0), (TOPIC_BLOCK_SET, 0), (TOPIC_CAPS, 0)])
    client.publish(TOPIC_AVAILABLE, "online", qos=0, retain=True)
    publish_pc_time_left(client)
    # Re-assert block state from persistence after a restart.
    if _is_blocked:
        client.publish(TOPIC_BLOCK_STATE, "ON", qos=0, retain=True)


def _on_disconnect(client, userdata, flags, reason_code, properties):
    _LOG.warning("Disconnected from MQTT broker (reason_code=%s)", reason_code)


def _on_message(client, userdata, msg):
    global _weekly_budget_remaining, _is_blocked
    payload = msg.payload.decode().strip()

    if msg.topic == TOPIC_CAPS:
        _apply_caps(payload)
        if not _is_blocked:
            _clamp_to_allowance()

    elif msg.topic == TOPIC_WEEKLY_BUDGET:
        try:
            _weekly_budget_remaining = max(0, int(float(payload)))
        except ValueError:
            _LOG.warning("Invalid weekly budget payload: %r", payload)
            return
        _LOG.info("Weekly budget set to %s mins", _weekly_budget_remaining)
        if not _is_blocked:
            _clamp_to_allowance()

    elif msg.topic == TOPIC_BLOCK_SET:
        if payload == "ON":
            _is_blocked = True
            _persist_blocked(True)
            _agent_set(0)
            client.publish(TOPIC_BLOCK_STATE, "ON", qos=0, retain=True)
            _LOG.warning("PC access BLOCKED by Home Assistant")
        elif payload == "OFF":
            _is_blocked = False
            _persist_blocked(False)
            restore_allowance()
            client.publish(TOPIC_BLOCK_STATE, "OFF", qos=0, retain=True)
            _LOG.info("PC access UNBLOCKED by Home Assistant")


def publish_pc_time_left(client) -> None:
    seconds = get_timekpr_time_left()
    if seconds is not None:
        client.publish(TOPIC_PC_TIME_LEFT, str(seconds), qos=0, retain=True)



# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> int:
    global _last_pc_seconds, _is_blocked, _pending_seconds

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    _is_blocked = _load_persisted_blocked()
    _LOG.info(
        "Starting timekpr-agent for user=%s node=%s blocked=%s",
        _TARGET_USER,
        _NODE_ID,
        _is_blocked,
    )

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"timekpr-agent-{_NODE_ID}",
    )
    if _MQTT_USER:
        client.username_pw_set(_MQTT_USER, _MQTT_PASS)

    client.will_set(TOPIC_AVAILABLE, "offline", qos=0, retain=True)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    client.connect_async(_MQTT_BROKER, _MQTT_PORT, keepalive=60)
    client.loop_start()

    try:
        while True:
            # Keep the LWT topic fresh and reflect liveness.
            client.publish(TOPIC_AVAILABLE, "online", qos=0, retain=True)

            if _is_blocked:
                # Stay locked while blocked (re-assert in case time was granted another way).
                current = get_timekpr_time_left()
                if current is not None and current != 0:
                    set_timekpr_seconds(0)
                _last_pc_seconds = 0
            else:
                current = get_timekpr_time_left()
                if current is not None:
                    publish_pc_time_left(client)
                if current is not None:
                    publish_pc_time_left(client)
                    if _last_pc_seconds is not None and current < _last_pc_seconds:
                        # Usage since last poll; carry partial minutes to the next report.
                        _pending_seconds += _last_pc_seconds - current
                        minutes = _pending_seconds // 60
                        if minutes > 0:
                            client.publish(TOPIC_DEDUCT, str(minutes), qos=0)
                            _pending_seconds -= minutes * 60
                            _LOG.info("Reported %s mins spent on PC", minutes)
                    _last_pc_seconds = current

            time.sleep(_POLL_SECONDS)
    except KeyboardInterrupt:
        _LOG.info("Shutting down.")
    finally:
        client.publish(TOPIC_AVAILABLE, "offline", qos=0, retain=True)
        client.loop_stop()
        client.disconnect()

    return 0


def _handle_sigterm(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_sigterm)
    sys.exit(main())

