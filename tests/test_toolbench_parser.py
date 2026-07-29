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
# A.5 — _find_candidates (replaces _match_server)
# ===========================================================================


def test_find_candidates_exact_name():
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    servers = [{"name": "scraper-mcp", "id": "abc", "status": "SCORED"}]
    result = _find_candidates(servers, "scraper-mcp")
    assert len(result) == 1
    assert result[0]["id"] == "abc"


def test_find_candidates_prefers_scored():
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    servers = [
        {"name": "scraper-mcp", "id": "unscored", "status": "UNSCORED"},
        {"name": "scraper-mcp", "id": "scored", "status": "SCORED"},
    ]
    result = _find_candidates(servers, "scraper-mcp")
    assert len(result) == 2
    assert result[0]["id"] == "scored"


def test_find_candidates_no_match_returns_empty():
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    servers = [{"name": "unrelated", "id": "nope"}]
    assert _find_candidates(servers, "scraper-mcp") == []


def test_find_candidates_case_insensitive():
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    servers = [{"name": "SCRAPER-MCP", "id": "upper", "status": "SCORED"}]
    result = _find_candidates(servers, "scraper-mcp")
    assert len(result) == 1
    assert result[0]["id"] == "upper"


def test_find_candidates_empty_list():
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    assert _find_candidates([], "scraper-mcp") == []


def test_find_candidates_real_fixture_finds_our_repo():
    """Our scraper-mcp is findable in the real fixture with 12 results."""
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    data = _load_json_fixture()
    servers: list[dict] = data.get("servers", data.get("data", []))
    assert len(servers) >= 2, "fixture too small"

    candidates = _find_candidates(servers, "scraper-mcp")
    assert len(candidates) >= 2, "should find multiple scraper-mcp entries"
    # First candidate should be SCORED with highest score
    assert candidates[0]["status"] == "SCORED"
    assert isinstance(candidates[0]["id"], str) and candidates[0]["id"]


def test_find_candidates_real_fixture_unknown_misses():
    """Unknown repo returns empty list gracefully."""
    from scraper_mcp.scrapers.toolbench_score import _find_candidates

    data = _load_json_fixture()
    servers: list[dict] = data.get("servers", data.get("data", []))
    assert _find_candidates(servers, "no-such-repo-zzz") == []


# ===========================================================================
# Owner verification
# ===========================================================================


def test_owner_from_soup_real_fixture():
    """Extract GitHub owner from the fixture assessment page."""
    from bs4 import BeautifulSoup

    from scraper_mcp.scrapers.toolbench_score import _owner_from_soup

    html = _load_html_fixture()
    soup = BeautifulSoup(html, "lxml")
    owner = _owner_from_soup(soup)
    assert owner is not None, "should find owner in fixture"
    assert owner.lower() == "aparajithn", f"expected aparajithn, got {owner}"


def test_owner_from_soup_no_link():
    from bs4 import BeautifulSoup

    from scraper_mcp.scrapers.toolbench_score import _owner_from_soup

    soup = BeautifulSoup("<html><body>no link here</body></html>", "lxml")
    assert _owner_from_soup(soup) is None


# ===========================================================================
# Blocker 2 — dimension reconciliation
# ===========================================================================


def test_dimensions_reconcile_exact():
    from scraper_mcp.scrapers.toolbench_score import _dimensions_reconcile

    # Our fixture: DQ=79, Protocol=80, Support=38 → overall=67 (66.9 rounded)
    assert _dimensions_reconcile(79, 80, 38, 67) is True


def test_dimensions_reconcile_exact_calculation():
    from scraper_mcp.scrapers.toolbench_score import _dimensions_reconcile

    # 0.5*80 + 0.2*80 + 0.3*80 = 80
    assert _dimensions_reconcile(80, 80, 80, 80) is True


def test_dimensions_reconcile_mismatch():
    from scraper_mcp.scrapers.toolbench_score import _dimensions_reconcile

    # 0.5*72 + 0.2*72 + 0.3*72 = 72, not 62
    assert _dimensions_reconcile(72, 72, 72, 62) is False


