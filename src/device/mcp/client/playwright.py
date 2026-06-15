from typing import Any, Dict, List, Optional, Tuple

from .base import BaseMcpDevice


class McpPlaywrightDevice(BaseMcpDevice):
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "playwright")
        super().__init__(**kwargs)
        
        self._tool_map = {
            "goto": {"tool": "browser_navigate"},
            "get_page_content": {"tool": "browser_evaluate", "mapper": lambda **k: {"function": "() => document.documentElement.outerHTML"}},
            "get_dom_tree": {"tool": "browser_snapshot"},
            "screenshot": {"tool": "browser_take_screenshot", "mapper": lambda **k: {"type": "png", "fullPage": k.get("full_page", True)}},
            "click": {"tool": "browser_click", "mapper": lambda **k: {"element": k.get("selector"), "target": k.get("selector")}},
            "input": {"tool": "browser_type", "mapper": lambda **k: {"element": k.get("selector"), "text": k.get("text")}},
            "scroll": {"tool": "browser_evaluate", "mapper": self._pw_scroll_mapper},
            "evaluate": {"tool": "browser_evaluate", "mapper": lambda **k: {"function": k.get("script")}},
            "keyboard_press": {"tool": "browser_press_key"},
            "ai_click": {"tool": "playwright_ai_click"},
            "ai_input": {"tool": "playwright_ai_input"},
            "ai_extract": {"tool": "playwright_ai_extract"},
            "ai_assert": {"tool": "playwright_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "browser"

    def size(self) -> Tuple[int, int]:
        try:
            viewport = self.evaluate_script(
                """
() => ({
  width: window.innerWidth || document.documentElement.clientWidth || 0,
  height: window.innerHeight || document.documentElement.clientHeight || 0
})
""".strip()
            )
            if isinstance(viewport, dict):
                width = int(round(float(viewport.get("width") or 0)))
                height = int(round(float(viewport.get("height") or 0)))
                if width > 0 and height > 0:
                    return (width, height)
        except Exception:
            pass
        return super().size()

    def _pw_scroll_mapper(self, **k):
        dist = k.get("distance") or self.viewport_height * 0.8
        direction = k.get("direction", "down")
        sign = {"down": ("0", str(dist)), "up": ("0", str(-dist))}.get(direction, ("0", str(dist)))
        return {"function": f"() => window.scrollBy({sign[0]}, {sign[1]})"}

    @staticmethod
    def _normalize_playwright_selector(selector: Optional[str], **kwargs) -> Dict[str, Any]:
        ref = BaseMcpDevice._selector_ref(selector, **kwargs)
        selector_type = ref.get("selector_type") or ""
        selector_value = ref.get("selector_value") or selector
        extra = ref.get("extra") or {}

        if not selector_value:
            return {}
        if selector_type == "playwright-ref":
            return {"element": selector_value, "ref": selector_value}
        if selector_type == "role" and extra.get("role") and extra.get("name"):
            return {"target": f'{extra["role"]}="{extra["name"]}"'}
        return {"target": selector_value}

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        resolved_selector = self._selector_value(selector, resolved_ref)
        if resolved_selector:
            normalize_kwargs = dict(kwargs)
            normalize_kwargs.pop("selector_ref", None)
            args = self._normalize_playwright_selector(
                resolved_selector,
                selector_ref=resolved_ref,
                **normalize_kwargs,
            )
            self._submit(self._call_mcp("browser_click", args))
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
        resolved_selector = self._selector_value(selector, resolved_ref)
        if resolved_selector:
            normalize_kwargs = dict(kwargs)
            normalize_kwargs.pop("selector_ref", None)
            args = self._normalize_playwright_selector(
                resolved_selector,
                selector_ref=resolved_ref,
                **normalize_kwargs,
            )
            args["text"] = text
            self._submit(self._call_mcp("browser_type", args))
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)

    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)

