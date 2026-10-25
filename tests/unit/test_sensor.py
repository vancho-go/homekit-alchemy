from custom_components.homekit_alchemy.model.binding import Source
from custom_components.homekit_alchemy.presets.sensor import SENSOR_TYPES
from tests.fakes import FakeView


def _behavior(sensor_type: str, **source):
    return SENSOR_TYPES[sensor_type].create(Source(**source))


def test_temperature_rounding_and_fahrenheit() -> None:
    view = FakeView({"sensor.t": ("21.37", {})})
    assert _behavior("temperature", entity_id="sensor.t").compute(view) == {"CurrentTemperature": 21.4}
    view.set("sensor.t", "71.6", {"unit_of_measurement": "°F"})
    assert _behavior("temperature", entity_id="sensor.t").compute(view) == {"CurrentTemperature": 22.0}


def test_unknown_values_are_skipped() -> None:
    view = FakeView({"sensor.h": ("unavailable", {})})
    assert _behavior("humidity", entity_id="sensor.h").compute(view) == {}


def test_attribute_and_template_sources() -> None:
    view = FakeView({"climate.ac": ("cool", {"current_humidity": 44.6})})
    assert _behavior("humidity", entity_id="climate.ac", attribute="current_humidity").compute(view) == {
        "CurrentRelativeHumidity": 45
    }
    view.templates["{{ 12 }}"] = 12
    assert _behavior("humidity", template="{{ 12 }}").compute(view) == {"CurrentRelativeHumidity": 12}


def test_battery() -> None:
    view = FakeView({"sensor.b": ("15", {})})
    assert _behavior("battery", entity_id="sensor.b").compute(view) == {
        "BatteryLevel": 15, "StatusLowBattery": 1, "ChargingState": 2,
    }


def test_binary_sensors() -> None:
    view = FakeView({"binary_sensor.door": ("on", {}), "binary_sensor.pir": ("off", {})})
    assert _behavior("contact", entity_id="binary_sensor.door").compute(view) == {"ContactSensorState": 1}
    assert _behavior("motion", entity_id="binary_sensor.pir").compute(view) == {"MotionDetected": False}
    view.set("binary_sensor.pir", "unavailable")
    assert _behavior("motion", entity_id="binary_sensor.pir").compute(view) == {}


def test_co2() -> None:
    view = FakeView({"sensor.co2": ("1250", {})})
    assert _behavior("co2", entity_id="sensor.co2").compute(view) == {
        "CarbonDioxideLevel": 1250, "CarbonDioxideDetected": 1,
    }
