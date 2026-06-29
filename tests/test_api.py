"""Tests for the MeteoRomania API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.meteoromania.api import (
    MeteoRomaniaApiClient,
    MeteoRomaniaApiError,
)


# ---------------------------------------------------------------------------
# Sample responses
# ---------------------------------------------------------------------------

SAMPLE_XML_ONE_ALERT = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare
    culoare="0"
    numeTipMesaj="Avertizare meteorologica"
    intervalul="15 februarie - 16 februarie"
    mesaj="&lt;img src=&quot;/images/galben.png&quot;&gt;&lt;br&gt;Interval de valabilitate: 15 februarie ora 10:00 - 16 februarie ora 06:00&lt;br&gt;Fenomene vizate: intensificari ale vantului&lt;br&gt;In zona montana vantul va avea intensificari sustinute."
  />
</avertizari>"""

SAMPLE_XML_TWO_ALERTS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="Avertizare meteorologica" intervalul="15 - 16 februarie"
    mesaj="&lt;img src=&quot;/images/galben.png&quot;&gt;&lt;br&gt;Interval de valabilitate: 15 feb&lt;br&gt;Fenomene vizate: vant&lt;br&gt;vant puternic" />
  <avertizare culoare="1" numeTipMesaj="Cod portocaliu" intervalul="16 - 17 februarie"
    mesaj="&lt;img src=&quot;/images/portocaliu.png&quot;&gt;&lt;br&gt;Interval de valabilitate: 16 feb&lt;br&gt;Fenomene vizate: ninsori&lt;br&gt;ninsori abundente" />
</avertizari>"""

SAMPLE_XML_EMPTY = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari/>"""

SAMPLE_XML_RED_ALERT = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="2" numeTipMesaj="Cod rosu" intervalul="16 februarie"
    mesaj="&lt;img src=&quot;/images/rosu.png&quot;&gt;&lt;br&gt;Interval de valabilitate: 16 februarie ora 06:00 - 18:00&lt;br&gt;Fenomene vizate: viscol&lt;br&gt;Viscol puternic in zona de munte." />
</avertizari>"""

SAMPLE_XML_UNKNOWN_COLOR = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="9" numeTipMesaj="Test" intervalul="test"
    mesaj="&lt;br&gt;Interval de valabilitate: test&lt;br&gt;Fenomene vizate: test&lt;br&gt;detalii" />
</avertizari>"""

# The feed sometimes splits a complete interval across a stray <br>, leaving the
# "Interval de valabilitate:" line ending in a bare fragment ("1") with the rest
# of the date on the following line. Without stitching, the fragment becomes the
# interval and the "Fenomene vizate:" line is swallowed into the description.
SAMPLE_XML_SPLIT_INTERVAL = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="Avertizare meteorologica" intervalul="1 iulie"
    mesaj="&lt;img src=&quot;/images/galben.png&quot;&gt;&lt;br&gt;Interval de valabilitate: 1&lt;br&gt;iulie, ora 12 - 1 iulie, ora 21&lt;br&gt;Fenomene vizate: val de caldura intens si persistent&lt;br&gt;Zone afectate: nordul tarii." />
</avertizari>"""


SAMPLE_HTML_ONE_MAP = b"""\
<html><body>
<div class="alerta_meteo_produse">
  <img src="/avertizari/harta.svg.php?id=123" />
</div>
</body></html>"""

SAMPLE_HTML_TWO_MAPS = b"""\
<html><body>
<div class="alerta_meteo_produse">
  <img src="/avertizari/harta.svg.php?id=100" />
</div>
<div class="alerta_meteo_produse">
  <img src="/avertizari/harta.svg.php?id=200" />
</div>
</body></html>"""

SAMPLE_HTML_EMPTY = b"<html><body></body></html>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(xml_bytes: bytes, html_bytes: bytes):
    """Build a mock ``aiohttp.ClientSession`` that returns canned responses."""
    session = MagicMock()

    def _get(url, **kwargs):
        data = xml_bytes if "xml" in url.lower() else html_bytes
        resp = AsyncMock()
        resp.raise_for_status = MagicMock()
        resp.read = AsyncMock(return_value=data)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=resp)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    session.get = _get
    return session


# ---------------------------------------------------------------------------
# fetch_alerts integration-style tests
# ---------------------------------------------------------------------------


async def test_fetch_alerts_single():
    """A header-less message collapses into a default alert with one warning."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert result["has_alerts"] is True
    assert result["alert_count"] == 1

    alert = result["alert 1"]
    assert alert["type"] == "ATENȚIONARE METEOROLOGICĂ"
    assert alert["color_code"] == "NECUNOSCUT"
    assert "url" not in alert

    warning = alert["warning 1"]
    assert warning["color_code"] == "GALBEN"
    assert "15 februarie" in warning["interval"]
    assert "intensificari" in warning["title"]
    assert "vantul" in warning["phenomena"]
    assert "harta.svg.php" in warning["url"]


