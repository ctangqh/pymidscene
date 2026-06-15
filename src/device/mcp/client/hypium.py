from typing import Any, List, Optional, Tuple

from .base import BaseMcpDevice


class McpHypiumDevice(BaseMcpDevice):
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "hypium")
        super().__init__(**kwargs)

        self._current_package_name: Optional[str] = None
        
        self._tool_map = {
            "create_session": {
                "tool": "hypium_start_app",
                "mapper": lambda **k: {
                    "package_name": k.get("package_name") or k.get("app"),
                    "page_name": k.get("page_name"),
                    "params": k.get("params", ""),
                    "wait_time": k.get("wait_time", 1),
                },
            },
            "delete_session": {
                "tool": "hypium_stop_app",
                "mapper": lambda **k: {
                    "package_name": k.get("package_name") or k.get("app"),
                    "wait_time": k.get("wait_time", 0.5),
                },
            },
            "get_page_content": {"tool": "hypium_get_source"},
            "get_dom_tree": {"tool": "hypium_get_source"},
            "screenshot": {"tool": "hypium_screenshot"},
            "click": {"tool": "hypium_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "hypium_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            "ai_click": {"tool": "hypium_ai_click"},
            "ai_input": {"tool": "hypium_ai_input"},
            "ai_extract": {"tool": "hypium_ai_extract"},
            "ai_assert": {"tool": "hypium_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "hypium"

    def _execute_mcp_action(self, action_name: str, **kwargs) -> Any:
        if action_name == "create_session":
            package_name = kwargs.get("package_name") or kwargs.get("app")
            if package_name:
                self._current_package_name = str(package_name)
            return super()._execute_mcp_action(action_name, **kwargs)
        if action_name == "delete_session":
            if not (kwargs.get("package_name") or kwargs.get("app")) and self._current_package_name:
                kwargs = dict(kwargs)
                kwargs["package_name"] = self._current_package_name
            return super()._execute_mcp_action(action_name, **kwargs)
        return super()._execute_mcp_action(action_name, **kwargs)

    @staticmethod
    def _normalize_mobile_selector(selector: Optional[str], **kwargs) -> Optional[str]:
        ref = BaseMcpDevice._selector_ref(selector, **kwargs)
        selector_value = ref.get("selector_value") or selector
        selector_type = (ref.get("selector_type") or "").strip().lower()
        if not selector_value:
            return None
        if selector_type in {"xpath", "predicate", "css", "text", "name", "label", "identifier", "resource-id", "accessibility-id"}:
            return selector_value
        return selector_value

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        normalized_selector = self._normalize_mobile_selector(
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
        normalized_selector = self._normalize_mobile_selector(
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

