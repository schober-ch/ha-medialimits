"""TV-time buttons: deduct or give back a preset number of minutes."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import BUTTON_UNIQUE_ID, DOMAIN
from .coordinator import TimekprSyncCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Add a deduct and an add button for every configured preset."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[TvTimeButton] = []
    for minutes in coordinator.tv_presets:
        entities.append(TvTimeButton(coordinator, minutes, deduct=True))
        entities.append(TvTimeButton(coordinator, minutes, deduct=False))
    async_add_entities(entities)


class TvTimeButton(ButtonEntity):
    """Deducts from, or adds back to, the weekly budget when pressed."""

    _attr_should_poll = False

    def __init__(
        self, coordinator: TimekprSyncCoordinator, minutes: int, *, deduct: bool
    ) -> None:
        self._coordinator = coordinator
        self._minutes = minutes
        self._deduct = deduct
        node = coordinator.node_id
        action = "deduct" if deduct else "add"
        self._attr_name = f"TV {action.capitalize()} {minutes} min ({node})"
        self._attr_unique_id = f"{BUTTON_UNIQUE_ID}_{action}_{minutes}_{node}"
        self._attr_icon = "mdi:television-off" if deduct else "mdi:undo"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        if self._deduct:
            await self._coordinator.async_deduct(self._minutes)
        else:
            await self._coordinator.async_add(self._minutes)
