# scraper-mcp

<p align="center">
  <a href="https://github.com/casey/just"><img src="https://img.shields.io/badge/just-ready_to_go-7c5cfc?style=flat-square&logo=just&logoColor=white" alt="Just"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://biomejs.dev"><img src="https://img.shields.io/badge/Linted_with-Biome-60a5fa?style=flat-square&logo=biome&logoColor=white" alt="Biome"></a>
  <a href="https://github.com/PrefectHQ/fastmcp"><img src="https://img.shields.io/badge/FastMCP-3.2-7c5cfc?style=flat-square" alt="FastMCP"></a>
</p>


> 📖 **[Installation Guide](INSTALL.md)** — quick start, manual setup, and troubleshooting

**FastMCP 3.2** fleet server for MCP directory grades and ToolBench workflows. Monitors **ToolBench** (Arcade.dev), **Glama.ai**, and **LobeHub Marketplace**, plus the former **toolbench-mcp** features: `toolbench_guide`, Playwright page archiver, `/tools` and `/logs` fleet pages.

### Supersedes toolbench-mcp

| Repo | Role | Ports |
|------|------|-------|
| **scraper-mcp** (this) | Grades matrix + ToolBench guide + Playwright archiver | **10998** backend / **10999** frontend |
| **[toolbench-mcp](https://github.com/sandraschi/toolbench-mcp)** | **Deprecated** — migrate MCP config to this repo | ~~10816 / 10817~~ |

MCP clients: point HTTP transport at `http://127.0.0.1:10998/mcp` (was 10817).

## Features

- **Coverage matrix** — which fleet repos are indexed on which platforms
- **Grade tracking** — letter grades, numeric scores, TDQS dimensions per platform
- **Delta history** — SQLite-persisted grade changes over time
- **Reassess triggers** — request rescoring via ToolBench submit flow
- **toolbench_guide** — curated Arcade links, rescoring steps, Glama vs ToolBench notes
- **Playwright archiver** — `/api/scraper/*` + **Tools** webapp page (optional `uv sync --extra scraper`)
- **Fleet pages** — `/tools`, `/logs`, `/api/capabilities`, `/api/logs`

## Quick Start

```powershell
git clone https://github.com/sandraschi/scraper-mcp
cd scraper-mcp
just
```

Or:

```powershell
cd D:\Dev\repos\scraper-mcp
.\start.ps1
```

Backend only:

```powershell
uv run python -m scraper_mcp.server --http --port 10998
```

Browser: `http://127.0.0.1:10999`

## MCP Tools

| Tool | Description |
|---|---|
| `scraper_refresh` | Scan all platforms for fleet repos, persist grades |
| `scraper_matrix` | Coverage matrix: repos × platforms with grade badges |
| `scraper_repo` | Detailed report for a single repo with history |
| `scraper_reassess` | Request rescoring on ToolBench (or all platforms) |
| `scraper_platforms` | List available grading platforms & capabilities |
| `toolbench_guide` | Arcade ToolBench workflow links and rescoring guidance |

## Transports

- **HTTP**: `uv run python -m scraper_mcp.server --http --port 10998` — MCP at `/mcp`, REST at `/api/*`
- **Stdio**: `uv run python -m scraper_mcp.server --stdio` — for Cursor/Claude Desktop

## Architecture

```
scrapers/engine.py       # ToolBench, Glama, LobeHub scrapers
analytics.py             # SQLite grade store + delta history
scraper_api.py           # Playwright ToolBench archiver (from toolbench-mcp)
mcp/tools/coverage.py    # scraper_* tools
mcp/tools/guide.py       # toolbench_guide
app.py                   # FastAPI: grades API + fleet routes + MCP mount
```

## Fleet

| Role | Port |
|---|---|
| Backend (FastAPI + FastMCP) | **10998** |
| Frontend (Vite + React) | **10999** |

## License

MIT
