"""Extra blocks from entity_config: `sensors` and `switches`."""

from __future__ import annotations

from ..model.binding import Command, Source
from .sensor import SENSOR_TYPES, SensorType
from .switch import OnOffBehavior


def sensor_type(name: str) -> SensorType:
    return SENSOR_TYPES[name]


def switch_behavior(
    entity_id: str | None,
    state: Source | None,
    turn_on: Command | None,
    turn_off: Command | None,
) -> OnOffBehavior:
    """A user toggle: defaults come from `entity`, explicit fields override them."""
    if entity_id is not None:
        default = OnOffBehavior.for_entity(entity_id)
        return OnOffBehavior(
            state or default.state,
            turn_on or default.turn_on,
            turn_off or default.turn_off,
        )
    return OnOffBehavior(state, turn_on, turn_off)
