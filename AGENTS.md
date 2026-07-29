# scraper-mcp Agent Context

Fleet MCP server — **replaces toolbench-mcp** (ports 10816/10817 → 10998/10999).

## Scope

- Multi-platform grades: ToolBench (primary), LobeHub (probe only), ~~Glama~~ (disabled — site redesign 2026-07)
- ToolBench-only extras ported from toolbench-mcp: `toolbench_guide`, `/api/scraper/*`, webapp `/tools` + `/logs`

Do not re-add a separate toolbench-mcp scraper stack; extend here.

## Quick Ref

```powershell
uv sync --extra dev
uv run pytest tests/ -q          # 36 tests
.\start.ps1
uv run python -m scraper_mcp.server --http --port 10998
```

## Key paths

- `src/scraper_mcp/app.py` — FastAPI app (health, capabilities, coverage, MCP mount, `/api/trends`)
- `src/scraper_mcp/scrapers/toolbench_score.py` — ToolBench API + HTML parser (grade_from_score, _match_server, _extract_pct)
- `src/scraper_mcp/scrapers/engine.py` — 3 scraper classes + SCRAPERS registry + refresh_all/refresh_single
- `src/scraper_mcp/scrapers/glama_score.py` — BROKEN (site redesign; GlamaScraper disabled in engine.py)
- `src/scraper_mcp/mcp/tools/` — 13 MCP tools (coverage, guide, suggest, improvement, status, helptool, cards, platforms, shutdown)
- `tests/test_toolbench_parser.py` — 26 parser regression tests with fixtures
- `tests/fixtures/toolbench/` — Live API + HTML fixtures
- `docs/TOOLBENCH_UPLIFT_PLAN_20260729.md` — Active uplift plan (Part A DONE)

## Cross-connect

- **llm-gateway**: set `LLM_GATEWAY_URL`, `LLM_GATEWAY_PROVIDER`, `LLM_GATEWAY_MODEL` for AI-powered suggestions
- **aiwatcher-mcp**: grade drop alerts POST to `AIWATCHER_URL` (default http://127.0.0.1:10946/api/fleet/event)
- Threshold: `SCRAPER_ALERT_THRESHOLD` (default B)

## Current State (2026-07-29)

- All Part A parser bugs FIXED: dimension scores, grade regex, doubled API call, reassess stub, name matching
- Glama scraper DISABLED due to site redesign
- Fleet LICENSE sweep DONE (210/211 Python repos)
- Full fleet refresh: 52/150 ToolBench-indexed, mean 40.7, 0 fetch errors
- Tests: 36 passing, ruff clean

