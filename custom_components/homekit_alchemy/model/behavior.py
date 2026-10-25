"""Interfaces between the model and the outside world."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from .binding import Command, Source

UNAVAILABLE = "unavailable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class StateSnapshot:
    """Minimal view of a Home Assistant state."""

    state: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        """Has a usable value (behaviors skip unknown values)."""
        return self.state not in (UNAVAILABLE, UNKNOWN)

    @property
    def reachable(self) -> bool:
        """The device answers; 'unknown' is a valid state (e.g. a never-used scene)."""
        return self.state != UNAVAILABLE


class StateView(Protocol):
    """Read access to Home Assistant, implemented by the runtime layer."""

    def state(self, entity_id: str) -> StateSnapshot | None:
        """Return the current state of an entity, or None if it does not exist."""

    def value(self, source: Source) -> Any:
        """Return the raw value of a source (state, attribute or rendered template)."""


@dataclass(frozen=True)
class FieldSpec:
    """A characteristic exposed by a block, e.g. Brightness with its limits."""

    kind: str
    properties: Mapping[str, Any] = field(default_factory=dict)


class Behavior(ABC):
    """Logic of one block: which fields it has and how they map to Home Assistant."""

    @abstractmethod
    def fields(self) -> list[FieldSpec]:
        """Characteristics of the block (besides Name/ConfiguredName)."""

    @abstractmethod
    def sources(self) -> list[Source]:
        """Everything the block reads; the runtime subscribes to these."""

    @abstractmethod
    def compute(self, view: StateView) -> dict[str, Any]:
        """Current Apple values by field kind. Omit fields whose value is unknown."""

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        """Turn values written from Apple Home into Home Assistant actions."""
        return []
