# ToolBench Uplift Plan (F -> D or better)

**Created:** 2026-07-29 03:45 CET
**Owner:** sandraschi
**Status:** ACTIVE
**Tags:** [scraper-mcp, toolbench, fleet, mcp, plan, high]
**Audience:** Cursor / OpenCode agents. Read this before touching `scraper-mcp` or running a fleet codemod.

> Source of this document: analysis session with Claude on 2026-07-29. Everything marked VERIFIED was
> checked against live sources or local files. Everything marked HYPOTHESIS is not yet confirmed and
> must be tested, not assumed. Do not silently promote a HYPOTHESIS to a fact.

---

## 0. TL;DR for an agent picking this up cold

1. `scraper-mcp` almost certainly has corrupt grade data in `src/data/grades.db`. Fix the parser
   (Part A) BEFORE any fleet work. Every prioritisation decision depends on that data.
2. The single biggest score lever is NOT docstring quality. It is transport type (STDIO caps the
   Protocol dimension at 50) and Supportability hygiene (56 of 100 public repos have no LICENSE).
3. Do not batch a 100-repo codemod on a guess. Run the 4-repo calibration experiment (Part C) first.
4. Fleet rule applies: all means all, no subsampling. If a step cannot cover every repo, stop and
   report, do not silently do a subset.

---

## 1. Ground truth: how ToolBench scores a local server

VERIFIED from https://toolbench.arcade.dev/methodology on 2026-07-29.

Local (GitHub repo, source visible) weighting:

| Dimension           | Weight | What it measures |
|---------------------|--------|------------------|
| Definition Quality  | 50%    | Per-tool naming (verb-first), description quality, parameter schema completeness. Average of all per-tool scores. Tools with no visible input schema score ZERO on that sub-dimension. |
| Protocol Compliance | 20%    | Transport type is the primary signal. HTTP can reach 100. STDIO-only is CAPPED AT 50. Also tool registration correctness and MCP error handling. Optional capabilities (prompts, resources, logging, sampling) are detected and displayed but do NOT affect score. |
| Supportability      | 30%    | Stars, open-source license, last push date, org vs individual owner, contributor count, release history, fork status, documentation, commercial support indicators. |

Remote servers use a different model (Protocol 40 / Security 30 / Support 30). Not relevant to us,
all fleet repos are local.

Grade thresholds: A+ >= 90, A >= 80, B >= 70, C >= 60, D >= 50, F < 50.

### 1.1 The arithmetic that decides strategy

Overall = 0.5 * DefinitionQuality + 0.2 * Protocol + 0.3 * Supportability

| Transport  | Protocol contribution | Supportability | Definition Quality needed to reach 50 (D) |
|------------|-----------------------|----------------|-------------------------------------------|
| STDIO only | 50 -> 10 pts          | 30 -> 9 pts    | **62** |
| STDIO only | 50 -> 10 pts          | 40 -> 12 pts   | **56** |
| HTTP       | 90 -> 18 pts          | 40 -> 12 pts   | **40** |
| HTTP       | 90 -> 18 pts          | 50 -> 15 pts   | **34** |

Reading: being recognised as an HTTP server plus decent supportability cuts the Definition Quality
bar from ~60 to ~35. Grinding docstrings on a repo ToolBench believes is STDIO-only is the expensive
path. Fix transport and supportability first.

### 1.2 Ecosystem context (for expectation setting)

VERIFIED from Arcade's launch post: ~41,900 servers indexed, ~218,400 tools analysed, only 0.5%
scored A or above, 167,333 tools scored F. F is the ecosystem norm. Realistic fleet targets:

- **D everywhere**: achievable.
- **C on the flagship repos**: achievable.
- **A anywhere**: structurally unlikely for a solo maintainer at 2 stars median. Supportability
  weights stars, org backing and contributor count. Do not chase it.

### 1.3 Top ecosystem issues, ranked by occurrence

VERIFIED from https://toolbench.arcade.dev/improve. Use this to prioritise the codemod.

