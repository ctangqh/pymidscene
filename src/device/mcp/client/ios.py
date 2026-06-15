from typing import Any, List, Optional, Tuple

from .base import BaseMcpDevice
from .hypium import McpHypiumDevice


class McpIosDevice(BaseMcpDevice):
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "ios")
        super().__init__(**kwargs)
        
        self._tool_map = {
            "get_page_content": {"tool": "ios_get_source"},
            "get_dom_tree": {"tool": "ios_get_source"},
            "screenshot": {"tool": "ios_screenshot"},
            "click": {"tool": "ios_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "ios_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            "ai_click": {"tool": "ios_ai_click"},
            "ai_input": {"tool": "ios_ai_input"},
            "ai_extract": {"tool": "ios_ai_extract"},
            "ai_assert": {"tool": "ios_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "ios"

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

