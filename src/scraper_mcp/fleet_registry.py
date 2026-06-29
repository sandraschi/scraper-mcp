"""Load fleet repo ids from mcp-central-docs registry (local path override via env)."""

from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT = Path("D:/Dev/repos/mcp-central-docs/operations/fleet-registry.json")


def fleet_registry_path() -> Path:
    raw = os.getenv("SCRAPER_FLEET_REGISTRY", "").strip()
    return Path(raw) if raw else _DEFAULT


def load_fleet_repo_ids() -> list[str]:
    path = fleet_registry_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    fleet = data.get("fleet", data.get("repos", []))
    ids: list[str] = []
    for row in fleet:
        if isinstance(row, dict):
            rid = row.get("id") or row.get("name")
            if rid:
                ids.append(str(rid))
    # Always track scraper-mcp itself
    if "scraper-mcp" not in ids:
        ids.append("scraper-mcp")
    return sorted(set(ids))
