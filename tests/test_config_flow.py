"""Tests for the MeteoRomania config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.meteoromania.const import DOMAIN


async def test_user_step_shows_form(hass):
    """First step presents a confirmation form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_creates_entry(hass):
    """Submitting the form creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    with (
        patch(
            "custom_components.meteoromania.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.meteoromania.api.MeteoRomaniaApiClient.fetch_alerts",
            new_callable=AsyncMock,
            return_value={"has_alerts": False, "alert_count": 0},
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "MeteoRomania"
    assert result["data"] == {}


async def test_single_instance_only(hass):
    """Second instance is rejected."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
