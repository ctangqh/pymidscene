from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
from common.config import settings

# Forward imports to avoid circular dependencies
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.types import DeviceAction, ElementCacheFeature, Rect

class BaseDevice(ABC):
    def __init__(self, **kwargs):
        self.headless = kwargs.get("headless", settings.DEVICE_HEADLESS)
        self.viewport_width = kwargs.get("viewport_width", settings.DEVICE_VIEWPORT_WIDTH)
        self.viewport_height = kwargs.get("viewport_height", settings.DEVICE_VIEWPORT_HEIGHT)
        self.user_agent = kwargs.get("user_agent", settings.DEVICE_USER_AGENT)
        self.timeout = kwargs.get("timeout", settings.DEVICE_TIMEOUT)
        self.current_url = ""
        
    @property
    def interface_type(self) -> str:
        """Return device type string (e.g. 'browser', 'mobile')"""
        raise NotImplementedError
    
    @abstractmethod
    def launch(self) -> None: pass
    @abstractmethod
    def close(self) -> None: pass
    @abstractmethod
    def goto(self, url: str, **kwargs) -> None: pass
    @abstractmethod
    def get_page_content(self) -> str: pass
    @abstractmethod
    def get_dom_tree(self) -> Dict[str, Any]: pass
    @abstractmethod
    def screenshot(self, save_path: Optional[Path] = None, full_page: bool = True) -> bytes: pass
    
    def screenshot_base64(self) -> str:
        """Return base64 encoded screenshot"""
        import base64
        return base64.b64encode(self.screenshot()).decode()
    
    @abstractmethod
    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None: pass
    
    def right_click(self, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        """Right click at position"""
        raise NotImplementedError
    
    def double_click(self, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        """Double click at position"""
        raise NotImplementedError
    
    def hover(self, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        """Hover at position"""
        raise NotImplementedError
    
    def long_press(self, position: Optional[Tuple[float, float]], duration: int = 500, **kwargs) -> None:
        """Long press at position for duration (ms)"""
        raise NotImplementedError
    
    def keyboard_press(self, key_name: str, **kwargs) -> None:
        """Press keyboard key"""
        raise NotImplementedError
    
    @abstractmethod
    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None: pass
    @abstractmethod
    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None: pass
    @abstractmethod
    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool: pass
    @abstractmethod
    def evaluate_script(self, script: str, *args) -> Any: pass
    
    def size(self) -> Tuple[int, int]:
        """Return logical viewport size (width, height)"""
        return (self.viewport_width, self.viewport_height)
    
    def action_space(self) -> List["DeviceAction"]:
        """Return list of supported actions by this device. Default: empty."""
        return []
    
    def before_invoke_action(self, action_name: str, param: Dict[str, Any]) -> None:
        """Pre-action hook, called before executing an action"""
        pass
    
    def after_invoke_action(self, action_name: str, param: Dict[str, Any]) -> None:
        """Post-action hook, called after executing an action"""
        pass
    
    def cache_feature_for_point(self, point: Tuple[float, float], options: Optional[Dict[str, Any]] = None) -> Optional["ElementCacheFeature"]:
        """Get cache feature for a point (for element cache)"""
        return None
    
    def rect_matches_cache_feature(self, feature: "ElementCacheFeature") -> Optional["Rect"]:
        """Check if cache feature matches current page, return rect if found"""
        return None
    
    def destroy(self) -> None:
        """Cleanup resources, alias for close() for compatibility"""
        self.close()
    
    def get_device_local_time_string(self, format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Get device local time as string (defaults to host time if not implemented)"""
        from datetime import datetime
        return datetime.now().strftime(format)
    
    def get_elements_node_tree(self) -> Dict[str, Any]:
        """Get element node tree for DOM extraction (defaults to get_dom_tree())"""
        return self.get_dom_tree()
    
    def __enter__(self):
        self.launch()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


BaseBrowser = BaseDevice
