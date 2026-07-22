"""Tests for the locally-generated warning map rendering."""

import re

from custom_components.meteoromania.map import render_map


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