async def test_fetch_alerts_multiple():
    """Two <avertizare> elements become two separate alerts, one map each."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_TWO_ALERTS, SAMPLE_HTML_TWO_MAPS))
    result = await client.fetch_alerts()

    assert result["alert_count"] == 2
    a1 = result["alert 1"]
    a2 = result["alert 2"]
    assert a1["warning 1"]["color_code"] == "GALBEN"
    assert a2["warning 1"]["color_code"] == "PORTOCALIU"
    assert "harta.svg.php?id=100" in a1["warning 1"]["url"]
    assert "harta.svg.php?id=200" in a2["warning 1"]["url"]


async def test_fetch_alerts_empty():
    """No XML avertizare elements → has_alerts False, count 0."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_EMPTY, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert result["has_alerts"] is False
    assert result["alert_count"] == 0


async def test_fetch_alerts_red():
    """Red (rosu.png) image maps the warning to ROSU."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_RED_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert result["alert 1"]["warning 1"]["color_code"] == "ROSU"


async def test_fetch_alerts_unknown_color():
    """Unknown culoare value with no image maps to NECUNOSCUT."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_UNKNOWN_COLOR, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert result["alert 1"]["warning 1"]["color_code"] == "NECUNOSCUT"


async def test_fetch_alerts_split_interval():
    """A line-break-split interval is stitched, keeping the title/phenomena intact."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_SPLIT_INTERVAL, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    warning = result["alert 1"]["warning 1"]
    # Fragment "1" + continuation "iulie, ora 12 ..." form the full interval.
    assert warning["interval"] == "1 iulie, ora 12 - 1 iulie, ora 21"
    # The "Fenomene vizate:" line becomes the title, not part of the description.
    assert warning["title"] == "val de caldura intens si persistent"
    assert "iulie, ora 12" not in warning.get("phenomena", "")
    assert "Zone afectate" in warning["phenomena"]


async def test_html_url_absolute():
    """Relative image URL is expanded to an absolute URL on the warning."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert (
        result["alert 1"]["warning 1"]["url"]
        == "https://www.meteoromania.ro/avertizari/harta.svg.php?id=123"
    )


async def test_no_html_map():
    """When HTML has no map image, the warning has no 'url' key."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert "url" not in result["alert 1"]["warning 1"]


SAMPLE_HTML_LEADING_MAPLESS = b"""\
<html><body>
<div class="alerta_meteo_produse"><p>intro, no map</p></div>
<div class="alerta_meteo_produse">
  <img src="/avertizari/harta.svg.php?id=100" />
</div>
<div class="alerta_meteo_produse">
  <img src="/avertizari/harta.svg.php?id=200" />
</div>
</body></html>"""


async def test_maps_keyed_by_map_order_not_block_position():
    """A leading map-less block must not shift every map onto the wrong alert."""
    client = MeteoRomaniaApiClient(
        _make_session(SAMPLE_XML_TWO_ALERTS, SAMPLE_HTML_LEADING_MAPLESS)
    )
    result = await client.fetch_alerts()

    assert "harta.svg.php?id=100" in result["alert 1"]["warning 1"]["url"]
    assert "harta.svg.php?id=200" in result["alert 2"]["warning 1"]["url"]


SAMPLE_XML_LONE_INFORMARE = (
    """\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="x" intervalul="x"
    mesaj="INFORMARE METEOROLOGICĂ&lt;br&gt;Interval de valabilitate: 1 mai&lt;br&gt;Fenomene vizate: vreme calduroasa&lt;br&gt;detalii" />
