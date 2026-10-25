<div align="center">

<img src="images/logo.svg" width="120" alt="HomeKit Alchemy logo">

# HomeKit Alchemy

**Turn any Home Assistant entities into Apple Home devices — exactly the way you want them.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?logo=homeassistantcommunitystore&logoColor=white)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-18BCF2?logo=homeassistant&logoColor=white)](https://www.home-assistant.io)
[![Version](https://img.shields.io/badge/version-0.1.0-5E5CE6)](https://github.com/vancho-go/homekit-alchemy)
[![Tests](https://github.com/vancho-go/homekit-alchemy/actions/workflows/tests.yml/badge.svg)](https://github.com/vancho-go/homekit-alchemy/actions/workflows/tests.yml)
[![Validate](https://github.com/vancho-go/homekit-alchemy/actions/workflows/validate.yml/badge.svg)](https://github.com/vancho-go/homekit-alchemy/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**English** · [Русский](README.ru.md)

</div>

<p align="center">
  <img src="images/how-it-works.svg" alt="Several Home Assistant entities become one Apple Home device">
</p>

Home Assistant's built-in HomeKit Bridge shows **one entity as one accessory**. HomeKit Alchemy lets you **compose** accessories: take a lamp, add a temperature sensor from another device, a battery from a third one, a "Quiet mode" switch that runs a script — and Apple Home sees **one** device.

<table>
<tr>
<td width="33%" valign="top">

### 🧩 Compose
Any blocks from any entities in one Apple Home card.

</td>
<td width="33%" valign="top">

### 🎛️ Your controls
Own switches, sliders, mode lists and buttons — backed by any action.

</td>
<td width="33%" valign="top">

### 📺 TVs & remote
Inputs, volume and the iPhone remote for any `media_player`.

</td>
</tr>
<tr>
<td valign="top">

### ⚡ Zero config to start
Common devices just work; YAML changes every detail.

</td>
<td valign="top">

### 🏠 Fully local
No cloud, no Homebridge, no add-ons.

</td>
<td valign="top">

### 🤝 Plays nice
Runs next to the built-in HomeKit Bridge — move devices one by one.

</td>
</tr>
</table>

**[Install](#-installation)** · **[Quick start](#-quick-start)** · **[Configuration](#-configuration)** · **[Extra blocks](#-extra-blocks)** · **[Device types](#-device-types)** · **[Recipes](#-recipes)** · **[Services](#-services-and-events)** · **[Apple Home quirks](#-apple-home-quirks)** · **[Troubleshooting](#-troubleshooting)**

---

## ✨ What you can build

<!-- screenshot: a composite card in Apple Home (lamp + temperature + humidity) -->

| You have in Home Assistant | You get in Apple Home |
|---|---|
| a lamp + room sensors | one lamp card with temperature and humidity inside |
| an air conditioner + a "display light" entity + scripts | an air conditioner with fan speed and your own switches "Display", "Dry", "Fan only" |
| a relay + a reed switch | a garage door / gate that shows the real open/closed state |
| a `select` with modes | labelled mode switches, a stepped slider or a real pick-one list |
| any `number` | a slider |
| a wireless button (`event.*`) | a programmable switch for Apple Home automations |
| a TV (`media_player`) | an Apple TV-style accessory with inputs, volume and the iPhone remote |

Supported out of the box: lights, switches, outlets, sensors and detectors, thermostats, air conditioners, water heaters, blinds, windows, doors, garage doors, fans, air purifiers, humidifiers and dehumidifiers, locks, valves and sprinklers, security systems, scripts, scenes, buttons and TVs.

---

## 📦 Installation

**Requirements:** Home Assistant **2026.10+**, an iPhone / iPad on the **same local network**.

> [!TIP]
> An Apple home hub (HomePod or Apple TV) is optional. Apple needs it only for remote access, Apple Home automations and button events — everything else works without it.

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vancho-go&repository=homekit-alchemy&category=integration)

1. Click the button above — it opens HomeKit Alchemy in HACS of your Home Assistant.
2. Click **Download**.
3. Restart Home Assistant.

<details>
<summary><b>Without the button</b></summary>

HACS → ⋮ → **Custom repositories** → add `https://github.com/vancho-go/homekit-alchemy`, category **Integration** → find **HomeKit Alchemy** → **Download** → restart Home Assistant.

</details>

<details>
<summary><b>Manual installation</b></summary>

Copy `custom_components/homekit_alchemy` into `<config>/custom_components/` and restart Home Assistant.

</details>

---

## 🚀 Quick start

**1.** Add to `configuration.yaml` (or keep it in its own file with `homekit_alchemy: !include homekit_alchemy.yaml`):

```yaml
homekit_alchemy:
  filter:
    include_entities:
      - light.desk_lamp
      - climate.living_room_ac
```

**2.** Restart Home Assistant. The integration is created automatically and a notification shows a **QR code** and the **pairing code**.

<!-- screenshot: HA notification with the pairing code -->

**3.** On the iPhone: **Home** → **+** → **Add Accessory** → scan the QR code from the notification. Or tap **More options…** → **HomeKit Alchemy** → enter the code.

<!-- screenshot: Add Accessory list showing "HomeKit Alchemy" -->

> [!NOTE]
> Apple warns that the accessory is not certified — that is expected for every non-commercial HomeKit project. Tap **Add Anyway**.

**4.** Done. Change the YAML any time and apply it without a restart: **Developer tools → YAML → HomeKit Alchemy**.

---

## 🔧 Configuration

Everything is optional:

```yaml
homekit_alchemy:
  name: HomeKit Alchemy      # bridge name in Apple Home
  port: 21100                # bridge port; TVs and lists use the next ones (21101, 21102…)
  filter: { … }              # which entities to show
  entity_config:             # how to show them
    light.desk_lamp: { … }
```

### Choosing entities — `filter`

Same rules as Home Assistant's own filters:

```yaml
homekit_alchemy:
  filter:
    include_domains: [light, climate, cover]
    include_entities: [switch.kettle]
    include_entity_globs: ["sensor.*_temperature"]
    exclude_entities: [light.night_lamp]
    exclude_entity_globs: ["*_child_lock"]
```

- Everything in `entity_config` is shown even if the filter does not mention it (unless explicitly excluded).
- Hidden and configuration / diagnostic entities are shown only when included by name.
- Entities that cannot be shown (e.g. a power `sensor`) are skipped silently from a domain-wide include, with a log warning when named explicitly.

### Tuning a device — `entity_config`

The key is the **main entity** of the device; everything else is attached to it.

```yaml
homekit_alchemy:
  entity_config:
    light.desk_lamp:
      name: Desk lamp          # name in Apple Home
      type: light              # how to show it, see Device types
      sensors: [ … ]           # extra blocks, see below
      switches: [ … ]
      ranges: [ … ]
      modes: [ … ]
      buttons: [ … ]
```

> [!TIP]
> Renaming the entity in Home Assistant later does not break the device in Apple Home — it is tracked by the entity's internal id.

### Values and actions

Anywhere a **value** is expected:

```yaml
state: sensor.reed_switch                                   # state of an entity
state: { entity: climate.ac, attribute: current_humidity }  # an attribute
state: "{{ is_state('switch.beeper', 'off') }}"             # a template
```

Anywhere an **action** is expected:

```yaml
turn_on:
  action: climate.set_preset_mode
  entity_id: climate.ac          # shortcut for target.entity_id
  data: { preset_mode: quiet }
```

Actions of `ranges` can use `{{ value }}`, actions of `modes` — `{{ option }}`.

---

## 🧩 Extra blocks

### `sensors` — readings from other entities

<!-- screenshot: a card with temperature, humidity and battery blocks -->

```yaml
sensors:
  - type: temperature
    entity: sensor.room_temperature
  - type: humidity
    entity: sensor.room_humidity
    name: Room humidity
  - type: battery
    entity: sensor.motion_battery
```

<details>
<summary><b>All sensor types</b></summary>

| `type` | Shows | Notes |
|---|---|---|
| `temperature`, `humidity`, `illuminance` | value | °F is converted automatically |
| `co2` | CO₂ level | "abnormal" above 1000 ppm |
| `pm25`, `pm10` | air quality + density | quality levels as in Home Assistant |
| `motion`, `occupancy`, `contact`, `leak`, `smoke`, `co` | detector | any on/off-like value works |
| `battery` | battery level, low below 20 % | shown on sensor devices, not on lamps |
| `filter_life`, `filter_change` | filter status | "Replace filter soon" below 10 % |

Each sensor takes `entity` (+ optional `attribute`) or `template`, plus optional `name` / `id`.

</details>

### `switches` — your own toggles

<!-- screenshot: an air conditioner card with "Display" / "Dry" switches -->

```yaml
switches:
  - name: Display
    entity: light.ac_display              # state and on/off come from the entity
  - name: Quiet mode
    state: "{{ is_state_attr('climate.ac', 'preset_mode', 'quiet') }}"
    turn_on: { action: climate.set_preset_mode, entity_id: climate.ac, data: { preset_mode: quiet } }
    turn_off: { action: climate.set_preset_mode, entity_id: climate.ac, data: { preset_mode: none } }
```

Without `state` the switch remembers the last command.

### `ranges` — any number as a slider

<!-- screenshot: a range shown as a dimmer -->

Shown as a dimmable lamp: 0 % = `min`, 100 % = `max`. Turning the "lamp" off sets `min`, turning it on restores the previous value.

```yaml
ranges:
  - name: Display brightness
    entity: number.display_brightness    # min, max, step and the action come from number / input_number
  - name: Volume
    state: { entity: media_player.speaker, attribute: volume_level }
    min: 0
    max: 1
    step: 0.05
    set: { action: media_player.volume_set, entity_id: media_player.speaker, data: { volume_level: "{{ value }}" } }
```

### `modes` — pick one of a list

<!-- screenshot: the three mode displays side by side (switches / slider / television) -->

```yaml
modes:
  - name: Mode
    entity: select.humidifier_mode        # options and the action come from select / input_select
    options:                              # optional: labels, order, subset
      auto: Auto
      silent: Silent
  - name: Speed
    state: sensor.fan_speed
    options: [low, medium, high]
    set: { action: script.set_speed, data: { speed: "{{ option }}" } }
    display: slider
```

| `display` | Looks like | Best for |
|---|---|---|
| `switches` *(default)* | one labelled switch per option | any number of options; easy for scenes and Siri |
| `slider` | a lamp slider with steps | ordered options (low → high) |
| `television` | a real pick-one list | when you need a list — it becomes a **separate accessory** with its own pairing code |

> [!WARNING]
> YAML turns bare `on` / `off` / `yes` / `no` into true / false. In `options` they are converted back to `"on"` / `"off"`; anywhere else, put them in quotes.

### `buttons` — events for Apple Home automations

<!-- screenshot: button blocks "Button 1 — Single press" -->

```yaml
buttons:
  - name: Wall switch
    entity: event.wall_switch       # for event.* the press kind is the event_type attribute
    single: single                  # a value or a list of values
    double: double
    long: [hold, long_press]
  - name: Remote
    entity: sensor.remote_action    # for other entities — the state (or `attribute:`)
    single: arrow_left_click
```

Each button becomes an Apple "programmable switch" with single / double / long press. An `event.*` entity can also be shown on its own through `filter` — press kinds are guessed from its `event_types`.

> [!IMPORTANT]
> Apple Home runs automations from buttons only with a **home hub**.

---

## 📚 Device types

The type is chosen automatically; set `type:` to show an entity differently.

<details open>
<summary><b>Domains, defaults and options</b></summary>

| Domain | Default in Apple Home | Other `type:` values | Extra options |
|---|---|---|---|
| `light` | lightbulb (brightness, color, white temperature) | any shape below | `state`, `turn_on`, `turn_off` |
| `switch`, `input_boolean` | switch | `outlet`, `light`, `fan`, `thermostat`², `garage_door`, `window_covering`, `window`, `door`, `valve`, `sprinkler`, `shower`, `faucet` | `state`, `turn_on`, `turn_off`, cover options |
| `sensor` | by `device_class` | any sensor type except `battery` | `state` |
| `binary_sensor` | by `device_class` (`door`/`window` → contact, `moisture` → leak, …) | any detector type | `state` |
| `climate` | `heater_cooler` if it can cool, otherwise `thermostat` | `thermostat`, `heater_cooler` | `current_temperature`, `current_humidity`¹, `min_temp`, `max_temp`, `temperature_step` |
| `water_heater` | thermostat (off / heat) | — | `current_temperature`, `min_temp`, `max_temp` |
| `cover` | blind, or `window` / `door` / `garage_door` by `device_class` | `window_covering`, `window`, `door`, `garage_door` | `state`, `open`, `close`, `stop`, `obstruction` |
| `fan` | fan (speed, direction, oscillation, presets as switches) | `air_purifier` | `presets` |
| `humidifier` | humidifier or dehumidifier (modes as switches) | — | `current_humidity`, `presets` |
| `lock` | lock | — | `code` |
| `valve` | valve | `sprinkler`, `shower`, `faucet` | — |
| `alarm_control_panel` | security system (home / away / night / off) | — | `code` |
| `media_player` | TV if it is a TV / receiver or can select sources, otherwise a power switch | `television`, `receiver`, `switch` | `sources`, `remote_keys` |
| `script`, `scene`, `button`, `input_button` | a switch that runs it and turns itself off | — | — |
| `event` | programmable switch | — | `buttons` |

¹ only for `thermostat`; for `heater_cooler` add `sensors: - type: humidity`.
² a thermostat assembled from parts — see the [recipe](#a-towel-rail-as-a-thermostat).

</details>

### 🎚️ Presets of fans and humidifiers

Their modes become switches named as in Home Assistant. Rename, reorder or hide them with `presets:` (only the listed ones are shown):

```yaml
humidifier.bedroom:
  presets:
    Constant Humidity: Constant
    Sleep: Night
    Strong: Turbo          # "Off" is not listed, so it is hidden
```

### ❄️ Climate

<!-- screenshot: air conditioner card with the fan speed control -->

Air conditioners get a fan speed control inside the card. `dry` and `fan_only` have no Apple equivalent — add them as `switches` ([recipe](#an-air-conditioner-with-extra-modes)).

### 📺 TVs

<!-- screenshot / GIF: TV card with inputs + iPhone remote -->

A TV is a **separate accessory** (Apple requires it): add it in Apple Home with its own code from the notification. Inputs come from `source_list`; rename, reorder or hide them with `sources:`. The iPhone remote (Control Center → Apple TV Remote) sends play/pause and next/previous to the player; arrows, OK, back and info run your `remote_keys:` actions or fire an event.

```yaml
media_player.living_room_tv:
  sources:
    HDMI 1: Game console
    Netflix: Netflix
  remote_keys:
    arrow_up: { action: remote.send_command, entity_id: remote.living_room_tv, data: { command: UP } }
```

<details>
<summary><b>Remote key names</b></summary>

`arrow_up`, `arrow_down`, `arrow_left`, `arrow_right`, `select`, `back`, `exit`, `information`, `play_pause`, `next_track`, `previous_track`, `rewind`, `fast_forward`

</details>

---

## 🧪 Recipes

#### A lamp that also shows the room climate

```yaml
light.desk_lamp:
  name: Desk lamp
  sensors:
    - { type: temperature, entity: sensor.room_temperature }
    - { type: humidity, entity: sensor.room_humidity }
```

#### An air conditioner with extra modes

```yaml
climate.living_room_ac:
  name: Air conditioner
  max_temp: 30                                  # fixes a wrong range reported by the device
  current_temperature: sensor.room_temperature  # use a better sensor than the built-in one
  switches:
    - name: Display
      entity: light.living_room_ac_display
    - name: Dry
      state: "{{ is_state('climate.living_room_ac', 'dry') }}"
      turn_on:  { action: climate.set_hvac_mode, entity_id: climate.living_room_ac, data: { hvac_mode: dry } }
      turn_off: { action: climate.set_hvac_mode, entity_id: climate.living_room_ac, data: { hvac_mode: "off" } }
```

#### A gate on a relay with a reed switch

```yaml
switch.gate_relay:
  name: Gate
  type: garage_door
  state: binary_sensor.gate_reed          # on = open
  open:  { action: switch.turn_on, entity_id: switch.gate_relay }
  close: { action: switch.turn_on, entity_id: switch.gate_relay }
  obstruction: binary_sensor.gate_photocell
```

#### An air purifier with air quality and filter

```yaml
fan.purifier:
  type: air_purifier
  sensors:
    - { type: pm25, entity: sensor.purifier_pm25 }
    - { type: filter_life, entity: sensor.purifier_filter_life }
```

#### A towel rail as a thermostat

Power switch + temperature sensor + target `number` → a real Apple thermostat (off / heat):

```yaml
switch.towel_rail:
  name: Towel rail
  type: thermostat
  current_temperature: sensor.towel_rail_temperature
  target_temperature: number.towel_rail_target      # number / input_number; limits come from it
  min_temp: 30                                      # optional: narrower dial
  max_temp: 60
```

#### A relay in reverse — water shut-off valve

```yaml
light.water_stop_relay:               # relay on = water closed
  name: Water
  type: valve
  state: "{{ is_state('light.water_stop_relay', 'off') }}"
  turn_on:  { action: light.turn_off, entity_id: light.water_stop_relay }
  turn_off: { action: light.turn_on, entity_id: light.water_stop_relay }
```

#### A weather station

```yaml
sensor.outdoor_temperature:
  name: Weather
  sensors:
    - { type: humidity, entity: sensor.outdoor_humidity }
    - { type: battery, entity: sensor.outdoor_battery }
```

---

## 🧰 Services and events

| Service | What it does |
|---|---|
| `homekit_alchemy.reload` | re-reads the YAML without restarting; invalid YAML is rejected and the running config stays |
| `homekit_alchemy.reset_accessory` | makes Apple Home forget the given devices and add them again — fixes a stale look. Their room and scenes have to be set again |
| `homekit_alchemy.unpair` | forgets every paired iPhone / iPad, for the bridge and all separate accessories |

**Event** `homekit_alchemy_tv_remote_key_pressed` (`entity_id`, `key`) — an iPhone remote key without a `remote_keys:` action.

**Diagnostics:** Settings → Devices & services → HomeKit Alchemy → ⋮ → **Download diagnostics**. Pairing codes and lock codes are never included.

---

## 🍏 Apple Home quirks

> [!IMPORTANT]
> **Rooms cannot be set from YAML.** Apple's protocol for bridges has no room field. Pick the room once in Apple Home — it survives restarts, reloads and updates.

> [!TIP]
> **Apple Home caches how a device looks.** New blocks, renames and values appear by themselves, but if blocks are *regrouped* the old look can stay. Run `homekit_alchemy.reset_accessory` for that device.

- **Batteries** are shown on sensor devices (Status → Battery), not on lamps.
- **Fans inside a card are not labelled** — that is why mode sliders are lamps. **Oscillation** is hidden for climate fans and some fans.
- **TVs and `display: television` lists** are separate accessories with their own code and room.
- **Robot vacuums** reach Apple Home only through Matter — not supported. **Cameras** are not supported yet; keep them in the built-in HomeKit Bridge.
- Non-Latin names are fine in Apple Home; in the "Add Accessory" list they are transliterated (e.g. "Gostinaya TV").

---

## 🩺 Troubleshooting

<details>
<summary><b>The bridge is not found when adding</b></summary>

The iPhone must be on the same network. Home Assistant must be reachable on **TCP 21100+** (bridge port and the next ones for TVs) and **UDP 5353** (mDNS). Avoid putting Home Assistant and the iPhone in different VLANs without an mDNS reflector.

</details>

<details>
<summary><b>"Not responding"</b></summary>

Check that the main entity is not `unavailable`. Then look at the log and download diagnostics. Debug log:

```yaml
logger:
  logs:
    custom_components.homekit_alchemy: debug
```

</details>

<details>
<summary><b>A device looks wrong after a change</b></summary>

Run `homekit_alchemy.reset_accessory` for it.

</details>

<details>
<summary><b>Starting over</b></summary>

Remove the bridge in Apple Home, delete the integration in Home Assistant (this deletes its pairing data), add it again.

</details>

---

## ✅ What is tested

| Device type | Real device | Demo device | Automated tests |
|---|:---:|:---:|:---:|
| Lights, switches, sensors, composite devices | ✅ | ✅ | ✅ |
| Thermostats, air conditioners | ✅ | | ✅ |
| Covers, windows, doors, garage doors | | ✅ | ✅ |
| Fans, air purifiers | | ✅ | ✅ |
| Humidifiers, locks, valves, security, water heaters, scripts / scenes / buttons | | ✅ | ✅ |
| Ranges, modes, buttons, TV lists | | ✅ | ✅ |
| TVs (`media_player`) | | ✅ | ✅ |

Tested on Home Assistant 2026.10 and iOS 26. Reports from your devices are very welcome — [open an issue](https://github.com/vancho-go/homekit-alchemy/issues) with diagnostics attached.

---

## 🤝 Contributing

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

Issues and pull requests are welcome.

## 📄 License

[MIT](LICENSE)
