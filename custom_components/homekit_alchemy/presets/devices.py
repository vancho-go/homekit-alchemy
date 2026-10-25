"""Simpler device types: humidifiers, locks, valves, security systems,
water heaters and activate-only entities (scripts, scenes, buttons).

Each mirrors Home Assistant's built-in HomeKit bridge (type_humidifiers.py,
type_locks.py, type_switches.py, type_security_systems.py, type_thermostats.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..model.behavior import Behavior, FieldSpec, StateView
from ..model.binding import Command, Source
from ..model.keys import slugify
from .convert import clamp, to_bool, to_float


def _state(view: StateView, entity_id: str):
    state = view.state(entity_id)
    return state if state is not None and state.available else None


# --- Humidifier / dehumidifier ---------------------------------------------

HUMIDIFIER, DEHUMIDIFIER = 1, 2
HUM_INACTIVE, HUM_IDLE, HUM_HUMIDIFYING, HUM_DEHUMIDIFYING = 0, 1, 2, 3


class HumidifierBehavior(Behavior):
    """Apple HumidifierDehumidifier, fixed to the entity's device_class."""

    def __init__(self, entity_id: str, attributes: Mapping[str, Any], current_humidity: Source | None = None) -> None:
        self.entity_id = entity_id
        self.current_humidity = current_humidity
        self.mode = DEHUMIDIFIER if attributes.get("device_class") == "dehumidifier" else HUMIDIFIER
        self.threshold = (
            "RelativeHumidityDehumidifierThreshold" if self.mode == DEHUMIDIFIER else "RelativeHumidityHumidifierThreshold"
        )
        self.min_humidity = max(0, round(to_float(attributes.get("min_humidity")) or 0))
        self.max_humidity = min(100, round(to_float(attributes.get("max_humidity")) or 100))

    def fields(self) -> list[FieldSpec]:
        name = "Dehumidifier" if self.mode == DEHUMIDIFIER else "Humidifier"
        current_valid = {"Inactive": HUM_INACTIVE, "Idle": HUM_IDLE}
        if self.mode == DEHUMIDIFIER:
            current_valid["Dehumidifying"] = HUM_DEHUMIDIFYING
        else:
            current_valid["Humidifying"] = HUM_HUMIDIFYING
        return [
            FieldSpec("Active"),
            FieldSpec("CurrentHumidifierDehumidifierState", {"ValidValues": current_valid}),
            FieldSpec(
                "TargetHumidifierDehumidifierState",
                {"ValidValues": {name: self.mode}, "minValue": self.mode, "maxValue": self.mode},
            ),
            FieldSpec("CurrentRelativeHumidity"),
            FieldSpec(self.threshold, {"minValue": self.min_humidity, "maxValue": self.max_humidity, "minStep": 1}),
        ]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)] + ([self.current_humidity] if self.current_humidity else [])

    def compute(self, view: StateView) -> dict[str, Any]:
        state = _state(view, self.entity_id)
        if state is None:
            return {}
        attrs = state.attributes
        is_on = state.state == "on"
        values: dict[str, Any] = {"Active": int(is_on), "TargetHumidifierDehumidifierState": self.mode}
        action = attrs.get("action")
        if not is_on or action == "off":
            values["CurrentHumidifierDehumidifierState"] = HUM_INACTIVE
        elif action in ("humidifying", "drying"):
            values["CurrentHumidifierDehumidifierState"] = HUM_DEHUMIDIFYING if self.mode == DEHUMIDIFIER else HUM_HUMIDIFYING
        else:
            values["CurrentHumidifierDehumidifierState"] = HUM_IDLE
        raw = view.value(self.current_humidity) if self.current_humidity else attrs.get("current_humidity")
        if (current := to_float(raw)) is not None:
            values["CurrentRelativeHumidity"] = round(clamp(current, 0, 100))
        if (target := to_float(attrs.get("humidity"))) is not None:
            values[self.threshold] = round(clamp(target, self.min_humidity, self.max_humidity))
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        commands: list[Command] = []
        if "Active" in changes:
            commands.append(Command("humidifier.turn_on" if changes["Active"] else "humidifier.turn_off", target))
        if self.threshold in changes:
            humidity = round(clamp(changes[self.threshold], self.min_humidity, self.max_humidity))
            commands.append(Command("humidifier.set_humidity", target, {"humidity": humidity}))
        return commands


