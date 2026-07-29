# scraper-mcp — SPEC

> Multi-platform MCP server grade aggregator. Monitors fleet repo coverage and grades across
> ToolBench (Arcade.dev, primary), LobeHub Marketplace (presence probe only), and Glama.ai
> (**disabled** since the 2026-07 site redesign, needs a parser rewrite).

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
| `scraper_reassess` | MUTATING | **NOT IMPLEMENTED for ToolBench.** No programmatic submit endpoint is known, so it logs a warning, returns False, and points at the manual `/tools` submit flow. Glama and LobeHub return False by design. |
| `scraper_improve_suggest` | MUTATING | LLM-powered code fix suggestions |
| `scraper_improvement_plan` | READ_ONLY | Prioritized fix list from ToolBench findings |
| `scraper_status` | READ_ONLY | Server health, last refresh, platform status |
| `scraper_help` | READ_ONLY | Multi-level help |
| `scraper_platforms` | READ_ONLY | List available grading platforms |
| `scraper_shutdown` | DESTRUCTIVE | Graceful server shutdown |
| `show_matrix_card` | READ_ONLY | Prefab card: coverage matrix |
| `show_status_card` | READ_ONLY | Prefab card: platform health |

## ToolBench Data Integrity

Two behaviours exist specifically to stop wrong data being persisted. Both are load-bearing.

**Two-stage owner resolution.** `/api/servers?q=<repo>` returns bare slug names with **no owner
field**, and names collide across authors (a single query returned three unrelated servers all named
`scraper-mcp`). Matching by name alone attributes strangers' grades to fleet repos. So:

1. `_find_candidates()` returns every name-matching server, not the first.
2. For each candidate, fetch `/tools/{id}` and read the GitHub owner from the header link via
   `_owner_from_soup()`.
3. Accept only the candidate whose owner is the fleet owner. Otherwise record `not_indexed`.
4. Resolved owners are cached in `_server_owner_cache`, so this costs one page fetch per server per
   process lifetime.

Introducing this dropped ToolBench coverage from 52 to 22 repos. The 30 removed rows were other
people's servers.

**Dimension reconciliation.** Published weighting is
`0.5*Definition + 0.2*Protocol + 0.3*Supportability ≈ overallScore`. `_dimensions_reconcile()`
checks this with tolerance 1.5. On failure the dimensions are stored as `None` and a warning is
logged. A missing dimension is recoverable, a wrong one silently mis-ranks the improvement worklist.

**KNOWN LIMITATION (open):** `_extract_pct` currently returns the same value for all three
dimensions on real pages, because `text.find(label)` anchors on the methodology blurb at the top of
the page rather than the score row. Reconciliation rejects the result, so nothing wrong is stored,
but there is no usable dimension data at present. Fix by anchoring on the per-row method strings
(`Pattern-based scoring`, `Static analysis`, `GitHub signals`). Consumers should rank by
`overallScore` only until this lands.

**Rate limiting.** Concurrency 3, plus a 0.5s delay with 0.3s jitter applied after each repo,
outside the semaphore, so pacing is independent of concurrency. Failed fetches produce rows with
`status="fetch_error"` and are never silently dropped.

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
