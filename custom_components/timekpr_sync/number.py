"""Weekly screen-time balance number entity (master of the budget).

The native value lives in the coordinator (single source of truth). This entity simply mirrors it
and is restored from HA state on startup.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    NUMBER_ICON,
    NUMBER_NAME,
    NUMBER_UNIQUE_ID,
    NUMBER_UNIT,
)
from .coordinator import TimekprSyncCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Add the weekly screen-time number entity."""
    coordinator: TimekprSyncCoordinator = hass.data[DOMAIN][entry.entry_id]
    entity = WeeklyScreenTimeNumber(coordinator)
    coordinator.number_entity = entity
    async_add_entities([entity])


class WeeklyScreenTimeNumber(RestoreNumber):
    """Represents the master weekly balance slider."""

    def __init__(self, coordinator: TimekprSyncCoordinator) -> None:
        """Initialize the number with values from the coordinator."""
        self._coordinator = coordinator
        node = coordinator.node_id
        self._attr_name = f"{NUMBER_NAME} ({node})"
        self._attr_unique_id = f"{NUMBER_UNIQUE_ID}_{node}"
        self._attr_native_min_value = 0
        self._attr_native_max_value = coordinator.weekly_budget
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = NUMBER_UNIT
        self._attr_icon = NUMBER_ICON
        self._attr_should_poll = False
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> float:
        """Return the current balance."""
        return float(self._coordinator.balance)

    async def async_set_native_value(self, value: float) -> None:
        """Adjust the weekly balance and push it to the PC."""
        await self._coordinator.async_set_balance(int(value))

    async def async_added_to_hass(self) -> None:
        """Restore the last value after a restart, then broadcast to the PC."""
        await super().async_added_to_hass()
        if self._coordinator.consume_startup_reset():
            await self._coordinator.async_set_balance(self._coordinator.weekly_budget)
            return
        last = await self.async_get_last_number_data()
        restored = None
        if last is not None and last.native_value is not None:
            restored = int(last.native_value)
            _LOGGER.debug("Restored weekly balance to %s mins", restored)
        await self._coordinator.async_set_balance(
            restored if restored is not None else self._coordinator.balance
        )
