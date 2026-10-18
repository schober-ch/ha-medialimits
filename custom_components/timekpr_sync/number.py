"""Weekly screen time number slider with automatic MQTT sync and weekly reset."""

import logging
from homeassistant.components.number import RestoreNumber
from homeassistant.components import mqtt
from homeassistant.helpers.event import async_track_time_change
import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

DEFAULT_WEEKLY_MINUTES = 300
TOPIC_DEDUCT = "kids_pc/deduct_pc_minutes"
TOPIC_SET_BUDGET = "kids_pc/weekly_budget/set"


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Add the Weekly Screen Time number entity."""
    entity = WeeklyScreenTimeNumber(hass)
    async_add_entities([entity])


class WeeklyScreenTimeNumber(RestoreNumber):
    """Represents the master weekly balance slider."""

    def __init__(self, hass):
        self.hass = hass
        self._attr_name = "Weekly Screen Time Left"
        self._attr_unique_id = "timekpr_weekly_screen_time_left"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 300
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:timer-sand"
        self._attr_native_value = DEFAULT_WEEKLY_MINUTES

    async def async_added_to_hass(self):
        """Restore state on startup, register MQTT listeners, and set reset timer."""
        await super().async_added_to_hass()

        # 1. Restore previous value after Home Assistant restart
        last_state = await self.async_get_last_number_data()
        if last_state and last_state.native_value is not None:
            self._attr_native_value = int(last_state.native_value)
        else:
            self._attr_native_value = DEFAULT_WEEKLY_MINUTES

        # Broadcast current budget to the PC immediately
        await self._publish_to_pc(self._attr_native_value)

        # 2. MQTT Listener (Replaces Automation A: Deduct PC Time)
        async def handle_deduct_message(msg):
            try:
                spent = int(msg.payload)
                new_val = max(0, int(self._attr_native_value) - spent)
                await self.async_set_native_value(new_val)
            except ValueError:
                pass

        await mqtt.async_subscribe(self.hass, TOPIC_DEDUCT, handle_deduct_message)

        # 3. Monday Midnight Timer (Replaces Automation C: Weekly Reset)
        async def handle_monday_reset(now):
            # 0 = Monday in Python's weekday()
            if now.weekday() == 0:
                _LOGGER.info(
                    "Resetting weekly screen time allowance to %s mins",
                    DEFAULT_WEEKLY_MINUTES,
                )
                await self.async_set_native_value(DEFAULT_WEEKLY_MINUTES)

        async_track_time_change(
            self.hass, handle_monday_reset, hour=0, minute=0, second=0
        )

    async def async_set_native_value(self, value: float) -> None:
        """Update slider value and notify PC (Replaces Automation B)."""
        self._attr_native_value = int(value)
        self.async_write_ha_state()

        # Push updated budget to PC so it can clamp playtime if needed
        await self._publish_to_pc(int(value))

    async def _publish_to_pc(self, minutes: int):
        """Send budget to MQTT."""
        await mqtt.async_publish(self.hass, TOPIC_SET_BUDGET, str(minutes), retain=True)
