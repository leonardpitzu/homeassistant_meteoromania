import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from html import unescape
import re

URL_HTML = "https://www.meteoromania.ro/avertizari/"
URL_XML = "https://www.meteoromania.ro/avertizari-xml.php"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def clean_color_prefix(text):
    """Remove leading COD XXX markers like 'COD GALBEN'."""
    return re.sub(r"^COD\s+(GALBEN|PORTOCALIU|ROȘU|ROSU)\s*", "", text.strip(), flags=re.IGNORECASE)

def parse_alerts():
    alerts = {}

    # Step 1: Fetch and parse XML
    response_xml = requests.get(URL_XML, headers=HEADERS)
    root = ET.fromstring(response_xml.content)
    alerts_xml = root.findall(".//avertizare")

    for i, alert in enumerate(alerts_xml, start=1):
        alert_key = f"alert {i}"
        alerts[alert_key] = {
            "type": alert.attrib.get("numeTipMesaj", "").strip(),
            "interval": alert.attrib.get("intervalul", "").strip(),
            "color_code": {
                "0": "GALBEN", "1": "PORTOCALIU", "2": "ROSU"
            }.get(alert.attrib.get("culoare", "").strip(), "NECUNOSCUT"),
        }

        # Step 2: Decode warning content
        raw_html = alert.attrib.get("mesaj", "")
        decoded_html = unescape(raw_html)
        soup = BeautifulSoup(decoded_html, "html.parser")
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]

        # Collect <img> tags to detect color per warning
        images = soup.find_all("img")
        image_colors = []
        for img in images:
            src = img.get("src", "").lower()
            if "galben" in src:
                image_colors.append("GALBEN")
            elif "portocaliu" in src:
                image_colors.append("PORTOCALIU")
            elif "rosu" in src:
                image_colors.append("ROSU")
            else:
                image_colors.append("NECUNOSCUT")

        warning_counter = 1
        j = 0
        color_idx = 0

        while j < len(paragraphs) - 1:
            meta = paragraphs[j]
            meta_lc = meta.lower()

            if "interval de valabilitate" in meta_lc and "fenomene vizate" in meta_lc:
                warning = {}

                # Color code
                if color_idx < len(image_colors):
                    warning["color_code"] = image_colors[color_idx]
                    color_idx += 1
                else:
                    warning["color_code"] = "NECUNOSCUT"

                # Extract interval and title
                parts = meta.split("Fenomene vizate:")
                interval_part = parts[0].replace("Interval de valabilitate:", "").strip()
                title_part = parts[1].split("Zone afectate")[0].strip() if len(parts) > 1 else ""

                warning["interval"] = clean_color_prefix(interval_part)
                warning["title"] = clean_color_prefix(title_part)

                # Next paragraph is phenomena
                phenomena = paragraphs[j + 1].strip()
                if not any(x in phenomena.upper() for x in ["MESAJ", "AVERTIZARE"]):
                    warning["phenomena"] = phenomena
                    alerts[alert_key][f"warning {warning_counter}"] = warning
                    warning_counter += 1
                    j += 2
                else:
                    j += 1
            else:
                j += 1

    # Step 3: Match image URLs from HTML
    response_html = requests.get(URL_HTML, headers=HEADERS)
    soup = BeautifulSoup(response_html.content, "html.parser")
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

    return alerts

# Test it locally
if __name__ == "__main__":
    from pprint import pprint
    data = parse_alerts()
    pprint(data, width=160)
