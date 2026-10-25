# HomeKit Alchemy

**Turn any Home Assistant entities into Apple Home devices — exactly the way you want them.**

English · [Русский](README.ru.md)

<!-- screenshot: hero — one Apple Home card built from several HA entities (lamp + temperature + humidity) -->

Home Assistant's built-in HomeKit Bridge shows one entity as one accessory. HomeKit Alchemy lets you **compose** accessories: take a lamp, add a temperature sensor from another device, a battery from a third one, a "Quiet mode" switch that runs a script — and Apple Home sees **one** device.

- **Works with no configuration** for common devices, and lets you change every detail in YAML.
- **Runs locally.** No cloud, no Homebridge, no extra add-ons. Apple's protocol is spoken by [HAP-python](https://github.com/ikalchev/HAP-python), the same library the built-in bridge uses.
- **Lives next to the built-in HomeKit Bridge.** Separate port, name and storage: you can move devices over one by one.
- **Stable in Apple Home.** Numbers of accessories and their parts are stored, so adding or removing blocks never breaks rooms, scenes or automations of other blocks.

---

## Contents

- [What you can build](#what-you-can-build)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Configuration](#configuration)
  - [Choosing entities: `filter`](#choosing-entities-filter)
  - [Tuning a device: `entity_config`](#tuning-a-device-entity_config)
  - [Values and actions](#values-and-actions)
  - [Extra blocks: sensors, switches, ranges, modes, buttons](#extra-blocks)
  - [Device types](#device-types)
- [Recipes](#recipes)
- [Services and events](#services-and-events)
- [Apple Home quirks you should know](#apple-home-quirks-you-should-know)
- [Troubleshooting](#troubleshooting)
- [What is tested](#what-is-tested)
- [Development](#development)

---

## What you can build

| You have in Home Assistant | You get in Apple Home |
|---|---|
| a lamp + room sensors | one lamp card with temperature and humidity inside |
| an air conditioner + a "display light" entity + scripts | an air conditioner with fan speed and your own switches "Display", "Dry", "Fan only" |
| a relay + a reed switch | a garage door / gate that shows the real open/closed state |
| a `select` with modes | labelled mode switches, a stepped slider or a real pick-one list |
| any `number` | a slider |
| a wireless button (`event.*`) | a programmable switch for Apple Home automations |
| a TV (`media_player`) | an Apple TV-style accessory with inputs, volume and the iPhone remote |

Supported out of the box: lights, switches, outlets, sensors and detectors, thermostats, air conditioners, water heaters, blinds, windows, doors, garage doors, fans, air purifiers, humidifiers and dehumidifiers, locks, valves and sprinklers, security systems, scripts, scenes, buttons and TVs. See [Device types](#device-types).

## Requirements

- Home Assistant **2026.10** or newer.
- An iPhone / iPad on the **same local network** as Home Assistant.
- Optional: an Apple home hub (HomePod or Apple TV) — needed by Apple for remote access, for Apple Home automations and for button events. Everything else works without it.

## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/vancho-go/homekit-alchemy`, category **Integration**.
2. Find **HomeKit Alchemy** in HACS and install it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/homekit_alchemy` into `<config>/custom_components/` and restart Home Assistant.

## Quick start

1. Add to `configuration.yaml` (or put it in its own file with `homekit_alchemy: !include homekit_alchemy.yaml`):

   ```yaml
   homekit_alchemy:
     filter:
       include_entities:
         - light.desk_lamp
         - climate.living_room_ac
   ```

2. Restart Home Assistant. The integration is created automatically, and a notification shows the **pairing code**.

   <!-- screenshot: HA notification with the pairing code -->

3. On the iPhone: **Home** → **+** → **Add Accessory** → **More options…** → **HomeKit Alchemy** → enter the code. Apple warns that the accessory is not certified — tap **Add Anyway**.

   <!-- screenshot: Add Accessory list showing "HomeKit Alchemy" -->

4. Done. Change the YAML at any time and apply it without restarting: **Developer tools → YAML → HomeKit Alchemy**.

## Configuration

Full structure (everything is optional):

```yaml
homekit_alchemy:
  name: HomeKit Alchemy      # bridge name in Apple Home
  port: 21100                # bridge port; TVs and lists use the next ports (21101, 21102…)
  filter: { … }              # which entities to show
  entity_config:             # how to show them
    light.desk_lamp: { … }
```

### Choosing entities: `filter`

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

- Everything listed in `entity_config` is shown even if the filter does not mention it (unless it is explicitly excluded).
- Hidden entities and configuration/diagnostic entities are only shown when included by name.
- Entities that cannot be shown (for example a `sensor` measuring power) are skipped silently when they come from a domain-wide include, and with a warning in the log when you named them explicitly.

### Tuning a device: `entity_config`

The key is the **main entity** of the device. Everything else is attached to it.

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

Renaming the entity in Home Assistant later does not break the device in Apple Home: it is tracked by the entity's internal id.

### Values and actions

Anywhere a value is expected you can write:

```yaml
state: sensor.reed_switch                                   # state of an entity
state: { entity: climate.ac, attribute: current_humidity }  # an attribute
state: "{{ is_state('switch.beeper', 'off') }}"             # a template
```

Anywhere an action is expected:

```yaml
turn_on:
  action: climate.set_preset_mode
  entity_id: climate.ac          # shortcut for target.entity_id
  data: { preset_mode: quiet }
```

In actions of `ranges` you can use `{{ value }}`, in actions of `modes` — `{{ option }}`.

### Extra blocks

#### `sensors` — readings from other entities

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

| `type` | Shows | Notes |
|---|---|---|
| `temperature`, `humidity`, `illuminance` | value | °F is converted automatically |
| `co2` | CO₂ level | marked "abnormal" above 1000 ppm |
| `pm25`, `pm10` | air quality + density | quality levels as in Home Assistant |
| `motion`, `occupancy`, `contact`, `leak`, `smoke`, `co` | detector | any on/off-like value works |
| `battery` | battery level, low battery below 20 % | Apple shows it on sensor devices, not on lamps |
| `filter_life`, `filter_change` | filter status | "Replace filter soon" below 10 % |

Each sensor takes `entity` (+ optional `attribute`) or `template`, and optional `name` / `id`.

#### `switches` — your own toggles

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

#### `ranges` — any number as a slider

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

#### `modes` — pick one of a list

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
| `switches` (default) | one labelled switch per option | any number of options; easy for scenes and Siri |
| `slider` | a lamp slider with steps | ordered options (low → high) |
| `television` | a real pick-one list | when you need a list; it becomes a **separate accessory** with its own pairing code |

<!-- screenshot: the three mode displays side by side -->

> YAML turns bare `on` / `off` / `yes` / `no` into booleans. In `options` they are converted back to `"on"` / `"off"`; elsewhere, quote them.

#### `buttons` — events for Apple Home automations

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

Each button becomes an Apple "programmable switch" with single / double / long press. Apple Home needs a **home hub** to run automations from buttons. An `event.*` entity can also be shown on its own through `filter`: press kinds are guessed from its `event_types`.

### Device types

The type is chosen automatically. Change it with `type:` when you want something else.

| Domain | Default in Apple Home | Other `type:` values | Extra options |
|---|---|---|---|
| `light` | lightbulb (brightness, color, white temperature) | `switch`, `outlet` | `state`, `turn_on`, `turn_off` |
| `switch`, `input_boolean` | switch | `outlet`, `light`, `garage_door`, `window_covering`, `window`, `door`, `valve`, `sprinkler`, `shower`, `faucet` | `state`, `turn_on`, `turn_off`, cover options |
| `sensor` | by `device_class` (see sensor types) | any sensor type except `battery` | `state` |
| `binary_sensor` | by `device_class` (`door`/`window` → contact, `moisture` → leak, …) | any detector type | `state` |
| `climate` | `heater_cooler` if it can cool, otherwise `thermostat` | `thermostat`, `heater_cooler` | `current_temperature`, `current_humidity`¹, `min_temp`, `max_temp`, `temperature_step` |
| `water_heater` | thermostat (off / heat) | — | `current_temperature`, `min_temp`, `max_temp` |
| `cover` | blind, or `window` / `door` / `garage_door` by `device_class` | `window_covering`, `window`, `door`, `garage_door` | `state`, `open`, `close`, `stop`, `obstruction` |
| `fan` | fan (speed, direction, oscillation, presets as switches) | `air_purifier` | — |
| `humidifier` | humidifier or dehumidifier (modes as switches) | — | `current_humidity` |
| `lock` | lock | — | `code` |
| `valve` | valve | `sprinkler`, `shower`, `faucet` | — |
| `alarm_control_panel` | security system (home / away / night / off) | — | `code` |
| `media_player` | TV if it is a TV/receiver or can select sources, otherwise a power switch | `television`, `receiver`, `switch` | `sources`, `remote_keys` |
| `script`, `scene`, `button`, `input_button` | a switch that runs it and turns itself off | — | — |
| `event` | programmable switch | — | `buttons` |

¹ only for `thermostat`; for `heater_cooler` add `sensors: - type: humidity`.

**Climate.** Air conditioners get a fan speed control inside the card. `dry` and `fan_only` have no Apple equivalent — add them as `switches` (see [recipes](#an-air-conditioner-with-extra-modes)).

**TVs.** A TV is a separate accessory (Apple requires it): add it in Apple Home with its own code from the notification. Inputs come from `source_list`; rename, reorder or hide them with `sources:` (same format as `options`). The iPhone remote (Control Center → Apple TV Remote) sends play/pause and next/previous to the player; arrows, OK, back and info run your `remote_keys:` actions or fire an event:

```yaml
media_player.living_room_tv:
  sources:
    HDMI 1: Game console
    Netflix: Netflix
  remote_keys:
    arrow_up: { action: remote.send_command, entity_id: remote.living_room_tv, data: { command: UP } }
```

Key names: `arrow_up`, `arrow_down`, `arrow_left`, `arrow_right`, `select`, `back`, `exit`, `information`, `play_pause`, `next_track`, `previous_track`, `rewind`, `fast_forward`.

## Recipes

### A lamp that also shows the room climate

```yaml
light.desk_lamp:
  name: Desk lamp
  sensors:
    - { type: temperature, entity: sensor.room_temperature }
    - { type: humidity, entity: sensor.room_humidity }
```

### An air conditioner with extra modes

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

### A gate on a relay with a reed switch

```yaml
switch.gate_relay:
  name: Gate
  type: garage_door
  state: binary_sensor.gate_reed          # on = open
  open:  { action: switch.turn_on, entity_id: switch.gate_relay }
  close: { action: switch.turn_on, entity_id: switch.gate_relay }
  obstruction: binary_sensor.gate_photocell
```

### An air purifier with air quality and filter

```yaml
fan.purifier:
  type: air_purifier
  sensors:
    - { type: pm25, entity: sensor.purifier_pm25 }
    - { type: filter_life, entity: sensor.purifier_filter_life }
```

### A weather station

```yaml
sensor.outdoor_temperature:
  name: Weather
  sensors:
    - { type: humidity, entity: sensor.outdoor_humidity }
    - { type: battery, entity: sensor.outdoor_battery }
```

## Services and events

| Service | What it does |
|---|---|
| `homekit_alchemy.reload` | re-reads the YAML without restarting Home Assistant; invalid YAML is rejected and the running config stays |
| `homekit_alchemy.reset_accessory` | makes Apple Home forget the given devices and add them again (fixes a stale look, see below). Their room and scenes in Apple Home have to be set again |
| `homekit_alchemy.unpair` | forgets every paired iPhone/iPad, for the bridge and all separate accessories |

Event `homekit_alchemy_tv_remote_key_pressed` (`entity_id`, `key`) — a key of the iPhone remote that has no `remote_keys:` action.

**Diagnostics:** Settings → Devices & services → HomeKit Alchemy → ⋮ → Download diagnostics. Pairing codes and lock codes are never included.

## Apple Home quirks you should know

- **Rooms cannot be set from YAML.** Apple's protocol for bridges has no room field. Choose the room once in Apple Home; it survives restarts, reloads and updates.
- **Apple Home caches how a device looks.** New blocks, renames and new values appear by themselves, but if blocks are **regrouped** (for example a block that used to be linked to another), the old look can stay. Use `homekit_alchemy.reset_accessory` for that device.
- **Batteries** are shown on sensor devices ("Status → Battery"), but not on lamps.
- **Fans inside a card are not labelled**, so mode sliders are lamps, not fans. **Oscillation** is not shown for climate fans and some fans.
- **TVs and `display: television` lists** are separate accessories with their own pairing code and room.
- **Robot vacuums** can only be added to Apple Home through Matter — not supported here. **Cameras** are not supported yet; keep them in the built-in HomeKit Bridge.
- Names: Apple shows non-Latin names fine. In the "Add Accessory" list they are transliterated (e.g. "Gostinaya TV").

## Troubleshooting

- **The bridge is not found when adding.** The iPhone must be on the same network. Home Assistant must be reachable on **TCP 21100+** (bridge port and the next ones for TVs) and **UDP 5353** (mDNS). Avoid putting Home Assistant and the iPhone in different VLANs without an mDNS reflector.
- **"Not responding".** Check that the main entity is not `unavailable`. Then look at the log (`custom_components.homekit_alchemy`) and download diagnostics.
- **A device looks wrong after a change.** Run `homekit_alchemy.reset_accessory` for it.
- **Starting over.** Remove the bridge in Apple Home, delete the integration in Home Assistant (this deletes its pairing data), add it again.

Debug log:

```yaml
logger:
  logs:
    custom_components.homekit_alchemy: debug
```

## What is tested

| Device type | Real device | Demo device | Automated tests |
|---|---|---|---|
| Lights, switches, sensors, composite devices | ✅ | ✅ | ✅ |
| Thermostats, air conditioners | ✅ | | ✅ |
| Covers, windows, doors, garage doors | | ✅ | ✅ |
| Fans, air purifiers | | ✅ | ✅ |
| Humidifiers, locks, valves, security, water heaters, scripts / scenes / buttons | | ✅ | ✅ |
| Ranges, modes, buttons, TV lists | | ✅ | ✅ |
| TVs (`media_player`) | | ✅ | ✅ |

Tested on Home Assistant 2026.10 and iOS 26. Reports from your devices are very welcome — open an issue with diagnostics attached.

## Development

Run the tests:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

## License

MIT
