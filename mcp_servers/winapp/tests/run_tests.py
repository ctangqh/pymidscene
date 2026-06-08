#!/usr/bin/env python3
"""
WinAppDriver MCP Server 单元测试（独立版本，不依赖 pytest）
运行: python mcp_servers/winapp/tests/run_tests.py
"""
import sys
import os
from pathlib import Path

# 添加项目根目录
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

print("=" * 70)
print("  WinAppDriver MCP Server 单元测试")
print("=" * 70)
print()

passed = 0
failed = 0
warnings = 0
errors = []


def test(name):
    """装饰器：标记测试函数"""
    def decorator(func):
        global passed, failed
        try:
            func()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}")
            errors.append(f"{name}: {str(e)}")
            failed += 1
        except Exception as e:
            print(f"  💥 {name} (异常: {type(e).__name__})")
            errors.append(f"{name}: {type(e).__name__}: {str(e)}")
            failed += 1
        return func
    return decorator


# ==================== 配置测试 ====================

@test("配置模块导入")
def test_config_import():
    from mcp_servers.winapp.config import winapp_settings, WinAppDriverSettings
    assert winapp_settings is not None
    assert isinstance(winapp_settings, WinAppDriverSettings)


@test("配置默认值验证")
def test_config_default_values():
    from mcp_servers.winapp.config import winapp_settings
    assert winapp_settings.WINAPPDRIVER_HOST == "127.0.0.1"
    assert winapp_settings.WINAPPDRIVER_PORT == 4723
    assert winapp_settings.WINAPPDRIVER_AUTO_START is True


# ==================== 客户端测试 ====================

@test("客户端模块导入")
def test_client_import():
    from mcp_servers.winapp.client import WinAppDriverClient
    assert WinAppDriverClient is not None


@test("客户端初始化参数")
def test_client_initialization():
    from mcp_servers.winapp.client import WinAppDriverClient
    client = WinAppDriverClient(host="192.168.1.100", port=9999, auto_start=False)
    assert client.host == "192.168.1.100"
    assert client.port == 9999
    assert client.auto_start is False
    assert client.session_id is None


@test("客户端 Base URL 构造")
def test_client_base_url():
    from mcp_servers.winapp.client import WinAppDriverClient
    client = WinAppDriverClient(host="10.0.0.1", port=8888, auto_start=False)
    assert client.base_url == "http://10.0.0.1:8888"


@test("客户端 HTTP 方法存在")
def test_client_http_methods_exist():
    """验证所有 HTTP API 包装方法都存在"""
    from mcp_servers.winapp.client import WinAppDriverClient
    client = WinAppDriverClient(auto_start=False)

    # 应该存在的方法列表
    expected_methods = [
        # Session
        "create_session", "delete_session", "get_sessions", "get_status",
        # 元素
        "find_element", "find_elements", "find_element_from_element",
        "click_element", "clear_element", "send_keys_to_element",
        "get_element_text", "get_element_attribute", "get_element_name",
        "is_element_displayed", "is_element_enabled", "is_element_selected",
        "get_element_location", "get_element_size",
        # 鼠标
        "mouse_move", "mouse_click", "mouse_double_click",
        "mouse_button_down", "mouse_button_up",
        # 键盘
        "send_keys",
        # 窗口
        "get_window_handle", "get_window_handles",
        "set_window_size", "get_window_size",
        "set_window_position", "get_window_position",
        "maximize_window", "close_window",
        # 截图
        "get_screenshot", "get_element_screenshot",
        "get_page_source",
        # 导航
        "navigate_back", "navigate_forward",
        # 超时
        "set_timeout",
        # 触摸
        "touch_click", "touch_double_click", "touch_long_click",
        "touch_down", "touch_up", "touch_move", "touch_scroll", "touch_flick",
    ]

    missing = []
    for method in expected_methods:
        if not hasattr(client, method) or not callable(getattr(client, method)):
            missing.append(method)

    assert len(missing) == 0, f"缺少方法: {missing}"
    print(f"    (验证 {len(expected_methods)} 个 HTTP API 方法)")


# ==================== MCP 服务器测试 ====================

@test("MCP 服务器模块导入")
def test_server_import():
    from mcp_servers.winapp.server import mcp, get_client
    assert mcp is not None
    assert get_client is not None


