"""On/off blocks: switches, outlets, input_booleans and user-defined toggles."""

from __future__ import annotations

from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import to_bool

ONOFF_SERVICES = {"switch": "Switch", "outlet": "Outlet", "light": "Lightbulb"}


class OnOffBehavior(Behavior):
    """On/Off read from a source, switched by two commands."""

    def __init__(
        self,
        state: Source | None,
        turn_on: Command | None,
        turn_off: Command | None,
        outlet: bool = False,
    ) -> None:
        self.state = state
        self.turn_on = turn_on
        self.turn_off = turn_off
        self.outlet = outlet
        self._last: bool = False  # optimistic value for blocks without state

    @classmethod
    def for_entity(cls, entity_id: str, outlet: bool = False) -> OnOffBehavior:
        target = {"entity_id": entity_id}
        return cls(
            Source(entity_id=entity_id),
            Command("homeassistant.turn_on", target),
            Command("homeassistant.turn_off", target),
            outlet=outlet,
        )

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("On")]
        if self.outlet:
            fields.append(FieldSpec("OutletInUse"))
        return fields

    def sources(self) -> list[Source]:
        return [self.state] if self.state else []

    def compute(self, view: StateView) -> dict[str, Any]:
        is_on = self._last if self.state is None else to_bool(view.value(self.state))
        if is_on is None:
            return {}
        values: dict[str, Any] = {"On": is_on}
        if self.outlet:
            values["OutletInUse"] = is_on
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "On" not in changes:
            return []
        self._last = bool(changes["On"])
        command = self.turn_on if changes["On"] else self.turn_off
        return [command] if command else []
