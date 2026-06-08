"""WinAppDriver MCP 服务器主入口"""
import base64
import os
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from loguru import logger

from .config import winapp_settings
from .client import WinAppDriverClient

# 确保打包后能正确加载 .env
if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).parent
    env_path = exe_dir / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)

# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
)

# 创建 MCP 服务器
mcp = FastMCP(
    "WinAppDriver",
    instructions="控制 Windows 桌面应用的 MCP 服务器，基于 WinAppDriver",
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


@mcp.tool(description="设置会话超时时间")
def winapp_set_timeout(timeout_type: str, ms: int) -> str:
    """设置超时时间"""
    try:
        client = get_client()
        client.set_timeout(timeout_type, ms)
        return f"超时已设置: {timeout_type} = {ms}ms"
    except Exception as e:
        return _handle_error(e, "设置超时")


# ==================== 主入口 ====================

def main():
    """启动 MCP 服务器"""
    logger.info("=" * 50)
    logger.info("  WinAppDriver MCP Server 启动")
    logger.info("=" * 50)
    logger.info(f"  WinAppDriver: {winapp_settings.WINAPPDRIVER_HOST}:{winapp_settings.WINAPPDRIVER_PORT}")
    logger.info(f"  Auto-start: {winapp_settings.WINAPPDRIVER_AUTO_START}")
    logger.info("=" * 50)

    try:
        mcp.run()
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