</avertizari>"""
).encode("utf-8")


async def test_map_attaches_to_lone_alert_stub():
    """An alert with no warnings still receives its own map."""
    client = MeteoRomaniaApiClient(
        _make_session(SAMPLE_XML_LONE_INFORMARE, SAMPLE_HTML_ONE_MAP)
    )
    result = await client.fetch_alerts()

    alert = result["alert 1"]
    assert alert["type"] == "INFORMARE METEOROLOGICĂ"
    assert not any(key.startswith("warning ") for key in alert)
    assert "harta.svg.php?id=123" in alert["url"]



async def test_network_error():
    """Network failures propagate as exceptions."""
    session = MagicMock()

    def _get(url, **kwargs):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    session.get = _get
    client = MeteoRomaniaApiClient(session)

    with pytest.raises(Exception, match="Connection refused"):
        await client.fetch_alerts()


def _make_session_partial(xml_bytes: bytes, html_exc: Exception):
    """Session where the XML request succeeds but the HTML request fails."""
    session = MagicMock()

    def _get(url, **kwargs):
        ctx = MagicMock()
        if "xml" in url.lower():
            resp = AsyncMock()
            resp.raise_for_status = MagicMock()
            resp.read = AsyncMock(return_value=xml_bytes)
            ctx.__aenter__ = AsyncMock(return_value=resp)
        else:
            ctx.__aenter__ = AsyncMock(side_effect=html_exc)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    session.get = _get
    return session


async def test_html_failure_tolerated():
    """A failing HTML page still yields XML alerts, just without map URLs."""
    client = MeteoRomaniaApiClient(
        _make_session_partial(SAMPLE_XML_ONE_ALERT, Exception("503 Service Unavailable"))
    )
    result = await client.fetch_alerts()

    assert result["alert_count"] == 1
    assert "url" not in result["alert 1"]["warning 1"]


async def test_malformed_xml_raises():
    """Invalid XML surfaces as MeteoRomaniaApiError, not a raw parser error."""
    client = MeteoRomaniaApiClient(_make_session(b"<not-valid-xml", SAMPLE_HTML_EMPTY))

    with pytest.raises(MeteoRomaniaApiError):
        await client.fetch_alerts()


# ---------------------------------------------------------------------------
# Helper-method unit tests
# ---------------------------------------------------------------------------


def test_extract_lines():
    """_extract_lines turns HTML with <br> into clean text lines."""
    client = MeteoRomaniaApiClient(MagicMock())
    lines, _soup = client._extract_lines("Line one<br>Line two<br><br>Line three")

    assert len(lines) == 3
    assert lines[0] == "Line one"
    assert lines[1] == "Line two"
    assert lines[2] == "Line three"


def test_detect_image_colors():
    """_detect_image_colors extracts colour names from <img> src attributes."""
    from bs4 import BeautifulSoup

    client = MeteoRomaniaApiClient(MagicMock())
    html = '<img src="galben.png"><img src="portocaliu.png"><img src="rosu.png"><img src="other.png">'
    soup = BeautifulSoup(html, "html.parser")

    assert client._detect_image_colors(soup) == ["GALBEN", "PORTOCALIU", "ROSU", "NECUNOSCUT"]


def test_parse_blocks_empty():
    """Lines without known markers produce no blocks."""
    client = MeteoRomaniaApiClient(MagicMock())
    assert client._parse_blocks(["random text"], [], "GALBEN") == []


def test_clean_color_prefix():
    """_clean_color_prefix strips leading COD XXXX markers."""
    client = MeteoRomaniaApiClient(MagicMock())
    assert client._clean_color_prefix("COD GALBEN some text") == "some text"
    assert client._clean_color_prefix("COD PORTOCALIU test") == "test"
    assert client._clean_color_prefix("no prefix") == "no prefix"
    assert client._clean_color_prefix("  COD GALBEN  spaced  ") == "spaced"


# ---------------------------------------------------------------------------
# Bug-fix regression tests
# ---------------------------------------------------------------------------

SAMPLE_XML_AVERTIZARE_BOUNDARY = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="1" numeTipMesaj="Avertizare" intervalul="conform textelor"
    mesaj="Interval de valabilitate: 22 apr&lt;br&gt;Fenomene vizate:&lt;br&gt;precipitatii mixte&lt;br&gt;descriere lunga.&lt;br&gt;AVERTIZARE METEOROLOGICA&lt;br&gt;COD GALBEN&lt;br&gt;Interval de valabilitate: 23 apr&lt;br&gt;Fenomene vizate: vant puternic&lt;br&gt;rafale de 50 km/h" />
</avertizari>"""


async def test_avertizare_boundary_not_in_phenomena():
    """AVERTIZARE METEOROLOGICA must not bleed into the previous warning."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_AVERTIZARE_BOUNDARY, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    w1 = result["alert 1"]["warning 1"]
    assert "AVERTIZARE" not in w1.get("phenomena", "")

    w2 = result["alert 1"]["warning 2"]
    assert "vant puternic" in w2["title"]


SAMPLE_XML_FENOMENE_SPLIT = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="Informare" intervalul="22 apr"
    mesaj="Interval de valabilitate: 22 apr&lt;br&gt;Fenomene vizate:&lt;br&gt;ninsori abundente&lt;br&gt;Zone afectate: toata tara&lt;br&gt;text detaliat" />
</avertizari>"""


