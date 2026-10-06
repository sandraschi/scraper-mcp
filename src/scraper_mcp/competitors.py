"""Competitor tracking - Phase 3 of the email -> advice -> digest workflow.

Discovers rival MCP servers (Glama Related block, LobeHub market neighbors),
refreshes their grades into the shared store, and diffs them against ours:
grade gaps plus a feature-filch list (their tool names minus ours) and our
lead list. Links persist in `competitor_links`; grade snapshots reuse the
grades store under the competitor's own owner.
"""

from __future__ import annotations

import re
import time

from .analytics import DB_DIR, DB_PATH
from .scrapers.engine import _lobehub_market_search

FLEET_OWNER = "sandraschi"
MAX_COMPETITORS = 5

_KEYWORD_STOPWORDS = {"mcp", "server", "servers", "the", "for", "and", "with", "my", "hub"}


def repo_keywords(repo: str) -> list[str]:
    """Topic tokens from a repo slug for market-neighbor search."""
    tokens = [tok for tok in re.split(r"[-_.]+", (repo or "").lower()) if len(tok) >= 3]
    return [tok for tok in tokens if tok not in _KEYWORD_STOPWORDS][:3]


def _github_owner_repo(url: str | None) -> tuple[str, str] | None:
    match = re.match(r"https?://github\.com/([^/]+)/([^/?#]+?)(?:\.git)?/?$", (url or "").strip(), re.I)
    if not match:
        return None
    return match.group(1).lower(), match.group(2).lower()


def discover_glama(raw: dict | None, owner: str, repo: str) -> list[dict]:
    """Related-server links from a stored Glama raw, minus our own entry."""
    if not raw:
        return []
    owner, repo = owner.lower(), repo.lower()
    links = []
    for link in raw.get("related_servers") or []:
        if link.get("owner", "").lower() == owner and link.get("repo", "").lower() == repo:
            continue
        links.append({**link, "platform": "glama"})
    return links


def discover_lobehub(repo: str, owner: str = FLEET_OWNER, limit: int = MAX_COMPETITORS) -> list[dict]:
    """Live LobeHub market neighbors: same-topic items from other owners.

    Owner-verified identity via github.url (the A.5 lesson applies to rivals
    too); our own listing is excluded. Live-only: market-cli has no cache.
    """
    keywords = repo_keywords(repo)
    if not keywords:
        return []
    neighbors = []
    seen: set[tuple[str, str]] = set()
    for item in _lobehub_market_search(" ".join(keywords), page_size=40):
        identity = _github_owner_repo((item.get("github") or {}).get("url"))
        if not identity:
            continue
        comp_owner, comp_repo = identity
        if (comp_owner, comp_repo) in seen:
            continue
        if comp_owner == owner.lower() and comp_repo == repo.lower():
            continue
        seen.add((comp_owner, comp_repo))
        neighbors.append(
            {
                "owner": comp_owner,
                "repo": comp_repo,
                "name": item.get("name", comp_repo),
                "url": f"https://github.com/{comp_owner}/{comp_repo}",
                "platform": "lobehub",
            }
        )
        if len(neighbors) >= limit:
            break
    return neighbors


def _tool_names(raw: dict | None) -> set[str]:
    """Tool-name set from a fresh row (flat) or a stored raw (nested under raw)."""
    if not raw:
        return set()
    details = raw.get("tool_details") or raw.get("raw", {}).get("tool_details") or []
    return {str(tool.get("name", "")).lower() for tool in details if tool.get("name")}


def diff_grades(mine: dict, theirs: dict) -> dict:
    """Grade/tooling diff between our refresh_single rows and a rival's.

    Rows map platform -> grade row (or None). Returns grade gaps, tool
    counts, filch list (their tools we lack) and lead list (ours they lack).
    """
    platforms = sorted(set(mine) | set(theirs))
    gaps = []
    my_tools: set[str] = set()
    their_tools: set[str] = set()
    for pid in platforms:
        mine_row, their_row = mine.get(pid), theirs.get(pid)
        my_tools |= _tool_names(mine_row)
        their_tools |= _tool_names(their_row)
        my_score = (mine_row or {}).get("score")
        their_score = (their_row or {}).get("score")
        if isinstance(my_score, (int, float)) and isinstance(their_score, (int, float)):
            gaps.append(
                {
                    "platform": pid,
                    "mine": {"grade": (mine_row or {}).get("grade"), "score": my_score},
                    "theirs": {"grade": (their_row or {}).get("grade"), "score": their_score},
                    "gap": round(their_score - my_score, 2),
                }
            )
    gaps.sort(key=lambda gap: gap["gap"], reverse=True)
    return {
        "platforms": platforms,
        "gaps": gaps,
        "filch": sorted(their_tools - my_tools),
        "leads": sorted(my_tools - their_tools),
    }


# --- store -------------------------------------------------------------------

_COMPETITOR_SCHEMA = """
    CREATE TABLE IF NOT EXISTS competitor_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo TEXT NOT NULL,
        platform TEXT NOT NULL,
        comp_owner TEXT NOT NULL,
        comp_repo TEXT NOT NULL,
        name TEXT,
        discovered_at REAL NOT NULL,
        UNIQUE(repo, platform, comp_owner, comp_repo)
    )
"""


def _get_db():
    import sqlite3

    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(_COMPETITOR_SCHEMA)
    conn.commit()
    return conn


def upsert_links(repo: str, links: list[dict]) -> int:
    """Record discovered competitor links. Returns count of newly added."""
    conn = _get_db()
    now = time.time()
    new = 0
    for link in links:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO competitor_links
            (repo, platform, comp_owner, comp_repo, name, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                repo.strip().lower(),
                link.get("platform", "?"),
                link.get("owner", "").lower(),
                link.get("repo", "").lower(),
                link.get("name", "")[:120],
                now,
            ),
        )
        new += cursor.rowcount
    conn.commit()
    conn.close()
    return new


def list_links(repo: str | None = None) -> list[dict]:
    """Read back recorded competitor links."""
    conn = _get_db()
    query = "SELECT repo, platform, comp_owner, comp_repo, name, discovered_at FROM competitor_links"
    params: list = []
    if repo:
        query += " WHERE repo = ?"
        params.append(repo.strip().lower())
    query += " ORDER BY discovered_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    keys = ("repo", "platform", "comp_owner", "comp_repo", "name", "discovered_at")
    return [dict(zip(keys, row)) for row in rows]
