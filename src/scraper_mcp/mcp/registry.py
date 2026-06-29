"""Shared FastMCP instance — imported by all tool modules."""

from fastmcp import FastMCP

mcp = FastMCP(
    "scraper-mcp",
    instructions=(
        "Fleet MCP grade aggregator: ToolBench, Glama, LobeHub coverage matrix with SQLite history. "
        "Includes toolbench_guide (rescoring links) and ToolBench Playwright page archiver via /api/scraper. "
        "Replaces deprecated toolbench-mcp (10816/10817) — use ports 10998/10999."
    ),
)
