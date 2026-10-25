"""Climate presets, tested on the attributes of real devices."""

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.climate import (
    ClimateFanBehavior,
    ClimateOverrides,
    HeaterCoolerBehavior,
    ThermostatBehavior,
)
from custom_components.homekit_alchemy.presets.registry import main_block
from tests.fakes import FakeView

RADIATOR = "climate.radiator"
RADIATOR_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "current_temperature": 22.6,
    "temperature": 23.0,
    "min_temp": 5.0,
    "max_temp": 30.0,
    "supported_features": 385,
}
AC = "climate.ac"
AC_ATTRS = {
    "hvac_modes": ["off", "cool", "heat", "dry", "fan_only", "heat_cool"],
    "current_temperature": 27,
    "temperature": 23.0,
    "min_temp": 16.0,
    "max_temp": 88.0,
    "target_temp_step": 0.5,
    "fan_modes": ["auto", "quiet", "low", "medlow", "medium", "medhigh", "high", "strong"],
    "fan_mode": "medium",
    "swing_modes": ["off", "on"],
    "swing_mode": "off",
    "supported_features": 937,
}


def _fields(behavior) -> dict:
    return {f.kind: dict(f.properties) for f in behavior.fields()}


def test_auto_type() -> None:
    assert main_block(RADIATOR, RADIATOR_ATTRS).service == "Thermostat"
    assert main_block(AC, AC_ATTRS).service == "HeaterCooler"
    assert main_block(AC, AC_ATTRS, "thermostat").service == "Thermostat"


def test_radiator_thermostat() -> None:
    behavior = ThermostatBehavior(RADIATOR, RADIATOR_ATTRS)
    fields = _fields(behavior)
    assert fields["TargetHeatingCoolingState"] == {"ValidValues": {"Off": 0, "Heat": 1}}
    assert fields["TargetTemperature"] == {"minValue": 5.0, "maxValue": 30.0, "minStep": 0.1}
    assert "CurrentRelativeHumidity" not in fields
    assert "HeatingThresholdTemperature" not in fields

    view = FakeView({RADIATOR: ("heat", RADIATOR_ATTRS)})
    assert behavior.compute(view) == {
        "TemperatureDisplayUnits": 0,
        "TargetHeatingCoolingState": 1,
        "CurrentTemperature": 22.6,
        "TargetTemperature": 23.0,
        "CurrentHeatingCoolingState": 1,  # no hvac_action: 22.6 < 23 -> heating
    }
    view.set(RADIATOR, "off", RADIATOR_ATTRS)
    assert behavior.compute(view)["CurrentHeatingCoolingState"] == 0

    target = {"entity_id": RADIATOR}
    assert behavior.handle({"TargetHeatingCoolingState": 0}, view) == [
        Command("climate.set_hvac_mode", target, {"hvac_mode": "off"})
    ]
    assert behavior.handle({"TargetTemperature": 21.5}, view) == [
        Command("climate.set_temperature", target, {"temperature": 21.5})
    ]
    assert behavior.handle({"TargetHeatingCoolingState": 1, "TargetTemperature": 24}, view) == [
        Command("climate.set_temperature", target, {"temperature": 24, "hvac_mode": "heat"})
    ]


def test_thermostat_overrides_and_fahrenheit() -> None:
    overrides = ClimateOverrides(
        current_temperature=Source(entity_id="sensor.room"),
        current_humidity=Source(entity_id="sensor.hum"),
        max_temp=28,
    )
    attrs_f = {**RADIATOR_ATTRS, "min_temp": 41, "max_temp": 86, "temperature": 73.4, "current_temperature": 70}
    behavior = ThermostatBehavior(RADIATOR, attrs_f, "°F", overrides)
    assert _fields(behavior)["TargetTemperature"]["maxValue"] == 28
    view = FakeView({RADIATOR: ("heat", attrs_f), "sensor.room": ("68", {}), "sensor.hum": ("41.4", {})})
    values = behavior.compute(view)
    assert values["CurrentTemperature"] == 20.0  # 68 °F from the override sensor
    assert values["TargetTemperature"] == 23.0
    assert values["CurrentRelativeHumidity"] == 41
    assert values["TemperatureDisplayUnits"] == 1
    assert behavior.handle({"TargetTemperature": 23}, view) == [
        Command("climate.set_temperature", {"entity_id": RADIATOR}, {"temperature": 73})
    ]
    assert set(behavior.sources()) == {Source(entity_id=RADIATOR), Source(entity_id="sensor.room"), Source(entity_id="sensor.hum")}


