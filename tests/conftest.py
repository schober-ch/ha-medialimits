"""Shared fixtures for Timekpr Sync integration tests.

Uses pytest-homeassistant-custom-component's `hass`, `enable_custom_integrations`
and `mqtt_mock` fixtures.
"""

import pytest

from homeassistant import config_entries

from custom_components.timekpr_sync import DOMAIN


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """HA's MQTT subscription debouncer leaves a timer behind; it is not ours."""
    return True


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations):
    """Make the custom_components/timekpr_sync package importable in every test."""
    yield


@pytest.fixture(autouse=True)
async def _cleanup_integration(hass):
    """Unload all config entries after each test to release timers/subscriptions."""
    yield
    for entry in list(hass.config_entries.async_entries()):
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
async def mqtt_mock_async(hass, mqtt_mock):
    """Provide the mocked MQTT client (captures publishes/subscribes)."""
    return mqtt_mock


async def setup_integration(hass, config=None):
    """Create a config entry and set up the integration."""
    if config is None:
        config = {"node_id": "child_pc", "weekly_budget": 300}
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Timekpr",
        data=config,
        source="user",
        entry_id="test_entry",
        options={},
        discovery_keys={},
        unique_id=None,
    )
    await hass.config_entries.async_add(entry)
    await hass.async_block_till_done()
    return entry


def published_topics(mqtt_mock):
    """Return a list of (topic, payload) tuples captured by the mocked MQTT client."""
    out = []
    for call in mqtt_mock.async_publish.call_args_list:
        topic = call.args[0]
        payload = call.args[1] if len(call.args) > 1 else call.kwargs.get("payload")
        out.append((topic, str(payload)[2:-1] if isinstance(payload, bytes) else str(payload)))
    return out


def number_value(hass) -> float | None:
    """Return the weekly number entity's numeric value, or None if not present."""
    state = hass.states.get("number.weekly_screen_time_left_child_pc")
    if state is None:
        return None
    return float(state.state)
