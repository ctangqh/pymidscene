#!/usr/bin/env python3
"""Playwright MCP 示例：按 docs/sdk.md 的公开 SDK 方法搜索并提取结果。"""

import json
import sys
import time
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sdk.pymidscene import create_client


# MCP_SERVER_URL = "http://192.168.3.3:8931/sse"
MCP_SERVER_URL = "http://localhost:8931/sse"
SEARCH_KEYWORD = "PyMidscene"


def normalize_result(result):
    """兼容 ai_extract 返回 dict、JSON 字符串或 markdown code fence。"""
    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        text = result.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": result}

    return {"raw": result}


def main():
    print("=" * 60)
    print("PyMidscene Playwright MCP Google 搜索示例")
    print("=" * 60)

    ms = create_client(
        device_provider="mcp_playwright",
        llm_provider=None,
        vision_provider=None,
        debug=True,
        device_options={
            "mcp_server_url": MCP_SERVER_URL,
            "mcp_transport": "sse",
            "mcp_timeout": 120,
            "viewport_width": 1440,
            "viewport_height": 900,
        },
    )

    try:
        print("\n[1] 连接 Playwright MCP Server")
        ms.launch()

        print("\n[2] 打开 Google 首页")
        ms.goto("https://www.bing.com")
        time.sleep(2)
        ms.screenshot("01_google_home.png")

        print(f"\n[3] 搜索关键词: {SEARCH_KEYWORD}")
        ms.ai_input("Google 搜索输入框", SEARCH_KEYWORD)
        ms.keyboard_press("Enter")

        print("\n[4] 等待搜索结果出现")
        ms.ai_wait_for("页面显示 Google 搜索结果列表，且可以看到第一条自然搜索结果")
        time.sleep(2)

        ms.screenshot("02_google_search_results.png")

        print("\n[5] 提取第一条搜索结果")
        first_result = ms.ai_extract(
            "提取 Google 搜索结果中的第一条自然搜索结果，"
            "返回 JSON 对象，包含 title 和 href 两个字段，不要返回其他说明文字"
        )
        normalized_result = normalize_result(first_result)
        print(f"搜索词: {SEARCH_KEYWORD}")
        print(f"第一条结果标题: {normalized_result.get('title', '')}")
        print(f"第一条结果链接: {normalized_result.get('href', '')}")
        print(json.dumps(normalized_result, ensure_ascii=False, indent=2))

        print("\n操作完成，截图已保存到当前 report 的 screenshots 目录。")
    finally:
        print("\n[6] 关闭浏览器连接")
        ms.close()
        print("=" * 60)


if __name__ == "__main__":
    main()
