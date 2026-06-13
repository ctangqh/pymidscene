$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Hypium MCP Server Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Split-Path -Parent $scriptDir
Set-Location $sourceDir

$goExe = "C:\Program Files\Go\bin\go.exe"
if (-not (Test-Path $goExe)) {
    $goCmd = Get-Command go -ErrorAction SilentlyContinue
    if ($goCmd) {
        $goExe = $goCmd.Source
    }
}

$goVersion = & $goExe version 2>$null
if (-not $goVersion) {
    Write-Host "[ERROR] Go is not installed or not in PATH" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] $goVersion" -ForegroundColor Green

$distDir = Join-Path $sourceDir "dist"
if (-not (Test-Path $distDir)) {
    New-Item -ItemType Directory -Path $distDir | Out-Null
}

$targets = @(
    @{ GOARCH = "386";   Output = "hypium_x86.exe" },
    @{ GOARCH = "amd64"; Output = "hypium_x86_64.exe" },
    @{ GOARCH = "arm64"; Output = "hypium_arm64.exe" }
)

$legacyOutputs = @(
    (Join-Path $sourceDir "hypium.exe"),
    (Join-Path $distDir "hypium.exe")
)
foreach ($legacy in $legacyOutputs) {
    Remove-Item -Path $legacy -Force -ErrorAction SilentlyContinue
}

foreach ($target in $targets) {
    $outputPath = Join-Path $distDir $target.Output
    Remove-Item -Path $outputPath -Force -ErrorAction SilentlyContinue

    Write-Host "[INFO] Building $($target.GOARCH) -> dist\$($target.Output)" -ForegroundColor Yellow
    $env:GOOS = "windows"
    $env:GOARCH = $target.GOARCH

    & $goExe build -ldflags="-s -w" -o $outputPath .
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Write-Host ""
        Write-Host "[ERROR] Build failed for GOARCH=$($target.GOARCH) with exit code $exitCode" -ForegroundColor Red
        Remove-Item Env:GOOS -ErrorAction SilentlyContinue
        Remove-Item Env:GOARCH -ErrorAction SilentlyContinue
        exit $exitCode
    }

    Write-Host "[OK] Build output: dist\$($target.Output)" -ForegroundColor Green
}

Remove-Item Env:GOOS -ErrorAction SilentlyContinue
Remove-Item Env:GOARCH -ErrorAction SilentlyContinue

Copy-Item "mcp.conf" -Destination (Join-Path $distDir "mcp.conf") -Force
Copy-Item "helper.py" -Destination (Join-Path $distDir "helper.py") -Force
Write-Host "[OK] Runtime assets: dist\mcp.conf, dist\helper.py" -ForegroundColor Green

Write-Host ""
Write-Host "[DONE] Build finished." -ForegroundColor Green