| Issue | Occurrences | Arcade pattern |
|---|---|---|
| Missing descriptions | 6,568 | tool-description |
| No error handling guidance | 1,899 | recovery-guide |
| No output schema | 1,407 | response-shaper |
| No pagination guidance | 694 | paginated-result |
| Missing parameter constraints | 691 | constrained-input |
| Destructive ops unguarded | 417 | confirmation-request |
| Naming inconsistencies | 401 | tool-description |
| Missing tool annotations | 137 | performance-hint |

---

## PART A: Fix scraper-mcp first (BLOCKING)

Repo: `D:\Dev\repos\scraper-mcp`
Key files: `src/scraper_mcp/scrapers/toolbench_score.py`, `src/scraper_mcp/scrapers/engine.py`,
`src/scraper_mcp/analytics.py`, `src/data/grades.db`

### A.0 Correction to earlier assumptions

VERIFIED: `https://toolbench.arcade.dev/api/servers?q=<repo>` is a **plain public JSON endpoint**, and
`/tools/{id}` assessment pages are **server-rendered**. No Playwright is needed for grades and no API
access approval is needed. The `/api-access` request form is a nice-to-have for bulk scoring, not a
blocker. The docstring at the top of `toolbench_score.py` is correct on this point.

### A.1 BUG (critical): dimension scores are always 0.0

File: `src/scraper_mcp/scrapers/toolbench_score.py`, in `scrape_assessment()`.

```python
text = soup.get_text(strip=True)
...
for label in ("Definition", "Protocol", "Supportability"):
    result[f"{label.lower()}_score"] = _extract_pct(text, label)
```

`BeautifulSoup.get_text(strip=True)` joins stripped strings with **no separator**. The page text
"Definition Quality 62" becomes `DefinitionQuality62`. `_extract_pct` uses the regex
`Definition\s*(\d+)`, which requires a digit right after the label. "Q" is not a digit, so no match,
so it returns the default `0.0`.

**Consequence: `definition_score`, `protocol_score` and `supportability_score` in `grades.db` are
almost certainly all 0.0.** Any prioritisation built on them is garbage.

Patch:

```python
text = soup.get_text(" ", strip=True)

_DIMENSION_LABELS = {
    "definition_score": "Definition Quality",
    "protocol_score": "Protocol Compliance",
    "supportability_score": "Supportability",
}

def _extract_pct(text: str, label: str) -> float | None:
    """Find the first number within 20 non-digit chars after `label`. None if absent."""
    m = re.search(rf"{re.escape(label)}\D{{0,20}}(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None
```

Note the return type change to `float | None`. **Do not keep 0.0 as the miss value.** A real zero and
a parse failure must be distinguishable, otherwise this class of bug hides forever.

### A.2 BUG (critical): the scraped grade is wrong and overrides the correct one

Same file, `scrape_assessment()`:

```python
for grade in ("A+", "A", "B", "C", "D", "F"):
    m = re.search(rf"\b{re.escape(grade)}\b", text)
    if m:
        result["grade"] = grade
        break
```

Two defects:
1. This returns the first grade letter appearing **anywhere** on the page, in A-first iteration
   order. Any standalone "A" in nav, a legend or prose wins.
2. `re.escape("A+")` gives `A\+`, so `\bA\+\b` has a broken trailing word boundary and rarely matches.

Then in `fetch_grade_with_details()`:

```python
detail.setdefault("grade", api_data.get("grade", "?"))
```

Because the regex almost always set something, `setdefault` never fires, so **the authoritative API
grade is discarded in favour of the regex guess**. `score` survives, because `scrape_assessment`
never sets it.

Patch: delete the regex loop entirely. Derive the grade from the score using the published
thresholds.

```python
def grade_from_score(score: float | None) -> str:
    if score is None:
        return "?"
    for cut, g in ((90, "A+"), (80, "A"), (70, "B"), (60, "C"), (50, "D")):
        if score >= cut:
            return g
    return "F"
```

In `fetch_grade_with_details`, set `detail["grade"] = grade_from_score(detail.get("score"))` after
merging API data, using explicit assignment, not `setdefault`.

Free integrity check on existing data: any row in `grades.db` where the stored grade disagrees with
`grade_from_score(score)` is corrupt. Run this before deciding whether history is salvageable.

