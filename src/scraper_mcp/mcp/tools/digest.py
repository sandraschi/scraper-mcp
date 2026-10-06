"""Digest tool - daily grades digest (Phase 4)."""

from typing import Annotated

from pydantic import Field

from ...digest import run_digest
from ..registry import mcp


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_digest(
    format: Annotated[str, Field(description="'markdown', 'json', or 'both'.")] = "both",
    notify: Annotated[
        bool, Field(description="Post new-competitor/aged-advice/failed-build events to aiwatcher.")
    ] = False,
) -> dict:
    """Build the daily grades digest from local stores (no network reads).

    Sections: grade distribution, score changes, worst tools, stale pairs,
    open/aged advice, pending releases, failed builds, new competitors.
    notify=True also pushes fleet events and records the run as notified
    (new items are diffed against the last notified run).

    ## Return Format
    {"success": bool, "message": str, "data": {...}, "markdown": str, "notified": [...]}

    ## Examples
    await scraper_digest()
    await scraper_digest(format="markdown", notify=True)
    """
    result = await run_digest(notify_flag=notify)
    payload: dict = {"success": True}
    want = (format or "both").strip().lower()
    if want in ("markdown", "both"):
        payload["markdown"] = result["markdown"]
    if want in ("json", "both"):
        payload["data"] = result["data"]
    else:
        payload["data"] = {"summary": "markdown only"}
    payload["notified"] = result["notified"]
    payload["message"] = f"Digest built, {len(result['notified'])} events sent."
    return payload
