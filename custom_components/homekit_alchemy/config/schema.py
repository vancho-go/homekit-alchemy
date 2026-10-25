"""YAML schema: validates `homekit_alchemy:` and converts it into config dataclasses."""

from __future__ import annotations

from typing import Any

import probatio as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entityfilter import BASE_FILTER_SCHEMA, convert_filter

from ..const import DEFAULT_NAME, DEFAULT_PORT, DOMAIN
from ..model.binding import Command, Source
from ..presets.sensor import SENSOR_TYPES
from .models import (
    ButtonConfig,
    EntityConfig,
    AlchemyConfig,
    ModeConfig,
    RangeConfig,
    SensorConfig,
    SwitchConfig,
)

CONF_ACTION = "action"
CONF_ATTRIBUTE = "attribute"
CONF_CURRENT_HUMIDITY = "current_humidity"
CONF_CURRENT_TEMPERATURE = "current_temperature"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_TEMP = "min_temp"
CONF_OPEN = "open"
CONF_CLOSE = "close"
CONF_STOP = "stop"
CONF_OBSTRUCTION = "obstruction"
CONF_CODE = "code"
CONF_BUTTONS = "buttons"
CONF_SINGLE = "single"
CONF_DOUBLE = "double"
CONF_LONG = "long"
CONF_DISPLAY = "display"
CONF_MAX = "max"
CONF_MIN = "min"
CONF_MODES = "modes"
CONF_OPTIONS = "options"
CONF_RANGES = "ranges"
CONF_SET = "set"
CONF_STEP = "step"
CONF_SOURCES = "sources"
CONF_REMOTE_KEYS = "remote_keys"
REMOTE_KEY_NAMES = (
    "arrow_up", "arrow_down", "arrow_left", "arrow_right", "select", "back", "exit",
    "information", "play_pause", "next_track", "previous_track", "rewind", "fast_forward",
)

MODE_DISPLAYS = ("switches", "slider", "television")
CONF_TEMPERATURE_STEP = "temperature_step"
CONF_DATA = "data"
CONF_ENTITY = "entity"
CONF_ENTITY_CONFIG = "entity_config"
CONF_ENTITY_ID = "entity_id"
CONF_FILTER = "filter"
CONF_ID = "id"
CONF_NAME = "name"
CONF_PORT = "port"
CONF_SENSORS = "sensors"
CONF_STATE = "state"
CONF_SWITCHES = "switches"
CONF_TARGET = "target"
CONF_TEMPLATE = "template"
CONF_TURN_OFF = "turn_off"
CONF_TURN_ON = "turn_on"
CONF_TYPE = "type"


def _template_string(value: Any) -> str:
    cv.template(value)  # syntax check only; rendered later by the runtime
    return str(value)


def _source_from_dict(value: dict[str, Any]) -> Source:
    entity = value.get(CONF_ENTITY)
    template = value.get(CONF_TEMPLATE)
    if (entity is None) == (template is None):
        raise vol.Invalid("specify exactly one of 'entity' or 'template'")
    if template is not None and CONF_ATTRIBUTE in value:
        raise vol.Invalid("'attribute' can only be used with 'entity'")
    return Source(entity_id=entity, attribute=value.get(CONF_ATTRIBUTE), template=template)


SOURCE_DICT_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_TEMPLATE): _template_string,
    }
)


def source(value: Any) -> Source:
    """`sensor.x` | `{{ template }}` | {entity, attribute} | {template}."""
    if isinstance(value, str):
        if "{" in value:
            return Source(template=_template_string(value))
        return Source(entity_id=cv.entity_id(value))
    return _source_from_dict(SOURCE_DICT_SCHEMA(value))


def _service_name(value: Any) -> str:
    value = cv.string(value)
    if "." not in value:
        raise vol.Invalid(f"'{value}' is not an action like 'light.turn_on'")
    return value


COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACTION): _service_name,
        vol.Optional(CONF_ENTITY_ID): cv.entity_ids,
        vol.Optional(CONF_TARGET): dict,
        vol.Optional(CONF_DATA): dict,
    }
)


def command(value: Any) -> Command:
    """{action, entity_id?, target?, data?}; `entity_id` is a shortcut for target."""
    value = COMMAND_SCHEMA(value)
    target = dict(value.get(CONF_TARGET, {}))
    if CONF_ENTITY_ID in value:
        target[CONF_ENTITY_ID] = value[CONF_ENTITY_ID]
    return Command(value[CONF_ACTION], target, dict(value.get(CONF_DATA, {})))


SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): vol.In(sorted(SENSOR_TYPES)),
        vol.Optional(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_TEMPLATE): _template_string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ID): cv.string,
    }
)


def sensor(value: Any) -> SensorConfig:
    value = SENSOR_SCHEMA(value)
    return SensorConfig(
        type=value[CONF_TYPE],
        source=_source_from_dict(value),
        name=value.get(CONF_NAME),
        id=value.get(CONF_ID),
    )


SWITCH_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ID): cv.string,
        vol.Optional(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_STATE): source,
        vol.Optional(CONF_TURN_ON): command,
        vol.Optional(CONF_TURN_OFF): command,
    }
)


def switch(value: Any) -> SwitchConfig:
    value = SWITCH_SCHEMA(value)
    if CONF_ENTITY not in value:
        if CONF_NAME not in value:
            raise vol.Invalid("a switch without 'entity' needs a 'name'")
        if CONF_TURN_ON not in value or CONF_TURN_OFF not in value:
            raise vol.Invalid("a switch without 'entity' needs 'turn_on' and 'turn_off'")
    return SwitchConfig(
        name=value.get(CONF_NAME),
        id=value.get(CONF_ID),
        entity_id=value.get(CONF_ENTITY),
        state=value.get(CONF_STATE),
        turn_on=value.get(CONF_TURN_ON),
        turn_off=value.get(CONF_TURN_OFF),
    )


RANGE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ID): cv.string,
        vol.Optional(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_STATE): source,
        vol.Optional(CONF_MIN): vol.Coerce(float),
        vol.Optional(CONF_MAX): vol.Coerce(float),
        vol.Optional(CONF_STEP): vol.All(vol.Coerce(float), vol.Range(min=0, min_included=False)),
        vol.Optional(CONF_SET): command,
    }
)


def range_(value: Any) -> RangeConfig:
    value = RANGE_SCHEMA(value)
    if CONF_ENTITY not in value:
        missing = [k for k in (CONF_NAME, CONF_STATE, CONF_MIN, CONF_MAX, CONF_SET) if k not in value]
        if missing:
            raise vol.Invalid(f"a range without 'entity' needs: {', '.join(missing)}")
    return RangeConfig(
        name=value.get(CONF_NAME),
        id=value.get(CONF_ID),
        entity_id=value.get(CONF_ENTITY),
        state=value.get(CONF_STATE),
        min=value.get(CONF_MIN),
        max=value.get(CONF_MAX),
        step=value.get(CONF_STEP),
        set=value.get(CONF_SET),
    )


def _option_value(value: Any) -> str:
    # YAML turns bare on/off/yes/no keys into booleans; HA states are "on"/"off".
    if isinstance(value, bool):
        return "on" if value else "off"
    return cv.string(value)


def options(value: Any) -> tuple[tuple[str, str], ...]:
    """[a, b] or {a: Label A, b: Label B} -> ((value, label), …) in the given order."""
    if isinstance(value, dict):
        pairs = tuple((_option_value(k), cv.string(v)) for k, v in value.items())
    elif isinstance(value, list):
        pairs = tuple((_option_value(v), _option_value(v)) for v in value)
    else:
        raise vol.Invalid("options must be a list or a mapping of value: label")
    if not pairs:
        raise vol.Invalid("options must not be empty")
    return pairs


MODE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ID): cv.string,
        vol.Optional(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_STATE): source,
        vol.Optional(CONF_OPTIONS): options,
        vol.Optional(CONF_SET): command,
        vol.Optional(CONF_DISPLAY, default="switches"): vol.In(MODE_DISPLAYS),
    }
)


def mode(value: Any) -> ModeConfig:
    value = MODE_SCHEMA(value)
    if CONF_ENTITY not in value:
        missing = [k for k in (CONF_NAME, CONF_STATE, CONF_OPTIONS, CONF_SET) if k not in value]
        if missing:
            raise vol.Invalid(f"a mode without 'entity' needs: {', '.join(missing)}")
    return ModeConfig(
        name=value.get(CONF_NAME),
        id=value.get(CONF_ID),
        entity_id=value.get(CONF_ENTITY),
        state=value.get(CONF_STATE),
        options=value.get(CONF_OPTIONS),
        set=value.get(CONF_SET),
        display=value[CONF_DISPLAY],
    )