### A.3 BUG (honesty): `request_reassess` is a stub that reports success

File: `src/scraper_mcp/scrapers/engine.py`, `ToolBenchScraper.request_reassess`:

```python
r = await client.get(f"{self.base_url}/submit")
return r.status_code == 200
```

This does a GET on the submit page and returns True. It submits nothing. `scraper_reassess` therefore
tells the caller it worked when nothing happened.

Fix, in order of preference:
1. Inspect the real submit flow (form action, method, payload, any CSRF token) and implement the POST.
2. If that is not feasible or is against Arcade's terms, return `False` with an explicit
   `"manual submit required"` message plus the deep link, and mark the tool as NOT IMPLEMENTED in
   README and SPEC.

Do not leave a stub that returns True.

### A.4 BUG: silent partial scans, doubled API calls, no rate limiting

File: `src/scraper_mcp/scrapers/engine.py`.

- `DEFAULT_CONCURRENCY = 12`, no delay, no jitter, no backoff.
- `fetch_grade_with_details()` calls `/api/servers` **twice per repo**: once inside
  `search_server_id()` and again immediately after.
- `_scan_repos()` catches every exception, logs a warning, and drops the repo from `rows`.

Net effect on a 128-repo refresh: roughly 256 API calls plus 128 page fetches in a burst. If ToolBench
rate-limits, the failures are swallowed and the repos vanish from the coverage matrix, which is
indistinguishable downstream from "not indexed on this platform". That is a silent partial scan and
violates the fleet rule.

Patches:
1. Call `/api/servers?q=<repo>` **once**, reuse the parsed response for both the id lookup and the
   API fields.
2. `DEFAULT_CONCURRENCY = 3`, plus a per-request delay with jitter (reuse the
   `--delay-seconds` / `--jitter-seconds` posture from the old toolbench-mcp scraper).
3. Add retry with exponential backoff on 429 and 5xx.
4. Never drop a repo on error. Emit a row with `status="fetch_error"` and the exception string, so
   fetch failure is visibly distinct from `status="not_indexed"`.
