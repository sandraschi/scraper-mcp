"""FastAPI backend: fleet grade aggregator + ToolBench archiver (replaces toolbench-mcp)."""

from __future__ import annotations

import time
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

    mcp_http = mcp.http_app(path="/mcp")
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
            "*",
        ],
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

    app.include_router(build_meta_router())
    app.include_router(build_scraper_router())
    app.include_router(build_logs_router())

    app.mount("/mcp", mcp_http)
    return app


app = build_app()
