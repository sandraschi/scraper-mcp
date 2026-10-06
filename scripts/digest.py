"""CLI: print the daily grades digest (markdown and/or JSON), optionally notify.

Usage:
    uv run python scripts/digest.py [--format markdown|json|both] [--notify] [--out FILE]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from scraper_mcp.digest import run_digest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily grades digest")
    parser.add_argument("--format", default="both", choices=("markdown", "json", "both"))
    parser.add_argument("--notify", action="store_true", help="Post fleet events to aiwatcher")
    parser.add_argument("--out", default="", help="Write markdown to FILE (stdout otherwise)")
    args = parser.parse_args()

    result = asyncio.run(run_digest(notify_flag=args.notify))
    if args.format in ("markdown", "both"):
        if args.out:
            Path(args.out).write_text(result["markdown"] + "\n", encoding="utf-8")
            print(f"Wrote {args.out}")
        else:
            print(result["markdown"])
    if args.format in ("json", "both"):
        print(json.dumps(result["data"], indent=1, default=str))
    if result["notified"]:
        print(f"Notified {len(result['notified'])} events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
