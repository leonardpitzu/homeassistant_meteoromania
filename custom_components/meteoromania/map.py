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
from datetime import timedelta
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MAP_URL_BASE

_LOGGER = logging.getLogger(__name__)

# Signed map URLs are refreshed every poll; give them a comfortable margin over
# the scan interval so a link embedded in the dashboard never expires mid-cycle.
MAP_URL_EXPIRY = timedelta(hours=3)

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


def apply_map_urls(hass: HomeAssistant, data: dict) -> None:
    """Attach an HA-signed local map URL to each alert in *data* (in place).

    The URL points at :class:`MeteoRomaniaMapView` (``MAP_URL_BASE/<index>``) and
    is signed so a plain dashboard ``<img>`` can load it without a session while
    the endpoint itself stays authenticated. Best-effort: if signing is
    unavailable (e.g. the http component is not ready) the alert simply gets no
    map URL.
    """
    for key, alert in data.items():
        if not (key.startswith("alert ") and isinstance(alert, dict)):
            continue
        index = key.split(" ", 1)[1]
        try:
            alert["url"] = async_sign_path(
                hass, f"{MAP_URL_BASE}/{index}", MAP_URL_EXPIRY
            )
        except Exception as err:  # noqa: BLE001 - signing is a best-effort UI aid
            _LOGGER.debug("Could not sign map URL for %s: %s", key, err)


def _find_alert(hass: HomeAssistant, index: str) -> dict | None:
    """Return the ``alert <index>`` dict from any MeteoRomania coordinator."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        data = getattr(coordinator, "data", None) or {}
        alert = data.get(f"alert {index}")
        if isinstance(alert, dict):
            return alert
    return None


class MeteoRomaniaMapView(HomeAssistantView):
    """Serve the locally-recoloured ANM warning map for an alert.

    Authenticated (a valid session or an HA-signed URL is required); the map
    URLs handed to the dashboard by :func:`apply_map_urls` are signed so plain
    ``<img>`` tags can load them.
    """

    url = MAP_URL_BASE + "/{index}"
    name = "api:meteoromania:map"

    async def get(self, request: web.Request, index: str) -> web.Response:
        hass = request.app["hass"]
        alert = _find_alert(hass, index)
        if alert is None:
            return web.Response(status=404, text="Unknown alert")
        body = render_map(alert.get("county_codes", {}), alert.get("zone_codes", {}))
        return web.Response(
            body=body,
            content_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )
