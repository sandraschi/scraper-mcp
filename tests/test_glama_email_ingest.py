"""Tests for Glama email ingest (Phase 1). Fixture mails, mocked HTTP, tmp DB."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest

from scraper_mcp import email_ingest

FIXTURES = Path(__file__).parent / "fixtures" / "glama_email"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """Redirect the SQLite depot to a temp dir."""
    monkeypatch.setattr(email_ingest, "DB_DIR", tmp_path)
    monkeypatch.setattr(email_ingest, "DB_PATH", tmp_path / "test_grades.db")
    return tmp_path


# ===========================================================================
# classify_subject
# ===========================================================================


def test_classify_release():
    kind, version, repo = email_ingest.classify_subject("Release 1.0.4 published for onenote-mcp")
    assert (kind, version, repo) == ("R", "1.0.4", "onenote-mcp")


def test_classify_build_ok():
    assert email_ingest.classify_subject("Build succeeded for onenote-mcp")[0] == "B"


def test_classify_build_failed():
    kind, _, repo = email_ingest.classify_subject("Build failed for virtualization-mcp")
    assert (kind, repo) == ("F", "virtualization-mcp")


def test_classify_otp():
    assert email_ingest.classify_subject("Your OTP: NCQR0R")[0] == "O"


def test_classify_unknown():
    assert email_ingest.classify_subject("Glama weekly digest")[0] == "unknown"


# ===========================================================================
# parse_message (pure, fixture-driven)
# ===========================================================================


def test_parse_release():
    event = email_ingest.parse_message(_load("release_onenote_104.json"))
    assert event["type"] == "R"
    assert event["repo"] == "onenote-mcp"
    assert event["version"] == "1.0.4"
    assert event["owner"] == "sandraschi"
    assert event["glama_url"] == "https://glama.ai/mcp/servers/sandraschi/onenote-mcp"
    assert event["email_id"] == "glama-msg-r1"


def test_parse_build_ok_links():
    event = email_ingest.parse_message(_load("build_ok_onenote.json"))
    assert event["type"] == "B"
    assert event["repo"] == "onenote-mcp"
    assert event["build_url"] and "build" in event["build_url"]
    assert event["releases_url"] and "releases" in event["releases_url"]


def test_parse_build_failed():
    event = email_ingest.parse_message(_load("build_failed_virt.json"))
    assert event["type"] == "F"
    assert event["repo"] == "virtualization-mcp"
    assert event["build_url"] is not None


def test_parse_otp_no_crash():
    event = email_ingest.parse_message(_load("otp.json"))
    assert event["type"] == "O"
    assert event["repo"] is None


def test_parse_non_repo_kept_with_note():
    """'AI Producer Hub' is a display name, not a slug: repo rescued from the
    Glama URL, with a provenance note (no silent force-fit)."""
    event = email_ingest.parse_message(_load("release_nonrepo.json"))
    assert event["type"] == "R"
    assert event["version"] == "0.1.0"
    assert event["repo"] == "ai-producer-hub"
    assert event["note"] and "Glama URL" in event["note"]


# ===========================================================================
# store: idempotent upsert, filters, pending_releases
# ===========================================================================


def test_upsert_idempotent(tmp_store):
    event = email_ingest.parse_message(_load("release_onenote_104.json"))
    assert email_ingest.upsert_event(event) is True
    assert email_ingest.upsert_event(event) is False
    assert len(email_ingest.list_events()) == 1


def test_list_events_filters(tmp_store):
    for name in ("release_onenote_104.json", "build_ok_onenote.json", "build_failed_virt.json"):
        email_ingest.upsert_event(email_ingest.parse_message(_load(name)))
    assert len(email_ingest.list_events()) == 3
    assert len(email_ingest.list_events(repo="onenote-mcp")) == 2
    assert len(email_ingest.list_events(type="F")) == 1
    assert email_ingest.list_events(type="F")[0]["repo"] == "virtualization-mcp"


def _event(email_id: str, kind: str, repo: str, received_at: float) -> dict:
    return {
        "email_id": email_id,
        "type": kind,
        "repo": repo,
        "version": "1.0.0",
        "owner": "sandraschi",
        "subject": f"{kind} {repo}",
        "from": "Glama Support <support@glama.ai>",
        "received_at": received_at,
        "glama_url": None,
        "build_url": None,
        "releases_url": None,
        "note": None,
    }


def test_pending_releases_only_old_lone_builds(tmp_store):
    now = time.time()
    day = 86400
    # Old lone build -> pending.
    email_ingest.upsert_event(_event("b-old", "B", "stale-mcp", now - 10 * day))
    # Recent lone build -> not yet pending.
    email_ingest.upsert_event(_event("b-new", "B", "fresh-mcp", now - 1 * day))
    # Old build WITH later release -> closed.
    email_ingest.upsert_event(_event("b-closed", "B", "done-mcp", now - 10 * day))
    email_ingest.upsert_event(_event("r-closed", "R", "done-mcp", now - 9 * day))
    pending = email_ingest.pending_releases(days=7)
    assert [p["repo"] for p in pending] == ["stale-mcp"]


# ===========================================================================
# ingest end-to-end with mocked email-mcp HTTP
# ===========================================================================


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Records calls; serves folder listing then per-message details."""

    def __init__(self, fixtures: dict[str, dict]):
        self.fixtures = fixtures
        self.calls: list[tuple[str, str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, auth=None):
        self.calls.append(("GET", url, params or {}))
        if url.endswith("/api/inbox"):
            return FakeResponse(
                {
                    "success": True,
                    "emails": [
                        {"id": fid, "subject": rec["subject"], "from": rec["from"], "date": rec["date"]}
                        for fid, rec in self.fixtures.items()
                    ],
                }
            )
        message_id = url.rsplit("/", 1)[-1]
        rec = self.fixtures[message_id]
        return FakeResponse({"success": True, **rec})

    async def post(self, url, auth=None):
        self.calls.append(("POST", url, {}))
        return FakeResponse({"success": True})


@pytest.fixture
def live_like(monkeypatch):
    fixtures = {name.stem: _load(name.name) for name in sorted(FIXTURES.glob("*.json"))}
    # Align fixture ids with lookup keys.
    by_id = {rec["id"]: rec for rec in fixtures.values()}
    fake = FakeAsyncClient(by_id)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake)
    monkeypatch.setattr(email_ingest, "EMAIL_MCP_WEB_PASSWORD", "test-pw")
    return fake


