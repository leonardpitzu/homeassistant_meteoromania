import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utcnow

from .const import DOMAIN
from .api import MeteoRomaniaApiClient

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=1)


class MeteoRomaniaDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant):
        session = async_get_clientsession(hass)
        self.api = MeteoRomaniaApiClient(session)
        self.last_updated: str | None = None
        self.county: str = ""

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_method=self._async_update_data,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        try:
            data = await self.api.fetch_alerts()
        except Exception as err:
            raise UpdateFailed(f"Error fetching Meteo Romania alerts: {err}") from err
        self.last_updated = utcnow().isoformat()
        return data
