from typing import Any, List, Optional, Tuple

from .base import BaseMcpDevice
from .hypium import McpHypiumDevice


class McpAndroidDevice(BaseMcpDevice):
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "android")
        super().__init__(**kwargs)
        
        self._tool_map = {
            "get_page_content": {"tool": "android_get_source"},
            "get_dom_tree": {"tool": "android_get_source"},
            "screenshot": {"tool": "android_screenshot"},
            "click": {"tool": "android_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "android_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            "ai_click": {"tool": "android_ai_click"},
            "ai_input": {"tool": "android_ai_input"},
            "ai_extract": {"tool": "android_ai_extract"},
            "ai_assert": {"tool": "android_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "android"

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("click", selector=normalized_selector, **kwargs)
            return
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("input", text=text, selector=normalized_selector, clear_before=clear_before, **kwargs)
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)

