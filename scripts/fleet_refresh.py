"""Full fleet refresh with owner-verified matching.

Usage: uv run python scripts/fleet_refresh.py [--owner sandraschi]

Records results to the ToolBench grades DB.
"""
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, "src")
from scraper_mcp.scrapers.engine import refresh_all
from scraper_mcp.fleet_registry import load_fleet_repo_ids


async def main():
    owner = os.sys.argv[1] if len(os.sys.argv) > 1 else "sandraschi"
    t0 = datetime.now()
    fleet = load_fleet_repo_ids()
    print(f"Fleet: {len(fleet)} repos | concurrency=3 delay=0.5s+jitter | owner={owner}")
    results = await refresh_all(owner)
    elapsed = (datetime.now() - t0).total_seconds()

    for pid, rows in sorted(results.items()):
        found = sum(1 for r in rows if r.get("grade", "?") not in ("?", "N/A", ""))
        errors = sum(1 for r in rows if r.get("status") == "fetch_error")
        scored = [r for r in rows if r.get("score") is not None]
        grades = {}
        for r in rows:
            g = r.get("grade", "?")
            grades[g] = grades.get(g, 0) + 1

        print(f"[{pid}]  {found}/{len(rows)} found  |  {errors} errors")
        if scored:
            scores = [r["score"] for r in scored if r["score"] is not None]
            mean = sum(scores) / len(scores) if scores else 0
            print(f"       mean: {mean:.1f}  |  grades: {dict(sorted(grades.items()))}")

    print(f"\nDone in {elapsed:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
