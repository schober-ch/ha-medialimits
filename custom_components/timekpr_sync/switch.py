"""Emergency block switch for the PC (emergency lockout)."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SWITCH_ICON,
    SWITCH_NAME,
    SWITCH_UNIQUE_ID,
)
from .coordinator import TimekprSyncCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Add the block-PC-access switch entity."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entity = BlockPcSwitch(coordinator)
    coordinator.switch_entity = entity
    async_add_entities([entity])


class BlockPcSwitch(SwitchEntity):
    """Emergency lockout switch that tells the PC to set its time left to 0."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, coordinator: TimekprSyncCoordinator) -> None:
        """Store a reference to the coordinator and set identification."""
        self._coordinator = coordinator
        node = coordinator.node_id
        self._attr_name = f"{SWITCH_NAME} ({node})"
        self._attr_unique_id = f"{SWITCH_UNIQUE_ID}_{node}"
        self._attr_icon = SWITCH_ICON
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return the block state reported by the PC agent."""
        return self._coordinator.blocked

    async def async_turn_on(self, **kwargs) -> None:
        """Publish an ON command to the PC to lock it immediately."""
        await self._coordinator.async_set_blocked(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Publish an OFF command to let the PC restore its allowance."""
        await self._coordinator.async_set_blocked(False)
