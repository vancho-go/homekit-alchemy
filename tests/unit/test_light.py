from custom_components.homekit_alchemy.model.binding import Command
from custom_components.homekit_alchemy.presets.light import LightBehavior
from tests.fakes import FakeView

LIGHT = "light.lamp"
ATTRS = {
    "supported_color_modes": ["color_temp", "hs"],
    "min_color_temp_kelvin": 2700,
    "max_color_temp_kelvin": 6500,
}


def test_fields_follow_color_modes() -> None:
    assert [f.kind for f in LightBehavior(LIGHT, ["onoff"]).fields()] == ["On"]
    kinds = [f.kind for f in LightBehavior.from_attributes(LIGHT, ATTRS).fields()]
    assert kinds == ["On", "Brightness", "ColorTemperature", "Hue", "Saturation"]


def test_compute_on_and_off() -> None:
    behavior = LightBehavior.from_attributes(LIGHT, ATTRS)
    view = FakeView()
    view.set(LIGHT, "on", {"brightness": 128, "color_temp_kelvin": 4000, "hs_color": [30, 60]})
    assert behavior.compute(view) == {
        "On": True, "Brightness": 50, "ColorTemperature": 250, "Hue": 30, "Saturation": 60,
    }
    view.set(LIGHT, "off")
    assert behavior.compute(view) == {"On": False}
    view.set(LIGHT, "unavailable")
    assert behavior.compute(view) == {}


def test_handle_commands() -> None:
    behavior = LightBehavior.from_attributes(LIGHT, ATTRS)
    view = FakeView({LIGHT: ("on", {"hs_color": [10, 20]})})
    target = {"entity_id": LIGHT}
    assert behavior.handle({"On": 0}, view) == [Command("light.turn_off", target)]
    assert behavior.handle({"On": 1}, view) == [Command("light.turn_on", target, {})]
    assert behavior.handle({"On": 1, "Brightness": 30}, view) == [
        Command("light.turn_on", target, {"brightness_pct": 30})
    ]
    assert behavior.handle({"Hue": 200}, view) == [
        Command("light.turn_on", target, {"hs_color": [200, 20]})
    ]
    assert behavior.handle({"ColorTemperature": 250}, view) == [
        Command("light.turn_on", target, {"color_temp_kelvin": 4000})
    ]
