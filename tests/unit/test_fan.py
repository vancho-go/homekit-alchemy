"""Fans and air purifiers, on attributes like the HA demo fans."""

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.registry import main_block
from custom_components.homekit_alchemy.presets.sensor import SENSOR_TYPES
from tests.fakes import FakeView

FULL = {  # demo "Living Room Fan": speed, oscillate, direction, presets
    "supported_features": 63,
    "percentage": 67,
    "percentage_step": 33.33,
    "direction": "forward",
    "oscillating": False,
    "preset_modes": ["auto", "smart", "sleep", "on"],
    "preset_mode": None,
}
ONE_PRESET = {"supported_features": 57, "percentage": 50, "preset_modes": ["auto"], "preset_mode": "auto"}
T = {"entity_id": "fan.f"}


def test_fan_fields_and_preset_switches() -> None:
    main = main_block("fan.f", FULL)
    assert (main.service, main.category) == ("Fanv2", "fan")
    assert [f.kind for f in main.behavior.fields()] == ["Active", "RotationSpeed", "RotationDirection", "SwingMode"]
    assert [(e.key, e.name, e.linked) for e in main.extras] == [
        ("fan:preset:auto", "auto", False),
        ("fan:preset:smart", "smart", False),
        ("fan:preset:sleep", "sleep", False),
        ("fan:preset:on", "on", False),
    ]
    one = main_block("fan.f", ONE_PRESET)
    assert "TargetFanState" in [f.kind for f in one.behavior.fields()] and not one.extras


def test_fan_compute_and_commands() -> None:
    behavior = main_block("fan.f", FULL).behavior
    view = FakeView({"fan.f": ("on", FULL)})
    assert behavior.compute(view) == {"Active": 1, "RotationSpeed": 67, "RotationDirection": 0, "SwingMode": 0}
    view.set("fan.f", "off", FULL)
    assert "RotationSpeed" not in behavior.compute(view)

    assert behavior.handle({"Active": 0, "RotationSpeed": 30}, view) == [Command("fan.turn_off", T)]
    assert behavior.handle({"Active": 1, "RotationSpeed": 30}, view) == [
        Command("fan.set_percentage", T, {"percentage": 33})
    ]
    assert behavior.handle({"Active": 1}, view) == [Command("fan.turn_on", T)]
    assert behavior.handle({"SwingMode": 1, "RotationDirection": 1}, view) == [
        Command("fan.oscillate", T, {"oscillating": True}),
        Command("fan.set_direction", T, {"direction": "reverse"}),
    ]


def test_speed_snaps_to_step() -> None:
    # 3 speeds: 67 % would round up to speed 3 in HA, so speed 2 must be sent as 66 %.
    behavior = main_block("fan.f", FULL).behavior
    view = FakeView({"fan.f": ("on", FULL)})
    sent = [behavior.handle({"RotationSpeed": v}, view)[0].data["percentage"] for v in (33.33, 66.66, 99.99, 100)]
    assert sent == [33, 66, 100, 100]


def test_preset_switch() -> None:
    sleep = next(e for e in main_block("fan.f", FULL).extras if e.name == "sleep").behavior
    view = FakeView({"fan.f": ("on", {**FULL, "preset_mode": "sleep"})})
    assert sleep.compute(view) == {"On": True}
    assert sleep.handle({"On": 1}, view) == [Command("fan.set_preset_mode", T, {"preset_mode": "sleep"})]
    assert sleep.handle({"On": 0}, view) == [Command("fan.turn_on", T)]


def test_air_purifier() -> None:
    main = main_block("fan.f", FULL, "air_purifier")
    assert (main.service, main.category) == ("AirPurifier", "air_purifier")
    assert [e.name for e in main.extras] == ["smart", "sleep", "on"]  # auto is the native toggle
    assert "pm25" in main.linked_sensor_types
    view = FakeView({"fan.f": ("on", {**FULL, "preset_mode": "auto"})})
    values = main.behavior.compute(view)
    assert values["TargetAirPurifierState"] == 1 and values["CurrentAirPurifierState"] == 2
    assert main.behavior.handle({"TargetAirPurifierState": 1}, view) == [
        Command("fan.set_preset_mode", T, {"preset_mode": "auto"})
    ]
    assert main.behavior.handle({"TargetAirPurifierState": 0}, view) == [
        Command("fan.turn_on", T, {"percentage": 67})
    ]


def test_pm_and_filter_sensors() -> None:
    view = FakeView({"sensor.pm": ("40", {}), "sensor.filter": ("7", {}), "binary_sensor.f": ("off", {})})
    assert SENSOR_TYPES["pm25"].create(Source(entity_id="sensor.pm")).compute(view) == {
        "PM2.5Density": 40.0, "AirQuality": 3,
    }
    assert SENSOR_TYPES["pm10"].create(Source(entity_id="sensor.pm")).compute(view)["AirQuality"] == 1
    assert SENSOR_TYPES["filter_life"].create(Source(entity_id="sensor.filter")).compute(view) == {
        "FilterLifeLevel": 7, "FilterChangeIndication": 1,
    }
    assert SENSOR_TYPES["filter_change"].create(Source(entity_id="binary_sensor.f")).compute(view) == {
        "FilterChangeIndication": 0,
    }


def test_fan_presets_renamed() -> None:
    from custom_components.homekit_alchemy.presets.registry import MainOverrides

    main = main_block("fan.f", FULL, overrides=MainOverrides(presets=(("sleep", "Сон"), ("smart", "Умный"))))
    assert [(e.key, e.name) for e in main.extras] == [("fan:preset:sleep", "Сон"), ("fan:preset:smart", "Умный")]
