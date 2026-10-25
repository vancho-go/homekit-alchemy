"""Validated configuration. Same shape whether it came from YAML or (later) the UI."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.helpers.entityfilter import EntityFilter

from ..model.binding import Command, Source


@dataclass(frozen=True)
class SensorConfig:
    type: str
    source: Source
    name: str | None = None
    id: str | None = None


@dataclass(frozen=True)
class SwitchConfig:
    name: str | None = None
    id: str | None = None
    entity_id: str | None = None
    state: Source | None = None
    turn_on: Command | None = None
    turn_off: Command | None = None


@dataclass(frozen=True)
class RangeConfig:
    name: str | None = None
    id: str | None = None
    entity_id: str | None = None  # number / input_number: min, max, step and command come from it
    state: Source | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    set: Command | None = None


@dataclass(frozen=True)
class ModeConfig:
    name: str | None = None
    id: str | None = None
    entity_id: str | None = None  # select / input_select: options and command come from it
    state: Source | None = None
    options: tuple[tuple[str, str], ...] | None = None  # (value, label)
    set: Command | None = None
    display: str = "switches"


@dataclass(frozen=True)
class ButtonConfig:
    entity_id: str
    name: str | None = None
    id: str | None = None
    attribute: str | None = None  # default: event_type for event.*, otherwise the state
    single: tuple[str, ...] = ()
    double: tuple[str, ...] = ()
    long: tuple[str, ...] = ()


@dataclass(frozen=True)
class EntityConfig:
    name: str | None = None
    type: str | None = None
    state: Source | None = None
    turn_on: Command | None = None
    turn_off: Command | None = None
    current_temperature: Source | None = None
    current_humidity: Source | None = None
    min_temp: float | None = None
    max_temp: float | None = None
    temperature_step: float | None = None
    open: Command | None = None
    close: Command | None = None
    stop: Command | None = None
    obstruction: Source | None = None
    code: str | None = None
    sources: tuple[tuple[str, str], ...] | None = None
    remote_keys: dict[str, Command] | None = None
    presets: tuple[tuple[str, str], ...] | None = None
    sensors: tuple[SensorConfig, ...] = ()
    switches: tuple[SwitchConfig, ...] = ()
    ranges: tuple[RangeConfig, ...] = ()
    modes: tuple[ModeConfig, ...] = ()
    buttons: tuple[ButtonConfig, ...] = ()


@dataclass(frozen=True)
class AlchemyConfig:
    name: str
    port: int
    filter: EntityFilter
    entity_config: dict[str, EntityConfig] = field(default_factory=dict)
