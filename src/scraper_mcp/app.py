"""FastAPI backend: fleet grade aggregator + ToolBench archiver (replaces toolbench-mcp)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from scraper_mcp.activity_log import install_log_handler, log_activity
from scraper_mcp.capabilities import build_capabilities
from scraper_mcp.config import settings
from scraper_mcp.logs_api import build_router as build_logs_router
from scraper_mcp.meta_api import build_router as build_meta_router
from scraper_mcp.scraper_api import build_router as build_scraper_router

_startup = time.time()


def build_app() -> FastAPI:
    from scraper_mcp.mcp import tools as _tools  # noqa: F401 — register MCP tools
    from scraper_mcp.mcp.registry import mcp

    mcp_http = mcp.http_app(path="/")
    install_log_handler()
    log_activity("system", "scraper-mcp backend starting", level="INFO")

    app = FastAPI(
        title="scraper-mcp",
        version="0.2.0",
        lifespan=mcp_http.lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{settings.webapp_port}",
            f"http://localhost:{settings.webapp_port}",
            f"http://127.0.0.1:{settings.port}",
            f"http://localhost:{settings.port}",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_origin_regex=r"https?://(?:[a-zA-Z0-9-]+\.ts\.net|.*?\.tail-[a-f0-9]+\.ts\.net|tauri\.localhost|localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|100\.\d{1,3}\.\d{1,3}\.\d{1,3})(?::\d+)?$|^tauri://localhost$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "status": "ok",
            "service": "scraper-mcp",
            "port": settings.port,
            "mcp_http": f"http://{settings.host}:{settings.port}/mcp",
            "webapp": f"http://127.0.0.1:{settings.webapp_port}",
            "uptime": round(time.time() - _startup, 1),
        }

    @app.get("/api/capabilities")
    async def capabilities() -> dict[str, Any]:
        return await build_capabilities(mcp, version="0.2.0")

    @app.get("/api/tools")
    async def api_tools() -> dict[str, Any]:
        """Fleet-standard MCP tool list (WEBAPP_STANDARDS §2 /tools page)."""
        tools_out: list[dict[str, str]] = []
        try:
            tools = await mcp.list_tools(run_middleware=False)
            for t in tools:
                tools_out.append(
                    {
                        "name": t.name,
                        "description": (t.description or "").strip(),
                    }
                )
        except Exception as exc:
            return {"success": False, "tools": [], "error": str(exc)}
        return {"success": True, "tools": tools_out, "count": len(tools_out)}

    @app.get("/api/apps")
    async def api_apps() -> dict[str, Any]:
        """Fleet registry slice for /apps hub."""
        from scraper_mcp.fleet_registry import fleet_registry_path, load_fleet_repo_ids

        path = fleet_registry_path()
        apps: list[dict[str, Any]] = []
        if path.is_file():
            import json

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for row in data.get("fleet", []):
                    if not isinstance(row, dict):
                        continue
                    port = row.get("port") or 0
                    apps.append(
                        {
                            "id": row.get("id"),
                            "name": row.get("name") or row.get("id"),
                            "description": row.get("description", ""),
                            "port": port,
                            "category": row.get("category", ""),
                            "url": f"http://127.0.0.1:{port}" if port else None,
                        }
                    )
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "success": True,
            "registry_path": str(path),
            "fleet_total": len(load_fleet_repo_ids()),
            "apps": apps[:120],
        }

    @app.get("/api/llm/providers")
    async def llm_providers() -> dict:
        import httpx

        models: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:11434/api/tags")
                for m in r.json().get("models", []):
                    name = m.get("name", "")
                    if name:
                        models.append(name)
        except Exception:
            pass
        return {"providers": [{"name": "ollama", "models": models}]}

    @app.post("/api/llm/chat")
    async def llm_chat(body: dict) -> dict:
        import httpx

        model = body.get("model", "gemma3:1b")
        prompt = body.get("prompt", "")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "http://localhost:11434/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                data = r.json()
                return {"response": data.get("response", "")}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/status")
    async def api_status() -> dict[str, Any]:
        from scraper_mcp.analytics import get_coverage_matrix, get_latest

        matrix = get_coverage_matrix("sandraschi")
        latest = get_latest(owner="sandraschi")
        return {
            "status": "ok",
            "uptime": round(time.time() - _startup, 1),
            "repo_count": matrix["repo_count"],
            "platforms": matrix["platforms"],
            "latest_grades": len(latest),
        }

    skills_dir = Path(__file__).parent / "skills"

    @app.get("/api/skills")
    async def list_skills():
        skills = []
        if skills_dir.is_dir():
            for sd in skills_dir.iterdir():
                if (sd / "SKILL.md").is_file():
                    skills.append({"name": sd.name, "uri": f"/api/skills/{sd.name}"})
        return {"skills": skills}

    @app.get("/api/skills/{skill_name}")
    async def get_skill(skill_name: str):
        skill_path = skills_dir / skill_name / "SKILL.md"
        if skill_path.is_file():
            return skill_path.read_text(encoding="utf-8")
        return {"error": "Skill not found"}, 404

    @app.get("/api/trends")
    async def api_trends() -> dict:
        """Grade trends: improving (+), declining (-), or stable (=) per repo per platform."""
        from scraper_mcp.analytics import get_coverage_matrix, get_history

        matrix = get_coverage_matrix("sandraschi")
        trends = {}
        for repo, platforms in matrix["repos"].items():
            for pid in matrix["platforms"]:
                history = get_history(pid, "sandraschi", repo, limit=5)
                if len(history) < 2:
                    continue
                old = history[-1].get("score") or 0
                new = history[0].get("score") or 0
                diff = new - old
                if abs(diff) < 0.01:
                    arrow = "="
                elif diff > 0:
                    arrow = "+"
                else:
                    arrow = "-"
                trends.setdefault(repo, {})[pid] = {"arrow": arrow, "diff": round(diff, 2)}
        return {"trends": trends}

    @app.get("/api/coverage")
    async def api_coverage(owner: str = Query("sandraschi")) -> dict[str, Any]:
        from scraper_mcp.analytics import get_coverage_matrix

        return get_coverage_matrix(owner)

    @app.get("/api/coverage/{repo}")
    async def api_repo(repo: str, owner: str = Query("sandraschi")) -> dict[str, Any]:
        from scraper_mcp.analytics import get_latest

        latest = get_latest(owner=owner, repo=repo)
        return {"repo": repo, "owner": owner, "grades": latest}

    @app.post("/api/refresh")
    async def api_refresh(body: dict[str, Any] | None = None) -> dict[str, Any]:
        import time

        from scraper_mcp.analytics import upsert_grade
        from scraper_mcp.fleet_registry import load_fleet_repo_ids
        from scraper_mcp.scrapers.engine import SCRAPERS, refresh_all, refresh_single

        started = time.time()
        payload = body or {}
        repo = payload.get("repo")
        owner = payload.get("owner", "sandraschi")
        log_activity("refresh", f"grade refresh started owner={owner} repo={repo or '*'}", level="INFO")

        if repo:
            results = await refresh_single(owner, repo)
            count = 0
            per_platform: dict[str, int] = {}
            for pid, row in results.items():
                if row:
                    upsert_grade(pid, owner, repo, row.get("grade"), row.get("score"), row)
                    count += 1
                    per_platform[pid] = per_platform.get(pid, 0) + 1
            log_activity("refresh", f"single repo {repo}: {count} grades", level="INFO")
            return {
                "success": True,
                "refreshed": count,
                "repo": repo,
                "per_platform": per_platform,
                "duration_ms": int((time.time() - started) * 1000),
            }

        fleet_ids = load_fleet_repo_ids()
        results = await refresh_all(owner, fleet_ids or None)
        total = 0
        per_platform: dict[str, int] = {}
        for pid, repos_data in results.items():
            n = 0
            for row in repos_data:
                upsert_grade(pid, owner, row["repo"], row.get("grade"), row.get("score"), row)
                total += 1
                n += 1
            per_platform[pid] = n

        fleet_total = len(fleet_ids)
        duration_ms = int((time.time() - started) * 1000)
        log_activity(
            "refresh",
            f"fleet refresh: {total} remote grades across {fleet_total} fleet repos",
            level="INFO",
        )
        return {
            "success": True,
            "refreshed": total,
            "per_platform": per_platform,
            "platforms_scanned": len(SCRAPERS),
            "fleet_repos": fleet_total,
            "duration_ms": duration_ms,
            "message": (
                f"Scanned {fleet_total} fleet repos on {len(SCRAPERS)} platforms — "
                f"{total} remote hit(s) (ToolBench: {per_platform.get('toolbench', 0)}, "
                f"Glama: {per_platform.get('glama', 0)}, LobeHub: {per_platform.get('lobehub', 0)})."
            ),
        }

    @app.get("/api/badge.svg")
    async def api_badge(repo: str = "", owner: str = "sandraschi"):
        """Combined SVG score badge: ToolBench + Glama grades for a repo."""
        from scraper_mcp.analytics import get_latest

        tb_grade = "?"
        gl_grade = "?"
        if repo:
            latest = get_latest(owner=owner, repo=repo)
            for entry in latest:
                if entry["platform"] == "toolbench":
                    tb_grade = entry.get("grade") or "?"
                elif entry["platform"] == "glama":
                    gl_grade = entry.get("grade") or "?"

        def grade_color(g: str) -> str:
            return {
                "A+": "#2ea44f",
                "A": "#2ea44f",
                "B": "#0969da",
                "C": "#d4a72c",
                "D": "#d93f21",
                "F": "#cf222e",
            }.get(g, "#6e7681")

        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="220" height="20">
  <linearGradient id="b" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <rect rx="3" width="220" height="20" fill="#555"/>
  <rect rx="3" x="85" width="70" height="20" fill="{grade_color(tb_grade)}"/>
  <rect rx="3" x="155" width="65" height="20" fill="{grade_color(gl_grade)}"/>
  <rect fill={'"#url(#b)"'} width="220" height="20"/>
  <text x="6" y="14" fill="#fff" font-family="DejaVu Sans,sans-serif" font-size="11" font-weight="bold">scraper</text>
  <text x="92" y="14" fill="#fff" font-family="DejaVu Sans,sans-serif" font-size="11" font-weight="bold">TB {tb_grade}</text>
  <text x="162" y="14" fill="#fff" font-family="DejaVu Sans,sans-serif" font-size="11" font-weight="bold">GL {gl_grade}</text>
</svg>'''
        from fastapi.responses import Response

        return Response(content=svg, media_type="image/svg+xml")

    @app.post("/api/scraper/fix/{repo}")
    async def api_fix_repo(
        repo: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply safe mechanical fixes based on ToolBench criticism."""
        from scraper_mcp.mcp.tools.autofix import (
            apply_docstring_expansions,
            apply_range_constraints,
            fix_docstrings,
            fix_range_constraints,
        )
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        payload = body or {}
        fix_types = payload.get("fix_types", ["description", "range"])
        do_apply = payload.get("apply", False)

        detail = await fetch_grade_with_details("sandraschi", repo)
        if not detail:
            return {"success": False, "message": f"{repo}: not found on ToolBench"}

        issues = detail.get("top_issues", [])
        repo_path = Path(r"D:\Dev\repos") / repo

        results = {}
        if "description" in fix_types:
            if do_apply:
                results["description"] = await apply_docstring_expansions(repo_path)
            else:
                results["description"] = await fix_docstrings(repo_path)
        if "range" in fix_types:
            if do_apply:
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
            "message": f"{'Applied' if do_apply else 'Scanned'} {repo}: {total} fix opportunities",
            "fixes": results,
            "issues": issues[:5],
            "applied": do_apply,
        }

    @app.get("/api/export")
    async def api_export(owner: str = "sandraschi"):
        """Export all grades as JSON for CI pipelines."""
        from scraper_mcp.analytics import get_coverage_matrix, get_latest

        latest = get_latest(owner=owner)
        matrix = get_coverage_matrix(owner)
        return {
            "exported_at": time.time(),
            "owner": owner,
            "repo_count": matrix["repo_count"],
            "grades": [
                {
                    "platform": e["platform"],
                    "repo": e["repo"],
                    "grade": e["grade"],
                    "score": e["score"],
                    "fetched_at": e["fetched_at"],
                }
                for e in latest
            ],
        }

    app.include_router(build_meta_router())
    app.include_router(build_scraper_router())
    app.include_router(build_logs_router())

    app.mount("/mcp", mcp_http)
    return app


app = build_app()
