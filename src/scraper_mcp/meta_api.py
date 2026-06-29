"""Fleet metadata: MCP tool surface, local LLM Glom On probe."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "toolbench_guide",
        "description": "Curated ToolBench context (links, rescoring, Glama vs ToolBench, Arcade product).",
        "risk": "read",
        "operations": [
            "get_help",
            "list_official_links",
            "rescoring_after_improvements",
            "glama_vs_toolbench",
            "arcade_mcp_product",
        ],
    },
    {
        "name": "scraper_refresh",
        "description": "Refresh grades on all platforms for fleet owner.",
        "risk": "write",
        "operations": ["refresh_all"],
    },
    {
        "name": "scraper_matrix",
        "description": "Coverage matrix repos × platforms.",
        "risk": "read",
        "operations": ["get_matrix"],
    },
    {
        "name": "scraper_repo",
        "description": "Per-repo grade report + history.",
        "risk": "read",
        "operations": ["get_repo", "get_history"],
    },
    {
        "name": "scraper_reassess",
        "description": "Request rescoring where supported.",
        "risk": "write",
        "operations": ["reassess"],
    },
    {
        "name": "scraper_platforms",
        "description": "List grading platforms.",
        "risk": "read",
        "operations": ["list_platforms"],
    },
]


def build_router() -> APIRouter:
    r = APIRouter(prefix="/api/meta", tags=["meta"])

    @r.get("/tools")
    async def tools() -> dict[str, Any]:
        return {"success": True, "tools": MCP_TOOLS, "transport": {"stdio": True, "http": "/mcp"}}

    @r.get("/local-llm")
    async def local_llm_status() -> dict[str, Any]:
        """Glom On: probe Ollama + LM Studio default ports (WEBAPP_STANDARDS §3)."""
        out: dict[str, Any] = {"ollama": None, "lm_studio": None}

        async def ping(url: str, timeout: float = 1.2) -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    r2 = await client.get(url)
                    return {"ok": r2.status_code < 500, "status_code": r2.status_code}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        ollama, lm = await asyncio.gather(
            ping("http://127.0.0.1:11434/api/tags"),
            ping("http://127.0.0.1:1234/v1/models"),
        )
        out["ollama"] = ollama
        out["lm_studio"] = lm
        return out

    return r
