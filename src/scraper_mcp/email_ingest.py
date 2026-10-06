"""Glama email ingest - Phase 1 of the email -> advice -> digest workflow.

Turns the Hotmail `Glama` folder (via email-mcp) into typed lifecycle events:
R (release published), B (build succeeded), F (build failed), O (OTP, ignored),
unknown (kept for review, never dropped).

Spec: docs/SPEC_GLAMA_EMAIL_PHASE1_20261006.md. Phase 1 is ingest + store only;
advice/competitors/digest are later phases. All email content is untrusted:
regex-first extraction, no raw HTML leaves this module.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from .analytics import DB_DIR, DB_PATH

EMAIL_MCP_BASE_URL = os.getenv("EMAIL_MCP_BASE_URL", "http://127.0.0.1:10813")
EMAIL_MCP_WEB_USER = os.getenv("EMAIL_MCP_WEB_USER", "sandra")
# No default password, ever: fail with a clear message instead (see _auth).
EMAIL_MCP_WEB_PASSWORD = os.getenv("EMAIL_MCP_WEB_PASSWORD", "")

GLAMA_FOLDER = "Glama"
PENDING_DAYS_DEFAULT = 7

# --- subject shapes (subjects are primary; bodies confirm) -------------------

_SUBJECT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("R", re.compile(r"^Release (\S+) published for (.+)$")),
    ("B", re.compile(r"^Build succeeded for (.+)$")),
    ("F", re.compile(r"^Build failed for (.+)$")),
    ("O", re.compile(r"(?i)\bOTP\b")),
]

_BODY_PATTERNS: dict[str, re.Pattern[str]] = {
    "R": re.compile(r"Release (\S+) of ([\w][\w.\-]*) was published on (.+?)\."),
    "B": re.compile(r"The build for ([\w][\w.\-]*) has succeeded"),
    "F": re.compile(r"The build for ([\w][\w.\-]*) has failed"),
}

_HREF_RE = re.compile(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_GLAMA_SERVER_RE = re.compile(r"glama\.ai/mcp/servers/([^/]+)/([^/?#]+)", re.I)

_REPO_RE = re.compile(r"^[\w][\w.\-]*$")


def _norm_repo(raw: str | None) -> str | None:
    """Lowercase repo slug, or None for display names ('AI Producer Hub')."""
    if not raw:
        return None
    slug = raw.strip().lower()
    return slug if _REPO_RE.match(slug) else None


def classify_subject(subject: str) -> tuple[str, str | None, str | None]:
    """Return (type, version, repo_raw). Unknown subjects -> ('unknown', None, None)."""
    subject = (subject or "").strip()
    for kind, pattern in _SUBJECT_PATTERNS:
        match = pattern.search(subject)
        if not match:
            continue
        if kind == "R":
            return kind, match.group(1), match.group(2)
        if kind == "O":
            return kind, None, None
        return kind, None, match.group(1)
    return "unknown", None, None


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub("", html or "")


_BOUNDARY_RE = re.compile(r"---BEGIN EMAIL_DETAIL_\w+---\s*(.*?)\s*---END", re.S)


def _unwrap_boundary(text: str | None) -> str:
    """Strip email-mcp's prompt-injection safety boundary, return inner payload.

    The markers prove sanitize.py is active; the classifier must see through
    them (wrapped subjects otherwise start with '<<< UNTRUSTED ...'). Falls
    back to raw text when no markers are present (fixtures, other sources).
    """
    if not text:
        return ""
    match = _BOUNDARY_RE.search(text)
    return match.group(1) if match else text


def _unwrap_url(href: str) -> str:
    """Decode entities + unwrap Outlook SafeLinks to the real destination."""
    url = unescape((href or "").strip())
    if "safelinks.protection.outlook.com" in url.lower():
        try:
            inner = parse_qs(urlparse(url).query).get("url", [""])[0]
            return unquote(inner) if inner else url
        except Exception:
            return url
    return url


def _extract_links(html_body: str | None) -> list[tuple[str, str]]:
    """(unwrapped href, link_text) pairs from an HTML body. Empty for None."""
    if not html_body:
        return []
    body = _unwrap_boundary(html_body)
    return [(_unwrap_url(href), _strip_tags(text).strip()) for href, text in _HREF_RE.findall(body)]


def _classify_url(href: str, label: str = "") -> str | None:
    """build_url | releases_url | glama_url | None.

    Link TEXT rules first ("View build details" etc. - faithful to the mail
    structure and immune to path renames); URL patterns as fallback.
    Specific-before-generic: admin releases/build URLs also match the
    plain server pattern, and /admin/dockerfile/tests/ carries no
    "build" token at all.
    """
    text = (label or "").lower()
    if "build" in text:
        return "build_url"
    if "release" in text:
        return "releases_url"
    if "view server" in text:
        return "glama_url"
    low = href.lower()
    if "build" in low:
        return "build_url"
    if "releases" in low:
        return "releases_url"
    if "admin" in low and ("test" in low or "docker" in low):
        return "build_url"
    if _GLAMA_SERVER_RE.search(href):
        return "glama_url"
    return None


def _parse_epoch(date_str: str | None) -> float:
    """Best-effort mail date -> epoch. Unparseable -> now (never auto-pending)."""
    if date_str:
        text = date_str.strip()
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).timestamp()
            except ValueError:
                continue
    return time.time()


def parse_message(msg: dict) -> dict:
    """Pure: raw email-mcp message -> typed event dict (no I/O)."""
    subject = _unwrap_boundary(msg.get("subject", "") or "")
    kind, version, repo_raw = classify_subject(subject)
    text_body = _unwrap_boundary(msg.get("text_body", "") or "")
    html_body = _unwrap_boundary(msg.get("html_body"))
    sender = _unwrap_boundary(msg.get("from", "") or "")

    repo = _norm_repo(repo_raw)
    subject_slug_bad = bool(repo_raw and repo is None)
    note = None

    # Body confirmation (subjects rule; bodies corroborate version).
    if kind == "R":
        body_match = _BODY_PATTERNS["R"].search(text_body)
        if body_match:
            version = version or body_match.group(1)
            repo = repo or _norm_repo(body_match.group(2))
    elif kind in ("B", "F"):
        body_match = _BODY_PATTERNS[kind].search(text_body)
        if body_match:
            repo = repo or _norm_repo(body_match.group(1))

    urls: dict[str, str] = {}
    owner: str | None = None
    for href, label in _extract_links(html_body):
        slot = _classify_url(href, label)
        if slot and slot not in urls:
            urls[slot] = href
        server_match = _GLAMA_SERVER_RE.search(href)
        if server_match and owner is None:
            owner = server_match.group(1).lower()
            repo = repo or _norm_repo(server_match.group(2))

    if subject_slug_bad:
        if repo is None:
            note = f"non-repo display name kept as-is: {repo_raw.strip()!r}"
        else:
            note = f"subject name {repo_raw.strip()!r} is not a slug; repo resolved from Glama URL"

    return {
        "email_id": str(msg.get("id", "")),
        "type": kind,
        "repo": repo,
        "version": version,
        "owner": owner,
        "subject": subject,
        "from": sender,
        "received_at": _parse_epoch(msg.get("date")),
        "glama_url": urls.get("glama_url"),
        "build_url": urls.get("build_url"),
        "releases_url": urls.get("releases_url"),
        "note": note,
    }


# --- store (same SQLite depot as grades) -------------------------------------


def _get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL,
            repo TEXT,
            version TEXT,
            owner TEXT,
            subject TEXT,
            sender TEXT,
            received_at REAL NOT NULL,
            glama_url TEXT,
            build_url TEXT,
            releases_url TEXT,
            note TEXT,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_repo ON email_events(repo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(type)")
    conn.commit()
    return conn


def upsert_event(event: dict) -> bool:
    """Insert idempotently on email_id. Returns True if the row is new."""
    if not event.get("email_id"):
        return False
    conn = _get_db()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO email_events
        (email_id, type, repo, version, owner, subject, sender, received_at,
         glama_url, build_url, releases_url, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["email_id"],
            event["type"],
            event.get("repo"),
            event.get("version"),
            event.get("owner"),
            event.get("subject", ""),
            event.get("from", ""),
            event.get("received_at", time.time()),
            event.get("glama_url"),
            event.get("build_url"),
            event.get("releases_url"),
            event.get("note"),
            time.time(),
        ),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount == 1


def list_events(repo: str | None = None, type: str | None = None, since: float | None = None) -> list[dict]:
    """Read back stored events, optionally filtered."""
    conn = _get_db()
    query = (
        "SELECT email_id, type, repo, version, owner, subject, sender, received_at,"
        " glama_url, build_url, releases_url, note, created_at FROM email_events WHERE 1=1"
    )
    params: list = []
    if repo:
        query += " AND repo = ?"
        params.append(repo.strip().lower())
    if type:
        query += " AND type = ?"
        params.append(type)
    if since:
        query += " AND received_at >= ?"
        params.append(since)
    query += " ORDER BY received_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    keys = (
        "email_id",
        "type",
        "repo",
        "version",
        "owner",
        "subject",
        "from",
        "received_at",
        "glama_url",
        "build_url",
        "releases_url",
        "note",
        "created_at",
    )
    return [dict(zip(keys, row)) for row in rows]


def pending_releases(days: int = PENDING_DAYS_DEFAULT) -> list[dict]:
    """Type B older than `days` with no later Type R for the same repo.

    NOTE (SPEC deviation, documented): the git-github-mcp `release_list`
    cross-check is deferred until that API surface is confirmed; email-only
    for now, which already catches the "built but never released" case.
    """
    cutoff = time.time() - days * 86400
    conn = _get_db()
    builds = conn.execute(
        "SELECT repo, version, subject, received_at, build_url, releases_url, email_id"
        " FROM email_events WHERE type = 'B' AND repo IS NOT NULL AND received_at < ?",
        (cutoff,),
    ).fetchall()
    pending = []
    for repo, version, subject, received_at, build_url, releases_url, email_id in builds:
        later_release = conn.execute(
            "SELECT 1 FROM email_events WHERE type = 'R' AND repo = ? AND received_at > ? LIMIT 1",
            (repo, received_at),
        ).fetchone()
        if not later_release:
            pending.append(
                {
                    "repo": repo,
                    "version": version,
                    "subject": subject,
                    "built_at": received_at,
                    "build_url": build_url,
                    "releases_url": releases_url,
                    "email_id": email_id,
                }
            )
    conn.close()
    return sorted(pending, key=lambda item: item["built_at"])


# --- email-mcp HTTP client (fail-soft, like the aiwatcher pattern) -----------


def _auth() -> tuple[str, tuple[str, str] | None, str | None]:
    """(base_url, basic_auth_or_None, error_or_None). Password has no default."""
    if not EMAIL_MCP_WEB_PASSWORD:
        return (
            EMAIL_MCP_BASE_URL,
            None,
            "EMAIL_MCP_WEB_PASSWORD is not set - export it (same value as the"
            " email-mcp dashboard login) to enable mailbox ingest.",
        )
    return EMAIL_MCP_BASE_URL, (EMAIL_MCP_WEB_USER, EMAIL_MCP_WEB_PASSWORD), None


async def _email_mcp_get(path: str, params: dict | None = None) -> dict:
    base, auth, error = _auth()
    if error or auth is None:
        return {"success": False, "error": error or "email-mcp auth unavailable"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base}{path}", params=params or {}, auth=auth)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"success": False, "error": "unexpected response shape"}
    except Exception as exc:
        return {"success": False, "error": f"email-mcp request failed: {exc}"}


async def _email_mcp_post(path: str) -> dict:
    base, auth, error = _auth()
    if error or auth is None:
        return {"success": False, "error": error or "email-mcp auth unavailable"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base}{path}", auth=auth)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"success": True}
    except Exception as exc:
        return {"success": False, "error": f"email-mcp request failed: {exc}"}


async def ingest(
    service: str = "graph",
    folder: str = GLAMA_FOLDER,
    limit: int = 50,
    query: str | None = None,
    mark_read: bool = False,
) -> dict:
    """Fetch Glama mails, classify, parse, persist. Idempotent on email_id.

    Default path lists the folder (proven against the live mailbox); pass
    `query` to use folder-scoped $search instead. mark_read marks consumed
    messages read via email-mcp (default off).
    """
    if query:
        listing = await _email_mcp_get(
            "/api/search", {"q": query, "service": service, "folder": folder, "limit": limit}
        )
    else:
        listing = await _email_mcp_get("/api/inbox", {"service": service, "folder": folder, "limit": limit})
    if not listing.get("success"):
        return {"success": False, "error": listing.get("error", "mailbox listing failed"), "ingested": 0}

    ingested = 0
    by_type: dict[str, int] = {}
    for summary in listing.get("emails", []):
        email_id = summary.get("id", "")
        if not email_id:
            continue
        detail = await _email_mcp_get(f"/api/inbox/{email_id}")
        if not detail.get("success"):
            continue
        message = {
            "id": email_id,
            "subject": detail.get("subject", summary.get("subject", "")),
            "from": detail.get("from", summary.get("from", "")),
            "date": detail.get("date", summary.get("date", "")),
            "text_body": detail.get("text_body", ""),
            "html_body": detail.get("html_body"),
        }
        event = parse_message(message)
        if upsert_event(event):
            ingested += 1
        by_type[event["type"]] = by_type.get(event["type"], 0) + 1
        if mark_read:
            await _email_mcp_post(f"/api/inbox/{email_id}/mark-read")

    pending = pending_releases()
    return {
        "success": True,
        "message": f"Ingested {ingested} new Glama mails ({len(by_type)} types seen).",
        "data": {
            "ingested": ingested,
            "by_type": by_type,
            "pending_releases": [{"repo": p["repo"], "built_at": p["built_at"]} for p in pending],
        },
    }
