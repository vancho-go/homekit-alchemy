"""Default names of blocks the presets add, in the Home Assistant language."""

from __future__ import annotations

NAMES: dict[str, dict[str, str]] = {
    "en": {"fan": "Fan", "volume": "Volume"},
    "ru": {"fan": "Вентилятор", "volume": "Громкость"},
}


def block_name(key: str, language: str | None) -> str:
    """Name for `key`; falls back to English for unknown languages."""
    lang = (language or "en").split("-")[0].lower()
    return NAMES.get(lang, NAMES["en"]).get(key) or NAMES["en"][key]
