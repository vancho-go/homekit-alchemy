"""Test doubles shared by unit tests."""

from __future__ import annotations

from typing import Any

from custom_components.homekit_alchemy.model.behavior import StateSnapshot
from custom_components.homekit_alchemy.model.binding import Source


class FakeView:
    """StateView over a plain dict: {entity_id: (state, attributes)}."""

    def __init__(self, states: dict[str, tuple[str, dict[str, Any]]] | None = None) -> None:
        self.states = states or {}
        self.templates: dict[str, Any] = {}

    def set(self, entity_id: str, state: str, attributes: dict[str, Any] | None = None) -> None:
        self.states[entity_id] = (state, attributes or {})

    def state(self, entity_id: str) -> StateSnapshot | None:
        if entity_id not in self.states:
            return None
        state, attrs = self.states[entity_id]
        return StateSnapshot(state, attrs)

    def value(self, source: Source) -> Any:
        if source.template is not None:
            return self.templates.get(source.template)
        snapshot = self.state(source.entity_id)
        if snapshot is None:
            return None
        if source.attribute:
            return snapshot.attributes.get(source.attribute)
        return snapshot.state
