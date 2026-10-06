"""LobeHub criticism-capture unit tests.

Runs against inline records modeled on the live `@lobehub/market-cli mcp
search --output json` response for sandraschi/pywinauto-mcp (captured
2026-09-17). No live CLI calls, no HTTP.
"""

from unittest.mock import patch

import pytest


def _pywinauto_record() -> dict:
    """Trimmed shape of the real market record: listed but unvalidated,
    unclaimed, zero indexed tools/prompts/resources, zero ratings."""
    return {
        "identifier": "sandraschi-pywinauto-mcp",
        "name": "PyWinAuto MCP",
        "description": "Windows UI automation (PyWinAuto): desktop control.",
        "capabilities": {"prompts": False, "resources": False, "tools": False},
        "github": {"url": "https://github.com/sandraschi/pywinauto-mcp", "stars": 16},
        "installCount": 7,
        "isClaimed": False,
        "isValidated": False,
        "manifestUrl": "https://market.lobehub.com/api/v1/plugins/sandraschi-pywinauto-mcp/manifest",
        "promptsCount": 0,
        "ratingCount": 0,
        "resourcesCount": 0,
        "toolsCount": 0,
    }


def _healthy_record() -> dict:
    """Validated, claimed, fully indexed record with ratings."""
    return {
        "identifier": "acme-good-mcp",
        "name": "Good MCP",
        "description": "Does everything well.",
        "capabilities": {"prompts": True, "resources": True, "tools": True},
        "github": {"url": "https://github.com/acme/good-mcp", "stars": 500},
        "installCount": 2345,
        "isClaimed": True,
        "isValidated": True,
        "manifestUrl": "https://market.lobehub.com/api/v1/plugins/acme-good-mcp/manifest",
        "promptsCount": 3,
        "ratingAverage": 4.5,
        "ratingCount": 89,
        "resourcesCount": 2,
        "toolsCount": 12,
    }


# ===========================================================================
# _select_lobehub_item — owner-verified matching (A.5 lesson)
# ===========================================================================


def test_select_exact_match():
    from scraper_mcp.scrapers.engine import _select_lobehub_item

    items = [{"github": {"url": "https://github.com/other/unrelated"}}, _pywinauto_record()]
    found = _select_lobehub_item("sandraschi", "pywinauto-mcp", items)
    assert found is not None
    assert found["identifier"] == "sandraschi-pywinauto-mcp"


def test_select_rejects_name_collision():
    """pywinauto-mcp-fork must not match pywinauto-mcp (A.5 regression)."""
    from scraper_mcp.scrapers.engine import _select_lobehub_item

    fork = {"github": {"url": "https://github.com/sandraschi/pywinauto-mcp-fork"}}
    assert _select_lobehub_item("sandraschi", "pywinauto-mcp", [fork]) is None


def test_select_case_insensitive():
    from scraper_mcp.scrapers.engine import _select_lobehub_item

    item = {"github": {"url": "https://github.com/SandraSchi/PyWinAuto-MCP"}}
    assert _select_lobehub_item("sandraschi", "pywinauto-mcp", [item]) is not None


def test_select_no_match_returns_none():
    from scraper_mcp.scrapers.engine import _select_lobehub_item

    assert _select_lobehub_item("sandraschi", "no-such-repo-zzz", [_pywinauto_record()]) is None
    assert _select_lobehub_item("sandraschi", "pywinauto-mcp", []) is None
    assert _select_lobehub_item("sandraschi", "pywinauto-mcp", [{"name": "no-github-key"}]) is None


# ===========================================================================
# _lobehub_criticisms — the platform's detailed criticism, captured
# ===========================================================================


def test_criticisms_flag_real_gaps():
    from scraper_mcp.scrapers.engine import _lobehub_criticisms

    issues = _lobehub_criticisms(_pywinauto_record())
    assert "not LobeHub-validated" in issues
    assert "listing unclaimed (claim it to manage updates)" in issues
    assert "no tools indexed on LobeHub" in issues
    assert "no prompts defined" in issues
    assert "no resources defined" in issues
    assert "no ratings yet" in issues


def test_criticisms_healthy_record_is_empty():
    from scraper_mcp.scrapers.engine import _lobehub_criticisms

    assert _lobehub_criticisms(_healthy_record()) == []


def test_criticisms_missing_description():
    from scraper_mcp.scrapers.engine import _lobehub_criticisms

    record = _healthy_record()
    record["description"] = "   "
    assert "missing description" in _lobehub_criticisms(record)


# ===========================================================================
# _lobehub_row — grade stays N/A, criticism rides top_issues
# ===========================================================================


def test_row_grade_na_score_from_rating():
    from scraper_mcp.scrapers.engine import _lobehub_row

    row = _lobehub_row("good-mcp", _healthy_record())
    assert row["grade"] == "N/A"  # LobeHub publishes criticism, not letter grades
    assert row["score"] == 4.5
    assert row["status"] == "indexed"
    assert row["tools"] == 12
    assert row["top_issues"] == []
    assert row["server_id"] == "acme-good-mcp"


def test_row_unrated_score_none_criticism_kept():
    from scraper_mcp.scrapers.engine import _lobehub_row

    row = _lobehub_row("pywinauto-mcp", _pywinauto_record())
    assert row["grade"] == "N/A"
    assert row["score"] is None
    assert "no prompts defined" in row["top_issues"]


# ===========================================================================
# fetch_grade — market-cli first, legacy probe as fallback
# ===========================================================================


@pytest.mark.asyncio
async def test_fetch_grade_uses_market_record():
    """Market hit returns the criticism row without touching HTTP."""
    from scraper_mcp.scrapers.engine import LobeHubScraper

    with patch(
        "scraper_mcp.scrapers.engine._lobehub_market_search",
        return_value=[_pywinauto_record()],
    ):
        row = await LobeHubScraper().fetch_grade("sandraschi", "pywinauto-mcp")
    assert row is not None
    assert row["grade"] == "N/A"
    assert "not LobeHub-validated" in row["top_issues"]


@pytest.mark.asyncio
async def test_fetch_grade_miss_returns_none():
    """No market match and dead page probe returns None (no phantom rows)."""
    from unittest.mock import AsyncMock, MagicMock

    from scraper_mcp.scrapers.engine import LobeHubScraper

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = ""

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with (
        patch("scraper_mcp.scrapers.engine._lobehub_market_search", return_value=[]),
        patch("scraper_mcp.scrapers.engine._fetch_with_obscura", return_value=None),
        patch("scraper_mcp.scrapers.engine.httpx.AsyncClient", return_value=mock_client),
    ):
        row = await LobeHubScraper().fetch_grade("sandraschi", "no-such-repo-zzz")
    assert row is None
