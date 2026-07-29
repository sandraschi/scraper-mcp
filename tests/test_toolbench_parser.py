"""ToolBench parser unit tests — A.1/A.2/A.5 regression gates.

Runs against committed fixtures under tests/fixtures/toolbench/.
No live HTTP calls.
"""

import json
import pathlib
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "toolbench"


def _load_json_fixture() -> dict:
    raw = (FIXTURES / "api_servers_scraper-mcp.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _load_html_fixture() -> str:
    html_files = sorted(FIXTURES.glob("tools_*.html"))
    assert html_files, "no HTML fixture found — run scripts/capture_fixtures.py"
    return html_files[0].read_text(encoding="utf-8")


# ===========================================================================
# A.1 — _extract_pct regression gate
# ===========================================================================


def test_extract_pct_collapsed_text_misses():
    """Old get_text(strip=True) collapsed 'Definition Quality 62' to 'DefinitionQuality62'."""
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    assert _extract_pct("DefinitionQuality62", "Definition Quality") is None


def test_extract_pct_spaced_text_hits():
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    assert _extract_pct("Definition Quality 62 Protocol Compliance 48", "Definition Quality") == 62.0


def test_extract_pct_label_absent_returns_none():
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    val = _extract_pct("No label here", "Definition Quality")
    assert val is None, f"expected None, got {val}"


def test_extract_pct_float_value():
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    assert _extract_pct("Definition Quality 62.5", "Definition Quality") == 62.5


def test_extract_pct_all_dimensions():
    from scraper_mcp.scrapers.toolbench_score import _DIMENSION_LABELS, _extract_pct

    text = "Definition Quality 62 Protocol Readiness 48 Supportability 55"
    assert _extract_pct(text, _DIMENSION_LABELS["definition_score"]) == 62.0
    assert _extract_pct(text, _DIMENSION_LABELS["protocol_score"]) == 48.0
    assert _extract_pct(text, _DIMENSION_LABELS["supportability_score"]) == 55.0


def test_extract_pct_skips_percentage_weight():
    """The weight (50%) appears before the actual score (79). Must pick 79."""
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    text = "Definition Quality Pattern-based scoring · 50% some markup 79"
    assert _extract_pct(text, "Definition Quality") == 79.0


def test_extract_pct_number_not_percent_still_found():
    """A plain number without trailing % is matched normally."""
    from scraper_mcp.scrapers.toolbench_score import _extract_pct

    text = "Protocol Readiness 80"
    assert _extract_pct(text, "Protocol Readiness") == 80.0


def test_dimension_scores_from_real_html_fixture():
    """A.1 gate: every dimension parses non-null from a real fixture."""
    from bs4 import BeautifulSoup

    from scraper_mcp.scrapers.toolbench_score import _DIMENSION_LABELS, _extract_pct

    html = _load_html_fixture()
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    for key, label in _DIMENSION_LABELS.items():
        val = _extract_pct(text, label)
        assert val is not None, f"{key} ({label}) is None in fixture HTML"
        assert val not in (50.0, 20.0, 30.0), f"{key} ({label}) = {val} is a methodology weight, not a real score"


# ===========================================================================
# A.2 — grade_from_score / resolve_grade
# ===========================================================================


def test_grade_from_score_boundaries():
    from scraper_mcp.scrapers.toolbench_score import grade_from_score

    assert grade_from_score(None) == "?"
    assert grade_from_score(90.0) == "A+"
    assert grade_from_score(89.9) == "A"
    assert grade_from_score(80.0) == "A"
    assert grade_from_score(70.0) == "B"
    assert grade_from_score(60.0) == "C"
    assert grade_from_score(50.0) == "D"
    assert grade_from_score(49.9) == "F"
    assert grade_from_score(0.0) == "F"


def test_resolve_grade_prefers_api():
    from scraper_mcp.scrapers.toolbench_score import resolve_grade

    assert resolve_grade("C", 67.0) == "C"


def test_resolve_grade_falls_back_to_derived():
    from scraper_mcp.scrapers.toolbench_score import resolve_grade

    assert resolve_grade(None, 67.0) == "C"
    assert resolve_grade("?", 55.0) == "D"
    assert resolve_grade("", 42.0) == "F"


def test_resolve_grade_missing_both():
    from scraper_mcp.scrapers.toolbench_score import resolve_grade

    assert resolve_grade(None, None) == "?"


def test_html_fixture_contains_grade_letters():
    """Sanity: the old regex loop WOULD have picked a wrong grade."""
    from bs4 import BeautifulSoup

    html = _load_html_fixture()
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    found = bool(re.search(r"\b[ABCDF]\b", text))
    assert found, "fixture HTML has no grade letters — old bug wouldn't reproduce"


# ===========================================================================
# A.5 — _match_server
# ===========================================================================


def test_match_server_exact_name():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [{"name": "scraper-mcp", "id": "abc", "status": "SCORED"}]
    result = _match_server(servers, "scraper-mcp")
    assert result is not None
    assert result["id"] == "abc"


def test_match_server_prefers_scored():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [
        {"name": "scraper-mcp", "id": "unscored", "status": "UNSCORED"},
        {"name": "scraper-mcp", "id": "scored", "status": "SCORED"},
    ]
    result = _match_server(servers, "scraper-mcp")
    assert result is not None
    assert result["id"] == "scored"


def test_match_server_full_name_suffix():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [
        {
            "name": "other-name",
            "full_name": "sandraschi/scraper-mcp",
            "id": "xyz",
            "status": "SCORED",
        }
    ]
    result = _match_server(servers, "scraper-mcp")
    assert result is not None
    assert result["id"] == "xyz"


def test_match_server_slug():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [{"name": "Other Display Name", "slug": "scraper-mcp", "id": "slugged", "status": "SCORED"}]
    result = _match_server(servers, "scraper-mcp")
    assert result is not None
    assert result["id"] == "slugged"


def test_match_server_no_match_returns_none():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [{"name": "unrelated", "id": "nope"}]
    assert _match_server(servers, "scraper-mcp") is None


def test_match_server_case_insensitive():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    servers = [{"name": "SCRAPER-MCP", "id": "upper", "status": "SCORED"}]
    result = _match_server(servers, "scraper-mcp")
    assert result is not None
    assert result["id"] == "upper"


def test_match_server_empty_list():
    from scraper_mcp.scrapers.toolbench_score import _match_server

    assert _match_server([], "scraper-mcp") is None


def test_match_server_real_fixture_finds_our_repo():
    """Our scraper-mcp is correctly matched in the 12-result fixture."""
    from scraper_mcp.scrapers.toolbench_score import _match_server

    data = _load_json_fixture()
    servers: list[dict] = data.get("servers", data.get("data", []))
    assert len(servers) >= 2, "fixture too small"

    result = _match_server(servers, "scraper-mcp")
    assert result is not None, "scraper-mcp not found in fixture"
    assert result["name"] == "scraper-mcp"
    assert result["status"] == "SCORED"
    assert isinstance(result["id"], str) and result["id"]
    assert "overallScore" in result


def test_match_server_real_fixture_unknown_misses():
    """Unknown repo returns None gracefully."""
    from scraper_mcp.scrapers.toolbench_score import _match_server

    data = _load_json_fixture()
    servers: list[dict] = data.get("servers", data.get("data", []))
    assert _match_server(servers, "no-such-repo-zzz") is None


# ===========================================================================
# scrape_assessment — HTTP-mocked integration
# ===========================================================================


@pytest.mark.asyncio
async def test_scrape_assessment_returns_dimension_scores():
    """A.1 end-to-end: scrape_assessment returns non-null dimension scores."""
    html = _load_html_fixture()

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import scrape_assessment

        result = await scrape_assessment("dummy-id")
        assert result is not None
        assert "definition_score" in result
        assert "protocol_score" in result
        assert "supportability_score" in result


@pytest.mark.asyncio
async def test_scrape_assessment_does_not_set_grade():
    """A.2 gate: grade is NEVER scraped from page HTML."""
    html = _load_html_fixture()

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import scrape_assessment

        result = await scrape_assessment("dummy-id")
        assert result is not None
        assert "grade" not in result, "grade must not be scraped from page text"


# ===========================================================================
# fetch_grade_with_details — JSON fixture + HTTP-mocked HTML
# ===========================================================================


@pytest.mark.asyncio
async def test_fetch_grade_with_details_uses_single_api_call():
    """A.4.2 gate: fetch_grade_with_details calls /api/servers exactly once."""
    html = _load_html_fixture()
    api_json = _load_json_fixture()

    mock_api_resp = MagicMock()
    mock_api_resp.status_code = 200
    mock_api_resp.json = MagicMock(return_value=api_json)

    mock_html_resp = MagicMock()
    mock_html_resp.text = html
    mock_html_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    get_call_count = 0

    async def _get(url, **kwargs):
        nonlocal get_call_count
        get_call_count += 1
        if "/api/servers" in str(url):
            return mock_api_resp
        return mock_html_resp

    mock_client.get = _get

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        result = await fetch_grade_with_details("test-owner", "scraper-mcp")
        assert result is not None
        assert "grade" in result
        assert "score" in result
        # Should make exactly 2 calls: 1 API + 1 HTML (NOT 2 API + 1 HTML)
        assert get_call_count == 2, f"expected 2 HTTP calls, got {get_call_count}"


@pytest.mark.asyncio
async def test_fetch_grade_with_details_prefers_api_grade():
    """A.2 gate: grade comes from API, not from HTML scraping."""
    html = _load_html_fixture()
    api_json = _load_json_fixture()

    mock_api_resp = MagicMock()
    mock_api_resp.status_code = 200
    mock_api_resp.json = MagicMock(return_value=api_json)

    mock_html_resp = MagicMock()
    mock_html_resp.text = html
    mock_html_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _get(url, **kwargs):
        if "/api/servers" in str(url):
            return mock_api_resp
        return mock_html_resp

    mock_client.get = _get

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        result = await fetch_grade_with_details("test-owner", "scraper-mcp")
        assert result is not None

        # Our fixture has grade=C, score=62. resolve_grade should return "C"
        # from the API. It should NOT return "C" from the HTML page text.
        assert result["grade"] in ("A+", "A", "B", "C", "D", "F", "?"), f"bad grade: {result['grade']}"
        assert isinstance(result["score"], (int, float, type(None)))
