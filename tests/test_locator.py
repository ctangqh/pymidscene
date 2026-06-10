#!/usr/bin/env python3
"""定位引擎测试脚本"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, MagicMock
from unittest.mock import AsyncMock
from pymidscene.core.locator import ElementLocator, LocateResult
from pymidscene.device.browser.playwright_impl import PlaywrightDevice


def test_simplify_dom():
    """测试DOM简化功能"""
    mock_browser = Mock(spec=PlaywrightDevice)
    mock_llm = Mock()
    
    locator = ElementLocator(mock_browser, mock_llm)
    
    # 模拟DOM结构
    test_dom = {
        "tagName": "div",
        "attributes": {"id": "container", "class": "main"},
        "text": "",
        "children": [
            {
                "tagName": "input",
                "attributes": {"id": "kw", "name": "wd", "placeholder": "请输入搜索关键词", "class": "s_ipt"},
                "text": "",
                "children": []
            },
            {
                "tagName": "input",
                "attributes": {"id": "su", "type": "submit", "value": "百度一下", "class": "s_btn"},
                "text": "",
                "children": []
            },
            {
                "tagName": "script",
                "attributes": {"src": "xxx.js"},
                "text": "console.log('test')",
                "children": []
            }
        ]
    }
    
    simplified = locator._simplify_dom(test_dom)
    print("简化后的DOM:")
    import json
    print(json.dumps(simplified, ensure_ascii=False, indent=2))
    
    # 验证script标签被过滤
    assert len(simplified.get("children", [])) == 2
    # 验证input属性保留
    assert simplified["children"][0]["attrs"]["id"] == "kw"
    assert simplified["children"][0]["attrs"]["placeholder"] == "请输入搜索关键词"
    print("✅ DOM简化功能测试通过")


def test_locate_flow():
    """测试定位流程"""
    mock_browser = Mock(spec=PlaywrightDevice)
    mock_llm = Mock()
    
    # 模拟返回定位结果
    mock_llm.structured_chat.return_value = LocateResult(
        selector="#su",
        confidence=0.95,
        reason="按钮的value是'百度一下'，匹配搜索按钮描述",
    )
    
    # 模拟DOM返回
    mock_browser.get_dom_tree.return_value = {
        "tagName": "div",
        "children": [
            {
                "tagName": "input",
                "attributes": {"id": "su", "value": "百度一下", "type": "submit"},
                "children": []
            }
        ]
    }
    
    # 模拟元素坐标获取
    mock_browser.wait_for_selector.return_value = True
    mock_browser.evaluate_script.return_value = {
        "x": 800,
        "y": 200,
        "width": 100,
        "height": 40
    }
    
    locator = ElementLocator(mock_browser, mock_llm)
    
    # 测试定位
    x, y = locator.locate("搜索按钮")
    print(f"✅ 定位成功，坐标: ({x}, {y})")
    assert x == 800 + 100 / 2 == 850
    assert y == 200 + 40 / 2 == 220
    
    # 验证LLM被正确调用
    mock_llm.structured_chat.assert_called_once()
    print("✅ 定位流程测试通过")


def test_extract_info():
    """测试信息提取功能"""
    mock_browser = Mock(spec=PlaywrightDevice)
    mock_llm = Mock()
    
    # 模拟返回提取结果
    mock_llm.structured_chat.return_value = Mock(
        data=[{"title": "PyMidscene 介绍", "url": "https://xxx.com"}],
        confidence=0.9,
        reason="从搜索结果中提取到第一条标题和链接"
    )
    
    mock_browser.get_page_content.return_value = """
    <div class="result">
        <h3><a href="https://xxx.com">PyMidscene 介绍</a></h3>
        <p>Python AI 浏览器自动化框架</p>
    </div>
    <div class="result">
        <h3><a href="https://yyy.com">PyMidscene 教程</a></h3>
        <p>快速入门教程</p>
    </div>
    """
    
    locator = ElementLocator(mock_browser, mock_llm)
    mock_browser.size.return_value = (1920, 1080)
    mock_browser.screenshot_base64.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X6K6kAAAAASUVORK5CYII="
    locator.service.extract = AsyncMock(return_value={
        "data": [{"title": "PyMidscene 介绍", "url": "https://xxx.com"}],
        "thought": "从搜索结果中提取到第一条标题和链接",
        "usage": None,
    })
    
    result = locator.extract_info("提取第一条搜索结果的标题和链接")
    print(f"✅ 提取成功，结果: {result}")
    assert result["data"][0]["title"] == "PyMidscene 介绍"
    assert result["confidence"] == 1.0
    print("✅ 信息提取功能测试通过")


if __name__ == "__main__":
    print("🧪 开始测试定位引擎...")
    test_simplify_dom()
    test_locate_flow()
    test_extract_info()
    print("\n🎉 所有测试通过！定位引擎运行正常。")
