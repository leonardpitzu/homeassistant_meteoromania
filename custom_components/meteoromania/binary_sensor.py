import logging
import re

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import MATCH_ALL
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType

from .const import (
    DOMAIN,
    COUNTY_KEYWORDS,
    COUNTY_CODE,
    COD_COLOR,
    NATIONWIDE_PATTERNS,
    UNLOCALIZED_ZONE_MARKERS,
    PHENOMENA_MAP,
    MONTH_NUM,
    COLOR_EMOJI,
    COLOR_RGB,
)
from .coordinator import MeteoRomaniaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MeteoRomaniaSensor(coordinator, entry.entry_id)], update_before_add=True)


class MeteoRomaniaSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:alert"
    # The full nationwide alert tree (plus per-county/relief code dicts and the
    # signed map URLs) is large and only useful live for the dashboard card;
    # keep it out of the recorder so history stores just the on/off state.
    _unrecorded_attributes = frozenset({MATCH_ALL})

    def __init__(self, coordinator: MeteoRomaniaDataUpdateCoordinator, entry_id: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_alert"
        # Cache the (regex-heavy) attribute build for one coordinator update —
        # HA reads extra_state_attributes several times per update.
        self._attrs_cache_key: object = object()
        self._attrs_cache: dict = {}

    @property
    def is_on(self):
        return bool(self.coordinator.data and self.coordinator.data.get("has_alerts", False))

    @property
    def extra_state_attributes(self):
        cache_key = (self.coordinator.last_updated, self.coordinator.county)
        if cache_key == self._attrs_cache_key:
            return self._attrs_cache

        data = self.coordinator.data
        if not data:
            attrs = {"last_updated": self.coordinator.last_updated}
        else:
            attrs = {
                **data,
                "last_updated": self.coordinator.last_updated,
            }
            county = self.coordinator.county
            if county:
                alerts_list = _build_local_alerts(data, county)
                attrs["local_alerts"] = alerts_list
                attrs["local_summary"] = _format_local_summary(alerts_list)

        self._attrs_cache_key = cache_key
        self._attrs_cache = attrs
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name="MeteoRomania",
            manufacturer="Administrația Națională de Meteorologie",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.meteoromania.ro/"
        )


# ── Diacritics transliteration ─────────────────────────────────────────

_RO_DIACRITICS = str.maketrans(
    "ăâîșțĂÂÎȘȚşţŞŢ",
    "aaistAAISTstST",
)


def strip_diacritics(text: str) -> str:
    """Replace Romanian diacritical characters with ASCII equivalents."""
    return text.translate(_RO_DIACRITICS)


def _truncate_words(text: str, limit: int = 46) -> str:
    """Truncate *text* to at most *limit* chars without cutting a word in half."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0]
    return (cut or text[:limit]).rstrip(' ,;-')


# ── Local summary helpers ─────────────────────────────────────────────


def _warning_relevant(full_text: str, county: str) -> bool:
    """Return True if a warning's *full_text* is relevant for *county*."""
    text_lower = full_text.lower()

    # Nationwide patterns always match.
    for pat in NATIONWIDE_PATTERNS:
        if pat.lower() in text_lower:
            return True

    # Warnings whose affected zones are given only "conform textului si hartii"
    # carry no explicit region list — include them for every county.
    for marker in UNLOCALIZED_ZONE_MARKERS:
        if marker.lower() in text_lower:
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
    return ", ".join(labels[:2]) if labels else _truncate_words(strip_diacritics(title))


def _short_time(t: str) -> str:
    """'10:00' -> '10h', '09:00' -> '9h', '10:30' -> '10:30', '22' -> '22h'."""
    if ":" not in t:
        return f"{int(t)}h"
    if t.endswith(":00"):
        return f"{int(t.split(':')[0])}h"
    return t


def _compact_interval(interval: str) -> str:
    """Shorten '22 aprilie, ora 10:00 – 24 aprilie, ora 10:00' to '22/4 10h-24/4 10h'."""
    m = re.match(
        r"(\d+)\s+(\w+),?\s+ora\s+(\d+(?::\d+)?)\s*[–\-]\s*(\d+)\s+(\w+),?\s+ora\s+(\d+(?::\d+)?)",
        interval,
    )
    if m:
        d1, m1, t1, d2, m2, t2 = m.groups()
        mn1 = MONTH_NUM.get(m1.lower(), m1[:2])
        mn2 = MONTH_NUM.get(m2.lower(), m2[:2])
        st1 = _short_time(t1)
        st2 = _short_time(t2)
        if m1.lower() == m2.lower() and d1 == d2:
            return f"{int(d1)}/{mn1} {st1}-{st2}"
        return f"{int(d1)}/{mn1} {st1}-{int(d2)}/{mn2} {st2}"
    return _truncate_words(strip_diacritics(interval))


