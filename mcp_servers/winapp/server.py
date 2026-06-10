"""WinAppDriver MCP 服务器主入口"""
import base64
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# 确保打包后能正确导入同目录模块以及 src 目录
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
for d in [current_dir, os.path.join(project_root, "src")]:
    if d not in sys.path:
        sys.path.insert(0, d)

from mcp.server.fastmcp import FastMCP
from loguru import logger

from config import winapp_settings
from client import WinAppDriverClient

# ==================== Local Device Wrapper for AI SDK ====================
from device.base import BaseDevice

class LocalWinAppDevice(BaseDevice):
    """用于在 MCP Server 内部运行 PyMidscene 的本地设备封装"""
    def __init__(self, client: WinAppDriverClient, **kwargs):
        super().__init__(**kwargs)
        self.client = client
    
    @property
    def interface_type(self) -> str: return "windows"
    def launch(self) -> None: pass # 已经由 server 启动
    def close(self) -> None: pass
    def goto(self, url: str, **kwargs) -> None: pass
    def get_page_content(self) -> str: return self.client.get_page_source()
    def get_dom_tree(self) -> Dict[str, Any]: return {"xml": self.get_page_content()}
    def screenshot(self, save_path: Optional[Path] = None, full_page: bool = True) -> bytes:
        img = self.client.get_screenshot()
        if save_path:
            save_path.write_bytes(img)
        return img
    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        if selector:
            eid = self.client.find_element("accessibility id", selector)
            self.client.click_element(eid)
        elif position:
            self.client.mouse_move(int(position[0]), int(position[1]))
            self.client.mouse_click()
    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None:
        if selector:
            eid = self.client.find_element("accessibility id", selector)
            if clear_before: self.client.clear_element(eid)
            self.client.send_keys_to_element(eid, text)
        else:
            if position: self.client.mouse_move(int(position[0]), int(position[1]))
            self.client.send_keys(text)
    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None: pass
    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool: return True
    def evaluate_script(self, script: str, *args) -> Any: return None

# ==================== AI SDK 实例管理 ====================
from sdk.pymidscene import PyMidscene

_midscene: Optional[PyMidscene] = None

def get_midscene() -> PyMidscene:
    """获取本地 AI SDK 实例"""
    global _midscene
    if _midscene is None:
        client = get_client()
        local_device = LocalWinAppDevice(client)
        # 初始化 SDK，使用 manual 模式并手动注入本地设备
        _midscene = PyMidscene(device_provider="manual", use_agent=True)
        _midscene.browser = local_device
        _midscene.device = local_device
        _midscene._launched = True # 标记已启动
    return _midscene

# 配置日志
logger.remove()
_log_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>"
if sys.stderr is not None:
    logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"), format=_log_format)
