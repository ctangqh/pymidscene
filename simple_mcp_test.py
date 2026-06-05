#!/usr/bin/env python3
import asyncio
from mcp.client.streamable_http import HTTPParams, connect as http_connect

async def test_mcp_baidu():
    try:
        print("🔗 连接MCP服务...")
        http_params = HTTPParams(url="http://172.10.0.25:8000/mcp", timeout=30)
        async with http_connect(http_params) as session:
            print("✅ MCP服务连接成功，初始化完成")
            
            # 调用创建浏览器上下文
            print("🌐 创建浏览器上下文...")
            ctx_resp = await session.call_tool(
                "playwright_create_context",
                parameters={
                    "viewport": {"width": 1280, "height": 720},
                    "headless": True
                }
            )
            context_id = ctx_resp.content[0].text.strip()
            print(f"✅ 上下文创建成功：{context_id}")
            
            # 创建页面
            print("📄 创建新页面...")
            page_resp = await session.call_tool(
                "playwright_new_page",
                parameters={"context_id": context_id}
            )
            page_id = page_resp.content[0].text.strip()
            print(f"✅ 页面创建成功：{page_id}")
            
            # 打开百度
            print("🔍 打开百度页面...")
            await session.call_tool(
                "playwright_goto",
                parameters={"page_id": page_id, "url": "https://www.baidu.com", "timeout": 30000}
            )
            print("✅ 百度页面打开成功")
            
            # 获取标题
            print("📝 获取页面标题...")
            title_resp = await session.call_tool(
                "playwright_evaluate",
                parameters={"page_id": page_id, "script": "document.title", "args": []}
            )
            title = title_resp.content[0].text.strip()
            print(f"✅ 页面标题：{title}")
            
            # 截图
            print("📸 页面截图...")
            screenshot_resp = await session.call_tool(
                "playwright_screenshot",
                parameters={"page_id": page_id, "full_page": True, "encoding": "base64"}
            )
            print(f"✅ 截图成功，大小：{len(screenshot_resp.content[0].text.strip())} 字节")
            
            # 清理资源
            print("🧹 清理资源...")
            await session.call_tool("playwright_close_page", parameters={"page_id": page_id})
            await session.call_tool("playwright_close_context", parameters={"context_id": context_id})
            print("✅ 资源清理完成")
            
            print("\n🎉 全部测试通过！Playwright MCP服务运行正常")
            
    except Exception as e:
        print(f"❌ 测试失败：{str(e)}")

if __name__ == "__main__":
    asyncio.run(test_mcp_baidu())