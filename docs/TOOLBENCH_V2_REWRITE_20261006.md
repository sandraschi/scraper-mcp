# ToolBench v2 assessment parser — spec + build log (2026-10-06)

## Why

ToolBench shipped a rubric change (v1 → v2, visible in Score history: 2026-03-09
67/100·v1 → 2026-09-22 68/100·v2) and with it a Next.js flight-data redesign of
`/tools/{id}` pages. The v1 parser (method-string anchors `Pattern-based scoring`
etc.) returns all-None on live pages: 0 occurrences, 0 tools, 0 issues.
Verified live 2026-10-06 on `tools/cmmjaiup2042usb9t2r4bjype` (same server as the
committed v1 fixture, so old-vs-new is directly comparable).

NOT bot-walling: HTTP 200, real content, title intact. The strings are present
(both SSR'd DOM fragments and `self.__next_f.push` flight payloads), so
text-pattern parsing on flattened page text is the robust primary — same lesson
as the Glama hashed-class drift: anchor on data strings, not markup.

## New anchors (verified against live snapshot)

- Header strip (single regex, one match):
  `6 tools C 68 /100 Definition Quality 70 Protocol Readiness 82 Supportability 54`
  (spaces: flattened page text joins with spaces — the first implementation
  wrongly assumed pipes and returned all-None until the suite caught it).
  Pattern: `(\d+)\s*\|\s*/100\s*\|\s*Definition Quality\s*\|\s*(\d+)\s*\|\s*Protocol Readiness\s*\|\s*(\d+)\s*\|\s*Supportability\s*\|\s*(\d+)`
  → overall, definition, protocol, supportability. The grade letter is
  deliberately NOT captured (A.2 gate: grade comes from the API only).
- Score history: `2026-09-22: 68/100 (C) · v2 rubric` entries.
  Pattern: `(\d{4}-\d{2}-\d{2}):\s*(\d+)/100\s*\(([A-Z]\+?)\)\s*·\s*(v\d+)\s*rubric`
  → list of {date, score, grade, rubric}; newest = current; rubric tag enables
  rubric-change detection for the digest.
- Tool rows: `Tools (6)` + `tool_extract_links read only source verified 72 /100 <desc>`.
  Pattern per row, scoped to text after the `Tools (N)` marker so header and
  score-history numbers can never match as tool rows; flight-payload repeats deduped.
- Issues: real DOM `span.sev/sev-high/sev-med` inside `div.issue-head` (SSR'd) —
  DOM-first, text fallback. Existing policy kept (cap 10, min length 30).
- Reconciliation formula UNCHANGED: 0.5*70 + 0.2*82 + 0.3*54 = 67.6 ≈ 68 ✓.

## Gates preserved

- A.2: grade never scraped from page (API via `resolve_grade` only).
- Reconcile-or-None: dims that fail the weighted sum are stored as None.
- Owner verification path untouched.
- `tool_details` schema `{name, tool_score}` untouched (GAP 7).

## What changed

- `toolbench_score.py`: v2 header/history/tools/issues parsing in
  `_parse_assessment_data` (signature unchanged); `_DIMENSION_METHOD_STRINGS`
  removed (v1 anchors dead); `_extract_pct` kept as tested utility.
- `engine.py`: `score_history`, `rubric` added to `_normalize_row` pass-through.
- Fixture: `tools_cmmjaiup2042usb9t2r4bjype_20261006.html` added (live snapshot);
  loader takes newest `tools_*.html`; v1 fixture retained as history.
- Tests: 3 updated to v2 values/path, ~6 added (header exact, history, tools,
  issues, owner on new fixture, no-grade on new path). Synthetic `_extract_pct`
  unit tests kept.