def _extract_wind_speed(text: str) -> str:
    """Try to pull a wind speed range from the warning text."""
    m = re.search(r"(\d{2,3})\s*[.…]{2,}\s*(\d{2,3})\s*km/h", text)
    if m:
        return f" {m.group(1)}-{m.group(2)}km/h"
    return ""


_SEVERITY_ORDER = {"ROSU": 0, "PORTOCALIU": 1, "GALBEN": 2, "NECUNOSCUT": 3}

_COLOR_ICON = {
    "ROSU": "alert_red",
    "PORTOCALIU": "alert_orange",
    "GALBEN": "alert_yellow",
    "NECUNOSCUT": "alert_yellow",
}


def _build_local_alerts(data: dict, county: str) -> list[dict]:
    """Build a list of warning dicts relevant for *county*.

    Each dict contains: icon, text, color, r, g, b. Warnings are sorted by
    severity (red > orange > yellow).

    Relevance and severity come from ANM's own per-county codes
    (``county_codes`` on each alert, from the feed's ``<judet>`` elements)
    whenever they are available — that is authoritative and precise to the
    county. Only when the feed omits them does it fall back to the prose
    keyword heuristic.
    """
    county_code = COUNTY_CODE.get(county)
    pairs: list[tuple[str, dict]] = []
    alert_keys = sorted(
        (k for k in data if k.startswith("alert ") and isinstance(data[k], dict)),
        key=_key_index,
    )
    for alert_key in alert_keys:
        alert = data[alert_key]
        warnings = _iter_warnings(alert)
        alert_pairs = _alert_map_pairs(alert, warnings, county_code) if county_code else None
        if alert_pairs is None:
            # No authoritative codes for this alert — degrade to prose matching.
            alert_pairs = _alert_prose_pairs(warnings, county)
        pairs.extend(alert_pairs)

    # Most severe first.
    pairs.sort(key=lambda p: _SEVERITY_ORDER.get(p[0], 3))

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for color_code, w in pairs:
        title = w.get("title", "")
        phenomena = w.get("phenomena", "")
        full_text = f"{title} {phenomena}"

        label = _extract_phenomena_label(title, phenomena)
        speed = _extract_wind_speed(full_text) if "wind" in label.lower() else ""
        interval = _compact_interval(w.get("interval", ""))

        rgb = COLOR_RGB.get(color_code, COLOR_RGB["NECUNOSCUT"])
        text = f"{label}{speed} {interval}"
        key = (color_code, text)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "icon": _COLOR_ICON.get(color_code, "alert_yellow"),
            "text": text,
            "color": color_code,
            **rgb,
        })

    return results


def _key_index(key: str) -> int:
    """Trailing integer of a ``"<name> <n>"`` key, for natural ordering."""
    try:
        return int(key.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0


def _iter_warnings(alert: dict) -> list[dict]:
    """Return an alert's warning dicts in document order."""
    return [
        alert[k]
        for k in sorted(
            (k for k in alert if k.startswith("warning ")), key=_key_index
        )
    ]


def _alert_map_pairs(
    alert: dict, warnings: list[dict], county_code: str
) -> list[tuple[str, dict]] | None:
    """Relevance/severity for one alert from ANM's per-county codes.

    Returns ``(display_color, warning)`` pairs for the county (possibly empty if
    the county is not affected by this alert), or ``None`` if this alert carries
    no ``county_codes`` so the caller can fall back to prose matching for it.
    """
    alert_codes = alert.get("county_codes")
    if not isinstance(alert_codes, dict):
        return None

    cod = alert_codes.get(county_code, 0)
    if cod == 0:
        return []
    color = COD_COLOR[cod]
    # The per-county code only gives the county's severity; use the warning(s)
    # of that colour for the display text. If none match (rare — the county's
    # code came from a block we can't colour-key), fall back to the single
    # most-severe warning for the text while keeping the authoritative colour.
    matches = [w for w in warnings if w.get("color_code") == color]
    if matches:
        return [(color, w) for w in matches]
    if warnings:
        best = min(
            warnings,
            key=lambda w: _SEVERITY_ORDER.get(w.get("color_code", ""), 3),
        )
        return [(color, best)]
    return []


def _alert_prose_pairs(warnings: list[dict], county: str) -> list[tuple[str, dict]]:
    """Fallback relevance for one alert from the prose keyword heuristic."""
    out: list[tuple[str, dict]] = []
    for w in warnings:
        title = w.get("title", "")
        phenomena = w.get("phenomena", "")
        if _warning_relevant(f"{title} {phenomena}", county):
            out.append((w.get("color_code", "NECUNOSCUT"), w))
    return out


def _format_local_summary(alerts: list[dict]) -> str:
    """Format a local_alerts list into a human-readable multi-line string."""
    if not alerts:
        return "No alerts for your area"
    lines = []
    for a in alerts:
        emoji = COLOR_EMOJI.get(a.get("color", ""), "⚪")
        lines.append(f"{emoji} {a['text']}")
    return "\n".join(lines)
