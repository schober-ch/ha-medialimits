"""Tests for integration setup and the TV-deduction services."""

from tests.conftest import number_value, published_topics, setup_integration


async def test_setup_creates_services(hass, mqtt_mock_async):
    await setup_integration(hass)
    assert hass.services.has_service("timekpr_sync", "deduct_tv_minutes")
    assert hass.services.has_service("timekpr_sync", "add_tv_minutes")


async def test_deduct_tv_minutes_service(hass, mqtt_mock_async):
    await setup_integration(hass)
    assert number_value(hass) == 300

    await hass.services.async_call(
        "timekpr_sync",
        "deduct_tv_minutes",
        {"minutes": 15},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert number_value(hass) == 285
    topics = dict(published_topics(mqtt_mock_async))
    assert topics.get("timekpr/child_pc/weekly_budget") == "285"


async def test_add_tv_minutes_service(hass, mqtt_mock_async):
    await setup_integration(hass)

    await hass.services.async_call(
        "timekpr_sync",
        "deduct_tv_minutes",
        {"minutes": 30},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert number_value(hass) == 270

    await hass.services.async_call(
        "timekpr_sync",
        "add_tv_minutes",
        {"minutes": 30},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert number_value(hass) == 300


async def test_deduct_tv_clamps_at_zero(hass, mqtt_mock_async):
    await setup_integration(hass)

    await hass.services.async_call(
        "timekpr_sync",
        "deduct_tv_minutes",
        {"minutes": 999},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert number_value(hass) == 0


async def test_caps_published_retained_on_setup(hass, mqtt_mock_async):
    await setup_integration(hass)
    calls = [c for c in mqtt_mock_async.async_publish.call_args_list if c.args[0] == "timekpr/child_pc/caps"]
    assert len(calls) == 1
    assert calls[0].args[1] == '{"weekday_cap_minutes": 30, "weekend_cap_minutes": 90}'
    assert calls[0].args[3] is True
