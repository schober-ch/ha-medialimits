"""Config flow for the Timekpr Screen Time Sync integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import (
    CONF_NODE_ID,
    CONF_TV_PRESETS,
    CONF_WEEKDAY_CAP,
    CONF_WEEKEND_CAP,
    CONF_WEEKLY_BUDGET,
    DEFAULT_NODE_ID,
    DEFAULT_TV_PRESETS,
    DEFAULT_WEEKDAY_CAP,
    DEFAULT_WEEKEND_CAP,
    DEFAULT_WEEKLY_BUDGET,
    DOMAIN,
    parse_presets,
)


class TimekprSyncConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Timekpr Sync."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial user step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                parse_presets(user_input.get(CONF_TV_PRESETS, DEFAULT_TV_PRESETS))
            except ValueError:
                errors[CONF_TV_PRESETS] = "invalid_presets"
            else:
                return self.async_create_entry(
                    title=f"Timekpr {user_input.get(CONF_NODE_ID, DEFAULT_NODE_ID)}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NODE_ID, default=DEFAULT_NODE_ID): str,
                    vol.Optional(
                        CONF_WEEKLY_BUDGET, default=DEFAULT_WEEKLY_BUDGET
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_WEEKDAY_CAP, default=DEFAULT_WEEKDAY_CAP
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_WEEKEND_CAP, default=DEFAULT_WEEKEND_CAP
                    ): vol.Coerce(int),
                    vol.Optional(CONF_TV_PRESETS, default=DEFAULT_TV_PRESETS): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this integration."""
        return TimekprSyncOptionsFlow()


class TimekprSyncOptionsFlow(config_entries.OptionsFlow):
    """Edit the weekly budget and daily caps for an existing entry."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            errors: dict[str, str] = {}
            if user_input[CONF_WEEKLY_BUDGET] < 1:
                errors[CONF_WEEKLY_BUDGET] = "invalid_budget"
            try:
                parse_presets(user_input.get(CONF_TV_PRESETS, DEFAULT_TV_PRESETS))
            except ValueError:
                errors[CONF_TV_PRESETS] = "invalid_presets"
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors=errors,
                )
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=self._schema(dict(self.config_entry.data))
        )

    def _schema(self, current: dict) -> vol.Schema:
        cur = {**current, **self.config_entry.options}
        return vol.Schema(
            {
                vol.Optional(
                    CONF_WEEKLY_BUDGET,
                    default=int(cur.get(CONF_WEEKLY_BUDGET, DEFAULT_WEEKLY_BUDGET)),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_WEEKDAY_CAP,
                    default=int(cur.get(CONF_WEEKDAY_CAP, DEFAULT_WEEKDAY_CAP)),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_WEEKEND_CAP,
                    default=int(cur.get(CONF_WEEKEND_CAP, DEFAULT_WEEKEND_CAP)),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_TV_PRESETS,
                    default=str(cur.get(CONF_TV_PRESETS, DEFAULT_TV_PRESETS)),
                ): str,
            }
        )

