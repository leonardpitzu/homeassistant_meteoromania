import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType

from .const import DOMAIN
from .coordinator import MeteoRomaniaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeteoRomaniaAlertSensor(coordinator, entry.entry_id)], update_before_add=True)


class MeteoRomaniaAlertSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Meteo Romania Alert"
    _attr_icon = "mdi:alert"

    def __init__(self, coordinator: MeteoRomaniaDataUpdateCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_alert"

    @property
    def is_on(self):
        return bool(self.coordinator.data and self.coordinator.data.get("has_alerts", False))

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {"last_updated": self.coordinator.last_updated}
        return {
            **self.coordinator.data,
            "last_updated": self.coordinator.last_updated,
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Meteo Romania Alerts",
            manufacturer="Administrația Națională de Meteorologie",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.meteoromania.ro/"
        )
