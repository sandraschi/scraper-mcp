param(
    [switch]$Headless,
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoBrowser,
    [switch]$ReuseIfRunning)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FleetStartPath = Join-Path $ProjectRoot "scripts\FleetStartMode.ps1"
if (-not (Test-Path -LiteralPath $FleetStartPath)) {
    Write-Host "ERROR: Missing vendored launcher helper: $FleetStartPath" -ForegroundColor Red
    exit 1
}
. $FleetStartPath


$WebappStart = Join-Path $PSScriptRoot "webapp\start.ps1"
if (-not (Test-Path $WebappStart)) {
    Write-Host "Missing webapp/start.ps1" -ForegroundColor Red
    exit 1
}

& $WebappStart @PSBoundParameters
exit $LASTEXITCODE


