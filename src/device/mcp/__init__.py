"""MCP（Model Context Protocol）适配模块
支持两种模式：
1. Client模式：调用第三方标准Playwright MCP服务，使用远程/云浏览器运行自动化
2. Server模式：将pymidscene的AI自动化能力暴露为标准MCP工具，供Claude/Agent调用
"""
from .client import McpPlaywrightDevice
from .schema import MCP_TOOL_NAMES, STANDARD_PLAYWRIGHT_MCP_SCHEMA

__all__ = [
    "McpPlaywrightDevice",
    "MCP_TOOL_NAMES",
    "STANDARD_PLAYWRIGHT_MCP_SCHEMA"
]
