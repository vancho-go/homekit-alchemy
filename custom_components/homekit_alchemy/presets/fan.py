"""Fans and air purifiers.

Modeled on Home Assistant's built-in HomeKit bridge (type_fans.py,
type_air_purifiers.py): speed, direction, oscillation, a single "auto"
preset as the native auto toggle, other presets as linked switches.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from ..model.keys import slugify
from .convert import to_float

FEATURE_SET_SPEED, FEATURE_OSCILLATE, FEATURE_DIRECTION = 1, 2, 4
DIRECTION_FORWARD, DIRECTION_REVERSE = "forward", "reverse"

# AirPurifier
PURIFIER_INACTIVE, PURIFIER_IDLE, PURIFIER_PURIFYING = 0, 1, 2
PURIFIER_MANUAL, PURIFIER_AUTO = 0, 1


class FanBehavior(Behavior):
    """Apple Fanv2 (or AirPurifier when `purifier=True`)."""

    def __init__(self, entity_id: str, attributes: Mapping[str, Any], purifier: bool = False) -> None:
        self.entity_id = entity_id
        self.purifier = purifier
        features = int(attributes.get("supported_features") or 0)
        self.has_speed = bool(features & FEATURE_SET_SPEED)
        self.has_direction = bool(features & FEATURE_DIRECTION)
        self.has_swing = bool(features & FEATURE_OSCILLATE)
        self.speed_step = to_float(attributes.get("percentage_step")) or 1
        presets = list(attributes.get("preset_modes") or [])
        if purifier:
            self.auto_preset = next((p for p in presets if str(p).lower() == "auto"), None)
        else:
            # A fan with exactly one preset: show it as the native "auto" toggle.
            self.auto_preset = presets[0] if len(presets) == 1 else None
        self.switch_presets = [p for p in presets if p != self.auto_preset]

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("Active")]
        if self.purifier:
            fields += [FieldSpec("CurrentAirPurifierState"), FieldSpec("TargetAirPurifierState")]
        elif self.auto_preset is not None:
            fields.append(FieldSpec("TargetFanState"))
        if self.has_speed:
            fields.append(FieldSpec("RotationSpeed", {"minStep": self.speed_step}))
        if self.has_direction:
            fields.append(FieldSpec("RotationDirection"))
        if self.has_swing:
            fields.append(FieldSpec("SwingMode"))
        return fields

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        attrs = state.attributes
        is_on = state.state == "on"
        values: dict[str, Any] = {"Active": int(is_on)}
        is_auto = self.auto_preset is not None and attrs.get("preset_mode") == self.auto_preset
        if self.purifier:
            values["CurrentAirPurifierState"] = PURIFIER_PURIFYING if is_on else PURIFIER_INACTIVE
            values["TargetAirPurifierState"] = PURIFIER_AUTO if is_auto else PURIFIER_MANUAL
        elif self.auto_preset is not None:
            values["TargetFanState"] = int(is_auto)
        # 0 % means "off" to Apple: only report speed while running.
        if self.has_speed and is_on and (percentage := to_float(attrs.get("percentage"))):
            values["RotationSpeed"] = percentage
        if self.has_direction and (direction := attrs.get("direction")) is not None:
            values["RotationDirection"] = int(direction == DIRECTION_REVERSE)
        if self.has_swing and (oscillating := attrs.get("oscillating")) is not None:
            values["SwingMode"] = int(bool(oscillating))
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "Active" in changes:
            if not changes["Active"]:
                return [Command("fan.turn_off", target)]  # anything else would turn it back on
            # Setting a speed turns the fan on at that speed; plain turn_on would jump to 100 %.
            if not (self.has_speed and changes.get("RotationSpeed")):
                commands.append(Command("fan.turn_on", target))
        if "SwingMode" in changes and self.has_swing:
            commands.append(Command("fan.oscillate", target, {"oscillating": bool(changes["SwingMode"])}))
        if "RotationDirection" in changes and self.has_direction:
            direction = DIRECTION_REVERSE if changes["RotationDirection"] else DIRECTION_FORWARD
            commands.append(Command("fan.set_direction", target, {"direction": direction}))
        if self.has_speed and changes.get("RotationSpeed"):
            percentage = self.snap_percentage(changes["RotationSpeed"])
            commands.append(Command("fan.set_percentage", target, {"percentage": percentage}))
        auto = changes.get("TargetAirPurifierState" if self.purifier else "TargetFanState")
        if auto is not None and self.auto_preset is not None:
            if auto:
                commands.append(Command("fan.set_preset_mode", target, {"preset_mode": self.auto_preset}))
            else:
                state = view.state(self.entity_id)
                percentage = to_float(state.attributes.get("percentage")) if state else None
                commands.append(Command("fan.turn_on", target, {"percentage": percentage or 50}))
        return commands

    def snap_percentage(self, value: float) -> int:
        """Apple's slider value -> a whole percentage that lands on the intended speed.

        Fans map percentage to speed by rounding up, so 3 speeds turn 67 % into
        speed 3: round to the step, then down (66 %), as HA's own bridge does.
        """
        speed = round(value / self.speed_step)
        if speed >= round(100 / self.speed_step):
            return 100
        return max(1, math.floor(speed * self.speed_step + 1e-6))


class FanPresetBehavior(Behavior):
    """One preset mode as an on/off switch (on = this preset is active)."""

    def __init__(self, entity_id: str, preset: str) -> None:
        self.entity_id = entity_id
        self.preset = preset

    @staticmethod
    def key(preset: str) -> str:
        return f"fan:preset:{slugify(preset)}"

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On")]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        return {"On": state.state == "on" and state.attributes.get("preset_mode") == self.preset}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "On" not in changes:
            return []
        target = {"entity_id": self.entity_id}
        if changes["On"]:
            return [Command("fan.set_preset_mode", target, {"preset_mode": self.preset})]
        return [Command("fan.turn_on", target)]  # leave the preset, keep running
