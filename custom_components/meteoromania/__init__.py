from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_COUNTY, PLATFORMS
from .coordinator import MeteoRomaniaDataUpdateCoordinator
from .map import MeteoRomaniaMapView


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeteoRomania from a config entry."""
    coordinator = MeteoRomaniaDataUpdateCoordinator(hass, entry)
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Register the local map endpoint once (serves recoloured warning maps).
    if getattr(hass, "http", None) and not hass.data.get(f"{DOMAIN}_map_view"):
        hass.http.register_view(MeteoRomaniaMapView())
        hass.data[f"{DOMAIN}_map_view"] = True

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — refresh the county on the coordinator."""
    coordinator: MeteoRomaniaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload MeteoRomania entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
