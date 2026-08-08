from homeassistant.core import HomeAssistant

from .const import CONF_COUNTY, DOMAIN, PLATFORMS
from .coordinator import MeteoRomaniaConfigEntry, MeteoRomaniaDataUpdateCoordinator
from .map import MeteoRomaniaMapView

_MAP_VIEW_KEY = f"{DOMAIN}_map_view"


async def async_setup_entry(
    hass: HomeAssistant, entry: MeteoRomaniaConfigEntry
) -> bool:
    """Set up MeteoRomania from a config entry."""
    coordinator = MeteoRomaniaDataUpdateCoordinator(hass, entry)
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # Register the local map endpoint once (serves recoloured warning maps).
    if getattr(hass, "http", None) and not hass.data.get(_MAP_VIEW_KEY):
        hass.http.register_view(MeteoRomaniaMapView())
        hass.data[_MAP_VIEW_KEY] = True

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: MeteoRomaniaConfigEntry
) -> None:
    """Handle options update — refresh the county on the coordinator."""
    coordinator = entry.runtime_data
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_request_refresh()


async def async_unload_entry(
    hass: HomeAssistant, entry: MeteoRomaniaConfigEntry
) -> bool:
    """Unload MeteoRomania entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
