"""End-to-end: YAML -> running bridge -> Apple values / HA actions."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.homekit_alchemy.const import DOMAIN

LIGHT = "light.lamp"


def _states(hass: HomeAssistant) -> None:
    hass.states.async_set(LIGHT, "on", {"brightness": 128, "supported_color_modes": ["brightness"], "friendly_name": "Lamp"})
    hass.states.async_set("sensor.t", "21.37", {"device_class": "temperature", "friendly_name": "Room T"})
    hass.states.async_set("sensor.h", "44.6", {"device_class": "humidity"})
    hass.states.async_set("switch.kettle", "off")
    hass.states.async_set("binary_sensor.door", "on", {"device_class": "door"})
    hass.states.async_set("vacuum.robot", "docked")


async def _setup(hass: HomeAssistant, config: dict[str, Any]):
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})
    await hass.async_block_till_done()
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    return entry.runtime_data


def _by_entity(manager) -> dict[str, Any]:
    return {acc.device.entity_id: acc for acc in manager.accessories.values()}


async def test_yaml_builds_composite_device(hass: HomeAssistant, bridge_env: None) -> None:
    _states(hass)
    turn_on = async_mock_service(hass, "light", "turn_on")
    script = async_mock_service(hass, "script", "quiet_on")

    manager = await _setup(
        hass,
        {
            "port": 51827,
            "filter": {"include_domains": ["switch", "binary_sensor", "vacuum"]},
            "entity_config": {
                LIGHT: {
                    "name": "Desk lamp",
                    "sensors": [
                        {"type": "temperature", "entity": "sensor.t"},
                        {"type": "humidity", "entity": "sensor.h", "name": "Humidity"},
                    ],
                    "switches": [
                        {
                            "name": "Quiet",
                            "state": "{{ is_state('switch.kettle', 'on') }}",
                            "turn_on": {"action": "script.quiet_on"},
                            "turn_off": {"action": "script.quiet_off"},
                        }
                    ],
                }
            },
        },
    )
    accessories = _by_entity(manager)
    # vacuum is not supported yet: silently skipped; others are exposed.
    assert set(accessories) == {LIGHT, "switch.kettle", "binary_sensor.door"}

    lamp = accessories[LIGHT]
    assert lamp.display_name == "Desk lamp"
    assert set(lamp._chars) == {"main", "sensor:temperature", "sensor:humidity", "switch:name:quiet"}
    assert lamp._chars["sensor:temperature"]["CurrentTemperature"].value == 21.4
    assert lamp.get_service("TemperatureSensor").get_characteristic("ConfiguredName").value == "Room T"
    assert lamp._chars["switch:name:quiet"]["On"].value is False

    hass.states.async_set("switch.kettle", "on")
    await hass.async_block_till_done()
    assert lamp._chars["switch:name:quiet"]["On"].value is True

    lamp.get_service("Lightbulb").setter_callback({"Brightness": 30})
    lamp.get_service("Switch").setter_callback({"On": 1})
    await hass.async_block_till_done()
    assert turn_on[0].data == {"entity_id": LIGHT, "brightness_pct": 30}
    assert len(script) == 1

    assert accessories["binary_sensor.door"]._chars["main"]["ContactSensorState"].value == 1


async def test_invalid_yaml_is_rejected(hass: HomeAssistant, bridge_env: None) -> None:
    assert not await async_setup_component(
        hass, DOMAIN, {DOMAIN: {"entity_config": {LIGHT: {"sensors": [{"type": "nope", "entity": "sensor.t"}]}}}}
    )


async def test_reload_keeps_numbers(hass: HomeAssistant, bridge_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _states(hass)
    manager = await _setup(
        hass, {"port": 51828, "entity_config": {LIGHT: {"sensors": [{"type": "temperature", "entity": "sensor.t"}]}}}
    )
    lamp = _by_entity(manager)[LIGHT]
    temp_iid = lamp.iid_manager.get_iid(lamp.get_service("TemperatureSensor"))

    new_yaml = {
        DOMAIN: {
            "port": 51828,
            "entity_config": {
                LIGHT: {
                    "sensors": [
                        {"type": "battery", "entity": "sensor.h"},
                        {"type": "temperature", "entity": "sensor.t"},
                    ]
                }
            },
        }
    }

    monkeypatch.setattr("homeassistant.config.load_yaml_config_file", lambda *_: new_yaml)
    await hass.services.async_call(DOMAIN, "reload", blocking=True)
    await hass.async_block_till_done()

    (entry,) = hass.config_entries.async_entries(DOMAIN)
    lamp = _by_entity(entry.runtime_data)[LIGHT]
    assert lamp.iid_manager.get_iid(lamp.get_service("TemperatureSensor")) == temp_iid
    assert "sensor:battery" in lamp._chars

    monkeypatch.setattr(
        "homeassistant.config.load_yaml_config_file",
        lambda *_: {DOMAIN: {"entity_config": {LIGHT: {"type": "bogus_and_invalid", "sensors": "nope"}}}},
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "reload", blocking=True)


async def test_climate_from_yaml(hass: HomeAssistant, bridge_env: None) -> None:
    hass.states.async_set(
        "climate.ac",
        "cool",
        {
            "hvac_modes": ["off", "cool", "heat"],
            "current_temperature": 27,
            "temperature": 23,
            "min_temp": 16,
            "max_temp": 88,
            "fan_modes": ["auto", "low", "high"],
            "fan_mode": "low",
            "supported_features": 937,
        },
    )
    hass.states.async_set("sensor.room", "25.4")
    set_temperature = async_mock_service(hass, "climate", "set_temperature")

    manager = await _setup(
        hass,
        {
            "port": 51829,
            "entity_config": {
                "climate.ac": {"current_temperature": "sensor.room", "max_temp": 30},
            },
        },
    )
    ac = _by_entity(manager)["climate.ac"]
    service = ac.get_service("HeaterCooler")
    chars = ac._chars["main"]
    assert chars["CurrentTemperature"].value == 25.4
    assert chars["CoolingThresholdTemperature"].properties["maxValue"] == 30
    assert ac._chars["climate:fan"]["RotationSpeed"].value == 50
    fan_service = ac.get_service("Fanv2")
    assert fan_service in service.linked_services

    hass.states.async_set("sensor.room", "26")
    await hass.async_block_till_done()
    assert chars["CurrentTemperature"].value == 26

    service.setter_callback({"CoolingThresholdTemperature": 21.5})
    await hass.async_block_till_done()
    assert set_temperature[0].data == {"entity_id": "climate.ac", "temperature": 21.5}


async def test_air_purifier_links_sensors(hass: HomeAssistant, bridge_env: None) -> None:
    hass.states.async_set(
        "fan.purifier",
        "on",
        {"supported_features": 9, "percentage": 40, "preset_modes": ["Auto", "Sleep"], "preset_mode": "Sleep"},
    )
    hass.states.async_set("sensor.pm25", "12")
    hass.states.async_set("sensor.filter", "80")
    manager = await _setup(
        hass,
        {
            "port": 51830,
            "entity_config": {
                "fan.purifier": {
                    "type": "air_purifier",
                    "sensors": [
                        {"type": "pm25", "entity": "sensor.pm25"},
                        {"type": "filter_life", "entity": "sensor.filter"},
                        {"type": "battery", "entity": "sensor.filter"},
                    ],
                }
            },
        },
    )
    acc = _by_entity(manager)["fan.purifier"]
    main = acc.get_service("AirPurifier")
    linked = {s.unique_id for s in main.linked_services}
    assert linked == {"sensor:pm25", "sensor:filter_life"}  # presets and battery are not linked
    assert acc._chars["sensor:pm25"]["AirQuality"].value == 2
    assert acc._chars["fan:preset:sleep"]["On"].value is True



async def test_unknown_state_is_still_available(hass: HomeAssistant, bridge_env: None) -> None:
    hass.states.async_set("scene.movie", "unknown")
    hass.states.async_set("button.ring", "unavailable")
    manager = await _setup(hass, {"port": 51831, "filter": {"include_domains": ["scene", "button"]}})
    accessories = _by_entity(manager)
    assert accessories["scene.movie"].available  # never activated, but works
    assert not accessories["button.ring"].available


async def test_ranges_and_modes_from_yaml(hass: HomeAssistant, bridge_env: None) -> None:
    _states(hass)
    hass.states.async_set("number.volume", "40", {"min": 0, "max": 100, "step": 1})
    hass.states.async_set("select.speed", "medium", {"options": ["low", "medium", "high"]})
    hass.states.async_set("sensor.preset", "eco")
    set_value = async_mock_service(hass, "number", "set_value")
    select = async_mock_service(hass, "select", "select_option")
    script = async_mock_service(hass, "script", "preset")
    manager = await _setup(
        hass,
        {
            "port": 51832,
            "entity_config": {
                LIGHT: {
                    "ranges": [{"entity": "number.volume", "name": "Громкость"}],
                    "modes": [
                        {"entity": "select.speed", "options": {"low": "Тихо", "high": "Сильно"}},
                        {
                            "name": "Пресет",
                            "state": "sensor.preset",
                            "options": ["eco", "boost"],
                            "set": {"action": "script.preset", "data": {"p": "{{ option }}"}},
                            "display": "slider",
                        },
                    ],
                }
            },
        },
    )
    lamp = _by_entity(manager)[LIGHT]
    assert {"range:entity:number.volume", "mode:entity:select.speed:low", "mode:entity:select.speed:high",
            "mode:name:пресет"} <= set(lamp._chars)
    assert lamp._chars["range:entity:number.volume"]["Brightness"].value == 40
    assert lamp._chars["mode:name:пресет"]["Brightness"].value == 50

    by_key = {s.unique_id: s for s in lamp.services}
    by_key["range:entity:number.volume"].setter_callback({"Brightness": 75})
    by_key["mode:entity:select.speed:high"].setter_callback({"On": 1})
    by_key["mode:name:пресет"].setter_callback({"Brightness": 100})
    await hass.async_block_till_done()
    assert set_value[0].data == {"entity_id": "number.volume", "value": 75}
    assert select[0].data == {"entity_id": "select.speed", "option": "high"}
    assert script[0].data == {"p": "boost"}


async def test_mode_with_unknown_option_is_reported(hass: HomeAssistant, bridge_env: None, caplog) -> None:
    _states(hass)
    hass.states.async_set("select.speed", "medium", {"options": ["low", "medium"]})
    manager = await _setup(
        hass, {"port": 51833, "entity_config": {LIGHT: {"modes": [{"entity": "select.speed", "options": ["turbo"]}]}}}
    )
    assert LIGHT not in _by_entity(manager)
    assert "unknown options ['turbo']" in caplog.text


async def test_buttons_from_yaml(hass: HomeAssistant, bridge_env: None) -> None:
    _states(hass)
    hass.states.async_set("event.remote", "2026-10-25T10:00:00", {"event_type": "single", "event_types": ["single", "double"]})
    hass.states.async_set("sensor.wall", "")
    manager = await _setup(
        hass,
        {
            "port": 51834,
            "filter": {"include_entities": ["event.remote"]},
            "entity_config": {
                LIGHT: {
                    "buttons": [
                        {"entity": "event.remote", "name": "Пульт", "single": "single", "double": "double"},
                        {"entity": "sensor.wall", "name": "Стена", "long": ["hold", "long"]},
                    ]
                }
            },
        },
    )
    accessories = _by_entity(manager)
    assert accessories["event.remote"].get_service("StatelessProgrammableSwitch")  # event main entity
    lamp = accessories[LIGHT]
    assert {"button:entity:event.remote", "button:entity:sensor.wall", "buttons:label"} <= set(lamp._chars)
    assert lamp._chars["button:entity:sensor.wall"]["ServiceLabelIndex"].value == 2

    published = []
    char = lamp._chars["button:entity:event.remote"]["ProgrammableSwitchEvent"]
    char.broker.publish = lambda value, sender, *a, **k: published.append((sender.display_name, value))
    hass.states.async_set("event.remote", "2026-10-25T10:00:07", {"event_type": "double", "event_types": ["single", "double"]})
    await hass.async_block_till_done()
    assert ("ProgrammableSwitchEvent", 1) in published


async def test_television_mode_is_a_standalone_accessory(hass: HomeAssistant, bridge_env: None) -> None:
    _states(hass)
    hass.states.async_set("select.input", "hdmi2", {"options": ["hdmi1", "hdmi2", "tv"]})
    select = async_mock_service(hass, "select", "select_option")
    manager = await _setup(
        hass,
        {
            "port": 51840,
            "entity_config": {LIGHT: {"name": "Лампа", "modes": [{"entity": "select.input", "name": "Вход", "display": "television"}]}},
        },
    )
    bridge, tv_server = manager.servers
    assert not bridge.standalone and tv_server.standalone
    assert tv_server.port == 51841 and tv_server.ids.pincode
    assert tv_server.driver.state.port == 51841

    tv = next(a for a in manager.accessories.values() if a.device.standalone)
    assert tv.aid == 1 and tv.display_name == "Lampa Vkhod"  # mDNS name; Apple Home shows the real one
    assert tv.get_service("AccessoryInformation").get_characteristic("Name").value == "Лампа · Вход"
    television = tv.get_service("Television")
    inputs = {s.unique_id: s for s in television.linked_services}
    assert set(inputs) == {"input:hdmi1", "input:hdmi2", "input:tv"}
    assert inputs["input:tv"].get_characteristic("Identifier").value == 3
    assert tv._chars["main"]["ActiveIdentifier"].value == 2  # hdmi2

    television.setter_callback({"ActiveIdentifier": 3})
    await hass.async_block_till_done()
    assert select[0].data == {"entity_id": "select.input", "option": "tv"}

    # The bridge does not carry the television; the lamp has no mode blocks.
    lamp = _by_entity(manager)[LIGHT]
    assert not any(k.startswith("mode:") for k in lamp._chars)

    # Removing the integration deletes the files of every server.
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    import glob
    assert not glob.glob(hass.config.path(".storage", f"{DOMAIN}.{entry.entry_id}.*"))


async def test_reset_unpair_and_diagnostics(hass: HomeAssistant, bridge_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    from custom_components.homekit_alchemy import manager as manager_module
    from custom_components.homekit_alchemy.diagnostics import async_get_config_entry_diagnostics

    monkeypatch.setattr(manager_module, "RESET_DELAY", 0)
    _states(hass)
    manager = await _setup(
        hass,
        {"port": 51850, "filter": {"include_entities": ["switch.kettle"]}, "entity_config": {LIGHT: {"code": "9999"}}},
    )
    lamp = _by_entity(manager)[LIGHT]
    aid, service_iid = lamp.aid, lamp.iid_manager.get_iid(lamp.get_service("Lightbulb"))
    bridge = manager.driver.accessory

    await hass.services.async_call(DOMAIN, "reset_accessory", {"entity_id": [LIGHT]}, blocking=True)
    new_lamp = _by_entity(manager)[LIGHT]
    assert new_lamp is not lamp
    assert bridge.accessories[aid] is new_lamp
    assert new_lamp.iid_manager.get_iid(new_lamp.get_service("Lightbulb")) == service_iid
    # the new accessory follows state changes, the old one no longer does
    hass.states.async_set(LIGHT, "off", {"supported_color_modes": ["brightness"]})
    await hass.async_block_till_done()
    assert new_lamp._chars["main"]["On"].value is False

    (entry,) = hass.config_entries.async_entries(DOMAIN)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert {a["entity_id"] for a in diag["accessories"]} == {LIGHT, "switch.kettle"}
    assert "9999" not in str(diag) and manager.servers[0].ids.pincode not in str(diag)

    manager.driver.state.add_paired_client(str(__import__("uuid").uuid4()).encode(), b"k" * 32, b"\x01")
    assert manager.driver.state.paired
    await hass.services.async_call(DOMAIN, "unpair", {}, blocking=True)
    assert not manager.driver.state.paired


async def test_media_player_television(hass: HomeAssistant, bridge_env: None) -> None:
    hass.states.async_set(
        "media_player.tv",
        "on",
        {"supported_features": 2048 | 128 | 256 | 8 | 1024, "source_list": ["HDMI 1", "Netflix"], "source": "Netflix",
         "friendly_name": "TV"},
    )
    select = async_mock_service(hass, "media_player", "select_source")
    events = []
    hass.bus.async_listen("homekit_alchemy_tv_remote_key_pressed", lambda e: events.append(e.data))
    manager = await _setup(
        hass, {"port": 51860, "entity_config": {"media_player.tv": {"sources": {"HDMI 1": "Приставка", "Netflix": "Netflix"}}}}
    )
    tv_server = next(s for s in manager.servers if s.standalone)
    tv = _by_entity(manager)["media_player.tv"]
    assert tv.aid == 1 and tv_server.port == 51861
    television = tv.get_service("Television")
    linked = {s.unique_id for s in television.linked_services}
    assert linked == {"input:hdmi_1", "input:netflix", "tv:speaker"}
    assert tv._chars["main"]["ActiveIdentifier"].value == 2

    television.setter_callback({"ActiveIdentifier": 1, "RemoteKey": 4})
    await hass.async_block_till_done()
    assert select[0].data == {"entity_id": "media_player.tv", "source": "HDMI 1"}
    assert events == [{"entity_id": "media_player.tv", "key": "arrow_up"}]