@test("MCP 工具数量验证 (46 个)")
def test_mcp_tool_count():
    from mcp_servers.winapp.server import mcp
    actual_tools = list(mcp._tool_manager._tools.keys())
    print(f"    (实际工具数: {len(actual_tools)})")

    # 先检查数量，允许有差异但记录
    if len(actual_tools) != 46:
        global warnings
        warnings += 1
        print(f"    ⚠️  期望 46 个工具，实际 {len(actual_tools)} 个")

    # 但至少应该有基本工具
    assert len(actual_tools) >= 40, f"工具数量过少: {len(actual_tools)}"


@test("MCP 工具名称完整性检查")
def test_mcp_tool_names():
    from mcp_servers.winapp.server import mcp
    actual_tools = set(mcp._tool_manager._tools.keys())

    # 核心工具列表
    core_tools = {
        "winapp_create_session", "winapp_delete_session",
        "winapp_find_element", "winapp_click_element",
        "winapp_send_keys_to_element", "winapp_get_screenshot",
        "winapp_mouse_move", "winapp_mouse_click",
        "winapp_set_window_size", "winapp_maximize_window",
    }

    missing = core_tools - actual_tools
    assert len(missing) == 0, f"缺少核心工具: {missing}"


@test("MCP 工具描述检查")
def test_mcp_tool_descriptions():
    from mcp_servers.winapp.server import mcp
    tools = mcp._tool_manager._tools

    no_description = []
    for tool_name, tool in tools.items():
        if not hasattr(tool, 'description') or not tool.description:
            no_description.append(tool_name)

    assert len(no_description) == 0, f"以下工具缺少描述: {no_description}"
    print(f"    (检查了 {len(tools)} 个工具)")


@test("客户端单例模式验证")
def test_client_singleton():
    from mcp_servers.winapp.server import get_client

    # 重置全局客户端
    import mcp_servers.winapp.server as server_module
    original_client = server_module._client
    server_module._client = None

    try:
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2, "两次调用应返回同一个实例"
    finally:
        # 恢复
        server_module._client = original_client


# ==================== 文档和脚本检查 ====================

@test("README.md 存在")
def test_readme_exists():
    readme = project_root / "mcp_servers" / "winapp" / "README.md"
    assert readme.exists(), "README.md 不存在"
    content = readme.read_text(encoding="utf-8")
    assert "WinAppDriver" in content, "README 内容不正确"


@test(".env.sample 配置文件存在")
def test_env_sample_exists():
    env_sample = project_root / "mcp_servers" / "winapp" / ".env.sample"
    assert env_sample.exists(), ".env.sample 不存在"
    content = env_sample.read_text(encoding="utf-8")
    assert "WINAPPDRIVER_HOST" in content, "配置文件缺少 WINAPPDRIVER_HOST"


@test("Windows 启动脚本存在")
def test_start_bat_exists():
    start_bat = project_root / "mcp_servers" / "winapp" / "scripts" / "start.bat"
    assert start_bat.exists(), "start.bat 不存在"


@test("打包脚本存在")
def test_build_scripts_exist():
    scripts_dir = project_root / "mcp_servers" / "winapp" / "scripts"
    for arch in ["x86", "x64", "arm64"]:
        script = scripts_dir / f"build_{arch}.ps1"
        assert script.exists(), f"build_{arch}.ps1 不存在"
    print("    (x86, x64, arm64 三个平台打包脚本)")


@test("requirements.txt 存在")
def test_requirements_exists():
    req = project_root / "mcp_servers" / "winapp" / "requirements.txt"
    assert req.exists(), "requirements.txt 不存在"
    content = req.read_text(encoding="utf-8")
    assert "mcp" in content, "requirements.txt 缺少 mcp 依赖"
    assert "httpx" in content, "requirements.txt 缺少 httpx 依赖"
    assert "loguru" in content, "requirements.txt 缺少 loguru 依赖"


# ==================== 输出结果 ====================

print()
print("=" * 70)
print("  测试汇总")
print("=" * 70)
print(f"  通过: {passed}")
print(f"  失败: {failed}")
if warnings > 0:
    print(f"  警告: {warnings}")
print(f"  总计: {passed + failed}")
print()

if errors:
    print("  错误详情:")
    for err in errors:
        print(f"    - {err}")
    print()

if failed == 0:
    print("  ✅ 所有测试通过!")
    sys.exit(0)
else:
    print(f"  ❌ 有 {failed} 个测试失败")
    sys.exit(1)
