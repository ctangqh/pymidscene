"""Test: launch Windows Calculator via WinApp MCP server (SSE)"""
import asyncio
import json
import sys

from mcp.client.sse import sse_client
from mcp import ClientSession

MCP_URL = "http://127.0.0.1:55001/sse"


def safe_print(text: str) -> None:
    """Print safely, falling back to ASCII if encoding fails."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


async def main():
    safe_print(f"Connecting MCP server: {MCP_URL}")
    try:
        async with sse_client(MCP_URL, timeout=30, sse_read_timeout=300) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # List available tools
                tools = await session.list_tools()
                safe_print(f"Available tools: {len(tools.tools)}")
                for t in tools.tools:
                    safe_print(f"  - {t.name}")

                # Step 1: Check WinAppDriver status
                safe_print("\nWinAppDriver status:")
                status = await session.call_tool("winapp_get_status", {})
                safe_print(status.content[0].text)

                # Step 2: Launch Calculator
                safe_print("\nLaunch calculator result:")
                result = await session.call_tool("winapp_create_session", {
                    "app": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
                    "platform_name": "Windows",
                    "device_name": "WindowsPC",
                })
                safe_print(result.content[0].text)

    except Exception as e:
        safe_print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
