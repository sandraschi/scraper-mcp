# Changelog

## 2026-06-30

- Add llm-gateway integration: `scraper_improve_suggest(use_llm=True)` routes through LLM_GATEWAY_URL for AI-powered code fixes
- Add grade drop alerts: `scraper_refresh()` POSTs to aiwatcher-mcp when a repo falls below SCRAPER_ALERT_THRESHOLD
- Add `GET /api/trends` endpoint returning grade direction (+/-/=) per repo per platform
- Add `just daily-refresh` and `just register-daily-refresh` recipes
- Add `scraper_status` and `scraper_help` MCP tools
- Sortable/filterable dashboard with staleness coloring, SVG badges, JSON export
- Per-tool TDQS dimension bars in repo detail view
