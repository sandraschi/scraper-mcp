from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scraper_mcp.app import app


def test_health() -> None:
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert j.get("service") == "scraper-mcp"


async def _fake_run_script(_args: list[str]) -> dict:
    return {"returncode": 0, "stdout": "", "stderr": "", "command": []}


def test_scraper_post(monkeypatch: pytest.MonkeyPatch) -> None:
    import scraper_mcp.scraper_api as sa

    monkeypatch.setattr(sa, "_run_script", _fake_run_script)
    c = TestClient(app)
    r = c.post(
        "/api/scraper/scrape",
        json={
            "urls_text": "https://toolbench.arcade.dev/tools/example",
            "out_subdir": "pytest_tmp",
        },
    )
    assert r.status_code == 200
    assert r.json().get("success") is True


def test_capabilities() -> None:
    c = TestClient(app)
    r = c.get("/api/capabilities")
    assert r.status_code == 200
    assert r.json().get("server", {}).get("name") == "scraper-mcp"


def test_meta_tools_includes_guide() -> None:
    c = TestClient(app)
    r = c.get("/api/meta/tools")
    assert r.status_code == 200
    names = [t["name"] for t in r.json().get("tools", [])]
    assert "toolbench_guide" in names
    assert "scraper_matrix" in names
