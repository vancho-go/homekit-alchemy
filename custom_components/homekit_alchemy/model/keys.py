"""Stable keys for devices and blocks.

Apple caches services by their numeric ids; those ids are derived from these
keys, so a key must describe what a block *is*, never where it is in a list.
"""

from __future__ import annotations

import re

MAIN = "main"


def device_key(entity_id: str, unique_id: str | None) -> str:
    """Prefer the registry unique_id: it survives entity renames."""
    return f"uid:{unique_id}" if unique_id else f"eid:{entity_id}"


def sensor_key(sensor_type: str, entity_id: str | None = None) -> str:
    """Sensor block key; pass entity_id only to disambiguate same-type sensors."""
    return f"sensor:{sensor_type}" + (f":{entity_id}" if entity_id else "")


def extra_key(
    kind: str, *, block_id: str | None = None, entity_id: str | None = None, name: str | None = None
) -> str:
    """Key of a user-defined block (switch, range, mode…): explicit id > entity > name."""
    if block_id:
        return f"{kind}:id:{block_id}"
    if entity_id:
        return f"{kind}:entity:{entity_id}"
    if name:
        return f"{kind}:name:{slugify(name)}"
    raise ValueError(f"{kind} block needs an id, an entity or a name")


def switch_key(*, block_id: str | None = None, entity_id: str | None = None, name: str | None = None) -> str:
    return extra_key("switch", block_id=block_id, entity_id=entity_id, name=name)


def slugify(text: str) -> str:
    return re.sub(r"[^\w]+", "_", text.strip().lower()).strip("_")
