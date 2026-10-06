"""Daily digest - Phase 4 of the email -> advice -> digest workflow.

Assembles the multi-platform grades picture into one markdown+JSON report
from the local stores (grades, advice, email events, competitor links).
Read-only by default; notify=True posts new-competitor / aged-advice /
build-failed events to aiwatcher (same pattern as the grade-drop alerts).

Morning-digest integration is a PULL contract (deliberately no edits to
git-github-mcp, which is under active work elsewhere): the digest owner
fetches GET {scraper}/api/digest (or the scraper_digest tool) and embeds
the markdown section. See the plan doc §3.3.
"""

from __future__ import annotations

import os
import time

import httpx

from .advice import list_advice
from .analytics import DB_DIR, DB_PATH, get_latest
from .competitors import list_links
from .email_ingest import list_events, pending_releases
from .fleet_queries import grade_deltas, stale_entries, worst_tools

AIWATCHER_URL = os.getenv("AIWATCHER_URL", "http://127.0.0.1:10946")
AGED_DAYS = 14
RECENT_DAYS = 7
MAX_EVENTS = 10
FLEET_OWNER = "sandraschi"


def _get_db():
    import sqlite3

    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS digest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at REAL NOT NULL,
            notified INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def _last_notified_run() -> float:
    conn = _get_db()
    row = conn.execute("SELECT ran_at FROM digest_runs WHERE notified = 1 ORDER BY ran_at DESC LIMIT 1").fetchone()
    conn.close()
    return row[0] if row else 0.0


def _record_run(notified: bool) -> None:
    conn = _get_db()
    conn.execute("INSERT INTO digest_runs (ran_at, notified) VALUES (?, ?)", (time.time(), int(notified)))
    conn.commit()
    conn.close()


def _grade_distribution() -> dict:
    dist: dict[str, dict[str, int]] = {}
    repos: set[str] = set()
    for entry in get_latest(owner=FLEET_OWNER):
        repos.add(entry["repo"])
        bucket = dist.setdefault(entry["platform"], {})
        grade = entry.get("grade") or "none"
        bucket[grade] = bucket.get(grade, 0) + 1
    return {"platforms": dist, "repos": len(repos)}


def build_digest() -> dict:
    """Assemble the digest data dict from local stores (no network)."""
    now = time.time()
    recent_cutoff = now - RECENT_DAYS * 86400

    open_advice = list_advice(status="open")
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    open_advice.sort(key=lambda item: (severity_rank.get(item["severity"], 99), item["target"]))
    done_advice = list_advice(status="done")
    aged_advice = [item for item in open_advice if item["created_at"] < now - AGED_DAYS * 86400]

    recent_events = [event for event in list_events() if event["received_at"] >= recent_cutoff]
    failed_builds = [event for event in recent_events if event["type"] == "F"]
    moves = [link for link in list_links() if link["discovered_at"] >= recent_cutoff]

    return {
        "generated_at": now,
        "distribution": _grade_distribution(),
        "deltas": grade_deltas(FLEET_OWNER),
        "worst_tools": worst_tools(FLEET_OWNER, limit=5),
        "stale": stale_entries(FLEET_OWNER, max_days=7)[:5],
        "stale_count": len(stale_entries(FLEET_OWNER, max_days=7)),
        "advice_open": open_advice[:8],
        "advice_open_count": len(open_advice),
        "advice_done_count": len(done_advice),
        "aged_advice": aged_advice,
        "pending_releases": pending_releases(),
        "failed_builds": failed_builds,
        "recent_mail_count": len(recent_events),
        "competitor_moves": moves,
    }


