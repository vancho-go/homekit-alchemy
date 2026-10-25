"""Generic HAP accessory built from a model Device."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from pyhap import const as hap_const
from pyhap.accessory import Accessory
from pyhap.characteristic import Characteristic
from pyhap.service import Service

from ..const import MANUFACTURER
from ..model.behavior import StateView
from ..model.device import Block, Device
from .ids import StableIIDManager

_LOGGER = logging.getLogger(__name__)

NAME_CHARS = ("Name", "ConfiguredName")

_CYRILLIC = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
     "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"],
))


def advertised_name(name: str) -> str:
    """ASCII name for the network announcement.

    HAP-python drops non-Latin letters there, so "Гостиная ТВ" would be listed in
    "Add Accessory" as just a MAC suffix. The name inside Apple Home stays as is.
    """
    out = []
    for char in name:
        low = char.lower()
        if low in _CYRILLIC:
            latin = _CYRILLIC[low]
            out.append(latin.capitalize() if char != low and latin else latin)
        else:
            out.append(char)
    ascii_name = " ".join("".join(c if c.isascii() else " " for c in "".join(out)).split())
    return ascii_name or MANUFACTURER

CATEGORIES: dict[str, int] = {
    "other": hap_const.CATEGORY_OTHER,
    "lightbulb": hap_const.CATEGORY_LIGHTBULB,
    "switch": hap_const.CATEGORY_SWITCH,
    "outlet": hap_const.CATEGORY_OUTLET,
    "sensor": hap_const.CATEGORY_SENSOR,
    "fan": hap_const.CATEGORY_FAN,
    "thermostat": hap_const.CATEGORY_THERMOSTAT,
    "window_covering": hap_const.CATEGORY_WINDOW_COVERING,
    "garage_door": hap_const.CATEGORY_GARAGE_DOOR_OPENER,
    "window": hap_const.CATEGORY_WINDOW,
    "door": hap_const.CATEGORY_DOOR,
    "lock": hap_const.CATEGORY_DOOR_LOCK,
    "air_purifier": hap_const.CATEGORY_AIR_PURIFIER,
    "air_conditioner": hap_const.CATEGORY_AIR_CONDITIONER,
    "humidifier": hap_const.CATEGORY_HUMIDIFIER,
    "dehumidifier": hap_const.CATEGORY_DEHUMIDIFIER,
    "security": hap_const.CATEGORY_ALARM_SYSTEM,
    "faucet": hap_const.CATEGORY_FAUCET,
    "shower": hap_const.CATEGORY_SHOWER_HEAD,
    "sprinkler": hap_const.CATEGORY_SPRINKLER,
    "programmable_switch": hap_const.CATEGORY_PROGRAMMABLE_SWITCH,
    "television": hap_const.CATEGORY_TELEVISION,
    "receiver": 34,  # CATEGORY_AUDIO_RECEIVER (not in HAP-python's constants)
}

# (accessory, block, values written by Apple Home) -> None
CommandHandler = Callable[["AlchemyAccessory", Block, dict[str, Any]], None]


class AlchemyAccessory(Accessory):
    """One Apple Home card: a service per model block."""

    def __init__(
        self,
        driver: Any,
        device: Device,
        aid: int,
        iid_manager: StableIIDManager,
        view: StateView,
        on_command: CommandHandler,
        firmware: str,
    ) -> None:
        self.category = CATEGORIES.get(device.category, hap_const.CATEGORY_OTHER)
        super().__init__(driver, device.name, aid=aid, iid_manager=iid_manager)
        self.device = device
        self._view = view
        self._chars: dict[str, dict[str, Characteristic]] = {}

        self.set_info_service(
            firmware_revision=firmware,
            manufacturer=MANUFACTURER,
            model=device.entity_id.split(".", 1)[0],
            serial_number=device.entity_id,
        )
        services = {block.key: self._add_block(block, on_command) for block in device.blocks}
        for block in device.blocks:
            for key in block.linked:
                services[block.key].add_linked_service(services[key])
        # Only used for mDNS from here on; the Name characteristics keep the real name.
        self.display_name = advertised_name(device.name)

    def _add_block(self, block: Block, on_command: CommandHandler) -> Service:
        fields = block.behavior.fields()
        service = self.add_preload_service(
            block.kind,
            chars=[f.kind for f in fields] + list(NAME_CHARS),
            unique_id=block.key,
        )
        service.is_primary_service = block.primary
        for name_char in NAME_CHARS:
            service.configure_char(name_char, value=block.name)
        chars: dict[str, Characteristic] = {}
        for spec in fields:
            char = service.get_characteristic(spec.kind)
            if spec.properties:
                char.override_properties(properties=dict(spec.properties))
            chars[spec.kind] = char
        self._chars[block.key] = chars
        service.setter_callback = lambda values, block=block: on_command(self, block, values)
        return service

    @property
    def available(self) -> bool:
        state = self._view.state(self.device.entity_id)
        return state is not None and state.reachable

    def refresh(self) -> None:
        """Push current Home Assistant values to Apple Home (only changed ones notify)."""
        for block in self.device.blocks:
            chars = self._chars[block.key]
            for kind, value in block.behavior.compute(self._view).items():
                if (char := chars.get(kind)) is None:
                    continue
                if kind == "ProgrammableSwitchEvent":
                    _LOGGER.debug("%s / %s: button event %s", self.device.entity_id, block.key, value)
                try:
                    char.set_value(value)
                except ValueError as err:
                    _LOGGER.warning(
                        "%s / %s: bad value %r for %s: %s",
                        self.device.entity_id, block.key, value, kind, err,
                    )
