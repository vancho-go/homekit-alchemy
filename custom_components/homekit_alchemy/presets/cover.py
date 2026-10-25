"""Covers: garage doors / gates, window coverings, windows and doors.

Modeled on Home Assistant's built-in HomeKit bridge (type_covers.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import to_bool, to_float

FEATURE_OPEN, FEATURE_CLOSE, FEATURE_SET_POSITION, FEATURE_STOP = 1, 2, 4, 8
FEATURE_STOP_TILT, FEATURE_SET_TILT_POSITION = 64, 128

OPEN, CLOSED, OPENING, CLOSING = "open", "closed", "opening", "closing"

# GarageDoorOpener CurrentDoorState / TargetDoorState
DOOR_OPEN, DOOR_CLOSED, DOOR_OPENING, DOOR_CLOSING = 0, 1, 2, 3
DOOR_CURRENT = {OPEN: DOOR_OPEN, CLOSED: DOOR_CLOSED, OPENING: DOOR_OPENING, CLOSING: DOOR_CLOSING}
DOOR_TARGET = {OPEN: DOOR_OPEN, CLOSED: DOOR_CLOSED, OPENING: DOOR_OPEN, CLOSING: DOOR_CLOSED}

# PositionState
GOING_TO_MIN, GOING_TO_MAX, STOPPED = 0, 1, 2

# type -> (Apple service, accessory category)
COVER_TYPES: dict[str, tuple[str, str]] = {
    "garage_door": ("GarageDoorOpener", "garage_door"),
    "window_covering": ("WindowCovering", "window_covering"),
    "window": ("Window", "window"),
    "door": ("Door", "door"),
}


@dataclass(frozen=True)
class CoverOverrides:
    """User overrides from entity_config (example: a gate on a relay with a reed switch)."""

    state: Source | None = None  # on/open = open
    open: Command | None = None
    close: Command | None = None
    stop: Command | None = None
    obstruction: Source | None = None


def default_cover_type(attributes: Mapping[str, Any]) -> str:
    features = int(attributes.get("supported_features") or 0)
    device_class = attributes.get("device_class")
    if device_class in ("garage", "gate") and features & (FEATURE_OPEN | FEATURE_CLOSE):
        return "garage_door"
    if device_class == "window" and features & FEATURE_SET_POSITION:
        return "window"
    if device_class == "door" and features & FEATURE_SET_POSITION:
        return "door"
    return "window_covering"


class _CoverBase(Behavior):
    def __init__(self, entity_id: str, attributes: Mapping[str, Any], overrides: CoverOverrides) -> None:
        self.entity_id = entity_id
        self.overrides = overrides
        self.features = int(attributes.get("supported_features") or 0)
        target = {"entity_id": entity_id}
        self.open_cmd = overrides.open or Command("cover.open_cover", target)
        self.close_cmd = overrides.close or Command("cover.close_cover", target)
        self.stop_cmd = overrides.stop or (
            Command("cover.stop_cover", target) if self.features & FEATURE_STOP else None
        )

    def sources(self) -> list[Source]:
        sources = [Source(entity_id=self.entity_id)]
        sources += [s for s in (self.overrides.state, self.overrides.obstruction) if s]
        return sources

    def _state(self, view: StateView) -> str | None:
        """open / closed / opening / closing; the override source wins when given."""
        if self.overrides.state is not None:
            is_open = to_bool(view.value(self.overrides.state))
            return None if is_open is None else (OPEN if is_open else CLOSED)
        state = view.state(self.entity_id)
        if state is None or state.state not in DOOR_CURRENT:
            return None
        return state.state

    def _obstruction(self, view: StateView) -> bool | None:
        if self.overrides.obstruction is None:
            return None
        return to_bool(view.value(self.overrides.obstruction))


class GarageDoorBehavior(_CoverBase):
    """Apple GarageDoorOpener: open/close only."""

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("CurrentDoorState"), FieldSpec("TargetDoorState"), FieldSpec("ObstructionDetected")]

    def compute(self, view: StateView) -> dict[str, Any]:
        values: dict[str, Any] = {}
        if (state := self._state(view)) is not None:
            values["CurrentDoorState"] = DOOR_CURRENT[state]
            values["TargetDoorState"] = DOOR_TARGET[state]
        values["ObstructionDetected"] = bool(self._obstruction(view))
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "TargetDoorState" not in changes:
            return []
        return [self.open_cmd if changes["TargetDoorState"] == DOOR_OPEN else self.close_cmd]


class PositionCoverBehavior(_CoverBase):
    """Apple WindowCovering / Window / Door with position, optional stop and tilt.

    Covers without set_position get 0/100 positions and open/close/stop by thresholds.
    Tilt-only covers (pergolas, vertical blinds) drive the main slider with the tilt:
    Apple has no tilt-only service, and a locked position slider is useless.
    """

    def __init__(self, entity_id: str, attributes: Mapping[str, Any], overrides: CoverOverrides) -> None:
        super().__init__(entity_id, attributes, overrides)
        self.has_position = bool(self.features & FEATURE_SET_POSITION) and overrides.state is None
        supports_tilt = bool(self.features & FEATURE_SET_TILT_POSITION)
        self.tilt_only = supports_tilt and not self.features & (FEATURE_OPEN | FEATURE_CLOSE | FEATURE_SET_POSITION)
        self.has_tilt = supports_tilt and not self.tilt_only  # separate tilt angle fields
        if self.tilt_only and overrides.stop is None:
            self.stop_cmd = (
                Command("cover.stop_cover_tilt", {"entity_id": entity_id})
                if self.features & FEATURE_STOP_TILT
                else None
            )
        self._target: int | None = None

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("CurrentPosition"), FieldSpec("TargetPosition"), FieldSpec("PositionState")]
        if self.stop_cmd is not None:
            fields.append(FieldSpec("HoldPosition"))
        if self.has_tilt:
            fields += [FieldSpec("CurrentHorizontalTiltAngle"), FieldSpec("TargetHorizontalTiltAngle")]
        if self.overrides.obstruction is not None:
            fields.append(FieldSpec("ObstructionDetected"))
        return fields

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        values: dict[str, Any] = {}
        cover_state = self._state(view)
        moving = cover_state in (OPENING, CLOSING)
        values["PositionState"] = {OPENING: GOING_TO_MAX, CLOSING: GOING_TO_MIN}.get(cover_state, STOPPED)

        if self.tilt_only:
            if (tilt := to_float(state.attributes.get("current_tilt_position"))) is not None:
                values["CurrentPosition"] = values["TargetPosition"] = round(tilt)
        elif self.has_position and (position := to_float(state.attributes.get("current_position"))) is not None:
            current = round(position)
            values["CurrentPosition"] = current
            if not moving:
                values["TargetPosition"] = self._target = current
            elif self._target is None or (cover_state == OPENING and self._target < current) or (
                cover_state == CLOSING and self._target > current
            ):
                # Apple reads direction from target vs current: never leave a target already passed.
                values["TargetPosition"] = self._target = 100 if cover_state == OPENING else 0
        elif cover_state in (OPEN, CLOSED):
            position = 100 if cover_state == OPEN else 0
            values["CurrentPosition"] = values["TargetPosition"] = position

        if self.has_tilt and (tilt := to_float(state.attributes.get("current_tilt_position"))) is not None:
            angle = round(tilt / 100 * 180 - 90)  # HA 0..100 -> Apple -90..90
            values["CurrentHorizontalTiltAngle"] = values["TargetHorizontalTiltAngle"] = angle
        if self.overrides.obstruction is not None:
            values["ObstructionDetected"] = bool(self._obstruction(view))
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if changes.get("HoldPosition") and self.stop_cmd is not None:
            commands.append(self.stop_cmd)
        if "TargetPosition" in changes:
            value = round(changes["TargetPosition"])
            self._target = value
            if self.tilt_only:
                commands.append(Command("cover.set_cover_tilt_position", target, {"tilt_position": value}))
            elif self.has_position:
                commands.append(Command("cover.set_cover_position", target, {"position": value}))
            elif self.stop_cmd is not None and 30 <= value <= 70:
                commands.append(self.stop_cmd)
            else:
                commands.append(self.open_cmd if value >= 50 else self.close_cmd)
        if "TargetHorizontalTiltAngle" in changes and self.has_tilt:
            tilt = round((changes["TargetHorizontalTiltAngle"] + 90) / 180 * 100)
            commands.append(Command("cover.set_cover_tilt_position", target, {"tilt_position": tilt}))
        return commands
