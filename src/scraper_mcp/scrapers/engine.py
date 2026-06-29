"""Modular scraper engine — HTTP parsers for ToolBench, Glama, LobeHub.

Each scraper is a pluggable class with a standard interface:
    - id: str — platform identifier (toolbench, glama, lobehub)
    - name: str — human-readable platform name
    - fetch_coverage(owner, repos) -> list[dict] — discover repos on platform
    - fetch_grade(owner, repo) -> dict | None — get grade for one repo
    - request_reassess(owner, repo) -> bool — trigger rescoring
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from scraper_mcp.fleet_registry import load_fleet_repo_ids

log = logging.getLogger(__name__)

GradeRow = dict[str, Any]
DEFAULT_CONCURRENCY = 12


def _normalize_row(repo: str, **fields: Any) -> GradeRow:
    row = {
        "repo": repo,
        "grade": fields.get("grade", "?"),
        "score": fields.get("score"),
        "url": fields.get("url", ""),
        "status": fields.get("status", "unknown"),
        "tools": fields.get("tools", 0),
    }
    # Pass through extra fields (tdqs dimensions, etc.) for raw_json storage
    for key in ("tdqs_mean", "tdqs_min", "tdqs_grade", "coherence_grade",
                "maintenance_grade", "tool_details", "latest_release",
                "profile_completion"):
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

    await asyncio.gather(*[_one(repo) for repo in repos])
    return rows


class ToolBenchScraper(BaseScraper):
    """ToolBench by Arcade.dev — per-repo search via ?q=<repo>."""

    id = "toolbench"
    name = "ToolBench (Arcade.dev)"
    base_url = "https://toolbench.arcade.dev"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.base_url}/api/servers",
                params={"q": repo},
                headers={"Accept": "application/json"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            servers = data.get("servers", data.get("data", []))
            if not isinstance(servers, list):
                return None
            for s in servers:
                name = (s.get("name") or "").strip()
                if name.lower() != repo.lower():
                    continue
                server_id = s.get("id", "")
                url = f"{self.base_url}/servers/{server_id}" if server_id else f"{self.base_url}/servers"
                return _normalize_row(
                    repo,
                    grade=s.get("grade", "?"),
                    score=s.get("overallScore", s.get("score")),
                    url=url,
                    status=s.get("status", "unknown"),
                    tools=s.get("toolCount", 0),
                )
        return None

    async def request_reassess(self, owner: str, repo: str) -> bool:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(f"{self.base_url}/submit")
            return r.status_code == 200


class GlamaScraper(BaseScraper):
    """Glama.ai — score page scraper with per-tool TDQS dimensions."""

    id = "glama"
    name = "Glama.ai"
    base_url = "https://glama.ai"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        from scraper_mcp.scrapers.glama_score import scrape_score_page

        result = await scrape_score_page(owner, repo)
        if not result:
            return None
        slug = repo  # placeholder; slug can differ (e.g. calibremcp)
        page_url = f"{self.base_url}/mcp/servers/{owner}/{slug}/score"

        return _normalize_row(
            repo,
            grade=result.get("grade", "?"),
            score=result.get("score"),
            url=page_url,
            status=result.get("status", "indexed"),
            tools=result.get("tools", 0),
            tdqs_mean=result.get("tdqs_mean"),
            tdqs_min=result.get("tdqs_min"),
            tdqs_grade=result.get("tdqs_grade"),
            coherence_grade=result.get("coherence_grade"),
            maintenance_grade=result.get("maintenance_grade"),
            tool_details=result.get("tool_details"),
            latest_release=result.get("latest_release"),
            profile_completion=result.get("profile_completion"),
        )

    async def request_reassess(self, owner: str, repo: str) -> bool:
        return False


class LobeHubScraper(BaseScraper):
    """LobeHub MCP marketplace — per-repo page probe (no public grades API)."""

    id = "lobehub"
    name = "LobeHub Marketplace"
    base_url = "https://lobehub.com"

    async def fetch_grade(self, owner: str, repo: str) -> GradeRow | None:
        url = f"{self.base_url}/mcp/{owner}/{repo}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            text = r.text.lower()
            if owner.lower() not in text or repo.lower() not in text:
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
