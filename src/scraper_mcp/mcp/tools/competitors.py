"""Competitor tool - diff ours against rival MCP servers (Phase 3)."""

from typing import Annotated

from pydantic import Field

from ...analytics import get_latest, upsert_grade
from ...competitors import (
    MAX_COMPETITORS,
    diff_grades,
    discover_glama,
    discover_lobehub,
    list_links,
    upsert_links,
)
from ...scrapers.engine import refresh_single
from ..registry import mcp

FLEET_OWNER = "sandraschi"


def _competitor_markdown(repo: str, comparisons: list[dict]) -> str:
    lines = [f"## Competitors: {repo}", ""]
    for comp in comparisons:
        name = comp["link"].get("name", comp["link"]["repo"])
        lines.append(f"### {name} ({comp['link']['owner']}/{comp['link']['repo']})")
        for gap in comp["diff"]["gaps"]:
            mine = gap["mine"]
            theirs = gap["theirs"]
            flag = "BEHIND" if gap["gap"] > 0 else "AHEAD"
            lines.append(
                f"- {gap['platform']}: us {mine['grade']} ({mine['score']}) vs"
                f" them {theirs['grade']} ({theirs['score']}) [{flag}]"
            )
        if comp["diff"]["filch"]:
            lines.append(f"- Filch ({len(comp['diff']['filch'])}): {', '.join(comp['diff']['filch'][:8])}")
        if comp["diff"]["leads"]:
            lines.append(f"- Leads ({len(comp['diff']['leads'])}): {', '.join(comp['diff']['leads'][:8])}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_competitors(
    repo: Annotated[str, Field(description="Our repo name, e.g. 'onenote-mcp'.")],
    platform: Annotated[
        str, Field(description="'glama', 'lobehub', or 'all'. ToolBench has no neighbor concept.")
    ] = "all",
    limit: Annotated[int, Field(description="Max competitors to refresh+diff (1-5).")] = 5,
    refresh: Annotated[bool, Field(description="Refresh grades live first (slower, polite).")] = True,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Diff our repo against rival MCP servers found on Glama + LobeHub.

    Discovery: Glama Related-server links from the stored grade (needs a
    prior refresh) plus live LobeHub market neighbors by repo keywords
    (owner-verified, our own listing excluded). Each rival gets a full
    refresh_single whose grades persist under its own owner, then a diff:
    per-platform grade gaps plus feature-filch list (their tools we lack)
    and our lead list. Links persist in competitor_links.

    ## Return Format
    {"success": bool, "message": str, "data": {"repo": str, "competitors": [...], "markdown": str}}

    ## Examples
    await scraper_competitors(repo="onenote-mcp")
    await scraper_competitors(repo="onenote-mcp", platform="glama", refresh=False)
    """
    wanted = [platform] if platform in ("glama", "lobehub") else ["glama", "lobehub"]
    cap = max(1, min(limit, MAX_COMPETITORS))

    mine: dict = {}
    if refresh:
        mine = await refresh_single(owner, repo)
        for pid, row in mine.items():
            if row:
                upsert_grade(pid, owner, repo, row.get("grade"), row.get("score"), row)
    else:
        for pid in ("glama", "toolbench", "lobehub"):
            rows = get_latest(platform=pid, owner=owner, repo=repo)
            if rows:
                mine[pid] = rows[0]["raw"] or {}

    links: list[dict] = []
    if "glama" in wanted:
        raw = None
        if refresh:
            raw = mine.get("glama") or {}
        else:
            rows = get_latest(platform="glama", owner=owner, repo=repo)
            raw = rows[0]["raw"] if rows else None
        links.extend(discover_glama(raw, owner, repo))
    if "lobehub" in wanted and refresh:
        # Market search is live-only; without refresh there is nothing new.
        links.extend(discover_lobehub(repo, owner, limit=cap))

    links = links[:cap]
    upsert_links(repo, links)

    comparisons = []
    for link in links:
        theirs: dict = {}
        if refresh:
            theirs = await refresh_single(link["owner"], link["repo"])
            for pid, row in theirs.items():
                if row:
                    upsert_grade(pid, link["owner"], link["repo"], row.get("grade"), row.get("score"), row)
        else:
            for pid in ("glama", "toolbench", "lobehub"):
                rows = get_latest(platform=pid, owner=link["owner"], repo=link["repo"])
                if rows:
                    theirs[pid] = rows[0]["raw"] or {}
        comparisons.append({"link": link, "diff": diff_grades(mine, theirs)})

    known_links = list_links(repo)
    return {
        "success": True,
        "message": f"{repo}: {len(comparisons)} competitors compared.",
        "data": {
            "repo": repo,
            "competitors": comparisons,
            "known_links": known_links,
            "markdown": _competitor_markdown(repo, comparisons),
        },
    }
