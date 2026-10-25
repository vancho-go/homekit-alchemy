"""Small value converters shared by presets."""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


TRUE_STATES = {"on", "true", "open", "opening", "detected", "home", "wet", "unlocked", "1"}
FALSE_STATES = {"off", "false", "closed", "closing", "clear", "not_home", "dry", "locked", "0"}


def to_bool(value: Any) -> bool | None:
    """Interpret an HA state / attribute / template result as on/off; None if unknown."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_STATES:
            return True
        if text in FALSE_STATES:
            return False
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fahrenheit_to_celsius(value: float) -> float:
    return (value - 32) * 5 / 9


def celsius_to_fahrenheit(value: float) -> float:
    return value * 9 / 5 + 32


def kelvin_to_mired(kelvin: float) -> int:
    return round(1_000_000 / kelvin)


def mired_to_kelvin(mired: float) -> int:
    return round(1_000_000 / mired)


def brightness_to_percent(brightness: float) -> int:
    """HA brightness 0..255 -> Apple 0..100 (never 0 for a light that is on)."""
    return max(1, round(brightness / 255 * 100))
