from typing import Optional, Dict, Any
from .base import BaseDevice
from .browser.playwright_impl import PlaywrightDevice
from .mcp import (
    McpPlaywrightDevice,
    McpWinAppDevice,
    McpAndroidDevice,
    McpIosDevice,
    McpHypiumDevice
)
from common.exceptions import ModelUnsupportedError
from common.config import settings

class DeviceFactory:
    """设备实例工厂，创建不同类型的终端设备"""
    _device_providers: Dict[str, type[BaseDevice]] = {
        "browser": PlaywrightDevice, # 原生 Playwright Web 设备
        "mcp_playwright": McpPlaywrightDevice, # MCP Playwright
        "mcp_winapp": McpWinAppDevice,
        "mcp_android": McpAndroidDevice,
        "mcp_ios": McpIosDevice,
        "mcp_hypium": McpHypiumDevice,
        "manual": BaseDevice # 手动注入设备
    }
    
    @classmethod
    def create(cls, device_type: Optional[str] = None, **kwargs) -> BaseDevice:
        """创建设备实例
        
        Args:
            device_type: 设备类型 (browser, mcp_winapp, etc.)
            **kwargs: 
                mcp_name: 配置文件中 MCP_SERVERS 的 Key
                mcp_server_url: 覆盖配置文件中的 URL
                ... 其他参数
        """
        # 如果未指定设备类型，回退到配置中的默认 provider
        if not device_type:
            device_type = settings.DEFAULT_DEVICE_PROVIDER

        mcp_name = kwargs.get("mcp_name")
        if not mcp_name and isinstance(device_type, str) and device_type.startswith("mcp_"):
            inferred_name = device_type.removeprefix("mcp_")
            kwargs["mcp_name"] = settings.DEFAULT_MCP_NAME if device_type == settings.DEFAULT_DEVICE_PROVIDER else inferred_name

        device_type = device_type.lower()
        if device_type not in cls._device_providers:
            raise ModelUnsupportedError(f"不支持的设备类型：{device_type}，支持类型：{list(cls._device_providers.keys())}")
        
        return cls._device_providers[device_type](**kwargs)

def get_device(device_type: Optional[str] = None, **kwargs) -> BaseDevice:
    """获取通用设备实例，默认使用配置中的设备 provider"""
    return DeviceFactory.create(device_type, **kwargs)
