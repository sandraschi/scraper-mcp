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
    pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "D:\Dev\repos\mcp-central-docs\scripts\playwright-audit.ps1" -RepoPath "{{justfile_directory()}}"

lint:
    ruff check src/ tests/

fix:
    ruff check src/ tests/ --fix

dev:
    uv run python -m scraper_mcp.server --http --port 10998

# ── Tauri Native ───────────────────────────────────────────────────────────────

# Build Tauri native desktop app (full pipeline: frontend + backend)
build-native:
    Set-Location '{{justfile_directory()}}\native'
    $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
    npx @tauri-apps/cli build

# Run the CUA smoke test against the installed NSIS app
cua-nsis-test:
    uv run python scripts/cua-smoke.py
