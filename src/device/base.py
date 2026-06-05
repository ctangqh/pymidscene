from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from common.config import settings

class BaseDevice(ABC):
    def __init__(self, **kwargs):
        self.headless = kwargs.get("headless", settings.BROWSER_HEADLESS)
        self.viewport_width = kwargs.get("viewport_width", settings.BROWSER_VIEWPORT_WIDTH)
        self.viewport_height = kwargs.get("viewport_height", settings.BROWSER_VIEWPORT_HEIGHT)
        self.user_agent = kwargs.get("user_agent", settings.BROWSER_USER_AGENT)
        self.timeout = kwargs.get("timeout", settings.BROWSER_TIMEOUT)
        self.current_url = ""
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
    @abstractmethod
    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None: pass
    @abstractmethod
    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None: pass
    @abstractmethod
    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None: pass
    @abstractmethod
    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool: pass
    @abstractmethod
    def evaluate_script(self, script: str, *args) -> Any: pass
    def __enter__(self):
        self.launch()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
BaseBrowser = BaseDevice
