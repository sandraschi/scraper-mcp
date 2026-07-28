"""Basic server startup and tool registration tests."""

import pytest


def test_server_import():
    """Server module imports without error."""
    from scraper_mcp.server import build_app

    assert build_app is not None


def test_config():
    """Config loads with correct ports."""
    from scraper_mcp.config import settings

    assert settings.port == 10998
    assert settings.webapp_port == 10999
    assert settings.transport == "http"


def test_scrapers_registry():
    """All 3 scrapers are registered."""
    from scraper_mcp.scrapers.engine import SCRAPERS

    assert "toolbench" in SCRAPERS
    assert "glama" in SCRAPERS
    assert "lobehub" in SCRAPERS
    assert len(SCRAPERS) == 3


@pytest.mark.asyncio
async def test_mcp_registration():
    """FastMCP tools are discoverable."""
    from scraper_mcp.mcp import tools as _  # noqa: F401
    from scraper_mcp.mcp.registry import mcp

    tools = await mcp.list_tools()
    assert len(tools) >= 6  # scraper_* + toolbench_guide
    names = {t.name for t in tools}
    assert "toolbench_guide" in names


def test_analytics_schema():
    """Analytics DB creates tables without error."""
    from scraper_mcp.analytics import _get_db, get_coverage_matrix, get_latest, upsert_grade

    conn = _get_db()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    assert "grades" in table_names
    assert "grade_history" in table_names
    conn.close()

    # Insert test data
    upsert_grade("toolbench", "test-owner", "test-repo", "A", 85.0, {"url": "https://example.com"})
    results = get_latest(platform="toolbench", repo="test-repo")
    assert len(results) == 1
    assert results[0]["grade"] == "A"

    matrix = get_coverage_matrix("test-owner")
    assert "test-repo" in matrix["repos"]


def test_toolbench_scraper_metadata():
    """ToolBench scraper has correct metadata."""
    from scraper_mcp.scrapers.engine import ToolBenchScraper

    s = ToolBenchScraper()
    assert s.id == "toolbench"
    assert "Arcade" in s.name
    assert s.base_url.startswith("https")
