"""HTTP API: run the bundled Playwright scraper (subprocess)."""

from __future__ import annotations

import asyncio
import importlib.util
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class DiscoverBody(BaseModel):
    search_url: str = Field(..., min_length=12)
    out_subdir: str | None = None
    max_pages: int = Field(15, ge=1, le=100)
    delay_seconds: float = Field(3.0, ge=0.5, le=120.0)
    jitter_seconds: float = Field(2.0, ge=0.0, le=60.0)
    headed: bool = False


class ScrapeBody(BaseModel):
    urls_text: str = Field(..., min_length=8, description="One ToolBench assessment URL per line")
    out_subdir: str | None = None
    delay_seconds: float = Field(3.0, ge=0.5, le=120.0)
    jitter_seconds: float = Field(2.0, ge=0.0, le=60.0)
    save_html: bool = False
    headed: bool = False


class FullBody(BaseModel):
    search_url: str = Field(..., min_length=12)
    out_subdir: str | None = None
    max_pages: int = Field(15, ge=1, le=100)
    delay_seconds: float = Field(4.0, ge=0.5, le=120.0)
    jitter_seconds: float = Field(2.0, ge=0.0, le=60.0)
    save_html: bool = False
    headed: bool = False


def _script_path() -> Path:
    import os

    p = os.getenv("SCRAPER_MCP_TOOLBENCH_SCRIPT", "").strip()
    if p:
        return Path(p)
    return _REPO_ROOT / "scripts" / "scrape_toolbench_assessments.py"


def _output_root() -> Path:
    import os

    return Path(os.getenv("SCRAPER_MCP_SCRAPE_OUTPUT_ROOT", str(_REPO_ROOT / "scrape_out"))).resolve()


def _safe_subdir(name: str | None) -> str:
    if not name or name.strip() == "":
        return "default"
    n = name.strip()
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}$", n):
        raise HTTPException(status_code=400, detail="invalid out_subdir (use letters, numbers, ._-)")
    return n


def _resolve_out_dir(sub: str | None) -> Path:
    base = _output_root()
    d = (base / _safe_subdir(sub)).resolve()
    try:
        d.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail="out_dir escapes output root") from None
    return d


def _resolve_file_path(rel: str) -> Path:
    root = _output_root()
    clean = rel.replace("\\", "/").lstrip("/")
    p = (root / clean).resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="path escapes output root") from None
    if not p.exists():
        raise HTTPException(status_code=404, detail="not found")
    return p


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


async def _run_script(args: list[str]) -> dict[str, Any]:
    script = _script_path()
    if not script.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Scraper script not found: {script}. Set SCRAPER_MCP_TOOLBENCH_SCRIPT.",
        )
    cmd = [sys.executable, str(script), *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    return {
        "returncode": proc.returncode,
        "stdout": out_b.decode("utf-8", errors="replace"),
        "stderr": err_b.decode("utf-8", errors="replace"),
        "command": cmd,
    }


def build_router() -> APIRouter:
    r = APIRouter(prefix="/api/scraper", tags=["scraper"])

    @r.get("/status")
    async def status() -> dict[str, Any]:
        script = _script_path()
        root = _output_root()
        return {
            "script_path": str(script),
            "script_exists": script.is_file(),
            "python_executable": sys.executable,
            "playwright_available": playwright_available(),
            "output_root": str(root),
            "hint": "pip install -e '.[scraper]' ; python -m playwright install chromium",
        }

    @r.post("/discover")
    async def discover(discover_in: DiscoverBody) -> dict[str, Any]:
        out = _resolve_out_dir(discover_in.out_subdir)
        out.mkdir(parents=True, exist_ok=True)
        args = [
            "discover",
            "--search-url",
            discover_in.search_url,
            "--out-dir",
            str(out),
            "--max-pages",
            str(discover_in.max_pages),
            "--delay-seconds",
            str(discover_in.delay_seconds),
            "--jitter-seconds",
            str(discover_in.jitter_seconds),
        ]
        if discover_in.headed:
            args.append("--headed")
        result = await _run_script(args)
        return {"success": result["returncode"] == 0, **result, "out_dir": str(out)}

    @r.post("/scrape")
    async def scrape_urls(scrape_in: ScrapeBody) -> dict[str, Any]:
        out = _resolve_out_dir(scrape_in.out_subdir)
        out.mkdir(parents=True, exist_ok=True)
        urls_file = out / "urls.txt"
        urls_file.write_text(scrape_in.urls_text.strip() + "\n", encoding="utf-8")
        args = [
            "scrape",
            "--urls-file",
            str(urls_file),
            "--out-dir",
            str(out),
            "--delay-seconds",
            str(scrape_in.delay_seconds),
            "--jitter-seconds",
            str(scrape_in.jitter_seconds),
        ]
        if scrape_in.save_html:
            args.append("--save-html")
        if scrape_in.headed:
            args.append("--headed")
        result = await _run_script(args)
        return {"success": result["returncode"] == 0, **result, "out_dir": str(out)}

    @r.post("/full")
    async def full_run(full_in: FullBody) -> dict[str, Any]:
        out = _resolve_out_dir(full_in.out_subdir)
        out.mkdir(parents=True, exist_ok=True)
        args = [
            "full",
            "--search-url",
            full_in.search_url,
            "--out-dir",
            str(out),
            "--max-pages",
            str(full_in.max_pages),
            "--delay-seconds",
            str(full_in.delay_seconds),
            "--jitter-seconds",
            str(full_in.jitter_seconds),
        ]
        if full_in.save_html:
            args.append("--save-html")
        if full_in.headed:
            args.append("--headed")
        result = await _run_script(args)
        return {"success": result["returncode"] == 0, **result, "out_dir": str(out)}

    @r.get("/tree")
    async def tree(subdir: str | None = None) -> dict[str, Any]:
        base = _resolve_out_dir(subdir)
        if not base.exists():
            return {"path": str(base), "files": []}
        root = _output_root()
        files: list[dict[str, Any]] = []
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root)
                files.append(
                    {
                        "path": str(rel).replace("\\", "/"),
                        "size": p.stat().st_size,
                    }
                )
        files.sort(key=lambda x: x["path"])
        return {"path": str(base), "files": files[:800]}

    @r.get("/file")
    async def read_file(rel_path: str) -> dict[str, Any]:
        p = _resolve_file_path(rel_path)
        if p.is_dir():
            raise HTTPException(status_code=400, detail="is a directory")
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > 800_000:
            text = text[:800_000] + "\n… [truncated]"
        return {"path": rel_path.replace("\\", "/"), "content": text}

    @r.delete("/output")
    async def clear_output(subdir: str | None = None) -> dict[str, Any]:
        d = _resolve_out_dir(subdir)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
        return {"cleared": str(d)}

    return r
