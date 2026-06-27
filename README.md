# MeteoRomania for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration that monitors official weather alerts from [Administrația Națională de Meteorologie (ANM)](https://www.meteoromania.ro/) - colour-coded warnings, affected phenomena, validity intervals, and alert maps, all at a glance.

## Features

### Binary sensor

A binary sensor entity (`binary_sensor.meteoromania`) turns **on** whenever ANM has published one or more active weather alerts and **off** when the sky is clear.

The entity exposes **detailed attributes** for every active alert:

| Attribute | Description |
|---|---|
| `has_alerts` | Whether any alerts are currently active |
| `alert_count` | Total number of active alerts |
| `alert N -> type` | Alert type - `INFORMARE METEOROLOGICĂ` or `ATENȚIONARE METEOROLOGICĂ` |
| `alert N -> color_code` | Alert severity - `GALBEN`, `PORTOCALIU`, `ROSU`, or `NECUNOSCUT` |
| `alert N -> interval` | Validity interval (present on `INFORMARE` alerts) |
| `alert N -> title` | Headline of the alert (present on `INFORMARE` alerts) |
| `alert N -> warning M -> color_code` | Severity of the individual warning |
| `alert N -> warning M -> interval` | Validity interval of the warning |
| `alert N -> warning M -> title` | Headline phenomena for each warning inside the alert |
| `alert N -> warning M -> phenomena` | Full description of weather phenomena (optional) |
| `alert N -> url` | Link to the SVG alert map on meteoromania.ro (per-alert or per-warning) |
| `local_alerts` | List of per-warning dicts with `icon`, `text`, `color`, `r`, `g`, `b` (only when a county is configured) |
| `local_summary` | Concise, region-filtered summary string (only when a county is configured) |
| `last_updated` | ISO timestamp of the most recent successful poll |

Example attribute structure:
```
alert 1:
  type: INFORMARE METEOROLOGICĂ
  color_code: PORTOCALIU
  interval: 22 februarie, ora 10:00 - 23 februarie, ora 06:00
  title: Ninsori și intensificări ale vântului
  warning 1:
    color_code: PORTOCALIU
    interval: 22 februarie, ora 10:00 - 23 februarie, ora 06:00
    title: ninsori viscolite, strat de zăpadă
    phenomena: Se vor semnala ninsori abundente...
  url: https://www.meteoromania.ro/harta.svg.php?...
```

> Plain warnings (without a national *informare*) come through as
> `type: ATENȚIONARE METEOROLOGICĂ` and omit the alert-level `interval`/`title`.
> Always use `.get()` in templates for optional keys (`interval`, `title`,
> `phenomena`, `url`) - a missing-key subscript makes a Markdown card render blank.