def _press_values(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    return tuple(_option_value(v) for v in values)


BUTTON_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY): cv.entity_id,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ID): cv.string,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_SINGLE): _press_values,
        vol.Optional(CONF_DOUBLE): _press_values,
        vol.Optional(CONF_LONG): _press_values,
    }
)


def button(value: Any) -> ButtonConfig:
    value = BUTTON_SCHEMA(value)
    if not any(k in value for k in (CONF_SINGLE, CONF_DOUBLE, CONF_LONG)):
        raise vol.Invalid("a button needs at least one of 'single', 'double', 'long'")
    return ButtonConfig(
        entity_id=value[CONF_ENTITY],
        name=value.get(CONF_NAME),
        id=value.get(CONF_ID),
        attribute=value.get(CONF_ATTRIBUTE),
        single=value.get(CONF_SINGLE, ()),
        double=value.get(CONF_DOUBLE, ()),
        long=value.get(CONF_LONG, ()),
    )


ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_TYPE): cv.string,
        vol.Optional(CONF_STATE): source,
        vol.Optional(CONF_TURN_ON): command,
        vol.Optional(CONF_TURN_OFF): command,
        vol.Optional(CONF_CURRENT_TEMPERATURE): source,
        vol.Optional(CONF_CURRENT_HUMIDITY): source,
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TEMPERATURE_STEP): vol.All(vol.Coerce(float), vol.Range(min=0.1)),
        vol.Optional(CONF_OPEN): command,
        vol.Optional(CONF_CLOSE): command,
        vol.Optional(CONF_STOP): command,
        vol.Optional(CONF_OBSTRUCTION): source,
        vol.Optional(CONF_CODE): cv.string,
        vol.Optional(CONF_SOURCES): options,
        vol.Optional(CONF_REMOTE_KEYS): {vol.In(REMOTE_KEY_NAMES): command},
        vol.Optional(CONF_SENSORS, default=[]): [sensor],
        vol.Optional(CONF_SWITCHES, default=[]): [switch],
        vol.Optional(CONF_RANGES, default=[]): [range_],
        vol.Optional(CONF_MODES, default=[]): [mode],
        vol.Optional(CONF_BUTTONS, default=[]): [button],
    }
)


def entity_config(value: Any) -> EntityConfig:
    value = ENTITY_SCHEMA(value or {})
    return EntityConfig(
        name=value.get(CONF_NAME),
        type=value.get(CONF_TYPE),
        state=value.get(CONF_STATE),
        turn_on=value.get(CONF_TURN_ON),
        turn_off=value.get(CONF_TURN_OFF),
        current_temperature=value.get(CONF_CURRENT_TEMPERATURE),
        current_humidity=value.get(CONF_CURRENT_HUMIDITY),
        min_temp=value.get(CONF_MIN_TEMP),
        max_temp=value.get(CONF_MAX_TEMP),
        temperature_step=value.get(CONF_TEMPERATURE_STEP),
        open=value.get(CONF_OPEN),
        close=value.get(CONF_CLOSE),
        stop=value.get(CONF_STOP),
        obstruction=value.get(CONF_OBSTRUCTION),
        code=value.get(CONF_CODE),
        sources=value.get(CONF_SOURCES),
        remote_keys=value.get(CONF_REMOTE_KEYS),
        sensors=tuple(value[CONF_SENSORS]),
        switches=tuple(value[CONF_SWITCHES]),
        ranges=tuple(value[CONF_RANGES]),
        modes=tuple(value[CONF_MODES]),
        buttons=tuple(value[CONF_BUTTONS]),
    )


ALCHEMY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_FILTER, default={}): BASE_FILTER_SCHEMA,
        vol.Optional(CONF_ENTITY_CONFIG, default={}): {cv.entity_id: entity_config},
    }
)


def alchemy_config(value: Any) -> AlchemyConfig:
    value = ALCHEMY_SCHEMA(value or {})
    return AlchemyConfig(
        name=value[CONF_NAME],
        port=value[CONF_PORT],
        filter=convert_filter(value[CONF_FILTER]),
        entity_config=value[CONF_ENTITY_CONFIG],
    )


CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): alchemy_config}, extra=vol.ALLOW_EXTRA)
