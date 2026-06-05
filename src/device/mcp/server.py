#!/usr/bin/env python3
"""
pymidscene MCP服务端
将pymidscene的AI自动化能力暴露为标准MCP工具，支持Claude Desktop、LangChain、AutoGPT等所有MCP兼容框架直接调用
"""
import asyncio
import os
import sys
from pathlib import Path
# 自动添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent
from typing import Dict, Any, List
import json
from common.logger import logger
from common.config import settings
from sdk.pymidscene import create_client

# 初始化MCP服务端
server = Server("pymidscene-server")

# 全局客户端实例，复用连接提升性能
_client = None

def get_client():
    global _client
    if not _client:
        _client = create_client()
    return _client

@server.list_tools()
async def list_tools() -> List[Tool]:
    """返回pymidscene支持的所有MCP工具列表，符合标准JSON Schema规范"""
    return [
        Tool(
            name="ai_goto",
            description="打开指定的网页URL",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要打开的网页完整URL，例如https://www.baidu.com"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="ai_click",
            description="点击页面上的元素，不需要写CSS/XPath，直接用自然语言描述元素即可",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_description": {
                        "type": "string",
                        "description": "要点击的元素的自然语言描述，例如'蓝色的搜索按钮'、'页面顶部的登录链接'"
                    }
                },
                "required": ["element_description"]
            }
        ),
        Tool(
            name="ai_input",
            description="向页面元素输入文本，不需要写CSS/XPath，直接用自然语言描述元素即可",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要输入的文本内容"
                    },
                    "element_description": {
                        "type": "string",
                        "description": "要输入的元素的自然语言描述，例如'用户名输入框'、'搜索框'"
                    },
                    "clear_before": {
                        "type": "boolean",
                        "description": "输入前是否清空原有内容，默认为true",
                        "default": True
                    }
                },
                "required": ["text", "element_description"]
            }
        ),
        Tool(
            name="ai_extract",
            description="从页面中提取指定的信息，自动返回结构化JSON结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "提取要求的自然语言描述，例如'提取所有搜索结果的标题和链接，返回[{title: str, url: str}]格式'、'提取商品的价格和库存'"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="ai_assert",
            description="断言页面状态是否符合要求，不符合会返回错误",
            inputSchema={
                "type": "object",
                "properties": {
                    "assertion": {
                        "type": "string",
                        "description": "断言要求的自然语言描述，例如'页面显示登录成功提示'、'搜索结果数量大于10条'"
                    },
                    "error_message": {
                        "type": "string",
                        "description": "断言失败时返回的错误信息，可选",
                        "default": "断言失败"
                    }
                },
                "required": ["assertion"]
            }
        ),
        Tool(
            name="ai_screenshot",
            description="对当前页面截图，返回截图内容，可选择是否完整截图",
            inputSchema={
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "是否截取完整页面，默认为true",
                        "default": True
                    },
                    "save_path": {
                        "type": "string",
                        "description": "可选，截图保存到本地的路径",
                        "default": None
                    }
                }
            }
        ),
        Tool(
            name="ai_scroll",
            description="滚动页面，支持上下左右方向滚动",
            inputSchema={
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "滚动方向：down/up/left/right，默认为down",
                        "default": "down"
                    },
                    "distance": {
                        "type": "integer",
                        "description": "滚动距离，像素单位，默认滚动80%视口高度"
                    }
                }
            }
        ),
        Tool(
            name="ai_wait_for",
            description="等待页面满足指定条件，例如等待某个元素出现、等待页面加载完成",
            inputSchema={
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "等待条件的自然语言描述，例如'等待搜索结果加载完成'、'等待登录按钮出现'"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间，毫秒单位，默认30000毫秒",
                        "default": 30000
                    }
                },
                "required": ["condition"]
            }
        ),
        Tool(
            name="ai_close",
            description="关闭浏览器，结束当前会话"
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent | ImageContent]:
    """处理工具调用请求"""
    client = get_client()
    try:
        logger.info(f"收到MCP工具调用：{name}，参数：{json.dumps(arguments, ensure_ascii=False)}")
        result_content = []

        if name == "ai_goto":
            url = arguments["url"]
            client.goto(url)
            result_content.append(TextContent(type="text", text=f"✅ 成功打开页面：{url}，当前页面标题：{client.device.evaluate_script('document.title')}"))

        elif name == "ai_click":
            desc = arguments["element_description"]
            client.ai_click(desc)
            result_content.append(TextContent(type="text", text=f"✅ 成功点击元素：{desc}"))

        elif name == "ai_input":
            text = arguments["text"]
            desc = arguments["element_description"]
            clear_before = arguments.get("clear_before", True)
            client.ai_input(text, locate=desc, clear_before=clear_before)
            result_content.append(TextContent(type="text", text=f"✅ 成功向元素【{desc}】输入文本：{text[:50]}{'...' if len(text) > 50 else ''}"))

        elif name == "ai_extract":
            query = arguments["query"]
            result = client.ai_extract(query)
            result_content.append(TextContent(type="text", text=f"✅ 提取成功，结果：\n{json.dumps(result, ensure_ascii=False, indent=2)}"))

        elif name == "ai_assert":
            assertion = arguments["assertion"]
            error_msg = arguments.get("error_message", "断言失败")
            client.ai_assert(assertion, error_msg)
            result_content.append(TextContent(type="text", text=f"✅ 断言成功：{assertion}"))

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
                result_content.append(TextContent(type="text", text=f"✅ 截图已保存到：{save_path}"))

        elif name == "ai_scroll":
            direction = arguments.get("direction", "down")
            distance = arguments.get("distance")
            client.ai_scroll(direction=direction, distance=distance)
            result_content.append(TextContent(type="text", text=f"✅ 页面已向{direction}滚动{distance or '默认距离'}像素"))

        elif name == "ai_wait_for":
            condition = arguments["condition"]
            timeout = arguments.get("timeout", 30000)
            client.ai_wait_for(condition, timeout=timeout)
            result_content.append(TextContent(type="text", text=f"✅ 等待条件满足：{condition}"))

        elif name == "ai_close":
            global _client
            if _client:
                _client.device.close()
                _client = None
            result_content.append(TextContent(type="text", text="✅ 浏览器已关闭，会话结束"))

        else:
            raise ValueError(f"不支持的工具：{name}")

        return result_content

    except Exception as e:
        error_msg = f"❌ 工具调用失败：{str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

async def main():
    """启动MCP服务端，支持两种运行模式：
    1. STDIO模式（默认）：用于Claude Desktop等本地MCP客户端对接
    2. HTTP模式：用于远程Agent/服务调用
    """
    import argparse
    parser = argparse.ArgumentParser(description="pymidscene MCP服务端")
    parser.add_argument("--mode", choices=["stdio", "http"], default="stdio", help="运行模式")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP模式监听地址")
    parser.add_argument("--port", type=int, default=8765, help="HTTP模式监听端口")
    args = parser.parse_args()

    if args.mode == "stdio":
        logger.info("启动pymidscene MCP服务端（STDIO模式）")
        async with server.run_stdio():
            await asyncio.Future()  # 永久运行
    else:
        from mcp.server.http import HTTPTransport
        logger.info(f"启动pymidscene MCP服务端（HTTP模式）：http://{args.host}:{args.port}")
        transport = HTTPTransport(host=args.host, port=args.port)
        async with server.run(transport):
            await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
