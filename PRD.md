# scraper-mcp — Product Requirements

**Version**: 0.2.0 (2026-07-29)
**Status**: Active

## Purpose

Multi-platform MCP grade aggregator for the fleet. Scrapes, parses, and stores MCP server grades from ToolBench (Arcade.dev), Glama.ai, and LobeHub. Provides MCP tools and a FastAPI webapp for querying coverage, trends, improvement suggestions, and reassessment triggers.

Replaces the standalone `toolbench-mcp` server (ports 10816/10817) on ports 10998/10999.

## Architecture

```
scraper_* MCP tools ←→ FastAPI app (10998) ←→ parsers (toolbench_score, glama_score, engine)
                               ↕
                         SQLite (grades.db)
                               ↕
                    Vite React webapp (10999)
```

Three pluggable scrapers in `src/scraper_mcp/scrapers/engine.py`:
- `ToolBenchScraper` — HTTP parser for /api/servers and /tools/{id} pages
- `GlamaScraper` — disabled (site redesign 2026-07)
- `LobeHubScraper` — URL probe (no grades available)

## Shipped Features

| Area | Features |
|------|----------|
| **ToolBench scraping** | /api/servers lookup, /tools/{id} parse, dimension scores, top issues, tool risk, grade resolution, polite concurrency |
| **Glama scraping** | Pre-2026-07 redesign parser (now disabled) |
| **LobeHub scraping** | URL existence probe |
| **Analytics** | SQLite grades DB with upsert + history, coverage matrix, trends API |
| **MCP tools** | scraper_refresh, scraper_matrix, scraper_repo, scraper_reassess, scraper_improve_suggest, scraper_improvement_plan, scraper_status, scraper_help, scraper_platforms, toolbench_guide, scraper_shutdown, show_matrix_card, show_status_card |
| **Webapp** | Dashboard with KPIs, coverage matrix, per-repo detail, tools list, themes |
| **Fleet integration** | aiwatcher-mcp alerts, llm-gateway for suggestion generation |

## Non-Goals

- Playwright-based scraping (the ToolBench site is server-rendered)
- Scoring API access approval (nice-to-have, not blocking)
- Live multi-platform calibration experiment (Part C of uplift plan, pending)

## Known Gaps

- Glama scraper broken due to site redesign (2026-07)
- ToolBench name matching has 19 known mismatches (e.g. `inkscape-mcps`)
- Some repos not indexed on any platform
- No WebSocket/live updates — all data is polled

## Status

- **v0.1.0** (2026-06-30) — Initial port from toolbench-mcp
- **v0.2.0** (2026-07-29) — Parser fixes (dimension scores, grade resolution, concurrency, name matching), test suite, fleet LICENSE sweep
