import pytest

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.registry import MainOverrides, UnsupportedEntity, main_block
from custom_components.homekit_alchemy.presets.switch import OnOffBehavior
from tests.fakes import FakeView


def test_switch_defaults_and_outlet() -> None:
    main = main_block("switch.kettle", {})
    assert (main.category, main.service) == ("switch", "Switch")
    outlet = main_block("input_boolean.x", {}, "outlet")
    assert outlet.service == "Outlet"
    view = FakeView({"input_boolean.x": ("on", {})})
    assert outlet.behavior.compute(view) == {"On": True, "OutletInUse": True}
    assert outlet.behavior.handle({"On": 0}, view) == [
        Command("homeassistant.turn_off", {"entity_id": "input_boolean.x"})
    ]


def test_sensor_main_by_device_class() -> None:
    assert main_block("sensor.t", {"device_class": "temperature"}).service == "TemperatureSensor"
    assert main_block("binary_sensor.d", {"device_class": "door"}).service == "ContactSensor"
    assert main_block("binary_sensor.x", {}).service == "OccupancySensor"
    assert main_block("sensor.x", {}, "humidity").service == "HumiditySensor"
    with pytest.raises(UnsupportedEntity):
        main_block("sensor.power", {"device_class": "power"})
    with pytest.raises(UnsupportedEntity):
        main_block("sensor.b", {"device_class": "battery"})


def test_unsupported() -> None:
    with pytest.raises(UnsupportedEntity):
        main_block("vacuum.robot", {})
    with pytest.raises(UnsupportedEntity):
        main_block("switch.x", {}, "temperature")


def test_overrides() -> None:
    overrides = MainOverrides(
        state=Source(entity_id="binary_sensor.relay"),
        turn_on=Command("script.on"),
    )
    main = main_block("switch.gate", {}, overrides=overrides)
    view = FakeView({"binary_sensor.relay": ("off", {})})
    assert main.behavior.compute(view) == {"On": False}
    assert main.behavior.handle({"On": 1}, view) == [Command("script.on")]
    assert main.behavior.handle({"On": 0}, view) == [
        Command("homeassistant.turn_off", {"entity_id": "switch.gate"})
    ]

    light = main_block("light.l", {"supported_color_modes": ["brightness"]}, overrides=overrides)
    view.set("light.l", "on", {"brightness": 255})
    assert light.behavior.compute(view)["On"] is False
    assert light.behavior.handle({"On": 1}, view) == [Command("script.on")]
    assert light.behavior.handle({"Brightness": 40}, view) == [
        Command("light.turn_on", {"entity_id": "light.l"}, {"brightness_pct": 40})
    ]


def test_stateless_switch_is_optimistic() -> None:
    behavior = OnOffBehavior(None, Command("script.on"), Command("script.off"))
    view = FakeView()
    assert behavior.compute(view) == {"On": False}
    behavior.handle({"On": 1}, view)
    assert behavior.compute(view) == {"On": True}
