<#
.SYNOPSIS
    Register a daily Scheduled Task to refresh all grades at 6:00 AM.
.DESCRIPTION
    Creates a task named "scraper-mcp-refresh" that runs `just refresh`
    in the repo root daily. Skips if the task already exists.
.PARAMETER Force
    Overwrite existing task.
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = "Stop"
$TaskName = "scraper-mcp-refresh"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)

# Resolve uv
$uvExe = Get-Command "uv" -ErrorAction SilentlyContinue
if (-not $uvExe) {
    $uvCandidates = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe",
        "$env:USERPROFILE\.local\bin\uv.exe",
        "C:\Users\Sandra\AppData\Local\Microsoft\WinGet\Links\uv.exe"
    )
    $uvExe = $uvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $uvExe) { throw "uv not found. Install via winget: winget install astral-sh.uv" }

$action = New-ScheduledTaskAction -Execute "$uvExe" -Argument "run python -m scraper_mcp.server --http --port 10998" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "06:00"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    if (-not $Force) {
        Write-Host "Task '$TaskName' already exists. Use -Force to overwrite."
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -User $env:USERNAME
Write-Host "Registered: $TaskName (daily at 6:00 AM)"
