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

import base64
import gzip
import hashlib
import json
import logging
import re
import time
from datetime import timedelta
from pathlib import Path

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MAP_URL_BASE

_LOGGER = logging.getLogger(__name__)

# Signed map URLs are minted with a generous lifetime and reused for as long as
# they are valid, so an unchanged colouring keeps the same URL across polls.
MAP_URL_EXPIRY = timedelta(hours=25)
# Re-sign once a reused URL drops within this margin of expiring.
_MAP_URL_REFRESH_MARGIN = 3 * 3600  # 3 hours
# The URL names the colouring it renders, so what it serves can never change.
_MAP_CACHE_SECONDS = 86400

_TEMPLATE_FILE = Path(__file__).parent / "map_template.svg.gz"
_template_cache: str | None = None

# Signed URLs already minted, keyed by colouring etag. Pruned each poll to the
# colourings still in play, so it cannot grow without bound.
_URL_CACHE_KEY = f"{DOMAIN}_map_urls"
_template_cache: str | None = None

# etag -> gzip-compressed SVG bytes. Keyed on the colour codes, so identical
# maps are rendered+compressed once and reused for every request/alert.
_render_cache: dict[str, bytes] = {}
_RENDER_CACHE_MAX = 64

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
    """Recolour the master template for one alert and return raw SVG bytes."""
    svg = _template()
    svg = _apply(svg, _JUDET_RE, county_codes or {})
    svg = _apply(svg, _ZONA_RE, zone_codes or {})
    return svg.encode("utf-8")


def _etag(county_codes: dict[str, int], zone_codes: dict[str, int]) -> str:
    """Stable content hash for a colouring — identical codes give one etag."""
    payload = json.dumps([county_codes or {}, zone_codes or {}], sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()[:16]  # noqa: S324 - not security


def render_map_gz(
    county_codes: dict[str, int], zone_codes: dict[str, int]
) -> tuple[str, bytes]:
    """Return ``(etag, gzip_bytes)`` for a colouring, rendering+caching on miss.

    The recoloured 4.7MB SVG compresses to ~120KB, so serving it gzipped (and
    caching the result keyed on the colour codes) turns each map request from a
    multi-megabyte re-render into a cache hit + tiny transfer.
    """
    etag = _etag(county_codes, zone_codes)
    gz = _render_cache.get(etag)
    if gz is None:
        gz = gzip.compress(render_map(county_codes, zone_codes), 6)
        if len(_render_cache) >= _RENDER_CACHE_MAX:
            _render_cache.clear()
        _render_cache[etag] = gz
    return etag, gz


def _url_fresh(url: str) -> bool:
    """True if a previously signed map URL is not close to expiring."""
    try:
        token = url.split("authSig=", 1)[1].split("&", 1)[0]
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0)
    except (IndexError, ValueError, json.JSONDecodeError):
        return False
    return exp - time.time() > _MAP_URL_REFRESH_MARGIN


def apply_map_urls(hass: HomeAssistant, data: dict) -> None:
    """Attach an HA-signed local map URL to each alert in *data* (in place).

    The URL names the colouring it renders (``MAP_URL_BASE/<etag>``) rather than
    the alert's position in this poll, so it cannot come to mean a different
    alert when ANM reorders the feed — which, combined with browser caching,
    used to be able to show one alert's map beside another's text. Because the
    content behind a URL is then fixed, a still-valid URL is reused for as long
    as it lasts and the response is cacheable for a day.

    Signing is best-effort: if it is unavailable (e.g. the http component is not
    ready) the alert simply gets no URL.

    ANM publishes a single map per alert, painted with every warning's colours
    at once; the same URL is repeated on each warning so a dashboard can show a
    map beside every one of them.
    """
    cache: dict[str, str] = hass.data.setdefault(_URL_CACHE_KEY, {})
    live: set[str] = set()

    for key, alert in data.items():
        if not (key.startswith("alert ") and isinstance(alert, dict)):
            continue
        etag = _etag(alert.get("county_codes", {}), alert.get("zone_codes", {}))
        url = cache.get(etag)
        if url is None or not _url_fresh(url):
            try:
                url = async_sign_path(
                    hass, f"{MAP_URL_BASE}/{etag}", MAP_URL_EXPIRY
                )
            except Exception as err:  # noqa: BLE001 - signing is a best-effort UI aid
                _LOGGER.debug("Could not sign map URL for %s: %s", key, err)
                continue
            cache[etag] = url
        live.add(etag)
        alert["url"] = url
        for warning_key, warning in alert.items():
            if warning_key.startswith("warning ") and isinstance(warning, dict):
                warning["url"] = url

    for stale in cache.keys() - live:
        del cache[stale]


def _find_codes(hass: HomeAssistant, etag: str) -> tuple[dict, dict] | None:
    """Return the ``(county_codes, zone_codes)`` an *etag* was minted from."""
    for coordinator in hass.data.get(DOMAIN, {}).values():
        data = getattr(coordinator, "data", None) or {}
        for key, alert in data.items():
            if not (key.startswith("alert ") and isinstance(alert, dict)):
                continue
            county = alert.get("county_codes", {})
            zone = alert.get("zone_codes", {})
            if _etag(county, zone) == etag:
                return county, zone
    return None


class MeteoRomaniaMapView(HomeAssistantView):
    """Serve the locally-recoloured ANM warning map for a colouring.

    Authenticated (a valid session or an HA-signed URL is required); the map
    URLs handed to the dashboard by :func:`apply_map_urls` are signed so plain
    ``<img>`` tags can load them. Responses are gzipped and, because the URL
    names the colouring it renders, safely cacheable.
    """

    url = MAP_URL_BASE + "/{etag}"
    name = "api:meteoromania:map"

    async def get(self, request: web.Request, etag: str) -> web.Response:
        hass = request.app["hass"]
        codes = _find_codes(hass, etag)
        if codes is None:
            return web.Response(status=404, text="Unknown map")
        county_codes, zone_codes = codes

        # Off-load to the executor: the first render reads the gzipped template
        # from disk and every miss recolours + gzips a ~4.7MB SVG — both are
        # blocking/CPU-heavy and must not run in the event loop.
        rendered_etag, gz = await hass.async_add_executor_job(
            render_map_gz, county_codes, zone_codes
        )
        quoted_etag = f'"{rendered_etag}"'
        cache_headers = {
            "ETag": quoted_etag,
            "Cache-Control": f"private, max-age={_MAP_CACHE_SECONDS}, immutable",
        }
        if request.headers.get("If-None-Match") == quoted_etag:
            return web.Response(status=304, headers=cache_headers)

        if "gzip" in request.headers.get("Accept-Encoding", ""):
            return web.Response(
                body=gz,
                content_type="image/svg+xml",
                headers={**cache_headers, "Content-Encoding": "gzip"},
            )
        return web.Response(
            body=gzip.decompress(gz),
            content_type="image/svg+xml",
            headers=cache_headers,
        )
