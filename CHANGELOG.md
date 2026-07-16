# Changelog

## 2026-07-14 — update docs

- Add framer-motion + zustand to webapp deps (fleet standard)
- Add Playwright E2E tests (4 tests: health, frontend loads, no console errors, nav)
- Add data-testid to all 7 pages (platforms, tools, logs, apps, help, settings, repo-detail)
- Add show_matrix_card() and show_status_card() Prefab tools
- Add scraper_workflow() and toolbench_rescore() prompts
- Add grade_help_resource() MCP resource
- Add skills directory with SKILL.md + GET /api/skills endpoints
- Add .github/workflows/ci.yml (ruff + pytest)
- Fix e2e just recipe to point at Playwright
- Fix ruff lint in new files (N806, F401, F841, import sort)
- Update README: add new tools, CI badge, E2E, clean up formatting
- Update SPEC.md: add all 12 tools, mark Tauri as done
- Update llms-full.txt: add new tools and skills endpoints
- Sync mcd project page with new tools

- Fix CORS `["*"]` → fleet standard origins + unconditional regex (CRITICAL)
- Add .env.example, .cursorrules, CLAUDE.md, llms.txt, llms-full.txt, glama.json
- Add scraper_shutdown self-termination MCP tool
- Add .mcpbignore, fix .gitignore for *.mcpb and *.bak
- Add useZoom() hook for Ctrl+Scroll zoom (Tauri + CSS fallback)
- Add `certify` and `mcpb-pack` just recipes
- Fix ruff lint (import sort, unused vars, f-strings, missing import os)
- Run ruff format across 12 source files
- Fix tauri.conf.json resources to include .env.example
- Fix server.py missing `import os`

## 2026-06-30

- Add llm-gateway integration: `scraper_improve_suggest(use_llm=True)` routes through LLM_GATEWAY_URL for AI-powered code fixes
- Add grade drop alerts: `scraper_refresh()` POSTs to aiwatcher-mcp when a repo falls below SCRAPER_ALERT_THRESHOLD
- Add `GET /api/trends` endpoint returning grade direction (+/-/=) per repo per platform
- Add `just daily-refresh` and `just register-daily-refresh` recipes
- Add `scraper_status` and `scraper_help` MCP tools
- Sortable/filterable dashboard with staleness coloring, SVG badges, JSON export
- Per-tool TDQS dimension bars in repo detail view