Data is polled every **60 minutes**.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** -> **⋮** -> **Custom repositories**.
3. Add `https://github.com/leonardpitzu/homeassistant_meteoromania` as an **Integration**.
4. Search for **MeteoRomania** and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/meteoromania` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** -> **Devices & Services** -> **Add Integration**.
2. Search for **MeteoRomania**.
3. On the setup form, *(optionally)* pick your **county** to enable the `local_alerts` / `local_summary` attributes - leave it on *None (show all)* for nationwide coverage. No credentials are needed (ANM data is public).

Only a single instance of the integration is allowed.

You can change the county at any time via **Settings** -> **Devices & Services** -> **MeteoRomania** -> **Configure**.

### Local alerts

When a county is configured, the sensor gains two extra attributes:

#### `local_alerts` (list)

A list of all per-warning dictionaries relevant to your county, sorted by severity (red -> orange -> yellow), each containing:

| Key | Description |
|---|---|
| `icon` | `alert_yellow`, `alert_orange`, or `alert_red` |
| `text` | Compact summary: phenomena + wind speed (if any) + interval |
| `color` | Severity name (`GALBEN`, `PORTOCALIU`, `ROSU`) |
| `r`, `g`, `b` | RGB values for the severity colour |

Example:
```json
[
  {"icon": "alert_yellow", "text": "Strong wind, Snow 40-45km/h 22/4 10h-24/4 10h", "color": "GALBEN", "r": 255, "g": 200, "b": 0},
  {"icon": "alert_orange", "text": "Strong wind 70-90km/h 23/4 12h-20h", "color": "PORTOCALIU", "r": 255, "g": 120, "b": 0}
]
```

This is ideal for driving per-warning screens on ESPHome pixel displays (Awtrix-style), where each item maps to one `icon_screen` call. The companion automation drops yellow alerts when orange or red are present, keeping the display focused on the most important warnings.

#### `local_summary` (string)

A compact multi-line string derived from `local_alerts`, one line per warning with a colour emoji prefix:

```
🟡 Strong wind, Snow 40-45km/h 22/4 10h-24/4 10h
🟠 Strong wind 70-90km/h 23/4 12h-20h
```

Use it in templates:

```yaml
{{ state_attr('binary_sensor.meteoromania', 'local_summary') }}
```

## Dashboard

The following [Markdown card](https://www.home-assistant.io/dashboards/markdown/) renders every active alert and its warnings - colour-coded headers, validity intervals, phenomena descriptions, and the SVG alert map for each warning (falling back to the alert's shared map). When there are no alerts it shows a single tidy line:

```yaml
type: markdown
title: Weather Alerts
content: |
  {% set eid = 'binary_sensor.meteoromania' %}
  {% if is_state(eid, 'on') %}
  {% for i in range(1, (state_attr(eid, 'alert_count') | int(0)) + 1) %}
  {% set a = state_attr(eid, 'alert ' ~ i) %}
  {% if a %}
  ### ⚠️ Alert {{ i }} - {{ a.get('type', '') }}
  **Cod:** {{ a.get('color_code', '') }}
  {% if a.get('interval') %}**Interval:** {{ a.get('interval') }}{% endif %}
  {% if a.get('title') %}
  _{{ a.get('title') }}_
  {% endif %}
  {% set wcount = a.keys() | select('match', '^warning ') | list | count %}
  {% for j in range(1, wcount + 1) %}
  {% set w = a.get('warning ' ~ j) %}
  {% if w %}
  {% set c = (w.get('color_code', '')) | upper %}
  {% set icon = '🟡' if c == 'GALBEN' else '🟠' if c == 'PORTOCALIU' else '🔴' if c == 'ROSU' else '⚪' %}
  {% set murl = w.get('url') or a.get('url') %}
  #### {{ icon }} Warning {{ j }} - {{ w.get('title', '') }}
  {% if w.get('interval') %}**Interval:** {{ w.get('interval') }}{% endif %}
  {% if w.get('phenomena') %}
  {{ w.get('phenomena') }}
  {% endif %}
  {% if murl %}
  ![Warning {{ j }} map]({{ murl }})
  {% endif %}
  {% endif %}
  {% endfor %}
  {% if wcount == 0 and a.get('url') %}
  ![Alert {{ i }} map]({{ a.get('url') }})
  {% endif %}
  {% endif %}
  {% endfor %}
  {% else %}
  ✅ No current meteo alerts.
  {% endif %}
```

Put it on its own view and add a **conditional badge** to your main view that only shows up (and links to the alerts view) when something is active:

```yaml
type: entity
entity: binary_sensor.meteoromania
name: Weather Alerts
show_name: true
show_state: false
show_icon: true
visibility:
  - condition: state
    entity: binary_sensor.meteoromania
    state: "on"
tap_action:
  action: navigate
  navigation_path: /lovelace-weather/weather-alert
```

### Other ideas

- Drive an **automation** (e.g. a mobile notification) off the binary sensor's `off` -> `on` transition.
- Feed `local_summary` into a compact text/Markdown card, or `local_alerts` into per-warning screens on an ESPHome pixel display.
- Display a single `url` map directly with a [Picture card](https://www.home-assistant.io/dashboards/picture/).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
