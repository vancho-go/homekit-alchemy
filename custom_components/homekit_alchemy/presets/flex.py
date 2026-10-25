"""User-defined flexible blocks: ranges (any number as a slider) and modes (pick one of a list).

Apple has no generic slider or list, so these borrow native services:
- a range is a Lightbulb (brightness = position between min and max);
- a mode is a set of Switches (one per option) or a stepped Lightbulb slider
  (Apple Home does not label fan sliders inside a card, but labels lamps).
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import math
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import clamp, to_float


class RangeBehavior(Behavior):
    """A number between min and max shown as a dimmable lamp."""

    def __init__(self, source: Source, set_cmd: Command, low: float, high: float, step: float) -> None:
        if high <= low:
            raise ValueError("range max must be greater than min")
        self.source = source
        self.set_cmd = set_cmd
        self.low, self.high, self.step = low, high, step
        self._last_on: float | None = None  # restored when Apple turns the "lamp" back on

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On"), FieldSpec("Brightness")]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = to_float(view.value(self.source))
        if value is None:
            return {}
        value = clamp(value, self.low, self.high)
        if value <= self.low:
            return {"On": False}
        self._last_on = value
        percent = (value - self.low) / (self.high - self.low) * 100
        return {"On": True, "Brightness": max(1, round(percent))}

    def _snap(self, value: float) -> float:
        steps = round((value - self.low) / self.step)
        snapped = round(clamp(self.low + steps * self.step, self.low, self.high), 10)
        return int(snapped) if float(snapped).is_integer() and float(self.step).is_integer() else snapped

    def _set(self, value: float) -> list[Command]:
        return [self.set_cmd.with_variables(value=self._snap(value))]

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "Brightness" in changes:
            if changes["Brightness"] == 0:
                return self._set(self.low)
            return self._set(self.low + changes["Brightness"] / 100 * (self.high - self.low))
        if "On" in changes:
            if not changes["On"]:
                return self._set(self.low)
            current = to_float(view.value(self.source))
            if current is None or current <= self.low:
                return self._set(self._last_on if self._last_on is not None else self.high)
        return []


@dataclass(frozen=True)
class ModeSpec:
    """A list to choose from: where the current value is, the options and how to select one."""

    source: Source
    options: tuple[tuple[str, str], ...]  # (value, label), in display order
    select: Command  # rendered with variables `option` (and `value`, same thing)

    def command(self, option: str) -> Command:
        return self.select.with_variables(option=option, value=option)

    def current_index(self, view: StateView) -> int | None:
        value = view.value(self.source)
        if value is None:
            return None
        values = [v for v, _ in self.options]
        return values.index(str(value)) if str(value) in values else None


class ModeOptionBehavior(Behavior):
    """One option of a mode as a switch: on = this option is selected."""

    def __init__(self, spec: ModeSpec, option: str) -> None:
        self.spec = spec
        self.option = option

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On")]

    def sources(self) -> list[Source]:
        return [self.spec.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = view.value(self.spec.source)
        return {} if value is None else {"On": str(value) == self.option}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        # Turning an option off has no meaning; Apple resyncs on the next state update.
        return [self.spec.command(self.option)] if changes.get("On") else []


class ModeSliderBehavior(Behavior):
    """A mode as a stepped dimmer: each brightness band is one option, in order.

    The "lamp" is always on; turning it off is ignored and resynced.
    """

    def __init__(self, spec: ModeSpec) -> None:
        self.spec = spec

    @property
    def _band(self) -> float:
        return 100 / len(self.spec.options)

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On"), FieldSpec("Brightness")]

    def sources(self) -> list[Source]:
        return [self.spec.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        index = self.spec.current_index(view)
        if index is None:
            return {"On": True}
        return {"On": True, "Brightness": round((index + 1) * self._band)}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        brightness = changes.get("Brightness")
        if not brightness:
            return []  # off / 0 % is not an option
        index = min(len(self.spec.options), max(1, math.ceil(brightness / self._band))) - 1
        return [self.spec.command(self.spec.options[index][0])]


# --- Buttons: events for Apple Home automations ------------------------------

SINGLE, DOUBLE, LONG = 0, 1, 2
PRESS_NAMES = {SINGLE: "SinglePress", DOUBLE: "DoublePress", LONG: "LongPress"}
_UNSET = object()


def guess_presses(event_types: list[str]) -> dict[str, int]:
    """Map an event entity's event_types to Apple presses by their names."""
    if len(event_types) == 1:
        return {event_types[0]: SINGLE}
    mapping: dict[str, int] = {}
    for event_type in event_types:
        low = event_type.lower()
        if "double" in low:
            mapping[event_type] = DOUBLE
        elif "long" in low or "hold" in low:
            mapping[event_type] = LONG
        elif any(word in low for word in ("single", "press", "short", "click")):
            mapping[event_type] = SINGLE
    return mapping


