"""Auto-fix MCP tools based on ToolBench criticism list.

High-probability mechanical fixes:
1. Expand short docstrings on helper/discovery tools
2. Add Field(ge=..., le=...) to parameters with implied ranges

Each fix is scoped to be safe - docstring changes only, no behavioral changes.
"""

import ast
from pathlib import Path
from typing import Annotated

from pydantic import Field

from ..registry import mcp

REPOS_ROOT = Path(r"D:\Dev\repos")

_RANGE_PARAMS = {
    "timeout": (1, 300),
    "limit": (1, 500),
    "count": (1, 1000),
    "port": (1024, 65535),
    "max_results": (1, 500),
    "max_items": (1, 500),
    "depth": (1, 100),
    "max_depth": (1, 100),
    "page_size": (1, 500),
    "width": (1, 10000),
    "height": (1, 10000),
}


def _get_repo_path(repo: str) -> Path | None:
    p = REPOS_ROOT / repo
    return p if p.is_dir() else None


def _list_py_files(repo_path: Path) -> list[Path]:
    src = repo_path / "src"
    return sorted(src.rglob("*.py")) if src.is_dir() else []


def _has_tool_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        (isinstance(d, ast.Call) and getattr(d.func, "attr", None) == "tool")
        or (isinstance(d, ast.Attribute) and d.attr == "tool")
        for d in node.decorator_list
    )


def _short_docstring_fix(filepath: Path) -> list[dict]:
    """MCP tool functions with docstrings under 60 chars."""
    fixes: list[dict] = []
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return fixes

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _has_tool_decorator(node):
            continue
        doc = ast.get_docstring(node)
        if doc and len(doc) < 60:
            fixes.append(
                {
                    "function": node.name,
                    "file": str(filepath.relative_to(filepath.parent.parent.parent)),
                    "length": len(doc),
                    "current": doc.strip()[:80],
                }
            )
    return fixes


def _add_range_constraints(filepath: Path) -> list[dict]:
    """Tool function params with implied ranges but no Field(ge=/le=)."""
    fixes: list[dict] = []
    source = filepath.read_text(encoding="utf-8").splitlines()

    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return fixes

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _has_tool_decorator(node):
            continue
        for arg in node.args.args:
            if arg.arg in _RANGE_PARAMS and arg.lineno:
                lo, hi = _RANGE_PARAMS[arg.arg]
                line = source[arg.lineno - 1] if arg.lineno <= len(source) else ""
                if "ge=" not in line:
                    fixes.append(
                        {
                            "function": node.name,
                            "parameter": arg.arg,
                            "suggested": f"Field(ge={lo}, le={hi})",
                            "file": str(filepath.relative_to(filepath.parent.parent.parent)),
                            "line": arg.lineno,
                        }
                    )
    return fixes


async def fix_docstrings(repo_path: Path) -> dict:
    results = {"files_scanned": 0, "short_tool_docstrings": 0, "details": []}
    for pyf in _list_py_files(repo_path):
        results["files_scanned"] += 1
        try:
            items = _short_docstring_fix(pyf)
            if items:
                results["short_tool_docstrings"] += len(items)
                results["details"].extend(items)
        except Exception:
            pass
    return results


async def fix_range_constraints(repo_path: Path) -> dict:
    results = {"files_scanned": 0, "unconstrained_params": 0, "details": []}
    for pyf in _list_py_files(repo_path):
        results["files_scanned"] += 1
        try:
            items = _add_range_constraints(pyf)
            if items:
                results["unconstrained_params"] += len(items)
                results["details"].extend(items)
        except Exception:
            pass
    return results


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_fix_repo(
    repo: Annotated[str, Field(description="Repo name (e.g. blender-mcp)")],
    fix_types: Annotated[
        list[str] | None,
        Field(description="Fix types: 'description', 'range'. Omit for all."),
    ] = None,
) -> dict:
    """Read ToolBench criticism for a repo and report fix opportunities.

    Scans the repo's MCP tool functions for short docstrings
    and missing Field(ge=/le=) constraints on numeric parameters.

    ## Return Format
    {"success": bool, "message": str, "fixes": {...}, "issues_used": [...]}
    """
    repo_path = _get_repo_path(repo)
    if not repo_path:
        return {"success": False, "message": f"Repo {repo} not found"}

    from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

    detail = await fetch_grade_with_details("sandraschi", repo)
    issues = (detail or {}).get("top_issues", [])

    if not issues:
        return {"success": True, "message": f"{repo}: no ToolBench issues", "fixes": {}}

    active = set(fix_types or ["description", "range"])
    results = {}
    if "description" in active:
        results["description"] = await fix_docstrings(repo_path)
    if "range" in active:
        results["range"] = await fix_range_constraints(repo_path)

    total = sum(r.get("short_tool_docstrings", 0) + r.get("unconstrained_params", 0) for r in results.values())
    return {
        "success": True,
        "message": f"Scanned {repo}: {total} fix opportunities",
        "fixes": results,
        "issues_used": issues[:5],
    }
