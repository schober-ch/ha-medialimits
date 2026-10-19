"""PC time-left sensor (fed by the `pc_time_left` MQTT topic)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SENSOR_ICON,
    SENSOR_NAME,
    SENSOR_UNIQUE_ID,
    SENSOR_UNIT,
)
from .coordinator import TimekprSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Add the PC time-left and today's-bonus sensors."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entity = PcTimeLeftSensor(coordinator)
    coordinator.sensor_entity = entity
    bonus = DailyBonusSensor(coordinator)
    coordinator.daily_bonus_entity = bonus
    async_add_entities([entity, bonus])


class DailyBonusSensor(SensorEntity):
    """Minutes added to (or removed from) today's allowance; resets at midnight."""

    _attr_should_poll = False
    _attr_icon = "mdi:clock-plus-outline"
    _attr_native_unit_of_measurement = SENSOR_UNIT

    def __init__(self, coordinator: TimekprSyncCoordinator) -> None:
        self._coordinator = coordinator
        node = coordinator.node_id
        self._attr_name = f"Daily Bonus Today ({node})"
        self._attr_unique_id = f"timekpr_daily_bonus_{node}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int:
        return self._coordinator.daily_bonus


class PcTimeLeftSensor(SensorEntity):
    """Live PC time remaining, reported by the agent as raw seconds."""

    _attr_should_poll = False
    _attr_icon = SENSOR_ICON
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = SENSOR_UNIT

    def __init__(self, coordinator: TimekprSyncCoordinator) -> None:
        """Set up identification from the coordinator's node id."""
        self._coordinator = coordinator
        node = coordinator.node_id
        self._attr_name = f"{SENSOR_NAME} ({node})"
        self._attr_unique_id = f"{SENSOR_UNIQUE_ID}_{node}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> int | None:
        """Return the PC time left in minutes (rounded up)."""
        seconds = self._coordinator.pc_time_left_seconds
        if seconds is None:
            return None
        return max(0, (seconds + 59) // 60)