async def test_fenomene_split_line_title():
    """When 'Fenomene vizate:' has no content after colon, next line becomes title."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_FENOMENE_SPLIT, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    w = result["alert 1"]["warning 1"]
    assert w["title"] == "ninsori abundente"
    assert "Zone afectate" in w.get("phenomena", "")


SAMPLE_XML_FENOMEN_VARIANT = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="Test" intervalul="23 apr"
    mesaj="Interval de valabilitate: 23 apr&lt;br&gt;Fenomen vizate: vant puternic&lt;br&gt;detalii despre vant" />
</avertizari>"""


async def test_fenomen_variant_matched():
    """'Fenomen vizate' (without final 'e') is handled like 'Fenomene vizate'."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_FENOMEN_VARIANT, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    w = result["alert 1"]["warning 1"]
    assert w["title"] == "vant puternic"


SAMPLE_XML_INTERVAL_SPLIT = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="1" numeTipMesaj="Avertizare" intervalul="x"
    mesaj="COD PORTOCALIU&lt;br&gt;Interval de valabilitate:&lt;br&gt;26 iunie, ora 10 \xe2\x80\x93 27 iunie, ora 10&lt;br&gt;Fenomene vizate: canicula&lt;br&gt;Zone afectate: vest&lt;br&gt;detalii" />
</avertizari>"""


async def test_interval_split_line():
    """A bare 'Interval de valabilitate:' adopts the date from the next line."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_INTERVAL_SPLIT, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    w = result["alert 1"]["warning 1"]
    assert w["color_code"] == "PORTOCALIU"
    assert "26 iunie" in w["interval"]
    assert w["title"] == "canicula"
    assert "Zone afectate" in w.get("phenomena", "")


# ---------------------------------------------------------------------------
# Message-type grouping: INFORMARE opens an alert, ATENȚIONARE are its warnings
# ---------------------------------------------------------------------------

SAMPLE_XML_INFORMARE_WITH_WARNINGS = (
    """\
<?xml version="1.0" encoding="UTF-8"?>
<avertizari>
  <avertizare culoare="0" numeTipMesaj="x" intervalul="x"
    mesaj="INFORMARE METEOROLOGICĂ&lt;br&gt;Interval de valabilitate: 1 mai ora 10 – 2 mai ora 21&lt;br&gt;Fenomene vizate: vreme calduroasa&lt;br&gt;Zone afectate: toata tara&lt;br&gt;Nota: descriere generala&lt;br&gt;ATENȚIONARE METEOROLOGICĂ&lt;br&gt;COD GALBEN&lt;br&gt;Interval de valabilitate: 1 mai, intervalul orar 12 – 21&lt;br&gt;Fenomene vizate: temperaturi ridicate&lt;br&gt;Zone afectate: sud&lt;br&gt;detalii sud&lt;br&gt;COD PORTOCALIU&lt;br&gt;Interval de valabilitate: 1 mai, intervalul orar 14 – 20&lt;br&gt;Fenomene vizate: instabilitate atmosferica&lt;br&gt;Zone afectate: nord&lt;br&gt;detalii nord" />
</avertizari>"""
).encode("utf-8")


async def test_informare_groups_atentionari_as_warnings():
    """Within one element, INFORMARE is the header and the CODs are its warnings."""
    client = MeteoRomaniaApiClient(
        _make_session(SAMPLE_XML_INFORMARE_WITH_WARNINGS, SAMPLE_HTML_ONE_MAP)
    )
    result = await client.fetch_alerts()

    assert result["alert_count"] == 1
    alert = result["alert 1"]
    assert alert["type"] == "INFORMARE METEOROLOGICĂ"
    assert alert["color_code"] == "NECUNOSCUT"
    assert "1 mai" in alert["interval"]
    assert alert["title"] == "vreme calduroasa"
    # One map for the whole alert (fewer maps than warnings), shared by both.
    assert "harta.svg.php?id=123" in alert["url"]

    w1 = alert["warning 1"]
    assert w1["color_code"] == "GALBEN"
    assert w1["title"] == "temperaturi ridicate"

    w2 = alert["warning 2"]
    assert w2["color_code"] == "PORTOCALIU"
    assert w2["title"] == "instabilitate atmosferica"

