#!/usr/bin/env python3
"""示例用例：打开浏览器，搜索midscene"""
import sys
import os
# 自动添加src目录到PYTHONPATH，不用手动配置环境变量
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from sdk.pymidscene import create_client

def search_midscene():
    # 1. 创建客户端，自动加载.env里的模型配置
    with create_client() as client:
        # 2. 打开Google搜索主页（如果访问不了Google可以替换为https://www.baidu.com）
        client.goto("https://www.google.com")
        print("✅ 已打开Google搜索主页")

        # 3. AI定位搜索输入框，输入"midscene"
        # 不需要写CSS/XPath，直接自然语言描述要操作的元素即可
        client.ai_input("midscene", locate="搜索输入框")
        print("✅ 已输入搜索关键词midscene")

        # 4. 点击搜索按钮执行搜索
        client.ai_click("搜索按钮")
        print("✅ 已执行搜索，等待结果加载...")

        # 5. 等待搜索结果加载完成
        client.ai_wait_for("搜索结果列表加载完成")
        print("✅ 搜索结果加载完成")

        # 6. 提取前3条搜索结果的标题和链接（可选）
        results = client.ai_extract("提取前3条搜索结果，返回格式：[{title: str, url: str}]")
        print("\n🎉 搜索结果前3条：")
        for i, res in enumerate(results, 1):
            print(f"{i}. {res['title']}: {res['url']}")

        # 7. （可选）截图保存搜索结果
        screenshot_path = "./output/search_result.png"
        client.device.screenshot(save_path=screenshot_path)
        print(f"\n✅ 搜索结果截图已保存到：{screenshot_path}")

if __name__ == "__main__":
    try:
        search_midscene()
        print("\n✅ 示例用例执行成功！")
    except Exception as e:
        print(f"\n❌ 执行失败：{str(e)}")
