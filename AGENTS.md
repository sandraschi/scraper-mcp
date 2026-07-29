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
- `src/scraper_mcp/scrapers/toolbench_score.py` — ToolBench API + HTML parser. Key functions:
  `grade_from_score`, `resolve_grade`, `_find_candidates`, `_owner_from_soup`,
  `_dimensions_reconcile`, `_extract_pct`, `fetch_grade_with_details` (two-stage owner-verified)
- `src/scraper_mcp/scrapers/engine.py` — 3 scraper classes + SCRAPERS registry + refresh_all/refresh_single
- `src/scraper_mcp/scrapers/glama_score.py` — BROKEN (site redesign; GlamaScraper disabled in engine.py)
- `src/scraper_mcp/mcp/tools/` — 13 MCP tools (coverage, guide, suggest, improvement, status, helptool, cards, platforms, shutdown)
- `tests/test_toolbench_parser.py` — 26 parser regression tests with fixtures
- `tests/fixtures/toolbench/` — Live API + HTML fixtures
- `docs/TOOLBENCH_UPLIFT_PLAN_20260729.md` — **ACTIVE PLAN. Read this before touching the scraper or
  running any fleet codemod.** Start at section 0 (TL;DR) and the Progress log at the end.

## Cross-connect

- **llm-gateway**: set `LLM_GATEWAY_URL`, `LLM_GATEWAY_PROVIDER`, `LLM_GATEWAY_MODEL` for AI-powered suggestions
- **aiwatcher-mcp**: grade drop alerts POST to `AIWATCHER_URL` (default http://127.0.0.1:10946/api/fleet/event)
- Threshold: `SCRAPER_ALERT_THRESHOLD` (default B)

## Current State (2026-07-29 05:35)

**Trustworthy:** grade, overallScore, status, transport, toolCount. All come from
`/api/servers` and are now owner-verified.

**NOT trustworthy: dimension scores.** `_extract_pct` anchors on `text.find(label)`, which lands on
the methodology blurb at the top of every assessment page ("Scored on Definition Quality (50%),
Protocol Readiness (20%), and Supportability (30%)"). The forward scan then skips every `%`-suffixed
number and returns the first bare score it meets, which is always Definition's. **All three
dimensions come back identical.** On our own fixture, true values 79/80/38 parse as 79/79/79.
`_dimensions_reconcile` catches this and stores None, so nothing wrong is persisted, but there is
currently **no usable dimension data**. Fix: anchor on the per-row method strings
(`Pattern-based scoring`, `Static analysis`, `GitHub signals`), which occur exactly once each.
Do not use `rfind`. See REVIEW 2 in the uplift plan.

**Part A status:** A.1 partial (grade path fixed, dimension path still wrong), A.2 done, A.3 done
(reassess honestly returns False, no programmatic submit endpoint known), A.4 done (single API call,
concurrency 3, delay 0.5s + jitter 0.3s, `fetch_error` rows), A.5 done (two-stage owner verification
via the GitHub link in the assessment page header, cached in `_server_owner_cache`), A.6 moot
(Glama disabled).

**Fleet refresh (owner-verified, 2026-07-29 05:25):** ToolBench 22/150 indexed, D:4 F:18, mean 32.8.
Glama disabled. LobeHub 0/150. The earlier 52/150 figure was wrong: 30 of those rows were other
people's servers matched by bare name collision. Do not quote 52 or mean 40.7 anywhere.

**Fleet denominator unreconciled:** 150 from the registry, 211 Python repos on disk, ~128 public on
GitHub. Coverage percentages are meaningless until `load_fleet_repo_ids()` is reconciled against the
authenticated GitHub repo list.

**Strategy note:** only 22 fleet repos are indexed, so the F-list is 18, not 37. The rest have no
public grade at all. Fix the 22 visible ones and run the Part C calibration on them first. Submitting
an unfixed repo turns "not listed" into "publicly graded F". An unindexed repo costs nothing.

**Other:** Glama scraper disabled (site redesign 2026-07, needs a rewrite). Fleet LICENSE sweep done
for 210/211 Python repos; topics, descriptions, homepages and tagged releases still outstanding.
Tests 36 passing, ruff clean, but note the parser value assertions run on synthetic strings, so the
suite does not currently catch the dimension bug.

