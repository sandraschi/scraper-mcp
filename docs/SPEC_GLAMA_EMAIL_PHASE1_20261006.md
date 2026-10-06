# SPEC: Phase 1 — Glama email ingest (scraper-mcp)

**Status:** draft (2026-10-06)
**Parent plan:** `mcp-central-docs/projects/scraper-mcp/GLAMA_EMAIL_DIGEST_PLAN.md` (§8)
**Scope:** email ingest + classify + parse + persist ONLY. No advice, no
competitors, no digest (Phases 2-4). No new repo, no new cron daemon.

## 1. Goal

Turn the Hotmail `Glama` folder into a typed event stream the later phases
consume: per-repo build/release/score lifecycle events with links, ready for
the B → R → rescored state machine and the "release pending" digest.

## 2. Non-goals

- No Glama page scraping (exists: `refresh_single`).
- No advice/competitor/digest logic.
- No auto-submit, no auto-release, no auto-push. Ingest is read-only against
  the mailbox (mark-read is opt-in, default off).
- No live mailbox in CI (recorded fixtures only, same convention as the
  parser tests).

## 3. Email taxonomy (verified live 2026-10-06, 70 mails in folder)

| Type | Subject shape | Payload | Count (latest 10) |
|---|---|---|---|
| R (release) | `Release {ver} published for {repo}` | view-server link | 6 |
| B (build ok) | `Build succeeded for {repo}` | build-details + releases links | 2 |
| F (build failed) | `Build failed for {repo}` | build-details link (fix-me item) | 1 |
| O (OTP) | `Your OTP: ...` | none — ignore pattern | 1 |
| G (grade/digest) | unconfirmed | — | 0 |

Body regexes (subjects are primary; bodies confirm):
- R: `Release (\S+) of ([\w-]+) was published on (.+?)\.`
- B: `The build for ([\w-]+) has succeeded`
- F: `The build for ([\w-]+) has failed` (shape inferred from subject; verify
  against one live F body at build time)

## 4. Ingest path (all pieces exist and are verified)

1. `email-mcp search_emails(query, service="graph", folder="Glama")` —
   folder-scoped search FIXED 2026-10-06 (was HTTP 400 on `folder:` clause;
   now `/me/mailFolders/{id}/messages`). Verified live: `onenote-mcp` in
   Glama returns the B→R pair + 1.0.0 release.
2. `fetch_email_detail(email_id)` per hit — full body WITH hrefs (link shapes
   TBD from live HTML at build time; pasted samples carry no URLs).
3. Classify by subject (table above); unknown subjects → `type: unknown`,
   kept for review, never dropped silently.
4. Sanitize: email-mcp already strips 37 Unicode chars + wraps content in a
   safety boundary server-side. Ingest treats all email content as untrusted:
   regex-first extraction, LLM (later phases) sees numbers + whitelisted
   strings, never raw HTML.

## 5. New surface (scraper-mcp, portmanteau style)

`scraper_email(operation="ingest" | "events" | "pending_releases", ...)` —
Phase 1 ships `ingest` (+ readback for free):

- `ingest(service="graph", folder="Glama", limit=50, mark_read=False)`:
  search → fetch details → classify → parse → upsert into store. Returns
  `{ingested, by_type: {R, B, F, O, unknown}, pending_releases}`.
- `events(repo?, type?, since?)`: read back stored events.
- `pending_releases`: Type B with no follow-up Type R within N days
  (default N=7), cross-checked via `git-github-mcp release_list` where
  available. This is the digest's nudge list.

## 6. Data model (SQLite analytics store, new table `email_events`)

`id | received_at | type | repo | version | subject | glama_url |
build_url | releases_url | email_id | created_at`. Unique key
`(email_id)` — re-ingest is idempotent. `repo` normalized lowercase;
non-`sandraschi/*` repos (e.g. `AI Producer Hub`, a marketplace item, not a
repo) kept with `repo` NULL + `note` rather than force-fit.

## 7. State machine (persisted, consumed by Phase 4)

Per repo: B(release pending) → R(published) → page `scored_at` ≈ release
date (verified: onenote-mcp 1.0.4, scored 2026-09-29 09:30). Transitions
derived at digest time from `email_events` + `refresh_single` output; Phase 1
only stores the events.

## 8. Tests (no live calls)

- Fixture: 5+ anonymized recorded mails (one per type + one unknown) as
  JSON in `tests/fixtures/glama_email/`.
- `test_classify_*`: subject → type for R/B/F/O/unknown.
- `test_parse_release_subject/body`: version + repo extraction incl. the
  `AI Producer Hub`-style non-repo case (repo NULL, no crash).
- `test_ingest_idempotent`: same payload twice → one row.
- `test_search_uses_folder_endpoint`: mock email-mcp at the HTTP-client
  boundary; assert folder-scoped path (mirrors the email-mcp regression test
  that caught the 400).
- Live verification (manual, documented): run `ingest` against the real
  `Glama` folder once, confirm the onenote-mcp B→R triple appears.

## 9. Acceptance

- `ingest` on the live folder returns the known B→R pairs (onenote-mcp,
  Japanophile) and the virtualization-mcp Type F.
- Suite green (`pytest`), `ruff check` + `ruff format --check` clean.
- Assfix-zero for new ops: real behavior, no stubs; fixtures documented.

## 10. Open questions (resolved 2026-10-06 via live ingest)

- ~~Exact href shapes~~ RESOLVED from live `fetch_email_detail` HTML: all
  links arrive Outlook-SafeLinks-wrapped (`emea01.safelinks.../?url=...`) and
  must be unwrapped + entity-decoded. Inner shapes: view-server =
  `glama.ai/mcp/servers/{owner}/{repo}`; build details =
  `.../admin/dockerfile/tests/{uuid}`; create-a-release =
  `.../admin/releases` (Glama admin page, not GitHub). Parser handles all
  three (`_unwrap_url`, `_classify_url` specific-first).
- ~~Sanitize-boundary interplay~~ RESOLVED: email-mcp wraps every field in
  `---BEGIN EMAIL_DETAIL_*---` markers; the classifier unwraps first
  (`_unwrap_boundary`, falls back to raw). Without this, 9/10 live mails
  classified `unknown` (verified live before/after).
- Type G existence — ongoing watch; pipeline handles it as `unknown` until
  specced.
- `mark_read` default stays False; digest may want auto-mark-read of
  consumed OTP mails later (explicit decision, not now).
