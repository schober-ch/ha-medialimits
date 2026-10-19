"""Tests for the emergency block switch."""

from tests.conftest import published_topics, setup_integration


def _switch_state(hass):
    return hass.states.get("switch.block_pc_access_child_pc")


def _get_sub_callback(mqtt_mock, topic):
    for call in mqtt_mock.async_subscribe.call_args_list:
        if call.args[0] == topic:
            return call.args[1]
    return None


async def test_switch_registers(hass, mqtt_mock_async):
    await setup_integration(hass)
    state = _switch_state(hass)
    assert state is not None
    assert state.state == "off"


async def test_turn_on_publishes_block_command(hass, mqtt_mock_async):
    await setup_integration(hass)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.block_pc_access_child_pc"},
        blocking=True,
    )
    await hass.async_block_till_done()

    topics = dict(published_topics(mqtt_mock_async))
    assert topics.get("timekpr/child_pc/blocked/set") == "ON"


async def test_turn_off_publishes_unblock_command(hass, mqtt_mock_async):
    await setup_integration(hass)

    # Block first.
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.block_pc_access_child_pc"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.block_pc_access_child_pc"},
        blocking=True,
    )
    await hass.async_block_till_done()

    topics = dict(published_topics(mqtt_mock_async))
    assert topics.get("timekpr/child_pc/blocked/set") == "OFF"


async def test_switch_reflects_blocked_state(hass, mqtt_mock_async):
    await setup_integration(hass)
    assert _switch_state(hass).state == "off"

    callback = _get_sub_callback(mqtt_mock_async, "timekpr/child_pc/blocked/state")
    assert callback is not None

    # The PC confirms it is blocked.
    msg = type("Msg", (), {"topic": "timekpr/child_pc/blocked/state", "payload": b"ON"})()
    callback(msg)
    await hass.async_block_till_done()

    assert _switch_state(hass).state == "on"
