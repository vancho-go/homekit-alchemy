"""Climate: Apple Thermostat (heating devices) and HeaterCooler (air conditioners).

Modeled on Home Assistant's built-in HomeKit bridge (type_thermostats.py,
type_heater_coolers.py), trimmed to what Apple Home actually shows.
`dry` / `fan_only` are deliberately not mapped to Apple modes: expose them
with `switches:` instead of pretending they are "cool".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import celsius_to_fahrenheit, fahrenheit_to_celsius, to_float

FAHRENHEIT = "°F"

FEATURE_TARGET_TEMPERATURE_RANGE = 2
FEATURE_TURN_OFF = 128

OFF, HEAT, COOL, HEAT_COOL, AUTO = "off", "heat", "cool", "heat_cool", "auto"

# Thermostat: TargetHeatingCoolingState / CurrentHeatingCoolingState
TH_OFF, TH_HEAT, TH_COOL, TH_AUTO = 0, 1, 2, 3
# HeaterCooler: TargetHeaterCoolerState / CurrentHeaterCoolerState
HC_AUTO, HC_HEAT, HC_COOL = 0, 1, 2
HC_INACTIVE, HC_IDLE, HC_HEATING, HC_COOLING = 0, 1, 2, 3

CURRENT_TEMPERATURE_PROPS = {"minValue": -100, "maxValue": 200, "minStep": 0.1}
DEFAULT_MIN_TEMP, DEFAULT_MAX_TEMP = 7.0, 35.0
DEFAULT_STEP = 0.1

ACTION_HEATING = {"heating", "preheating", "defrosting"}
ACTION_COOLING = {"cooling", "drying", "fan"}


@dataclass(frozen=True)
class ClimateOverrides:
    """User overrides from entity_config."""

    current_temperature: Source | None = None
    current_humidity: Source | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    temperature_step: float | None = None


class _ClimateBase(Behavior):
    """Shared parsing of a climate entity's capabilities and temperatures."""

    def __init__(
        self,
        entity_id: str,
        attributes: Mapping[str, Any],
        temperature_unit: str = "°C",
        overrides: ClimateOverrides = ClimateOverrides(),
    ) -> None:
        self.entity_id = entity_id
        self.unit = temperature_unit
        self.overrides = overrides
        self.hvac_modes: list[str] = list(attributes.get("hvac_modes") or [])
        features = int(attributes.get("supported_features") or 0)
        self.supports_range = bool(features & FEATURE_TARGET_TEMPERATURE_RANGE)
        self.can_turn_off = OFF in self.hvac_modes or bool(features & FEATURE_TURN_OFF)

        low = overrides.min_temp if overrides.min_temp is not None else self._attr_c(attributes, "min_temp")
        high = overrides.max_temp if overrides.max_temp is not None else self._attr_c(attributes, "max_temp")
        low = DEFAULT_MIN_TEMP if low is None else low
        high = DEFAULT_MAX_TEMP if high is None else high
        # Apple Home crashes on negative bounds (see HA climate_util).
        self.min_temp = max(0.0, min(low, high))
        self.max_temp = max(low, high)
        self.step = overrides.temperature_step or to_float(attributes.get("target_temp_step")) or DEFAULT_STEP
        self._configure(attributes)

    def _configure(self, attributes: Mapping[str, Any]) -> None:
        """Subclass hook: derive Apple-specific capabilities from the attributes."""

    # Temperatures: Apple is always Celsius.

    def _to_c(self, value: Any) -> float | None:
        number = to_float(value)
        if number is None:
            return None
        return fahrenheit_to_celsius(number) if self.unit == FAHRENHEIT else number

    def _from_c(self, value: float) -> float:
        return round(celsius_to_fahrenheit(value)) if self.unit == FAHRENHEIT else value

    def _attr_c(self, attributes: Mapping[str, Any], name: str) -> float | None:
        return self._to_c(attributes.get(name))

    def _target_props(self) -> dict[str, Any]:
        return {"minValue": self.min_temp, "maxValue": self.max_temp, "minStep": self.step}

    def _clamp_target(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(max(self.min_temp, min(self.max_temp, value)), 1)

    def _current_temperature(self, view: StateView, attributes: Mapping[str, Any]) -> float | None:
        if self.overrides.current_temperature:
            value = self._to_c(view.value(self.overrides.current_temperature))
        else:
            value = self._attr_c(attributes, "current_temperature")
        return None if value is None else round(value, 1)

    def _current_humidity(self, view: StateView, attributes: Mapping[str, Any]) -> float | None:
        raw = (
            view.value(self.overrides.current_humidity)
            if self.overrides.current_humidity
            else attributes.get("current_humidity")
        )
        value = to_float(raw)
        return None if value is None else round(max(0.0, min(100.0, value)))

    def sources(self) -> list[Source]:
        sources = [Source(entity_id=self.entity_id)]
        sources += [s for s in (self.overrides.current_temperature, self.overrides.current_humidity) if s]
        return sources

    def _is_heating(self, mode: str, attributes: Mapping[str, Any], current: float | None) -> bool | None:
        """True heating, False cooling, None idle — from hvac_action or a temperature guess."""
        if action := attributes.get("hvac_action"):
            if action in ACTION_HEATING:
                return True
            if action in ACTION_COOLING:
                return False
            return None
        target = self._attr_c(attributes, "temperature")
        if current is None or target is None:
            return None
        if mode == HEAT and current < target:
            return True
        if mode == COOL and current > target:
            return False
        return None

    def _off_command(self) -> Command:
        target = {"entity_id": self.entity_id}
        if OFF in self.hvac_modes:
            return Command("climate.set_hvac_mode", target, {"hvac_mode": OFF})
        return Command("climate.turn_off", target)

    def _apply(self, mode: str | None, temps: dict[str, float]) -> list[Command]:
        """One call for mode+temperatures, so the device never sees half a change."""
        target = {"entity_id": self.entity_id}
        if mode == OFF and not temps:
            return [self._off_command()]
        if temps:
            data: dict[str, Any] = {k: self._from_c(v) for k, v in temps.items()}
            if mode:
                data["hvac_mode"] = mode
            return [Command("climate.set_temperature", target, data)]
        if mode:
            return [Command("climate.set_hvac_mode", target, {"hvac_mode": mode})]
        return []

    def _range_or_single(
        self, view: StateView, low: float | None, high: float | None
    ) -> dict[str, float]:
        """Fill the missing end of a low/high pair from the current state."""
        state = view.state(self.entity_id)
        attrs = state.attributes if state else {}
        low = low if low is not None else self._attr_c(attrs, "target_temp_low")
        high = high if high is not None else self._attr_c(attrs, "target_temp_high")
        if low is None or high is None:
            return {}
        return {"target_temp_low": low, "target_temp_high": high}


class ThermostatBehavior(_ClimateBase):
    """Apple Thermostat: off / heat / cool / auto with a target temperature."""

    def _configure(self, attributes: Mapping[str, Any]) -> None:
        # Apple value -> HA mode, only for modes the entity really has.
        self.to_ha: dict[int, str] = {}
        for ha_mode, apple in ((OFF, TH_OFF), (HEAT, TH_HEAT), (COOL, TH_COOL), (HEAT_COOL, TH_AUTO), (AUTO, TH_AUTO)):
            if ha_mode in self.hvac_modes and apple not in self.to_ha:
                self.to_ha[apple] = ha_mode
        if TH_OFF not in self.to_ha and self.can_turn_off:
            self.to_ha[TH_OFF] = OFF
        self.from_ha = {ha: apple for apple, ha in self.to_ha.items()}
        self.has_range = self.supports_range and TH_AUTO in self.to_ha
        self.has_humidity = (
            self.overrides.current_humidity is not None
            or attributes.get("current_humidity") is not None
        )

    def fields(self) -> list[FieldSpec]:
        names = {TH_OFF: "Off", TH_HEAT: "Heat", TH_COOL: "Cool", TH_AUTO: "Auto"}
        fields = [
            FieldSpec("CurrentHeatingCoolingState"),
            FieldSpec(
                "TargetHeatingCoolingState",
                {"ValidValues": {names[v]: v for v in sorted(self.to_ha)}},
            ),
            FieldSpec("CurrentTemperature", CURRENT_TEMPERATURE_PROPS),
            FieldSpec("TargetTemperature", self._target_props()),
            FieldSpec("TemperatureDisplayUnits"),
        ]
        if self.has_range:
            fields += [
                FieldSpec("HeatingThresholdTemperature", self._target_props()),
                FieldSpec("CoolingThresholdTemperature", self._target_props()),
            ]
        if self.has_humidity:
            fields.append(FieldSpec("CurrentRelativeHumidity"))
        return fields

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        attrs = state.attributes
        values: dict[str, Any] = {"TemperatureDisplayUnits": int(self.unit == FAHRENHEIT)}
        if (apple := self.from_ha.get(state.state)) is not None:
            values["TargetHeatingCoolingState"] = apple
        current = self._current_temperature(view, attrs)
        if current is not None:
            values["CurrentTemperature"] = current
        if (target := self._clamp_target(self._attr_c(attrs, "temperature"))) is not None:
            values["TargetTemperature"] = target
        if self.has_range:
            for field_kind, attr in (("HeatingThresholdTemperature", "target_temp_low"), ("CoolingThresholdTemperature", "target_temp_high")):
                if (value := self._clamp_target(self._attr_c(attrs, attr))) is not None:
                    values[field_kind] = value
        heating = self._is_heating(state.state, attrs, current)
        values["CurrentHeatingCoolingState"] = TH_OFF if heating is None else (TH_HEAT if heating else TH_COOL)
        if self.has_humidity and (hum := self._current_humidity(view, attrs)) is not None:
            values["CurrentRelativeHumidity"] = hum
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        mode = self.to_ha.get(changes["TargetHeatingCoolingState"]) if "TargetHeatingCoolingState" in changes else None
        temps: dict[str, float] = {}
        if "TargetTemperature" in changes:
            temps["temperature"] = changes["TargetTemperature"]
        if "HeatingThresholdTemperature" in changes or "CoolingThresholdTemperature" in changes:
            temps.update(
                self._range_or_single(
                    view,
                    changes.get("HeatingThresholdTemperature"),
                    changes.get("CoolingThresholdTemperature"),
                )
            )
        return self._apply(mode, temps)


class HeaterCoolerBehavior(_ClimateBase):
    """Apple HeaterCooler: power, auto/heat/cool and thresholds (fan lives in ClimateFanBehavior)."""

    def _configure(self, attributes: Mapping[str, Any]) -> None:
        self.to_ha: dict[int, str] = {}
        for ha_mode, apple in ((HEAT_COOL, HC_AUTO), (AUTO, HC_AUTO), (HEAT, HC_HEAT), (COOL, HC_COOL)):
            if ha_mode in self.hvac_modes and apple not in self.to_ha:
                self.to_ha[apple] = ha_mode
        self.from_ha = {ha: apple for apple, ha in self.to_ha.items()}
        self._last_mode: str | None = None

    def fields(self) -> list[FieldSpec]:
        names = {HC_AUTO: "Auto", HC_HEAT: "Heat", HC_COOL: "Cool"}
        fields = [
            FieldSpec("Active"),
            FieldSpec("CurrentHeaterCoolerState"),
            FieldSpec("TargetHeaterCoolerState", {"ValidValues": {names[v]: v for v in sorted(self.to_ha)}}),
            FieldSpec("CurrentTemperature", CURRENT_TEMPERATURE_PROPS),
        ]
        if HC_COOL in self.to_ha or HC_AUTO in self.to_ha:
            fields.append(FieldSpec("CoolingThresholdTemperature", self._target_props()))
        if HC_HEAT in self.to_ha or HC_AUTO in self.to_ha:
            fields.append(FieldSpec("HeatingThresholdTemperature", self._target_props()))
        return fields

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        attrs, mode = state.attributes, state.state
        values: dict[str, Any] = {}
        current = self._current_temperature(view, attrs)
        if current is not None:
            values["CurrentTemperature"] = current

        if mode == OFF:
            values["Active"] = 0
            values["CurrentHeaterCoolerState"] = HC_INACTIVE
        else:
            values["Active"] = 1
            if (apple := self.from_ha.get(mode)) is not None:
                values["TargetHeaterCoolerState"] = apple
                self._last_mode = mode
            heating = self._is_heating(mode, attrs, current)
            values["CurrentHeaterCoolerState"] = HC_IDLE if heating is None else (HC_HEATING if heating else HC_COOLING)

        target = self._clamp_target(self._attr_c(attrs, "temperature"))
        low = self._clamp_target(self._attr_c(attrs, "target_temp_low"))
        high = self._clamp_target(self._attr_c(attrs, "target_temp_high"))
        if mode in (HEAT_COOL, AUTO) and low is not None and high is not None:
            values["HeatingThresholdTemperature"], values["CoolingThresholdTemperature"] = low, high
        elif target is not None:
            # Single set point: show it on whichever dial the current mode uses (both when unknown).
            if mode != HEAT:
                values["CoolingThresholdTemperature"] = target
            if mode != COOL:
                values["HeatingThresholdTemperature"] = target
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if changes.get("Active") == 0:
            return [self._off_command()]

        state = view.state(self.entity_id)
        current_mode = state.state if state else OFF
        mode: str | None = None
        if "TargetHeaterCoolerState" in changes:
            mode = self.to_ha.get(changes["TargetHeaterCoolerState"])
        elif changes.get("Active") == 1 and current_mode == OFF:
            mode = self._last_mode or next(iter(self.to_ha.values()), None)
        effective = mode or current_mode

        temps: dict[str, float] = {}
        heat, cool = changes.get("HeatingThresholdTemperature"), changes.get("CoolingThresholdTemperature")
        if heat is not None or cool is not None:
            if effective in (HEAT_COOL, AUTO) and self.supports_range:
                temps = self._range_or_single(view, heat, cool)
            elif effective == HEAT and heat is not None:
                temps = {"temperature": heat}
            elif effective == COOL and cool is not None:
                temps = {"temperature": cool}
            else:
                temps = {"temperature": cool if cool is not None else heat}
        return self._apply(mode, temps)


class ClimateFanBehavior(Behavior):
    """Fan speed and auto fan of a climate entity, as an Apple Fan linked to the main block.

    Apple Home ignores RotationSpeed on Thermostat and HeaterCooler; a linked
    fan service is how the built-in HA bridge makes it visible.
    """

    def __init__(self, entity_id: str, attributes: Mapping[str, Any]) -> None:
        self.entity_id = entity_id
        fan_modes = list(attributes.get("fan_modes") or [])
        self.auto_mode = next((m for m in fan_modes if str(m).lower() == AUTO), None)
        self.speeds = [m for m in fan_modes if m != self.auto_mode]

    @classmethod
    def applies(cls, attributes: Mapping[str, Any]) -> bool:
        return bool(cls("climate.x", attributes).speeds)

    @property
    def _step(self) -> float:
        return 100 / len(self.speeds)

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("Active"), FieldSpec("RotationSpeed", {"minStep": self._step})]
        if self.auto_mode is not None:
            fields.append(FieldSpec("TargetFanState"))
        return fields

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        attrs = state.attributes
        values: dict[str, Any] = {"Active": int(state.state != OFF)}
        fan = attrs.get("fan_mode")
        if fan in self.speeds:
            values["RotationSpeed"] = round((self.speeds.index(fan) + 1) * self._step, 4)
        if self.auto_mode is not None and fan is not None:
            values["TargetFanState"] = int(fan == self.auto_mode)  # 1 = auto
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "Active" in changes:
            state = view.state(self.entity_id)
            is_on = state is not None and state.state != OFF
            if bool(changes["Active"]) != is_on:
                commands.append(Command("climate.turn_on" if changes["Active"] else "climate.turn_off", target))
        if changes.get("TargetFanState") == 1 and self.auto_mode is not None:
            commands.append(Command("climate.set_fan_mode", target, {"fan_mode": self.auto_mode}))
        elif speed := changes.get("RotationSpeed"):
            index = min(len(self.speeds), max(1, math.ceil(speed / self._step))) - 1
            commands.append(Command("climate.set_fan_mode", target, {"fan_mode": self.speeds[index]}))
        elif changes.get("TargetFanState") == 0:
            commands.append(Command("climate.set_fan_mode", target, {"fan_mode": self.speeds[len(self.speeds) // 2]}))
        return commands


class WaterHeaterBehavior(_ClimateBase):
    """water_heater as an Apple Thermostat with off / heat (like the built-in bridge)."""

    FEATURE_ON_OFF = 8

    def _configure(self, attributes: Mapping[str, Any]) -> None:
        self.operations: list[str] = list(attributes.get("operation_list") or [])
        self.on_operation = next((op for op in self.operations if op != OFF), None)
        self.supports_on_off = bool(int(attributes.get("supported_features") or 0) & self.FEATURE_ON_OFF)

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("CurrentHeatingCoolingState"),
            FieldSpec("TargetHeatingCoolingState", {"ValidValues": {"Off": TH_OFF, "Heat": TH_HEAT}}),
            FieldSpec("CurrentTemperature", CURRENT_TEMPERATURE_PROPS),
            FieldSpec("TargetTemperature", self._target_props()),
            FieldSpec("TemperatureDisplayUnits"),
        ]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or not state.available:
            return {}
        attrs = state.attributes
        is_on = state.state != OFF
        values: dict[str, Any] = {
            "TemperatureDisplayUnits": int(self.unit == FAHRENHEIT),
            "TargetHeatingCoolingState": TH_HEAT if is_on else TH_OFF,
        }
        current = self._current_temperature(view, attrs)
        if current is not None:
            values["CurrentTemperature"] = current
        target = self._clamp_target(self._attr_c(attrs, "temperature"))
        if target is not None:
            values["TargetTemperature"] = target
        heating = is_on and current is not None and target is not None and current < target
        values["CurrentHeatingCoolingState"] = TH_HEAT if heating else TH_OFF
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "TargetHeatingCoolingState" in changes:
            turn_on = changes["TargetHeatingCoolingState"] != TH_OFF
            if self.supports_on_off:
                commands.append(Command("water_heater.turn_on" if turn_on else "water_heater.turn_off", target))
            elif (operation := self.on_operation if turn_on else OFF) in self.operations:
                commands.append(Command("water_heater.set_operation_mode", target, {"operation_mode": operation}))
        if "TargetTemperature" in changes:
            commands.append(
                Command("water_heater.set_temperature", target, {"temperature": self._from_c(changes["TargetTemperature"])})
            )
        return commands
