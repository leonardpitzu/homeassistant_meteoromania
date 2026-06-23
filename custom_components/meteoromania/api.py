import asyncio
import logging
from html import unescape
import re
from xml.etree.ElementTree import ParseError

import aiohttp
from bs4 import BeautifulSoup
from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

_LOGGER = logging.getLogger(__name__)

URL_HTML = "https://www.meteoromania.ro/avertizari/"
URL_XML = "https://www.meteoromania.ro/avertizari-xml.php"
HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://www.meteoromania.ro"

# Numeric ``culoare`` attribute -> colour name.
_COLOR_BY_CULOARE = {"0": "GALBEN", "1": "PORTOCALIU", "2": "ROSU"}

# A warning block starts at this marker line inside an alert's HTML message.
_INTERVAL_MARKER = "interval de valabilitate"

# "COD GALBEN" colour header that precedes a warning block.
_COD_COLOR_RE = re.compile(r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)", re.IGNORECASE)
# Any "COD ..." line — marks the boundary between two warning blocks.
_COD_BOUNDARY_RE = re.compile(r"^COD\s+", re.IGNORECASE)
# "AVERTIZARE/INFORMARE METEOROLOGICĂ" section header.
_METEO_HEADER_RE = re.compile(r"^(AVERTIZARE|INFORMARE)\s+METEOROLOGIC", re.IGNORECASE)


class MeteoRomaniaApiError(Exception):
    """Raised when alert data cannot be retrieved or parsed."""


class MeteoRomaniaApiClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def fetch_alerts(self):
        timeout = aiohttp.ClientTimeout(total=30, connect=10)

        xml_content, html_content = await asyncio.gather(
            self._fetch(URL_XML, timeout),
            self._fetch(URL_HTML, timeout),
            return_exceptions=True,
        )

        # The XML feed is the source of truth; without it there is nothing to do.
        if isinstance(xml_content, BaseException):
            raise MeteoRomaniaApiError(
                f"Could not fetch alerts XML: {xml_content}"
            ) from xml_content

        # The HTML page only supplies the map image URLs — treat it as optional so
        # a hiccup there never hides active weather warnings.
        if isinstance(html_content, BaseException):
            _LOGGER.warning(
                "MeteoRomania HTML page unavailable, alert map images skipped: %s",
                html_content,
            )
            html_content = None

        return self.parse(xml_content, html_content)

    def parse(self, xml_content: bytes, html_content: bytes | None) -> dict:
        """Parse the raw XML/HTML feeds into the alert dict.

        Pure, synchronous and free of any network/HA dependency so it can be
        reused by the standalone ``meteo_alerts_romania_parser.py`` runner.
        """
        try:
            root = ET.fromstring(xml_content)
        except (ParseError, DefusedXmlException) as err:
            raise MeteoRomaniaApiError(f"Could not parse alerts XML: {err}") from err

        alerts = {}
        for i, alert in enumerate(root.findall(".//avertizare"), start=1):
            try:
                alerts[f"alert {i}"] = self._parse_alert(alert)
            except Exception:  # noqa: BLE001 - one malformed alert must not drop the rest
                _LOGGER.exception("Skipping malformed MeteoRomania alert %d", i)

        if html_content is not None:
            try:
                self._map_images(alerts, html_content)
            except Exception:  # noqa: BLE001 - image mapping is best-effort
                _LOGGER.exception("Failed to map MeteoRomania alert images")

        return {
            "has_alerts": bool(alerts),
            "alert_count": len(alerts),
            **alerts,
        }

    # ---------------- helpers ----------------

    async def _fetch(self, url: str, timeout: aiohttp.ClientTimeout) -> bytes:
        """Fetch a URL and return the response body as bytes."""
        async with self._session.get(url, headers=HEADERS, timeout=timeout) as resp:
            resp.raise_for_status()
            return await resp.read()

    def _parse_alert(self, alert) -> dict:
        """Parse a single ``<avertizare>`` element into an alert dict."""
        alert_level_color = _COLOR_BY_CULOARE.get(
            alert.attrib.get("culoare", "").strip(), "NECUNOSCUT"
        )

        result = {
            "type": alert.attrib.get("numeTipMesaj", "").strip(),
            "interval": alert.attrib.get("intervalul", "").strip(),
            "color_code": alert_level_color,
        }

        decoded_html = unescape(alert.attrib.get("mesaj", ""))
        lines, soup = self._extract_lines(decoded_html)
        image_colors = self._detect_image_colors(soup)

        warnings = self._parse_warnings(
            lines=lines,
            image_colors=image_colors,
            fallback_color=alert_level_color,
        )

        for idx, warning in enumerate(warnings, start=1):
            result[f"warning {idx}"] = warning

        return result

    def _map_images(self, alerts: dict, html_content: bytes) -> None:
        """Attach map image URLs from the HTML page to the parsed alerts.

        The page lists maps in the same order as the alerts, but it also holds
        map-less ``alerta_meteo_produse`` blocks (footer/promo). Key off the
        order of the *maps themselves*, not the block position, so a stray
        map-less block can never shift every URL onto the wrong alert.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        map_index = 0
        for block in soup.find_all("div", class_="alerta_meteo_produse"):
            img = block.find("img", src=lambda x: x and "harta.svg.php" in x)
            if not img:
                continue
            map_index += 1
            url = img["src"]
            if url.startswith("/"):
                url = BASE_URL + url
            alert_key = f"alert {map_index}"
            if alert_key in alerts:
                alerts[alert_key]["url"] = url

    def _extract_lines(self, html):
        soup = BeautifulSoup(html, "html.parser")
        for br in soup.find_all("br"):
            br.replace_with("\n")

        text = soup.get_text("\n", strip=True)
        return [ln.strip() for ln in text.split("\n") if ln.strip()], soup

    def _detect_image_colors(self, soup):
        colors = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            if "galben" in src:
                colors.append("GALBEN")
            elif "portocaliu" in src:
                colors.append("PORTOCALIU")
            elif "rosu" in src or "ro%c8%99u" in src:
                colors.append("ROSU")
            else:
                colors.append("NECUNOSCUT")
        return colors

    def _parse_warnings(self, lines, image_colors, fallback_color):
        """Split one alert's text lines into individual warning dicts.

        Each warning starts at an "Interval de valabilitate" line and carries
        its own interval, so a single alert can yield several warnings nested
        within the alert-level interval. A warning's colour comes from a
        preceding "COD <colour>" header if present, otherwise the next map
        image colour, otherwise the alert-level fallback colour.
        """
        warnings = []
        colors = iter(image_colors)
        pending_color = None

        def resolve_color():
            nonlocal pending_color
            if pending_color:
                color, pending_color = pending_color, None
                return color
            image_color = next(colors, "NECUNOSCUT")
            return image_color if image_color != "NECUNOSCUT" else fallback_color

        i = 0
        while i < len(lines):
            line = lines[i]

            if _COD_COLOR_RE.match(line):
                pending_color = line.split()[1].replace("ROȘU", "ROSU")
                i += 1
                continue

            if _INTERVAL_MARKER in line.lower():
                warning = {"color_code": resolve_color()}
                pending_color = None
                warning["interval"] = self._clean_color_prefix(
                    line.split(":", 1)[1].strip() if ":" in line else line
                )

                title, j = self._extract_warning_title(lines, i + 1)
                warning["title"] = self._clean_color_prefix(title)

                phenomena, j = self._extract_warning_phenomena(lines, j)
                if phenomena:
                    warning["phenomena"] = phenomena

                warnings.append(warning)
                i = j
                continue

            i += 1

        return warnings

    def _extract_warning_title(self, lines, j):
        """Return ``(title, next_index)`` from the "Fenomene vizate" line(s)."""
        title = ""
        if j < len(lines) and "fenomen" in lines[j].lower():
            line = lines[j]
            title = line.split(":", 1)[1].strip() if ":" in line else line.strip()
            j += 1
            # A bare "Fenomene vizate:" puts the phenomenon on the next line.
            if (not title and j < len(lines)
                    and "zone " not in lines[j].lower()
                    and "interval" not in lines[j].lower()):
                title = lines[j].strip()
                j += 1
        return title, j

    def _extract_warning_phenomena(self, lines, j):
        """Collect description lines until the next warning/section boundary."""
        desc = []
        while j < len(lines):
            line = lines[j]
            if (_COD_BOUNDARY_RE.match(line)
                    or _INTERVAL_MARKER in line.lower()
                    or line.upper().startswith("MESAJ")
                    or _METEO_HEADER_RE.match(line)):
                break
            desc.append(line)
            j += 1
        return (" ".join(desc) if desc else ""), j

    def _clean_color_prefix(self, text):
        return re.sub(
            r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)\s*",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        )
