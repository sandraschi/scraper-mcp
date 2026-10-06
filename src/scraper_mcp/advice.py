"""Advice engine - Phase 2 of the email -> advice -> digest workflow.

Turns stored grades into prioritized, persisted fix items:
- Glama: per-tool TDQS dimensions (purpose, usage_guidelines, behavior,
  parameters, conciseness, completeness) -> weakest dims + worst tools,
  each mapped to a concrete docstring fix.
- ToolBench: top_issues via the shared fleet-standard map (single source
  of truth lives HERE; mcp/tools/improvement.py imports from this module).

Advice items persist in the `advice_items` table (same SQLite depot as
grades) with open/done status so the daily digest can track resolution.
"""

from __future__ import annotations

import sqlite3
import time

from .analytics import DB_DIR, DB_PATH

# --- ToolBench issue -> fleet standard (moved here from mcp/tools/improvement.py) ---

FLEET_STANDARD_MAP = {
    "constrained-input": "TOOL_DESIGN_STANDARDS.md §5.1 - Use Literal/enums + Annotated Field for params",
    "response-shaper": "TOOL_DESIGN_STANDARDS.md §4.4 - Document return shape with named keys",
    "recovery-guide": "TOOL_DESIGN_STANDARDS.md §6 - Add structured errors + recovery_options",
    "param-validation-rules": "TOOL_DESIGN_STANDARDS.md §5.1 - Add Field(ge=/le=/description=)",
    "tool-description": "TOOL_DESIGN_STANDARDS.md §3 - Use gold-standard docstring template",
    "confirmation-request": "TOOL_DESIGN_STANDARDS.md §5 - Add confirm/dry-run for destructive ops",
    "tool-name": "TOOL_DESIGN_STANDARDS.md (§5 naming row) - Use verb-led snake_case names",
    "output-schema": "TOOL_DESIGN_STANDARDS.md §7 - Add FastMCP output_schema= for stable shapes",
    "annotations": "TOOL_DESIGN_STANDARDS.md §9 - Set READ_ONLY/MUTATING/DESTRUCTIVE annotations",
    "pagination": "TOOL_DESIGN_STANDARDS.md §5 - Add limit + offset or cursor pagination",
    "error-handling": "TOOL_DESIGN_STANDARDS.md §6 - Add error_type + suggestions in failure dicts",
    "parameter-semantics": "TOOL_DESIGN_STANDARDS.md §5.1 - Document param defaults, ranges, interactions",
}

