"""Tests for the TV-time buttons."""

from homeassistant.config_entries import ConfigEntryState

from tests.conftest import number_value, published_topics, setup_integration


async def _press(hass, entity_id):
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def test_default_buttons_registered(hass, mqtt_mock_async):
    await setup_integration(hass)
    for entity_id in (
        "button.tv_deduct_15_min_child_pc",
        "button.tv_add_15_min_child_pc",
        "button.tv_deduct_30_min_child_pc",
        "button.tv_add_30_min_child_pc",
    ):
        assert hass.states.get(entity_id) is not None, entity_id


async def test_deduct_button_reduces_budget(hass, mqtt_mock_async):
    await setup_integration(hass)
    await _press(hass, "button.tv_deduct_15_min_child_pc")

    assert number_value(hass) == 285
    assert dict(published_topics(mqtt_mock_async)).get("timekpr/child_pc/weekly_budget") == "285"


async def test_add_button_gives_back_minutes(hass, mqtt_mock_async):
    await setup_integration(hass)
    await _press(hass, "button.tv_deduct_30_min_child_pc")
    assert number_value(hass) == 270

    await _press(hass, "button.tv_add_30_min_child_pc")
    assert number_value(hass) == 300


async def test_custom_presets(hass, mqtt_mock_async):
    entry = await setup_integration(
        hass, {"node_id": "child_pc", "weekly_budget": 300, "tv_presets": "10, 45"}
    )
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("button.tv_deduct_10_min_child_pc") is not None
    assert hass.states.get("button.tv_add_45_min_child_pc") is not None
    assert hass.states.get("button.tv_deduct_15_min_child_pc") is None


async def test_invalid_presets_fall_back_to_default(hass, mqtt_mock_async):
    await setup_integration(
        hass, {"node_id": "child_pc", "weekly_budget": 300, "tv_presets": "abc"}
    )
    assert hass.states.get("button.tv_deduct_15_min_child_pc") is not None


def test_parse_presets():
    import pytest

    from custom_components.timekpr_sync.const import parse_presets

    assert parse_presets("15,30") == [15, 30]
    assert parse_presets(" 30 , 15,30 ") == [30, 15]
    for bad in ("", " , ", "0", "-5", "abc", "15,x"):
        with pytest.raises(ValueError):
            parse_presets(bad)
