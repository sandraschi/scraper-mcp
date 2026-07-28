$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$RepoName = Split-Path -Leaf $Root
$Triple = "x86_64-pc-windows-msvc"
$ResourceDir = "$PSScriptRoot\resources"
$DevDir = "$PSScriptRoot\binaries"
New-Item -ItemType Directory -Force -Path $ResourceDir, $DevDir | Out-Null

Write-Host "=== scraper-mcp Tauri Release Build ===" -ForegroundColor Cyan

# Step 0: Verify API_BASE matches backend port
$apiFile = Join-Path $Root "webapp\src\lib\api.ts"
$altFiles = @("webapp\src\api\client.ts", "web_sota\src\lib\api.ts")
foreach ($f in @($apiFile) + $altFiles) {
    if (Test-Path $f) {
        $apiContent = Get-Content $f -Raw
        if ($apiContent -match "127.0.0.1:(\d+)") {
            $apiPort = [int]$Matches[1]
            if ($apiPort -ne 10998) {
                throw "API_BASE in $f points to port $apiPort but backend serves on 10998. Fix before building."
            }
            Write-Host "  API_BASE port: $apiPort (matches backend) OK" -ForegroundColor Green
        }
        break
    }
}

# Step 1: Frontend build
$frontendDirs = @("web_sota", "webapp\frontend", "webapp")
foreach ($dir in $frontendDirs) {
    $frontend = Join-Path $Root $dir
    if (Test-Path "$frontend\package.json") {
        Write-Host "-> [1/4] Building frontend ($dir)..." -ForegroundColor Yellow
        Push-Location $frontend
        npm install --silent 2>$null
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
        Pop-Location
        break
    }
}

# Step 2: PyInstaller backend
Write-Host "-> [2/4] PyInstaller backend..." -ForegroundColor Yellow
$specFile = "$Root\scraper-mcp-backend.spec"
if (Test-Path $specFile) {
    Push-Location $Root
    $entryFile = "$Root\run_server.py"
    if (-not (Test-Path $entryFile)) {
        throw "run_server.py not found at $entryFile"
    }
    $pyiExe = "$Root\.venv\Scripts\pyinstaller.exe"
    if (-not (Test-Path $pyiExe)) {
        uv add --dev pyinstaller
    }
    Remove-Item "$Root\dist\scraper-mcp-backend.exe" -Force -ErrorAction SilentlyContinue
    & $pyiExe "$specFile" --clean --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
} else {
    throw "Backend spec file not found at $specFile"
}

# Step 3: Embed in Tauri resources
Write-Host "-> [3/4] Embedding backend..." -ForegroundColor Yellow
$src = "$Root\dist\scraper-mcp-backend.exe"
if (-not (Test-Path $src)) { throw "Backend exe not found at $src" }
$sizeMB = (Get-Item $src).Length / 1MB
if ($sizeMB -lt 5) { throw "Backend exe is only $([math]::Round($sizeMB, 1)) MB" }
Copy-Item $src "$ResourceDir\scraper-mcp-backend.exe" -Force
Copy-Item $src "$DevDir\scraper-mcp-backend-$Triple.exe" -Force
Write-Host "  Backend exe: $sizeMB MB" -ForegroundColor Green

# Bundle .env.example
$envExample = "$Root\.env.example"
if (Test-Path $envExample) {
    Copy-Item $envExample "$ResourceDir\.env.example" -Force
}

# Step 4: NSIS installer
Write-Host "-> [4/4] Tauri NSIS bundle..." -ForegroundColor Yellow
Push-Location $PSScriptRoot
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
npx @tauri-apps/cli build --bundles nsis
if ($LASTEXITCODE -ne 0) { throw "Tauri build failed" }
Pop-Location

Write-Host "=== Build complete ===" -ForegroundColor Green
