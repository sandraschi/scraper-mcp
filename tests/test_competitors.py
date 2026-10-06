"""Tests for Phase 3 competitor tracking (tmp DB, mocked market search)."""

from __future__ import annotations

import pytest

from scraper_mcp import competitors


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    import scraper_mcp.analytics as analytics

    monkeypatch.setattr(analytics, "DB_DIR", tmp_path)
    monkeypatch.setattr(analytics, "DB_PATH", tmp_path / "test_grades.db")
    monkeypatch.setattr(competitors, "DB_DIR", tmp_path)
    monkeypatch.setattr(competitors, "DB_PATH", tmp_path / "test_grades.db")
    return tmp_path


def test_repo_keywords_drop_stopwords():
    assert competitors.repo_keywords("onenote-mcp") == ["onenote"]
    assert competitors.repo_keywords("virtualization-mcp") == ["virtualization"]
    assert competitors.repo_keywords("mcp") == []


def test_github_owner_repo_parse():
    assert competitors._github_owner_repo("https://github.com/danosb/onenote-mcp") == (
        "danosb",
        "onenote-mcp",
    )
    assert competitors._github_owner_repo("https://github.com/danosb/onenote-mcp.git") == (
        "danosb",
        "onenote-mcp",
    )
    assert competitors._github_owner_repo("https://example.com/x") is None
    assert competitors._github_owner_repo(None) is None


def test_discover_glama_filters_self():
    raw = {
        "related_servers": [
            {"owner": "sandraschi", "repo": "onenote-mcp", "name": "OneNote MCP", "url": "x"},
            {"owner": "danosb", "repo": "onenote-mcp", "name": "OneNote MCP", "url": "y"},
        ]
    }
    links = competitors.discover_glama(raw, "sandraschi", "onenote-mcp")
    assert len(links) == 1
    assert links[0]["owner"] == "danosb"
    assert links[0]["platform"] == "glama"
    assert competitors.discover_glama(None, "sandraschi", "onenote-mcp") == []


def test_discover_lobehub_excludes_own_and_unverifiable(monkeypatch):
    items = [
        {"name": "OneNote MCP", "github": {"url": "https://github.com/danosb/onenote-mcp"}},
        {"name": "Our listing", "github": {"url": "https://github.com/sandraschi/onenote-mcp"}},
        {"name": "No URL", "github": {}},
        {"name": " Dup", "github": {"url": "https://github.com/danosb/onenote-mcp"}},
    ]
    monkeypatch.setattr(competitors, "_lobehub_market_search", lambda query, page_size=40: items)
    neighbors = competitors.discover_lobehub("onenote-mcp", limit=5)
    assert len(neighbors) == 1
    assert neighbors[0]["owner"] == "danosb"
    assert neighbors[0]["platform"] == "lobehub"
    assert competitors.discover_lobehub("mcp") == []


def test_diff_grades_gaps_and_filch():
    mine = {
        "glama": {
            "grade": "C",
            "score": 3.0,
            "tool_details": [{"name": "our_tool"}, {"name": "shared_tool"}],
        }
    }
    theirs = {
        "glama": {
            "grade": "B",
            "score": 3.5,
            "tool_details": [{"name": "their_tool"}, {"name": "shared_tool"}],
        }
    }
    diff = competitors.diff_grades(mine, theirs)
    assert diff["gaps"][0]["gap"] == 0.5
    assert diff["gaps"][0]["platform"] == "glama"
    assert diff["filch"] == ["their_tool"]
    assert diff["leads"] == ["our_tool"]


def test_links_store_roundtrip(tmp_store):
    links = [{"owner": "danosb", "repo": "onenote-mcp", "name": "OneNote MCP", "platform": "glama"}]
    assert competitors.upsert_links("onenote-mcp", links) == 1
    assert competitors.upsert_links("onenote-mcp", links) == 0
    stored = competitors.list_links("onenote-mcp")
    assert len(stored) == 1
    assert stored[0]["comp_owner"] == "danosb"


async def test_tool_registered():
    from scraper_mcp.mcp import tools as _tools  # noqa: F401 - registration side effect
    from scraper_mcp.mcp.registry import mcp

    names = [tool.name for tool in await mcp.list_tools()]
    assert "scraper_competitors" in names