class HumidifierModeBehavior(Behavior):
    """One humidifier mode (`available_modes`) as a switch."""

    def __init__(self, entity_id: str, mode: str) -> None:
        self.entity_id = entity_id
        self.mode = mode

    @staticmethod
    def key(mode: str) -> str:
        return f"humidifier:mode:{slugify(mode)}"

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On")]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = _state(view, self.entity_id)
        return {} if state is None else {"On": state.attributes.get("mode") == self.mode}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if not changes.get("On"):
            return []  # a mode cannot be "un-selected"; Apple resyncs on the next state update
        return [Command("humidifier.set_mode", {"entity_id": self.entity_id}, {"mode": self.mode})]


# --- Lock ------------------------------------------------------------------

LOCK_CURRENT = {"unlocked": 0, "unlocking": 1, "locking": 0, "locked": 1, "jammed": 2, "open": 0, "opening": 0}
LOCK_TARGET = {"unlocked": 0, "unlocking": 0, "locking": 1, "locked": 1, "open": 0, "opening": 0}
LOCK_UNKNOWN = 3


class LockBehavior(Behavior):
    """Apple LockMechanism."""

    def __init__(self, entity_id: str, code: str | None = None) -> None:
        self.entity_id = entity_id
        self.code = code

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("LockCurrentState"), FieldSpec("LockTargetState")]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or state.state == "unavailable":
            return {}
        values: dict[str, Any] = {"LockCurrentState": LOCK_CURRENT.get(state.state, LOCK_UNKNOWN)}
        if (target := LOCK_TARGET.get(state.state)) is not None:
            values["LockTargetState"] = target
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "LockTargetState" not in changes:
            return []
        data = {"code": self.code} if self.code else {}
        action = "lock.lock" if changes["LockTargetState"] else "lock.unlock"
        return [Command(action, {"entity_id": self.entity_id}, data)]


# --- Valve -----------------------------------------------------------------

# type -> (Apple ValveType, accessory category)
VALVE_TYPES: dict[str, tuple[int, str]] = {
    "valve": (0, "faucet"),
    "sprinkler": (1, "sprinkler"),
    "shower": (2, "shower"),
    "faucet": (3, "faucet"),
}


class ValveBehavior(Behavior):
    """Apple Valve (Active / InUse) from a valve entity or any on/off entity."""

    def __init__(self, valve_type: int, state: Source, open_cmd: Command, close_cmd: Command) -> None:
        self.valve_type = valve_type
        self.state = state
        self.open_cmd = open_cmd
        self.close_cmd = close_cmd

    @classmethod
    def for_valve_entity(cls, entity_id: str, valve_type: int) -> ValveBehavior:
        target = {"entity_id": entity_id}
        return cls(
            valve_type,
            Source(entity_id=entity_id),
            Command("valve.open_valve", target),
            Command("valve.close_valve", target),
        )

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("Active"), FieldSpec("InUse"), FieldSpec("ValveType")]

    def sources(self) -> list[Source]:
        return [self.state]

    def compute(self, view: StateView) -> dict[str, Any]:
        is_open = to_bool(view.value(self.state))
        if is_open is None:
            return {}
        return {"Active": int(is_open), "InUse": int(is_open), "ValveType": self.valve_type}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if "Active" not in changes:
            return []
        return [self.open_cmd if changes["Active"] else self.close_cmd]


# --- Security system -------------------------------------------------------

