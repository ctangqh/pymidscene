#!/usr/bin/env python3
"""基础使用示例"""
import os
from pymidscene import create_client

# 配置 API 密钥（也可以放在 .env 文件中）
os.environ["OPENAI_API_KEY"] = "sk-xxx"
os.environ["OPENAI_BASE_URL"] = "https://api.openai.com/v1"  # 可以替换为代理地址


def basic_usage():
    """基础使用示例"""
    with create_client(
        browser_options={"headless": False},  # 显示浏览器窗口方便调试
        llm_options={"model": "gpt-4o"}
    ) as client:
        # 跳转到百度
        client.goto("https://www.baidu.com")
        
        # 输入搜索词
        client.input("搜索输入框", "PyMidscene AI 浏览器自动化")
        
        # 点击搜索按钮
        client.click("搜索按钮")
        
        # 截图保存
        client.screenshot("output/baidu_search_result.png")
        
        # 提取搜索结果
        result = client.extract("提取页面所有搜索结果的标题和链接，返回数组格式")
        print("搜索结果：", result)
        
        print("执行完成！")


def yaml_usage():
    """YAML 流程示例"""
    with create_client() as client:
        result = client.run_yaml("examples/search_demo.yaml")
        print("YAML 流程执行结果：", result)


if __name__ == "__main__":
    basic_usage()
