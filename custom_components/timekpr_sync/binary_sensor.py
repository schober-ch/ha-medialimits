"""PC agent online binary sensor (fed by the `available` MQTT topic)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import BINARY_SENSOR_NAME, BINARY_SENSOR_UNIQUE_ID, DOMAIN
from .coordinator import TimekprSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Add the PC online binary sensor."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entity = PcOnlineBinarySensor(coordinator)
    coordinator.binary_sensor_entity = entity
    async_add_entities([entity])


class PcOnlineBinarySensor(BinarySensorEntity):
    """Whether the PC agent is connected."""

    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: TimekprSyncCoordinator) -> None:
        """Set up identification from the coordinator's node id."""
        self._coordinator = coordinator
        node = coordinator.node_id
        self._attr_name = f"{BINARY_SENSOR_NAME} ({node})"
        self._attr_unique_id = f"{BINARY_SENSOR_UNIQUE_ID}_{node}"

    @property
    def is_on(self) -> bool:
        """Return whether the agent is reporting online."""
        return self._coordinator.available