SEC_STAY, SEC_AWAY, SEC_NIGHT, SEC_DISARMED, SEC_TRIGGERED = 0, 1, 2, 3, 4
FEATURE_ARM_HOME, FEATURE_ARM_AWAY, FEATURE_ARM_NIGHT, FEATURE_ARM_VACATION = 1, 2, 4, 32
SEC_CURRENT = {
    "armed_home": SEC_STAY,
    "armed_away": SEC_AWAY,
    "armed_vacation": SEC_AWAY,
    "armed_night": SEC_NIGHT,
    "armed_custom_bypass": SEC_STAY,
    "arming": SEC_DISARMED,
    "disarmed": SEC_DISARMED,
    "triggered": SEC_TRIGGERED,
}
SEC_TARGET = {**SEC_CURRENT, "arming": SEC_AWAY, "triggered": None}
SEC_ACTIONS = {
    SEC_STAY: "alarm_control_panel.alarm_arm_home",
    SEC_AWAY: "alarm_control_panel.alarm_arm_away",
    SEC_NIGHT: "alarm_control_panel.alarm_arm_night",
    SEC_DISARMED: "alarm_control_panel.alarm_disarm",
}


class SecuritySystemBehavior(Behavior):
    """Apple SecuritySystem: home / away / night / off (+ triggered)."""

    def __init__(self, entity_id: str, attributes: Mapping[str, Any], code: str | None = None) -> None:
        self.entity_id = entity_id
        self.code = code
        features = int(attributes.get("supported_features") or 0)
        self.targets = [SEC_DISARMED]
        if features & FEATURE_ARM_HOME:
            self.targets.append(SEC_STAY)
        if features & (FEATURE_ARM_AWAY | FEATURE_ARM_VACATION):
            self.targets.append(SEC_AWAY)
        if features & FEATURE_ARM_NIGHT:
            self.targets.append(SEC_NIGHT)

    def fields(self) -> list[FieldSpec]:
        names = {SEC_STAY: "StayArm", SEC_AWAY: "AwayArm", SEC_NIGHT: "NightArm", SEC_DISARMED: "Disarm"}
        current = {names[v]: v for v in sorted(self.targets)} | {"AlarmTriggered": SEC_TRIGGERED}
        return [
            FieldSpec("SecuritySystemCurrentState", {"ValidValues": current}),
            FieldSpec("SecuritySystemTargetState", {"ValidValues": {names[v]: v for v in sorted(self.targets)}}),
        ]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = _state(view, self.entity_id)
        if state is None:
            return {}
        values: dict[str, Any] = {}
        if (current := SEC_CURRENT.get(state.state)) is not None:
            values["SecuritySystemCurrentState"] = current
        if (target := SEC_TARGET.get(state.state)) is not None and target in self.targets:
            values["SecuritySystemTargetState"] = target
        return values

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        if (value := changes.get("SecuritySystemTargetState")) not in SEC_ACTIONS:
            return []
        data = {"code": self.code} if self.code else {}
        return [Command(SEC_ACTIONS[value], {"entity_id": self.entity_id}, data)]


# --- Activate-only: script / scene / button --------------------------------

ACTIVATE_ACTIONS = {
    "script": "script.turn_on",
    "scene": "scene.turn_on",
    "button": "button.press",
    "input_button": "input_button.press",
}


class ActivateBehavior(Behavior):
    """A Switch that runs the entity when turned on and then flips back off.

    Scripts show "on" while running; scenes and buttons are momentary, and the
    state change they cause pushes "off" back to Apple Home.
    """

    def __init__(self, entity_id: str) -> None:
        self.entity_id = entity_id
        self.domain = entity_id.split(".", 1)[0]

    def fields(self) -> list[FieldSpec]:
        return [FieldSpec("On")]

    def sources(self) -> list[Source]:
        return [Source(entity_id=self.entity_id)]

    def compute(self, view: StateView) -> dict[str, Any]:
        state = view.state(self.entity_id)
        if state is None or state.state == "unavailable":
            return {}
        return {"On": self.domain == "script" and state.state == "on"}

    def handle(self, changes: dict[str, Any], view: StateView) -> list[Command]:
        target = {"entity_id": self.entity_id}
        if changes.get("On"):
            return [Command(ACTIVATE_ACTIONS[self.domain], target)]
        if self.domain == "script":
            return [Command("script.turn_off", target)]
        return []
