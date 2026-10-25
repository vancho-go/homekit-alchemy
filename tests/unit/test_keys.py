import pytest

from custom_components.homekit_alchemy.model import keys
from custom_components.homekit_alchemy.model.binding import Source


def test_device_key_prefers_unique_id() -> None:
    assert keys.device_key("light.a", "abc") == "uid:abc"
    assert keys.device_key("light.a", None) == "eid:light.a"


def test_block_keys() -> None:
    assert keys.sensor_key("temperature") == "sensor:temperature"
    assert keys.switch_key(block_id="x", entity_id="switch.a") == "switch:id:x"
    assert keys.switch_key(entity_id="switch.a", name="N") == "switch:entity:switch.a"
    assert keys.switch_key(name="Тихий режим") == "switch:name:тихий_режим"


def test_source_validation() -> None:
    with pytest.raises(ValueError):
        Source()
    with pytest.raises(ValueError):
        Source(entity_id="a.b", template="{{ 1 }}")
    with pytest.raises(ValueError):
        Source(template="{{ 1 }}", attribute="x")


def test_block_names_follow_language() -> None:
    from custom_components.homekit_alchemy.presets.names import block_name

    assert block_name("fan", "ru") == "Вентилятор"
    assert block_name("fan", "en-GB") == "Fan"
    assert block_name("fan", "de") == "Fan"
