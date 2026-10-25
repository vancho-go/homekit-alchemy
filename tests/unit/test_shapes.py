"""On/off entities shown as other Apple devices; thermostats assembled from parts."""

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.climate import ClimateOverrides
from custom_components.homekit_alchemy.presets.registry import MainOverrides, main_block, supported_types
from tests.fakes import FakeView


def test_light_can_take_any_shape() -> None:
    assert {"fan", "thermostat", "valve", "garage_door", "outlet"} <= supported_types("light")


def test_light_relay_as_inverted_valve() -> None:
    """A water shut-off relay: relay on = water closed."""
    relay = "light.water_stop"
    overrides = MainOverrides(
        state=Source(template="{{ is_state('light.water_stop', 'off') }}"),
        turn_on=Command("light.turn_off", {"entity_id": relay}),
        turn_off=Command("light.turn_on", {"entity_id": relay}),
    )
    main = main_block(relay, {}, "valve", overrides)
    assert main.service == "Valve"
    view = FakeView({relay: ("on", {})})
    view.templates["{{ is_state('light.water_stop', 'off') }}"] = False
    assert main.behavior.compute(view)["Active"] == 0  # relay on -> water closed
    assert main.behavior.handle({"Active": 1}, view) == [Command("light.turn_off", {"entity_id": relay})]


def test_light_as_fan() -> None:
    main = main_block("light.exhaust", {}, "fan")
    assert (main.service, main.category) == ("Fanv2", "fan")
    view = FakeView({"light.exhaust": ("on", {})})
    assert main.behavior.compute(view) == {"Active": 1}
    assert main.behavior.handle({"Active": 0}, view) == [
        Command("homeassistant.turn_off", {"entity_id": "light.exhaust"})
    ]


def test_assembled_thermostat() -> None:
    overrides = MainOverrides(
        climate=ClimateOverrides(
            current_temperature=Source(entity_id="sensor.rail_temp"),
            target_temperature="number.rail_target",
            min_temp=30,
            max_temp=60,
        )
    )
    main = main_block("switch.rail", {}, "thermostat", overrides)
    assert (main.service, main.category) == ("Thermostat", "thermostat")
    fields = {f.kind: dict(f.properties) for f in main.behavior.fields()}
    assert fields["TargetTemperature"] == {"minValue": 30, "maxValue": 60, "minStep": 1}
    assert fields["TargetHeatingCoolingState"] == {"ValidValues": {"Off": 0, "Heat": 1}}

    view = FakeView({"switch.rail": ("on", {}), "sensor.rail_temp": ("41", {}), "number.rail_target": ("45", {})})
    assert main.behavior.compute(view) == {
        "TemperatureDisplayUnits": 0,
        "TargetHeatingCoolingState": 1,
        "CurrentTemperature": 41.0,
        "TargetTemperature": 45.0,
        "CurrentHeatingCoolingState": 1,
    }
    assert main.behavior.handle({"TargetTemperature": 50, "TargetHeatingCoolingState": 0}, view) == [
        Command("homeassistant.turn_off", {"entity_id": "switch.rail"}),
        Command("number.set_value", {"entity_id": "number.rail_target"}, {"value": 50}),
    ]


def test_assembled_thermostat_needs_target() -> None:
    import pytest
    from custom_components.homekit_alchemy.presets.registry import UnsupportedEntity

    with pytest.raises(UnsupportedEntity):
        main_block("switch.rail", {}, "thermostat")
