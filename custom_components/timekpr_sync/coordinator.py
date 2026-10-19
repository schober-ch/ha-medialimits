"""Coordinator: single source of truth for the weekly budget + MQTT wiring.

The coordinator owns the weekly balance, the block state, the PC online/availability and the PC
time-left reported by the client. Entities read and write through it; the coordinator is the only
component that publishes to or subscribes from MQTT.
"""

from __future__ import annotations

import json
import logging

import homeassistant.components.mqtt as mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_TV_PRESETS,
    DEFAULT_TV_PRESETS,
    parse_presets,
    CONF_NODE_ID,
    CONF_WEEKDAY_CAP,
    CONF_WEEKEND_CAP,
    CONF_WEEKLY_BUDGET,
    DEFAULT_NODE_ID,
    DEFAULT_WEEKDAY_CAP,
    DEFAULT_WEEKEND_CAP,
    DEFAULT_WEEKLY_BUDGET,
    PAYLOAD_OFF,
    PAYLOAD_OFFLINE,
    PAYLOAD_ON,
    PAYLOAD_ONLINE,
    TOPIC_SUFFIX_AVAILABLE,
    TOPIC_SUFFIX_BLOCK_SET,
    TOPIC_SUFFIX_BLOCK_STATE,
    TOPIC_SUFFIX_CAPS,
    TOPIC_SUFFIX_DAILY_BONUS,
    MAX_DAILY_BONUS,
    TOPIC_SUFFIX_DEDUCT,
    TOPIC_SUFFIX_PC_TIME_LEFT,
    TOPIC_SUFFIX_WEEKLY_BUDGET,
)

_LOGGER = logging.getLogger(__name__)

_TOPIC_ROOT = "timekpr"


