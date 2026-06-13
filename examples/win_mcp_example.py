#!/usr/bin/env python3
"""Windows 记事本自动化示例"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sdk.pymidscene import create_client
import time


def main():
    print("=" * 60)
    print("PyMidscene Windows 记事本自动化示例")
    print("=" * 60)
    
    # 初始化 SDK
    print("\n[1] 初始化 PyMidscene...")
    ms = create_client(
        device_provider="mcp_winapp",
        llm_provider=None,
        vision_provider=None,
        mcp_name="winapp",
        mcp_server_url=None,
        debug=True,
        device_options=None,
        llm_options=None,
        vision_options=None
    )
    
    # 启动设备并打开记事本
    print("\n[2] 启动设备并打开记事本")
    ms.launch()
    session_result = ms.goto(
        "notepad.exe",
        platform_name="Windows",
        device_name="WindowsPC"
    )
    print(session_result)
    time.sleep(2)
    
    # 截图 1: 记事本启动后
    ms.screenshot("01_notepad_started.png")
    
    # 输入文本
    print("\n[3] 输入文本: Hello PyMidscene!")
    ms.ai_input("文本编辑区域", "Hello PyMidscene!")
    time.sleep(1)
    ms.screenshot("02_text_entered.png")
    
    # 点击文件菜单
    print("\n[4] 点击菜单栏的文件按钮")
    ms.ai_click("菜单栏的文件按钮")
    time.sleep(1)
    ms.screenshot("03_file_menu_clicked.png")
    
    # 点击退出菜单
    print("\n[5] 点击退出菜单")
    ms.ai_click("文件菜单中的退出菜单项")
    time.sleep(1)
    ms.screenshot("04_exit_clicked.png")
    
    # 点击不保存按钮
    print("\n[6] 点击不保存按钮")
    ms.ai_click("保存对话框中的不保存按钮")
    time.sleep(1)
    ms.screenshot("05_not_saved_clicked.png")
    
    # 关闭应用和设备
    print("\n[7] 关闭应用和设备")
    ms.close()
    
    print("\n✅ 所有操作完成！截图已保存到当前 report 的 screenshots 目录。")
    print("=" * 60)


if __name__ == "__main__":
    main()
