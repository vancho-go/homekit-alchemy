"""Executing commands as Home Assistant actions."""

from __future__ import annotations

from collections.abc import Iterable
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.template import Template, render_complex

from ..model.binding import Command

_LOGGER = logging.getLogger(__name__)


@callback
def async_execute(
    hass: HomeAssistant, commands: Iterable[Command], variables: dict[str, Any] | None = None
) -> None:
    """Fire commands without blocking the HAP request (Apple expects a fast reply)."""
    for command in commands:
        merged = {**(variables or {}), **command.variables}
        hass.async_create_task(_async_call(hass, command, merged), eager_start=True)


EVENT_PREFIX = "event:"


async def _async_call(hass: HomeAssistant, command: Command, variables: dict[str, Any]) -> None:
    target = _render(hass, command.target, variables)
    data = _render(hass, command.data, variables)
    if command.action.startswith(EVENT_PREFIX):
        event_type = command.action.removeprefix(EVENT_PREFIX)
        _LOGGER.debug("Firing %s %s", event_type, data)
        hass.bus.async_fire(event_type, data)
        return
    _LOGGER.debug("Calling %s target=%s data=%s", command.action, target, data)
    try:
        await hass.services.async_call(
            command.domain, command.service, data, blocking=True, target=target or None
        )
    except (HomeAssistantError, ValueError) as err:
        _LOGGER.error("Action %s failed: %s", command.action, err)


def _render(hass: HomeAssistant, value: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    templated = _attach(hass, value)
    return render_complex(templated, variables)


def _attach(hass: HomeAssistant, value: Any) -> Any:
    if isinstance(value, str) and "{" in value:
        return Template(value, hass)
    if isinstance(value, dict):
        return {k: _attach(hass, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_attach(hass, v) for v in value]
    return value