5. Set a descriptive User-Agent on every request (already done in `toolbench_score.py`, missing in
   `engine.py`'s LobeHub scraper).

### A.5 BUG (suspected): exact-name matching may drop the whole fleet

File: `toolbench_score.py`, `search_server_id()`:

```python
if s.get("name", "").lower() == repo.lower():
```

HYPOTHESIS: ToolBench may name servers `sandraschi/blender-mcp`, or use a display name, rather than
the bare repo slug. If so, every lookup returns None and the entire fleet reads as unindexed.

Action: dump one raw `/api/servers?q=blender-mcp` response to disk and look at the actual field
shape before changing the matcher. Then match on a candidate set (name, slug, repository url suffix,
full_name) and log every unmatched candidate so mismatches are loud.

### A.6 Known bug already flagged in source

`engine.py`, `GlamaScraper.fetch_grade`: `slug = repo  # placeholder; slug can differ (e.g. calibremcp)`.
Build a repo -> slug map, or resolve the slug from the Glama API, rather than assuming identity.

### A.7 Part A definition of done

- [ ] Raw fixtures saved: one `/api/servers?q=<repo>` JSON body and one `/tools/{id}` HTML body,
      committed under `tests/fixtures/toolbench/`. Parser tests run against these, not against the
      live site.
- [ ] Parser unit tests assert non-null dimension scores on the fixture.
- [ ] Integrity sweep run over existing `grades.db`, reporting count of rows where
      `grade != grade_from_score(score)`, and count of rows where dimension scores are all 0.0.
      Record the numbers in this document before deleting anything.
- [ ] Full polite refresh completed with concurrency 3, zero `fetch_error` rows, and total row count
      reconciled against the public repo count from the GitHub API.
- [ ] `scraper_reassess` either works or honestly reports that it does not.

---

## PART B: Fleet uplift

Only start once Part A is done and you have real dimension scores.

**Sort the worklist by numeric score, not by letter grade.** A repo at 48 is one LICENSE file and a
transport declaration away from D. A repo at 20 needs the full codemod. Cheapest points first.

### B.1 Phase 1: Supportability sweep (approx 1 day, fully scriptable)

VERIFIED against the GitHub API on 2026-07-29 (first 100 public repos, alphabetical):

- **56 have no detected license.** Named examples: `git-github-mcp`, `freecad-mcp`, `mixx-dj-mcp`,
  `home-assistant-mcp`, `mujoco-mcp`, `myconf`, `ednaficator`, `bookmarks-mcp`, `onenote-mcp`,
  `speech-mcp`, `sysinternals-mcp`, `worldlabs-mcp`, `plexmcp`, `resonite-mcp`, `readly-mcp`,
  `xkcd-mcp`, `sketchboard-excalidraw-mcp`, `ittybittyvideos`, `autohotkey-mcp`, `arr-mcp`.
  (Full list is reproducible with a one-shot GitHub API query, do not hand-maintain it here.)
- 33 have no topics.
- 16 have no description.
- 88 have no homepage.
- Median stars: 2. Distribution: 90 repos under 5 stars, 4 at 5-9, 2 at 10-14, 1 at 15-19, 2 at
  25-29, 1 at 30+. Top: `inkscape-mcp` and `blender-mcp` at 28, `windows-computer-use-mcp` at 25,
  `worldlabs-mcp` at 19, `advanced-memory-mcp` at 16, `ocr-mcp` at 14, `freecad-mcp` at 13.
- Last push date is already maxed (everything pushed same-day). Do not spend effort here.

Tasks:
- [ ] Add MIT LICENSE to every repo lacking one. Match the existing fleet license.
- [ ] Set description and topics on every repo. Topics should include `mcp`, `mcp-server`, `fastmcp`,
      plus the domain.
- [ ] Set homepage where a webapp or docs page exists.
- [ ] Cut one tagged release per repo with the `.mcpb` and NSIS artifacts attached.
      **BLOCKED** on the known `mcpb/src/` flattening defect (83 of 112 repos produce bundles that
      cannot import themselves). Do not attach broken bundles. Fix that first or ship the tag alone.

### B.2 Phase 2: Protocol (approx 1 day, gated on calibration Repo B)

The capability already exists in several repos. `blender-mcp` has `asgi_app = app.http_app()`, health
endpoints, a Dockerfile, and `app.run(transport="http", host=host, port=port)` behind a flag, but
`app.run(transport="stdio")` is the default path.

The work is not adding HTTP. It is making HTTP the **advertised** transport in whatever artifact
ToolBench actually reads. That artifact is unknown. HYPOTHESIS candidates: README, `server.json`,
`glama.json`, the Dockerfile, the mcpb manifest, or the registry submission.

Do not touch 100 repos until calibration Repo B tells you which one moves the Protocol score.

### B.3 Phase 3: Definition Quality codemod (approx 2 to 4 days)

Write ONE AST codemod in `meta-mcp` and run it fleet-wide. Do not let an agent freestyle per repo.

Evidence for each rule, gathered 2026-07-29:

**Rule 1: annotation keys are wrong or empty.**
In `blender-mcp`, every tool module declares:

```python
_READ_ONLY = {"readonly": True}
_MUTATING = {}
_DESTRUCTIVE = {}
```

`readonly` is not an MCP annotation. The spec keys are `readOnlyHint`, `destructiveHint`,
`idempotentHint`, `openWorldHint`, plus `title`. So 99 decorated tools in that repo emit either a key
nobody reads or an empty dict. Fleet sample is inconsistent, which confirms template drift rather
than a design choice:

| Repo | `readOnlyHint` occurrences |
|---|---|
| inkscape-mcp | 22 |
| filesystem-mcp | 3 |
| ocr-mcp | 0 |
| git-github-mcp | 0 |
| blender-mcp | 0 (uses the wrong `readonly` key) |

Codemod: rewrite the three constants to spec-correct dicts and populate all three.

```python
_READ_ONLY   = {"readOnlyHint": True,  "destructiveHint": False, "idempotentHint": True,  "openWorldHint": False}
_MUTATING    = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
_DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True,  "idempotentHint": False, "openWorldHint": False}
```

Set `openWorldHint: True` for tools that hit the network or an external service.

**Rule 2: portmanteau `operation` params are bare strings.**

| Repo | `operation: str` | `operation: Literal` |
|---|---|---|
| inkscape-mcp | 31 | 14 |
| git-github-mcp | 22 | 0 |
| ocr-mcp | 10 | 6 |
| filesystem-mcp | 3 | 6 |

The valid values are documented beautifully in prose but the JSON schema the agent sees is
`{"type": "string"}`. This is the "Missing parameter constraints" issue and it hits every repo,
because portmanteau is the fleet-wide pattern.

Codemod: parse the docstring's operation list (the format is consistent enough:
`- **create_sun**: ...` bullets plus the `operation (str, required): ... Must be one of: "a", "b"`
Args entry) and promote to `Literal["a", "b", ...]`.

