"""Tests for the Phase 4 digest (seeded tmp stores, mocked aiwatcher POST)."""

from __future__ import annotations

import time

import httpx
import pytest

from scraper_mcp import advice as advice_mod
from scraper_mcp import digest as digest_mod
from scraper_mcp.analytics import upsert_grade
from scraper_mcp.competitors import upsert_links
from scraper_mcp.email_ingest import upsert_event


@pytest.fixture
def seeded(monkeypatch, tmp_path):
    """All four stores redirected to tmp; seed one of everything."""
    import scraper_mcp.analytics as analytics
    import scraper_mcp.competitors as competitors_mod
    import scraper_mcp.email_ingest as email_mod

    for mod in (analytics, advice_mod, competitors_mod, email_mod, digest_mod):
        monkeypatch.setattr(mod, "DB_DIR", tmp_path)
        monkeypatch.setattr(mod, "DB_PATH", tmp_path / "test_grades.db")

    now = time.time()
    upsert_grade(
        "glama",
        "sandraschi",
        "demo-mcp",
        "C",
        3.0,
        {"grade": "C", "score": 3.0, "tool_details": [{"name": "weak_tool", "score": 2.0}]},
    )
    advice_mod.upsert_advice(
        [
            {
                "repo": "demo-mcp",
                "platform": "glama",
                "kind": "dimension",
                "target": "purpose",
                "severity": "high",
                "text": "Purpose averages 2.0/5.",
                "fix_ref": "Fix it.",
            }
        ]
    )
    upsert_event(
        {
            "email_id": "m1",
            "type": "B",
            "repo": "demo-mcp",
            "version": "0.1.0",
            "owner": "sandraschi",
            "subject": "Build succeeded for demo-mcp",
            "from": "Glama",
            "received_at": now - 10 * 86400,
            "glama_url": None,
            "build_url": None,
            "releases_url": None,
            "note": None,
        }
    )
    upsert_links(
        "demo-mcp",
        [{"owner": "rival", "repo": "demo-mcp", "name": "Rival", "platform": "glama"}],
    )
    # Backdate the link + advice so they count as moves/aged.
    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "test_grades.db"))
    conn.execute("UPDATE competitor_links SET discovered_at = ?", (now - 86400,))
    conn.execute("UPDATE advice_items SET created_at = ?", (now - 20 * 86400,))
    conn.commit()
    conn.close()
    return tmp_path


def test_build_digest_sections(seeded):
    data = digest_mod.build_digest()
    assert data["distribution"]["repos"] == 1
    assert data["distribution"]["platforms"]["glama"]["C"] == 1
    assert data["worst_tools"][0]["tool_name"] == "weak_tool"
    assert data["advice_open_count"] == 1
    assert len(data["aged_advice"]) == 1
    assert len(data["pending_releases"]) == 1
    assert data["pending_releases"][0]["repo"] == "demo-mcp"
    assert len(data["competitor_moves"]) == 1


def test_render_markdown_ascii_and_sections(seeded):
    markdown = digest_mod.render_markdown(digest_mod.build_digest())
    assert markdown.isascii()
    for section in (
        "# Grades Digest",
        "## Grade distribution",
        "## Worst tools",
        "## Advice",
        "## Release pending",
        "## New competitors",
    ):
        assert section in markdown
    assert "demo-mcp" in markdown


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {}


class FakeAsyncClient:
    def __init__(self):
        self.posts: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None):
        self.posts.append(json)
        return FakeResponse()


async def test_notify_sends_once_then_dedupes(seeded, monkeypatch):
    fake = FakeAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake)

    first = await digest_mod.run_digest(notify_flag=True)
    titles = first["notified"]
    assert any("demo-mcp" in title for title in titles)
    assert any("Rival" in title or "rival" in title for title in titles)

    # Competitor moves dedupe against the recorded run; aged advice nags on.
    second = await digest_mod.run_digest(notify_flag=True)
    assert not [t for t in second["notified"] if "competitor" in t.lower()]


async def test_tool_registered():
    from scraper_mcp.mcp import tools as _tools  # noqa: F401 - registration side effect
    from scraper_mcp.mcp.registry import mcp

    names = [tool.name for tool in await mcp.list_tools()]
    assert "scraper_digest" in names


def test_justfile_has_digest_recipe():
    from pathlib import Path

    justfile = Path(__file__).parent.parent / "justfile"
    text = justfile.read_text(encoding="utf-8").replace("\\", "/")
    assert "digest *args:" in text
    assert "scripts/digest.py" in text
