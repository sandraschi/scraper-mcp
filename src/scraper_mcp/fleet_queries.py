"""Fleet-status queries - pure store reads shared by the fleet tool and the digest.

Split out from mcp/tools/fleet.py so non-MCP modules (digest.py) can use
them without importing the MCP registry (which would be circular:
tools/__init__ imports every tool module).
"""

from __future__ import annotations

import time

from .analytics import get_history, get_latest


def stale_entries(owner: str, max_days: int) -> list[dict]:
    """Repos whose stored grades are older than max_days (any platform)."""
    cutoff = time.time() - max_days * 86400
    stale: list[dict] = []
    for entry in get_latest(owner=owner):
        fetched = entry.get("fetched_at") or 0
        if fetched < cutoff:
            stale.append(
                {
                    "repo": entry["repo"],
                    "platform": entry["platform"],
                    "grade": entry["grade"],
                    "score": entry["score"],
                    "days_stale": round((time.time() - fetched) / 86400, 1) if fetched else -1,
                }
            )
    stale.sort(key=lambda item: item["days_stale"], reverse=True)
    return stale


def worst_tools(owner: str, limit: int) -> list[dict]:
    """Lowest-scoring tools fleet-wide across Glama + ToolBench raws."""
    scored: list[dict] = []
    for entry in get_latest(owner=owner):
        raw = entry.get("raw") or {}
        for tool in raw.get("tool_details") or []:
            score = tool.get("score", tool.get("tool_score"))
            if isinstance(score, (int, float)):
                scored.append(
                    {
                        "repo": entry["repo"],
                        "platform": entry["platform"],
                        "tool_name": tool.get("name", "?"),
                        "tool_score": score,
                        "tool_grade": tool.get("grade", "?"),
                    }
                )
    scored.sort(key=lambda item: item["tool_score"])
    return scored[:limit]


def grade_deltas(owner: str) -> list[dict]:
    """Grade/score changes between the last two history entries per repo+platform."""
    changes: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in get_latest(owner=owner):
        key = (entry["platform"], entry["repo"])
        if key in seen:
            continue
        seen.add(key)
        history = get_history(entry["platform"], owner, entry["repo"], limit=2)
        if len(history) < 2:
            continue
        new, old = history[0], history[1]
        if new.get("score") != old.get("score") or new.get("grade") != old.get("grade"):
            old_score = old.get("score") or 0
            new_score = new.get("score") or 0
            changes.append(
                {
                    "repo": entry["repo"],
                    "platform": entry["platform"],
                    "previous_grade": old.get("grade"),
                    "current_grade": new.get("grade"),
                    "previous_score": old.get("score"),
                    "current_score": new.get("score"),
                    "score_change": round(new_score - old_score, 2),
                }
            )
    changes.sort(key=lambda item: abs(item["score_change"]), reverse=True)
    return changes
