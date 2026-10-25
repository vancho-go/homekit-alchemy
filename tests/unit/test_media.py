"""Media players as Apple televisions."""

from custom_components.homekit_alchemy.model.binding import Command
from custom_components.homekit_alchemy.presets.registry import MainOverrides, main_block
from tests.fakes import FakeView

TV = {  # like the demo "Lounge room" (Netflix) player
    "supported_features": 1 | 128 | 256 | 2048 | 16384 | 16 | 32,
    "source_list": ["dvd", "youtube", "dvd"],
    "source": "youtube",
}
SPEAKER = {"supported_features": 4 | 8 | 1024 | 128 | 256, "volume_level": 0.42, "is_volume_muted": False}
T = {"entity_id": "media_player.tv"}


def test_type_selection() -> None:
    assert main_block("media_player.tv", TV).standalone
    assert main_block("media_player.tv", TV).service == "Television"
    assert main_block("media_player.music", {"supported_features": 1}).service == "Switch"
    assert main_block("media_player.av", {"device_class": "receiver"}).category == "receiver"
    assert main_block("media_player.music", {}, "television").standalone


def test_sources_and_power() -> None:
    main = main_block("media_player.tv", TV)
    inputs = [e for e in main.extras if e.service == "InputSource"]
    assert [(e.key, e.name, e.linked) for e in inputs] == [("input:dvd", "dvd", True), ("input:youtube", "youtube", True)]
    view = FakeView({"media_player.tv": ("playing", TV)})
    values = main.behavior.compute(view)
    assert values["Active"] == 1 and values["ActiveIdentifier"] == 2
    view.set("media_player.tv", "standby", TV)
    assert main.behavior.compute(view)["Active"] == 0
    view.set("media_player.tv", "playing", TV)
    assert main.behavior.handle({"Active": 1}, view) == []  # already on: remote key presses send this
    view.set("media_player.tv", "standby", TV)
    assert main.behavior.handle({"ActiveIdentifier": 1, "Active": 1}, view) == [
        Command("media_player.turn_on", T),
        Command("media_player.select_source", T, {"source": "dvd"}),
    ]

    renamed = main_block("media_player.tv", TV, overrides=MainOverrides(sources=(("youtube", "YouTube"),)))
    assert [e.name for e in renamed.extras if e.service == "InputSource"] == ["YouTube"]
    assert renamed.behavior.compute(FakeView({"media_player.tv": ("on", TV)}))["ActiveIdentifier"] == 1


def test_remote_keys() -> None:
    custom = Command("remote.send_command", {"entity_id": "remote.tv"}, {"command": "UP"})
    behavior = main_block("media_player.tv", TV, overrides=MainOverrides(remote_keys={"arrow_up": custom})).behavior
    view = FakeView({"media_player.tv": ("on", TV)})
    assert behavior.handle({"RemoteKey": 11}, view) == [Command("media_player.media_play_pause", T)]
    assert behavior.handle({"RemoteKey": 2}, view) == [Command("media_player.media_next_track", T)]
    assert behavior.handle({"RemoteKey": 4}, view) == [custom]
    assert behavior.handle({"RemoteKey": 9}, view) == [
        Command("event:homekit_alchemy_tv_remote_key_pressed", data={"entity_id": "media_player.tv", "key": "back"})
    ]
    assert behavior.handle({"RemoteKey": 99}, view) == []


def test_speaker() -> None:
    main = main_block("media_player.tv", {**TV, **SPEAKER, "supported_features": TV["supported_features"] | SPEAKER["supported_features"]})
    speaker = next(e for e in main.extras if e.service == "TelevisionSpeaker")
    assert speaker.linked and speaker.name_key == "volume"
    view = FakeView({"media_player.tv": ("on", SPEAKER)})
    assert speaker.behavior.compute(view) == {"Active": 1, "VolumeControlType": 1, "Mute": False, "Volume": 42}
    assert speaker.behavior.handle({"VolumeSelector": 1, "Mute": 1}, view) == [
        Command("media_player.volume_mute", T, {"is_volume_muted": True}),
        Command("media_player.volume_down", T),
    ]
    assert speaker.behavior.handle({"Volume": 55}, view) == [Command("media_player.volume_set", T, {"volume_level": 0.55})]
    assert not any(e.service == "TelevisionSpeaker" for e in main_block("media_player.tv", TV).extras)


def test_advertised_name() -> None:
    from custom_components.homekit_alchemy.hap.accessory import advertised_name

    assert advertised_name("Гостиная ТВ") == "Gostinaya TV"
    assert advertised_name("Lounge room") == "Lounge room"
    assert advertised_name("日本") == "HomeKit Alchemy"
