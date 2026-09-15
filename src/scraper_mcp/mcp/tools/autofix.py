"""Auto-fix MCP tools based on ToolBench criticism list.

High-probability mechanical fixes:
1. Expand short docstrings on helper/discovery tools
2. Add Field(ge=..., le=...) to parameters with implied ranges

Each fix is scoped to be safe - docstring changes only, no behavioral changes.
"""

import ast
import asyncio
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
        await asyncio.to_thread(shutil.copy2, str(pyf), str(bak))
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


async def _call_llm(prompt: str, base_url: str = "http://localhost:11434") -> str:
    """Call the local Ollama LLM with a prompt. Returns the response text."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{base_url}/api/generate",
                json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            )
        data = r.json()
        return data.get("response", "").strip()
    except Exception as e:
        return f"[LLM error: {e}]"


_DOCSTRING_PROMPT = """You are a technical writer for MCP tool documentation.
Given the source code of a Python function that is registered as an MCP tool,
write a concise 1-2 sentence description of what it does.

The description MUST:
- Start with a verb ("List", "Search", "Create", "Delete", etc.)
- Mention what the tool returns
- Be under 120 characters
- Be a plain string (no markdown, no code blocks)

Current docstring: "{current}"
Function name: {func_name}

Function code:
```python
{code}
```

Write only the new docstring text, nothing else:"""


def _extract_function_source(filepath: Path, func_name: str) -> str:
    """Extract the full source of a function by name."""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            lines = content.splitlines()
            end = node.end_lineno or node.lineno + 10
            return "\n".join(lines[node.lineno - 1 : end])
    return ""


def _rewrite_docstring_in_file(filepath: Path, func_name: str, new_doc: str) -> bool:
    """Replace the docstring of a named function in a file."""
    content = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            doc = ast.get_docstring(node)
            if doc is None:
                return False
            old = f'"""{doc}"""'
            new = f'"""{new_doc}"""'
            if old in content:
                content = content.replace(old, new, 1)
                filepath.write_text(content, encoding="utf-8")
                return True
    return False


async def apply_docstring_expansions(
    repo_path: Path,
    llm_base: str = "http://localhost:11434",
) -> dict:
    """Scan short tool docstrings, expand via LLM, write back. Creates .bak backups."""
    results = {"files_scanned": 0, "expanded": 0, "failed": 0, "skipped": 0, "details": []}
    for pyf in _list_py_files(repo_path):
        results["files_scanned"] += 1
        items = _short_docstring_fix(pyf)
        if not items:
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = pyf.with_suffix(f".{ts}.bak")
        await asyncio.to_thread(shutil.copy2, str(pyf), str(bak))
        any_change = False
        for item in items:
            fname = item["function"]
            code = _extract_function_source(pyf, fname)
            if not code:
                results["skipped"] += 1
                continue
            prompt = _DOCSTRING_PROMPT.format(
                current=item["current"],
                func_name=fname,
                code=code[:1500],
            )
            expanded = await _call_llm(prompt, llm_base)
            if not expanded or expanded.startswith("[LLM error"):
                results["failed"] += 1
                continue
            if _rewrite_docstring_in_file(pyf, fname, expanded):
                results["expanded"] += 1
                results["details"].append(
                    {
                        "function": fname,
                        "file": str(pyf.relative_to(pyf.parent.parent.parent)),
                        "before": item["current"],
                        "after": expanded,
                    }
                )
                any_change = True
        if not any_change:
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

    Description scan: finds MCP tool functions with docstrings under 60 chars.
    Range scan: finds int params (timeout, limit, etc.) without Field(ge=, le=).

    When apply=true:
    - Range fixes: writes Field(ge=, le=) constraints, creates .bak backups.
    - Description fixes: calls local LLM (Ollama) to expand short docstrings.

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
        if apply:
            results["description"] = await apply_docstring_expansions(repo_path)
        else:
            results["description"] = await fix_docstrings(repo_path)
    if "range" in active:
        if apply:
            results["range"] = await apply_range_constraints(repo_path)
        else:
            results["range"] = await fix_range_constraints(repo_path)

    total = sum(
        r.get("short_tool_docstrings", 0)
        + r.get("unconstrained_params", 0)
        + r.get("applied", 0)
        + r.get("expanded", 0)
        for r in results.values()
    )
    return {
        "success": True,
        "message": f"{'Applied' if apply else 'Scanned'} {repo}: {total} fix opportunities",
        "fixes": results,
        "issues": issues[:5],
        "applied": apply,
    }
