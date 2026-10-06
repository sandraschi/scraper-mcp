"""Fleet-status tools - ported from glama-status-mcp (archived 2026-10-06).

Same UX (staleness / worst_tools / deltas) running on the unified grades
store instead of the Glama-only database. The full markdown digest stays a
Phase 4 job; these are the query primitives it will consume.
"""

import time
from typing import Annotated

from pydantic import Field

from ...analytics import get_history, get_latest
from ..registry import mcp

FLEET_OWNER = "sandraschi"
STALE_DAYS = 7


def _stale_entries(owner: str, max_days: int) -> list[dict]:
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


def _worst_tools(owner: str, limit: int) -> list[dict]:
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


def _deltas(owner: str) -> list[dict]:
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


@mcp.tool(annotations={"readOnly": True})
async def scraper_fleet(
    operation: Annotated[str, Field(description="staleness, worst_tools, or deltas.")] = "staleness",
    limit: Annotated[int, Field(description="Max rows for worst_tools.")] = 20,
    max_days: Annotated[int, Field(description="Staleness threshold in days.")] = STALE_DAYS,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Fleet-wide grade queries ported from glama-status-mcp (archived).

    Operations:
    - staleness: repos whose grades are older than max_days (need refresh).
    - worst_tools: lowest-scoring tools fleet-wide (docstring fix queue).
    - deltas: grade/score changes between the last two snapshots.

    ## Return Format
    {"success": bool, "operation": str, "data": [...], "count": int, "message": str}

    ## Examples
    await scraper_fleet(operation="staleness")
    await scraper_fleet(operation="worst_tools", limit=10)
    await scraper_fleet(operation="deltas")
    """
    op = (operation or "staleness").strip().lower()
    if op == "staleness":
        data = _stale_entries(owner, max_days)
        message = f"{len(data)} stale repo-platform pairs (>{max_days}d)."
    elif op == "worst_tools":
        data = _worst_tools(owner, max(1, min(limit, 200)))
        message = f"{len(data)} worst tools fleet-wide."
    elif op == "deltas":
        data = _deltas(owner)
        message = f"{len(data)} repos with grade changes."
    else:
        return {
            "success": False,
            "operation": operation,
            "data": [],
            "count": 0,
            "message": f"Unknown operation '{operation}'. Use staleness, worst_tools, or deltas.",
        }
    return {"success": True, "operation": op, "data": data, "count": len(data), "message": message}
