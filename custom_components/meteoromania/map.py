"""Locally-generated ANM warning maps.

ANM's per-alert map (``harta.svg.php``) is a ~4.7MB SVG whose geometry — the
country outline, county borders and mountain/relief zones — never changes; only
the per-county / per-relief colour classes differ between alerts. So instead of
having the browser fetch that 4.7MB SVG from meteoromania.ro on every dashboard
render, we ship the geometry once as a neutralised template
(``map_template.svg.gz``) and recolour it on demand from the authoritative codes
the feed already gives us:

- ``<judet cod="XX" culoare="N">``  -> county ``XX`` fill  (``class="judet codN"``)
- ``<zona cod="XX_munte_1" culoare="N">`` -> relief patch fill (``class="munte codN ..."``)

The recoloured SVG is served from a small local endpoint, so the existing
dashboard cards keep working unchanged while nothing hits the remote per render.
"""

import gzip
import logging
import re
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN, MAP_URL_BASE

_LOGGER = logging.getLogger(__name__)

_TEMPLATE_FILE = Path(__file__).parent / "map_template.svg.gz"
_template_cache: str | None = None

# Matches a county/relief path by its identifying data attribute, capturing the
# following ``class`` value so a ``codN`` token can be appended. Relies on the
# feed's consistent attribute order (``data-*`` before ``class``) within a tag.
_JUDET_RE = re.compile(r'data-judet="(?P<key>[A-Z]{1,2})"[^>]*?class="(?P<cls>judet[^"]*)"')
_ZONA_RE = re.compile(r'data-munte="(?P<key>[^"]+)"[^>]*?class="(?P<cls>[^"]*)"')


def _template() -> str:
    """Load and cache the neutralised master SVG template."""
    global _template_cache
    if _template_cache is None:
        with gzip.open(_TEMPLATE_FILE, "rt", encoding="utf-8") as handle:
            _template_cache = handle.read()
    return _template_cache


def _apply(svg: str, pattern: re.Pattern, codes: dict[str, int]) -> str:
    """Append ``codN`` to the class of every path whose key has ``culoare > 0``."""

    def repl(match: re.Match) -> str:
        cod = codes.get(match.group("key"), 0)
        if cod <= 0:
            return match.group(0)
        cls = match.group("cls")
        return match.group(0).replace(f'class="{cls}"', f'class="{cls} cod{cod}"')

    return pattern.sub(repl, svg)


def render_map(county_codes: dict[str, int], zone_codes: dict[str, int]) -> bytes:
    """Recolour the master template for one alert and return SVG bytes."""
    svg = _template()
    svg = _apply(svg, _JUDET_RE, county_codes or {})
    svg = _apply(svg, _ZONA_RE, zone_codes or {})
    return svg.encode("utf-8")


def _find_alert(hass, id_avertizare: str) -> dict | None:
    """Return the alert dict carrying *id_avertizare* across all coordinators."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        data = getattr(coordinator, "data", None) or {}
        for key, alert in data.items():
            if (
                key.startswith("alert ")
                and isinstance(alert, dict)
                and alert.get("id_avertizare") == id_avertizare
            ):
                return alert
    return None


class MeteoRomaniaMapView(HomeAssistantView):
    """Serve the locally-recoloured ANM warning map for an alert.

    Unauthenticated so the map can be loaded as a plain ``<img>`` by dashboard
    cards; it only ever exposes public ANM weather-warning colouring.
    """

    url = MAP_URL_BASE + "/{id_avertizare}"
    name = "api:meteoromania:map"
    requires_auth = False

    async def get(self, request: web.Request, id_avertizare: str) -> web.Response:
        hass = request.app["hass"]
        alert = _find_alert(hass, id_avertizare)
        if alert is None:
            return web.Response(status=404, text="Unknown alert")
        body = render_map(alert.get("county_codes", {}), alert.get("zone_codes", {}))
        return web.Response(
            body=body,
            content_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )
