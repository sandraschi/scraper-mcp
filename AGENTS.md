# scraper-mcp Agent Context

Fleet MCP server — **replaces toolbench-mcp** (ports 10816/10817 → 10998/10999).

## Scope

- Multi-platform grades: ToolBench, Glama, LobeHub (`scraper_*` MCP tools, SQLite history)
- ToolBench-only extras ported from toolbench-mcp: `toolbench_guide`, `scripts/scrape_toolbench_assessments.py`, `/api/scraper/*`, webapp `/tools` + `/logs`

Do not re-add a separate toolbench-mcp scraper stack; extend here.

## Quick Ref

```powershell
uv sync --extra dev
uv run pytest tests/ -q
.\start.ps1                    # or webapp\start.ps1 (FleetStartMode)
uv run python -m scraper_mcp.server --http --port 10998
```

Optional Playwright archiver: `uv sync --extra scraper` then `playwright install chromium`

## Key paths

- `src/scraper_mcp/app.py` — FastAPI app (health, capabilities, coverage, MCP mount, `/api/trends`)
- `src/scraper_mcp/scraper_api.py` — ToolBench Playwright subprocess API
- `src/scraper_mcp/mcp/tools/guide.py` — `toolbench_guide`
- `src/scraper_mcp/mcp/tools/suggest.py` — `scraper_improve_suggest` (+ llm-gateway integration)
- `src/scraper_mcp/mcp/tools/improvement.py` — `scraper_improvement_plan`
- `src/scraper_mcp/mcp/tools/status.py` — `scraper_status`
- `src/scraper_mcp/mcp/tools/helptool.py` — `scraper_help`
- `webapp/src/pages/tools.tsx` — archiver UI

## Cross-connect

- **llm-gateway**: set `LLM_GATEWAY_URL`, `LLM_GATEWAY_PROVIDER`, `LLM_GATEWAY_MODEL` for AI-powered suggestions
- **aiwatcher-mcp**: grade drop alerts POST to `AIWATCHER_URL` (default http://127.0.0.1:10946/api/fleet/event)
- Threshold: `SCRAPER_ALERT_THRESHOLD` (default B)
