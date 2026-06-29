param(
    [switch]$Headless,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoBrowser,
    [switch]$ReuseIfRunning)

$RepoRoot = Split-Path -Parent $PSScriptRoot
$FleetStartPath = Join-Path $RepoRoot "scripts\FleetStartMode.ps1"
if (-not (Test-Path -LiteralPath $FleetStartPath)) {
    Write-Host "ERROR: Missing vendored launcher helper: $FleetStartPath" -ForegroundColor Red
    exit 1
}
. $FleetStartPath
$FleetStart = Initialize-FleetStartMode @PSBoundParameters
Enter-FleetHeadlessConsole -Headless:$Headless -BackendOnly:$BackendOnly

$portResolve = @{
    Ports      = @($WebPort, $BackendPort)
    Label      = "scraper-mcp"
    AllowReuse = $ReuseIfRunning
}
if ($ReuseIfRunning) {
    $portResolve.HealthChecks = @{
        $WebPort = "http://127.0.0.1:$WebPort/"
        $BackendPort = "http://127.0.0.1:$BackendPort/health"
    }
}
$portState = Resolve-FleetPortConflict @portResolve
if ($portState.Action -eq 'Blocked') { exit 1 }
if ($portState.Reuse) { return }
$WebPort = 10999
$BackendPort = 10998

Write-Host "Starting scraper-mcp (fleet SOTA)..." -ForegroundColor Cyan
Write-Host "Frontend $WebPort | Backend $BackendPort | MCP /mcp" -ForegroundColor Gray


Set-Location $PSScriptRoot
if (-not (Test-Path "node_modules")) { npm install }

if ($FleetStart.RunBackend) {
    Write-Host "Syncing Python deps (uv sync) ..." -ForegroundColor Cyan
    Push-Location $RepoRoot
    try { uv sync; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } } finally { Pop-Location }

    $backendCmd = @"
Set-Location '$RepoRoot'
uv run python -m scraper_mcp.server --http --port $BackendPort
"@
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WorkingDirectory $RepoRoot -WindowStyle Normal

    $healthUrl = "http://127.0.0.1:$BackendPort/health"
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $null = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
            $ready = $true
            Write-Host "Backend ready on $BackendPort" -ForegroundColor Green
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        Write-Host "Backend failed to bind on $BackendPort within 30s" -ForegroundColor Red
        exit 1
    }
}

if (-not $FleetStart.RunFrontend) { return }

$frontendUrl = "http://127.0.0.1:$WebPort/"
if (-not $FleetStart.SkipBrowser) {
    $pollAndOpen = @"
for (`$i = 0; `$i -lt 60; `$i++) {
    try {
        `$null = Invoke-WebRequest -Uri '$frontendUrl' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        Start-Process '$frontendUrl'
        exit
    } catch { Start-Sleep -Seconds 1 }
}
"@
    Start-Process powershell -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-Command", $pollAndOpen
}

Write-Host "Starting Vite on $WebPort ..." -ForegroundColor Green
for ($i = 0; $i -lt 10; $i++) {
    $listeners = Get-NetTCPConnection -LocalPort $WebPort -ErrorAction SilentlyContinue
    if (-not $listeners) { break }
    Start-Sleep -Milliseconds 500
}
npm run dev -- --port $WebPort --host 127.0.0.1 --strictPort