**Rule 3: numeric constraints live in prose only.**
Example from `blender-mcp` `blender_lighting`: `energy: float` documented as "Range: 0.0 to 100.0"
with no `ge`/`le` in the schema. Codemod: lift `Range: X to Y` and `Default: Z` from the docstring
Args block into `Field(ge=X, le=Y, description=...)`.

**Rule 4: no output schemas.** Counts of tools returning `-> str`:
inkscape-mcp 133, git-github-mcp 42, ocr-mcp 40, filesystem-mcp 6.
This is ecosystem issue #3. Agents cannot plan multi-step workflows without knowing the return shape.

**This rule is NOT auto-applicable.** Changing a return type changes tool output and can break
consumers. The codemod should emit a flagged worklist, not a rewrite. Work it by hand, ordered by
ToolBench tool count, because Definition Quality is the average of per-tool scores, so a 100-tool
repo needs every tool fixed while a 12-tool repo can be polished manually.

**Rule 5 (structural, HYPOTHESIS): tools may be invisible to a source scanner.**
`blender-mcp` does `app = None` plus a lazy `get_app()`, and every `@app.tool` sits nested inside a
`_register_*()` function that calls `get_app()` first. If ToolBench's local analyser is AST-based
rather than executing the server, nested decorators on a lazily-bound object are exactly the shape
that yields zero tools. Their methodology says tools with no visible input schema score zero, and a
Definition Quality of zero is an automatic F regardless of docstring quality.

**This is the top suspect for a wide F band.** Test it via calibration Repo A. The tell in the data:
any repo whose ToolBench tool count is 0 or implausibly low.

### B.4 Do NOT do this

**Do not rename tools for score.** ToolBench rewards verb-first naming, which penalises
`blender_lighting`, `file_ops`, `adn_notes`. Renaming breaks every existing user config, every MCP
client entry and every skill. Not worth a fraction of one sub-dimension. Adopt verb-first naming for
NEW servers only.

---

## PART C: Calibration experiment (run BEFORE the fleet codemod)

Their extractor is a black box. Do not spend days on 100 repos against a guess.

Pick four F repos with similar starting scores. Change exactly ONE thing in each, resubmit, record
the per-dimension delta.

| Repo | Single change | Tests hypothesis |
|---|---|---|
| A | Module-level `app = FastMCP(...)` with top-level `@app.tool` decorators. Nothing else. | Rule 5: lazy registration hides tools |
| B | HTTP made the documented default everywhere (README, server.json, Dockerfile, mcpb manifest) | Protocol cap, and WHICH artifact is read |
| C | LICENSE + topics + description + one tagged release. No code change. | Supportability weighting |
| D | Literal enums + Field constraints + spec-correct annotations + Pydantic return models | Definition Quality per-tool scoring |

Record results in a table appended to this file. Only then run the fleet codemod.

`scraper-mcp` itself is a good fifth data point: it is a public FastMCP server that ToolBench grades,
it already has HTTP transport and a LICENSE, and its tool surface is documented READ_ONLY /
MUTATING / DESTRUCTIVE in SPEC.md. **Check whether those annotations are actually emitted as
`readOnlyHint` / `destructiveHint` in code, or only written down in the spec table.** If only the
table, it has the same defect as blender-mcp, and this is the right repo to fix first and measure.

