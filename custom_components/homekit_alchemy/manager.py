"""Bridge lifecycle: model -> HAP servers (the bridge + standalone accessories) -> running."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
import logging
from typing import Any

from pyhap.accessory import Bridge
from pyhap.const import STANDALONE_AID
from pyhap.util import generate_pincode, generate_setup_id

from homeassistant.components import network, persistent_notification, zeroconf
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import instance_id
from homeassistant.helpers.event import async_call_later

from .const import DOMAIN, MANUFACTURER, VERSION
from .hap.accessory import AlchemyAccessory
from .hap.driver import AlchemyDriver, create_driver
from .hap.ids import IdStorage, StableIIDManager
from .model.device import Block, Device
from .pairing import async_forget_qr, async_publish_qr
from .runtime.commands import async_execute
from .runtime.sources import HassStateView

_LOGGER = logging.getLogger(__name__)

BIND_ADDRESS = ["0.0.0.0"]
RESYNC_DELAY = 2  # seconds after a write from Apple Home
RESET_DELAY = 10  # seconds for Apple Home to notice a removed accessory (same as HA's bridge)


def standalone_storage_key(entry_id: str, slot: int) -> str:
    """Files of standalone accessory #slot: .storage/homekit_alchemy.<entry>.sa<slot>.{state,ids}."""
    return f"{entry_id}.sa{slot}"


# (driver, device, aid, id storage) -> accessory
AccessoryFactory = Callable[[AlchemyDriver, Device, int, IdStorage], AlchemyAccessory]


