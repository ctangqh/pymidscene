#!/usr/bin/env python3
"""MCP模式示例用例：调用远程MCP Playwright服务，搜索midscene
完全兼容原有API，只需要修改device_type即可切换MCP模式，业务逻辑零修改
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sdk.pymidscene import create_client

def mcp_search_midscene():
    # 1. 创建MCP设备客户端，自动加载.env中的MCP_SERVER_URL配置
    with create_client(
        device_type="mcp_playwright",  # 指定使用MCP Playwright设备
        device_options={
            # 也可以在这里手动指定MCP配置，会覆盖.env中的配置
            # "mcp_server_url": "http://192.168.10.66:55002/mcp",
            # "mcp_api_key": "",
            "headless": True
        }
    ) as client:
        print("✅ 已成功连接MCP Playwright服务")

        # 2. 打开百度搜索（国内网络适配，不需要访问Google）
        client.goto("https://www.baidu.com")
        print("✅ 已打开百度搜索主页")

        # 3. 输入搜索关键词"midscene"
        client.ai_input("midscene", locate="搜索输入框")
        print("✅ 已输入搜索关键词midscene")

        # 4. 点击搜索按钮
        client.ai_click("百度一下按钮")
        print("✅ 已执行搜索，等待结果加载...")

        # 5. 等待搜索结果加载完成
        client.ai_wait_for("搜索结果列表加载完成", timeout=30000)
        print("✅ 搜索结果加载完成")

        # 6. 提取前3条搜索结果
        results = client.ai_extract("提取前3条搜索结果，返回格式：[{title: str, url: str}]")
        print("\n🎉 搜索结果前3条：")
        for i, res in enumerate(results, 1):
            print(f"{i}. {res['title']}: {res['url']}")

        # 7. 截图保存搜索结果（截图由MCP服务生成，返回给本地保存）
        screenshot_path = "./output/mcp_search_result.png"
        client.device.screenshot(save_path=screenshot_path)
        print(f"\n✅ 搜索结果截图已保存到：{screenshot_path}")

if __name__ == "__main__":
    try:
        mcp_search_midscene()
        print("\n✅ MCP模式示例用例执行成功！")
    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
        import traceback
        traceback.print_exc()
