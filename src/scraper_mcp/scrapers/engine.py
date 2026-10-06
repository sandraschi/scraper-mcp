"""Modular scraper engine - HTTP parsers for ToolBench, Glama, LobeHub.

Each scraper is a pluggable class with a standard interface:
    - id: str - platform identifier (toolbench, glama, lobehub)
    - name: str - human-readable platform name
    - fetch_coverage(owner, repos) -> list[dict] - discover repos on platform
    - fetch_grade(owner, repo) -> dict | None - get grade for one repo
    - request_reassess(owner, repo) -> bool - trigger rescoring
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

from scraper_mcp.fleet_registry import load_fleet_repo_ids

log = logging.getLogger(__name__)

GradeRow = dict[str, Any]
DEFAULT_CONCURRENCY = 3
_REQUEST_DELAY = 0.5  # base seconds between requests
_REQUEST_JITTER = 0.3  # max random jitter added to the delay
_LobeHub_USER_AGENT = "scraper-mcp/0.1 (fleet monitor; polite daily scan)"


def _normalize_row(repo: str, **fields: Any) -> GradeRow:
    row = {
        "repo": repo,
        "grade": fields.get("grade", "?"),
        "score": fields.get("score"),
        "url": fields.get("url", ""),
        "status": fields.get("status", "unknown"),
        "tools": fields.get("tools", 0),
    }
    # Pass through extra fields for raw_json storage
    for key in (
        "tdqs_mean",
        "tdqs_min",
        "tdqs_grade",
        "coherence_grade",
        "maintenance_grade",
        "tool_details",
        "latest_release",
        "profile_completion",
        "definition_score",
        "protocol_score",
        "supportability_score",
        "trust_score",
        "top_issues",
        "server_id",
        "score_history",
        "rubric",
        "expected_tool_count",
        "error",
    ):
        if key in fields:
            row[key] = fields[key]
    return row


class BaseScraper:
    """Pluggable scraper base. Subclass per platform."""

    id: str = "unknown"
    name: str = "Unknown"
    base_url: str = ""
    timeout: float = 30.0

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        """Return {repo, grade, score, url, status, tools} or None if not found."""
        raise NotImplementedError

    async def fetch_coverage(self, owner: str, repos: list[str] | None = None) -> list[GradeRow]:
        """Scan fleet repos and return rows for those indexed on this platform."""
        fleet = repos if repos is not None else load_fleet_repo_ids()
        if not fleet:
            return []
        return await _scan_repos(self.fetch_grade, owner, fleet)

    async def request_reassess(self, owner: str, repo: str) -> bool:
        """Trigger rescoring. Return True if request accepted."""
        raise NotImplementedError


async def _scan_repos(
    fetch_one,
    owner: str,
    repos: list[str],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[GradeRow]:
    sem = asyncio.Semaphore(concurrency)
    rows: list[GradeRow] = []

    async def _one(repo: str) -> None:
        async with sem:
            try:
                row = await fetch_one(owner, repo)
                if row:
                    rows.append(row)
            except Exception as exc:
                log.warning("%s: fetch_grade(%s) failed: %s", fetch_one.__self__.id, repo, exc)
                rows.append(
                    _normalize_row(
                        repo,
                        grade="?",
                        score=None,
                        status="fetch_error",
                        tools=0,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
        await asyncio.sleep(_REQUEST_DELAY + random.random() * _REQUEST_JITTER)

    await asyncio.gather(*[_one(repo) for repo in repos])
    return rows


class ToolBenchScraper(BaseScraper):
    """ToolBench by Arcade.dev - per-repo search via ?q=<repo>."""

    id = "toolbench"
    name = "ToolBench (Arcade.dev)"
    base_url = "https://toolbench.arcade.dev"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        from scraper_mcp.scrapers.toolbench_score import fetch_grade_with_details

        detail = await fetch_grade_with_details(owner, repo)
        if not detail:
            return None
        return _normalize_row(
            repo,
            grade=detail.get("grade", "?"),
            score=detail.get("score"),
            url=detail.get("url", f"{self.base_url}/tools/{detail.get('server_id', '')}"),
            status=detail.get("status", "unknown"),
            tools=detail.get("tools", 0),
            definition_score=detail.get("definition_score"),
            protocol_score=detail.get("protocol_score"),
            supportability_score=detail.get("supportability_score"),
            trust_score=detail.get("trust_score"),
            top_issues=detail.get("top_issues"),
            tool_details=detail.get("tool_details"),
            server_id=detail.get("server_id"),
        )

    async def request_reassess(self, owner: str, repo: str) -> bool:
        log.warning(
            "request_reassess(%s/%s): ToolBench manual submit required. "
            "No programmatic endpoint is known. Visit %s/tools and click 'Submit'.",
            owner,
            repo,
            self.base_url,
        )
        return False


class GlamaScraper(BaseScraper):
    """Glama.ai - server page scraper (TDQS moved off the old /score sub-page).

    NOTE (2026-07-29): Glama redesigned their site; the dedicated /score page
    started 302-redirecting to the main server page and the old <button
    class="ULqjq"> per-tool markup stopped existing, breaking this scraper.
    NOTE (2026-09-15): re-verified against live HTML and rewrote the parser in
    glama_score.py for the current <details id="tool_name"> layout - see that
    module's docstring for the full structural diff. Re-enabled below.
    """

    id = "glama"
    name = "Glama.ai"
    base_url = "https://glama.ai"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        from scraper_mcp.scrapers.glama_score import scrape_score_page

        detail = await scrape_score_page(owner, repo)
        if not detail:
            return None
        return _normalize_row(
            repo,
            grade=detail.get("grade", "?"),
            score=detail.get("score"),
            url=detail.get("url", f"{self.base_url}/mcp/servers/{owner}/{repo}"),
            status=detail.get("status", "unknown"),
            tools=detail.get("tools", 0),
            tdqs_mean=detail.get("tdqs_mean"),
            tdqs_min=detail.get("tdqs_min"),
            tdqs_grade=detail.get("tdqs_grade"),
            coherence_grade=detail.get("coherence_grade"),
            maintenance_grade=detail.get("maintenance_grade"),
            tool_details=detail.get("tool_details"),
            latest_release=detail.get("latest_release"),
            profile_completion=detail.get("profile_completion"),
        )

    async def request_reassess(self, owner: str, repo: str) -> bool:
        log.warning(
            "request_reassess(%s/%s): Glama has no manual reassess endpoint. "
            "Grades update automatically on every commit/rebuild and at least "
            "daily via Glama's own sync - no action needed to trigger a refresh.",
            owner,
            repo,
        )
        return False


def _fetch_with_obscura(url: str, dump: str = "html") -> str | None:
    """Synchronous Obscura stealth fetch helper for platform scrapers."""
    try:
        import sys
        from pathlib import Path

        obscura_mcp_path = Path("D:/Dev/repos/obscura-mcp/src")
        if obscura_mcp_path.exists() and str(obscura_mcp_path) not in sys.path:
            sys.path.insert(0, str(obscura_mcp_path))

        from obscura_mcp.server import fetch_with_obscura

        return fetch_with_obscura(url, dump=dump, stealth=True, timeout=35)
    except Exception as e:
        log.warning("Obscura fetch fallback failed for %s: %s", url, e)
        return None


_LOBEHUB_MARKET_TIMEOUT = 120.0


def _lobehub_market_search(query: str, page_size: int = 40) -> list[dict]:
    """Run `market-cli mcp search --output json`, return the raw item list.

    Search is anonymous (no registration needed — unlike `mcp view`, which
    requires `market-cli register`). page_size 40 is the server-side maximum
    (the CLI docs claim 100, the API rejects >40) — needed because common
    names like filesystem-mcp drown the owner's listing off page 1 at
    smaller sizes. Returns [] on any failure so callers can fall back to
    the legacy HTML probe.
    """
    import json
    import shutil
    import subprocess

    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx is None:
        log.warning("LobeHub market-cli search skipped: npx not found on PATH")
        return []
    try:
        proc = subprocess.run(
            [
                npx,
                "-y",
                "@lobehub/market-cli",
                "mcp",
                "search",
                "--q",
                query,
                "--page-size",
                str(page_size),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            # Market records contain CJK descriptions; the Windows locale
            # codec (cp1252) chokes on them and kills the reader thread,
            # leaving stdout=None. Force UTF-8.
            encoding="utf-8",
            errors="replace",
            timeout=_LOBEHUB_MARKET_TIMEOUT,
        )
    except Exception as exc:
        log.warning("LobeHub market-cli search failed for %s: %s", query, exc)
        return []
    if proc.returncode != 0:
        log.warning("LobeHub market-cli search failed for %s: %s", query, proc.stderr.strip()[:200])
        return []
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        log.warning("LobeHub market-cli returned non-JSON for %s: %s", query, exc)
        return []
    items = payload.get("items", [])
    return items if isinstance(items, list) else []


def _select_lobehub_item(owner: str, repo: str, items: list[dict]) -> dict | None:
    """Owner-verified match: the record's github.url must equal owner/repo.

    Bare-name matching caused 30 misattributed rows fleet-wide (A.5) — never
    match on name/identifier alone. `foobar` must not match `foo`.
    """
    want = f"https://github.com/{owner.lower()}/{repo.lower()}"
    for item in items:
        url = ((item.get("github") or {}).get("url") or "").lower().rstrip("/").removesuffix(".git")
        if url == want:
            return item
    return None


def _lobehub_criticisms(item: dict) -> list[str]:
    """Human-readable listing criticisms from a market plugin record.

    LobeHub publishes no letter grades, but the record flags concrete gaps
    ("no prompts defined", unvalidated, unclaimed, ...). Returned as
    top_issues so downstream consumers need no platform special-casing.
    """
    caps = item.get("capabilities") or {}
    issues: list[str] = []
    if not item.get("isValidated", False):
        issues.append("not LobeHub-validated")
    if not item.get("isClaimed", False):
        issues.append("listing unclaimed (claim it to manage updates)")
    if (item.get("toolsCount", 0) or 0) == 0 and not caps.get("tools", False):
        issues.append("no tools indexed on LobeHub")
    if (item.get("promptsCount", 0) or 0) == 0 and not caps.get("prompts", False):
        issues.append("no prompts defined")
    if (item.get("resourcesCount", 0) or 0) == 0 and not caps.get("resources", False):
        issues.append("no resources defined")
    if (item.get("ratingCount", 0) or 0) == 0:
        issues.append("no ratings yet")
    if not (item.get("description") or "").strip():
        issues.append("missing description")
    return issues


def _lobehub_row(repo: str, item: dict) -> GradeRow:
    """Build a GradeRow from a market plugin record."""
    rating = item.get("ratingAverage")
    try:
        score = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        score = None
    return _normalize_row(
        repo,
        grade="N/A",  # LobeHub publishes criticism, not letter grades
        score=score,  # 0-5 rating scale, same range as Glama TDQS
        # Human listing-page URL format is unconfirmed; manifestUrl is the
        # stable per-listing link (resolves, unique per identifier).
        url=item.get("manifestUrl") or "",
        status="indexed",
        tools=item.get("toolsCount", 0) or 0,
        top_issues=_lobehub_criticisms(item),
        server_id=item.get("identifier"),
    )


class LobeHubScraper(BaseScraper):
    """LobeHub MCP marketplace - market-cli search + criticism capture.

    Primary source is `@lobehub/market-cli mcp search` (anonymous JSON).
    The old lobehub.com/mcp/<owner>/<repo> page probe is kept as a last
    resort but 404s since the market moved to market.lobehub.com.
    """

    id = "lobehub"
    name = "LobeHub Marketplace"
    base_url = "https://lobehub.com"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        # Query "owner repo" (space-separated): the market tokenizes the
        # query, and the rare owner token constrains results to our own
        # listings. A bare repo name drowns in generic "mcp" matches and an
        # "owner/repo" string matches nothing. Owner-verification happens
        # in _select_lobehub_item, so collisions stay excluded.
        items = await asyncio.to_thread(_lobehub_market_search, f"{owner} {repo}")
        item = _select_lobehub_item(owner, repo, items)
        if item is not None:
            return _lobehub_row(repo, item)

        # Fallback: legacy per-repo page probe
        url = f"{self.base_url}/mcp/{owner}/{repo}"
        headers = {"User-Agent": _LobeHub_USER_AGENT}
        text = None
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    text = r.text.lower()
            except Exception as e:
                log.warning("LobeHub HTTP fetch failed for %s: %s — attempting Obscura fallback", url, e)

        if text is None:
            # Fallback to Obscura stealth rendering
            text = await asyncio.to_thread(_fetch_with_obscura, url, "html")
            if text:
                text = text.lower()

        if not text or owner.lower() not in text or repo.lower() not in text:
            return None

        return _normalize_row(
            repo,
            grade="N/A",
            score=None,
            url=url,
            status="indexed",
            tools=0,
        )

    async def request_reassess(self, owner: str, repo: str) -> bool:
        log.warning(
            "request_reassess(%s/%s): LobeHub has no rescore endpoint. "
            "Listing owners refresh with `lhm plugin update` after fixing "
            "the flagged gaps (validation, prompts/resources, description).",
            owner,
            repo,
        )
        return False


SCRAPERS: dict[str, BaseScraper] = {
    "toolbench": ToolBenchScraper(),
    "glama": GlamaScraper(),
    "lobehub": LobeHubScraper(),
}


async def refresh_all(
    owner: str,
    repos: list[str] | None = None,
) -> dict[str, list[GradeRow]]:
    """Refresh coverage for all platforms across fleet repos in parallel."""
    fleet = repos if repos else load_fleet_repo_ids()
    results: dict[str, list[GradeRow]] = {}
    tasks = [(pid, scraper.fetch_coverage(owner, fleet)) for pid, scraper in SCRAPERS.items()]
    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (pid, _), result in zip(tasks, gathered):
        if isinstance(result, Exception):
            log.error("refresh_all %s failed: %s", pid, result)
            results[pid] = []
        else:
            results[pid] = result
    return results


async def refresh_single(owner: str, repo: str) -> dict[str, GradeRow | None]:
    """Refresh grades for a single repo across all platforms."""
    results: dict[str, GradeRow | None] = {}
    tasks = [(pid, scraper.fetch_grade(owner, repo)) for pid, scraper in SCRAPERS.items()]
    gathered = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (pid, _), result in zip(tasks, gathered):
        if isinstance(result, Exception):
            log.warning("refresh_single %s/%s on %s: %s", owner, repo, pid, result)
            results[pid] = None
        else:
            results[pid] = result
    return results
