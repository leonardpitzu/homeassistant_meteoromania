import asyncio
import xml.etree.ElementTree as ET
from html import unescape
import re

import aiohttp
from bs4 import BeautifulSoup

URL_HTML = "https://www.meteoromania.ro/avertizari/"
URL_XML = "https://www.meteoromania.ro/avertizari-xml.php"
HEADERS = {"User-Agent": "Mozilla/5.0"}


class MeteoRomaniaApiClient:
    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def fetch_alerts(self):
        alerts = {}
        timeout = aiohttp.ClientTimeout(total=30)

        xml_content, html_content = await asyncio.gather(
            self._fetch(URL_XML, timeout),
            self._fetch(URL_HTML, timeout),
        )

        root = ET.fromstring(xml_content)
        alerts_xml = root.findall(".//avertizare")

        for i, alert in enumerate(alerts_xml, start=1):
            alert_key = f"alert {i}"

            alert_level_color = {
                "0": "GALBEN", "1": "PORTOCALIU", "2": "ROSU"
            }.get(alert.attrib.get("culoare", "").strip(), "NECUNOSCUT")

            alerts[alert_key] = {
                "type": alert.attrib.get("numeTipMesaj", "").strip(),
                "interval": alert.attrib.get("intervalul", "").strip(),
                "color_code": alert_level_color,
            }

            raw_html = alert.attrib.get("mesaj", "")
            decoded_html = unescape(raw_html)

            lines, soup = self._extract_lines(decoded_html)
            image_colors = self._detect_image_colors(soup)

            warnings = self._parse_warnings(
                lines=lines,
                image_colors=image_colors,
                fallback_color=alert_level_color,
            )

            for idx, warning in enumerate(warnings, start=1):
                alerts[alert_key][f"warning {idx}"] = warning

        # Map images from HTML page
        soup = BeautifulSoup(html_content, "html.parser")

        alert_blocks = soup.find_all("div", class_="alerta_meteo_produse")
        for idx, block in enumerate(alert_blocks, start=1):
            img = block.find("img", src=lambda x: x and "harta.svg.php" in x)
            if img:
                url = img["src"]
                if url.startswith("/"):
                    url = "https://www.meteoromania.ro" + url
                alert_key = f"alert {idx}"
                if alert_key in alerts:
                    alerts[alert_key]["url"] = url

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
        warnings = []
        color_idx = 0
        pending_color = None

        def next_color():
            nonlocal color_idx
            if pending_color:
                return pending_color
            if color_idx < len(image_colors):
                c = image_colors[color_idx]
                color_idx += 1
                if c != "NECUNOSCUT":
                    return c
            return fallback_color

        i = 0
        while i < len(lines):
            line = lines[i]

            if re.match(r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)", line, re.IGNORECASE):
                pending_color = line.split()[1].replace("ROȘU", "ROSU")
                i += 1
                continue

            if "interval de valabilitate" in line.lower():
                warning = {"color_code": next_color()}
                pending_color = None

                warning["interval"] = self._clean_color_prefix(
                    line.split(":", 1)[1].strip() if ":" in line else line
                )

                title = ""
                j = i + 1
#                if j < len(lines) and "fenomene" in lines[j].lower():
#                    title = lines[j].split(":", 1)[1].strip()
#                    j += 1

                if j < len(lines) and "fenomen" in lines[j].lower():
                    if ":" in lines[j]:
                        title = lines[j].split(":", 1)[1].strip()
                    else:
                        title = lines[j].strip()
                    j += 1
                    # Content may be on the next line if the colon line was bare
                    if not title and j < len(lines) \
                       and "zone " not in lines[j].lower() \
                       and "interval" not in lines[j].lower():
                        title = lines[j].strip()
                        j += 1

                warning["title"] = self._clean_color_prefix(title)

                desc = []
                while j < len(lines):
                    if re.match(r"^COD\s+", lines[j], re.IGNORECASE) \
                       or "interval de valabilitate" in lines[j].lower() \
                       or lines[j].upper().startswith("MESAJ") \
                       or re.match(r"^(AVERTIZARE|INFORMARE)\s+METEOROLOGIC",
                                   lines[j], re.IGNORECASE):
                        break
                    desc.append(lines[j])
                    j += 1

                if desc:
                    warning["phenomena"] = " ".join(desc)

                warnings.append(warning)
                i = j
                continue

            i += 1

        return warnings

    def _clean_color_prefix(self, text):
        return re.sub(
            r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)\s*",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        )
