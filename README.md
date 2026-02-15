# Meteo Romania Alerts

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that monitors weather alerts from [Administrația Națională de Meteorologie (ANM)](https://www.meteoromania.ro/).

## Features

- Binary sensor that turns **on** when there are active weather alerts in Romania
- Exposes alert details (type, interval, color code, phenomena, affected zones) as sensor attributes
- Polls ANM every hour for updates

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click the three-dot menu (top right) → **Custom repositories**
4. Add this repository URL and select **Integration** as the category
5. Click **Add**, then install **Meteo Romania Alerts**
6. Restart Home Assistant
7. Go to **Settings → Devices & Services → Add Integration** and search for **Meteo Romania Alerts**

## Manual Installation

1. Copy the `custom_components/meteo_romania_alerts` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration from **Settings → Devices & Services**

## License

See [LICENSE](LICENSE) for details.
