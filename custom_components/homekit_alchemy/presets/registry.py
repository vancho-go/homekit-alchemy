"""Default representation of a main entity, by Home Assistant domain."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..model.behavior import Behavior
from ..model.binding import Command, Source
from ..model.keys import slugify
from .climate import (
    ClimateFanBehavior,
    ClimateOverrides,
    HeaterCoolerBehavior,
    ThermostatBehavior,
    WaterHeaterBehavior,
)
from .cover import (
    COVER_TYPES,
    CoverOverrides,
    GarageDoorBehavior,
    PositionCoverBehavior,
    default_cover_type,
)
from .devices import (
    ACTIVATE_ACTIONS,
    VALVE_TYPES,
    ActivateBehavior,
    HumidifierBehavior,
    HumidifierModeBehavior,
    LockBehavior,
    SecuritySystemBehavior,
    ValveBehavior,
)
from .fan import FanBehavior, FanPresetBehavior
from .flex import MAX_TV_OPTIONS, ButtonBehavior, InputSourceBehavior, guess_presses, input_identifier
from .light import LightBehavior
from .media import MediaPowerBehavior, TelevisionMediaBehavior, TelevisionSpeakerBehavior
from .sensor import (
    BINARY_SENSOR_DEVICE_CLASSES,
    DEFAULT_BINARY_SENSOR_TYPE,
    SENSOR_DEVICE_CLASSES,
    SENSOR_TYPES,
)
from .switch import ONOFF_SERVICES, OnOffBehavior

ONOFF_DOMAINS = {"switch", "input_boolean"}
ONOFF_TYPES = set(ONOFF_SERVICES)
CLIMATE_TYPES = {"thermostat", "heater_cooler"}
FAN_TYPES = {"fan", "air_purifier"}
MEDIA_TYPES = {"television", "receiver", "switch"}
FEATURE_SELECT_SOURCE = 2048
# Extra sensors Apple shows inside an air purifier when linked to it.
PURIFIER_LINKED_SENSORS = frozenset({"pm25", "pm10", "temperature", "humidity", "filter_life", "filter_change"})


@dataclass(frozen=True)
class MainOverrides:
    """User overrides of the main block (state / turn_on / turn_off)."""

    state: Source | None = None
    turn_on: Command | None = None
    turn_off: Command | None = None
    climate: ClimateOverrides = ClimateOverrides()
    cover: CoverOverrides = CoverOverrides()
    code: str | None = None  # lock / alarm code
    sources: tuple[tuple[str, str], ...] | None = None  # media_player inputs (value, label)
    remote_keys: Mapping[str, Command] | None = None  # media_player remote key -> command


@dataclass(frozen=True)
class ExtraBlock:
    """A block the preset adds next to the main one (e.g. a climate fan)."""

    key: str
    service: str
    behavior: Behavior
    name_key: str | None = None  # looked up in names.py in the HA language…
    name: str | None = None  # …or a literal name (e.g. a fan preset)
    linked: bool = False  # shown as part of the main block rather than on its own


@dataclass(frozen=True)
class MainBlock:
    """What the main entity becomes in Apple Home."""

    category: str
    service: str
    behavior: Behavior
    extras: tuple[ExtraBlock, ...] = ()
    linked_sensor_types: frozenset[str] = frozenset()  # `sensors:` of these types get linked
    standalone: bool = False  # needs its own pairing (televisions)


class UnsupportedEntity(ValueError):
    """The entity (or requested type) cannot be shown in Apple Home yet."""


def supported_types(domain: str) -> set[str]:
    """`type:` values allowed for a domain (for config validation messages)."""
    if domain in ONOFF_DOMAINS:
        return ONOFF_TYPES | set(COVER_TYPES) | set(VALVE_TYPES)
    if domain == "valve":
        return set(VALVE_TYPES)
    if domain == "light":
        return ONOFF_TYPES
    if domain in ("sensor", "binary_sensor"):
        return set(SENSOR_TYPES) - {"battery"}
    if domain == "climate":
        return CLIMATE_TYPES
    if domain == "fan":
        return FAN_TYPES
    if domain == "media_player":
        return MEDIA_TYPES
    if domain == "cover":
        return set(COVER_TYPES)
    return set()


def main_block(
    entity_id: str,
    attributes: Mapping[str, Any],
    type_: str | None = None,
    overrides: MainOverrides = MainOverrides(),
    temperature_unit: str = "°C",
) -> MainBlock:
    domain = entity_id.split(".", 1)[0]

    if domain == "climate":
        if type_ is None:
            type_ = "heater_cooler" if "cool" in (attributes.get("hvac_modes") or []) else "thermostat"
        if type_ not in CLIMATE_TYPES:
            raise UnsupportedEntity(f"type '{type_}' is not available for climate")
        extras: list[ExtraBlock] = []
        if ClimateFanBehavior.applies(attributes):
            extras.append(
                ExtraBlock("climate:fan", "Fanv2", ClimateFanBehavior(entity_id, attributes), name_key="fan", linked=True)
            )
        if type_ == "heater_cooler":
            if overrides.climate.current_humidity is not None:
                raise UnsupportedEntity(
                    "heater_cooler has no humidity field; add it with sensors: - type: humidity"
                )
            behavior = HeaterCoolerBehavior(entity_id, attributes, temperature_unit, overrides.climate)
            return MainBlock("air_conditioner", "HeaterCooler", behavior, tuple(extras))
        behavior = ThermostatBehavior(entity_id, attributes, temperature_unit, overrides.climate)
        return MainBlock("thermostat", "Thermostat", behavior, tuple(extras))

    if domain == "cover" or (type_ in COVER_TYPES and domain in ONOFF_DOMAINS):
        type_ = type_ or default_cover_type(attributes)
        if type_ not in COVER_TYPES:
            raise UnsupportedEntity(f"type '{type_}' is not available for cover")
        service, category = COVER_TYPES[type_]
        state = overrides.state or overrides.cover.state
        open_cmd, close_cmd = overrides.cover.open, overrides.cover.close
        if domain != "cover":
            # A relay / input_boolean shown as a gate or blind: on = open.
            default = OnOffBehavior.for_entity(entity_id)
            state = state or default.state
            open_cmd = open_cmd or default.turn_on
            close_cmd = close_cmd or default.turn_off
        cover_overrides = CoverOverrides(
            state=state,
            open=open_cmd,
            close=close_cmd,
            stop=overrides.cover.stop,
            obstruction=overrides.cover.obstruction,
        )
        cls = GarageDoorBehavior if type_ == "garage_door" else PositionCoverBehavior
        return MainBlock(category, service, cls(entity_id, attributes, cover_overrides))

    if domain == "media_player":
        return _media_player(entity_id, attributes, type_, overrides)

    if domain == "event":
        presses = guess_presses([str(t) for t in attributes.get("event_types") or []])
        if not presses:
            raise UnsupportedEntity("cannot guess presses from event_types; describe them in 'buttons'")
        return MainBlock("programmable_switch", "StatelessProgrammableSwitch", ButtonBehavior(entity_id, presses, "event_type"))

    if domain in ACTIVATE_ACTIONS:
        return MainBlock("switch", "Switch", ActivateBehavior(entity_id))

    if domain == "lock":
        return MainBlock("lock", "LockMechanism", LockBehavior(entity_id, overrides.code))

    if domain == "alarm_control_panel":
        return MainBlock("security", "SecuritySystem", SecuritySystemBehavior(entity_id, attributes, overrides.code))

    if domain == "water_heater":
        return MainBlock("thermostat", "Thermostat", WaterHeaterBehavior(entity_id, attributes, temperature_unit, overrides.climate))

    if domain == "humidifier":
        behavior = HumidifierBehavior(entity_id, attributes, overrides.climate.current_humidity)
        modes = tuple(
            ExtraBlock(HumidifierModeBehavior.key(m), "Switch", HumidifierModeBehavior(entity_id, m), name=str(m))
            for m in attributes.get("available_modes") or []
        )
        category = "dehumidifier" if attributes.get("device_class") == "dehumidifier" else "humidifier"
        return MainBlock(category, "HumidifierDehumidifier", behavior, modes)

    if domain == "valve" or (type_ in VALVE_TYPES and domain in ONOFF_DOMAINS):
        type_ = type_ or "valve"
        if type_ not in VALVE_TYPES:
            raise UnsupportedEntity(f"type '{type_}' is not available for {domain}")
        apple_type, category = VALVE_TYPES[type_]
        if domain == "valve":
            behavior = ValveBehavior.for_valve_entity(entity_id, apple_type)
        else:
            default = OnOffBehavior.for_entity(entity_id)
            behavior = ValveBehavior(
                apple_type,
                overrides.state or default.state,
                overrides.turn_on or default.turn_on,
                overrides.turn_off or default.turn_off,
            )
        return MainBlock(category, "Valve", behavior)

    if domain == "fan":
        type_ = type_ or "fan"
        if type_ not in FAN_TYPES:
            raise UnsupportedEntity(f"type '{type_}' is not available for fan")
        purifier = type_ == "air_purifier"
        fan = FanBehavior(entity_id, attributes, purifier=purifier)
        presets = tuple(
            ExtraBlock(FanPresetBehavior.key(p), "Switch", FanPresetBehavior(entity_id, p), name=str(p))
            for p in fan.switch_presets
        )
        if purifier:
            return MainBlock("air_purifier", "AirPurifier", fan, presets, PURIFIER_LINKED_SENSORS)
        return MainBlock("fan", "Fanv2", fan, presets)

    if domain == "light" and type_ in (None, "light"):
        behavior = LightBehavior.from_attributes(
            entity_id,
            attributes,
            state=overrides.state,
            turn_on=overrides.turn_on,
            turn_off=overrides.turn_off,
        )
        return MainBlock("lightbulb", "Lightbulb", behavior)

    if domain in ONOFF_DOMAINS or domain == "light":
        type_ = type_ or "switch"
        if type_ not in ONOFF_TYPES:
            raise UnsupportedEntity(f"type '{type_}' is not available for {domain}")
        default = OnOffBehavior.for_entity(entity_id, outlet=type_ == "outlet")
        behavior = OnOffBehavior(
            overrides.state or default.state,
            overrides.turn_on or default.turn_on,
            overrides.turn_off or default.turn_off,
            outlet=type_ == "outlet",
        )
        category = "lightbulb" if type_ == "light" else type_
        return MainBlock(category, ONOFF_SERVICES[type_], behavior)

    if domain in ("sensor", "binary_sensor"):
        if type_ is None:
            device_class = attributes.get("device_class")
            if domain == "sensor":
                type_ = SENSOR_DEVICE_CLASSES.get(device_class)
                if type_ is None:
                    raise UnsupportedEntity(
                        f"sensor with device_class '{device_class}' needs an explicit type"
                    )
            else:
                type_ = BINARY_SENSOR_DEVICE_CLASSES.get(device_class, DEFAULT_BINARY_SENSOR_TYPE)
        if type_ not in supported_types(domain):
            raise UnsupportedEntity(f"type '{type_}' is not available for {domain}")
        sensor = SENSOR_TYPES[type_]
        source = overrides.state or Source(entity_id=entity_id)
        return MainBlock("sensor", sensor.service, sensor.create(source))

    raise UnsupportedEntity(f"domain '{domain}' is not supported yet")


def _media_player(
    entity_id: str, attributes: Mapping[str, Any], type_: str | None, overrides: MainOverrides
) -> MainBlock:
    device_class = attributes.get("device_class")
    features = int(attributes.get("supported_features") or 0)
    if type_ is None:
        if device_class == "receiver":
            type_ = "receiver"
        elif device_class == "tv" or features & FEATURE_SELECT_SOURCE:
            type_ = "television"
        else:
            type_ = "switch"
    if type_ not in MEDIA_TYPES:
        raise UnsupportedEntity(f"type '{type_}' is not available for media_player")
    if type_ == "switch":
        return MainBlock("switch", "Switch", MediaPowerBehavior(entity_id))

    if overrides.sources is not None:
        sources = overrides.sources
    else:
        sources = tuple((str(s), str(s)) for s in dict.fromkeys(attributes.get("source_list") or []))
    sources = sources[:MAX_TV_OPTIONS]
    extras = [
        ExtraBlock(f"input:{slugify(value)}", "InputSource", InputSourceBehavior(input_identifier(index)), name=label, linked=True)
        for index, (value, label) in enumerate(sources)
    ]
    if TelevisionSpeakerBehavior.applies(attributes):
        extras.append(
            ExtraBlock("tv:speaker", "TelevisionSpeaker", TelevisionSpeakerBehavior(entity_id, attributes), name_key="volume", linked=True)
        )
    behavior = TelevisionMediaBehavior(entity_id, attributes, sources, overrides.remote_keys)
    category = "receiver" if type_ == "receiver" else "television"
    return MainBlock(category, "Television", behavior, tuple(extras), standalone=True)
