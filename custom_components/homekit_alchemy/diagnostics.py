"""Diagnostics download: bridge, accessories, blocks and current Apple values."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import AlchemyConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: AlchemyConfigEntry) -> dict[str, Any]:
    """Pairing codes, client keys and lock/alarm codes are never included."""
    return entry.runtime_data.diagnostics()
