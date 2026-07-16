# scraper-mcp — SPEC

> Multi-platform MCP server grade aggregator. Monitors fleet repo coverage and grades across ToolBench (Arcade.dev), Glama.ai, and LobeHub Marketplace.

## Components

| Component | Technology | Port |
|---|---|---|
| Backend | FastMCP 3.2 + FastAPI | 10998 |
| Frontend | Vite 5 + React 18 + Tailwind 3 | 10999 |
| Analytics | SQLite (grades + history) | local file |
| Scrapers | httpx-based HTTP + JSON parsers | N/A |

## Tool Surface

| Tool | Type | Description |
|---|---|---|
| `scraper_refresh` | MUTATING | Scan all platforms, persist grades |
| `scraper_matrix` | READ_ONLY | Coverage matrix: repos x platforms |
| `scraper_repo` | READ_ONLY | Single-repo grade detail + history |
| `scraper_reassess` | MUTATING | Request rescoring on platforms |
| `scraper_improve_suggest` | MUTATING | LLM-powered code fix suggestions |
| `scraper_improvement_plan` | READ_ONLY | Prioritized fix list from ToolBench findings |
| `scraper_status` | READ_ONLY | Server health, last refresh, platform status |
| `scraper_help` | READ_ONLY | Multi-level help |
| `scraper_platforms` | READ_ONLY | List available grading platforms |
| `scraper_shutdown` | DESTRUCTIVE | Graceful server shutdown |
| `show_matrix_card` | READ_ONLY | Prefab card: coverage matrix |
| `show_status_card` | READ_ONLY | Prefab card: platform health |

## Architecture

```
webapp (Vite React, :10999)
  └── /api/* ──► backend (Starlette + FastMCP, :10998)
                    ├── /mcp ──► FastMCP Streamable HTTP (MCP tools)
                    ├── /api/coverage ──► analytics.get_coverage_matrix()
                    ├── /api/coverage/{repo} ──► analytics.get_latest()
                    └── /api/refresh ──► scrapers.engine.refresh_all()

scrapers/
  engine.py          — BaseScraper + 3 platform implementations
  analytics.py       — SQLite grade persistence + delta tracking

Plug in new graders: subclass BaseScraper, register in SCRAPERS dict.
```

## Modular Scraper Interface

```python
class BaseScraper:
    id: str           # platform identifier
    name: str         # human-readable
    base_url: str     # API base

    async fetch_coverage(owner: str) -> list[dict]
    async fetch_grade(owner: str, repo: str) -> dict | None
    async request_reassess(owner: str, repo: str) -> bool
```

## To Do (v0.2+)

- [x] Grade alerting: notify when a fleet repo drops below B on any platform
- [x] llm-gateway integration for AI-powered improvement suggestions
- [x] Trend API (`GET /api/trends`) with grade direction tracking
- [ ] NVIDIA-AI co new scraping agent via `@mcp.tool(sampling=True)` for AG2.0 spec-awareness
- [ ] Clickhouse-scorer modularity: independent grader quality scoring via separate service
- [x] Tauri 2.0 native wrapper (system tray grade monitor)
- [ ] Trend chart in webapp dashboard (frontend for `/api/trends`)
