"""Where values come from and what to do on commands."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Source:
    """A value in Home Assistant: entity state, one of its attributes, or a template."""

    entity_id: str | None = None
    attribute: str | None = None
    template: str | None = None

    def __post_init__(self) -> None:
        if (self.entity_id is None) == (self.template is None):
            raise ValueError("Source needs exactly one of entity_id or template")
        if self.attribute is not None and self.entity_id is None:
            raise ValueError("Source attribute requires entity_id")


@dataclass(frozen=True)
class Command:
    """A Home Assistant action call, e.g. light.turn_on.

    String values in `target` and `data` may be templates; they are rendered
    with `variables` (e.g. `value`, `option`) when the command is executed.
    An action "event:<type>" fires that event on the HA bus with `data` instead.
    """

    action: str
    target: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    def with_variables(self, **variables: Any) -> Command:
        return replace(self, variables={**self.variables, **variables})

    @property
    def domain(self) -> str:
        return self.action.split(".", 1)[0]

    @property
    def service(self) -> str:
        return self.action.split(".", 1)[1]
