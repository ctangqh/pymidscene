"""
WinAppDriver MCP Server 单元测试
运行: python -m pytest mcp_servers/winapp/tests/test_server.py -v
"""
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import pytest

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestConfig:
    """配置测试"""

    def test_config_import(self):
        """测试配置模块导入"""
        from mcp_servers.winapp.config import winapp_settings, WinAppDriverSettings
        assert winapp_settings is not None
        assert isinstance(winapp_settings, WinAppDriverSettings)

    def test_config_default_values(self):
        """测试默认配置值"""
        from mcp_servers.winapp.config import winapp_settings
        assert winapp_settings.WINAPPDRIVER_HOST == "127.0.0.1"
        assert winapp_settings.WINAPPDRIVER_PORT == 4723
        assert winapp_settings.WINAPPDRIVER_AUTO_START is True


class TestClient:
    """WinAppDriver 客户端测试"""

    def test_client_import(self):
        """测试客户端模块导入"""
        from mcp_servers.winapp.client import WinAppDriverClient
        assert WinAppDriverClient is not None

    def test_client_initialization(self):
        """测试客户端初始化"""
        from mcp_servers.winapp.client import WinAppDriverClient
        client = WinAppDriverClient(host="127.0.0.1", port=4723, auto_start=False)
        assert client.host == "127.0.0.1"
        assert client.port == 4723
        assert client.auto_start is False
        assert client.session_id is None

    def test_client_base_url(self):
        """测试客户端 base URL 构造"""
        from mcp_servers.winapp.client import WinAppDriverClient
        client = WinAppDriverClient(host="192.168.1.100", port=9999, auto_start=False)
        assert client.base_url == "http://192.168.1.100:9999"


class TestMCPTools:
    """MCP 工具注册测试"""

    def test_server_import(self):
        """测试服务器模块导入"""
        from mcp_servers.winapp.server import mcp, get_client
        assert mcp is not None
        assert get_client is not None

    def test_all_tools_registered(self):
        """测试所有 MCP 工具是否已注册"""
        from mcp_servers.winapp.server import mcp

        expected_tools = {
            # Session 管理 (5)
            "winapp_create_session",
            "winapp_delete_session",
            "winapp_get_sessions",
            "winapp_get_status",
            "winapp_set_timeout",
            # 元素操作 (15)
            "winapp_find_element",
            "winapp_find_elements",
            "winapp_find_element_from_element",
            "winapp_click_element",
            "winapp_clear_element",
            "winapp_send_keys_to_element",
            "winapp_get_element_text",
            "winapp_get_element_attribute",
            "winapp_get_element_name",
            "winapp_is_element_displayed",
            "winapp_is_element_enabled",
            "winapp_is_element_selected",
            "winapp_get_element_location",
            "winapp_get_element_size",
            "winapp_get_element_screenshot",
            # 鼠标操作 (5)
            "winapp_mouse_move",
            "winapp_mouse_click",
            "winapp_mouse_double_click",
            "winapp_mouse_button_down",
            "winapp_mouse_button_up",
            # 键盘操作 (1)
            "winapp_send_keys",
            # 窗口操作 (8)
            "winapp_get_window_handle",
            "winapp_get_window_handles",
            "winapp_set_window_size",
            "winapp_get_window_size",
            "winapp_set_window_position",
            "winapp_get_window_position",
            "winapp_maximize_window",
            "winapp_close_window",
            # 截图 & 源码 (2)
            "winapp_get_screenshot",
            "winapp_get_page_source",
            # 导航 (2)
            "winapp_navigate_back",
            "winapp_navigate_forward",
            # 触摸操作 (8)
            "winapp_touch_click",
            "winapp_touch_double_click",
            "winapp_touch_long_click",
            "winapp_touch_down",
            "winapp_touch_up",
            "winapp_touch_move",
            "winapp_touch_scroll",
            "winapp_touch_flick",
        }

        actual_tools = set(mcp._tool_manager._tools.keys())
        missing_tools = expected_tools - actual_tools
        extra_tools = actual_tools - expected_tools

        assert len(missing_tools) == 0, f"缺少工具: {missing_tools}"
        assert len(extra_tools) == 0, f"多余工具: {extra_tools}"
        assert len(actual_tools) == 46, f"期望 46 个工具，实际 {len(actual_tools)} 个"

    def test_tool_descriptions(self):
        """测试工具是否都有描述"""
        from mcp_servers.winapp.server import mcp

        for tool_name, tool in mcp._tool_manager._tools.items():
            assert tool.description is not None, f"工具 {tool_name} 缺少 description"
            assert len(tool.description) > 0, f"工具 {tool_name} 的 description 为空"

    def test_tool_function_signatures(self):
        """测试工具函数签名是否正确"""
        from mcp_servers.winapp.server import mcp

        # 检查需要特定参数的工具
        param_checks = {
            "winapp_find_element": ["using", "value"],
            "winapp_click_element": ["element_id"],
            "winapp_send_keys_to_element": ["element_id", "text"],
            "winapp_mouse_move": ["x", "y"],
            "winapp_set_window_size": ["width", "height"],
            "winapp_touch_click": ["x", "y"],
        }

        for tool_name, expected_params in param_checks.items():
            tool = mcp._tool_manager._tools.get(tool_name)
            assert tool is not None, f"工具 {tool_name} 不存在"

            # 检查参数
            actual_params = set(tool.parameters.keys()) if hasattr(tool, 'parameters') else set()
            for param in expected_params:
                # MCP 内部存储可能略有不同，我们检查函数定义
                import inspect
                sig = inspect.signature(tool.fn)
                func_params = set(sig.parameters.keys())
                assert param in func_params, f"工具 {tool_name} 缺少参数: {param}"


class TestErrorHandling:
    """错误处理测试"""

    def test_get_client_singleton(self):
        """测试客户端单例模式"""
        from mcp_servers.winapp.server import get_client

        # 重置全局客户端
        import mcp_servers.winapp.server as server_module
        server_module._client = None

        # 第一次调用创建新客户端
        client1 = get_client()
        client2 = get_client()

        # 验证是同一个实例
        assert client1 is client2


def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("  WinAppDriver MCP Server 单元测试")
    print("=" * 70)
    print()

    # 运行测试
    test_dir = os.path.dirname(os.path.abspath(__file__))
    result = pytest.main([test_dir, "-v", "--tb=short"])

    print()
    print("=" * 70)
    if result == 0:
        print("  ✅ 所有测试通过!")
    else:
        print(f"  ❌ 测试失败，退出码: {result}")
    print("=" * 70)

    return result


if __name__ == "__main__":
    sys.exit(run_tests())