async def test_ingest_end_to_end(tmp_store, live_like):
    result = await email_ingest.ingest(service="graph", folder="Glama", limit=50)
    assert result["success"] is True
    assert result["data"]["ingested"] == 7
    assert result["data"]["by_type"] == {"R": 2, "B": 2, "F": 1, "O": 1, "unknown": 1}
    assert len(email_ingest.list_events()) == 7
    # Idempotent second run.
    again = await email_ingest.ingest(service="graph", folder="Glama", limit=50)
    assert again["data"]["ingested"] == 0


async def test_ingest_uses_folder_listing_by_default(tmp_store, live_like):
    await email_ingest.ingest()
    urls = [url for _, url, _ in live_like.calls]
    assert any(u.endswith("/api/inbox") for u in urls)
    assert not any("folder:" in str(params.get("$search", "")) for _, _, params in live_like.calls)


async def test_ingest_without_password_fails_clearly(tmp_store, monkeypatch):
    monkeypatch.setattr(email_ingest, "EMAIL_MCP_WEB_PASSWORD", "")
    result = await email_ingest.ingest()
    assert result["success"] is False
    assert "EMAIL_MCP_WEB_PASSWORD" in result["error"]


async def test_scraper_email_tool_registered():
    """The scraper_email portmanteau op is actually registered on the MCP server."""
    from scraper_mcp.mcp import tools as _tools  # noqa: F401 - registration side effect
    from scraper_mcp.mcp.registry import mcp

    names = [tool.name for tool in await mcp.list_tools()]
    assert "scraper_email" in names


def test_parse_wrapped_boundary_and_safelinks():
    """Live shape: sanitize boundary markers + Outlook SafeLinks hrefs.

    The classifier must see through the boundary; stored URLs must be the
    unwrapped glama.ai destinations (releases = admin releases page).
    """
    event = email_ingest.parse_message(_load("build_wrapped_safelinks.json"))
    assert event["type"] == "B"
    assert event["repo"] == "onenote-mcp"
    assert event["subject"] == "Build succeeded for onenote-mcp"
    assert event["from"] == "Glama Support <support@glama.ai>"
    assert "safelinks" not in (event["build_url"] or "")
    assert "safelinks" not in (event["releases_url"] or "")
    assert event["build_url"].startswith("https://glama.ai/mcp/servers/sandraschi/onenote-mcp")
    assert event["releases_url"] == "https://glama.ai/mcp/servers/sandraschi/onenote-mcp/admin/releases"


def test_unwrap_boundary_passthrough():
    """No markers -> raw text (fixtures, other sources)."""
    assert email_ingest._unwrap_boundary("Release 1.0.4 published for x") == "Release 1.0.4 published for x"
    assert email_ingest._unwrap_boundary(None) == ""
    assert email_ingest._unwrap_url("https://glama.ai/mcp/servers/a/b") == "https://glama.ai/mcp/servers/a/b"
