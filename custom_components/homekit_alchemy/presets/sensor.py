"""Read-only sensors: numeric readings, binary detectors and battery.

`SENSOR_TYPES` is the single list of sensor types users can write in
`type:` (main entity) or `sensors: - type:` (extra blocks).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Source
from .convert import clamp, fahrenheit_to_celsius, to_bool, to_float

LOW_BATTERY_THRESHOLD = 20
NOT_CHARGEABLE = 2  # Apple ChargingState
CO2_ABNORMAL_PPM = 1000


@dataclass(frozen=True)
class NumericSensorType:
    """A sensor whose Apple service has one numeric reading."""

    service: str
    field: str
    properties: dict[str, Any] = field(default_factory=dict)
    integer: bool = False


@dataclass(frozen=True)
class BinarySensorType:
    """A detector: Apple field value for 'detected' (on) and 'clear' (off)."""

    service: str
    field: str
    on_value: Any = 1
    off_value: Any = 0


NUMERIC_SENSOR_TYPES: dict[str, NumericSensorType] = {
    "temperature": NumericSensorType(
        "TemperatureSensor",
        "CurrentTemperature",
        {"minValue": -100, "maxValue": 200, "minStep": 0.1},
    ),
    "humidity": NumericSensorType(
        "HumiditySensor", "CurrentRelativeHumidity", {"minStep": 1}, integer=True
    ),
    "illuminance": NumericSensorType(
        "LightSensor", "CurrentAmbientLightLevel", {"minValue": 0.0001, "maxValue": 100000}
    ),
}

BINARY_SENSOR_TYPES: dict[str, BinarySensorType] = {
    "motion": BinarySensorType("MotionSensor", "MotionDetected", True, False),
    "occupancy": BinarySensorType("OccupancySensor", "OccupancyDetected"),
    # Apple: 0 = contact detected (closed), 1 = no contact (open).
    "contact": BinarySensorType("ContactSensor", "ContactSensorState"),
    "leak": BinarySensorType("LeakSensor", "LeakDetected"),
    "smoke": BinarySensorType("SmokeSensor", "SmokeDetected"),
    "co": BinarySensorType("CarbonMonoxideSensor", "CarbonMonoxideDetected"),
}


class NumericSensorBehavior(Behavior):
    """A single numeric reading from any Home Assistant source."""

    def __init__(self, sensor_type: str, source: Source) -> None:
        self.type = NUMERIC_SENSOR_TYPES[sensor_type]
        self.sensor_type = sensor_type
        self.source = source

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec(self.type.field, self.type.properties)]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = to_float(view.value(self.source))
        if value is None:
            return {}
        if self.sensor_type == "temperature" and _unit(view, self.source) == "°F":
            value = fahrenheit_to_celsius(value)
        props = self.type.properties
        value = clamp(value, props.get("minValue", 0), props.get("maxValue", 100))
        return {self.type.field: round(value) if self.type.integer else round(value, 1)}


class BinarySensorBehavior(Behavior):
    """Detector (motion, contact, leak…) from any on/off-like source."""

    def __init__(self, sensor_type: str, source: Source) -> None:
        self.type = BINARY_SENSOR_TYPES[sensor_type]
        self.source = source

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec(self.type.field)]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        detected = to_bool(view.value(self.source))
        if detected is None:
            return {}
        return {self.type.field: self.type.on_value if detected else self.type.off_value}


class CarbonDioxideBehavior(Behavior):
    """CO2 level in ppm plus the 'abnormal' flag Apple requires."""

    def __init__(self, source: Source, threshold: float = CO2_ABNORMAL_PPM) -> None:
        self.source = source
        self.threshold = threshold

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("CarbonDioxideDetected"),
            FieldSpec("CarbonDioxideLevel", {"minValue": 0, "maxValue": 100000}),
        ]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = to_float(view.value(self.source))
        if value is None:
            return {}
        return {
            "CarbonDioxideLevel": round(clamp(value, 0, 100000)),
            "CarbonDioxideDetected": int(value > self.threshold),
        }


# PM density (µg/m³) -> Apple AirQuality 1 (excellent) .. 5 (poor); same breakpoints as HA.
PM25_BREAKPOINTS = (9, 35.4, 55.4, 125.4)
PM10_BREAKPOINTS = (54, 154, 254, 354)


def _air_quality(density: float, breakpoints: tuple[float, ...]) -> int:
    return next((i + 1 for i, limit in enumerate(breakpoints) if density <= limit), 5)


class ParticulateBehavior(Behavior):
    """PM2.5 / PM10 as an Apple AirQualitySensor (quality level + density)."""

    def __init__(self, field: str, breakpoints: tuple[float, ...], source: Source) -> None:
        self.field = field
        self.breakpoints = breakpoints
        self.source = source

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("AirQuality"), FieldSpec(self.field, {"maxValue": 1000})]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = to_float(view.value(self.source))
        if value is None:
            return {}
        density = clamp(value, 0, 1000)
        return {self.field: round(density, 1), "AirQuality": _air_quality(density, self.breakpoints)}


class FilterBehavior(Behavior):
    """Filter maintenance from a life-left percentage or from a 'replace filter' flag."""

    def __init__(self, source: Source, percentage: bool, change_below: float = 10) -> None:
        self.source = source
        self.percentage = percentage
        self.change_below = change_below

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("FilterChangeIndication")]
        if self.percentage:
            fields.append(FieldSpec("FilterLifeLevel"))
        return fields

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        raw = view.value(self.source)
        if self.percentage:
            life = to_float(raw)
            if life is None:
                return {}
            life = clamp(life, 0, 100)
            return {"FilterLifeLevel": round(life), "FilterChangeIndication": int(life < self.change_below)}
        change = to_bool(raw)
        return {} if change is None else {"FilterChangeIndication": int(change)}


class BatteryBehavior(Behavior):
    """Battery level with low-battery flag."""

    def __init__(self, source: Source, low_threshold: int = LOW_BATTERY_THRESHOLD) -> None:
        self.source = source
        self.low_threshold = low_threshold

    def fields(self) -> list[FieldSpec]:
        return [
            FieldSpec("BatteryLevel"),
            FieldSpec("StatusLowBattery"),
            FieldSpec("ChargingState"),
        ]

    def sources(self) -> list[Source]:
        return [self.source]

    def compute(self, view: StateView) -> dict[str, Any]:
        value = to_float(view.value(self.source))
        if value is None:
            return {}
        level = round(clamp(value, 0, 100))
        return {
            "BatteryLevel": level,
            "StatusLowBattery": int(level < self.low_threshold),
            "ChargingState": NOT_CHARGEABLE,
        }


@dataclass(frozen=True)
class SensorType:
    """A user-facing sensor type: Apple service + behavior factory."""

    service: str
    create: Callable[[Source], Behavior]


SENSOR_TYPES: dict[str, SensorType] = {
    **{
        name: SensorType(spec.service, lambda source, name=name: NumericSensorBehavior(name, source))
        for name, spec in NUMERIC_SENSOR_TYPES.items()
    },
    **{
        name: SensorType(spec.service, lambda source, name=name: BinarySensorBehavior(name, source))
        for name, spec in BINARY_SENSOR_TYPES.items()
    },
    "co2": SensorType("CarbonDioxideSensor", CarbonDioxideBehavior),
    "pm25": SensorType("AirQualitySensor", lambda source: ParticulateBehavior("PM2.5Density", PM25_BREAKPOINTS, source)),
    "pm10": SensorType("AirQualitySensor", lambda source: ParticulateBehavior("PM10Density", PM10_BREAKPOINTS, source)),
    "filter_life": SensorType("FilterMaintenance", lambda source: FilterBehavior(source, percentage=True)),
    "filter_change": SensorType("FilterMaintenance", lambda source: FilterBehavior(source, percentage=False)),
    "battery": SensorType("BatteryService", BatteryBehavior),
}

# Home Assistant device_class -> sensor type, used for main entities.
SENSOR_DEVICE_CLASSES = {
    "temperature": "temperature",
    "humidity": "humidity",
    "illuminance": "illuminance",
    "carbon_dioxide": "co2",
    "pm25": "pm25",
    "pm10": "pm10",
    "battery": "battery",
}
BINARY_SENSOR_DEVICE_CLASSES = {
    "motion": "motion",
    "occupancy": "occupancy",
    "presence": "occupancy",
    "door": "contact",
    "window": "contact",
    "opening": "contact",
    "garage_door": "contact",
    "moisture": "leak",
    "smoke": "smoke",
    "carbon_monoxide": "co",
    "gas": "co",
}
DEFAULT_BINARY_SENSOR_TYPE = "occupancy"


def _unit(view: StateView, source: Source) -> str | None:
    if source.entity_id is None or source.attribute is not None:
        return None
    state = view.state(source.entity_id)
    return state.attributes.get("unit_of_measurement") if state else None
