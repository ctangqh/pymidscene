# WinAppDriver MCP Server x64 打包脚本
# 需在 x64 位 Python 环境下运行

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  WinAppDriver MCP Server x64 打包" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 架构
$pythonArch = (python -c "import sys; print(sys.maxsize > 2**32)")
if ($pythonArch -ne "True") {
    Write-Host "[!] 错误: 当前 Python 不是 x64 版本" -ForegroundColor Red
    Write-Host "[!] 请使用 x64 Python 运行此脚本" -ForegroundColor Red
    exit 1
}
Write-Host "[√] Python 架构: x64" -ForegroundColor Green

# 切换到脚本所在目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Join-Path $scriptDir ".."
Set-Location $sourceDir

# 检查是否安装了 PyInstaller
if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host "[i] 安装 PyInstaller..." -ForegroundColor Yellow
    pip install pyinstaller
}

# 创建输出目录
$binDir = Join-Path $scriptDir "..\..\..\bin"
if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir | Out-Null
}

Write-Host "[i] 开始打包..." -ForegroundColor Yellow
Write-Host ""

# 执行打包
pyinstaller --onefile `
    --name winapp-mcp-x64 `
    --clean `
    --noconsole `
    --add-data ".env.sample;." `
    --hidden-import mcp `
    --hidden-import httpx `
    --hidden-import loguru `
    --hidden-import pydantic_settings `
    server.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[√] 打包成功!" -ForegroundColor Green

    # 复制到 bin 目录
    Copy-Item "dist\winapp-mcp-x64.exe" -Destination $binDir -Force
    Write-Host "[√] 已复制到 bin 目录" -ForegroundColor Green

    # 复制配置文件和脚本
    Copy-Item ".env.sample" -Destination $binDir -Force
    Copy-Item "scripts\start.bat" -Destination $binDir -Force

    Write-Host ""
    Write-Host "输出文件:" -ForegroundColor Cyan
    Get-ChildItem "$binDir\winapp-mcp-x64.exe" | ForEach-Object {
        Write-Host "  $($_.Name)  $([math]::Round($_.Length / 1MB, 2)) MB" -ForegroundColor White
    }
} else {
    Write-Host ""
    Write-Host "[!] 打包失败!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "完成!" -ForegroundColor Green
