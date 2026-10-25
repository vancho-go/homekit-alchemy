"""Reading sources and subscribing to their changes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    TrackTemplateResultInfo,
    async_track_state_change_event,
    async_track_template_result,
)
from homeassistant.helpers.template import Template

from ..model.behavior import StateSnapshot
from ..model.binding import Source

_LOGGER = logging.getLogger(__name__)


class HassStateView:
    """StateView backed by the live Home Assistant state machine."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._templates: dict[str, Any] = {}  # template string -> last rendered result

    def state(self, entity_id: str) -> StateSnapshot | None:
        if (state := self.hass.states.get(entity_id)) is None:
            return None
        return StateSnapshot(state.state, state.attributes)

    def value(self, source: Source) -> Any:
        if source.template is not None:
            return self._templates.get(source.template)
        assert source.entity_id is not None
        state = self.hass.states.get(source.entity_id)
        if state is None:
            return None
        if source.attribute is not None:
            return state.attributes.get(source.attribute)
        return state.state

    @callback
    def async_track(self, sources: Iterable[Source], on_change: Callable[[], None]) -> CALLBACK_TYPE:
        """Call on_change whenever any of the sources may have changed."""
        sources = list(sources)
        unsubs: list[CALLBACK_TYPE] = []

        if entity_ids := sorted({s.entity_id for s in sources if s.entity_id}):

            @callback
            def _state_changed(_event: Event[EventStateChangedData]) -> None:
                on_change()

            unsubs.append(async_track_state_change_event(self.hass, entity_ids, _state_changed))

        for template_str in sorted({s.template for s in sources if s.template}):
            unsubs.append(self._async_track_template(template_str, on_change).async_remove)

        @callback
        def _unsub() -> None:
            while unsubs:
                unsubs.pop()()

        return _unsub

    @callback
    def _async_track_template(
        self, template_str: str, on_change: Callable[[], None]
    ) -> TrackTemplateResultInfo:
        @callback
        def _result(_event: Event | None, updates: list[TrackTemplateResult]) -> None:
            for update in updates:
                if isinstance(update.result, TemplateError):
                    _LOGGER.warning("Template %s failed: %s", template_str, update.result)
                    self._templates[template_str] = None
                else:
                    self._templates[template_str] = update.result
            on_change()

        info = async_track_template_result(
            self.hass, [TrackTemplate(Template(template_str, self.hass), None)], _result
        )
        info.async_refresh()
        return info
