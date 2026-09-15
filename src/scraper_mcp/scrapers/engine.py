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


class LobeHubScraper(BaseScraper):
    """LobeHub MCP marketplace - per-repo page probe (no public grades API)."""

    id = "lobehub"
    name = "LobeHub Marketplace"
    base_url = "https://lobehub.com"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
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
