"""Virtual devices: what Apple Home will see."""

from __future__ import annotations

from dataclasses import dataclass, field

from .behavior import Behavior
from .binding import Source


@dataclass
class Block:
    """One Apple service inside a device, e.g. a lightbulb or a temperature sensor."""

    key: str  # stable within the device, see keys.py
    kind: str  # Apple service type, e.g. "Lightbulb"
    name: str
    behavior: Behavior
    primary: bool = False
    linked: tuple[str, ...] = ()  # keys of blocks shown as part of this one (e.g. a fan)


@dataclass
class Device:
    """One card in Apple Home, built around a main Home Assistant entity."""

    key: str  # stable across renames (registry unique_id when available)
    entity_id: str
    name: str
    category: str  # icon / accessory category, e.g. "lightbulb"
    blocks: list[Block] = field(default_factory=list)
    standalone: bool = False  # own pairing instead of living in the bridge (needed for TVs)

    def __post_init__(self) -> None:
        keys = [block.key for block in self.blocks]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate block keys in device {self.entity_id}: {keys}")
        for block in self.blocks:
            if missing := set(block.linked) - set(keys):
                raise ValueError(f"Block {block.key} links to unknown blocks {missing}")

    def sources(self) -> list[Source]:
        seen: dict[Source, None] = {}
        for block in self.blocks:
            for source in block.behavior.sources():
                seen.setdefault(source)
        return list(seen)