def render_markdown(data: dict) -> str:
    """ASCII-only markdown digest (no em dashes, per fleet hygiene)."""
    dist = data["distribution"]
    lines = [
        "# Grades Digest",
        "",
        f"Repos tracked: {dist['repos']}",
        "",
        "## Grade distribution",
    ]
    for platform in sorted(dist["platforms"]):
        buckets = dist["platforms"][platform]
        parts = " ".join(f"{grade}:{count}" for grade, count in sorted(buckets.items()))
        lines.append(f"- {platform}: {parts}")
    lines.append("")

    if data["deltas"]:
        lines.append("## Score changes")
        for delta in data["deltas"][:8]:
            lines.append(
                f"- {delta['repo']} [{delta['platform']}]:"
                f" {delta['previous_grade']}->{delta['current_grade']} ({delta['score_change']:+.2f})"
            )
        lines.append("")

    if data["worst_tools"]:
        lines.append("## Worst tools")
        for tool in data["worst_tools"]:
            lines.append(f"- {tool['tool_name']} ({tool['repo']} [{tool['platform']}]): {tool['tool_score']}")
        lines.append("")

    if data["stale_count"]:
        lines.append(f"## Stale ({data['stale_count']} pairs >7d, top 5)")
        for row in data["stale"]:
            lines.append(f"- {row['repo']} [{row['platform']}]: {row['days_stale']}d")
        lines.append("")

    lines.append(f"## Advice ({data['advice_open_count']} open, {data['advice_done_count']} done)")
    for item in data["advice_open"]:
        lines.append(f"- [{item['severity'].upper()}] {item['repo']}: {item['kind']}/{item['target']}")
    lines.append("")
    if data["aged_advice"]:
        lines.append(f"## Aged advice (open >{AGED_DAYS}d)")
        for item in data["aged_advice"][:5]:
            lines.append(f"- {item['repo']}: {item['kind']}/{item['target']} [{item['severity']}]")
        lines.append("")

    if data["pending_releases"]:
        lines.append("## Release pending (built, never released)")
        for pending in data["pending_releases"]:
            lines.append(f"- {pending['repo']} {pending.get('version') or ''}".rstrip())
        lines.append("")
    if data["failed_builds"]:
        lines.append("## Failed builds (last 7d)")
        for event in data["failed_builds"]:
            lines.append(f"- {event['repo'] or event['subject'][:60]}")
        lines.append("")
    if data["competitor_moves"]:
        lines.append("## New competitors (last 7d)")
        for link in data["competitor_moves"]:
            lines.append(f"- {link['comp_owner']}/{link['comp_repo']} [{link['platform']}] for {link['repo']}")
        lines.append("")

    lines.append(f"Mail processed (7d): {data['recent_mail_count']}")
    return "\n".join(lines)


async def _post_event(title: str, urgency: float = 6.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{AIWATCHER_URL}/api/fleet/event",
                json={"title": title, "source": "scraper-mcp", "urgency_hint": urgency},
            )
        return True
    except Exception:
        return False


async def notify(data: dict) -> list[str]:
    """Post new-competitor / aged-advice / build-failed events. Returns sent titles."""
    since = _last_notified_run()
    sent: list[str] = []

    async def _send(title: str, urgency: float) -> None:
        if len(sent) < MAX_EVENTS and await _post_event(title, urgency):
            sent.append(title)

    for link in data["competitor_moves"]:
        if link["discovered_at"] > since:
            await _send(
                f"New competitor: {link['comp_owner']}/{link['comp_repo']} [{link['platform']}] rivals {link['repo']}",
                6.0,
            )
    for item in data["aged_advice"]:
        await _send(f"Aged advice: {item['repo']} {item['kind']}/{item['target']} open >{AGED_DAYS}d", 5.0)
    for event in data["failed_builds"]:
        await _send(f"Glama build failed: {event['repo'] or event['subject'][:60]}", 8.0)

    _record_run(notified=True)
    return sent


async def run_digest(notify_flag: bool = False) -> dict:
    """Build the digest; optionally notify. Always records the run."""
    data = build_digest()
    markdown = render_markdown(data)
    sent: list[str] = []
    if notify_flag:
        sent = await notify(data)
    else:
        _record_run(notified=False)
    return {"data": data, "markdown": markdown, "notified": sent}