class HapServer:
    """One HAP endpoint Apple pairs with: the bridge, or a single standalone accessory."""

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str,
        port: int,
        storage_key: str,
        devices: list[Device],
        standalone: bool,
    ) -> None:
        self.hass = hass
        self.name = name
        self.port = port
        self.storage_key = storage_key  # also the pairing notification id
        self.devices = devices
        self.standalone = standalone
        self.ids = IdStorage(hass, storage_key)
        self.driver: AlchemyDriver | None = None

    async def async_start(
        self, make_accessory: AccessoryFactory, async_zc: Any, zeroconf_server: str, advertised: list[str]
    ) -> list[AlchemyAccessory]:
        await self.ids.async_load()
        if self.ids.pincode is None:
            self.ids.pincode = generate_pincode().decode()
        if self.ids.setup_id is None:
            self.ids.setup_id = generate_setup_id()
        persist_file = self.hass.config.path(".storage", f"{DOMAIN}.{self.storage_key}.state")
        driver, loaded = await self.hass.async_add_executor_job(
            lambda: create_driver(
                loop=self.hass.loop,
                port=self.port,
                persist_file=persist_file,
                bind_address=BIND_ADDRESS,
                advertised_address=advertised,
                async_zeroconf=async_zc,
                zeroconf_server=zeroconf_server,
                pincode=self.ids.pincode,
                on_paired=self._on_paired,
            )
        )
        self.driver = driver
        # HAP-python does not persist the setup id; keep the QR code stable across restarts.
        driver.state.setup_id = self.ids.setup_id

        if self.standalone:
            accessories = [make_accessory(driver, self.devices[0], STANDALONE_AID, self.ids)]
            root = accessories[0]
        else:
            root = Bridge(driver, self.name)
            root.set_info_service(firmware_revision=VERSION, manufacturer=MANUFACTURER, model="Bridge")
            accessories = []
            for device in self.devices:
                try:
                    accessory = make_accessory(driver, device, self.ids.get_or_allocate_aid(device.key), self.ids)
                except Exception:
                    # One broken device must never take the whole bridge down.
                    _LOGGER.exception("HomeKit Alchemy %s: cannot create accessory for %s", self.name, device.entity_id)
                    continue
                root.add_accessory(accessory)
                accessories.append(accessory)
        # Not driver.add_accessory(): it does blocking file I/O in the event loop.
        driver.accessory = root

        await driver.async_start()
        if not loaded:
            await self.hass.async_add_executor_job(driver.persist)
        await self.ids.async_save()
        _LOGGER.info(
            "HomeKit Alchemy %s %s started on port %s with %s accessories",
            "accessory" if self.standalone else "bridge", self.name, self.port, len(accessories),
        )
        if not driver.state.paired:
            self._show_pairing()
        return accessories

    async def async_stop(self) -> None:
        if self.driver is not None:
            driver, self.driver = self.driver, None
            if driver.accessory is not None:  # a failed start never got this far
                await driver.async_stop()
        await self.ids.async_save()
        self._dismiss_pairing()

    async def async_reset(
        self, keys: set[str], make_accessory: AccessoryFactory
    ) -> list[AlchemyAccessory]:
        """Make Apple Home forget bridged accessories, then add them back (fresh cache).

        Same approach as HA's homekit.reset_accessory: remove, announce the new
        configuration, wait, re-add with the same numbers.
        """
        assert self.driver is not None and not self.standalone
        bridge = self.driver.accessory
        removed = [acc for acc in list(bridge.accessories.values()) if acc.device.key in keys]
        if not removed:
            return []
        for accessory in removed:
            del bridge.accessories[accessory.aid]
        self._announce_config_change()
        await asyncio.sleep(RESET_DELAY)
        added = []
        for old in removed:
            accessory = make_accessory(self.driver, old.device, old.aid, self.ids)
            bridge.add_accessory(accessory)
            added.append(accessory)
        self._announce_config_change()
        _LOGGER.info("HomeKit Alchemy %s: reset %s", self.name, [a.device.entity_id for a in added])
        return added

    @callback
    def async_unpair(self) -> None:
        """Forget every paired iPhone/iPad so the accessory can be added again."""
        assert self.driver is not None
        state = self.driver.state
        for client_uuid in list(state.paired_clients):
            # Removing an admin can also remove the clients it invited.
            if client_uuid in state.paired_clients:
                state.remove_paired_client(client_uuid)
        self.driver.async_persist()
        self.driver.async_update_advertisement()
        self._show_pairing()

    @callback
    def _announce_config_change(self) -> None:
        assert self.driver is not None
        if self.driver.state.set_accessories_hash(self.driver.accessories_hash):
            self.driver.async_persist()
            self.driver.async_update_advertisement()

    def diagnostics(self) -> dict[str, Any]:
        state = self.driver.state if self.driver else None
        return {
            "name": self.name,
            "port": self.port,
            "standalone": self.standalone,
            "running": self.driver is not None,
            "paired_clients": len(state.paired_clients) if state else None,
            "config_version": state.config_version if state else None,
        }

    @callback
    def _on_paired(self, paired: bool) -> None:
        if paired:
            self._dismiss_pairing()
        else:
            self._show_pairing()

    @callback
    def _show_pairing(self) -> None:
        assert self.driver is not None
        pin = self.driver.state.pincode.decode()
        _LOGGER.info("HomeKit Alchemy %s pairing code: %s", self.name, pin)
        qr_url = async_publish_qr(self.hass, self.storage_key, self.driver.accessory.xhm_uri())
        persistent_notification.async_create(
            self.hass,
            f"Add **{self.name}** to Apple Home: **+** → **Add Accessory**, then scan the code\n\n"
            f"![pairing QR code]({qr_url})\n\n"
            f"or choose **More options…** and enter:\n### {pin}",
            "HomeKit Alchemy pairing",
            self.storage_key,
        )

    @callback
    def _dismiss_pairing(self) -> None:
        persistent_notification.async_dismiss(self.hass, self.storage_key)
        async_forget_qr(self.hass, self.storage_key)


