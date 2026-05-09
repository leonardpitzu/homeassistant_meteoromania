# MeteoRomania for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration that monitors official weather alerts from [Administrația Națională de Meteorologie (ANM)](https://www.meteoromania.ro/) — colour-coded warnings, affected phenomena, validity intervals, and alert maps, all at a glance.

## Features

### Binary sensor

A binary sensor entity (`binary_sensor.meteoromania`) turns **on** whenever ANM has published one or more active weather alerts and **off** when the sky is clear.

The entity exposes **detailed attributes** for every active alert:

| Attribute | Description |
|---|---|
| `has_alerts` | Whether any alerts are currently active |
| `alert_count` | Total number of active alerts |
| `alert N → type` | Alert type (e.g. *Avertizare meteorologică*) |
| `alert N → interval` | Validity interval as reported by ANM |
| `alert N → color_code` | Severity — `GALBEN`, `PORTOCALIU`, or `ROSU` |
| `alert N → warning M → title` | Headline phenomena for each warning inside the alert |
| `alert N → warning M → phenomena` | Full description of weather phenomena |
| `alert N → url` | Link to the SVG alert map on meteoromania.ro |
| `local_alerts` | List of per-warning dicts with `icon`, `text`, `color`, `r`, `g`, `b` (only when a county is configured) |
| `local_summary` | Concise, region-filtered summary string (only when a county is configured) |
| `local_summary_ascii` | Same as `local_summary` with Romanian diacritics replaced by ASCII equivalents (only when a county is configured) |
| `last_updated` | ISO timestamp of the most recent successful poll |

Example attribute structure:
```
alert 1:
  type: Avertizare meteorologică
  interval: 22 februarie, ora 10:00 – 23 februarie, ora 06:00
  color_code: PORTOCALIU
  warning 1:
    color_code: PORTOCALIU
    interval: 22 februarie, ora 10:00 – 23 februarie, ora 06:00
    title: ninsori viscolite, strat de zăpadă
    phenomena: Se vor semnala ninsori abundente…
  url: https://www.meteoromania.ro/harta.svg.php?…
```

Data is polled every **60 minutes**.

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance.
2. Go to **Integrations** → **⋮** → **Custom repositories**.
3. Add `https://github.com/leonardpitzu/homeassistant_meteoromania` as an **Integration**.
4. Search for **MeteoRomania** and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/meteoromania` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **MeteoRomania**.
3. Confirm — no credentials are needed (ANM data is public).
4. *(Optional)* Select your **county** to enable the `local_summary` attribute.

Only a single instance of the integration is allowed.

You can change the county at any time via **Settings** → **Devices & Services** → **MeteoRomania** → **Configure**.

### Local alerts

When a county is configured, the sensor gains two extra attributes:

#### `local_alerts` (list)

A list of all per-warning dictionaries relevant to your county, sorted by severity (red → orange → yellow), each containing:

| Key | Description |
|---|---|
| `icon` | `alert_yellow`, `alert_orange`, or `alert_red` |
| `text` | Compact summary: phenomena + wind speed (if any) + interval |
| `color` | Severity name (`GALBEN`, `PORTOCALIU`, `ROSU`) |
| `r`, `g`, `b` | RGB values for the severity colour |

Example:
```json
[
  {"icon": "alert_yellow", "text": "Strong wind, Snow 40-45km/h 22 apr 10:00 - 24 apr 10:00", "color": "GALBEN", "r": 255, "g": 255, "b": 0},
  {"icon": "alert_orange", "text": "Strong wind 70-90km/h 23 apr 12:00-20:00", "color": "PORTOCALIU", "r": 255, "g": 126, "b": 0}
]
```

This is ideal for driving per-warning screens on ESPHome pixel displays (Awtrix-style), where each item maps to one `icon_screen` call. The companion automation drops yellow alerts when orange or red are present, keeping the display focused on the most important warnings.

#### `local_summary` (string)

A compact multi-line string derived from `local_alerts`, one line per warning with a colour emoji prefix:

```
🟡 Strong wind, Snow 40-45km/h 22 apr 10:00 - 24 apr 10:00
🟠 Strong wind 70-90km/h 23 apr 12:00-20:00
```

Use it in templates:

```yaml
{{ state_attr('binary_sensor.meteoromania', 'local_summary') }}
```

#### `local_summary_ascii` (string)

Identical to `local_summary` but with Romanian diacritics (ă, â, î, ș, ț) replaced by their ASCII equivalents (a, a, i, s, t). Useful for ESPHome pixel displays whose bitmap fonts lack diacritical glyphs:

```yaml
{{ state_attr('binary_sensor.meteoromania', 'local_summary_ascii') }}
```

## Dashboard ideas

- Use a **conditional card** that only appears when `binary_sensor.meteoromania` is **on** to surface weather warnings without cluttering your dashboard on calm days.
- Use **Markdown cards** with Jinja templates to render each alert's colour code, phenomena, and validity interval in a styled list.
- Display the **alert map** (`url` attribute) with a [Picture Entity card](https://www.home-assistant.io/dashboards/picture-entity/) for a visual overview of affected regions.
- Trigger **automations** (e.g. send a mobile notification) whenever the binary sensor transitions from `off` to `on`.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
