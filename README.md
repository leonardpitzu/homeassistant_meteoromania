# Meteo Romania Alerts for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration that monitors official weather alerts from [Administrația Națională de Meteorologie (ANM)](https://www.meteoromania.ro/) — colour-coded warnings, affected phenomena, validity intervals, and alert maps, all at a glance.

## Features

### Binary sensor

A binary sensor entity (`binary_sensor.meteo_romania_alert`) turns **on** whenever ANM has published one or more active weather alerts and **off** when the sky is clear.

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
| `local_summary` | Concise, region-filtered summary (only when a county is configured) |
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
3. Add `https://github.com/leonardpitzu/meteo_romania_alerts` as an **Integration**.
4. Search for **Meteo Romania Alerts** and install it.
5. Restart Home Assistant.

### Manual

1. Copy the `custom_components/meteo_romania_alerts` folder into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Meteo Romania Alerts**.
3. Confirm — no credentials are needed (ANM data is public).
4. *(Optional)* Select your **county** to enable the `local_summary` attribute.

Only a single instance of the integration is allowed.

You can change the county at any time via **Settings** → **Devices & Services** → **Meteo Romania Alerts** → **Configure**.

### Local summary

When a county is configured, the sensor gains a `local_summary` attribute — a compact, one-line-per-warning text filtered to your region. Only warnings that mention your county, its geographic region, or a nationwide scope are included.

```
🟡 Strong wind, Snow 40-45km/h 22 apr 10:00 - 24 apr 10:00
🟡 Strong wind 50-70km/h 23 apr 09:00-22:00
🟠 Strong wind 70-90km/h 23 apr 12:00-20:00
```

This is ideal for space-constrained displays (e.g. LED pixel screens, small dashboards) or notification text. Use it in a template:

```yaml
{{ state_attr('binary_sensor.meteo_romania_alert', 'local_summary') }}
```

## Dashboard ideas

- Use a **conditional card** that only appears when `binary_sensor.meteo_romania_alert` is **on** to surface weather warnings without cluttering your dashboard on calm days.
- Use **Markdown cards** with Jinja templates to render each alert's colour code, phenomena, and validity interval in a styled list.
- Display the **alert map** (`url` attribute) with a [Picture Entity card](https://www.home-assistant.io/dashboards/picture-entity/) for a visual overview of affected regions.
- Trigger **automations** (e.g. send a mobile notification) whenever the binary sensor transitions from `off` to `on`.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