class BridgeManager:
    """Runs the bridge and the standalone accessories of one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        name: str,
        port: int,
        build_devices: Callable[[HomeAssistant], list[Device]],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self.port = port
        self._build_devices = build_devices
        self.view = HassStateView(hass)
        self.servers: list[HapServer] = []
        self.accessories: dict[str, AlchemyAccessory] = {}
        self._tracking: dict[str, CALLBACK_TYPE] = {}  # device key -> state subscription
        self._resync: dict[int, CALLBACK_TYPE] = {}

    @property
    def driver(self) -> AlchemyDriver | None:
        """The bridge's driver."""
        return self.servers[0].driver if self.servers else None

    async def async_start(self) -> None:
        devices = self._build_devices(self.hass)
        bridge = HapServer(
            self.hass,
            name=self.name,
            port=self.port,
            storage_key=self.entry_id,
            devices=[d for d in devices if not d.standalone],
            standalone=False,
        )
        # Slots and ports of standalone accessories live in the bridge's storage.
        await bridge.ids.async_load()
        self.servers = [bridge]
        for device in (d for d in devices if d.standalone):
            slot, port = bridge.ids.get_or_allocate_standalone(device.key, self.port)
            self.servers.append(
                HapServer(
                    self.hass,
                    name=device.name,
                    port=port,
                    storage_key=standalone_storage_key(self.entry_id, slot),
                    devices=[device],
                    standalone=True,
                )
            )

        async_zc = await zeroconf.async_get_async_instance(self.hass)
        uuid = await instance_id.async_get(self.hass)
        advertised = await network.async_get_announce_addresses(self.hass)
        for server in self.servers:
            for accessory in await server.async_start(
                self._make_accessory, async_zc, f"{uuid}-{DOMAIN}.local.", advertised
            ):
                self.accessories[accessory.device.key] = accessory

    @callback
    def _make_accessory(self, driver: AlchemyDriver, device: Device, aid: int, ids: IdStorage) -> AlchemyAccessory:
        accessory = AlchemyAccessory(
            driver,
            device,
            aid=aid,
            iid_manager=StableIIDManager(ids),
            view=self.view,
            on_command=self._on_command,
            firmware=VERSION,
        )
        accessory.refresh()
        if old := self._tracking.pop(device.key, None):
            old()
        self._tracking[device.key] = self.view.async_track(device.sources(), accessory.refresh)
        return accessory

    @callback
    def _on_command(self, accessory: AlchemyAccessory, block: Block, values: dict[str, Any]) -> None:
        _LOGGER.debug("Apple Home set %s: %s", block.key, values)
        async_execute(self.hass, block.behavior.handle(values, self.view))
        # If Home Assistant ignores or rejects the change (e.g. "un-selecting" a mode),
        # nothing triggers a state update: push the real values back shortly.
        token = id(accessory)
        if cancel := self._resync.pop(token, None):
            cancel()

        @callback
        def _resync(_now: Any) -> None:
            self._resync.pop(token, None)
            accessory.refresh()

        self._resync[token] = async_call_later(self.hass, RESYNC_DELAY, _resync)

    async def async_stop(self) -> None:
        while self._tracking:
            self._tracking.popitem()[1]()
        while self._resync:
            self._resync.popitem()[1]()
        for server in self.servers:
            await server.async_stop()

    async def async_reset_accessories(self, entity_ids: Iterable[str]) -> list[str]:
        """Reset bridged accessories whose main entity is in entity_ids; returns the reset ones."""
        wanted = set(entity_ids)
        keys = {
            key
            for key, acc in self.accessories.items()
            if acc.device.entity_id in wanted and not acc.device.standalone
        }
        if not keys or not self.servers:
            return []
        for accessory in await self.servers[0].async_reset(keys, self._make_accessory):
            self.accessories[accessory.device.key] = accessory
        return sorted(self.accessories[k].device.entity_id for k in keys)

    @callback
    def async_unpair(self) -> None:
        for server in self.servers:
            if server.driver is not None:
                server.async_unpair()

    def diagnostics(self) -> dict[str, Any]:
        """Structure and current values, without pairing codes or keys."""
        accessories = []
        for accessory in self.accessories.values():
            device = accessory.device
            accessories.append(
                {
                    "aid": accessory.aid,
                    "key": device.key,
                    "entity_id": device.entity_id,
                    "name": device.name,
                    "category": device.category,
                    "standalone": device.standalone,
                    "available": accessory.available,
                    "blocks": [
                        {
                            "key": block.key,
                            "service": block.kind,
                            "name": block.name,
                            "linked": list(block.linked),
                            "values": {k: c.value for k, c in accessory._chars[block.key].items()},
                        }
                        for block in device.blocks
                    ],
                }
            )
        return {"servers": [s.diagnostics() for s in self.servers], "accessories": accessories}