FLEET_EXCEPTIONS = {
    "portmanteau": [
        "single-responsibility",
        "bundles multiple unrelated operations",
        "portmanteau pattern",
        "does many different things",
    ],
    "one_action_per_tool": [
        "one tool per action",
        "atomic tool",
        "single action per tool",
    ],
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def is_fleet_exception(issue_text: str) -> bool:
    """Check if an issue is a known fleet exception we choose not to fix."""
    lower = (issue_text or "").lower()
    for _category, patterns in FLEET_EXCEPTIONS.items():
        for pattern in patterns:
            if pattern.lower() in lower:
                return True
    return False


def classify_issue(issue_text: str) -> list[str]:
    """Map issue text to fleet standard sections."""
    lower = (issue_text or "").lower()
    matched = []
    for keyword, ref in FLEET_STANDARD_MAP.items():
        if keyword.replace("-", " ") in lower or keyword in lower:
            matched.append(ref)
    if not matched:
        if "description" in lower or "docstring" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §3 - Improve docstring quality")
        elif "schema" in lower or "parameter" in lower or "param" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §5.1 - Add parameter constraints")
        elif "output" in lower or "return" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §4.4 - Document return format")
        elif "error" in lower or "recovery" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md §6 - Add error handling guidance")
        elif "name" in lower:
            matched.append("TOOL_DESIGN_STANDARDS.md (§5 naming row) - Rename for verb-led pattern")
        else:
            matched.append("Refer to TOOL_DESIGN_STANDARDS.md for guidance")
    return matched


def extract_severity(issue_text: str) -> str:
    for sev in ("critical", "high", "medium", "low"):
        if (issue_text or "").lower().startswith(sev):
            return sev
    return "medium"


def strip_severity_prefix(issue_text: str) -> str:
    clean = issue_text or ""
    for sev in ("critical ", "high ", "medium ", "low "):
        if clean.lower().startswith(sev):
            return clean[len(sev) :]
    return clean


# --- Glama TDQS dimensions -> docstring fixes --------------------------------

GLAMA_DIMS = ("purpose", "usage_guidelines", "behavior", "parameters", "conciseness", "completeness")

GLAMA_DIM_FIXES = {
    "purpose": (
        "TOOL_DESIGN_STANDARDS.md §3 - First sentence must state what the tool does",
        "Rewrite the docstring's first sentence as a crisp purpose statement (verb-led, <25 words).",
    ),
    "usage_guidelines": (
        "TOOL_DESIGN_STANDARDS.md §3 - Add 'When to use / When NOT to use' guidance",
        "Add a When-to-use block with 2-3 call scenarios and 1-2 explicit non-uses.",
    ),
    "behavior": (
        "TOOL_DESIGN_STANDARDS.md §6 - Document behavior, side effects, and warnings",
        "Document side effects, destructive operations, and behavioral warnings in the docstring body.",
    ),
    "parameters": (
        "TOOL_DESIGN_STANDARDS.md §5.1 - Describe every parameter via Field(description=...)",
        "Add a description to every parameter (type, range/default, and what happens if omitted).",
    ),
    "conciseness": (
        "TOOL_DESIGN_STANDARDS.md §3 - Keep docstrings 80-250 words",
        "Trim boilerplate; move long examples to docs/ and keep the docstring focused.",
    ),
    "completeness": (
        "TOOL_DESIGN_STANDARDS.md §4.4 - Document return shape with named keys",
        "Add a Returns section naming every key (success/data/message or equivalent).",
    ),
}

DIM_WARN = 3.5  # dim average below this -> advice item (TDQS is 0-5)
DIM_CRITICAL = 2.5


def _dim_severity(avg: float) -> str:
    if avg < DIM_CRITICAL:
        return "critical"
    if avg < DIM_WARN:
        return "high"
    return "medium"


def build_glama_advice(raw: dict | None, repo: str) -> tuple[list[dict], list[dict]]:
    """(advice_items, worst_tools) from a stored Glama grade raw dict."""
    if not raw:
        return [], []
    tools = raw.get("tool_details") or []
    worst_tools = sorted(tools, key=lambda t: t.get("score", 0))[:5]
    items: list[dict] = []

    for tool in worst_tools:
        score = tool.get("score", 0) or 0
        if score < DIM_WARN:
            items.append(
                {
                    "repo": repo,
                    "platform": "glama",
                    "kind": "tool",
                    "target": tool.get("name", "?"),
                    "severity": "critical" if score < DIM_CRITICAL else "high",
                    "text": f"Tool '{tool.get('name', '?')}' scores {score}/5 - worst on this server"
                    " (the server grade blends mean with minimum, so this tool drags everything).",
                    "fix_ref": "Fix its weakest dimensions first (see dim items), then re-release.",
                }
            )

    dim_sums: dict[str, float] = {dim: 0.0 for dim in GLAMA_DIMS}
    dim_counts: dict[str, int] = {dim: 0 for dim in GLAMA_DIMS}
    for tool in tools:
        for dim in GLAMA_DIMS:
            value = tool.get(dim)
            if isinstance(value, (int, float)) and value > 0:
                dim_sums[dim] += value
                dim_counts[dim] += 1
    for dim in GLAMA_DIMS:
        if not dim_counts[dim]:
            continue
        avg = dim_sums[dim] / dim_counts[dim]
        if avg < DIM_WARN:
            fix_ref, action = GLAMA_DIM_FIXES[dim]
            items.append(
                {
                    "repo": repo,
                    "platform": "glama",
                    "kind": "dimension",
                    "target": dim,
                    "severity": _dim_severity(avg),
                    "text": f"Dimension '{dim}' averages {avg:.1f}/5 across {dim_counts[dim]} tools.",
                    "fix_ref": f"{fix_ref} - {action}",
                }
            )

    items.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), item["target"]))
    return items, worst_tools


