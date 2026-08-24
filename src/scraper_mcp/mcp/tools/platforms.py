"""Platform listing tool - discover available and pluggable grade platforms."""

from typing import Annotated

from pydantic import Field

from ...scrapers.engine import SCRAPERS
from ..registry import mcp


@mcp.tool(annotations={"readOnly": True})
async def scraper_platforms(
    operation: Annotated[str, Field(description="list | info | add")] = "list",
    platform_id: Annotated[str | None, Field(description="Platform ID for 'info' operation.")] = None,
) -> dict:
    """List available grade platforms and their capabilities.

    Platforms can be plugged in modularly - add new scrapers by subclassing BaseScraper.

    ## Return Format
    {"success": bool, "message": str, "data": {"platforms": [{"id": str, "name": str, "reassess_supported": bool}]}}

    ## Examples
    await scraper_platforms()
    await scraper_platforms(operation="info", platform_id="toolbench")
    """
    if operation == "list":
        platforms = [
            {"id": pid, "name": s.name, "reassess_supported": s.id == "toolbench"} for pid, s in SCRAPERS.items()
        ]
        return {
            "success": True,
            "message": f"{len(platforms)} platforms available.",
            "data": {"platforms": platforms},
        }
    if operation == "info" and platform_id:
        if platform_id in SCRAPERS:
            s = SCRAPERS[platform_id]
            return {
                "success": True,
                "message": s.name,
                "data": {
                    "id": s.id,
                    "name": s.name,
                    "base_url": s.base_url,
                    "reassess_supported": s.id == "toolbench",
                },
            }
        return {"success": False, "message": f"Unknown platform: {platform_id}", "data": {}}
    return {"success": True, "message": "Use operation='list' or operation='info'", "data": {}}
