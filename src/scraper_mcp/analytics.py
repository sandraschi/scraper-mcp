"""Analytics store - in-memory grade history with SQLite persistence for delta tracking."""

import json
import sqlite3
import time
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "grades.db"


def _get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            grade TEXT,
            score REAL,
            raw_json TEXT,
            fetched_at REAL NOT NULL,
            UNIQUE(platform, owner, repo)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            grade TEXT,
            score REAL,
            raw_json TEXT,
            recorded_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def upsert_grade(
    platform: str, owner: str, repo: str, grade: str | None, score: float | None, raw: dict | None
) -> None:
    """Insert or update a grade snapshot, recording history on change."""
    conn = _get_db()
    now = time.time()
    raw_str = json.dumps(raw) if raw else None
    conn.execute(
        """
        INSERT INTO grades (platform, owner, repo, grade, score, raw_json, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(platform, owner, repo) DO UPDATE SET
            grade=excluded.grade, score=excluded.score,
            raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
    """,
        (platform, owner, repo, grade, score, raw_str, now),
    )
    conn.execute(
        """
        INSERT INTO grade_history (platform, owner, repo, grade, score, raw_json, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (platform, owner, repo, grade, score, raw_str, now),
    )
    conn.commit()
    conn.close()


def get_latest(platform: str | None = None, owner: str | None = None, repo: str | None = None) -> list[dict]:
    """Get latest grades, optionally filtered."""
    conn = _get_db()
    query = "SELECT platform, owner, repo, grade, score, raw_json, fetched_at FROM grades WHERE 1=1"
    params = []
    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if owner:
        query += " AND owner = ?"
        params.append(owner)
    if repo:
        query += " AND repo = ?"
        params.append(repo)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        {
            "platform": r[0],
            "owner": r[1],
            "repo": r[2],
            "grade": r[3],
            "score": r[4],
            "raw": json.loads(r[5]) if r[5] else None,
            "fetched_at": r[6],
        }
        for r in rows
    ]


def get_history(platform: str, owner: str, repo: str, limit: int = 20) -> list[dict]:
    """Get grade history for a specific repo on a specific platform."""
    conn = _get_db()
    rows = conn.execute(
        "SELECT grade, score, raw_json, recorded_at FROM grade_history "
        "WHERE platform=? AND owner=? AND repo=? ORDER BY recorded_at DESC LIMIT ?",
        (platform, owner, repo, limit),
    ).fetchall()
    conn.close()
    return [
        {"grade": r[0], "score": r[1], "raw": json.loads(r[2]) if r[2] else None, "recorded_at": r[3]} for r in rows
    ]


def get_coverage_matrix(owner: str) -> dict:
    """Build a coverage matrix: repos × platforms with grades."""
    import json

    from scraper_mcp.fleet_registry import load_fleet_repo_ids
    from scraper_mcp.scrapers.engine import SCRAPERS

    conn = _get_db()
    rows = conn.execute(
        "SELECT platform, repo, grade, score, raw_json, fetched_at FROM grades WHERE owner=? ORDER BY repo, platform",
        (owner,),
    ).fetchall()
    conn.close()

    repos: dict[str, dict] = {}
    platforms_seen: set[str] = set(SCRAPERS.keys())
    for platform, repo, grade, score, raw_json, fetched_at in rows:
        platforms_seen.add(platform)
        if repo not in repos:
            repos[repo] = {}
        raw = json.loads(raw_json) if raw_json else {}
        repos[repo][platform] = {
            "grade": grade,
            "score": score,
            "url": raw.get("url", ""),
            "fetched_at": fetched_at,
        }

    fleet_ids = load_fleet_repo_ids()
    for repo_id in fleet_ids:
        repos.setdefault(repo_id, {})

    return {
        "repos": repos,
        "platforms": sorted(platforms_seen),
        "repo_count": len(repos),
        "fleet_total": len(fleet_ids),
    }
