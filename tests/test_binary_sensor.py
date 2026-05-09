"""Tests for the MeteoRomania binary sensor."""

from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoromania.binary_sensor import (
    _build_local_alerts,
    _format_local_summary,
    _compact_interval,
    _extract_phenomena_label,
    _warning_relevant,
    strip_diacritics,
)
from custom_components.meteoromania.const import DOMAIN

ENTITY_ID = "binary_sensor.meteoromania"

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

    with (
        patch(
            "custom_components.meteoromania.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.meteoromania.api.MeteoRomaniaApiClient.fetch_alerts",
            new_callable=AsyncMock,
            return_value=alerts_data,
        ),
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


# ---------------------------------------------------------------------------
# Local summary unit tests (no HA context needed)
# ---------------------------------------------------------------------------

MOCK_DATA_MULTI = {
    "has_alerts": True,
    "alert_count": 1,
    "alert 1": {
        "type": "Avertizare",
        "interval": "conform textelor",
        "color_code": "PORTOCALIU",
        "warning 1": {
            "color_code": "GALBEN",
            "interval": "22 aprilie, ora 10:00 – 24 aprilie, ora 10:00",
            "title": "precipitații mixte la munte, vreme rece",
            "phenomena": "Zone afectate: Transilvania, în toate regiunile se va resimți vânt puternic.",
        },
        "warning 2": {
            "color_code": "GALBEN",
            "interval": "23 aprilie, ora 09:00 – 23 aprilie, ora 22:00",
            "title": "intensificări ale vântului",
            "phenomena": "Pe parcursul zilei de joi, în Moldova, Transilvania.",
        },
        "warning 3": {
            "color_code": "PORTOCALIU",
            "interval": "23 aprilie, ora 12:00 – 23 aprilie, ora 20:00",
            "title": "intensificări puternice ale vântului",
            "phenomena": "în județele Botoșani, Iași, zona joasă Suceava, rafale de 70...90 km/h.",
        },
    },
}


def test_compact_interval_same_day():
    assert _compact_interval("23 aprilie, ora 09:00 – 23 aprilie, ora 22:00") == "23/4 9h-22h"


def test_compact_interval_multi_day():
    assert _compact_interval("22 aprilie, ora 10:00 – 24 aprilie, ora 10:00") == "22/4 10h-24/4 10h"


def test_compact_interval_bare_hours():
    assert _compact_interval("09 mai, ora 22 – 10 mai, ora 10") == "9/5 22h-10/5 10h"


def test_compact_interval_bare_hours_same_day():
    assert _compact_interval("09 mai, ora 10 – 09 mai, ora 22") == "9/5 10h-22h"


def test_compact_interval_fallback():
    assert _compact_interval("conform textelor") == "conform textelor"


def test_extract_phenomena_wind():
    label = _extract_phenomena_label("intensificări ale vântului", "rafale de 50 km/h")
    assert "Strong wind" in label


def test_extract_phenomena_heavy_rain():
    label = _extract_phenomena_label("cantități de apă însemnate", "averse ce vor acumula")
    assert "Heavy rain" in label


def test_extract_phenomena_snow():
    label = _extract_phenomena_label("ninsori abundente", "se va depune zăpadă")
    assert "Snow" in label


def test_extract_phenomena_cold():
    label = _extract_phenomena_label("vreme rece, brumă", "temperaturi scăzute")
    assert "Cold" in label or "Frost" in label


def test_warning_relevant_direct_county():
    w = {"color_code": "GALBEN"}
    assert _warning_relevant(w, "Vânt în județul Brașov", "Brașov") is True


def test_warning_relevant_region():
    w = {"color_code": "GALBEN"}
    assert _warning_relevant(w, "precipitații în Transilvania", "Brașov") is True


def test_warning_relevant_nationwide():
    w = {"color_code": "GALBEN"}
    assert _warning_relevant(w, "în toate regiunile", "Constanța") is True


def test_warning_not_relevant():
    w = {"color_code": "GALBEN"}
    assert _warning_relevant(w, "în județele Botoșani, Iași", "Brașov") is False


def test_local_alerts_brasov():
    alerts = _build_local_alerts(MOCK_DATA_MULTI, "Brașov")
    # Warnings 1 & 2 match (Transilvania), warning 3 does not (Botoșani/Iași only)
    assert len(alerts) == 2
    assert alerts[0]["color"] == "GALBEN"
    assert alerts[0]["icon"] == "alert_yellow"
    assert "r" in alerts[0] and "g" in alerts[0] and "b" in alerts[0]


def test_local_alerts_botosani():
    alerts = _build_local_alerts(MOCK_DATA_MULTI, "Botoșani")
    # All 3 match, most severe first (PORTOCALIU before GALBEN)
    assert len(alerts) == 3
    assert alerts[0]["color"] == "PORTOCALIU"
    assert alerts[0]["icon"] == "alert_orange"


def test_local_alerts_no_match():
    alerts = _build_local_alerts(MOCK_DATA_MULTI, "Constanța")
    # Warning 1 (toate regiunile) matches, warning 2 and 3 don't mention Dobrogea/Constanța
    assert len(alerts) == 1


def test_local_alerts_no_alerts():
    data = {"has_alerts": False, "alert_count": 0}
    alerts = _build_local_alerts(data, "Brașov")
    assert alerts == []


def test_format_local_summary_from_alerts():
    alerts = _build_local_alerts(MOCK_DATA_MULTI, "Brașov")
    summary = _format_local_summary(alerts)
    lines = summary.strip().split("\n")
    assert len(lines) == 2
    assert "🟡" in lines[0]


def test_format_local_summary_empty():
    assert _format_local_summary([]) == "No alerts for your area"


def test_strip_diacritics():
    assert strip_diacritics("ăâîșț") == "aaist"
    assert strip_diacritics("ĂÂÎȘȚ") == "AAIST"
    # Legacy cedilla variants (ş ţ)
    assert strip_diacritics("şţ") == "st"
    assert strip_diacritics("Brașov") == "Brasov"
    assert strip_diacritics("Hello world") == "Hello world"
    assert strip_diacritics("") == ""


async def test_local_alerts_in_attributes(hass):
    """When county is configured, both local_alerts and local_summary appear."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"county": "Brașov"})
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.meteoromania.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.meteoromania.api.MeteoRomaniaApiClient.fetch_alerts",
            new_callable=AsyncMock,
            return_value=MOCK_DATA_MULTI,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert "local_alerts" in state.attributes
    assert "local_summary" in state.attributes
    assert isinstance(state.attributes["local_alerts"], list)

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