def test_dimensions_reconcile_none_rejected():
    from scraper_mcp.scrapers.toolbench_score import _dimensions_reconcile

    assert _dimensions_reconcile(None, 80, 38, 67) is False
    assert _dimensions_reconcile(79, None, 38, 67) is False
    assert _dimensions_reconcile(79, 80, None, 67) is False
    assert _dimensions_reconcile(79, 80, 38, None) is False


def test_dimensions_reconcile_within_tolerance():
    from scraper_mcp.scrapers.toolbench_score import _dimensions_reconcile

    # 0.5*79 + 0.2*80 + 0.3*38 = 66.9, overall=67, diff=0.1 < tol=1.5
    assert _dimensions_reconcile(79, 80, 38, 67) is True
    # 0.5*78 + 0.2*80 + 0.3*39 = 66.7, overall=67, diff=0.3 < tol=1.5
    assert _dimensions_reconcile(78, 80, 39, 67) is True


# ===========================================================================
# GAP 7 — tool_details schema
# ===========================================================================


def test_tool_details_uses_tool_score():
    """GAP 7: tool_detail entries use 'tool_score', not 'risk_score'."""
    from bs4 import BeautifulSoup

    from scraper_mcp.scrapers.toolbench_score import _parse_assessment_data

    html = _load_html_fixture()
    soup = BeautifulSoup(html, "lxml")
    result = _parse_assessment_data(soup, "https://example.com", "dummy-id")
    assert "tool_details" in result
    for tool in result["tool_details"]:
        assert "tool_score" in tool, f"missing tool_score in {tool}"
        assert "risk_score" not in tool, f"old key risk_score still present in {tool}"


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
    api_json = _load_json_fixture()

    mock_api_resp = MagicMock()
    mock_api_resp.status_code = 200
    mock_api_resp.json = MagicMock(return_value=api_json)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    get_call_count = 0

    async def _get(url, **kwargs):
        nonlocal get_call_count
        get_call_count += 1
        return mock_api_resp

    mock_client.get = _get

    # Pre-populate owner cache so no page fetch is needed
    from scraper_mcp.scrapers.toolbench_score import _server_owner_cache

    _server_owner_cache.clear()
    servers = api_json.get("servers", api_json.get("data", []))
    for s in servers:
        if s.get("name", "").lower() == "scraper-mcp":
            _server_owner_cache[s["id"]] = "test-owner"

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        result = await fetch_grade_with_details("test-owner", "scraper-mcp")
        assert result is not None
        assert "grade" in result
        assert "score" in result
        # Only 1 API call — no page fetch (owner was cached)
        assert get_call_count == 1, f"expected 1 HTTP call, got {get_call_count}"
        _server_owner_cache.clear()


@pytest.mark.asyncio
async def test_fetch_grade_with_details_prefers_api_grade():
    """A.2 gate: grade comes from API, not from HTML scraping."""
    api_json = _load_json_fixture()

    mock_api_resp = MagicMock()
    mock_api_resp.status_code = 200
    mock_api_resp.json = MagicMock(return_value=api_json)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _get(url, **kwargs):
        return mock_api_resp

    mock_client.get = _get

    # Pre-populate owner cache
    from scraper_mcp.scrapers.toolbench_score import _server_owner_cache

    _server_owner_cache.clear()
    servers = api_json.get("servers", api_json.get("data", []))
    for s in servers:
        if s.get("name", "").lower() == "scraper-mcp":
            _server_owner_cache[s["id"]] = "test-owner"

    with patch("scraper_mcp.scrapers.toolbench_score.httpx.AsyncClient", return_value=mock_client):
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        result = await fetch_grade_with_details("test-owner", "scraper-mcp")
        assert result is not None

        assert result["grade"] in ("A+", "A", "B", "C", "D", "F", "?"), f"bad grade: {result['grade']}"
        assert isinstance(result["score"], (int, float, type(None)))
        _server_owner_cache.clear()
