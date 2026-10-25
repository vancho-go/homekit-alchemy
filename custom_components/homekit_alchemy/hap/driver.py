"""HAP accessory driver wired into Home Assistant's shared resources."""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import Any

from pyhap.accessory_driver import AccessoryDriver
from pyhap.loader import get_loader


class AlchemyDriver(AccessoryDriver):
    """Accessory driver that reports pairing changes to the owner."""

    def __init__(self, on_paired: Callable[[bool], None], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._on_paired = on_paired

    def pair(self, client_username_bytes: bytes, client_public: str, client_permissions: int) -> bool:
        success = super().pair(client_username_bytes, client_public, client_permissions)
        if success:
            self._on_paired(True)
        return success

    def unpair(self, client_uuid: Any) -> None:
        super().unpair(client_uuid)
        if not self.state.paired:
            self._on_paired(False)


def create_driver(
    *,
    loop: Any,
    port: int,
    persist_file: str,
    bind_address: list[str],
    advertised_address: list[str],
    async_zeroconf: Any,
    zeroconf_server: str,
    pincode: str,
    on_paired: Callable[[bool], None],
) -> tuple[AlchemyDriver, bool]:
    """Create the driver and load pairing state. Blocking: run in the executor.

    Returns (driver, loaded_from_disk).
    """
    os.makedirs(os.path.dirname(persist_file), exist_ok=True)
    driver = AlchemyDriver(
        on_paired,
        loop=loop,
        address=bind_address,
        port=port,
        persist_file=persist_file,
        advertised_address=advertised_address,
        async_zeroconf_instance=async_zeroconf,
        zeroconf_server=zeroconf_server,
        pincode=pincode.encode(),
        loader=get_loader(),
    )
    loaded = os.path.exists(persist_file)
    if loaded:
        driver.load()
    return driver, loaded
