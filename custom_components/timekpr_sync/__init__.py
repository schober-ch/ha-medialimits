"""Timekpr Screen Time Sync integration.

Modern config-entry integration:
- async_setup_entry / async_unload_entry lifecycle
- Forwards the entry to the number, switch, binary_sensor and sensor platforms
- Registers the deduct_tv_minutes / add_tv_minutes services once per domain
"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_NODE_ID, DOMAIN, SERVICE_ADD_TV, SERVICE_DEDUCT_TV
from .coordinator import TimekprSyncCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]

_SCHEMA_MINUTES = vol.Schema(
    {
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional(CONF_NODE_ID): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    coordinator = TimekprSyncCoordinator(hass, entry)
    await coordinator.async_init()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: TimekprSyncCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    if not hass.data.get(DOMAIN):
        _async_remove_services(hass)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _resolve_coordinator(
    hass: HomeAssistant, node_id: str | None
) -> TimekprSyncCoordinator:
    """Pick the coordinator for a service call (by node_id, or the only one loaded)."""
    coordinators: dict[str, TimekprSyncCoordinator] = hass.data.get(DOMAIN, {})
    if node_id is not None:
        for coordinator in coordinators.values():
            if coordinator.node_id == node_id:
                return coordinator
        raise HomeAssistantError(f"No Timekpr Sync entry for node_id '{node_id}'")
    if len(coordinators) == 1:
        return next(iter(coordinators.values()))
    raise HomeAssistantError("Multiple PCs configured; specify node_id")


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the TV-deduction services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_DEDUCT_TV):
        return

    async def _handle_deduct(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call.data.get(CONF_NODE_ID))
        await coordinator.async_deduct(int(call.data["minutes"]))

    async def _handle_add(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call.data.get(CONF_NODE_ID))
        await coordinator.async_add(int(call.data["minutes"]))

    hass.services.async_register(
        DOMAIN, SERVICE_DEDUCT_TV, _handle_deduct, _SCHEMA_MINUTES
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_TV, _handle_add, _SCHEMA_MINUTES)


def _async_remove_services(hass: HomeAssistant) -> None:
    """Remove the services when the last config entry unloads."""
    hass.services.async_remove(DOMAIN, SERVICE_DEDUCT_TV)
    hass.services.async_remove(DOMAIN, SERVICE_ADD_TV)
