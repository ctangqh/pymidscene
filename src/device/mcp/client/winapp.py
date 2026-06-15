from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .base import BaseMcpDevice


class McpWinAppDevice(BaseMcpDevice):
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "winapp")
        super().__init__(**kwargs)
        
        self._tool_map = {
            "create_session": {"tool": "winapp_create_session"},
            "delete_session": {"tool": "winapp_delete_session"},
            "get_status": {"tool": "winapp_get_status"},
            "get_page_content": {"tool": "winapp_get_source"},
            "get_dom_tree": {"tool": "winapp_get_source"},
            "screenshot": {"tool": "winapp_screenshot"},
            "click": {"tool": "winapp_click", "mapper": lambda **k: {"x": int(k.get("position", (0, 0))[0]), "y": int(k.get("position", (0, 0))[1])}},
            "input": {"tool": "winapp_send_keys", "mapper": lambda **k: {"selector": k.get("selector"), "keys": k.get("text")}},
            "keyboard_press": {"tool": "winapp_press_keys", "mapper": lambda **k: {"keys": k.get("key")}},
            "clear": {"tool": "winapp_clear_element"},
            "ai_click": {"tool": "winapp_ai_click"},
            "ai_input": {"tool": "winapp_ai_input"},
            "ai_extract": {"tool": "winapp_ai_extract"},
            "ai_assert": {"tool": "winapp_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "windows"

    @staticmethod
    def _winapp_element_args(selector_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ref = selector_ref or {}
        selector_value = ref.get("selector_value")
        if not selector_value:
            return {}
        selector_type = (ref.get("selector_type") or "accessibility id").strip()
        if ref.get("ref_kind") == "handle" or selector_type.lower() == "element_id" or ref.get("resolved"):
            return {"element_id": selector_value}
        return {"selector": selector_value, "using": selector_type}

    def resolve_selector_ref(
        self,
        selector: Optional[str] = None,
        *,
        action_type: str = "tap",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        ref = super().resolve_selector_ref(selector, action_type=action_type, **kwargs)
        if not ref:
            return None

        selector_value = ref.get("selector_value")
        selector_type = (ref.get("selector_type") or "accessibility id").strip()
        if not selector_value:
            return None
        if ref.get("resolved") and (ref.get("ref_kind") == "handle" or selector_type.lower() == "element_id"):
            return ref
        if not ref.get("requires_resolution", False):
            return ref

        try:
            result = self._submit(
                self._call_mcp(
                    "winapp_find_element",
                    {"selector": selector_value, "using": selector_type},
                )
            )
            element_id = self._parse_text(result).strip()
            if not element_id:
                return ref
            return {
                "platform": ref.get("platform", "windows"),
                "ref_kind": "handle",
                "source": "remote_resolved",
                "selector_type": "element_id",
                "selector_value": element_id,
                "actionable": True,
                "persistable": False,
                "requires_resolution": False,
                "resolved": True,
                "extra": {
                    "resolved_from": {
                        "selector_type": selector_type,
                        "selector_value": selector_value,
                    },
                    **dict(ref.get("extra") or {}),
                },
            }
        except Exception as e:
            logger.debug(
                f"WinApp resolve selector ref failed, keep selector ref: selector={selector_value}, using={selector_type}, error={e}"
            )
            return ref

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        action_args = self._winapp_element_args(resolved_ref)
        if action_args:
            try:
                self._submit(
                    self._call_mcp(
                        "winapp_click_element",
                        action_args,
                    )
                )
                return
            except Exception as e:
                logger.debug(
                    f"WinApp element click failed, fallback to coordinate click: ref={resolved_ref}, error={e}"
                )
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
        action_args = self._winapp_element_args(resolved_ref)
        if action_args:
            try:
                if clear_before:
                    self._submit(
                        self._call_mcp(
                            "winapp_clear_element",
                            action_args,
                        )
                    )
                self._submit(
                    self._call_mcp(
                        "winapp_send_keys_to_element",
                        {**action_args, "text": text},
                    )
                )
                return
            except Exception as e:
                logger.debug(
                    f"WinApp element input failed, fallback to generic input: ref={resolved_ref}, error={e}"
                )
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)

