"""Coverage & grade tools — portmanteau for fleet repo monitoring."""

from typing import Annotated

from pydantic import Field

from ...analytics import get_coverage_matrix, get_history, get_latest, upsert_grade
from ...scrapers.engine import SCRAPERS, refresh_all, refresh_single
from ..registry import mcp

try:
    from .suggest import _alert_if_drop
except ImportError:
    async def _alert_if_drop(*args, **kwargs): return None

FLEET_OWNER = "sandraschi"


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_refresh(
    owner: Annotated[str, Field(description="GitHub owner to scan. Default: sandraschi.")] = FLEET_OWNER,
    repo: Annotated[str | None, Field(description="Single repo to refresh. Omit to scan all.")] = None,
) -> dict:
    """Refresh grades across all platforms (ToolBench, Glama, LobeHub) for fleet repos.

    Fetches current grades from each platform and persists to local grade store.
    Use before viewing coverage matrix to ensure fresh data.

    ## Return Format
    {"success": bool, "message": str, "data": {"refreshed": int, "platforms": {platform_id: {"found": int}}}}

    ## Examples
    await scraper_refresh()
    await scraper_refresh(repo="email-mcp")
    """
    if repo:
        results = await refresh_single(owner, repo)
        count = 0
        alerts = []
        for pid, r in results.items():
            if r:
                old = get_latest(platform=pid, owner=owner, repo=repo)
                old_grade = old[0]["grade"] if old else None
                upsert_grade(pid, owner, repo, r.get("grade"), r.get("score"), r)
                alert = await _alert_if_drop(repo, pid, old_grade, r.get("grade"))
                if alert:
                    alerts.append(alert)
                count += 1
        return {
            "success": True,
            "message": f"Refreshed {repo}: found on {count}/3 platforms.",
            "data": {"refreshed": count, "alerts": alerts} if alerts else {"refreshed": count},
        }

    results = await refresh_all(owner, None)
    total = 0
    summary = {}
    alerts = []
    for pid, repos in results.items():
        for r in repos:
            old = get_latest(platform=pid, owner=owner, repo=r["repo"])
            old_grade = old[0]["grade"] if old else None
            upsert_grade(pid, owner, r["repo"], r.get("grade"), r.get("score"), r)
            alert = await _alert_if_drop(r["repo"], pid, old_grade, r.get("grade"))
            if alert:
                alerts.append(alert)
            total += 1
        summary[pid] = {"found": len(repos)}

    return {
        "success": True,
        "message": f"Refreshed {total} repo-grade entries across {len(summary)} platforms.",
        "data": {"refreshed": total, "platforms": summary, "alerts": alerts} if alerts else {"refreshed": total, "platforms": summary},
    }


@mcp.tool(annotations={"readOnly": True})
async def scraper_matrix(
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Show coverage matrix: which sandraschi repos are indexed on which platforms, with grades.

    Reports the grade letter, numeric score, and last-check timestamp per repo per platform.
    Gaps indicate repos not yet discovered by a platform's scraper.

    ## Return Format
    {"success": bool, "message": str, "data": {"repos": {repo_name: {platform_id: {"grade": str, "score": float}}}, "platforms": [...], "repo_count": int}}

    ## Examples
    await scraper_matrix()
    await scraper_matrix(owner="sandraschi")
    """
    matrix = get_coverage_matrix(owner)
    return {
        "success": True,
        "message": f"{matrix['repo_count']} repos tracked across {len(matrix['platforms'])} platforms.",
        "data": matrix,
    }


@mcp.tool(annotations={"readOnly": True})
async def scraper_repo(
    repo: Annotated[str, Field(description="Repo name, e.g. 'email-mcp'.")],
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Get detailed grade report for a single repo across all platforms.

    Includes current grades, score breakdown, history delta, and platform URLs.

    ## Return Format
    {"success": bool, "message": str, "data": {"repo": str, "grades": {platform_id: dict, ...}, "history": {platform_id: [...]}}}

    ## Examples
    await scraper_repo(repo="email-mcp")
    await scraper_repo(repo="fleet-agent-mcp")
    """
    latest = get_latest(owner=owner, repo=repo)
    if not latest:
        return {
            "success": False,
            "message": f"No grade data for {repo}. Run scraper_refresh() first.",
            "data": {"repo": repo, "grades": {}, "history": {}},
        }

    grades = {}
    histories = {}
    for entry in latest:
        pid = entry["platform"]
        grades[pid] = {
            "grade": entry["grade"],
            "score": entry["score"],
            "url": entry.get("raw", {}).get("url", ""),
            "tools": entry.get("raw", {}).get("tools", 0),
            "fetched_at": entry["fetched_at"],
        }
        histories[pid] = get_history(pid, owner, repo, limit=10)

    return {
        "success": True,
        "message": f"Grade report for {repo}: {len(grades)} platforms.",
        "data": {"repo": repo, "grades": grades, "history": histories},
    }


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_reassess(
    repo: Annotated[str, Field(description="Repo name to request rescoring for.")],
    platform: Annotated[str | None, Field(description="Platform to reassess on. Omit = all.")] = None,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Request rescoring for a repo on grading platforms.

    Attempts to trigger reassessment via each platform's API.
    Some platforms auto-index and don't support manual triggers (returns skipped).

    ## Return Format
    {"success": bool, "message": str, "data": {"results": {platform_id: {"accepted": bool, "note": str}}}}

    ## Examples
    await scraper_reassess(repo="email-mcp", platform="toolbench")
    await scraper_reassess(repo="email-mcp")
    """
    targets = [platform] if platform else list(SCRAPERS.keys())
    results = {}
    for pid in targets:
        if pid not in SCRAPERS:
            results[pid] = {"accepted": False, "note": f"Unknown platform: {pid}"}
            continue
        scraper = SCRAPERS[pid]
        accepted = await scraper.request_reassess(owner, repo)
        note = "Request sent" if accepted else "Auto-indexed or API not available"
        results[pid] = {"accepted": accepted, "note": note}

    return {
        "success": True,
        "message": f"Reassess requested for {repo}.",
        "data": {"results": results},
    }