def test_ac_heater_cooler_fields() -> None:
    behavior = HeaterCoolerBehavior(AC, AC_ATTRS, overrides=ClimateOverrides(max_temp=30))
    fields = _fields(behavior)
    assert fields["TargetHeaterCoolerState"] == {"ValidValues": {"Auto": 0, "Heat": 1, "Cool": 2}}
    assert fields["CoolingThresholdTemperature"] == {"minValue": 16.0, "maxValue": 30, "minStep": 0.5}
    assert "RotationSpeed" not in fields  # Apple ignores it here; it lives on the linked fan

    main = main_block(AC, AC_ATTRS)
    assert [(b.key, b.service, b.linked) for b in main.extras] == [("climate:fan", "Fanv2", True)]
    assert not main_block(RADIATOR, RADIATOR_ATTRS).extras


def test_ac_compute() -> None:
    behavior = HeaterCoolerBehavior(AC, AC_ATTRS)
    view = FakeView({AC: ("cool", AC_ATTRS)})
    assert behavior.compute(view) == {
        "CurrentTemperature": 27.0,
        "Active": 1,
        "TargetHeaterCoolerState": 2,
        "CurrentHeaterCoolerState": 3,  # 27 > 23 in cool -> cooling
        "CoolingThresholdTemperature": 23.0,
    }
    view.set(AC, "off", AC_ATTRS)
    values = behavior.compute(view)
    assert values["Active"] == 0 and values["CurrentHeaterCoolerState"] == 0
    view.set(AC, "dry", AC_ATTRS)
    values = behavior.compute(view)
    assert values["Active"] == 1 and "TargetHeaterCoolerState" not in values


def test_ac_commands() -> None:
    behavior = HeaterCoolerBehavior(AC, AC_ATTRS)
    target = {"entity_id": AC}
    view = FakeView({AC: ("heat", AC_ATTRS)})
    behavior.compute(view)  # remembers 'heat' as last mode
    view.set(AC, "off", AC_ATTRS)

    assert behavior.handle({"Active": 0}, view) == [Command("climate.set_hvac_mode", target, {"hvac_mode": "off"})]
    assert behavior.handle({"Active": 1}, view) == [Command("climate.set_hvac_mode", target, {"hvac_mode": "heat"})]
    assert behavior.handle({"Active": 1, "TargetHeaterCoolerState": 2, "CoolingThresholdTemperature": 22}, view) == [
        Command("climate.set_temperature", target, {"temperature": 22, "hvac_mode": "cool"})
    ]


def test_ac_fan() -> None:
    fan = ClimateFanBehavior(AC, AC_ATTRS)
    target = {"entity_id": AC}
    assert [f.kind for f in fan.fields()] == ["Active", "RotationSpeed", "TargetFanState"]
    view = FakeView({AC: ("cool", AC_ATTRS)})
    assert fan.compute(view) == {
        "Active": 1,
        "RotationSpeed": round(4 * 100 / 7, 4),  # medium = 4th of 7 speeds
        "TargetFanState": 0,
    }
    view.set(AC, "cool", {**AC_ATTRS, "fan_mode": "auto"})
    assert fan.compute(view)["TargetFanState"] == 1

    assert fan.handle({"RotationSpeed": 100}, view) == [Command("climate.set_fan_mode", target, {"fan_mode": "strong"})]
    assert fan.handle({"RotationSpeed": 10}, view) == [Command("climate.set_fan_mode", target, {"fan_mode": "quiet"})]
    assert fan.handle({"TargetFanState": 1}, view) == [Command("climate.set_fan_mode", target, {"fan_mode": "auto"})]
    assert fan.handle({"Active": 1}, view) == []  # already on
    assert fan.handle({"Active": 0}, view) == [Command("climate.turn_off", target)]
