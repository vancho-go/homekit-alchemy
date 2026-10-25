"""Ranges and modes."""

import pytest

from custom_components.homekit_alchemy.model.binding import Command, Source
from custom_components.homekit_alchemy.presets.flex import (
    ModeOptionBehavior,
    ModeSliderBehavior,
    ModeSpec,
    RangeBehavior,
)
from tests.fakes import FakeView

SET = Command("number.set_value", {"entity_id": "number.v"}, {"value": "{{ value }}"})


def test_range_percent_and_snap() -> None:
    rng = RangeBehavior(Source(entity_id="number.v"), SET, 0, 1, 0.05)
    view = FakeView({"number.v": ("0.5", {})})
    assert rng.compute(view) == {"On": True, "Brightness": 50}
    assert rng.handle({"Brightness": 33}, view) == [SET.with_variables(value=0.35)]
    view.set("number.v", "0")
    assert rng.compute(view) == {"On": False}


def test_range_on_off_restores_last() -> None:
    rng = RangeBehavior(Source(entity_id="number.v"), SET, 10, 30, 1)
    view = FakeView({"number.v": ("20", {})})
    rng.compute(view)
    assert rng.handle({"On": 0}, view) == [SET.with_variables(value=10)]
    view.set("number.v", "10")
    rng.compute(view)
    assert rng.handle({"On": 1}, view) == [SET.with_variables(value=20)]
    assert rng.handle({"On": 1, "Brightness": 100}, view) == [SET.with_variables(value=30)]
    with pytest.raises(ValueError):
        RangeBehavior(Source(entity_id="number.v"), SET, 5, 5, 1)


SPEC = ModeSpec(
    Source(entity_id="select.speed"),
    (("low", "Тихо"), ("medium", "Средне"), ("high", "Сильно")),
    Command("select.select_option", {"entity_id": "select.speed"}, {"option": "{{ option }}"}),
)


def test_mode_switches() -> None:
    medium = ModeOptionBehavior(SPEC, "medium")
    view = FakeView({"select.speed": ("medium", {})})
    assert medium.compute(view) == {"On": True}
    assert ModeOptionBehavior(SPEC, "low").compute(view) == {"On": False}
    assert medium.handle({"On": 1}, view) == [SPEC.command("medium")]
    assert medium.handle({"On": 0}, view) == []
    assert SPEC.command("medium").variables == {"option": "medium", "value": "medium"}


def test_mode_slider() -> None:
    slider = ModeSliderBehavior(SPEC)
    view = FakeView({"select.speed": ("high", {})})
    assert slider.compute(view) == {"On": True, "Brightness": 100}
    view.set("select.speed", "low")
    assert slider.compute(view) == {"On": True, "Brightness": 33}
    assert slider.handle({"Brightness": 40}, view) == [SPEC.command("medium")]
    assert slider.handle({"Brightness": 1}, view) == [SPEC.command("low")]
    assert slider.handle({"On": 0}, view) == []


from custom_components.homekit_alchemy.presets.flex import (  # noqa: E402
    ButtonBehavior,
    ServiceLabelBehavior,
    guess_presses,
)


def test_guess_presses() -> None:
    assert guess_presses(["press"]) == {"press": 0}
    assert guess_presses(["single_press", "double_press", "long_press", "release"]) == {
        "single_press": 0, "double_press": 1, "long_press": 2,
    }


def test_event_button_fires_only_on_new_events() -> None:
    btn = ButtonBehavior("event.sw", {"single": 0, "double": 1}, "event_type")
    fields = {f.kind: dict(f.properties) for f in btn.fields()}
    assert fields["ProgrammableSwitchEvent"] == {"ValidValues": {"SinglePress": 0, "DoublePress": 1}}

    view = FakeView({"event.sw": ("2026-10-25T10:00:00", {"event_type": "single"})})
    assert btn.compute(view) == {}  # startup: remember, do not fire
    assert btn.compute(view) == {}  # unrelated refresh
    view.set("event.sw", "2026-10-25T10:00:05", {"event_type": "double"})
    assert btn.compute(view) == {"ProgrammableSwitchEvent": 1}
    view.set("event.sw", "2026-10-25T10:00:09", {"event_type": "double"})
    assert btn.compute(view) == {"ProgrammableSwitchEvent": 1}  # same kind again still fires
    view.set("event.sw", "2026-10-25T10:00:12", {"event_type": "release"})
    assert btn.compute(view) == {}  # unmapped


def test_state_button_and_label() -> None:
    btn = ButtonBehavior("sensor.action", {"hold": 2}, index=2)
    view = FakeView({"sensor.action": ("", {})})
    assert btn.compute(view) == {"ServiceLabelIndex": 2}
    view.set("sensor.action", "hold")
    assert btn.compute(view) == {"ServiceLabelIndex": 2, "ProgrammableSwitchEvent": 2}
    assert ServiceLabelBehavior().compute(view) == {"ServiceLabelNamespace": 1}


from custom_components.homekit_alchemy.presets.flex import (  # noqa: E402
    InputSourceBehavior,
    TelevisionModeBehavior,
    display_order,
)


def test_display_order_tlv() -> None:
    import base64

    raw = base64.b64decode(display_order([0, 1, 258]))
    assert raw == bytes([1, 4, 0, 0, 0, 0, 0, 0, 1, 4, 1, 0, 0, 0, 0, 0, 1, 4, 2, 1, 0, 0])


def test_television_mode() -> None:
    tv = TelevisionModeBehavior(SPEC)
    view = FakeView({"select.speed": ("high", {})})
    values = tv.compute(view)
    assert values["ActiveIdentifier"] == 3 and values["Active"] == 1
    assert values["DisplayOrder"] == display_order([1, 2, 3])
    assert tv.handle({"ActiveIdentifier": 1}, view) == [SPEC.command("low")]
    assert tv.handle({"ActiveIdentifier": 0}, view) == []
    assert tv.handle({"ActiveIdentifier": 7}, view) == []
    assert tv.handle({"Active": 0}, view) == []
    assert InputSourceBehavior(1).compute(view)["Identifier"] == 1
