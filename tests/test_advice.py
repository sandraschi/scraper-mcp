"""Tests for the Phase 2 advice engine + fleet-status port (tmp DB, no live calls)."""

from __future__ import annotations

import pytest

from scraper_mcp import advice
from scraper_mcp.analytics import upsert_grade


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """Redirect both depots (grades + advice share one SQLite file)."""
    import scraper_mcp.analytics as analytics

    monkeypatch.setattr(analytics, "DB_DIR", tmp_path)
    monkeypatch.setattr(analytics, "DB_PATH", tmp_path / "test_grades.db")
    monkeypatch.setattr(advice, "DB_DIR", tmp_path)
    monkeypatch.setattr(advice, "DB_PATH", tmp_path / "test_grades.db")
    return tmp_path


def _glama_raw() -> dict:
    return {
        "grade": "C",
        "score": 3.0,
        "tool_details": [
            {
                "name": "good_tool",
                "grade": "B",
                "score": 4.0,
                "purpose": 4.0,
                "usage_guidelines": 4.0,
                "behavior": 4.0,
                "parameters": 4.0,
                "conciseness": 4.0,
                "completeness": 4.0,
            },
            {
                "name": "weak_tool",
                "grade": "D",
                "score": 2.0,
                "purpose": 2.0,
                "usage_guidelines": 4.0,
                "behavior": 4.0,
                "parameters": 1.5,
                "conciseness": 4.0,
                "completeness": 4.0,
            },
        ],
    }


def _tb_raw() -> dict:
    return {
        "grade": "C",
        "score": 68.0,
        "top_issues": [
            "high Add description to tool",
            "low Single-responsibility bundles multiple unrelated operations",
        ],
        "tool_details": [{"name": "risky_tool", "tool_score": 91.0}],
    }


# ===========================================================================
# Glama advice
# ===========================================================================


def test_glama_worst_tool_and_weak_dims():
    items, worst = advice.build_glama_advice(_glama_raw(), "demo-mcp")
    assert worst[0]["name"] == "weak_tool"
    kinds = {(item["kind"], item["target"]) for item in items}
    assert ("tool", "weak_tool") in kinds
    assert ("dimension", "purpose") in kinds
    assert ("dimension", "parameters") in kinds
    # Healthy dims produce no items.
    assert not [item for item in items if item["target"] in ("behavior", "conciseness")]
    purp = next(item for item in items if item["target"] == "purpose")
    assert purp["severity"] == "high"
    assert "TOOL_DESIGN_STANDARDS" in purp["fix_ref"]


def test_glama_empty_raw():
    assert advice.build_glama_advice(None, "demo-mcp") == ([], [])


# ===========================================================================
# ToolBench advice + shared map
# ===========================================================================


def test_toolbench_maps_issues_skips_exceptions():
    items, worst, skipped = advice.build_toolbench_advice(_tb_raw(), "demo-mcp")
    assert len(items) == 1
    assert items[0]["severity"] == "high"
    assert "TOOL_DESIGN_STANDARDS" in items[0]["fix_ref"]
    assert len(skipped) == 1
    assert worst[0]["name"] == "risky_tool"


def test_shared_map_matches_improvement_tool():
    """Single source of truth: improvement.py imports from advice.py."""
    from scraper_mcp.mcp.tools import improvement

    assert improvement._classify_issue("high Add description to tool") == advice.classify_issue(
        "high Add description to tool"
    )
    assert improvement._is_fleet_exception("bundles multiple unrelated operations") is True


# ===========================================================================
# advice store
# ===========================================================================


def test_upsert_list_resolve(tmp_store):
    items, _ = advice.build_glama_advice(_glama_raw(), "demo-mcp")
    assert advice.upsert_advice(items) == len(items)
    assert advice.upsert_advice(items) == 0  # idempotent re-run refreshes, adds nothing
    assert len(advice.list_advice(repo="demo-mcp")) == len(items)
    assert len(advice.list_advice(repo="demo-mcp", status="open")) == len(items)
    first_id = advice.list_advice(repo="demo-mcp")[0]["id"]
    assert advice.resolve_advice(first_id) is True
    assert advice.resolve_advice(first_id) is False  # already done
    assert len(advice.list_advice(repo="demo-mcp", status="open")) == len(items) - 1


# ===========================================================================
# fleet-status port (seeded grades store)
# ===========================================================================


def test_fleet_staleness_and_deltas(tmp_store):
    upsert_grade("glama", "sandraschi", "old-mcp", "C", 3.0, _glama_raw())
    upsert_grade("glama", "sandraschi", "new-mcp", "B", 4.0, _glama_raw())
    upsert_grade("glama", "sandraschi", "new-mcp", "A", 4.5, _glama_raw())

    from scraper_mcp.mcp.tools.fleet import _deltas, _stale_entries, _worst_tools

    stale = _stale_entries("sandraschi", max_days=0)
    assert {row["repo"] for row in stale} == {"old-mcp", "new-mcp"}

    fresh = _stale_entries("sandraschi", max_days=365)
    assert fresh == []

    deltas = _deltas("sandraschi")
    assert len(deltas) == 1
    assert deltas[0]["repo"] == "new-mcp"
    assert deltas[0]["previous_grade"] == "B"
    assert deltas[0]["current_grade"] == "A"

    worst = _worst_tools("sandraschi", limit=10)
    assert worst[0]["tool_name"] == "weak_tool"
    assert worst[0]["tool_score"] == 2.0


async def test_tools_registered():
    from scraper_mcp.mcp import tools as _tools  # noqa: F401 - registration side effect
    from scraper_mcp.mcp.registry import mcp

    names = [tool.name for tool in await mcp.list_tools()]
    assert "scraper_advice" in names
    assert "scraper_fleet" in names
