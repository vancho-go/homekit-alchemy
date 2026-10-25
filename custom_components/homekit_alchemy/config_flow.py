"""Config flow for HomeKit Alchemy: one entry per bridge; devices come from YAML."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DEFAULT_NAME, DOMAIN


class AlchemyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the bridge entry from the UI or from `homekit_alchemy:` in YAML."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title=DEFAULT_NAME, data={})

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry automatically when `homekit_alchemy:` is in configuration.yaml."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=DEFAULT_NAME, data={})