class ButtonBehavior(Behavior):
    """Apple StatelessProgrammableSwitch fed by state changes of an entity.

    For event.* entities the state is a timestamp and the press kind is the
    `event_type` attribute, so every press is a new state. Other entities fire
    when their state (or `attribute`) changes to a mapped value.
    """

    def __init__(
        self,
        entity_id: str,
        presses: dict[str, int],
        attribute: str | None = None,
        index: int | None = None,
    ) -> None:
        if not presses:
            raise ValueError("a button needs at least one of single / double / long")
        self.entity_id = entity_id
        self.presses = presses
        self.attribute = attribute
        self.index = index  # ServiceLabelIndex when the device has several buttons
        self._last: Any = _UNSET

    def fields(self) -> list[FieldSpec]:
        kinds = sorted(set(self.presses.values()))
        fields = [FieldSpec("ProgrammableSwitchEvent", {"ValidValues": {PRESS_NAMES[k]: k for k in kinds}})]
        if self.index is not None:
            fields.append(FieldSpec("ServiceLabelIndex"))
        return fields

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        values: dict[str, Any] = {} if self.index is None else {"ServiceLabelIndex": self.index}
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return values
        value = state.attributes.get(self.attribute) if self.attribute else state.state
        key = (state.state, value)
        first, changed = self._last is _UNSET, key != self._last
        self._last = key
        if first or not changed:
            return values  # startup or an unrelated refresh: not a press
        if (press := self.presses.get(str(value))) is not None:
            values["ProgrammableSwitchEvent"] = press
        return values


class ServiceLabelBehavior(Behavior):
    """Tells Apple that the buttons of a device are numbered 1, 2, 3…"""

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("ServiceLabelNamespace")]

    def sources(self) -> list[Source]:
        return []

    def compute(self, view: StateView) -> dict[str, Any]:
        return {"ServiceLabelNamespace": 1}  # arabic numerals



# --- Television: a real pick-one list (standalone accessory) -----------------

MAX_TV_OPTIONS = 90  # same limit as Home Assistant's built-in bridge


def input_identifier(index: int) -> int:
    """Identifier of the input at `index`. Starts at 1: Apple Home puts input 0 last
    whatever DisplayOrder says (seen on iOS in 2026)."""
    return index + 1


def input_index(identifier: Any, count: int) -> int | None:
    """Back from an ActiveIdentifier written by Apple Home to a list index."""
    if identifier is None or not 1 <= identifier <= count:
        return None
    return identifier - 1


def display_order(identifiers: list[int]) -> str:
    """Apple DisplayOrder TLV8 (base64): input sources shown in this order."""
    items = [b"\x01\x04" + i.to_bytes(4, "little") for i in identifiers]
    return base64.b64encode(b"\x00\x00".join(items)).decode()


class TelevisionModeBehavior(Behavior):
    """A mode as an Apple Television whose inputs are the options."""

    def __init__(self, spec: ModeSpec) -> None:
        self.spec = spec

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("Active"),
            FieldSpec("ActiveIdentifier"),
            FieldSpec("SleepDiscoveryMode"),
            FieldSpec("DisplayOrder"),
        ]

    def sources(self) -> list[Source]:
        return [self.spec.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        values: dict[str, Any] = {
            "Active": 1,
            "SleepDiscoveryMode": 1,
            "DisplayOrder": display_order([input_identifier(i) for i in range(len(self.spec.options))]),
        }
        if (index := self.spec.current_index(view)) is not None:
            values["ActiveIdentifier"] = input_identifier(index)
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        index = input_index(changes.get("ActiveIdentifier"), len(self.spec.options))
        if index is None:
            return []  # power button: nothing to do, resync puts it back on
        return [self.spec.command(self.spec.options[index][0])]


class InputSourceBehavior(Behavior):
    """One option of a television mode (static description)."""

    def __init__(self, identifier: int) -> None:
        self.identifier = identifier

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("Identifier"),
            FieldSpec("IsConfigured"),
            FieldSpec("CurrentVisibilityState"),
            FieldSpec("InputSourceType"),
        ]

    def sources(self) -> list[Source]:
        return []

    def compute(self, view: StateView) -> dict[str, Any]:
        return {
            "Identifier": self.identifier,
            "IsConfigured": 1,
            "CurrentVisibilityState": 0,  # shown
            "InputSourceType": 0,  # other
        }
