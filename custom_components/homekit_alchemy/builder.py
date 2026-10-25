"""Build model devices from configuration and Home Assistant registries."""

from __future__ import annotations

from collections import Counter
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .config.models import (
    ButtonConfig,
    EntityConfig,
    AlchemyConfig,
    ModeConfig,
    RangeConfig,
    SensorConfig,
    SwitchConfig,
)
from .model import keys
from .model.binding import Command, Source
from .model.device import Block, Device
from .presets.extras import sensor_type, switch_behavior
from .presets.flex import (
    DOUBLE,
    LONG,
    SINGLE,
    MAX_TV_OPTIONS,
    input_identifier,
    ButtonBehavior,
    InputSourceBehavior,
    ModeOptionBehavior,
    ModeSliderBehavior,
    ModeSpec,
    RangeBehavior,
    ServiceLabelBehavior,
    TelevisionModeBehavior,
)
from .presets.names import block_name
from .presets.climate import ClimateOverrides
from .presets.cover import CoverOverrides
from .presets.registry import MainOverrides, UnsupportedEntity, main_block

_LOGGER = logging.getLogger(__name__)


def build_devices(hass: HomeAssistant, config: AlchemyConfig) -> list[Device]:
    """All devices of the bridge. Problems are logged; one bad entity never blocks others."""
    registry = er.async_get(hass)
    devices: list[Device] = []
    for entity_id in sorted(exposed_entity_ids(hass, registry, config)):
        explicit = entity_id in config.entity_config or config.filter.explicitly_included(entity_id)
        try:
            devices += build_device(hass, registry, entity_id, config.entity_config.get(entity_id, EntityConfig()))
        except UnsupportedEntity as err:
            # Domain-wide includes pick up lots of entities we cannot show yet: stay quiet about those.
            _LOGGER.log(logging.WARNING if explicit else logging.DEBUG, "Skipping %s: %s", entity_id, err)
    return devices


def exposed_entity_ids(hass: HomeAssistant, registry: er.EntityRegistry, config: AlchemyConfig) -> set[str]:
    """Entities picked by `filter`, plus everything in `entity_config` unless explicitly excluded."""
    flt = config.filter
    selected: set[str] = set()
    if not flt.empty_filter:
        for entity_id in hass.states.async_entity_ids():
            if not flt(entity_id):
                continue
            if not flt.explicitly_included(entity_id) and _is_auxiliary(registry, entity_id):
                continue
            selected.add(entity_id)
    selected.update(e for e in config.entity_config if not flt.explicitly_excluded(e))
    return selected


def build_device(
    hass: HomeAssistant, registry: er.EntityRegistry, entity_id: str, cfg: EntityConfig
) -> list[Device]:
    """The device for one entity, plus standalone devices it spawns (television modes)."""
    state = hass.states.get(entity_id)
    if state is None:
        raise UnsupportedEntity("entity not found")
    climate = ClimateOverrides(
        current_temperature=cfg.current_temperature,
        current_humidity=cfg.current_humidity,
        min_temp=cfg.min_temp,
        max_temp=cfg.max_temp,
        temperature_step=cfg.temperature_step,
    )
    main = main_block(
        entity_id,
        state.attributes,
        cfg.type,
        MainOverrides(
            cfg.state,
            cfg.turn_on,
            cfg.turn_off,
            climate,
            CoverOverrides(open=cfg.open, close=cfg.close, stop=cfg.stop, obstruction=cfg.obstruction),
            code=cfg.code,
            sources=cfg.sources,
            presets=cfg.presets,
            remote_keys=cfg.remote_keys,
        ),
        temperature_unit=hass.config.units.temperature_unit,
    )
    name = cfg.name or state.name
    sensor_blocks = _sensor_blocks(hass, cfg.sensors)
    linked = [extra.key for extra in main.extras if extra.linked]
    linked += [block.key for sensor, block in zip(cfg.sensors, sensor_blocks) if sensor.type in main.linked_sensor_types]
    blocks = [Block(keys.MAIN, main.service, name, main.behavior, primary=True, linked=tuple(linked))]
    blocks += [
        Block(
            extra.key,
            extra.service,
            extra.name or block_name(extra.name_key or "", hass.config.language),
            extra.behavior,
        )
        for extra in main.extras
    ]
    blocks += sensor_blocks
    blocks += [_switch_block(hass, sw) for sw in cfg.switches]
    blocks += [_range_block(hass, rng) for rng in cfg.ranges]
    televisions = [m for m in cfg.modes if m.display == "television"]
    for mode in cfg.modes:
        if mode.display != "television":
            blocks += _mode_blocks(hass, mode)
    blocks += [_button_block(hass, btn) for btn in cfg.buttons]
    _number_buttons(blocks)

    entry = registry.async_get(entity_id)
    device_key = keys.device_key(entity_id, entry.unique_id if entry else None)
    try:
        devices = [
            Device(
                key=device_key,
                entity_id=entity_id,
                name=name,
                category=main.category,
                blocks=blocks,
                standalone=main.standalone,
            )
        ]
    except ValueError as err:
        raise UnsupportedEntity(f"{err}; give the blocks distinct 'id's") from err
    devices += [_television_device(hass, device_key, entity_id, name, mode) for mode in televisions]
    return devices


