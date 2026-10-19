"""TV-time and today's-time buttons for the preset minutes."""

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
    """Add weekly (TV) and daily (Today) add/deduct buttons for every preset."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[PresetButton] = []
    for minutes in coordinator.tv_presets:
        for daily in (False, True):
            entities.append(PresetButton(coordinator, minutes, deduct=True, daily=daily))
            entities.append(PresetButton(coordinator, minutes, deduct=False, daily=daily))
    async_add_entities(entities)


class PresetButton(ButtonEntity):
    """Changes the weekly budget (TV) or today's allowance (Today) by a preset amount."""

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TimekprSyncCoordinator,
        minutes: int,
        *,
        deduct: bool,
        daily: bool,
    ) -> None:
        self._coordinator = coordinator
        self._minutes = minutes
        self._deduct = deduct
        self._daily = daily
        node = coordinator.node_id
        scope = "Today" if daily else "TV"
        action = "deduct" if deduct else "add"
        self._attr_name = f"{scope} {action.capitalize()} {minutes} min ({node})"
        if daily:
            self._attr_unique_id = f"{BUTTON_UNIQUE_ID}_today_{action}_{minutes}_{node}"
            self._attr_icon = "mdi:clock-minus-outline" if deduct else "mdi:clock-plus-outline"
        else:
            self._attr_unique_id = f"{BUTTON_UNIQUE_ID}_{action}_{minutes}_{node}"
            self._attr_icon = "mdi:television-off" if deduct else "mdi:undo"
        self._attr_device_info = coordinator.device_info

    async def async_press(self) -> None:
        if self._daily:
            delta = -self._minutes if self._deduct else self._minutes
            await self._coordinator.async_adjust_daily(delta)
        elif self._deduct:
            await self._coordinator.async_deduct(self._minutes)
        else:
            await self._coordinator.async_add(self._minutes)
