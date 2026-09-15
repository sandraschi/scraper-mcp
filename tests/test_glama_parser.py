"""Glama TDQS parser regression tests.

Runs against a committed HTML fixture (real page, fetched 2026-09-15, after
Glama's 2026-07 redesign) under tests/fixtures/glama/. No live HTTP calls.

If Glama redesigns again and these break: re-fetch a live page, diff the
class names against glama_score.py's docstring, and re-verify by hand before
assuming the data disappeared - it moved once already (from a dedicated
/score sub-page onto the main server page).
"""

import pathlib

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "glama"


def _load_fixture() -> str:
    return (FIXTURES / "server_virtualization-mcp_20260915.html").read_text(encoding="utf-8")


def test_parses_expected_tool_count():
    from scraper_mcp.scrapers.glama_score import parse_score_html

    result = parse_score_html(_load_fixture())
    assert result["tools"] == 9
    assert len(result["tool_details"]) == 9


def test_per_tool_grade_and_dimensions_present():
    from scraper_mcp.scrapers.glama_score import parse_score_html

    result = parse_score_html(_load_fixture())
    by_name = {t["name"]: t for t in result["tool_details"]}

    info_tool = by_name["info_tools"]
    assert info_tool["grade"] == "A"
    assert info_tool["score"] == 4.8
    for dim in ("purpose", "usage_guidelines", "behavior", "conciseness", "completeness"):
        assert dim in info_tool
        assert 0.0 < info_tool[dim] <= 5.0


def test_server_level_tdqs_extracted():
    from scraper_mcp.scrapers.glama_score import parse_score_html

    result = parse_score_html(_load_fixture())
    assert result["tdqs_grade"] in ("A", "B", "C", "D", "F")
    assert result["tdqs_mean"] > 0
    assert result["scored_at"]


def test_tdqs_min_derived_from_lowest_tool_not_missing_text():
    """The old 'Average X/5 ... Lowest: X/5' sentence is gone post-redesign;
    tdqs_min must come from the actual minimum per-tool score instead."""
    from scraper_mcp.scrapers.glama_score import parse_score_html

    result = parse_score_html(_load_fixture())
    tool_scores = [t["score"] for t in result["tool_details"] if t.get("score", 0) > 0]
    assert result["tdqs_min"] == min(tool_scores)


def test_no_stale_button_ulqjq_dependency():
    """Regression guard: the pre-redesign parser looked for <button
    class="ULqjq">, which no longer exists. Must not silently return zero
    tools on real post-redesign HTML."""
    from scraper_mcp.scrapers.glama_score import parse_score_html

    result = parse_score_html(_load_fixture())
    assert result["tools"] > 0, "parser regressed to the pre-redesign button-based selector"