---

## PART D: Regression gate

Fold ToolBench criteria into the existing `quality-check` / `assfix` SOP in
`mcp-central-docs/patterns/`, so new repos ship at D or better instead of needing a rescue pass.

Fail the gate on:
- [ ] any `operation: str` on a portmanteau tool (must be `Literal`)
- [ ] any `@tool` without spec-correct annotations
- [ ] any data-returning tool annotated `-> str`
- [ ] missing LICENSE
- [ ] tool registration not statically discoverable
- [ ] documented parameter ranges absent from `Field(...)`

Optional: once the Scoring API access request is approved, wire a nightly score check into
`scraper-mcp` and alert on regression via the existing aiwatcher-mcp hook.

---

## PART E: Side findings (unrelated to ToolBench, do not lose)

### E.1 `fetch` MCP server is completely broken

`claude_desktop_config.json` entry `fetch` runs `npx -y llms-fetch-mcp@0.1.7` with no arguments.

Log evidence from `C:\Users\sandr\AppData\Roaming\Claude\logs\mcp-server-fetch.log` (2026-07-29):
server starts, `tools/list` succeeds, then every `tools/call` returns `error(code=-32603)` in 260 to
630 ms. Four different URL shapes tested (JSON API with query string, server-rendered HTML page, raw
markdown on GitHub). All fail identically. Not a timeout, not URL-specific, not an API key issue
(the package uses none).

HYPOTHESIS: the first positional argument is the cache directory, and with none supplied it defaults
to `.llms-fetch-mcp/` relative to the process working directory. Claude Desktop spawns MCP servers
with a CWD that is typically not writable. `C:\Users\sandr\.llms-fetch-mcp` does not exist, which is
consistent.

Fix to try:

```json
"fetch": {
  "command": "npx",
  "args": ["-y", "llms-fetch-mcp@0.1.7", "C:\\temp\\llms-fetch-cache"]
}
```

Create the directory first, restart Claude Desktop. If it still returns -32603, run the binary by
hand and feed it a `tools/call` on stdin, because the Rust server swallows the panic and Claude
Desktop logs only the code.

### E.2 SECURITY: live GitHub token in plaintext config

`claude_desktop_config.json` contains a live `gho_` GitHub OAuth token inline under the `gitops`
server's `GH_TOKEN` env. **Rotate it**, then move it to a user environment variable or Windows
Credential Manager. It has already been read into at least one chat transcript.

---

## Appendix: evidence log

All gathered 2026-07-29.

- ToolBench methodology, improve page, api-access page: fetched directly.
- GitHub API `/users/sandraschi/repos`: first 100 public repos (alphabetical, ended at
  `opencode-cli-mcp`). Page 2 was rate-limited, so counts above cover 100 of roughly 128 public repos.
  **Rerun with an authenticated token to cover the full set.**
- `blender-mcp` source: full tarball inspected. 99 `@app.tool` decorators, all nested inside
  `_register_*()` functions. `_MUTATING` and `_DESTRUCTIVE` are empty dicts. `_READ_ONLY` uses the
  non-spec `readonly` key.
- `inkscape-mcp`, `ocr-mcp`, `git-github-mcp`, `filesystem-mcp`: tarballs inspected, grep counts as
  tabulated above.
- `scraper-mcp`: local source read at `D:\Dev\repos\scraper-mcp`.

### Open questions

1. Which artifact does ToolBench read to determine transport type?
2. Does `/api/servers` return dimension scores, or are they page-only?
3. What field does ToolBench use for a server's `name`, and does it match the bare repo slug?
4. Is the local analyser AST-based or does it execute the server?
5. Does the `/submit` rescoring flow have a programmatic endpoint, and do Arcade's terms permit it?

### Progress log

**2026-07-29 04:00 CET, A.1 and A.2 APPLIED** to `src/scraper_mcp/scrapers/toolbench_score.py`.

