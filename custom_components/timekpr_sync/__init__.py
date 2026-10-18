"""Timekpr Screen Time Sync Integration."""

import logging

DOMAIN = "timekpr_sync"
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    """Set up the integration via YAML or auto-load."""
    hass.async_create_task(
        hass.helpers.discovery.async_load_platform("number", DOMAIN, {}, config)
    )
    return True
