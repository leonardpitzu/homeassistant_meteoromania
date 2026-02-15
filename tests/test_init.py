"""Tests for the Meteo Romania Alerts integration setup / teardown."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteo_romania_alerts.const import DOMAIN

MOCK_DATA = {"has_alerts": False, "alert_count": 0}


def _patch_api():
    """Patch the API client so no real HTTP calls are made."""
    return patch(
        "custom_components.meteo_romania_alerts.api.MeteoRomaniaApiClient.fetch_alerts",
        new_callable=AsyncMock,
        return_value=MOCK_DATA,
    )


async def test_setup_entry(hass):
    """Config entry is set up and coordinator stored."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with _patch_api():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]


async def test_unload_entry(hass):
    """Unloading removes coordinator data."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with _patch_api():
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_setup_entry_api_failure(hass):
    """When the API fails on first refresh the entry is not ready."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    with patch(
        "custom_components.meteo_romania_alerts.api.MeteoRomaniaApiClient.fetch_alerts",
        new_callable=AsyncMock,
        side_effect=Exception("timeout"),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Coordinator first-refresh failure → entry not fully loaded
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
