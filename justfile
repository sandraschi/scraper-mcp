set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

# scraper-mcp justfile
import 'scripts/just/fleet.just'
# scraper-mcp justfile
# Fleet SOTA recipes

# Open the interactive recipe dashboard in the browser
default:
    @just --list

start:
    pwsh -ExecutionPolicy Bypass -File "{{justfile_directory()}}\start.ps1"

start-backend:
    uv run python -m scraper_mcp.server --http --port 10998

start-webapp:
    cd webapp && npm run dev

build-webapp:
    cd webapp && npm install && npm run build

test:
    uv run pytest tests/ -v

e2e:
    Set-Location '{{justfile_directory()}}\webapp'; npx playwright test

lint:
    ruff check src/ tests/

fix:
    ruff check src/ tests/ --fix

dev:
    uv run python -m scraper_mcp.server --http --port 10998

# ── Tauri Native ───────────────────────────────────────────────────────────────

# Certify: run all verification gates
certify: lint
    uv run pytest tests/ -q

# Build Tauri native desktop app (full pipeline: frontend + backend)
build-native:
    Set-Location '{{justfile_directory()}}\native'
    $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
    npx @tauri-apps/cli build

# Daily refresh: pull grades from all platforms and alert on drops
daily-refresh:
    uv run python -c "import asyncio; from scraper_mcp.scrapers.engine import refresh_all; from scraper_mcp.analytics import upsert_grade; from scraper_mcp.mcp.tools.suggest import _alert_if_drop; r = asyncio.run(refresh_all('sandraschi', None)); [(upsert_grade(p,'sandraschi',x['repo'],x.get('grade'),x.get('score'),x), print(f'{p}/{x[\"repo\"]}: {x.get(\"grade\",\"?\")}')) for p,rs in r.items() for x in rs]"

# Register daily refresh Windows scheduled task
register-daily-refresh:
    powershell.exe -NoProfile -File "{{justfile_directory()}}\scripts\register-daily-refresh.ps1"
