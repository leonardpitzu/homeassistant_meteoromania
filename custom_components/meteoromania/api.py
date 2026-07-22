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

# Warning colour severity, most severe first, for rolling warnings up to their alert.
_COLOR_SEVERITY = {"ROSU": 3, "PORTOCALIU": 2, "GALBEN": 1, "NECUNOSCUT": 0}

# A warning block starts at this marker line inside an alert's HTML message.
_INTERVAL_MARKER = "interval de valabilitate"

# "COD GALBEN" colour header that precedes a warning block.
_COD_COLOR_RE = re.compile(r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)", re.IGNORECASE)
# Any "COD ..." line — marks the boundary between two warning blocks.
_COD_BOUNDARY_RE = re.compile(r"^COD\s+", re.IGNORECASE)
# Message-type headers that delimit blocks inside an element's HTML message.
# An INFORMARE opens an alert; ATENȚIONARE/AVERTIZARE blocks are its warnings.
_INFORMARE_HEADER_RE = re.compile(r"^INFORMARE\s+METEOROLOGIC", re.IGNORECASE)
_ATENTIONARE_HEADER_RE = re.compile(
    r"^(ATEN[ȚT]IONARE|AVERTIZARE)\s+METEOROLOGIC", re.IGNORECASE
)


class MeteoRomaniaApiError(Exception):
    """Raised when alert data cannot be retrieved or parsed."""


# ANM's per-alert map SVG colours each county authoritatively. The base county
# path is ``<path data-judet="XX" ... class="judet codN">`` (cod0..cod3); relief
# overlays are separate ``munte``/``alt###``/``litoral`` paths we deliberately
# ignore so the value reflects the county lowland (the populated area).
_SVG_PATH_RE = re.compile(r"<path\b[^>]*>")
_SVG_JUDET_RE = re.compile(r'data-judet="([A-Z]{1,2})"')
_SVG_CLASS_RE = re.compile(r'class="([^"]*)"')


def parse_county_codes(svg: bytes) -> dict[str, int]:
    """Extract each county's base *județ* warning code from an ANM map SVG.

    Returns ``{judet_code: cod}`` with cod 0 (none/green), 1 (galben),
    2 (portocaliu) or 3 (roșu), read from the base ``class="judet codN"`` path
    of every county. This is ANM's own per-county colouring, so it is exact and
    replaces the prose keyword heuristic for deciding local relevance/severity.
    """
    text = svg.decode("utf-8", "replace")
    codes: dict[str, int] = {}
    for tag in _SVG_PATH_RE.findall(text):
        cls = _SVG_CLASS_RE.search(tag)
        if not cls:
            continue
        tokens = cls.group(1).split()
        if "judet" not in tokens:
            continue
        cod = next(
            (int(t[3:]) for t in tokens if t.startswith("cod") and t[3:].isdigit()),
            None,
        )
        if cod is None:
            continue
        jm = _SVG_JUDET_RE.search(tag)
        if jm:
            codes[jm.group(1)] = cod
    return codes


def _most_severe_color(warnings: list[dict]) -> str:
    """Return the most severe ``color_code`` among *warnings*.

    An ATENȚIONARE alert has no COD colour of its own; the public page shows it
    with the colour of its highest-severity warning (e.g. "COD GALBEN"). Roll
    the warnings up the same way so the alert-level ``color_code`` matches.
    """
    return max(
        (w.get("color_code", "NECUNOSCUT") for w in warnings),
        key=lambda c: _COLOR_SEVERITY.get(c, 0),
        default="NECUNOSCUT",
    )


class MeteoRomaniaApiClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        # url -> {judet_code: cod} cache; a given ``id_avertizare`` map is
        # immutable, so this is reused across polls and pruned to live URLs.
        self._svg_codes_cache: dict[str, dict[str, int]] = {}

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

        result = self.parse(xml_content, html_content)
        await self._annotate_county_codes(result, timeout)
        return result

    async def _annotate_county_codes(self, result: dict, timeout) -> None:
        """Attach ANM's authoritative per-county codes to each mapped target.

        Every alert/warning that carries a ``harta.svg.php`` map URL gets a
        ``county_codes`` dict (``{judet_code: cod}``) parsed from that map.
        Best-effort: any fetch/parse failure simply leaves ``county_codes``
        unset, and the sensor falls back to prose keyword matching.
        """
        targets: list[tuple[dict, str]] = []
        for key, alert in result.items():
            if not (key.startswith("alert ") and isinstance(alert, dict)):
                continue
            candidates = [alert] + [
                alert[k] for k in alert if k.startswith("warning ")
            ]
            for target in candidates:
                url = target.get("url")
                if url and "harta.svg.php" in url:
                    targets.append((target, url))

        if not targets:
            self._svg_codes_cache = {}
            return

        fresh: dict[str, dict[str, int]] = {}

        async def resolve(url: str) -> None:
            cached = self._svg_codes_cache.get(url)
            if cached is not None:
                fresh[url] = cached
                return
            try:
                raw = await self._fetch(url, timeout)
                fresh[url] = parse_county_codes(raw)
            except Exception as err:  # noqa: BLE001 - map codes are best-effort
                _LOGGER.warning("MeteoRomania map SVG unavailable (%s): %s", url, err)

        await asyncio.gather(*(resolve(url) for url in {u for _, u in targets}))
        # Prune the cache to only the maps still referenced this cycle.
        self._svg_codes_cache = fresh

        for target, url in targets:
            codes = fresh.get(url)
            if codes is not None:
                target["county_codes"] = codes

    def parse(self, xml_content: bytes, html_content: bytes | None) -> dict:
        """Parse the raw XML/HTML feeds into the alert dict.

        Pure, synchronous and free of any network/HA dependency so it can be
        reused by the standalone ``meteo_alerts_romania_parser.py`` runner.

        Each ``<avertizare>`` element is one alert, exactly mirroring the
        public page (one map per element). Inside an element the message text
        carries the structure: an ``INFORMARE`` block is the alert's own
        header and the ``ATENȚIONARE`` (COD) blocks that follow are its
        warnings. Elements without an INFORMARE are plain warning alerts.
        """
        try:
            root = ET.fromstring(xml_content)
        except (ParseError, DefusedXmlException) as err:
            raise MeteoRomaniaApiError(f"Could not parse alerts XML: {err}") from err

        alerts = {}
        alert_idx = 0
        for i, element in enumerate(root.findall(".//avertizare"), start=1):
            try:
                fallback_color = _COLOR_BY_CULOARE.get(
                    element.attrib.get("culoare", "").strip(), "NECUNOSCUT"
                )
                lines, soup = self._extract_lines(
                    unescape(element.attrib.get("mesaj", ""))
                )
                blocks = self._parse_blocks(
                    lines, self._detect_image_colors(soup), fallback_color
                )
            except Exception:  # noqa: BLE001 - one malformed element must not drop the rest
                _LOGGER.exception("Skipping malformed MeteoRomania avertizare %d", i)
                continue

            if not blocks:
                continue
            alert_idx += 1
            alerts[f"alert {alert_idx}"] = self._build_alert(blocks)

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

    def _parse_blocks(self, lines, image_colors, fallback_color):
        """Parse one element's HTML lines into a flat list of message blocks.

        Each block is one "Interval de valabilitate" section tagged with its
        ``kind`` ("informare" or "atentionare") from the most recent message
        header. Colour comes from a preceding "COD <colour>" header, else the
        next map image colour, else the element's ``culoare``; informare
        blocks carry no COD colour.
        """
        blocks = []
        colors = iter(image_colors)
        pending_color = None
        kind = "atentionare"

        def block_color():
            nonlocal pending_color
            if pending_color:
                color, pending_color = pending_color, None
                return color
            if kind == "informare":
                return "NECUNOSCUT"
            image_color = next(colors, "NECUNOSCUT")
            return image_color if image_color != "NECUNOSCUT" else fallback_color

        i = 0
        while i < len(lines):
            line = lines[i]

            if _INFORMARE_HEADER_RE.match(line):
                kind = "informare"
                i += 1
                continue
            if _ATENTIONARE_HEADER_RE.match(line):
                kind = "atentionare"
                i += 1
                continue
            if _COD_COLOR_RE.match(line):
                pending_color = line.split()[1].replace("ROȘU", "ROSU")
                i += 1
                continue

            if _INTERVAL_MARKER in line.lower():
                block = {"kind": kind, "color_code": block_color()}
                pending_color = None
                interval = self._clean_color_prefix(
                    line.split(":", 1)[1].strip() if ":" in line else line
                )
                next_i = i + 1
                # The interval value can be split across a stray line break:
                # either a bare "Interval de valabilitate:" with the date on the
                # next line, or a complete interval broken mid-value (e.g. "...: 1"
                # then "iulie, ora 12 – 1 iulie, ora 21"). A complete interval
                # always carries the "ora <time>" marker, so when it is missing the
                # value is a fragment — stitch the continuation line back on.
                if "ora" not in interval.lower() and next_i < len(lines):
                    nxt = lines[next_i]
                    if not (_COD_BOUNDARY_RE.match(nxt)
                            or _INTERVAL_MARKER in nxt.lower()
                            or "fenomen" in nxt.lower()
                            or _INFORMARE_HEADER_RE.match(nxt)
                            or _ATENTIONARE_HEADER_RE.match(nxt)):
                        cont = self._clean_color_prefix(nxt)
                        interval = f"{interval} {cont}".strip()
                        next_i += 1
                block["interval"] = interval
                title, j = self._extract_warning_title(lines, next_i)
                block["title"] = self._clean_color_prefix(title)
                phenomena, j = self._extract_warning_phenomena(lines, j)
                if phenomena:
                    block["phenomena"] = phenomena
                blocks.append(block)
                i = j
                continue

            i += 1

        return blocks

    def _build_alert(self, blocks):
        """Build a single alert dict from one element's ordered blocks.

        An "informare" block, if present, supplies the alert's own header
        (type ``INFORMARE METEOROLOGICĂ`` with its interval/title/phenomena);
        otherwise the alert is a plain ``ATENȚIONARE METEOROLOGICĂ``. Every
        "atentionare" block becomes a numbered warning under the alert.
        """
        informare = next((b for b in blocks if b["kind"] == "informare"), None)
        warnings = [b for b in blocks if b["kind"] != "informare"]

        if informare is not None:
            alert = {
                "type": "INFORMARE METEOROLOGICĂ",
                "interval": informare["interval"],
                "color_code": informare["color_code"],
            }
            if informare.get("title"):
                alert["title"] = informare["title"]
            if informare.get("phenomena"):
                alert["phenomena"] = informare["phenomena"]
        else:
            alert = {
                "type": "ATENȚIONARE METEOROLOGICĂ",
                "color_code": _most_severe_color(warnings),
            }

        for idx, block in enumerate(warnings, start=1):
            warning = {
                "color_code": block["color_code"],
                "interval": block["interval"],
                "title": block["title"],
            }
            if block.get("phenomena"):
                warning["phenomena"] = block["phenomena"]
            alert[f"warning {idx}"] = warning

        return alert

    def _map_images(self, alerts: dict, html_content: bytes) -> None:
        """Attach map image URLs to the alerts/warnings, in document order.

        The page lists one ``alerta_meteo_produse`` block per product; only
        some carry a ``harta.svg.php`` map (others are map-less nowcasting or
        footer blocks). The maps are collected in document order and the
        map-less blocks are skipped so a stray one can never shift every URL
        onto the wrong target.

        The feed is inconsistent about granularity: sometimes there is one map
        per alert (shared by all its warnings) and sometimes one map per
        warning. The count of maps disambiguates — when it matches the number
        of alerts (and that differs from the number of warnings) the map is
        attached to the whole alert; otherwise each warning gets its own map,
        with a lone warning-less alert carrying its map directly. The zip is
        non-strict so either side may be the shorter one.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        urls = []
        for block in soup.find_all("div", class_="alerta_meteo_produse"):
            img = block.find("img", src=lambda x: x and "harta.svg.php" in x)
            if not img:
                continue
            url = img["src"]
            if url.startswith("/"):
                url = BASE_URL + url
            urls.append(url)

        if not urls:
            return

        alert_list = list(alerts.values())
        # Per-warning targets: each warning, or the alert itself if it has none.
        warning_targets = []
        for alert in alert_list:
            warnings = [alert[key] for key in alert if key.startswith("warning ")]
            warning_targets.extend(warnings if warnings else [alert])

        if len(urls) == len(alert_list) and len(alert_list) != len(warning_targets):
            targets = alert_list
        else:
            targets = warning_targets

        for target, url in zip(targets, urls, strict=False):
            target["url"] = url


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
                    or _INFORMARE_HEADER_RE.match(line)
                    or _ATENTIONARE_HEADER_RE.match(line)):
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
