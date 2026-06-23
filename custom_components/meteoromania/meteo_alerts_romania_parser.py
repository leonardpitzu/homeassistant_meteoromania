"""Standalone, synchronous runner for the MeteoRomania alert parser.

This is a dev/debug helper, NOT part of the integration runtime. It fetches the
live ANM feeds with ``requests`` and runs the *exact same* parsing code as the
Home Assistant integration (``api.py``) by importing and calling
``MeteoRomaniaApiClient.parse``. There is a single parsing implementation, so
running this script shows precisely the data the integration would expose and
the two can never drift out of sync.

Run it from this directory:

    python meteo_alerts_romania_parser.py            # parsed result
    python meteo_alerts_romania_parser.py --raw-xml  # dump the raw XML feed
"""

import sys

import requests

from api import HEADERS, URL_HTML, URL_XML, MeteoRomaniaApiClient


def fetch_raw() -> tuple[bytes, bytes]:
    """Fetch the XML and HTML feeds synchronously and return their bytes."""
    xml = requests.get(URL_XML, headers=HEADERS, timeout=30)
    xml.raise_for_status()
    html = requests.get(URL_HTML, headers=HEADERS, timeout=30)
    html.raise_for_status()
    return xml.content, html.content


def parse_alerts() -> dict:
    """Fetch the live feeds and parse them with the integration's own logic."""
    xml_content, html_content = fetch_raw()
    # parse() needs no network session, so a None session is fine here.
    client = MeteoRomaniaApiClient(session=None)
    return client.parse(xml_content, html_content)


if __name__ == "__main__":
    if "--raw-xml" in sys.argv:
        xml_content, _ = fetch_raw()
        sys.stdout.buffer.write(xml_content)
    else:
        from pprint import pprint

        pprint(parse_alerts(), width=160, sort_dicts=False)
