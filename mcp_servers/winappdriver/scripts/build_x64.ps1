# WinAppDriver MCP Server x64 build script (Go)
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WinAppDriver MCP Server x64 Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Split-Path -Parent $scriptDir  # Go up from /scripts to project root
Set-Location $sourceDir

$goExe = "C:\Program Data\Go\bin\go.exe"
$goVersion = & $goExe version 2>$null
if (-not $goVersion) {
    Write-Host "[ERROR] Go is not installed or not in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] $goVersion" -ForegroundColor Green

# Create output directory
$distDir = Join-Path $sourceDir "dist"
if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

# Clean previous build
Remove-Item -Path (Join-Path $sourceDir "winappdriver.exe") -Force -ErrorAction SilentlyContinue
Remove-Item -Path (Join-Path $distDir "winappdriver.exe") -Force -ErrorAction SilentlyContinue

Write-Host "[INFO] Building..." -ForegroundColor Yellow
& $goExe build -ldflags="-s -w" -o "winappdriver.exe" .
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Build failed with exit code $exitCode" -ForegroundColor Red
    exit $exitCode
}

Write-Host "[OK] Build success!" -ForegroundColor Green
Copy-Item "winappdriver.exe" -Destination $distDir -Force
Write-Host "[OK] Build output: dist\winappdriver.exe" -ForegroundColor Green

# Copy config
Copy-Item ".env.example" -Destination $distDir -Force
Write-Host "[OK] Config output: dist\.env.example" -ForegroundColor Green

Write-Host ""
Write-Host "[DONE] Build finished." -ForegroundColor Green
