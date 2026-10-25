"""Light: On + Brightness + ColorTemperature + Hue/Saturation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import brightness_to_percent, kelvin_to_mired, mired_to_kelvin, to_bool

COLOR_MODES_COLOR = {"hs", "xy", "rgb", "rgbw", "rgbww"}
COLOR_MODE_TEMP = "color_temp"
COLOR_MODE_ONOFF = "onoff"

DEFAULT_MIN_KELVIN = 2000
DEFAULT_MAX_KELVIN = 6500


class LightBehavior(Behavior):
    """Maps a light entity onto an Apple Lightbulb service."""

    def __init__(
        self,
        entity_id: str,
        color_modes: Iterable[str] = (),
        min_kelvin: int | None = None,
        max_kelvin: int | None = None,
        state: Source | None = None,
        turn_on: Command | None = None,
        turn_off: Command | None = None,
    ) -> None:
        self.entity_id = entity_id
        # Optional user overrides for plain on/off (brightness/color still go to the light).
        self.state_override = state
        self.turn_on_override = turn_on
        self.turn_off_override = turn_off
        modes = set(color_modes)
        self.dimmable = bool(modes - {COLOR_MODE_ONOFF})
        self.has_color = bool(modes & COLOR_MODES_COLOR)
        self.has_temp = COLOR_MODE_TEMP in modes
        # Apple wants mireds: min mired = max kelvin.
        self.min_mired = kelvin_to_mired(max_kelvin or DEFAULT_MAX_KELVIN)
        self.max_mired = kelvin_to_mired(min_kelvin or DEFAULT_MIN_KELVIN)

    @classmethod
    def from_attributes(
        cls, entity_id: str, attributes: Mapping[str, Any], **overrides: Any
    ) -> LightBehavior:
        return cls(
            entity_id,
            color_modes=attributes.get("supported_color_modes") or (),
            min_kelvin=attributes.get("min_color_temp_kelvin"),
            max_kelvin=attributes.get("max_color_temp_kelvin"),
            **overrides,
        )

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("On")]
        if self.dimmable:
            fields.append(FieldSpec("Brightness"))
        if self.has_temp:
            fields.append(
                FieldSpec(
                    "ColorTemperature",
                    {"minValue": self.min_mired, "maxValue": self.max_mired},
                )
            )
        if self.has_color:
            fields += [FieldSpec("Hue"), FieldSpec("Saturation")]
        return fields

    def sources(self) -> list[Source]:
        sources = [Source(entity_id=self.entity_id)]
        if self.state_override:
            sources.append(self.state_override)
        return sources

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        if self.state_override:
            is_on = to_bool(view.value(self.state_override))
            if is_on is None:
                return {}
        else:
            is_on = state.state == "on"
        values: dict[str, Any] = {"On": is_on}
        if not is_on:
            return values  # keep last brightness/color in Apple Home
        attrs = state.attributes
        if self.dimmable and (brightness := attrs.get("brightness")) is not None:
            values["Brightness"] = brightness_to_percent(brightness)
        if self.has_temp and (kelvin := attrs.get("color_temp_kelvin")):
            values["ColorTemperature"] = kelvin_to_mired(kelvin)
        if self.has_color and (hs := attrs.get("hs_color")):
            values["Hue"], values["Saturation"] = hs[0], hs[1]
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        if ("On" in changes and not changes["On"]) or changes.get("Brightness") == 0:
            return [self.turn_off_override or Command("light.turn_off", target)]
        data: dict[str, Any] = {}
        if "Brightness" in changes:
            data["brightness_pct"] = changes["Brightness"]
        if "ColorTemperature" in changes:
            data["color_temp_kelvin"] = mired_to_kelvin(changes["ColorTemperature"])
        if "Hue" in changes or "Saturation" in changes:
            current = self.compute(view)
            hue = changes.get("Hue", current.get("Hue", 0))
            saturation = changes.get("Saturation", current.get("Saturation", 0))
            data["hs_color"] = [hue, saturation]
        if not data:
            if not changes.get("On"):
                return []
            return [self.turn_on_override or Command("light.turn_on", target)]
        return [Command("light.turn_on", target, data)]