def _sensor_blocks(hass: HomeAssistant, sensors: tuple[SensorConfig, ...]) -> list[Block]:
    per_type = Counter(s.type for s in sensors if not s.id)
    blocks = []
    for sensor in sensors:
        if sensor.id:
            key = f"sensor:id:{sensor.id}"
        elif per_type[sensor.type] == 1:
            key = keys.sensor_key(sensor.type)
        else:
            key = keys.sensor_key(sensor.type, sensor.source.entity_id or sensor.source.template)
        spec = sensor_type(sensor.type)
        name = sensor.name or _source_name(hass, sensor.source) or sensor.type
        blocks.append(Block(key, spec.service, name, spec.create(sensor.source)))
    return blocks


def _switch_block(hass: HomeAssistant, switch: SwitchConfig) -> Block:
    key = keys.switch_key(block_id=switch.id, entity_id=switch.entity_id, name=switch.name)
    name = switch.name or _source_name(hass, Source(entity_id=switch.entity_id)) or "Switch"
    behavior = switch_behavior(switch.entity_id, switch.state, switch.turn_on, switch.turn_off)
    return Block(key, "Switch", name, behavior)


NUMBER_DOMAINS = ("number", "input_number")
SELECT_DOMAINS = ("select", "input_select")


def _range_block(hass: HomeAssistant, rng: RangeConfig) -> Block:
    key = keys.extra_key("range", block_id=rng.id, entity_id=rng.entity_id, name=rng.name)
    low, high, step, set_cmd, state = rng.min, rng.max, rng.step, rng.set, rng.state
    if rng.entity_id is not None:
        domain = rng.entity_id.split(".", 1)[0]
        attrs = _attributes(hass, rng.entity_id)
        if domain in NUMBER_DOMAINS:
            low = low if low is not None else attrs.get("min")
            high = high if high is not None else attrs.get("max")
            step = step or attrs.get("step")
            set_cmd = set_cmd or Command(
                f"{domain}.set_value", {"entity_id": rng.entity_id}, {"value": "{{ value }}"}
            )
        elif set_cmd is None:
            raise UnsupportedEntity(f"range {rng.entity_id}: only number/input_number work without 'set'")
        state = state or Source(entity_id=rng.entity_id)
    if low is None or high is None or set_cmd is None or state is None:
        raise UnsupportedEntity(f"range {key}: needs min, max, state and set")
    try:
        behavior = RangeBehavior(state, set_cmd, float(low), float(high), float(step or 1))
    except ValueError as err:
        raise UnsupportedEntity(f"range {key}: {err}") from err
    name = rng.name or _source_name(hass, state) or key
    return Block(key, "Lightbulb", name, behavior)


