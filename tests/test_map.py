"""Tests for the locally-generated warning map rendering."""

import base64
import gzip
import json
import re
import time

from custom_components.meteoromania.map import (
    _url_fresh,
    render_map,
    render_map_gz,
)


def test_render_map_colours_counties():
    svg = render_map({"TL": 3, "GL": 2, "BV": 0}, {}).decode("utf-8")
    assert re.search(r'data-judet="TL"[^>]*class="judet cod3"', svg)
    assert re.search(r'data-judet="GL"[^>]*class="judet cod2"', svg)
    # A cod0 county stays neutral (no cod class appended).
    assert re.search(r'data-judet="BV"[^>]*class="judet"', svg)


def test_render_map_colours_relief():
    svg = render_map({}, {"BV_munte_1": 1, "CL_E": 2}).decode("utf-8")
    assert re.search(r'data-munte="BV_munte_1"[^>]*class="[^"]*\bcod1\b[^"]*"', svg)
    assert re.search(r'data-munte="CL_E"[^>]*class="[^"]*\bcod2\b[^"]*"', svg)


def test_render_map_neutral_when_no_codes():
    svg = render_map({}, {}).decode("utf-8")
    # Nothing coloured: no county carries a cod class.
    assert 'class="judet cod' not in svg


def test_render_map_is_valid_svg():
    svg = render_map({"TL": 3}, {}).decode("utf-8")
    assert svg.lstrip().startswith("<")
    assert "</svg>" in svg


def test_render_map_gz_roundtrips_and_is_deterministic():
    etag1, gz1 = render_map_gz({"TL": 3, "GL": 2}, {"BV_munte_1": 1})
    etag2, gz2 = render_map_gz({"GL": 2, "TL": 3}, {"BV_munte_1": 1})
    # Same colouring (order-independent) -> same etag, served from cache.
    assert etag1 == etag2
    # Gzip decompresses to exactly the raw render.
    assert gzip.decompress(gz1) == render_map({"TL": 3, "GL": 2}, {"BV_munte_1": 1})
    # Compressed payload is dramatically smaller than the raw SVG.
    assert len(gz1) < len(gzip.decompress(gz1)) // 10


def test_render_map_gz_different_codes_differ():
    etag_a, _ = render_map_gz({"TL": 3}, {})
    etag_b, _ = render_map_gz({"TL": 2}, {})
    assert etag_a != etag_b


def _signed(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"/api/meteoromania/map/1?authSig=h.{payload}.s"


def test_url_fresh_true_when_far_from_expiry():
    assert _url_fresh(_signed(int(time.time()) + 24 * 3600)) is True


def test_url_fresh_false_when_near_expiry():
    assert _url_fresh(_signed(int(time.time()) + 60)) is False


def test_url_fresh_false_on_garbage():
    assert _url_fresh("/api/meteoromania/map/1") is False
    assert _url_fresh("not a url") is False
