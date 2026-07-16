"""CLI entry: HTTP (FastAPI) or stdio MCP."""

from __future__ import annotations

import argparse
import os

import uvicorn

from scraper_mcp.config import settings


def build_app():
    """Backward-compatible alias for tests."""
    from scraper_mcp.app import build_app as _build

    return _build()


def main() -> None:
    proxy_url = os.getenv("SCRAPER_MCP_API_URL", "http://127.0.0.1:10998/mcp")
    try:
        import httpx

        r = httpx.post(
            proxy_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "1"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
            timeout=0.5,
        )
        if r.status_code == 200:
            from fastmcp.server import create_proxy

            proxy = create_proxy(proxy_url, name="scraper-mcp")
            proxy.run(transport="stdio")
            return
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="scraper-mcp server")
    parser.add_argument("--http", action="store_true", help="Run FastAPI HTTP server (default)")
    parser.add_argument("--stdio", action="store_true", help="MCP stdio transport")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    args = parser.parse_args()

    if args.stdio:
        from scraper_mcp.mcp import tools as _  # noqa: F401
        from scraper_mcp.mcp.registry import mcp

        mcp.run(transport="stdio")
        return

    from scraper_mcp.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
