"""Tests for the Meteo Romania Alerts binary sensor."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteo_romania_alerts.const import DOMAIN

ENTITY_ID = "binary_sensor.meteo_romania_alert"

MOCK_ALERTS_ACTIVE = {
    "has_alerts": True,
    "alert_count": 1,
    "alert 1": {
        "type": "Avertizare meteorologica",
        "interval": "15 - 16 februarie",
        "color_code": "GALBEN",
    },
}

MOCK_ALERTS_NONE = {"has_alerts": False, "alert_count": 0}


async def _setup(hass, alerts_data):
    """Set up the integration with mocked alert data and return the entry."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.meteo_romania_alerts.api.MeteoRomaniaApiClient.fetch_alerts",
        new_callable=AsyncMock,
        return_value=alerts_data,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_sensor_on_with_alerts(hass):
    """Binary sensor is ON when alerts are present."""
    entry = await _setup(hass, MOCK_ALERTS_ACTIVE)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "on"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensor_off_without_alerts(hass):
    """Binary sensor is OFF when there are no alerts."""
    entry = await _setup(hass, MOCK_ALERTS_NONE)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "off"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_attributes_include_alert_data(hass):
    """Extra state attributes contain the alert payload."""
    entry = await _setup(hass, MOCK_ALERTS_ACTIVE)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["has_alerts"] is True
    assert state.attributes["alert_count"] == 1
    assert "last_updated" in state.attributes

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_attributes_include_last_updated(hass):
    """Even with no alerts, last_updated is present."""
    entry = await _setup(hass, MOCK_ALERTS_NONE)

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert "last_updated" in state.attributes

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
