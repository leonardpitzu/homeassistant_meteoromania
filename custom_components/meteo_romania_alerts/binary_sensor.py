import logging
import re

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType

from .const import (
    DOMAIN,
    COUNTY_KEYWORDS,
    NATIONWIDE_PATTERNS,
    PHENOMENA_MAP,
    MONTH_SHORT,
    COLOR_EMOJI,
)
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
        attrs = {
            **self.coordinator.data,
            "last_updated": self.coordinator.last_updated,
        }
        county = self.coordinator.county
        if county:
            attrs["pixel_summary"] = _build_pixel_summary(self.coordinator.data, county)
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="Meteo Romania Alerts",
            manufacturer="Administrația Națională de Meteorologie",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.meteoromania.ro/"
        )


# ── Pixel summary helpers ─────────────────────────────────────────────


def _warning_relevant(warning: dict, full_text: str, county: str) -> bool:
    """Return True if *warning* is relevant for *county*."""
    text_lower = full_text.lower()

    # Nationwide patterns always match.
    for pat in NATIONWIDE_PATTERNS:
        if pat.lower() in text_lower:
            return True

    # County-specific keywords.
    keywords = COUNTY_KEYWORDS.get(county, [county])
    for kw in keywords:
        if kw.lower() in text_lower:
            return True

    return False


def _extract_phenomena_label(title: str, phenomena: str) -> str:
    """Pick the best concise English label for the warning."""
    combined = f"{title} {phenomena}"
    labels = []
    for pattern, label in PHENOMENA_MAP:
        if re.search(pattern, combined, re.IGNORECASE):
            if label not in labels:
                labels.append(label)
    return ", ".join(labels[:2]) if labels else title[:30]


def _compact_interval(interval: str) -> str:
    """Shorten '22 aprilie, ora 10:00 – 24 aprilie, ora 10:00' for pixel."""
    m = re.match(
        r"(\d+)\s+(\w+),?\s+ora\s+(\d+:\d+)\s*[–\-]\s*(\d+)\s+(\w+),?\s+ora\s+(\d+:\d+)",
        interval,
    )
    if m:
        d1, m1, t1, d2, m2, t2 = m.groups()
        ms1 = MONTH_SHORT.get(m1.lower(), m1[:3])
        ms2 = MONTH_SHORT.get(m2.lower(), m2[:3])
        if m1.lower() == m2.lower():
            if d1 == d2:
                return f"{d1} {ms1} {t1}-{t2}"
            return f"{d1} {ms1} {t1} - {d2} {ms1} {t2}"
        return f"{d1} {ms1} {t1} - {d2} {ms2} {t2}"
    return interval[:30]


def _extract_wind_speed(text: str) -> str:
    """Try to pull a wind speed range from the warning text."""
    m = re.search(r"(\d{2,3})\s*[.…]{2,}\s*(\d{2,3})\s*km/h", text)
    if m:
        return f" {m.group(1)}-{m.group(2)}km/h"
    return ""


def _build_pixel_summary(data: dict, county: str) -> str:
    """Build a short multi-line summary of warnings relevant for *county*."""
    lines: list[str] = []

    for alert_key in sorted(k for k in data if k.startswith("alert ") and isinstance(data[k], dict)):
        alert = data[alert_key]
        for warn_key in sorted(k for k in alert if k.startswith("warning ")):
            w = alert[warn_key]
            title = w.get("title", "")
            phenomena = w.get("phenomena", "")
            full_text = f"{title} {phenomena}"

            if not _warning_relevant(w, full_text, county):
                continue

            color = COLOR_EMOJI.get(w.get("color_code", ""), "⚪")
            label = _extract_phenomena_label(title, phenomena)
            speed = _extract_wind_speed(full_text) if "wind" in label.lower() else ""
            interval = _compact_interval(w.get("interval", ""))

            lines.append(f"{color} {label}{speed} {interval}")

    return "\n".join(lines) if lines else "No alerts for your area"
