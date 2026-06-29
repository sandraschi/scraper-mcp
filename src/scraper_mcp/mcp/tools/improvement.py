"""Improvement plan tool — generates prioritized fix list from ToolBench criticisms."""

from typing import Annotated

from pydantic import Field

from ...analytics import get_latest, upsert_grade
from ...scrapers.engine import SCRAPERS
from ..registry import mcp

FLEET_OWNER = "sandraschi"

# Known fleet exceptions — criteria we explicitly disagree with
FLEET_EXCEPTIONS = {
    "portmanteau": [
        "single-responsibility", "bundles multiple unrelated operations",
        "portmanteau pattern", "multiple operations into a single",
        "does many different things",
    ],
    "one_action_per_tool": [
        "one tool per action", "atomic tool", "single action per tool",
    ],
}

# Pattern mapping from ToolBench issue text → fleet standard
FLEET_STANDARD_MAP = {
    "constrained-input": "TOOL_DESIGN_STANDARDS.md §5.1 — Use Literal/enums + Annotated Field for params",
    "response-shaper": "TOOL_DESIGN_STANDARDS.md §4.4 — Document return shape with named keys",
    "recovery-guide": "TOOL_DESIGN_STANDARDS.md §6 — Add structured errors + recovery_options",
    "param-validation-rules": "TOOL_DESIGN_STANDARDS.md §5.1 — Add Field(ge=/le=/description=)",
    "tool-description": "TOOL_DESIGN_STANDARDS.md §3 — Use gold-standard docstring template",
    "confirmation-request": "TOOL_DESIGN_STANDARDS.md §5 — Add confirm/dry-run for destructive ops",
    "tool-name": "TOOL_DESIGN_STANDARDS.md (§5 naming row) — Use verb-led snake_case names",
    "output-schema": "TOOL_DESIGN_STANDARDS.md §7 — Add FastMCP output_schema= for stable shapes",
    "annotations": "TOOL_DESIGN_STANDARDS.md §9 — Set READ_ONLY/MUTATING/DESTRUCTIVE annotations",
    "pagination": "TOOL_DESIGN_STANDARDS.md §5 — Add limit + offset or cursor pagination",
    "error-handling": "TOOL_DESIGN_STANDARDS.md §6 — Add error_type + suggestions in failure dicts",
    "parameter-semantics": "TOOL_DESIGN_STANDARDS.md §5.1 — Document param defaults, ranges, interactions",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _is_fleet_exception(issue_text: str) -> bool:
    """Check if an issue is a known fleet exception we choose not to fix."""
    lower = issue_text.lower()
    for category, patterns in FLEET_EXCEPTIONS.items():
        for p in patterns:
            if p.lower() in lower:
                return True
    return False


def _classify_issue(issue_text: str) -> list[str]:
    """Map issue text to fleet standard sections."""
    lower = issue_text.lower()
    matched = []
    for keyword, ref in FLEET_STANDARD_MAP.items():
        if keyword.replace("-", " ") in lower or keyword in lower:
            matched.append(ref)
    if not matched:
        # Generic fallback
        if "description" in lower or "docstring" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §3 — Improve docstring quality")
        elif "schema" in lower or "parameter" in lower or "param" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §5.1 — Add parameter constraints")
        elif "output" in lower or "return" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §4.4 — Document return format")
        elif "error" in lower or "recovery" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §6 — Add error handling guidance")
        elif "name" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md (§5 naming row) — Rename for verb-led pattern")
        else:
            matched.append("Refer to TOOL_DESIGN_STANDARDS.md for guidance")
    return matched


def _extract_severity(issue_text: str) -> str:
    for sev in ("critical", "high", "medium", "low"):
        if issue_text.lower().startswith(sev):
            return sev
    return "medium"


def _severity_sort_key(issue: dict) -> tuple:
    return (SEVERITY_ORDER.get(issue.get("severity", "medium"), 99), issue.get("text", ""))


@mcp.tool(annotations={"readOnly": True})
async def scraper_improvement_plan(
    repo: Annotated[str, Field(description="Repo name, e.g. 'email-mcp'.")],
    refresh: Annotated[bool, Field(description="Set true to fetch live from ToolBench first.")] = True,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Generate a prioritized improvement plan from ToolBench criticisms.

    Fetches the latest ToolBench assessment (live or from DB), extracts top issues,
    filters out known fleet exceptions (portmanteau stance), maps each issue to
    specific TOOL_DESIGN_STANDARDS.md sections, and returns an actionable fix list
    ordered by severity.

    ## Return Format
    {"success": bool, "message": str, "data": {"repo": str, "grade": str, "score": float,
      "filtered_issues": [{"severity": str, "text": str, "fixes": [str]}],
      "skipped_exceptions": [str],
      "worst_tools": [{"name": str, "risk_score": float}],
      "summary": str}}

    ## Examples
    await scraper_improvement_plan(repo="email-mcp")
    await scraper_improvement_plan(repo="tailscale-mcp", refresh=False)
    """
    # Try DB first
    rows = get_latest(platform="toolbench", owner=owner, repo=repo)
    raw = rows[0]["raw"] if rows else None

    # Optionally fetch live
    if refresh or not raw:
        tb_scraper = SCRAPERS.get("toolbench")
        if tb_scraper:
            result = await tb_scraper.fetch_grade(owner, repo)
            if result:
                upsert_grade("toolbench", owner, repo,
                             result.get("grade"), result.get("score"), result)
                raw = result

    if not raw:
        return {
            "success": False,
            "message": f"No ToolBench data for {repo}. Run scraper_refresh() or check repo name.",
            "data": {"repo": repo},
        }

    issues = raw.get("top_issues") or []
    tools = raw.get("tool_details") or []
    grade = raw.get("grade", "?")
    score = raw.get("score")

    # Filter and classify issues
    filtered = []
    skipped = []
    for issue_text in issues:
        if _is_fleet_exception(issue_text):
            skipped.append(issue_text[:120])
            continue
        severity = _extract_severity(issue_text)
        # Clean severity prefix from text
        clean_text = issue_text
        for sev in ("critical ", "high ", "medium ", "low "):
            if clean_text.lower().startswith(sev):
                clean_text = clean_text[len(sev):]
                break
        fixes = _classify_issue(issue_text)
        filtered.append({
            "severity": severity,
            "text": clean_text[:300],
            "fixes": fixes,
        })

    filtered.sort(key=_severity_sort_key)

    # Sort tools by risk (highest first = worst = needs most attention)
    worst_tools = sorted(tools, key=lambda t: t.get("risk_score", 0), reverse=True)[:10]

    # Build summary
    critical_count = sum(1 for i in filtered if i["severity"] == "critical")
    high_count = sum(1 for i in filtered if i["severity"] == "high")
    skipped_count = len(skipped)

    # Generate markdown summary
    summary_lines = [
        f"## Improvement Plan: {repo}",
        f"**ToolBench Grade:** {grade} (Score: {score})",
        f"**Issues to fix:** {len(filtered)} ({critical_count} critical, {high_count} high)",
        f"**Fleet exceptions skipped:** {skipped_count} (portmanteau stance)",
        "",
    ]

    if filtered:
        summary_lines.append("### Issues by Priority")
        for i, issue in enumerate(filtered, 1):
            sev_tag = {
                "critical": "CRIT", "high": "HIGH",
                "medium": "MED", "low": "LOW",
            }.get(issue["severity"], "???")
            summary_lines.append(f"\n**{i}. [{sev_tag}]** {issue['text'][:200]}")
            for fix in issue["fixes"]:
                summary_lines.append(f"   - {fix}")

    if worst_tools:
        summary_lines.append("\n### Worst-Risk Tools")
        for t in worst_tools[:5]:
            summary_lines.append(f"- {t.get('name')}: risk {t.get('risk_score', '?')}")

    if skipped:
        summary_lines.append(f"\n### Skipped (Fleet Exceptions)")
        for s in skipped:
            summary_lines.append(f"- {s[:100]}")

    summary_lines.append(f"\n**Standards:** {', '.join(sorted(set(f for i in filtered for f in i['fixes'])))}")

    return {
        "success": True,
        "message": f"Improvement plan for {repo}: {len(filtered)} actionable issues ({critical_count} critical).",
        "data": {
            "repo": repo,
            "grade": grade,
            "score": score,
            "filtered_issues": filtered,
            "skipped_exceptions": skipped,
            "worst_tools": worst_tools,
            "summary": "\n".join(summary_lines),
        },
    }
