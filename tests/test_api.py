"""Tests for the Meteo Romania API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.meteo_romania_alerts.api import MeteoRomaniaApiClient


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
    """One alert with one warning is parsed correctly."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert result["has_alerts"] is True
    assert result["alert_count"] == 1

    alert = result["alert 1"]
    assert alert["type"] == "Avertizare meteorologica"
    assert alert["color_code"] == "GALBEN"
    assert "harta.svg.php" in alert["url"]

    warning = alert["warning 1"]
    assert warning["color_code"] == "GALBEN"
    assert "15 februarie" in warning["interval"]
    assert "intensificari" in warning["title"]
    assert "vantul" in warning["phenomena"]


async def test_fetch_alerts_multiple():
    """Two alerts produce two keyed entries."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_TWO_ALERTS, SAMPLE_HTML_TWO_MAPS))
    result = await client.fetch_alerts()

    assert result["alert_count"] == 2
    assert result["alert 1"]["color_code"] == "GALBEN"
    assert result["alert 2"]["color_code"] == "PORTOCALIU"
    assert "harta.svg.php?id=100" in result["alert 1"]["url"]
    assert "harta.svg.php?id=200" in result["alert 2"]["url"]


async def test_fetch_alerts_empty():
    """No XML avertizare elements → has_alerts False, count 0."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_EMPTY, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert result["has_alerts"] is False
    assert result["alert_count"] == 0


async def test_fetch_alerts_red():
    """Red (culoare=2) alert is mapped to ROSU."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_RED_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert result["alert 1"]["color_code"] == "ROSU"


async def test_fetch_alerts_unknown_color():
    """Unknown culoare value maps to NECUNOSCUT."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_UNKNOWN_COLOR, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert result["alert 1"]["color_code"] == "NECUNOSCUT"


async def test_html_url_absolute():
    """Relative image URL is expanded to an absolute URL."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_ONE_MAP))
    result = await client.fetch_alerts()

    assert result["alert 1"]["url"] == "https://www.meteoromania.ro/avertizari/harta.svg.php?id=123"


async def test_no_html_map():
    """When HTML has no map image, alert has no 'url' key."""
    client = MeteoRomaniaApiClient(_make_session(SAMPLE_XML_ONE_ALERT, SAMPLE_HTML_EMPTY))
    result = await client.fetch_alerts()

    assert "url" not in result["alert 1"]


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


def test_parse_warnings_empty():
    """Lines without known markers produce no warnings."""
    client = MeteoRomaniaApiClient(MagicMock())
    assert client._parse_warnings(lines=["random text"], image_colors=[], fallback_color="GALBEN") == []


def test_clean_color_prefix():
    """_clean_color_prefix strips leading COD XXXX markers."""
    client = MeteoRomaniaApiClient(MagicMock())
    assert client._clean_color_prefix("COD GALBEN some text") == "some text"
    assert client._clean_color_prefix("COD PORTOCALIU test") == "test"
    assert client._clean_color_prefix("no prefix") == "no prefix"
    assert client._clean_color_prefix("  COD GALBEN  spaced  ") == "spaced"
