# WinAppDriver MCP Server x86 build script
# Requires x86 (32-bit) Python environment

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WinAppDriver MCP Server x86 Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python architecture
$pythonArch = (python -c "import struct; print(8 * struct.calcsize('P'))")
if ($pythonArch -ne "32") {
    Write-Host "[ERROR] Current Python is not x86 (32-bit)" -ForegroundColor Red
    Write-Host "[ERROR] Current bitness: $pythonArch" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Python arch: x86 (32-bit)" -ForegroundColor Green

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
    --name winapp-mcp-x86 `
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
Copy-Item "dist\winapp-mcp-x86.exe" -Destination $distDir -Force
Write-Host "[OK] Build output: dist\winapp-mcp-x86.exe" -ForegroundColor Green

# Copy config file
Copy-Item ".env.sample" -Destination $distDir -Force
Write-Host "[OK] Config output: dist\.env.sample" -ForegroundColor Green

Write-Host ""
Write-Host "[DONE] Build finished." -ForegroundColor Green
