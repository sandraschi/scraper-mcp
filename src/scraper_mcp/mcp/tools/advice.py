"""Advice tool - per-repo prioritized fixes from Glama TDQS + ToolBench, persisted."""

from typing import Annotated

from pydantic import Field

from ...advice import build_glama_advice, build_toolbench_advice, upsert_advice
from ...analytics import get_latest, upsert_grade
from ...scrapers.engine import refresh_single
from ..registry import mcp

FLEET_OWNER = "sandraschi"


def _advice_markdown(repo: str, items: list[dict], worst_tools: list[dict], skipped: list[str]) -> str:
    lines = [f"## Advice: {repo}", f"**Open items:** {len(items)}", ""]
    for item in items:
        lines.append(f"### [{item['severity'].upper()}] {item['kind']}: {item['target']}")
        lines.append(item["text"])
        lines.append(f"Fix: {item['fix_ref']}")
        lines.append("")
    if worst_tools:
        lines.append("### Worst tools")
        for tool in worst_tools[:5]:
            name = tool.get("name", "?")
            score = tool.get("score", tool.get("tool_score", "?"))
            lines.append(f"- {name}: {score}")
        lines.append("")
    if skipped:
        lines.append(f"### Skipped fleet exceptions ({len(skipped)})")
        for text in skipped[:5]:
            lines.append(f"- {text[:100]}")
    return "\n".join(lines)


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_advice(
    repo: Annotated[str, Field(description="Repo name, e.g. 'email-mcp'.")],
    platform: Annotated[str, Field(description="'glama', 'toolbench', or 'all'.")] = "all",
    refresh: Annotated[bool, Field(description="Fetch live grades first.")] = True,
    persist: Annotated[bool, Field(description="Persist items to the advice store.")] = True,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Build a prioritized, persisted fix list for one repo from stored grades.

    Glama: worst tools (lowest TDQS) + weakest of the 6 TDQS dimensions,
    each mapped to a concrete docstring fix. ToolBench: top issues mapped
    to TOOL_DESIGN_STANDARDS sections (fleet exceptions skipped). Items
    persist with open status so the digest can track resolution; re-running
    refreshes them. Use scraper_refresh() first for fresh grades, or
    refresh=True here.

    ## Return Format
    {"success": bool, "message": str, "data": {"repo": str, "items": [...],
      "worst_tools": [...], "skipped_exceptions": [...], "persisted": int, "markdown": str}}

    ## Examples
    await scraper_advice(repo="email-mcp")
    await scraper_advice(repo="onenote-mcp", platform="glama", refresh=False)
    """
    wanted = [platform] if platform in ("glama", "toolbench") else ["glama", "toolbench"]
    if refresh:
        await refresh_single(owner, repo)

    all_items: list[dict] = []
    worst_tools: list[dict] = []
    skipped: list[str] = []
    grades: dict[str, dict] = {}
    for pid in wanted:
        rows = get_latest(platform=pid, owner=owner, repo=repo)
        raw = rows[0]["raw"] if rows else None
        if pid == "glama":
            items, worst = build_glama_advice(raw, repo)
            all_items.extend(items)
            worst_tools.extend([{**t, "platform": pid} for t in worst])
            if raw:
                grades[pid] = {"grade": raw.get("grade"), "score": raw.get("score")}
        else:
            items, worst, skip = build_toolbench_advice(raw, repo)
            all_items.extend(items)
            worst_tools.extend([{**t, "platform": pid} for t in worst])
            skipped.extend(skip)
            if raw:
                grades[pid] = {"grade": raw.get("grade"), "score": raw.get("score")}

    # Persist second: refresh_single may have stored fresh grades above.
    for pid in wanted:
        rows = get_latest(platform=pid, owner=owner, repo=repo)
        if rows and rows[0]["raw"]:
            upsert_grade(pid, owner, repo, rows[0]["grade"], rows[0]["score"], rows[0]["raw"])

    persisted = upsert_advice(all_items) if persist else 0
    return {
        "success": True,
        "message": f"Advice for {repo}: {len(all_items)} open items ({persisted} new).",
        "data": {
            "repo": repo,
            "grades": grades,
            "items": all_items,
            "worst_tools": worst_tools[:10],
            "skipped_exceptions": skipped,
            "persisted": persisted,
            "markdown": _advice_markdown(repo, all_items, worst_tools, skipped),
        },
    }