def build_toolbench_advice(raw: dict | None, repo: str) -> tuple[list[dict], list[dict], list[str]]:
    """(advice_items, worst_tools, skipped_exceptions) from a ToolBench raw dict."""
    if not raw:
        return [], [], []
    items: list[dict] = []
    skipped: list[str] = []
    for issue_text in raw.get("top_issues") or []:
        if is_fleet_exception(issue_text):
            skipped.append(issue_text[:120])
            continue
        clean = strip_severity_prefix(issue_text)
        for fix_ref in classify_issue(issue_text):
            items.append(
                {
                    "repo": repo,
                    "platform": "toolbench",
                    "kind": "issue",
                    "target": clean[:120],
                    "severity": extract_severity(issue_text),
                    "text": clean[:300],
                    "fix_ref": fix_ref,
                }
            )
    items.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), item["target"]))
    tools = raw.get("tool_details") or []
    worst_tools = sorted(tools, key=lambda t: t.get("tool_score", 0), reverse=True)[:5]
    return items, worst_tools, skipped


# --- store -------------------------------------------------------------------

_ADVICE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS advice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo TEXT NOT NULL,
        platform TEXT NOT NULL,
        kind TEXT NOT NULL,
        target TEXT NOT NULL,
        severity TEXT NOT NULL,
        text TEXT NOT NULL,
        fix_ref TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at REAL NOT NULL,
        resolved_at REAL,
        UNIQUE(repo, platform, kind, target)
    )
"""


def _get_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_ADVICE_SCHEMA)
    conn.commit()
    return conn


def upsert_advice(items: list[dict]) -> int:
    """Refresh open items, insert new ones. Returns count of newly opened."""
    conn = _get_db()
    now = time.time()
    new = 0
    for item in items:
        cursor = conn.execute(
            """
            UPDATE advice_items SET severity=?, text=?, fix_ref=?, status='open'
            WHERE repo=? AND platform=? AND kind=? AND target=?
            """,
            (
                item["severity"],
                item["text"],
                item["fix_ref"],
                item["repo"],
                item["platform"],
                item["kind"],
                item["target"],
            ),
        )
        if cursor.rowcount == 0:
            conn.execute(
                """
                INSERT INTO advice_items
                (repo, platform, kind, target, severity, text, fix_ref, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    item["repo"],
                    item["platform"],
                    item["kind"],
                    item["target"],
                    item["severity"],
                    item["text"],
                    item["fix_ref"],
                    now,
                ),
            )
            new += 1
    conn.commit()
    conn.close()
    return new


def list_advice(repo: str | None = None, status: str | None = None) -> list[dict]:
    """Read back advice items, optionally filtered."""
    conn = _get_db()
    query = (
        "SELECT id, repo, platform, kind, target, severity, text, fix_ref,"
        " status, created_at, resolved_at FROM advice_items WHERE 1=1"
    )
    params: list = []
    if repo:
        query += " AND repo = ?"
        params.append(repo.strip().lower())
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    keys = (
        "id",
        "repo",
        "platform",
        "kind",
        "target",
        "severity",
        "text",
        "fix_ref",
        "status",
        "created_at",
        "resolved_at",
    )
    return [dict(zip(keys, row)) for row in rows]


def resolve_advice(item_id: int) -> bool:
    """Mark an advice item done. Returns True if a row flipped."""
    conn = _get_db()
    cursor = conn.execute(
        "UPDATE advice_items SET status='done', resolved_at=? WHERE id=? AND status='open'",
        (time.time(), item_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount == 1
