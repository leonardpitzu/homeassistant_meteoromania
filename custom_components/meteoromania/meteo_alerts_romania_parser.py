"""Standalone, synchronous runner for the MeteoRomania alert parser.

This is a dev/debug helper, NOT part of the integration runtime. It fetches the
live ANM feeds with ``requests`` and runs the *exact same* parsing code as the
Home Assistant integration (``api.py``) by importing and calling
``MeteoRomaniaApiClient.parse``. There is a single parsing implementation, so
running this script shows precisely the data the integration would expose,
including the per-county ``county_codes`` and per-relief ``zone_codes``.

Run it from this directory:

    python meteo_alerts_romania_parser.py            # parsed result
    python meteo_alerts_romania_parser.py --raw-xml  # dump the raw XML feed
"""

import sys

import requests
from api import HEADERS, URL_XML, MeteoRomaniaApiClient


def fetch_raw() -> bytes:
    """Fetch the ANM XML feed synchronously and return its bytes."""
    resp = requests.get(URL_XML, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_alerts() -> dict:
    """Fetch the live feed and parse it with the integration's own logic."""
    # parse() needs no network session, so a None session is fine here.
    client = MeteoRomaniaApiClient(session=None)
    return client.parse(fetch_raw())



if __name__ == "__main__":
    if "--raw-xml" in sys.argv:
        sys.stdout.buffer.write(fetch_raw())
    else:
        from pprint import pprint

        pprint(parse_alerts(), width=160, sort_dicts=False)
