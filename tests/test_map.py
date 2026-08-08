"""Tests for the locally-generated warning map rendering."""

import base64
import gzip
import json
import re
import time
from types import SimpleNamespace

from custom_components.meteoromania.const import DOMAIN
from custom_components.meteoromania.map import (
    _etag,
    _find_codes,
    _url_fresh,
    apply_map_urls,
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


def _token(exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{payload}.s"


def _signed(exp: int) -> str:
    return f"/api/meteoromania/map/abc123?authSig={_token(exp)}"


def test_url_fresh_true_when_far_from_expiry():
    assert _url_fresh(_signed(int(time.time()) + 24 * 3600)) is True


def test_url_fresh_false_when_near_expiry():
    assert _url_fresh(_signed(int(time.time()) + 60)) is False


def test_url_fresh_false_on_garbage():
    assert _url_fresh("/api/meteoromania/map/abc123") is False
    assert _url_fresh("not a url") is False


class _Hass:
    """Minimal stand-in exposing only the ``data`` dict apply_map_urls uses."""

    def __init__(self):
        self.data = {}


def _sign_verbatim(monkeypatch, counter=None):
    """Stand in for async_sign_path with a token _url_fresh will accept."""
    token = _token(int(time.time()) + 24 * 3600)

    def _sign(hass, path, expiry):
        if counter is not None:
            counter.append(path)
        return f"{path}?authSig={token}"

    monkeypatch.setattr("custom_components.meteoromania.map.async_sign_path", _sign)
    return token


def test_apply_map_urls_gives_every_warning_the_alert_map(monkeypatch):
    """ANM ships one map per alert — repeat it on each warning."""
    token = _sign_verbatim(monkeypatch)
    data = {
        "alert 1": {
            "color_code": "PORTOCALIU",
            "county_codes": {"TL": 3},
            "warning 1": {"color_code": "GALBEN"},
            "warning 2": {"color_code": "PORTOCALIU"},
        }
    }
    apply_map_urls(_Hass(), data)

    alert = data["alert 1"]
    expected = f"/api/meteoromania/map/{_etag({'TL': 3}, {})}?authSig={token}"
    assert alert["url"] == expected
    assert alert["warning 1"]["url"] == alert["url"]
    assert alert["warning 2"]["url"] == alert["url"]


def test_apply_map_urls_addresses_by_colouring_not_position(monkeypatch):
    """A reordered feed must not repoint a URL at a different alert's map."""
    _sign_verbatim(monkeypatch)
    first = {
        "alert 1": {"county_codes": {"TL": 3}},
        "alert 2": {"county_codes": {"GL": 1}},
    }
    apply_map_urls(_Hass(), first)
    # Same two alerts, opposite order after ANM dropped an earlier message.
    second = {
        "alert 1": {"county_codes": {"GL": 1}},
        "alert 2": {"county_codes": {"TL": 3}},
    }
    apply_map_urls(_Hass(), second)

    assert first["alert 1"]["url"] == second["alert 2"]["url"]
    assert first["alert 2"]["url"] == second["alert 1"]["url"]


def test_apply_map_urls_reuses_a_still_valid_url(monkeypatch):
    """An unchanged colouring keeps its URL, so browsers keep their cache."""
    signed = []
    _sign_verbatim(monkeypatch, signed)
    hass = _Hass()
    for _ in range(3):
        apply_map_urls(hass, {"alert 1": {"county_codes": {"TL": 3}}})

    assert len(signed) == 1


def test_apply_map_urls_forgets_colourings_that_are_gone(monkeypatch):
    """The URL cache must not accumulate every colouring ever seen."""
    _sign_verbatim(monkeypatch)
    hass = _Hass()
    apply_map_urls(hass, {"alert 1": {"county_codes": {"TL": 3}}})
    apply_map_urls(hass, {"alert 1": {"county_codes": {"GL": 1}}})

    cache = hass.data["meteoromania_map_urls"]
    assert list(cache) == [_etag({"GL": 1}, {})]


def test_find_codes_resolves_the_colouring_named_in_the_url():
    """The view recolours from whichever alert currently carries that colouring."""
    county, zone = {"TL": 3}, {"BV_munte_1": 1}
    hass = _Hass()
    hass.data[DOMAIN] = {
        "entry": SimpleNamespace(
            data={"alert 1": {"county_codes": county, "zone_codes": zone}}
        )
    }

    assert _find_codes(hass, _etag(county, zone)) == (county, zone)


def test_find_codes_returns_none_for_a_colouring_no_longer_present():
    """An expired URL must 404 rather than serve some other alert's map."""
    hass = _Hass()
    hass.data[DOMAIN] = {
        "entry": SimpleNamespace(data={"alert 1": {"county_codes": {"TL": 3}}})
    }

    assert _find_codes(hass, _etag({"GL": 1}, {})) is None
