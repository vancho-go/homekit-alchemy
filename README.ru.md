# HomeKit Alchemy

**Превращает любые сущности Home Assistant в устройства Apple Home — ровно такими, как вам нужно.**

[English](README.md) · Русский

<!-- screenshot: главный — одна карточка в «Доме», собранная из нескольких сущностей (лампа + температура + влажность) -->

Штатный HomeKit Bridge в Home Assistant показывает одну сущность как одно устройство. HomeKit Alchemy позволяет **собирать** устройства: берёте лампу, добавляете к ней датчик температуры с другого устройства, батарейку с третьего, переключатель «Тихий режим», который запускает скрипт, — и «Дом» видит **одно** устройство.

- **Работает без настройки** для обычных устройств и позволяет поменять любую деталь в YAML.
- **Всё локально.** Без облака, без Homebridge, без лишних аддонов. С Apple общается библиотека [HAP-python](https://github.com/ikalchev/HAP-python) — та же, что у штатного моста.
- **Уживается со штатным HomeKit Bridge.** Свой порт, имя и хранилище: устройства можно переносить по одному.
- **Стабильно в «Доме».** Номера устройств и их частей сохраняются, поэтому добавление или удаление блоков не ломает комнаты, сцены и автоматизации остальных.

---

## Содержание

- [Что можно собрать](#что-можно-собрать)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Настройка](#настройка)
  - [Какие сущности показывать: `filter`](#какие-сущности-показывать-filter)
  - [Настройка устройства: `entity_config`](#настройка-устройства-entity_config)
  - [Значения и действия](#значения-и-действия)
  - [Дополнительные блоки: датчики, переключатели, ползунки, режимы, кнопки](#дополнительные-блоки)
  - [Типы устройств](#типы-устройств)
- [Рецепты](#рецепты)
- [Сервисы и события](#сервисы-и-события)
- [Особенности «Дома», о которых стоит знать](#особенности-дома-о-которых-стоит-знать)
- [Если что-то не работает](#если-что-то-не-работает)
- [Что проверено](#что-проверено)
- [Разработка](#разработка)

---

## Что можно собрать

| В Home Assistant | В «Доме» |
|---|---|
| лампа + датчики комнаты | одна карточка лампы, а внутри температура и влажность |
| кондиционер + сущность «подсветка дисплея» + скрипты | кондиционер со скоростью вентилятора и вашими переключателями «Подсветка», «Осушение», «Вентиляция» |
| реле + геркон | гаражные ворота / калитка, показывающие реальное «открыто/закрыто» |
| `select` с режимами | подписанные переключатели режимов, ступенчатый ползунок или настоящий список |
| любой `number` | ползунок |
| беспроводная кнопка (`event.*`) | программируемый выключатель для автоматизаций «Дома» |
| телевизор (`media_player`) | ТВ как у Apple TV: входы, громкость и пульт в iPhone |

Из коробки поддерживаются: лампы, выключатели, розетки, датчики, термостаты, кондиционеры, водонагреватели, шторы, окна, двери, гаражные ворота, вентиляторы, очистители воздуха, увлажнители и осушители, замки, краны и полив, охранные системы, скрипты, сцены, кнопки и телевизоры. Подробнее — в разделе [Типы устройств](#типы-устройств).

## Требования

- Home Assistant **2026.10** или новее.
- iPhone / iPad в **той же локальной сети**, что и Home Assistant.
- Необязательно: домашний центр Apple (HomePod или Apple TV). Он нужен Apple для управления вне дома, для автоматизаций «Дома» и для событий кнопок. Всё остальное работает и без него.

## Установка

### Через HACS (рекомендуется)

1. HACS → ⋮ → **Пользовательские репозитории** → добавьте `https://github.com/vancho-go/homekit-alchemy`, категория **Интеграция**.
2. Найдите **HomeKit Alchemy** в HACS и установите.
3. Перезапустите Home Assistant.

### Вручную

Скопируйте `custom_components/homekit_alchemy` в `<config>/custom_components/` и перезапустите Home Assistant.

## Быстрый старт

1. Добавьте в `configuration.yaml` (или вынесите в отдельный файл через `homekit_alchemy: !include homekit_alchemy.yaml`):

   ```yaml
   homekit_alchemy:
     filter:
       include_entities:
         - light.desk_lamp
         - climate.living_room_ac
   ```

2. Перезапустите Home Assistant. Интеграция создастся сама, а в уведомлении появится **код сопряжения**.

   <!-- screenshot: уведомление HA с кодом -->

3. На iPhone: **Дом** → **+** → **Добавить аксессуар** → **Другие параметры…** → **HomeKit Alchemy** → введите код. Apple предупредит, что аксессуар не сертифицирован, — нажмите **Все равно добавить**.

   <!-- screenshot: список «Добавить аксессуар» с HomeKit Alchemy -->

4. Готово. Меняйте YAML когда угодно и применяйте без перезапуска: **Инструменты разработчика → YAML → HomeKit Alchemy**.

## Настройка

Полная структура (всё необязательно):

```yaml
homekit_alchemy:
  name: HomeKit Alchemy      # имя моста в «Доме»
  port: 21100                # порт моста; телевизоры и списки занимают следующие (21101, 21102…)
  filter: { … }              # какие сущности показывать
  entity_config:             # как их показывать
    light.desk_lamp: { … }
```

### Какие сущности показывать: `filter`

Правила те же, что у фильтров самого Home Assistant:

```yaml
homekit_alchemy:
  filter:
    include_domains: [light, climate, cover]
    include_entities: [switch.kettle]
    include_entity_globs: ["sensor.*_temperature"]
    exclude_entities: [light.night_lamp]
    exclude_entity_globs: ["*_child_lock"]
```

- Всё, что описано в `entity_config`, показывается, даже если фильтр о нём не говорит (если только оно явно не исключено).
- Скрытые сущности и служебные (настройки / диагностика) показываются, только если указаны по имени.
- Сущности, которые нельзя показать (например, `sensor` мощности), молча пропускаются, если попали через целый домен, и с предупреждением в логе, если указаны явно.

### Настройка устройства: `entity_config`

Ключ — **главная сущность** устройства. Всё остальное прикрепляется к ней.

```yaml
homekit_alchemy:
  entity_config:
    light.desk_lamp:
      name: Настольная лампа   # имя в «Доме»
      type: light              # как показывать, см. Типы устройств
      sensors: [ … ]           # дополнительные блоки, см. ниже
      switches: [ … ]
      ranges: [ … ]
      modes: [ … ]
      buttons: [ … ]
```

Если потом переименовать сущность в Home Assistant, устройство в «Доме» не сломается: оно отслеживается по внутреннему ID сущности.

### Значения и действия

Везде, где нужно значение, можно написать:

```yaml
state: sensor.reed_switch                                   # состояние сущности
state: { entity: climate.ac, attribute: current_humidity }  # атрибут
state: "{{ is_state('switch.beeper', 'off') }}"             # шаблон
```

Везде, где нужно действие:

```yaml
turn_on:
  action: climate.set_preset_mode
  entity_id: climate.ac          # короткая запись для target.entity_id
  data: { preset_mode: quiet }
```

В действиях `ranges` можно использовать `{{ value }}`, в действиях `modes` — `{{ option }}`.

### Дополнительные блоки

#### `sensors` — показания с других сущностей

```yaml
sensors:
  - type: temperature
    entity: sensor.room_temperature
  - type: humidity
    entity: sensor.room_humidity
    name: Влажность в комнате
  - type: battery
    entity: sensor.motion_battery
```

| `type` | Что показывает | Примечания |
|---|---|---|
| `temperature`, `humidity`, `illuminance` | значение | °F переводятся автоматически |
| `co2` | уровень CO₂ | выше 1000 ppm — «превышение» |
| `pm25`, `pm10` | качество воздуха + концентрация | уровни как в Home Assistant |
| `motion`, `occupancy`, `contact`, `leak`, `smoke`, `co` | датчик-детектор | подходит любое значение вида вкл/выкл |
| `battery` | заряд, «низкий заряд» ниже 20 % | Apple показывает его у устройств-датчиков, но не у ламп |
| `filter_life`, `filter_change` | состояние фильтра | «Смените фильтр скоро» ниже 10 % |

Каждый датчик принимает `entity` (+ необязательно `attribute`) или `template`, а также необязательные `name` / `id`.

#### `switches` — свои переключатели

```yaml
switches:
  - name: Подсветка
    entity: light.ac_display              # состояние и вкл/выкл берутся из сущности
  - name: Тихий режим
    state: "{{ is_state_attr('climate.ac', 'preset_mode', 'quiet') }}"
    turn_on: { action: climate.set_preset_mode, entity_id: climate.ac, data: { preset_mode: quiet } }
    turn_off: { action: climate.set_preset_mode, entity_id: climate.ac, data: { preset_mode: none } }
```

Без `state` переключатель запоминает последнюю команду.

#### `ranges` — любое число как ползунок

Показывается как лампа с яркостью: 0 % = `min`, 100 % = `max`. Выключение «лампы» ставит `min`, включение возвращает прежнее значение.

```yaml
ranges:
  - name: Яркость дисплея
    entity: number.display_brightness    # min, max, step и действие берутся из number / input_number
  - name: Громкость
    state: { entity: media_player.speaker, attribute: volume_level }
    min: 0
    max: 1
    step: 0.05
    set: { action: media_player.volume_set, entity_id: media_player.speaker, data: { volume_level: "{{ value }}" } }
```

#### `modes` — выбор из списка

```yaml
modes:
  - name: Режим
    entity: select.humidifier_mode        # варианты и действие берутся из select / input_select
    options:                              # необязательно: подписи, порядок, подмножество
      auto: Авто
      silent: Тихий
  - name: Скорость
    state: sensor.fan_speed
    options: [low, medium, high]
    set: { action: script.set_speed, data: { speed: "{{ option }}" } }
    display: slider
```

| `display` | Как выглядит | Когда подходит |
|---|---|---|
| `switches` (по умолчанию) | подписанный переключатель на каждый вариант | любое количество вариантов; удобно для сцен и Siri |
| `slider` | ползунок-лампа со ступеньками | упорядоченные варианты (низкий → высокий) |
| `television` | настоящий список с выбором одного | когда нужен именно список; становится **отдельным аксессуаром** со своим кодом сопряжения |

<!-- screenshot: три вида режимов рядом -->

> YAML превращает `on` / `off` / `yes` / `no` без кавычек в true/false. В `options` они автоматически превращаются обратно в `"on"` / `"off"`, в остальных местах берите их в кавычки.

#### `buttons` — события для автоматизаций «Дома»

```yaml
buttons:
  - name: Выключатель у двери
    entity: event.wall_switch       # у event.* тип нажатия — атрибут event_type
    single: single                  # значение или список значений
    double: double
    long: [hold, long_press]
  - name: Пульт
    entity: sensor.remote_action    # у остальных сущностей — состояние (или attribute:)
    single: arrow_left_click
```

Каждая кнопка становится «программируемым выключателем» Apple: одно / двойное / долгое нажатие. Для автоматизаций по кнопкам «Дому» нужен **домашний центр**. Сущность `event.*` можно отдать и саму по себе через `filter`: типы нажатий угадываются по её `event_types`.

### Типы устройств

Тип выбирается автоматически. Если нужен другой, укажите `type:`.

| Домен | По умолчанию в «Доме» | Другие значения `type:` | Доп. параметры |
|---|---|---|---|
| `light` | лампа (яркость, цвет, цветовая температура) | `switch`, `outlet` | `state`, `turn_on`, `turn_off` |
| `switch`, `input_boolean` | выключатель | `outlet`, `light`, `garage_door`, `window_covering`, `window`, `door`, `valve`, `sprinkler`, `shower`, `faucet` | `state`, `turn_on`, `turn_off`, параметры штор |
| `sensor` | по `device_class` (см. типы датчиков) | любой тип датчика, кроме `battery` | `state` |
| `binary_sensor` | по `device_class` (`door`/`window` → открытие, `moisture` → протечка, …) | любой тип детектора | `state` |
| `climate` | `heater_cooler`, если умеет охлаждать, иначе `thermostat` | `thermostat`, `heater_cooler` | `current_temperature`, `current_humidity`¹, `min_temp`, `max_temp`, `temperature_step` |
| `water_heater` | термостат (выкл / нагрев) | — | `current_temperature`, `min_temp`, `max_temp` |
| `cover` | штора, либо `window` / `door` / `garage_door` по `device_class` | `window_covering`, `window`, `door`, `garage_door` | `state`, `open`, `close`, `stop`, `obstruction` |
| `fan` | вентилятор (скорость, направление, качание, пресеты переключателями) | `air_purifier` | — |
| `humidifier` | увлажнитель или осушитель (режимы переключателями) | — | `current_humidity` |
| `lock` | замок | — | `code` |
| `valve` | кран | `sprinkler`, `shower`, `faucet` | — |
| `alarm_control_panel` | охрана (дома / не дома / ночь / выкл) | — | `code` |
| `media_player` | ТВ, если это ТВ/ресивер или умеет выбирать источник, иначе выключатель питания | `television`, `receiver`, `switch` | `sources`, `remote_keys` |
| `script`, `scene`, `button`, `input_button` | переключатель, который запускает и сам выключается | — | — |
| `event` | программируемый выключатель | — | `buttons` |

¹ только для `thermostat`; для `heater_cooler` добавьте `sensors: - type: humidity`.

**Климат.** У кондиционеров внутри карточки появляется регулятор скорости вентилятора. У режимов `dry` и `fan_only` нет аналога у Apple — добавьте их через `switches` (см. [рецепт](#кондиционер-с-дополнительными-режимами)).

**Телевизоры.** ТВ — отдельный аксессуар (так требует Apple): добавьте его в «Дом» по отдельному коду из уведомления. Входы берутся из `source_list`; переименовать, упорядочить или скрыть их можно через `sources:` (формат как у `options`). Пульт в iPhone («Пункт управления» → «Пульт Apple TV») отправляет плееру play/pause и следующий/предыдущий трек; стрелки, OK, «назад» и «инфо» выполняют ваши действия из `remote_keys:` или генерируют событие:

```yaml
media_player.living_room_tv:
  sources:
    HDMI 1: Приставка
    Netflix: Netflix
  remote_keys:
    arrow_up: { action: remote.send_command, entity_id: remote.living_room_tv, data: { command: UP } }
```

Имена клавиш: `arrow_up`, `arrow_down`, `arrow_left`, `arrow_right`, `select`, `back`, `exit`, `information`, `play_pause`, `next_track`, `previous_track`, `rewind`, `fast_forward`.

## Рецепты

### Лампа, которая показывает климат в комнате

```yaml
light.desk_lamp:
  name: Настольная лампа
  sensors:
    - { type: temperature, entity: sensor.room_temperature }
    - { type: humidity, entity: sensor.room_humidity }
```

### Кондиционер с дополнительными режимами

```yaml
climate.living_room_ac:
  name: Кондиционер
  max_temp: 30                                  # исправляет неверный диапазон от устройства
  current_temperature: sensor.room_temperature  # брать температуру с более точного датчика
  switches:
    - name: Подсветка
      entity: light.living_room_ac_display
    - name: Осушение
      state: "{{ is_state('climate.living_room_ac', 'dry') }}"
      turn_on:  { action: climate.set_hvac_mode, entity_id: climate.living_room_ac, data: { hvac_mode: dry } }
      turn_off: { action: climate.set_hvac_mode, entity_id: climate.living_room_ac, data: { hvac_mode: "off" } }
```

### Ворота на реле с герконом

```yaml
switch.gate_relay:
  name: Ворота
  type: garage_door
  state: binary_sensor.gate_reed          # on = открыто
  open:  { action: switch.turn_on, entity_id: switch.gate_relay }
  close: { action: switch.turn_on, entity_id: switch.gate_relay }
  obstruction: binary_sensor.gate_photocell
```

### Очиститель воздуха с качеством воздуха и фильтром

```yaml
fan.purifier:
  type: air_purifier
  sensors:
    - { type: pm25, entity: sensor.purifier_pm25 }
    - { type: filter_life, entity: sensor.purifier_filter_life }
```

### Метеостанция

```yaml
sensor.outdoor_temperature:
  name: Погода
  sensors:
    - { type: humidity, entity: sensor.outdoor_humidity }
    - { type: battery, entity: sensor.outdoor_battery }
```

## Сервисы и события

| Сервис | Что делает |
|---|---|
| `homekit_alchemy.reload` | перечитывает YAML без перезапуска Home Assistant; YAML с ошибкой отклоняется, работающая конфигурация остаётся |
| `homekit_alchemy.reset_accessory` | заставляет «Дом» забыть выбранные устройства и добавить их заново (лечит устаревший вид, см. ниже). Комнату и сцены для них в «Доме» придётся назначить заново |
| `homekit_alchemy.unpair` | забывает все сопряжённые iPhone/iPad — у моста и у всех отдельных аксессуаров |

Событие `homekit_alchemy_tv_remote_key_pressed` (`entity_id`, `key`) — клавиша пульта iPhone, для которой не задано действие в `remote_keys:`.

**Диагностика:** Настройки → Устройства и службы → HomeKit Alchemy → ⋮ → Скачать диагностику. Коды сопряжения и коды замков туда не попадают.

## Особенности «Дома», о которых стоит знать

- **Комнату нельзя задать в YAML.** В протоколе Apple для мостов нет такого поля. Выберите комнату в «Доме» один раз — она сохраняется при перезапусках, перезагрузке конфигурации и обновлениях.
- **«Дом» кэширует, как выглядит устройство.** Новые блоки, переименования и новые значения подхватываются сами, но если блоки **перегруппированы** (например, блок, раньше связанный с другим), старый вид может остаться. Выполните `homekit_alchemy.reset_accessory` для этого устройства.
- **Батарейка** показывается у устройств-датчиков («Статус → Уровень заряда»), но не у ламп.
- **Вентиляторы внутри карточки не подписываются**, поэтому ползунки режимов сделаны «лампами». **Качание** не показывается у вентиляторов кондиционеров и у некоторых вентиляторов.
- **Телевизоры и списки `display: television`** — отдельные аксессуары со своим кодом сопряжения и своей комнатой.
- **Роботы-пылесосы** добавляются в «Дом» только через Matter — здесь не поддерживаются. **Камеры** пока не поддерживаются; оставьте их в штатном HomeKit Bridge.
- Имена: «Дом» нормально показывает кириллицу. В списке «Добавить аксессуар» имена транслитерируются (например, «Gostinaya TV»).

## Если что-то не работает

- **Мост не находится при добавлении.** iPhone должен быть в той же сети. Home Assistant должен быть доступен по **TCP 21100+** (порт моста и следующие для телевизоров) и **UDP 5353** (mDNS). Не разносите Home Assistant и iPhone по разным VLAN без mDNS-репитера.
- **«Нет ответа».** Проверьте, что главная сущность не `unavailable`. Затем посмотрите лог (`custom_components.homekit_alchemy`) и скачайте диагностику.
- **Устройство выглядит не так после изменения.** Выполните для него `homekit_alchemy.reset_accessory`.
- **Начать с нуля.** Удалите мост в «Доме», удалите интеграцию в Home Assistant (это удаляет её данные сопряжения), добавьте заново.

Подробный лог:

```yaml
logger:
  logs:
    custom_components.homekit_alchemy: debug
```

## Что проверено

| Тип устройств | Реальное устройство | Демо-устройство | Автотесты |
|---|---|---|---|
| Лампы, выключатели, датчики, составные устройства | ✅ | ✅ | ✅ |
| Термостаты, кондиционеры | ✅ | | ✅ |
| Шторы, окна, двери, гаражные ворота | | ✅ | ✅ |
| Вентиляторы, очистители | | ✅ | ✅ |
| Увлажнители, замки, краны, охрана, водонагреватели, скрипты / сцены / кнопки | | ✅ | ✅ |
| Ползунки, режимы, кнопки, ТВ-списки | | ✅ | ✅ |
| Телевизоры (`media_player`) | | ✅ | ✅ |

Проверено на Home Assistant 2026.10 и iOS 26. Отчёты с ваших устройств очень приветствуются — создайте issue и приложите диагностику.

## Разработка

Запуск тестов:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

## Лицензия

MIT
