"""Config flow for the Jandy TCX integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, DOMAIN
from .coordinator import TCXApiError, TCXClient

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class TCXConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jandy TCX."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            self._async_abort_entries_match({CONF_HOST: host, CONF_PORT: port})

            session = async_get_clientsession(self.hass)
            client = TCXClient(session, host, port)
            try:
                await client.async_get_status()
            except TCXApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Jandy TCX ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
