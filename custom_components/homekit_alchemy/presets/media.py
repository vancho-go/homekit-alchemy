"""Media players: Apple Television (or receiver) with inputs, speaker and the iPhone remote.

Modeled on Home Assistant's built-in HomeKit bridge (type_media_players.py,
type_remotes.py). Remote keys without a matching media_player action fire
`homekit_alchemy_tv_remote_key_pressed` on the event bus (or run a user command).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from .convert import to_float
from .flex import display_order, input_identifier, input_index

FEATURE_PAUSE, FEATURE_VOLUME_SET, FEATURE_VOLUME_MUTE = 1, 4, 8
FEATURE_PREVIOUS_TRACK, FEATURE_NEXT_TRACK = 16, 32
FEATURE_VOLUME_STEP, FEATURE_SELECT_SOURCE, FEATURE_PLAY = 1024, 2048, 16384

OFF_STATES = {"off", "standby", "unknown", "None"}
REMOTE_KEY_EVENT = "homekit_alchemy_tv_remote_key_pressed"

# Apple RemoteKey value -> key name (same names as HA's homekit_tv_remote_key_pressed)
REMOTE_KEYS = {
    0: "rewind",
    1: "fast_forward",
    2: "next_track",
    3: "previous_track",
    4: "arrow_up",
    5: "arrow_down",
    6: "arrow_left",
    7: "arrow_right",
    8: "select",
    9: "back",
    10: "exit",
    11: "play_pause",
    15: "information",
}


def _is_on(state: str) -> bool:
    return state not in OFF_STATES


class TelevisionMediaBehavior(Behavior):
    """Power, input sources and remote keys of a media_player."""

    def __init__(
        self,
        entity_id: str,
        attributes: Mapping[str, Any],
        inputs: tuple[tuple[str, str], ...],
        remote_keys: Mapping[str, Command] | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.inputs = inputs  # (source value, label)
        self.remote_keys = dict(remote_keys or {})
        self.features = int(attributes.get("supported_features") or 0)

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("Active"), FieldSpec("SleepDiscoveryMode"), FieldSpec("RemoteKey")]
        if self.inputs:
            fields += [FieldSpec("ActiveIdentifier"), FieldSpec("DisplayOrder")]
        return fields

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or state.state == "unavailable":
            return {}
        values: dict[str, Any] = {"Active": int(_is_on(state.state)), "SleepDiscoveryMode": 1}
        if self.inputs:
            values["DisplayOrder"] = display_order([input_identifier(i) for i in range(len(self.inputs))])
            current = state.attributes.get("source")
            names = [value for value, _ in self.inputs]
            if current is not None and str(current) in names:
                values["ActiveIdentifier"] = input_identifier(names.index(str(current)))
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "Active" in changes:
            state = view.state(self.entity_id)
            is_on = state is not None and _is_on(state.state)
            # The iPhone remote sends Active=1 with every key press: only act on a real change.
            if bool(changes["Active"]) != is_on:
                commands.append(Command("media_player.turn_on" if changes["Active"] else "media_player.turn_off", target))
        index = input_index(changes.get("ActiveIdentifier"), len(self.inputs))
        if index is not None:
            commands.append(Command("media_player.select_source", target, {"source": self.inputs[index][0]}))
        if "RemoteKey" in changes and (command := self._remote_key(changes["RemoteKey"])) is not None:
            commands.append(command)
        return commands

    def _remote_key(self, value: int) -> Command | None:
        if (key := REMOTE_KEYS.get(value)) is None:
            return None
        target = {"entity_id": self.entity_id}
        if key in self.remote_keys:
            return self.remote_keys[key]
        if key == "play_pause" and self.features & (FEATURE_PLAY | FEATURE_PAUSE):
            return Command("media_player.media_play_pause", target)
        if key == "next_track" and self.features & FEATURE_NEXT_TRACK:
            return Command("media_player.media_next_track", target)
        if key == "previous_track" and self.features & FEATURE_PREVIOUS_TRACK:
            return Command("media_player.media_previous_track", target)
        return Command(f"event:{REMOTE_KEY_EVENT}", data={"entity_id": self.entity_id, "key": key})


class TelevisionSpeakerBehavior(Behavior):
    """Volume of a media_player as the TV's speaker (iPhone remote volume buttons)."""

    def __init__(self, entity_id: str, attributes: Mapping[str, Any]) -> None:
        self.entity_id = entity_id
        features = int(attributes.get("supported_features") or 0)
        self.has_mute = bool(features & FEATURE_VOLUME_MUTE)
        self.has_level = bool(features & FEATURE_VOLUME_SET)
        self.has_step = bool(features & (FEATURE_VOLUME_STEP | FEATURE_VOLUME_SET))

    @staticmethod
    def applies(attributes: Mapping[str, Any]) -> bool:
        features = int(attributes.get("supported_features") or 0)
        return bool(features & (FEATURE_VOLUME_MUTE | FEATURE_VOLUME_STEP | FEATURE_VOLUME_SET))

    def fields(self) -> list[FieldSpec]:
        fields = [FieldSpec("Mute"), FieldSpec("Active"), FieldSpec("VolumeControlType"), FieldSpec("VolumeSelector")]
        if self.has_level:
            fields.append(FieldSpec("Volume"))
        return fields

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or state.state == "unavailable":
            return {}
        attrs = state.attributes
        # Same VolumeControlType values as HA's bridge: with them the iPhone side buttons
        # send VolumeSelector (the "absolute" type 3 made the remote ignore them).
        values: dict[str, Any] = {
            "Active": 1,
            "VolumeControlType": 1 if self.has_level else 2,
            "Mute": bool(attrs.get("is_volume_muted")),
        }
        if self.has_level and (level := to_float(attrs.get("volume_level"))) is not None:
            values["Volume"] = round(level * 100)
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "Mute" in changes and self.has_mute:
            commands.append(Command("media_player.volume_mute", target, {"is_volume_muted": bool(changes["Mute"])}))
        if "VolumeSelector" in changes and self.has_step:
            action = "media_player.volume_down" if changes["VolumeSelector"] else "media_player.volume_up"
            commands.append(Command(action, target))
        if "Volume" in changes and self.has_level:
            commands.append(Command("media_player.volume_set", target, {"volume_level": round(changes["Volume"] / 100, 2)}))
        return commands


class MediaPowerBehavior(Behavior):
    """A simple player as a power switch: on = anything but off/standby."""

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On")]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or state.state == "unavailable":
            return {}
        return {"On": _is_on(state.state)}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "On" not in changes:
            return []
        return [Command("media_player.turn_on" if changes["On"] else "media_player.turn_off", {"entity_id": self.entity_id})]
