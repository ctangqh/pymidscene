"""MCP（Model Context Protocol）适配模块
支持两种模式：
1. Client模式：调用第三方标准MCP服务，支持 Playwright, WinAppDriver, Android, iOS, Hypium 等
2. Server模式：将pymidscene的AI自动化能力暴露为标准MCP工具，供Claude/Agent调用
"""
from .client import (
    McpPlaywrightDevice,
    McpWinAppDevice,
    McpAndroidDevice,
    McpIosDevice,
    McpHypiumDevice,
    BaseMcpDevice
)
from .schema import (
    MCP_TOOL_NAMES,
    NATIVE_SOURCE_TOOL_NAMES,
    STANDARD_NATIVE_SOURCE_MCP_SCHEMA,
    STANDARD_PLAYWRIGHT_MCP_SCHEMA,
)

__all__ = [
    "McpPlaywrightDevice",
    "McpWinAppDevice",
    "McpAndroidDevice",
    "McpIosDevice",
    "McpHypiumDevice",
    "BaseMcpDevice",
    "MCP_TOOL_NAMES",
    "NATIVE_SOURCE_TOOL_NAMES",
    "STANDARD_PLAYWRIGHT_MCP_SCHEMA",
    "STANDARD_NATIVE_SOURCE_MCP_SCHEMA",
]