class TimekprSyncCoordinator:
    """Owns budget state and all MQTT publish/subscribe wiring."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        data = {**entry.data, **entry.options}

        self.node_id = str(data.get(CONF_NODE_ID, DEFAULT_NODE_ID))
        self.weekly_budget = int(data.get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET))
        self.weekday_cap = int(data.get(CONF_WEEKDAY_CAP, DEFAULT_WEEKDAY_CAP))
        self.weekend_cap = int(data.get(CONF_WEEKEND_CAP, DEFAULT_WEEKEND_CAP))
        try:
            self.tv_presets = parse_presets(data.get(CONF_TV_PRESETS, DEFAULT_TV_PRESETS))
        except ValueError:
            self.tv_presets = parse_presets(DEFAULT_TV_PRESETS)

        # Runtime state
        self.balance: int = self.weekly_budget
        self.blocked: bool = False
        self.available: bool = False
        self.pc_time_left_seconds: int | None = None
        self.daily_bonus: int = 0

        # Entities to notify when state changes
        self.daily_bonus_entity = None
        self.number_entity = None
        self.switch_entity = None
        self.binary_sensor_entity = None
        self.sensor_entity = None

        self._topic = {
            TOPIC_SUFFIX_WEEKLY_BUDGET: self._full(TOPIC_SUFFIX_WEEKLY_BUDGET),
            TOPIC_SUFFIX_DEDUCT: self._full(TOPIC_SUFFIX_DEDUCT),
            TOPIC_SUFFIX_BLOCK_SET: self._full(TOPIC_SUFFIX_BLOCK_SET),
            TOPIC_SUFFIX_BLOCK_STATE: self._full(TOPIC_SUFFIX_BLOCK_STATE),
            TOPIC_SUFFIX_AVAILABLE: self._full(TOPIC_SUFFIX_AVAILABLE),
            TOPIC_SUFFIX_PC_TIME_LEFT: self._full(TOPIC_SUFFIX_PC_TIME_LEFT),
            TOPIC_SUFFIX_CAPS: self._full(TOPIC_SUFFIX_CAPS),
            TOPIC_SUFFIX_DAILY_BONUS: self._full(TOPIC_SUFFIX_DAILY_BONUS),
        }
        self._unsubs = []
        self._startup_reset = False
        self._stored: dict = {}
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    def _full(self, suffix: str) -> str:
        return f"{_TOPIC_ROOT}/{self.node_id}/{suffix}"

    @property
    def weekly_budget_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_WEEKLY_BUDGET]

    @property
    def deduct_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_DEDUCT]

    @property
    def blocked_set_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_BLOCK_SET]

    @property
    def blocked_state_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_BLOCK_STATE]

    @property
    def available_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_AVAILABLE]

    @property
    def pc_time_left_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_PC_TIME_LEFT]

    @property
    def caps_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_CAPS]

    @property
    def daily_bonus_topic(self) -> str:
        return self._topic[TOPIC_SUFFIX_DAILY_BONUS]

    async def _async_publish_caps(self) -> None:
        payload = json.dumps(
            {
                "weekday_cap_minutes": self.weekday_cap,
                "weekend_cap_minutes": self.weekend_cap,
            }
        )
        await mqtt.async_publish(self.hass, self.caps_topic, payload, qos=0, retain=True)

    async def async_init(self) -> None:
        """Subscribe to MQTT and schedule the Monday reset."""
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise ConfigEntryNotReady("MQTT is not available")

        await self._async_check_missed_reset()

        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, self.deduct_topic, self._on_deduct, qos=0
            )
        )
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, self.blocked_state_topic, self._on_blocked_state, qos=0
            )
        )
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, self.available_topic, self._on_available, qos=0
            )
        )
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass, self.pc_time_left_topic, self._on_pc_time_left, qos=0
            )
        )

        await self._async_publish_caps()
        await self._async_publish_daily_bonus()

        async def _midnight(now):
            await self._async_reset_daily_bonus()
            # weekday() == 0 means Monday
            if now.weekday() == 0:
                _LOGGER.info(
                    "Weekly screen-time budget reset to %s mins", self.weekly_budget
                )
                await self.async_set_balance(self.weekly_budget)
                await self._async_save_reset_week()

        self._unsubs.append(
            async_track_time_change(self.hass, _midnight, hour=0, minute=0, second=0)
        )

    @staticmethod
    def _current_week_key() -> str:
        year, week, _ = dt_util.now().isocalendar()
        return f"{year}-W{week:02d}"

    @staticmethod
    def _today() -> str:
        return dt_util.now().date().isoformat()

    async def _async_save_store(self) -> None:
        await self._store.async_save(self._stored)

    async def _async_save_reset_week(self) -> None:
        self._stored["reset_week"] = self._current_week_key()
        await self._async_save_store()

    async def _async_check_missed_reset(self) -> None:
        """Flag a reset if the stored week is older than this week (HA was down on Monday)."""
        self._stored = await self._store.async_load() or {}
        week = self._current_week_key()
        if "reset_week" not in self._stored:
            await self._async_save_reset_week()
        elif self._stored["reset_week"] != week:
            _LOGGER.info("Missed weekly reset detected; resetting budget to %s", self.weekly_budget)
            self._startup_reset = True
            await self._async_save_reset_week()

        if self._stored.get("daily_bonus_date") == self._today():
            self.daily_bonus = int(self._stored.get("daily_bonus", 0))

    def _today_cap(self) -> int:
        return self.weekday_cap if dt_util.now().weekday() < 5 else self.weekend_cap

    async def _async_publish_daily_bonus(self) -> None:
        payload = json.dumps({"minutes": self.daily_bonus, "date": self._today()})
        await mqtt.async_publish(
            self.hass, self.daily_bonus_topic, payload, qos=0, retain=True
        )

    async def async_adjust_daily(self, minutes: int) -> None:
        """Add (or remove) minutes for today only; the PC applies it on top of today's cap."""
        self.daily_bonus = max(
            -self._today_cap(), min(self.daily_bonus + int(minutes), MAX_DAILY_BONUS)
        )
        self._stored["daily_bonus"] = self.daily_bonus
        self._stored["daily_bonus_date"] = self._today()
        await self._async_save_store()
        await self._async_publish_daily_bonus()
        self._notify_daily_bonus()

    async def _async_reset_daily_bonus(self) -> None:
        self.daily_bonus = 0
        self._stored["daily_bonus"] = 0
        self._stored["daily_bonus_date"] = self._today()
        await self._async_save_store()
        await self._async_publish_daily_bonus()
        self._notify_daily_bonus()
    def consume_startup_reset(self) -> bool:
        """Return True once if the budget must be reset instead of restored."""
        pending, self._startup_reset = self._startup_reset, False
        return pending

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.node_id)},
            name=f"Timekpr {self.node_id}",
            manufacturer="Timekpr-nExT",
        )

    async def async_shutdown(self) -> None:
        """Unsubscribe from all listeners."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def async_set_balance(self, value: int) -> None:
        """Set the weekly balance (clamped) and publish to the PC; notify number entity."""
        self.balance = max(0, min(int(value), self.weekly_budget))
        await self._publish_balance()
        self._notify_number()

    async def async_deduct(self, minutes: int) -> None:
        """Deduct minutes from the weekly balance (from PC or TV)."""
        await self.async_set_balance(self.balance - int(minutes))

    async def async_add(self, minutes: int) -> None:
        """Add minutes back to the weekly balance."""
        await self.async_set_balance(self.balance + int(minutes))

    async def async_set_blocked(self, blocked: bool) -> None:
        """Publish a block/unblock command to the PC."""
        self.blocked = blocked
        payload = PAYLOAD_ON if blocked else PAYLOAD_OFF
        await mqtt.async_publish(self.hass, self.blocked_set_topic, payload, qos=0)
        self._notify_switch()

    async def _publish_balance(self) -> None:
        await mqtt.async_publish(
            self.hass,
            self.weekly_budget_topic,
            str(self.balance),
            qos=0,
            retain=True,
        )

    # ---- subscription callbacks ----

    @callback
    def _on_deduct(self, msg) -> None:
        try:
            minutes = int(msg.payload)
        except (ValueError, TypeError):
            return
        self.hass.async_create_task(self.async_deduct(minutes))

    @callback
    def _on_blocked_state(self, msg) -> None:
        payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
        self.blocked = payload == PAYLOAD_ON
        self._notify_switch()

    @callback
    def _on_available(self, msg) -> None:
        payload = msg.payload.decode() if isinstance(msg.payload, bytes) else str(msg.payload)
        self.available = payload == PAYLOAD_ONLINE
        self._notify_binary_sensor()
        if payload == PAYLOAD_OFFLINE:
            _LOGGER.warning("Timekpr PC agent went offline")

    @callback
    def _on_pc_time_left(self, msg) -> None:
        try:
            seconds = int(msg.payload)
        except (ValueError, TypeError):
            return
        self.pc_time_left_seconds = seconds
        self._notify_sensor()

    # ---- notify entities ----

    def _notify_number(self) -> None:
        if self.number_entity is not None:
            self.number_entity.async_write_ha_state()

    def _notify_switch(self) -> None:
        if self.switch_entity is not None:
            self.switch_entity.async_write_ha_state()

    def _notify_binary_sensor(self) -> None:
        if self.binary_sensor_entity is not None:
            self.binary_sensor_entity.async_write_ha_state()

    def _notify_sensor(self) -> None:
        if self.sensor_entity is not None:
            self.sensor_entity.async_write_ha_state()

    def _notify_daily_bonus(self) -> None:
        if self.daily_bonus_entity is not None:
            self.daily_bonus_entity.async_write_ha_state()
