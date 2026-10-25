"""HomeKit Alchemy: expose composite Home Assistant devices to Apple Home."""

from __future__ import annotations

import glob
import os

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
import probatio as vol

from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .builder import build_devices
from .config.models import AlchemyConfig
from .config.schema import CONFIG_SCHEMA, alchemy_config
from .const import DOMAIN
from .manager import BridgeManager

__all__ = ["CONFIG_SCHEMA"]

type AlchemyConfigEntry = ConfigEntry[BridgeManager]

DATA_CONFIG = f"{DOMAIN}_config"
SERVICE_RELOAD = "reload"
SERVICE_RESET_ACCESSORY = "reset_accessory"
SERVICE_UNPAIR = "unpair"

RESET_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_ids})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Read YAML, create the config entry on first run, register homekit_alchemy.reload."""
    hass.data[DATA_CONFIG] = config.get(DOMAIN)
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={})
        )

    async def _async_reload(_call: ServiceCall) -> None:
        # Raises (and shows the error in the UI) if the new YAML is invalid; old config keeps running.
        new = await async_integration_yaml_config(hass, DOMAIN, raise_on_failure=True)
        hass.data[DATA_CONFIG] = new.get(DOMAIN)
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_reload(entry.entry_id)

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_reload)

    async def _async_reset_accessory(call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_reset_accessories(call.data["entity_id"])

    hass.services.async_register(DOMAIN, SERVICE_RESET_ACCESSORY, _async_reset_accessory, schema=RESET_SCHEMA)

    async def _async_unpair(_call: ServiceCall) -> None:
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            entry.runtime_data.async_unpair()

    hass.services.async_register(DOMAIN, SERVICE_UNPAIR, _async_unpair)
    return True


def _current_config(hass: HomeAssistant) -> AlchemyConfig:
    return hass.data.get(DATA_CONFIG) or alchemy_config({})


async def async_setup_entry(hass: HomeAssistant, entry: AlchemyConfigEntry) -> bool:
    """Set up a HomeKit Alchemy bridge from a config entry."""
    config = _current_config(hass)
    manager = entry.runtime_data = BridgeManager(
        hass,
        entry.entry_id,
        name=config.name,
        port=config.port,
        build_devices=lambda hass: build_devices(hass, config),
    )

    async def _async_start(_hass: HomeAssistant) -> None:
        await manager.async_start()

    async def _async_on_hass_stop(_event: Event) -> None:
        await manager.async_stop()

    entry.async_on_unload(async_at_started(hass, _async_start))
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_on_hass_stop)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AlchemyConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: AlchemyConfigEntry) -> None:
    """Delete pairing state and id allocations of the bridge and its standalone accessories."""
    pattern = hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}.*")

    def _remove() -> None:
        for path in glob.glob(pattern):
            os.remove(path)

    await hass.async_add_executor_job(_remove)
