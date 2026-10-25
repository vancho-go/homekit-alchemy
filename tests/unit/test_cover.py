"""Covers, tested on the attributes of the HA demo covers."""

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.cover import CoverOverrides
from custom_components.homekit_alchemy.presets.registry import MainOverrides, main_block
from tests.fakes import FakeView

# DemoCover supported_features: default = open|close|set_position|stop (+tilt when tilt given)
WINDOW = {"supported_features": 15, "current_position": 10}
WINDOW_TILT = {"supported_features": 255, "current_position": 70, "current_tilt_position": 50}
GARAGE = {"supported_features": 3, "device_class": "garage"}
PERGOLA = {"supported_features": 240, "current_tilt_position": 60}
BASIC = {"supported_features": 11}


def _main(entity_id, attrs, **kw):
    return main_block(entity_id, attrs, **kw)


def test_type_selection() -> None:
    assert _main("cover.w", WINDOW).service == "WindowCovering"
    assert _main("cover.g", GARAGE).service == "GarageDoorOpener"
    assert _main("cover.w", {**WINDOW, "device_class": "window"}).service == "Window"
    assert _main("cover.d", {**WINDOW, "device_class": "door"}).service == "Door"
    assert _main("cover.w", WINDOW, type_="garage_door").service == "GarageDoorOpener"


def test_position_cover() -> None:
    behavior = _main("cover.w", WINDOW_TILT).behavior
    kinds = [f.kind for f in behavior.fields()]
    assert kinds == [
        "CurrentPosition", "TargetPosition", "PositionState", "HoldPosition",
        "CurrentHorizontalTiltAngle", "TargetHorizontalTiltAngle",
    ]
    view = FakeView({"cover.w": ("open", WINDOW_TILT)})
    assert behavior.compute(view) == {
        "PositionState": 2, "CurrentPosition": 70, "TargetPosition": 70,
        "CurrentHorizontalTiltAngle": 0, "TargetHorizontalTiltAngle": 0,
    }
    target = {"entity_id": "cover.w"}
    assert behavior.handle({"TargetPosition": 40}, view) == [
        Command("cover.set_cover_position", target, {"position": 40})
    ]
    assert behavior.handle({"HoldPosition": True}, view) == [Command("cover.stop_cover", target)]
    assert behavior.handle({"TargetHorizontalTiltAngle": 90}, view) == [
        Command("cover.set_cover_tilt_position", target, {"tilt_position": 100})
    ]


def test_moving_target_never_behind() -> None:
    behavior = _main("cover.w", WINDOW).behavior
    view = FakeView({"cover.w": ("opening", {**WINDOW, "current_position": 30})})
    values = behavior.compute(view)
    assert values["PositionState"] == 1 and values["TargetPosition"] == 100
    behavior.handle({"TargetPosition": 60}, view)
    view.set("cover.w", "opening", {**WINDOW, "current_position": 50})
    assert "TargetPosition" not in behavior.compute(view)  # still heading to 60


def test_basic_and_tilt_only() -> None:
    basic = _main("cover.b", BASIC).behavior
    view = FakeView({"cover.b": ("open", BASIC)})
    assert basic.compute(view)["CurrentPosition"] == 100
    target = {"entity_id": "cover.b"}
    assert basic.handle({"TargetPosition": 0}, view) == [Command("cover.close_cover", target)]
    assert basic.handle({"TargetPosition": 50}, view) == [Command("cover.stop_cover", target)]
    assert basic.handle({"TargetPosition": 100}, view) == [Command("cover.open_cover", target)]

    pergola = _main("cover.p", PERGOLA).behavior
    assert [f.kind for f in pergola.fields()] == ["CurrentPosition", "TargetPosition", "PositionState", "HoldPosition"]
    view = FakeView({"cover.p": ("closed", PERGOLA)})
    assert pergola.compute(view)["CurrentPosition"] == 60  # main slider = tilt
    assert pergola.handle({"TargetPosition": 20, "HoldPosition": True}, view) == [
        Command("cover.stop_cover_tilt", {"entity_id": "cover.p"}),
        Command("cover.set_cover_tilt_position", {"entity_id": "cover.p"}, {"tilt_position": 20}),
    ]


def test_garage_with_overrides() -> None:
    overrides = MainOverrides(
        state=Source(entity_id="binary_sensor.gate_contact"),
        cover=CoverOverrides(
            open=Command("switch.turn_on", {"entity_id": "switch.relay"}),
            close=Command("switch.turn_on", {"entity_id": "switch.relay"}),
            obstruction=Source(entity_id="binary_sensor.gate_obstacle"),
        ),
    )
    garage = _main("switch.relay_cover", GARAGE)  # not a cover: must not be a garage
    assert garage.service == "Switch"

    behavior = main_block("cover.gate", GARAGE, overrides=overrides).behavior
    view = FakeView({
        "cover.gate": ("closed", GARAGE),
        "binary_sensor.gate_contact": ("on", {}),
        "binary_sensor.gate_obstacle": ("off", {}),
    })
    assert behavior.compute(view) == {"CurrentDoorState": 0, "TargetDoorState": 0, "ObstructionDetected": False}
    assert behavior.handle({"TargetDoorState": 1}, view) == [Command("switch.turn_on", {"entity_id": "switch.relay"})]
    assert set(behavior.sources()) == {
        Source(entity_id="cover.gate"),
        Source(entity_id="binary_sensor.gate_contact"),
        Source(entity_id="binary_sensor.gate_obstacle"),
    }


def test_relay_as_garage_door() -> None:
    """A relay switch shown as a gate (state from a reed switch)."""
    overrides = MainOverrides(state=Source(entity_id="binary_sensor.gate_contact"))
    main = main_block("switch.gate_relay", {}, "garage_door", overrides)
    assert (main.service, main.category) == ("GarageDoorOpener", "garage_door")
    view = FakeView({"switch.gate_relay": ("off", {}), "binary_sensor.gate_contact": ("off", {})})
    assert main.behavior.compute(view)["CurrentDoorState"] == 1  # closed per the reed switch
    assert main.behavior.handle({"TargetDoorState": 0}, view) == [
        Command("homeassistant.turn_on", {"entity_id": "switch.gate_relay"})
    ]

    blind = main_block("input_boolean.blind", {}, "window_covering")
    view = FakeView({"input_boolean.blind": ("on", {})})
    assert blind.behavior.compute(view)["CurrentPosition"] == 100
