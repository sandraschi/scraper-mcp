"""scraper_improve_suggest — generates concrete code-level fix suggestions from ToolBench findings."""

from typing import Annotated

from pydantic import Field

from ...analytics import get_latest, upsert_grade
from ...scrapers.engine import SCRAPERS
from ..registry import mcp

FLEET_OWNER = "sandraschi"

# Code-level fix templates for each common ToolBench issue pattern
FIX_TEMPLATES: list[dict] = [
    {
        "triggers": ["constrained-input", "parameter", "underspecified", "free-form string",
                     "missing enum", "untyped string", "operation.*str"],
        "severity": "critical",
        "title": "Add Literal constraints to string parameters",
        "code": """from typing import Literal
from pydantic import Field
from typing_extensions import Annotated

# Before:
operation: str

# After:
operation: Literal["list", "get", "create", "delete", "update"]
""",
        "tools": "all portmanteau tools",
    },
    {
        "triggers": ["param-validation-rules", "numeric param", "range constraint",
                     "min.*max", "missing.*range", "no.*bounds"],
        "severity": "high",
        "title": "Add numeric bounds to integer/float parameters",
        "code": """from typing_extensions import Annotated
from pydantic import Field

# Before:
port: int

# After:
port: Annotated[int, Field(ge=1, le=65535, description="TCP port number")]
""",
        "tools": "tools with numeric params (ports, counts, sizes, timeouts)",
    },
    {
        "triggers": ["response-shaper", "output.*schema", "output.*document",
                     "return.*undocumented", "no.*output", "chaining"],
        "severity": "critical",
        "title": "Document the return shape in the docstring",
        "code": """# Add to every tool docstring:

    Returns:
        Dict with:
          success (bool): True if the operation succeeded.
          data (dict): Operation-specific payload.
          message (str): Human-readable result summary.
        On failure:
          success (bool): False.
          error (str): Description of what went wrong.
          recovery_options (list[str]): Suggested next steps.
""",
        "tools": "every tool that returns a dict",
    },
    {
        "triggers": ["recovery-guide", "error handling", "error.*recovery", "retryable",
                     "what can go wrong"],
        "severity": "critical",
        "title": "Add structured error responses with recovery hints",
        "code": """# Return pattern for error cases:

return {
    "success": False,
    "error": "Failed to connect to API: connection refused",
    "error_type": "connection_error",
    "recovery_options": [
        "Check that the service is running",
        "Verify your API key is set in the .env file",
        "Try again in a few seconds",
    ],
}
""",
        "tools": "all tools that call external APIs or services",
    },
    {
        "triggers": ["tool-description", "description.*generic", "actionable",
                     "llm guidance", "not explain", "when to use"],
        "severity": "high",
        "title": "Rewrite tool descriptions as actionable LLM guidance",
        "code": """# Before (generic):
\"\"\"Network management operations.\"\"\"

# After (actionable — tells the agent when and why):
\"\"\"Manage tailnet DNS, routes, and subnet settings.

Use this when you need to configure DNS nameservers, add or remove
network routes, or manage subnet routing. For device-level operations
use manage_tailnet_devices instead.

Preconditions: TAILSCALE_API_KEY must be set.
Returns: summary of the applied network changes.
\"\"\"
""",
        "tools": "tools with short or generic descriptions",
    },
    {
        "triggers": ["confirmation-request", "destructive", "irreversible",
                     "dry.run", "confirm", "preview"],
        "severity": "high",
        "title": "Add a confirm/dry-run guard to destructive operations",
        "code": """# Add a confirm parameter to destructive tools:

async def delete_resource(
    name: str,
    confirm: Annotated[bool, Field(description="Set to true to confirm deletion")] = False,
) -> dict:
    \"\"\"Delete a resource permanently.

    Use dry_run=True to preview what would be deleted first.
    \"\"\"
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to proceed.",
            "recovery_options": ["Call with confirm=True to execute"],
        }
    # ... actual deletion logic ...
""",
        "tools": "tools that delete, overwrite, or modify state irreversibly",
    },
    {
        "triggers": ["tool-name", "naming", "verb.*prefix", "action verb",
                     "generic name", "not start with verb"],
        "severity": "high",
        "title": "Rename tools to verb-led snake_case",
        "code": """# Use FastMCP's name= override to keep internal function names:
from fastmcp import FastMCP

@mcp.tool(name="manage_tailnet_devices")
async def tailscale_device(operation: str, ...) -> dict:
    \"\"\"...\"\"\"

# Naming convention: verb_noun or verb_adjective_noun
# Good: list_devices, get_status, create_backup, delete_snapshot
# Bad:  device_manager, tailscale_helper, utils
""",
        "tools": "tools with non-verb names",
    },
    {
        "triggers": ["output-schema", "output_schema", "fastmcp.*output"],
        "severity": "medium",
        "title": "Add FastMCP output_schema for stable return shapes",
        "code": """from fastmcp import FastMCP

@mcp.tool(
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "data": {"type": "object"},
            "message": {"type": "string"},
        },
        "required": ["success"],
    }
)
async def my_tool(...) -> dict:
    \"\"\"...\"\"\"
""",
        "tools": "tools with stable return shapes",
    },
    {
        "triggers": ["annotations", "tool annotations", "read.only", "mutating",
                     "destructive.*annotation", "missing annotation"],
        "severity": "medium",
        "title": "Set MCP ToolAnnotations on every tool",
        "code": "from fastmcp import FastMCP\n\n_README_ONLY = {\"readonly\": True}\n_MUTATING = {}\n\n@mcp.tool(annotations=_README_ONLY)\nasync def list_items(...):\n    ...\n\n@mcp.tool(annotations=_MUTATING)\nasync def create_item(...):\n    ...\n",
        "tools": "all tools",
    },
    {
        "triggers": ["pagination", "unbounded", "growing collection", "limit",
                     "page", "context blowup"],
        "severity": "medium",
        "title": "Add pagination parameters to list/search tools",
        "code": """# Add these parameters to any tool that returns a list:

limit: Annotated[int, Field(ge=1, le=100, description="Max items to return")] = 50,
cursor: Annotated[str | None, Field(description="Page token from previous response")] = None,

# In Returns:
#   items (list): Current page of results.
#   has_more (bool): True if more results exist.
#   next_cursor (str | None): Pass this as cursor to get the next page.
""",
        "tools": "list_*, search_*, get_all_* tools",
    },
]