def _mode_spec(hass: HomeAssistant, mode: ModeConfig) -> tuple[str, str, ModeSpec]:
    """(block key, display name, spec) of a mode."""
    key = keys.extra_key("mode", block_id=mode.id, entity_id=mode.entity_id, name=mode.name)
    state, select, option_pairs = mode.state, mode.set, mode.options
    if mode.entity_id is not None:
        domain = mode.entity_id.split(".", 1)[0]
        if domain in SELECT_DOMAINS:
            entity_options = [str(o) for o in _attributes(hass, mode.entity_id).get("options") or []]
            if option_pairs is None:
                option_pairs = tuple((o, o) for o in entity_options)
            elif unknown := [v for v, _ in option_pairs if v not in entity_options]:
                raise UnsupportedEntity(f"mode {mode.entity_id}: unknown options {unknown}")
            select = select or Command(
                f"{domain}.select_option", {"entity_id": mode.entity_id}, {"option": "{{ option }}"}
            )
        elif select is None or option_pairs is None:
            raise UnsupportedEntity(f"mode {mode.entity_id}: only select/input_select work without 'options' and 'set'")
        state = state or Source(entity_id=mode.entity_id)
    if not option_pairs or select is None or state is None:
        raise UnsupportedEntity(f"mode {key}: needs options, state and set")
    spec = ModeSpec(state, tuple(option_pairs), select)
    return key, mode.name or _source_name(hass, state) or key, spec


def _mode_blocks(hass: HomeAssistant, mode: ModeConfig) -> list[Block]:
    key, name, spec = _mode_spec(hass, mode)
    option_pairs = spec.options
    if mode.display == "slider":
        return [Block(key, "Lightbulb", name, ModeSliderBehavior(spec))]
    return [
        Block(f"{key}:{keys.slugify(value)}", "Switch", label, ModeOptionBehavior(spec, value))
        for value, label in option_pairs
    ]


def _television_device(
    hass: HomeAssistant, owner_key: str, entity_id: str, owner_name: str, mode: ModeConfig
) -> Device:
    """A mode as a standalone Apple TV: inputs are the options (a real pick-one list)."""
    key, name, spec = _mode_spec(hass, mode)
    if len(spec.options) > MAX_TV_OPTIONS:
        raise UnsupportedEntity(f"mode {key}: a television list holds at most {MAX_TV_OPTIONS} options")
    inputs = [
        Block(f"input:{keys.slugify(value)}", "InputSource", label, InputSourceBehavior(input_identifier(index)))
        for index, (value, label) in enumerate(spec.options)
    ]
    tv = Block(
        keys.MAIN, "Television", name, TelevisionModeBehavior(spec), primary=True, linked=tuple(b.key for b in inputs)
    )
    return Device(
        key=f"{owner_key}|{key}",
        entity_id=entity_id,
        name=f"{owner_name} · {name}",
        category="television",
        blocks=[tv, *inputs],
        standalone=True,
    )


def _button_block(hass: HomeAssistant, btn: ButtonConfig) -> Block:
    key = keys.extra_key("button", block_id=btn.id, entity_id=btn.entity_id, name=btn.name)
    presses = {v: SINGLE for v in btn.single} | {v: DOUBLE for v in btn.double} | {v: LONG for v in btn.long}
    attribute = btn.attribute or ("event_type" if btn.entity_id.startswith("event.") else None)
    name = btn.name or _source_name(hass, Source(entity_id=btn.entity_id)) or key
    return Block(key, "StatelessProgrammableSwitch", name, ButtonBehavior(btn.entity_id, presses, attribute))


def _number_buttons(blocks: list[Block]) -> None:
    """Apple needs a ServiceLabel and per-button indexes when a device has several buttons."""
    buttons = [b for b in blocks if isinstance(b.behavior, ButtonBehavior)]
    if len(buttons) < 2:
        return
    for index, block in enumerate(buttons, start=1):
        block.behavior.index = index
    blocks.append(Block("buttons:label", "ServiceLabel", "Buttons", ServiceLabelBehavior()))


def _attributes(hass: HomeAssistant, entity_id: str) -> dict:
    state = hass.states.get(entity_id)
    return dict(state.attributes) if state else {}


def _source_name(hass: HomeAssistant, source: Source) -> str | None:
    if source.entity_id and (state := hass.states.get(source.entity_id)):
        return state.name
    return None


def _is_auxiliary(registry: er.EntityRegistry, entity_id: str) -> bool:
    """Hidden and config/diagnostic entities are only exposed when named explicitly."""
    entry = registry.async_get(entity_id)
    return entry is not None and (entry.hidden_by is not None or entry.entity_category is not None)
