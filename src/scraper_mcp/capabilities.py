"""Build /api/capabilities from the mounted FastMCP instance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx


async def build_capabilities(mcp: Any, *, version: str = "0.2.0") -> dict[str, Any]:
    tool_names: list[str] = []
    try:
        tools = await mcp.list_tools(run_middleware=False)
        tool_names = sorted({t.name for t in tools})
    except Exception:
        tool_names = ["toolbench_guide"]

    portmanteau_tools = [n for n in tool_names if n.startswith("scraper_") or n == "toolbench_guide"]
    atomic_tools = [n for n in tool_names if n not in portmanteau_tools]

    prompt_names: list[str] = []
    try:
        prompts = await mcp.list_prompts()
        prompt_names = sorted({p.name for p in prompts})
    except Exception:
        prompt_names = []

    resource_uris: list[str] = []
    skill_uris: list[str] = []
    try:
        resources = await mcp.list_resources()
        for resource in resources:
            raw = getattr(resource, "uri", None) or getattr(resource, "name", "")
            uri = str(raw) if raw else ""
            if not uri:
                continue
            resource_uris.append(uri)
            if uri.startswith("skill://"):
                skill_uris.append(uri)
    except Exception:
        resource_uris = []
        skill_uris = []

    local_llm = False
    try:
        async with httpx.AsyncClient(timeout=1.2) as client:
            ollama = await client.get("http://127.0.0.1:11434/api/tags")
            lm = await client.get("http://127.0.0.1:1234/v1/models")
            local_llm = ollama.status_code < 500 or lm.status_code < 500
    except Exception:
        local_llm = False

    return {
        "status": "ok",
        "server": {"name": "scraper-mcp", "version": version, "fastmcp": "3.2+"},
        "tool_surface": {
            "total": len(tool_names),
            "portmanteau_count": len(portmanteau_tools),
            "atomic_count": len(atomic_tools),
            "portmanteau_tools": portmanteau_tools,
            "atomic_tools": atomic_tools,
        },
        "features": {
            "sampling": False,
            "agentic_workflows": False,
            "prompts": len(prompt_names) > 0,
            "resources": len(resource_uris) > 0,
            "skills": len(skill_uris) > 0,
            "local_llm": local_llm,
            "local_llm_autodiscovery": True,
            "scraper_api": True,
        },
        "inventory": {
            "workflow_tools": [],
            "prompt_names": prompt_names,
            "resource_uris": sorted(resource_uris),
            "skill_uris": sorted(skill_uris),
        },
        "runtime": {
            "transport": "http",
            "surface_mode": "portmanteau",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
