"""scraper_status — server health, last refresh, platform status."""

from datetime import UTC, datetime

from ...analytics import get_coverage_matrix, get_latest
from ...scrapers.engine import SCRAPERS
from ..registry import mcp


@mcp.tool(annotations={"readOnly": True})
async def scraper_status() -> dict:
    """Return server status, platform health, last refresh times, and repo counts.

    Shows which platforms are configured, how many repos have data,
    when each platform was last fetched, and any stale data warnings.

    ## Return Format
    {"success": bool, "message": str, "data": {
      "uptime": str, "repo_count": int, "fleet_total": int,
      "platforms": [{"id": str, "name": str, "last_fetch": str, "stale": bool, "repos_found": int}],
      "grade_summary": {"A": int, "B": int, "C": int, "D": int, "F": int, "total": int}}}

    ## Examples
    await scraper_status()
    """
    import time

    matrix = get_coverage_matrix("sandraschi")
    latest = get_latest(owner="sandraschi")

    now = time.time()
    platform_info = []
    for pid, scraper in SCRAPERS.items():
        entries = [e for e in latest if e["platform"] == pid]
        last_ts = max((e["fetched_at"] for e in entries), default=0)
        last_fetch = datetime.fromtimestamp(last_ts, tz=UTC).isoformat() if last_ts else "never"
        stale = last_ts > 0 and (now - last_ts) > 86400 * 3
        repos_found = len({e["repo"] for e in entries})
        platform_info.append(
            {
                "id": pid,
                "name": scraper.name,
                "last_fetch": last_fetch,
                "stale": stale,
                "repos_found": repos_found,
            }
        )

    # Grade distribution across all platforms
    grades: dict[str, int] = {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for e in latest:
        g = e.get("grade") or ""
        if g in grades:
            grades[g] += 1
    total_with_grades = sum(grades.values())

    return {
        "success": True,
        "message": f"{len(platform_info)} platforms, {matrix['repo_count']} repos in matrix, {total_with_grades} with grades.",
        "data": {
            "repo_count": matrix["repo_count"],
            "fleet_total": matrix["fleet_total"],
            "platforms": platform_info,
            "grade_summary": {**grades, "total": total_with_grades},
            "platform_count": len(platform_info),
        },
    }
