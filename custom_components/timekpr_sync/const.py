"""Constants for the Timekpr Screen Time Sync integration."""

from __future__ import annotations

DOMAIN = "timekpr_sync"

# Config flow option keys (stored on the config entry data)
CONF_NODE_ID = "node_id"
CONF_WEEKLY_BUDGET = "weekly_budget"
CONF_WEEKDAY_CAP = "weekday_cap_minutes"
CONF_WEEKEND_CAP = "weekend_cap_minutes"

# Defaults
DEFAULT_NODE_ID = "child_pc"
DEFAULT_WEEKLY_BUDGET = 300
DEFAULT_WEEKDAY_CAP = 30
DEFAULT_WEEKEND_CAP = 90

# Entity identifiers
NUMBER_UNIQUE_ID = "timekpr_weekly_screen_time_left"
SWITCH_UNIQUE_ID = "timekpr_block_pc_access"
BINARY_SENSOR_UNIQUE_ID = "timekpr_pc_agent_online"
SENSOR_UNIQUE_ID = "timekpr_pc_time_left"

# Entity names
NUMBER_NAME = "Weekly Screen Time Left"
SWITCH_NAME = "Block PC Access"
BINARY_SENSOR_NAME = "PC Agent Online"
SENSOR_NAME = "PC Time Left"

# Icons / units
NUMBER_ICON = "mdi:timer-sand"
SWITCH_ICON = "mdi:shield-lock"
SENSOR_ICON = "mdi:desktop-classic"
NUMBER_UNIT = "min"
SENSOR_UNIT = "min"

# MQTT topic suffix parts (see README topic contract)
TOPIC_SUFFIX_WEEKLY_BUDGET = "weekly_budget"
TOPIC_SUFFIX_DEDUCT = "deduct"
TOPIC_SUFFIX_BLOCK_SET = "blocked/set"
TOPIC_SUFFIX_BLOCK_STATE = "blocked/state"
TOPIC_SUFFIX_AVAILABLE = "available"
TOPIC_SUFFIX_PC_TIME_LEFT = "pc_time_left"
TOPIC_SUFFIX_CAPS = "caps"

# MQTT payload values
PAYLOAD_ON = "ON"
PAYLOAD_OFF = "OFF"
PAYLOAD_ONLINE = "online"
PAYLOAD_OFFLINE = "offline"

# Service names
SERVICE_DEDUCT_TV = "deduct_tv_minutes"
SERVICE_ADD_TV = "add_tv_minutes"
