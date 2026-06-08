@echo off
chcp 65001 >nul
title WinAppDriver MCP Server

:: ==============================================
:: WinAppDriver MCP 服务器启动脚本
:: ==============================================

echo.
echo ==============================================
echo   WinAppDriver MCP Server 启动中...
echo ==============================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [√] 管理员权限: 已获取
) else (
    echo [!] 警告: 未获取管理员权限
    echo [!] WinAppDriver 可能无法正常启动
    echo [!] 建议: 右键 - 以管理员身份运行此脚本
    echo.
    pause
)

:: 自动检测架构并选择对应 exe
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set "EXE_NAME=winapp-mcp-x64.exe"
    echo [√] 架构检测: x64 (AMD64)
) else if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set "EXE_NAME=winapp-mcp-arm64.exe"
    echo [√] 架构检测: ARM64
) else if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    set "EXE_NAME=winapp-mcp-x86.exe"
    echo [√] 架构检测: x86
) else (
    echo [!] 未知架构: %PROCESSOR_ARCHITECTURE%
    echo [!] 默认使用 x64 版本
    set "EXE_NAME=winapp-mcp-x64.exe"
)

:: 检查 exe 是否存在
if not exist "%~dp0%EXE_NAME%" (
    echo [!] 错误: 未找到 %EXE_NAME%
    echo [!] 请确保 exe 文件与脚本在同一目录
    echo.
    pause
    exit /b 1
)

:: 检查配置文件
if not exist "%~dp0.env" (
    if exist "%~dp0.env.sample" (
        echo [i] 未找到 .env，正在从 .env.sample 复制...
        copy "%~dp0.env.sample" "%~dp0.env" >nul
        echo [√] 已创建默认配置文件 .env
    ) else (
        echo [!] 警告: 未找到 .env 和 .env.sample
        echo [!] 将使用默认配置运行
    )
) else (
    echo [√] 配置文件: 已加载
)

echo.
echo [i] 正在启动 %EXE_NAME% ...
echo [i] 按 Ctrl+C 停止服务
echo.
echo ==============================================
echo.

:: 启动 MCP 服务器
cd /d "%~dp0"
"%EXE_NAME%"

if %errorLevel% neq 0 (
    echo.
    echo [!] 程序异常退出，错误代码: %errorLevel%
    echo.
    pause
)
