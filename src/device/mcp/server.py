#!/usr/bin/env python3
"""
pymidscene MCP server
Expose pymidscene AI automation capabilities as standard MCP tools for direct use by MCP-compatible frameworks.
"""
import asyncio
import os
import sys
from pathlib import Path
# Automatically add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent
from typing import Dict, Any, List
import json
from common.logger import logger
from common.config import settings
from sdk.pymidscene import create_client

# Initialize MCP server
server = Server("pymidscene-server")

# Reuse a global client instance to avoid reconnect overhead
_client = None

def get_client():
    global _client
    if not _client:
        _client = create_client()
    return _client

@server.list_tools()
async def list_tools() -> List[Tool]:
    """Return the MCP tools supported by pymidscene in standard JSON Schema format."""
    return [
        Tool(
            name="ai_goto",
            description="Open the specified web page URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the page to open, for example https://www.baidu.com"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="ai_click",
            description="Click an element on the page using a natural-language description instead of CSS or XPath.",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_description": {
                        "type": "string",
                        "description": "Natural-language description of the element to click, for example 'the blue search button' or 'the login link at the top of the page'"
                    }
                },
                "required": ["element_description"]
            }
        ),
        Tool(
            name="ai_input",
            description="Type text into a page element using a natural-language description instead of CSS or XPath.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text content to input"
                    },
                    "element_description": {
                        "type": "string",
                        "description": "Natural-language description of the target element, for example 'the username input field' or 'the search box'"
                    },
                    "clear_before": {
                        "type": "boolean",
                        "description": "Whether to clear the existing content before typing. Defaults to true.",
                        "default": True
                    }
                },
                "required": ["text", "element_description"]
            }
        ),
        Tool(
            name="ai_extract",
            description="Extract the requested information from the page and return structured JSON.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language extraction request, for example 'extract the titles and links of all search results and return [{title: str, url: str}]' or 'extract product price and stock'"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="ai_assert",
            description="Assert that the page state matches the requirement and return an error if it does not.",
            inputSchema={
                "type": "object",
                "properties": {
                    "assertion": {
                        "type": "string",
                        "description": "Natural-language assertion, for example 'the page shows a login success message' or 'there are more than 10 search results'"
                    },
                    "error_message": {
                        "type": "string",
                        "description": "Optional error message to return when the assertion fails",
                        "default": "Assertion failed"
                    }
                },
                "required": ["assertion"]
            }
        ),
        Tool(
            name="ai_screenshot",
            description="Capture a screenshot of the current page and optionally save it locally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "Whether to capture the full page. Defaults to true.",
                        "default": True
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional local path where the screenshot will be saved",
                        "default": None
                    }
                }
            }
        ),
        Tool(
            name="ai_scroll",
            description="Scroll the page in the specified direction.",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "Scroll direction: down, up, left, or right. Defaults to down.",
                        "default": "down"
                    },
                    "distance": {
                        "type": "integer",
                        "description": "Scroll distance in pixels. By default, scrolls about 80% of the viewport height."
                    }
                }
            }
        ),
        Tool(
            name="ai_wait_for",
            description="Wait until the page satisfies the specified condition, such as an element appearing or loading finishing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "Natural-language wait condition, for example 'wait until search results finish loading' or 'wait for the login button to appear'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds. Defaults to 30000.",
                        "default": 30000
                    }
                },
                "required": ["condition"]
            }
        ),
        Tool(
            name="ai_close",
            description="Close the browser and end the current session.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent | ImageContent]:
    """Handle MCP tool invocation requests."""
    client = get_client()
    try:
        logger.info(f"MCP tool call received: {name}, arguments: {json.dumps(arguments, ensure_ascii=False)}")
        result_content = []

        if name == "ai_goto":
            url = arguments["url"]
            client.goto(url)
            result_content.append(TextContent(type="text", text=f"Opened page successfully: {url}. Current page title: {client.device.evaluate_script('document.title')}"))

        elif name == "ai_click":
            desc = arguments["element_description"]
            client.ai_click(desc)
            result_content.append(TextContent(type="text", text=f"Clicked element successfully: {desc}"))

        elif name == "ai_input":
            text = arguments["text"]
            desc = arguments["element_description"]
            clear_before = arguments.get("clear_before", True)
            client.ai_input(text, locate=desc, clear_before=clear_before)
            result_content.append(TextContent(type="text", text=f"Entered text into element [{desc}]: {text[:50]}{'...' if len(text) > 50 else ''}"))

        elif name == "ai_extract":
            query = arguments["query"]
            result = client.ai_extract(query)
            result_content.append(TextContent(type="text", text=f"Extraction succeeded. Result:\n{json.dumps(result, ensure_ascii=False, indent=2)}"))

        elif name == "ai_assert":
            assertion = arguments["assertion"]
            error_msg = arguments.get("error_message", "Assertion failed")
            client.ai_assert(assertion, error_msg)
            result_content.append(TextContent(type="text", text=f"Assertion passed: {assertion}"))

        elif name == "ai_screenshot":
            full_page = arguments.get("full_page", True)
            save_path = arguments.get("save_path")
            if save_path:
                save_path = Path(save_path)
            img_bytes = client.device.screenshot(save_path=save_path, full_page=full_page)
            import base64
            base64_img = base64.b64encode(img_bytes).decode("utf-8")
            result_content.append(ImageContent(type="image", data=base64_img, mime_type="image/png"))
            if save_path:
                result_content.append(TextContent(type="text", text=f"Screenshot saved to: {save_path}"))

        elif name == "ai_scroll":
            direction = arguments.get("direction", "down")
            distance = arguments.get("distance")
            client.ai_scroll(direction=direction, distance=distance)
            result_content.append(TextContent(type="text", text=f"Scrolled page {direction} by {distance or 'the default distance'} pixels"))

        elif name == "ai_wait_for":
            condition = arguments["condition"]
            timeout = arguments.get("timeout", 30000)
            client.ai_wait_for(condition, timeout=timeout)
            result_content.append(TextContent(type="text", text=f"Wait condition satisfied: {condition}"))

        elif name == "ai_close":
            global _client
            if _client:
                _client.device.close()
                _client = None
            result_content.append(TextContent(type="text", text="Browser closed. Session ended."))

        else:
            raise ValueError(f"Unsupported tool: {name}")

        return result_content

    except Exception as e:
        error_msg = f"Tool call failed: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

async def main():
    """Start the MCP server.
    1. STDIO mode (default): for local MCP clients such as Claude Desktop
    2. HTTP mode: for remote agents or services
    """
    import argparse
    parser = argparse.ArgumentParser(description="pymidscene MCP server")
    parser.add_argument("--mode", choices=["stdio", "http"], default="stdio", help="Run mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP mode")
    parser.add_argument("--port", type=int, default=8765, help="Port for HTTP mode")
    args = parser.parse_args()

    if args.mode == "stdio":
        logger.info("Starting pymidscene MCP server in STDIO mode")
        async with server.run_stdio():
            await asyncio.Future()  # Run forever
    else:
        from mcp.server.http import HTTPTransport
        logger.info(f"Starting pymidscene MCP server in HTTP mode: http://{args.host}:{args.port}")
        transport = HTTPTransport(host=args.host, port=args.port)
        async with server.run(transport):
            await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