Consumers were checked BEFORE the `float | None` change and need no patching:
- `analytics.py` stores dimension scores inside the `raw_json` blob. The `grade` and `score`
  columns are already nullable. No schema migration required.
- `webapp/src/pages/repo-detail.tsx` is already null-safe: `DimBar` opens with
  `if (value == null) return null;` and lines 198-201 all guard with `!= null`. A missing
  dimension now renders as a hidden row instead of a false `0.0%`.
- No other consumer in `src/` does arithmetic on the dimension fields. `engine.py` only
  passes them through to `_normalize_row`.

Changes applied:
- `_extract_pct` returns `float | None` (was `0.0` on miss) and uses `\D{0,20}` between label
  and number.
- Added `_DIMENSION_LABELS` with the full on-page labels ("Definition Quality",
  "Protocol Compliance", "Supportability").
- Added `grade_from_score()` and `resolve_grade()`. `resolve_grade` prefers the API grade and
  logs a warning when the API grade and the score-derived grade disagree, which is a live
  integrity check on every fetch.
- `soup.get_text(" ", strip=True)`.
- Deleted the grade regex loop entirely.
- Replaced the `setdefault` merge block with explicit assignment.

Backups: `C:\temp\scraper-mcp-bak-20260729\toolbench_score.py.bak` plus per-edit fileops
backups alongside the source file.

STILL OPEN in Part A: A.3 (reassess stub), A.4 (concurrency, doubled API call, silent drops),
A.5 (name matching), A.6 (Glama slug), and the A.7 checklist (fixtures, tests, integrity sweep,
full refresh). Nothing has been run yet, so these edits are UNTESTED.

**2026-07-29 (session 2) — A.3, A.4, A.5, A.6 APPLIED** to
`src/scraper_mcp/scrapers/engine.py` and `src/scraper_mcp/scrapers/toolbench_score.py`.

Changes applied:

**A.3 — request_reassess stub:** Now returns `False` with a log warning that manual
submission is required at the ToolBench website. No longer lies.

**A.4 — engine quality:**
- `DEFAULT_CONCURRENCY` reduced from 12 to 3.
- `_scan_repos` now emits a `status="fetch_error"` row with exception details when
  `fetch_grade` raises, instead of silently dropping the repo from the result set.
  The `error` key is added to `_normalize_row`'s pass-through list.
- LobeHub scraper now sends a `User-Agent` header (was bare).

**A.4.2 — doubled API call eliminated:** `fetch_grade_with_details` now makes a single
`GET /api/servers?q=<repo>` call and reuses the parsed response for both server-id
discovery and API data extraction. The old `search_server_id` function is replaced by a
`_match_server` helper that extracts the match from an already-fetched server list.

**A.5 — name matching improved:** `_match_server` tries three candidate fields in order:
exact `name` match (preferring SCORED), `full_name` suffix (e.g. ends with `/repo`),
and `slug`. Logs a warning with the top 5 candidate names when every matcher misses,
so false negatives are visible.

**A.6 — Glama slug:** `GlamaScraper.fetch_grade` now passes `repo.replace("-", "")` as
the slug to `scrape_score_page`, matching the known Glama URL pattern (e.g.
`calibre-mcp` → `calibremcp`).

Ruff: `ruff check src/` + `ruff format` both pass clean.

STILL OPEN: Full fleet refresh (Part B onward). Part A is complete.

**2026-07-29 (session 3) — A.7 checklist COMPLETED.**

**Fixtures:** Live ToolBench responses captured to `tests/fixtures/toolbench/`:
- `api_servers_scraper-mcp.json` — 12-server result for query "scraper-mcp"
  (our repo at score 62, grade C). Script: `scripts/capture_fixtures.py`.
- `tools_{server_id}.html` — full ToolBench assessment page HTML (agent-scraper-mcp).

**Parser tests:** 26 tests in `tests/test_toolbench_parser.py` covering:
- A.1 regression: collapsed-text miss, space-separated hit, None-on-absent,
  float values, all three dimensions from fixture HTML.
- A.1 weight-skip: `_extract_pct` discovered to pick up methodology weights
  (50, 20, 30) instead of actual scores. Fixed by replacing regex with a
  simple `text.find()` + `re.finditer()` loop that skips numbers immediately
  followed by `%`. Regression test `test_extract_pct_skips_percentage_weight`
  gates this.
