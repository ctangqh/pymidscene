"""
iOS UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import ElementRef, UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class IOSUITreeAdapter(BaseUITreeAdapter):
    """iOS MCP 设备 UI 树适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        if device_type and "ios" in device_type.lower():
            return True
        return isinstance(raw_data, dict) and any(k in raw_data for k in ["XCUIElement", "elementType", "identifier"])

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        if isinstance(raw_data, dict):
            return self._parse_dict_element(raw_data, path=[], depth=0)
        return None

    def _parse_dict_element(self, data: Dict[str, Any], path: List[str], depth: int) -> UIElement:
        attrs = dict(data)
        name = (attrs.get("label") or attrs.get("identifier") or attrs.get("value") or attrs.get("name") or "").strip()
        locator_candidates = self._build_locator_candidates(name=name, attrs=attrs)
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="ios",
            name=name,
            tag=attrs.get("elementType") or attrs.get("type") or attrs.get("XCUIElementType") or "node",
            control_type=attrs.get("elementType") or attrs.get("type") or "",
            automation_id=attrs.get("identifier") or attrs.get("id") or "",
            class_name=attrs.get("XCUIElementType") or attrs.get("elementType") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
            element_ref=element_ref,
            locator_candidates=locator_candidates,
            action_capabilities=self._build_action_capabilities(attrs),
        )

        if name:
            element.path.append(name)

        children = attrs.get("children")
        if isinstance(children, list):
            for child_data in children:
                if isinstance(child_data, dict):
                    child = self._parse_dict_element(child_data, element.path.copy(), depth + 1)
                    element.children.append(child)

        return element

    @staticmethod
    def _append_candidate(candidates: List[ElementRef], selector_type: str, selector_value: str, **extra: Any) -> None:
        value = str(selector_value or "").strip()
        if not value:
            return
        if any(item.selector_type == selector_type and item.selector_value == value for item in candidates):
            return
        candidates.append(
            ElementRef(platform="ios", selector_type=selector_type, selector_value=value, extra=extra)
        )

    def _build_locator_candidates(self, *, name: str, attrs: Dict[str, Any]) -> List[ElementRef]:
        candidates: List[ElementRef] = []
        identifier = attrs.get("identifier") or attrs.get("id")
        self._append_candidate(candidates, "identifier", identifier)
        self._append_candidate(candidates, "name", attrs.get("name"))
        self._append_candidate(candidates, "label", attrs.get("label"))
        if name:
            self._append_candidate(candidates, "predicate", f"name == '{name}' OR label == '{name}'")
            self._append_candidate(candidates, "xpath", f"//*[@name='{name}' or @label='{name}']")
        return candidates

    @staticmethod
    def _build_action_capabilities(attrs: Dict[str, Any]) -> Dict[str, bool]:
        searchable = " ".join(
            str(value).lower()
            for value in [attrs.get("elementType"), attrs.get("type"), attrs.get("XCUIElementType")]
            if value is not None
        )
        return {
            "click": True,
            "input": any(keyword in searchable for keyword in ["text", "field", "input", "secure"]),
        }
