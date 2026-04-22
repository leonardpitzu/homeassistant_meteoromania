from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_COUNTY
from .coordinator import MeteoRomaniaDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meteo Romania Alerts from a config entry."""
    coordinator = MeteoRomaniaDataUpdateCoordinator(hass)
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])
    
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — refresh the county on the coordinator."""
    coordinator: MeteoRomaniaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.county = entry.options.get(CONF_COUNTY, "")
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Meteo Romania Alerts entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    
    return unload_ok
