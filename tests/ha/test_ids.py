"""Stable numbering: the experiment-2 regression test."""

from unittest.mock import MagicMock

from pyhap.loader import get_loader

from homeassistant.core import HomeAssistant

from custom_components.homekit_alchemy.hap.accessory import AlchemyAccessory
from custom_components.homekit_alchemy.hap.ids import IdStorage, StableIIDManager
from custom_components.homekit_alchemy.model import keys
from custom_components.homekit_alchemy.model.binding import Source
from custom_components.homekit_alchemy.model.device import Block, Device
from custom_components.homekit_alchemy.presets.light import LightBehavior
from custom_components.homekit_alchemy.presets.sensor import SENSOR_TYPES
from tests.fakes import FakeView


def _sensor(sensor_type: str, name: str) -> Block:
    spec = SENSOR_TYPES[sensor_type]
    return Block(keys.sensor_key(sensor_type), spec.service, name, spec.create(Source(entity_id=f"sensor.{sensor_type}")))


def _device(blocks: list[Block]) -> Device:
    return Device("uid:lamp", "light.lamp", "Lamp", "lightbulb", blocks)


def _iids(storage: IdStorage, device: Device) -> dict[tuple[str, str], int]:
    driver = MagicMock(loader=get_loader())
    aid = storage.get_or_allocate_aid(device.key)
    acc = AlchemyAccessory(driver, device, aid, StableIIDManager(storage), FakeView(), MagicMock(), "0")
    result = {}
    for service in acc.services:
        sid = acc.iid_manager.get_iid(service)
        result[(service.unique_id or service.display_name, "")] = sid
        for char in service.characteristics:
            result[(service.unique_id or service.display_name, char.display_name)] = acc.iid_manager.get_iid(char)
    return result


async def test_iids_survive_adding_and_removing_blocks(hass: HomeAssistant) -> None:
    storage = IdStorage(hass, "test")
    await storage.async_load()

    lamp_onoff = Block(keys.MAIN, "Lightbulb", "Лампа", LightBehavior("light.lamp", ["onoff"]), primary=True)
    before = _iids(storage, _device([lamp_onoff, _sensor("temperature", "T"), _sensor("battery", "B")]))

    # Lamp gains a Brightness field, battery is removed, humidity is added.
    lamp_dim = Block(keys.MAIN, "Lightbulb", "Лампа", LightBehavior("light.lamp", ["brightness"]), primary=True)
    after = _iids(storage, _device([lamp_dim, _sensor("temperature", "T"), _sensor("humidity", "H")]))

    common = before.keys() & after.keys()
    assert {k: before[k] for k in common} == {k: after[k] for k in common}
    assert after[("AccessoryInformation", "")] == 1

    new_iids = {after[k] for k in after.keys() - before.keys()}
    assert min(new_iids) > max(before.values()), "new blocks must not reuse old numbers"


async def test_aids_are_stable_and_never_reused(hass: HomeAssistant) -> None:
    storage = IdStorage(hass, "test")
    await storage.async_load()
    assert storage.get_or_allocate_aid("a") == 2
    assert storage.get_or_allocate_aid("b") == 3
    assert storage.get_or_allocate_aid("a") == 2
    await storage.async_save()

    reloaded = IdStorage(hass, "test")
    await reloaded.async_load()
    assert reloaded.get_or_allocate_aid("b") == 3
    assert reloaded.get_or_allocate_aid("c") == 4


async def test_pincode_is_persisted(hass: HomeAssistant) -> None:
    storage = IdStorage(hass, "pin")
    await storage.async_load()
    assert storage.pincode is None
    storage.pincode = "123-45-678"
    await storage.async_save()
    reloaded = IdStorage(hass, "pin")
    await reloaded.async_load()
    assert reloaded.pincode == "123-45-678"


async def test_standalone_slots_and_ports(hass: HomeAssistant) -> None:
    storage = IdStorage(hass, "sa")
    await storage.async_load()
    assert storage.get_or_allocate_standalone("tv1", 21100) == (1, 21101)
    assert storage.get_or_allocate_standalone("tv2", 21100) == (2, 21102)
    assert storage.get_or_allocate_standalone("tv1", 21100) == (1, 21101)


async def test_aid_7_is_never_used(hass: HomeAssistant) -> None:
    storage = IdStorage(hass, "seven")
    await storage.async_load()
    aids = [storage.get_or_allocate_aid(f"d{i}") for i in range(7)]
    assert aids == [2, 3, 4, 5, 6, 8, 9]
