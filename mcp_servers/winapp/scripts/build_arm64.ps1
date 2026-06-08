# WinAppDriver MCP Server ARM64 build script
# Requires ARM64 Windows environment

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WinAppDriver MCP Server ARM64 Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check processor architecture
$osArch = $env:PROCESSOR_ARCHITECTURE
if ($osArch -ne "ARM64") {
    Write-Host "[WARN] Current arch is not ARM64" -ForegroundColor Yellow
    Write-Host "[WARN] Current arch: $osArch" -ForegroundColor Yellow
}

# Switch to script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Join-Path $scriptDir ".."
Set-Location $sourceDir

# Check PyInstaller
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "[INFO] Installing PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

# Create output directory
$distDir = Join-Path $sourceDir "dist"
if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

Write-Host "[INFO] Building..." -ForegroundColor Yellow
Write-Host ""

# Build
pyinstaller --onefile `
    --name winapp-mcp-arm64 `
    --clean `
    --noconsole `
    --add-data ".env.sample;." `
    --hidden-import mcp `
    --hidden-import httpx `
    --hidden-import loguru `
    --hidden-import pydantic_settings `
    server.py

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Build failed!" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "[OK] Build success!" -ForegroundColor Green

# Copy output to dist
Copy-Item "dist\winapp-mcp-arm64.exe" -Destination $distDir -Force
Write-Host "[OK] Build output: dist\winapp-mcp-arm64.exe" -ForegroundColor Green

# Copy config file
Copy-Item ".env.sample" -Destination $distDir -Force
Write-Host "[OK] Config output: dist\.env.sample" -ForegroundColor Green

Write-Host ""
Write-Host "[DONE] Build finished." -ForegroundColor Green
