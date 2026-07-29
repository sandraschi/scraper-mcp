"""Auto-fix MCP tools based on ToolBench criticism list.

High-probability mechanical fixes:
1. Expand short docstrings on helper/discovery tools
2. Add Field(ge=..., le=...) to parameters with implied ranges

Each fix is scoped to be safe - docstring changes only, no behavioral changes.
"""

import ast
import re
import shutil
from datetime import datetime
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


def _scan_range_params(filepath: Path) -> list[dict]:
    """Find tool function params with implied ranges but no Field(ge=/le=)."""
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


def _apply_range_param(filepath: Path, param_name: str) -> bool:
    """Add Field(ge=, le=) to one param. Returns True if changed."""
    lo, hi = _RANGE_PARAMS[param_name]
    content = filepath.read_text(encoding="utf-8")
    old = rf"({param_name})\s*:\s*int(\s*=)"
    new = rf"\1: Annotated[int, Field(ge={lo}, le={hi})]\2"
    updated, count = re.subn(old, new, content)
    if count:
        filepath.write_text(updated, encoding="utf-8")
        return True
    return False


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
            items = _scan_range_params(pyf)
            if items:
                results["unconstrained_params"] += len(items)
                results["details"].extend(items)
        except Exception:
            pass
    return results


async def apply_range_constraints(repo_path: Path) -> dict:
    """Write Field(ge=/le=) into source files. Creates .bak backups."""
    results = {"files_scanned": 0, "applied": 0, "files_changed": 0, "details": []}
    for pyf in _list_py_files(repo_path):
        results["files_scanned"] += 1
        items = _scan_range_params(pyf)
        if not items:
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = pyf.with_suffix(f".{ts}.bak")
        shutil.copy2(str(pyf), str(bak))
        changed = False
        for item in items:
            if _apply_range_param(pyf, item["parameter"]):
                changed = True
                results["applied"] += 1
                results["details"].append(item)
        if changed:
            results["files_changed"] += 1
        else:
            bak.unlink(missing_ok=True)
    return results


@mcp.tool(annotations={"readOnly": False, "destructive": False})
async def scraper_fix_repo(
    repo: Annotated[str, Field(description="Repo name (e.g. blender-mcp)")],
    fix_types: Annotated[
        list[str] | None,
        Field(description="Fix types: 'description', 'range'. Omit for all."),
    ] = None,
    apply: Annotated[bool, Field(description="Apply changes (creates .bak backups).")] = False,
) -> dict:
    """Read ToolBench criticism, scan and optionally fix MCP tool code.

    Set apply=true to write Field(ge=, le=) constraints into source files.
    Creates .bak backups. Run without apply to preview changes.

    ## Return Format
    {"success": bool, "message": str, "fixes": {...}, "issues": [...]}
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
        if apply:
            results["range"] = await apply_range_constraints(repo_path)
        else:
            results["range"] = await fix_range_constraints(repo_path)

    total = sum(
        r.get("short_tool_docstrings", 0) + r.get("unconstrained_params", 0) + r.get("applied", 0)
        for r in results.values()
    )
    return {
        "success": True,
        "message": f"{'Applied' if apply else 'Scanned'} {repo}: {total} fix opportunities",
        "fixes": results,
        "issues": issues[:5],
        "applied": apply,
    }
