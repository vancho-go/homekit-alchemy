"""Humidifiers, locks, valves, security systems, water heaters, scripts/scenes."""

from custom_components.homekit_alchemy.model.binding import Command
from custom_components.homekit_alchemy.presets.registry import MainOverrides, main_block
from tests.fakes import FakeView


def _fields(main) -> dict:
    return {f.kind: dict(f.properties) for f in main.behavior.fields()}


def test_humidifier_and_modes() -> None:
    attrs = {"device_class": "humidifier", "humidity": 65, "current_humidity": 45, "action": "humidifying",
             "min_humidity": 30, "max_humidity": 80, "available_modes": ["home", "eco"], "mode": "eco"}
    main = main_block("humidifier.h", attrs)
    assert (main.service, main.category) == ("HumidifierDehumidifier", "humidifier")
    assert _fields(main)["RelativeHumidityHumidifierThreshold"] == {"minValue": 30, "maxValue": 80, "minStep": 1}
    view = FakeView({"humidifier.h": ("on", attrs)})
    assert main.behavior.compute(view) == {
        "Active": 1, "TargetHumidifierDehumidifierState": 1, "CurrentHumidifierDehumidifierState": 2,
        "CurrentRelativeHumidity": 45, "RelativeHumidityHumidifierThreshold": 65,
    }
    target = {"entity_id": "humidifier.h"}
    assert main.behavior.handle({"RelativeHumidityHumidifierThreshold": 95}, view) == [
        Command("humidifier.set_humidity", target, {"humidity": 80})  # clamped to max_humidity
    ]
    eco = next(e for e in main.extras if e.name == "eco").behavior
    assert eco.compute(view) == {"On": True}
    assert eco.handle({"On": 1}, view) == [Command("humidifier.set_mode", target, {"mode": "eco"})]

    dry = main_block("humidifier.d", {"device_class": "dehumidifier"})
    assert dry.category == "dehumidifier" and "RelativeHumidityDehumidifierThreshold" in _fields(dry)


def test_lock_with_code() -> None:
    main = main_block("lock.door", {}, overrides=MainOverrides(code="1234"))
    view = FakeView({"lock.door": ("jammed", {})})
    assert main.behavior.compute(view) == {"LockCurrentState": 2}
    view.set("lock.door", "locked")
    assert main.behavior.compute(view) == {"LockCurrentState": 1, "LockTargetState": 1}
    assert main.behavior.handle({"LockTargetState": 0}, view) == [
        Command("lock.unlock", {"entity_id": "lock.door"}, {"code": "1234"})
    ]


def test_valves() -> None:
    main = main_block("valve.garden", {}, "sprinkler")
    assert (main.service, main.category) == ("Valve", "sprinkler")
    view = FakeView({"valve.garden": ("open", {})})
    assert main.behavior.compute(view) == {"Active": 1, "InUse": 1, "ValveType": 1}
    assert main.behavior.handle({"Active": 0}, view) == [Command("valve.close_valve", {"entity_id": "valve.garden"})]

    relay = main_block("switch.tap", {}, "faucet")
    assert relay.service == "Valve"
    assert relay.behavior.handle({"Active": 1}, FakeView()) == [
        Command("homeassistant.turn_on", {"entity_id": "switch.tap"})
    ]


def test_security_system() -> None:
    attrs = {"supported_features": 1 | 2 | 4 | 8}
    main = main_block("alarm_control_panel.home", attrs, overrides=MainOverrides(code="1234"))
    assert _fields(main)["SecuritySystemTargetState"]["ValidValues"] == {
        "StayArm": 0, "AwayArm": 1, "NightArm": 2, "Disarm": 3,
    }
    view = FakeView({"alarm_control_panel.home": ("triggered", attrs)})
    assert main.behavior.compute(view) == {"SecuritySystemCurrentState": 4}
    view.set("alarm_control_panel.home", "armed_night", attrs)
    assert main.behavior.compute(view) == {"SecuritySystemCurrentState": 2, "SecuritySystemTargetState": 2}
    assert main.behavior.handle({"SecuritySystemTargetState": 1}, view) == [
        Command("alarm_control_panel.alarm_arm_away", {"entity_id": "alarm_control_panel.home"}, {"code": "1234"})
    ]
    only_away = main_block("alarm_control_panel.x", {"supported_features": 2})
    assert _fields(only_away)["SecuritySystemTargetState"]["ValidValues"] == {"AwayArm": 1, "Disarm": 3}


def test_water_heater() -> None:
    attrs = {"temperature": 50, "current_temperature": 45, "min_temp": 30, "max_temp": 70,
             "operation_list": ["eco", "electric", "off"], "supported_features": 7}
    main = main_block("water_heater.boiler", attrs)
    assert main.service == "Thermostat"
    view = FakeView({"water_heater.boiler": ("eco", attrs)})
    values = main.behavior.compute(view)
    assert values["TargetHeatingCoolingState"] == 1 and values["CurrentHeatingCoolingState"] == 1
    target = {"entity_id": "water_heater.boiler"}
    assert main.behavior.handle({"TargetHeatingCoolingState": 0, "TargetTemperature": 55}, view) == [
        Command("water_heater.set_operation_mode", target, {"operation_mode": "off"}),
        Command("water_heater.set_temperature", target, {"temperature": 55}),
    ]


def test_activate_only() -> None:
    script = main_block("script.good_night", {})
    view = FakeView({"script.good_night": ("on", {}), "scene.movie": ("2026-10-24T20:00:00", {})})
    assert script.behavior.compute(view) == {"On": True}
    assert script.behavior.handle({"On": 0}, view) == [Command("script.turn_off", {"entity_id": "script.good_night"})]
    scene = main_block("scene.movie", {})
    assert scene.behavior.compute(view) == {"On": False}
    assert scene.behavior.handle({"On": 1}, view) == [Command("scene.turn_on", {"entity_id": "scene.movie"})]
    assert main_block("button.ring", {}).behavior.handle({"On": 1}, view) == [
        Command("button.press", {"entity_id": "button.ring"})
    ]


def test_humidifier_presets_renamed_and_hidden() -> None:
    attrs = {"device_class": "humidifier", "available_modes": ["Off", "Constant Humidity", "Sleep", "Strong"], "mode": "Sleep"}
    presets = (("Sleep", "Сон"), ("Constant Humidity", "Постоянная влажность"))
    main = main_block("humidifier.h", attrs, overrides=MainOverrides(presets=presets))
    assert [(e.key, e.name) for e in main.extras] == [
        ("humidifier:mode:sleep", "Сон"),
        ("humidifier:mode:constant_humidity", "Постоянная влажность"),
    ]
    import pytest
    from custom_components.homekit_alchemy.presets.registry import UnsupportedEntity

    with pytest.raises(UnsupportedEntity):
        main_block("humidifier.h", attrs, overrides=MainOverrides(presets=(("Turbo", "Турбо"),)))
