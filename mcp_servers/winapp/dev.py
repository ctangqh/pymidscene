#!/usr/bin/env python3
"""
WinAppDriver MCP Server 开发调试入口

由于 WinAppDriver 仅支持 Windows，此脚本用于：
1. 语法检查
2. 导入测试
3. MCP 服务器基本功能验证（不实际连接 WinAppDriver）
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试所有模块是否能正确导入"""
    print("=" * 60)
    print("  模块导入测试")
    print("=" * 60)

    try:
        from mcp_servers.winapp import config
        print("  ✅ config.py 导入成功")
    except Exception as e:
        print(f"  ❌ config.py 导入失败: {e}")
        return False

    try:
        from mcp_servers.winapp import client
        print("  ✅ client.py 导入成功")
    except Exception as e:
        print(f"  ❌ client.py 导入失败: {e}")
        return False

    try:
        from mcp_servers.winapp import server
        print("  ✅ server.py 导入成功")
    except Exception as e:
        print(f"  ❌ server.py 导入失败: {e}")
        return False

    print()
    return True


def test_config():
    """测试配置加载"""
    print("=" * 60)
    print("  配置加载测试")
    print("=" * 60)

    from mcp_servers.winapp.config import winapp_settings

    print(f"  WINAPPDRIVER_HOST:    {winapp_settings.WINAPPDRIVER_HOST}")
    print(f"  WINAPPDRIVER_PORT:    {winapp_settings.WINAPPDRIVER_PORT}")
    print(f"  WINAPPDRIVER_AUTO_START: {winapp_settings.WINAPPDRIVER_AUTO_START}")
    print(f"  MCP_TOOL_PREFIX:      {winapp_settings.MCP_TOOL_PREFIX}")
    print(f"  LOG_LEVEL:            INFO")
    print()
    return True


def test_mcp_tools():
    """检查 MCP 工具定义"""
    print("=" * 60)
    print("  MCP 工具列表")
    print("=" * 60)

    from mcp_servers.winapp.server import mcp

    tools = list(mcp._tool_manager._tools.keys())
    print(f"  已定义工具数量: {len(tools)}")
    print()
    for i, tool in enumerate(tools, 1):
        print(f"  {i:2d}. {tool}")
    print()
    return True


def main():
    """主函数"""
    print()
    print("🚀 WinAppDriver MCP Server 开发模式")
    print("   (注意: 实际运行需要 Windows + WinAppDriver)")
    print()

    all_passed = True
    all_passed &= test_imports()
    all_passed &= test_config()
    all_passed &= test_mcp_tools()

    print("=" * 60)
    if all_passed:
        print("  ✅ 所有测试通过！")
        print()
        print("  下一步:")
        print("  1. 在 Windows 上安装 WinAppDriver")
        print("  2. 安装 Python 依赖: pip install -r requirements.txt")
        print("  3. 运行: python -m mcp.winapp.server")
        print("  4. 或使用打包脚本生成 exe")
    else:
        print("  ❌ 部分测试失败，请检查错误信息")
        sys.exit(1)
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
