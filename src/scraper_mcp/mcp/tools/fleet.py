"""Fleet-status tools - ported from glama-status-mcp (archived 2026-10-06).

Same UX (staleness / worst_tools / deltas) running on the unified grades
store instead of the Glama-only database. Query logic lives in
scraper_mcp.fleet_queries (shared with the digest); this module is the thin
MCP wrapper.
"""

from typing import Annotated

from pydantic import Field

from ...fleet_queries import grade_deltas, stale_entries, worst_tools
from ..registry import mcp

FLEET_OWNER = "sandraschi"
STALE_DAYS = 7


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
        data = stale_entries(owner, max_days)
        message = f"{len(data)} stale repo-platform pairs (>{max_days}d)."
    elif op == "worst_tools":
        data = worst_tools(owner, max(1, min(limit, 200)))
        message = f"{len(data)} worst tools fleet-wide."
    elif op == "deltas":
        data = grade_deltas(owner)
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