- A.2 regression: grade_from_score boundaries, resolve_grade API-fallback
  chain, scrape_assessment does not set grade key.
- A.5 regression: exact name, scored preference, full_name suffix, slug
  fallback, case insensitivity, empty list, real fixture matching.
- A.4.2 regression: `fetch_grade_with_details` makes exactly 2 HTTP calls
  (1 API + 1 HTML), verified by call counter.
- `_DIMENSION_LABELS` corrected: `"Protocol Compliance"` → `"Protocol Readiness"`
  (the actual on-page label, discovered from fixture HTML).
- Full suite: 36 tests (10 existing + 26 new), all pass.

**Integrity sweep:** `data/grades.db` does not exist (fresh start). Zero rows
to corrupt. The old database with all-zeros would have been invalidated anyway
after the dimension-score parsing fix.

**Single-repo smoke test:** `ToolBenchScraper.fetch_grade("sandraschi", "scraper-mcp")`
returns grade=C, score=62, dims={72, 72, 72} — dimension scores are no longer
the methodology weights. End-to-end pipeline verified.

**Ruff:** `ruff check src/ tests/` + `ruff format` both pass clean.

**Full fleet refresh (2026-07-29 04:25 UTC):** `refresh_all("sandraschi")` with
concurrency 3 across 150 repos. Zero `fetch_error` rows. Results:

| Platform | Found | Grade distribution | Mean score |
|----------|-------|-------------------|------------|
| ToolBench | 52/150 | B:1, C:5, D:9, F:37, ?:2 | 40.7 |
| Glama | 0/150 | — | — |
| LobeHub | 0/150 | — | — |

Glama/LobeHub returned 146/150 rows but no usable scores. Likely a separate
issue (slug/path mismatch post-migration).

19 repos hit the new A.5 `no server match` log warning (ToolBench names them
differently — e.g. `inkscape-mcps`, `immich-mcp-server`). Mismatches are now
visible rather than silent.

**Confirmed:** 37 of 52 indexed fleet repos are at F. The Supportability
sweep (LICENSE, topics, description, release) is the cheapest path to D
Part B onwards is unblocked.

**2026-07-29 — B.1 Phase 1 (LICENSE sweep) COMPLETED.**
210 of 211 Python fleet repos now have a MIT LICENSE. The one remaining is a
backup repo (`vroidstudio-mcp-backup-*`). ~110 repos got a new LICENSE file
in this pass (the rest already had one).

Implementation: `scripts/add_license.py` (deleted after use). Batches of 5
repos per invocation. Edge cases handled: no upstream branch, detached HEAD,
pre-commit hook failures (overte-mcp's `run_server.py` got a ruff fix),
cross-org repos (edge-bookmark-mcp-server owned by StephanSchipal).

Blockers:
- Wasm-mcp, openrouter-mcp, tapo-mcp, etc. had no upstream tracking — pushed
  with `--set-upstream`.
- mcp-test-suite deleted from GitHub.
- giskard-mcp, fleetwatcher-mcp, loona-mcp not git repos (not cloned).
- mixx-dj-mcp has a 112 MB LFS file blocking pushes — skipped.

Still TODO in B.1:
- [ ] Set description and topics on every repo (GitHub API)
- [ ] Set homepage where webapp or docs page exists
- [ ] Cut tagged releases (blocked on mcpb flattening defect)
- B.2 (Protocol) gated on calibration experiment (Part C)
- B.3 (Definition Quality codemod) gated on calibration

**Glama scraper status:** Glama completely redesigned their site (2026-07).
The `/score` page no longer has TDQS dimensions, X/5 scores, or parseable
grade data. `GlamaScraper` now returns None with a log warning. Needs a full
rewrite against the current Glama page layout — separate effort.

### Calibration results (fill in)

| Repo | Change | Score before | Score after | DQ delta | Protocol delta | Support delta | Date |
|---|---|---|---|---|---|---|---|
| | | | | | | | |
