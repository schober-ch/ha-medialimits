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
    """Add the PC time-left sensor."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entity = PcTimeLeftSensor(coordinator)
    coordinator.sensor_entity = entity
    async_add_entities([entity])


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

    @property
    def native_value(self) -> int | None:
        """Return the PC time left in minutes (rounded up)."""
        seconds = self._coordinator.pc_time_left_seconds
        if seconds is None:
            return None
        return max(0, (seconds + 59) // 60)
