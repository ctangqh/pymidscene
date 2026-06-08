"""WinAppDriver MCP 服务器配置"""
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# 打包模式下 .env 放在 exe 同级目录
_base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
_env_file = _base_dir / ".env"


class WinAppDriverSettings(BaseSettings):
    """WinAppDriver 配置"""

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MCP 服务器监听地址
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 55001

    # WinAppDriver 服务地址
    WINAPPDRIVER_HOST: str = "127.0.0.1"
    WINAPPDRIVER_PORT: int = 4723

    @property
    def WINAPPDRIVER_URL(self) -> str:
        return f"http://{self.WINAPPDRIVER_HOST}:{self.WINAPPDRIVER_PORT}"

    # WinAppDriver HTTP 请求超时（秒）
    WINAPPDRIVER_HTTP_TIMEOUT: int = 120

    # 默认应用配置（启动 session 时可覆盖）
    WINAPPDRIVER_APP: Optional[str] = None  # 应用路径或 AppX 包名
    WINAPPDRIVER_APP_ARGS: Optional[str] = None  # 应用启动参数
    WINAPPDRIVER_PLATFORM_NAME: str = "Windows"
    WINAPPDRIVER_DEVICE_NAME: str = "WindowsPC"

    # 超时配置
    WINAPPDRIVER_TIMEOUT: int = 30000  # 毫秒
    WINAPPDRIVER_NEW_COMMAND_TIMEOUT: int = 60  # 秒

    # 元素定位配置
    WINAPPDRIVER_IMPLICIT_WAIT: int = 10  # 秒

    # MCP 工具配置
    MCP_TOOL_PREFIX: str = "winapp_"

    # 是否自动启动 WinAppDriver（设为 false 表示 WinAppDriver 已在外部启动）
    WINAPPDRIVER_AUTO_START: bool = True


winapp_settings = WinAppDriverSettings()
