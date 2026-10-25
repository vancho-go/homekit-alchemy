"""Persistent accessory (AID) and instance (IID) numbers.

Apple caches services and characteristics by these numbers. They are keyed by
meaning (device key, block key, characteristic type) and never reused, so that
adding or removing blocks cannot shift or recycle numbers of other blocks.
"""

from __future__ import annotations

from typing import Any

from pyhap.characteristic import Characteristic
from pyhap.iid_manager import IIDManager
from pyhap.service import Service
from pyhap.util import uuid_to_hap_type

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from ..const import DOMAIN

STORAGE_VERSION = 1
SAVE_DELAY = 2

FIRST_AID = 2  # 1 is the bridge itself
SKIPPED_AIDS = {7}  # Apple rejects AID 7 (HAP-python issue #61)
INFO_SERVICE_TYPE = "3E"  # AccessoryInformation must always be IID 1


class IdStorage:
    """AID/IID allocations and the pairing code of one bridge (.storage/homekit_alchemy.<entry_id>.ids).

    HAP-python does not persist the pairing code; keeping it here means the
    code shown to the user does not change on every restart.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}.ids"
        )
        self.aids: dict[str, int] = {}
        self.iids: dict[str, dict[str, int]] = {}
        self.pincode: str | None = None
        # Standalone accessories of this bridge: device key -> {"slot": n, "port": p}
        self.standalone: dict[str, dict[str, int]] = {}
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load() or {}
        self.aids = data.get("aids", {})
        self.iids = data.get("iids", {})
        self.pincode = data.get("pincode")
        self.standalone = data.get("standalone", {})
        self._loaded = True

    async def async_save(self) -> None:
        await self._store.async_save(self._data())

    async def async_remove(self) -> None:
        await self._store.async_remove()

    def get_or_allocate_aid(self, device_key: str) -> int:
        if (aid := self.aids.get(device_key)) is None:
            aid = max(self.aids.values(), default=FIRST_AID - 1) + 1
            while aid in SKIPPED_AIDS:
                aid += 1
            self.aids[device_key] = aid
            self._schedule_save()
        return aid

    def get_or_allocate_standalone(self, device_key: str, base_port: int) -> tuple[int, int]:
        """(slot, port) of a standalone accessory; both stay the same forever."""
        if (entry := self.standalone.get(device_key)) is None:
            used = self.standalone.values()
            entry = {
                "slot": max((e["slot"] for e in used), default=0) + 1,
                "port": max((e["port"] for e in used), default=base_port) + 1,
            }
            self.standalone[device_key] = entry
            self._schedule_save()
        return entry["slot"], entry["port"]

    def get_or_allocate_iid(self, aid: int, key: str) -> int:
        allocations = self.iids.setdefault(str(aid), {})
        if (iid := allocations.get(key)) is None:
            iid = max(allocations.values(), default=1) + 1
            allocations[key] = iid
            self._schedule_save()
        return iid

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data, SAVE_DELAY)

    @callback
    def _data(self) -> dict[str, Any]:
        return {"aids": self.aids, "iids": self.iids, "pincode": self.pincode, "standalone": self.standalone}


class StableIIDManager(IIDManager):
    """IIDManager that takes numbers from IdStorage instead of counting."""

    def __init__(self, storage: IdStorage) -> None:
        super().__init__()
        self._storage = storage

    def get_iid_for_obj(self, obj: Service | Characteristic) -> int:
        aid = obj.broker.aid
        if isinstance(obj, Characteristic):
            service: Service = obj.service
            key = _key(service, uuid_to_hap_type(obj.type_id))
        else:
            if uuid_to_hap_type(obj.type_id) == INFO_SERVICE_TYPE:
                return 1
            key = _key(obj, None)
        iid = self._storage.get_or_allocate_iid(aid, key)
        if iid in self.objs:
            raise RuntimeError(f"IID {iid} for {obj} already used by {self.objs[iid]}")
        return iid


def _key(service: Service, char_type: str | None) -> str:
    return f"{uuid_to_hap_type(service.type_id)}|{service.unique_id or ''}|{char_type or ''}"