if sys.stdout is not None:
    logger.add(sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"), format=_log_format)
# 打包模式下写入文件日志
if getattr(sys, "frozen", False):
    exe_dir = Path(sys.executable).parent
    logger.add(exe_dir / "winapp_mcp.log", level="DEBUG", rotation="10 MB", retention="3 days")

# 创建 MCP 服务器
mcp = FastMCP(
    "WinAppDriver",
    instructions="控制 Windows 桌面应用的 MCP 服务器，基于 WinAppDriver",
    host=winapp_settings.MCP_HOST,
    port=winapp_settings.MCP_PORT,
    dependencies=["httpx", "loguru", "pydantic-settings"],
)

# 全局客户端实例
_client: Optional[WinAppDriverClient] = None


def get_client() -> WinAppDriverClient:
    """获取客户端实例"""
    global _client
    if _client is None:
        _client = WinAppDriverClient(auto_start=winapp_settings.WINAPPDRIVER_AUTO_START)
    return _client


# ==================== 辅助函数 ====================

def _handle_error(e: Exception, action: str) -> str:
    """统一错误处理"""
    error_msg = f"❌ {action} 失败:\n{type(e).__name__}: {str(e)}"
    logger.error(f"{action} 失败: {e}", exc_info=True)
    return error_msg


# ==================== Session 管理工具 ====================

@mcp.tool(description="创建 WinAppDriver 会话并启动应用")
def winapp_create_session(
    app: str,
    app_args: Optional[str] = None,
    platform_name: str = "Windows",
    device_name: str = "WindowsPC",
) -> str:
    """创建新的 WinAppDriver 会话"""
    try:
        client = get_client()
        session_id = client.create_session(app, app_args, platform_name, device_name)
        logger.info(f"Session created: {session_id}")
        return f"会话创建成功，ID: {session_id}\n应用: {app}"
    except Exception as e:
        return _handle_error(e, "创建会话")


@mcp.tool(description="关闭当前 WinAppDriver 会话")
def winapp_delete_session() -> str:
    """关闭当前会话"""
    try:
        client = get_client()
        client.delete_session()
        return "会话已关闭"
    except Exception as e:
        return _handle_error(e, "关闭会话")


@mcp.tool(description="获取所有活跃会话列表")
def winapp_get_sessions() -> str:
    """获取所有活跃会话"""
    try:
        client = get_client()
        sessions = client.get_sessions()
        return f"活跃会话数: {len(sessions)}\n{str(sessions)}"
    except Exception as e:
        return _handle_error(e, "获取会话列表")


@mcp.tool(description="获取 WinAppDriver 服务状态")
def winapp_get_status() -> str:
    """获取 WinAppDriver 服务状态"""
    try:
        client = get_client()
        status = client.get_status()
        return f"WinAppDriver 状态:\n{str(status)}"
    except Exception as e:
        return _handle_error(e, "获取服务状态")


# ==================== 交互工具 ====================

@mcp.tool(description="在当前窗口截图")
def winapp_screenshot() -> str:
    """获取当前窗口截图，返回 base64 字符串"""
    try:
        client = get_client()
        img_bytes = client.get_screenshot()
        return base64.b64encode(img_bytes).decode()
    except Exception as e:
        return _handle_error(e, "截图")


@mcp.tool(description="获取当前窗口的 XML 源码")
def winapp_get_source() -> str:
    """获取当前页面源码 (XML)"""
    try:
        client = get_client()
        return client.get_page_source()
    except Exception as e:
        return _handle_error(e, "获取源码")


@mcp.tool(description="点击指定选择器的元素")
def winapp_click_element(selector: str, using: str = "accessibility id") -> str:
    """点击元素
    
    Args:
        selector: 元素选择器
        using: 定位策略 (id, name, class name, xpath, accessibility id)
    """
    try:
        client = get_client()
        element_id = client.find_element(using, selector)
        client.click_element(element_id)
        return f"已点击元素: {selector}"
    except Exception as e:
        return _handle_error(e, f"点击元素 {selector}")


@mcp.tool(description="点击指定坐标")
def winapp_click(x: int, y: int) -> str:
    """点击屏幕坐标"""
    try:
        client = get_client()
        client.mouse_move(x, y)
        client.mouse_click()
        return f"已点击坐标: ({x}, {y})"
    except Exception as e:
        return _handle_error(e, f"点击坐标 ({x}, {y})")


@mcp.tool(description="向指定选择器的元素发送文本")
def winapp_send_keys(keys: str, selector: Optional[str] = None, using: str = "accessibility id") -> str:
    """发送文本按键
    
    Args:
        keys: 要发送的文本
        selector: (可选) 目标元素选择器，若不提供则发送到当前焦点
        using: 定位策略
    """
    try:
        client = get_client()
        if selector:
            element_id = client.find_element(using, selector)
            client.send_keys_to_element(element_id, keys)
            return f"已向元素 {selector} 发送文本: {keys}"
        else:
            client.send_keys(keys)
            return f"已发送全局文本: {keys}"
    except Exception as e:
        return _handle_error(e, f"发送文本 {keys}")


@mcp.tool(description="清空指定选择器的元素内容")
def winapp_clear_element(selector: str, using: str = "accessibility id") -> str:
    """清空元素"""
    try:
        client = get_client()
        element_id = client.find_element(using, selector)
        client.clear_element(element_id)
        return f"已清空元素: {selector}"
    except Exception as e:
        return _handle_error(e, f"清空元素 {selector}")


@mcp.tool(description="设置会话超时时间")
def winapp_set_timeout(timeout_type: str, ms: int) -> str:
    """设置超时时间"""
    try:
        client = get_client()
        client.set_timeout(timeout_type, ms)
        return f"超时已设置: {timeout_type} = {ms}ms"
    except Exception as e:
        return _handle_error(e, "设置超时")


# ==================== AI 交互工具 (由 SDK 实现) ====================

@mcp.tool(description="使用 AI 定位并点击元素")
def winapp_ai_click(prompt: str) -> str:
    """AI 点击
    
    Args:
        prompt: 自然语言描述，如 '点击登录按钮'
    """
    try:
        midscene = get_midscene()
        midscene.ai_click(prompt)
        return f"✅ AI 点击成功: {prompt}"
    except Exception as e:
        return _handle_error(e, f"AI 点击 {prompt}")


@mcp.tool(description="使用 AI 定位并输入文本")
def winapp_ai_input(prompt: str, text: str) -> str:
    """AI 输入
    
    Args:
        prompt: 目标元素的自然语言描述
        text: 要输入的文本
    """
    try:
        midscene = get_midscene()
        midscene.ai_input(prompt, text)
        return f"✅ AI 输入成功: 向 {prompt} 输入 {text}"
    except Exception as e:
        return _handle_error(e, f"AI 输入 {prompt}")


@mcp.tool(description="使用 AI 提取页面信息")
def winapp_ai_extract(prompt: str) -> str:
    """AI 提取信息"""
    try:
        midscene = get_midscene()
        result = midscene.ai_extract(prompt)
        return f"✅ AI 提取成功: {json.dumps(result, ensure_ascii=False)}"
    except Exception as e:
        return _handle_error(e, f"AI 提取 {prompt}")


@mcp.tool(description="使用 AI 进行页面断言")
def winapp_ai_assert(prompt: str) -> str:
    """AI 断言"""
    try:
        midscene = get_midscene()
        midscene.ai_assert(prompt)
        return f"✅ AI 断言成立: {prompt}"
    except Exception as e:
        return _handle_error(e, f"AI 断言 {prompt}")


# ==================== 主入口 ====================

def main():
    """启动 MCP 服务器"""
    logger.info("=" * 50)
    logger.info("  WinAppDriver MCP Server 启动")
    logger.info("=" * 50)
    logger.info(f"  MCP 监听地址: http://{winapp_settings.MCP_HOST}:{winapp_settings.MCP_PORT}/sse")
    logger.info(f"  WinAppDriver: {winapp_settings.WINAPPDRIVER_HOST}:{winapp_settings.WINAPPDRIVER_PORT}")
    logger.info(f"  HTTP 超时: {winapp_settings.WINAPPDRIVER_HTTP_TIMEOUT}s")
    logger.info(f"  Auto-start: {winapp_settings.WINAPPDRIVER_AUTO_START}")
    logger.info("=" * 50)

    try:
        mcp.run(transport="sse")
    except KeyboardInterrupt:
        logger.info("收到停止信号")
    except Exception as e:
        logger.error(f"服务器异常: {e}")
        raise
    finally:
        global _client
        if _client:
            _client.close()
            _client = None
        logger.info("服务器已停止")


if __name__ == "__main__":
    main()
