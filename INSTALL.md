# scraper-mcp Installation Guide

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Git

## Quick Start

```powershell
# Clone and enter
git clone https://github.com/sandraschi/scraper-mcp.git
cd scraper-mcp

# Create virtualenv and install deps
uv sync --extra dev

# Run tests
uv run pytest tests/ -q

# Start the full stack (backend + webapp)
.\start.ps1
```

The backend starts on port **10998**, webapp on **10999**.

## Configuration

Set these environment variables (or copy `.env.example` to `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Backend bind address |
| `PORT` | `10998` | Backend port |
| `WEBAPP_PORT` | `10999` | Frontend dev server port |
| `LLM_GATEWAY_URL` | — | llm-gateway URL for AI suggestions |
| `LLM_GATEWAY_PROVIDER` | `ollama` | llm-gateway provider |
| `LLM_GATEWAY_MODEL` | `qwen2.5:14b` | llm-gateway model |
| `AIWATCHER_URL` | `http://127.0.0.1:10946/api/fleet/event` | aiwatcher-mcp alert target |
| `SCRAPER_ALERT_THRESHOLD` | `B` | Grade threshold for alerts |

## Webapp

The webapp is a React + Vite + Tailwind app in `webapp/`. Development:

```powershell
cd webapp
npm install
npm run dev
```

## Testing

```powershell
uv run pytest tests/ -q           # Unit tests (36 total)
uv run pytest tests/ -v           # Verbose
```
