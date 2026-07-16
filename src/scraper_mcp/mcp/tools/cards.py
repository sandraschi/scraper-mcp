"""Prefab UI cards for list/status tools — @mcp.tool(app=True)."""

from typing import Annotated, Any

from prefab_ui import PrefabApp
from prefab_ui.components import Heading, Row
from pydantic import Field

from ...analytics import get_coverage_matrix, get_latest
from ...scrapers.engine import SCRAPERS
from ..registry import mcp
from ..tools.coverage import FLEET_OWNER


@mcp.tool(app=True, annotations={"readOnly": True})
async def show_matrix_card(
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict[str, Any]:
    """Show fleet coverage matrix as a rich Prefab card.

    Renders repos vs platforms coverage with grade badges in an in-chat card.

    ## Return Format
    {"success": bool, "message": str, "content": str (fallback text)}

    ## Examples
    await show_matrix_card()
    """
    matrix = get_coverage_matrix(owner)
    with PrefabApp(title="Fleet Coverage Matrix") as _:
        Heading(f"{matrix['repo_count']} repos across {len(matrix['platforms'])} platforms")
        for repo_name, platforms in sorted(matrix["repos"].items()):
            bits = []
            for pid in matrix["platforms"]:
                g = platforms.get(pid)
                bits.append(f"{pid}: {g.get('grade', '?')}" if g else f"{pid}: --")
            Row(label=repo_name, value=" | ".join(bits))
    return {
        "success": True,
        "message": f"{matrix['repo_count']} repos across {len(matrix['platforms'])} platforms.",
        "content": f"Matrix: {matrix['repo_count']} repos, {len(matrix['platforms'])} platforms.",
    }


@mcp.tool(app=True, annotations={"readOnly": True})
async def show_status_card() -> dict[str, Any]:
    """Show server and platform health as a rich Prefab card.

    Renders platform status, grade distribution, and staleness info.

    ## Return Format
    {"success": bool, "message": str, "content": str (fallback text)}

    ## Examples
    await show_status_card()
    """
    matrix = get_coverage_matrix("sandraschi")
    latest = get_latest(owner="sandraschi")

    with PrefabApp(title="Scraper MCP Status") as _:
        Heading(f"{len(SCRAPERS)} platforms, {matrix['repo_count']} repos")
        for pid, scraper in SCRAPERS.items():
            entries = [e for e in latest if e["platform"] == pid]
            repos_found = len({e["repo"] for e in entries})
            Row(label=scraper.name, value=f"{repos_found} repos tracked")
    return {
        "success": True,
        "message": f"{len(SCRAPERS)} platforms, {matrix['repo_count']} repos.",
        "content": f"Status: {len(SCRAPERS)} platforms, {matrix['repo_count']} repos.",
    }
