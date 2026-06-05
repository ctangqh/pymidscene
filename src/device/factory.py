from typing import Optional, Dict, Any
from .base import BaseDevice
from .browser.playwright_impl import PlaywrightBrowser
from .mcp import McpPlaywrightDevice
from common.exceptions import ModelUnsupportedError

class DeviceFactory:
    """设备实例工厂，创建不同类型的终端设备"""
    _device_providers: Dict[str, type[BaseDevice]] = {
        "browser": PlaywrightBrowser,
        "mcp_playwright": McpPlaywrightDevice
    }
    @classmethod
    def create(cls, device_type: Optional[str] = "browser", **kwargs) -> BaseDevice:
        device_type = device_type.lower()
        if device_type not in cls._device_providers:
            raise ModelUnsupportedError(f"不支持的设备类型：{device_type}，支持类型：{list(cls._device_providers.keys())}")
        return cls._device_providers[device_type](**kwargs)

def get_browser(provider: Optional[str] = None, **kwargs) -> BaseDevice:
    return DeviceFactory.create("browser", **kwargs)

def get_device(device_type: str = "browser", **kwargs) -> BaseDevice:
    return DeviceFactory.create(device_type, **kwargs)
