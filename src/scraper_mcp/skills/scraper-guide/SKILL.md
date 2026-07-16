# Scraper MCP — Fleet Grade Aggregator

## Purpose
Monitors 80+ sandraschi fleet MCP repos across ToolBench, Glama.ai, and LobeHub.
Tracks grade changes over time and alerts when scores drop.

## Tools

### Coverage & Grades
- `scraper_matrix(owner)` — coverage matrix: repos x platforms with grade badges
- `scraper_repo(repo, owner)` — single-repo detail with history and TDQS dims
- `scraper_refresh(repo, owner)` — pull fresh grades from all platforms
- `scraper_reassess(repo, platform)` — request rescoring

### Improvements
- `scraper_improve_suggest(repo, use_llm)` — LLM-powered code fix suggestions
- `scraper_improvement_plan(repo)` — prioritized fix list from ToolBench findings

### System
- `scraper_status()` — server health, last refresh, platform status
- `scraper_help(level)` — multi-level help
- `scraper_platforms(operation)` — list/info/add grading platforms
- `shutdown()` — graceful server shutdown

### Prefab Cards
- `show_matrix_card(owner)` — rich card: repos x platforms with grades
- `show_status_card()` — rich card: platform health + grade distribution

### ToolBench Guide
- `toolbench_guide(operation)` — ToolBench links, rescoring, Glama contrast

## Best Practices
1. Start with `scraper_status()` to check freshness
2. Use `scraper_matrix()` for the big picture
3. `scraper_refresh()` before making decisions on stale data
4. Flag drops by setting `SCRAPER_ALERT_THRESHOLD`