def _match_templates(issue_text: str) -> list[dict]:
    """Find matching fix templates for an issue."""
    lower = issue_text.lower()
    matches = []
    for tmpl in FIX_TEMPLATES:
        for trigger in tmpl["triggers"]:
            if trigger.lower() in lower:
                matches.append(tmpl)
                break
    return matches


def _extract_severity(issue_text: str) -> str:
    for sev in ("critical", "high", "medium", "low"):
        if issue_text.lower().startswith(sev):
            return sev
    return "medium"


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

FLEET_EXCEPTION_PATTERNS = [
    "single-responsibility", "bundles multiple unrelated operations",
    "portmanteau pattern", "multiple operations into a single",
    "one tool per action",
]


def _is_fleet_exception(text: str) -> bool:
    lower = text.lower()
    return any(p.lower() in lower for p in FLEET_EXCEPTION_PATTERNS)


@mcp.tool(annotations={"readOnly": True})
async def scraper_improve_suggest(
    repo: Annotated[str, Field(description="Repo name, e.g. 'email-mcp'.")],
    refresh: Annotated[bool, Field(description="Set true to fetch live from ToolBench.")] = True,
    owner: Annotated[str, Field(description="GitHub owner. Default: sandraschi.")] = FLEET_OWNER,
) -> dict:
    """Generate concrete, copy-paste-able code fixes from ToolBench criticisms.

    Analyzes ToolBench assessment issues and per-tool risk scores, then generates
    specific code snippets for each fix — Literal constraints, return docs,
    error handling, pagination, annotations, naming, etc.

    Fleet exceptions (portmanteau/atomic-tool complaints) are filtered out.

    ## Return Format
    {"success": bool, "message": str, "data": {
      "repo": str, "grade": str, "score": float,
      "suggestions": [{"severity": str, "title": str, "code": str, "applies_to": str, "issue": str}],
      "worst_tools": [{"name": str, "risk_score": float}],
      "markdown": str}}

    ## Examples
    await scraper_improve_suggest(repo="email-mcp")
    await scraper_improve_suggest(repo="tailscale-mcp", refresh=False)
    """
    rows = get_latest(platform="toolbench", owner=owner, repo=repo)
    raw = rows[0]["raw"] if rows else None

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
            "message": f"No ToolBench data for {repo}. Run scraper_refresh() first.",
            "data": {"repo": repo},
        }

    issues = raw.get("top_issues") or []
    tools = raw.get("tool_details") or []
    grade = raw.get("grade", "?")
    score = raw.get("score")

    suggestions = []
    seen_templates = set()
    for issue_text in issues:
        if _is_fleet_exception(issue_text):
            continue
        severity = _extract_severity(issue_text)
        for sev_prefix in ("critical ", "high ", "medium ", "low "):
            if issue_text.lower().startswith(sev_prefix):
                issue_text = issue_text[len(sev_prefix):]
                break
        matches = _match_templates(issue_text)
        for tmpl in matches:
            tid = tmpl["title"]
            if tid not in seen_templates:
                seen_templates.add(tid)
                suggestions.append({
                    "severity": tmpl["severity"],
                    "title": tmpl["title"],
                    "code": tmpl["code"].strip(),
                    "applies_to": tmpl["tools"],
                    "issue": issue_text[:200],
                })

    suggestions.sort(key=lambda s: SEVERITY_ORDER.get(s["severity"], 99))

    worst_tools = sorted(tools, key=lambda t: t.get("risk_score", 0), reverse=True)[:5]

    # Build markdown
    md = [
        f"## Concrete Fixes: {repo}",
        f"**ToolBench:** {grade} (score: {score})",
        f"**Suggestions:** {len(suggestions)}",
        "",
    ]
    for s in suggestions:
        tag = s["severity"].upper()
        md.append(f"### [{tag}] {s['title']}")
        md.append(f"*Applies to: {s['applies_to']}*")
        md.append(f"\nTrigger: {s['issue'][:150]}\n")
        md.append("```python")
        md.append(s["code"])
        md.append("```\n")

    if worst_tools:
        md.append("### Tools needing most attention\n")
        for t in worst_tools:
            md.append(f"- {t.get('name')} (risk: {t.get('risk_score', '?')})")
        md.append("")

    return {
        "success": True,
        "message": f"{len(suggestions)} concrete fix suggestions for {repo}.",
        "data": {
            "repo": repo,
            "grade": grade,
            "score": score,
            "suggestions": suggestions,
            "worst_tools": worst_tools,
            "markdown": "\n".join(md),
        },
    }
