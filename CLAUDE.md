# scraper-mcp — Agent Guide

## Overview
FastMCP 3.2 fleet server: grade aggregator for ToolBench, Glama, LobeHub.
Replaces deprecated toolbench-mcp.

## Entry Points
- `uv run python -m scraper_mcp.server --http --port 10998` — HTTP mode
- `uv run python -m scraper_mcp.server --stdio` — stdio mode

## Key Files
- `src/scraper_mcp/app.py` — FastAPI app (health, CORS, routes)
- `src/scraper_mcp/mcp/tools/` — 8 MCP tools
- `src/scraper_mcp/scrapers/engine.py` — platform scrapers
- `src/scraper_mcp/analytics.py` — SQLite grade store
- `webapp/src/pages/` — 8 React pages

## Ports
- Backend: 10998 (FastAPI + FastMCP /mcp)
- Frontend: 10999 (Vite + React)

## Standards
- FastMCP >=3.4.2 dual transport (stdio + HTTP)
- Pydantic v2, Annotated+Field for params
- No Args: blocks in docstrings
