#!/usr/bin/env python3
from device.mcp.client import McpPlaywrightDevice

if __name__ == "__main__":
    # 初始化MCP Playwright设备
    device = McpPlaywrightDevice(
        mcp_server_url="http://172.10.0.25:8000/mcp",
        viewport_width=1280,
        viewport_height=720,
        headless=True
    )
    
    try:
        # 启动设备，连接MCP服务
        device.launch()
        print("✅ MCP服务连接成功")
        
        # 打开百度页面
        device.goto("https://www.baidu.com")
        print(f"✅ 成功打开百度页面，当前URL: {device.current_url}")
        
        # 获取页面标题
        title = device.evaluate_script("document.title")
        print(f"✅ 页面标题: {title}")
        
        # 截图保存
        screenshot_bytes = device.screenshot(save_path="./baidu_test.png")
        print(f"✅ 截图已保存，大小: {len(screenshot_bytes)} bytes")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
    finally:
        # 关闭设备
        device.close()
        print("✅ 测试完成，设备已关闭")