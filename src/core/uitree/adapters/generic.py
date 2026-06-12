"""
通用兜底 UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import ElementRef, UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class GenericUITreeAdapter(BaseUITreeAdapter):
    """通用回退适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        return True

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        if isinstance(raw_data, dict):
            return self._parse_dict_element(raw_data, path=[], depth=0)
        return None

    def _parse_dict_element(self, data: Dict[str, Any], path: List[str], depth: int) -> UIElement:
        attrs = dict(data)

        name = ""
        for key in ["name", "label", "text", "id", "identifier", "title", "value", "content"]:
            value = attrs.get(key)
            if value:
                name = str(value).strip()
                if name:
                    break

        locator_candidates = self._build_locator_candidates(name=name, attrs=attrs)
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="generic",
            name=name,
            tag=attrs.get("tag") or attrs.get("tagName") or attrs.get("type") or attrs.get("class") or "node",
            control_type=attrs.get("role") or attrs.get("type") or "",
            automation_id=attrs.get("id") or "",
            class_name=attrs.get("class") or attrs.get("className") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
            element_ref=element_ref,
            locator_candidates=locator_candidates,
            action_capabilities={"click": True, "input": False},
        )

        if name:
            element.path.append(name)

        for key in ["children", "nodes", "elements", "items", "subviews", "views", "child"]:
            children = attrs.get(key)
            if isinstance(children, list):
                for child_data in children:
                    if isinstance(child_data, dict):
                        child = self._parse_dict_element(child_data, element.path.copy(), depth + 1)
                        element.children.append(child)

        return element

    @staticmethod
    def _append_candidate(candidates: List[ElementRef], selector_type: str, selector_value: str) -> None:
        value = str(selector_value or "").strip()
        if not value:
            return
        if any(item.selector_type == selector_type and item.selector_value == value for item in candidates):
            return
        candidates.append(ElementRef(platform="generic", selector_type=selector_type, selector_value=value))

    def _build_locator_candidates(self, *, name: str, attrs: Dict[str, Any]) -> List[ElementRef]:
        candidates: List[ElementRef] = []
        for key in ["id", "identifier", "selector", "xpath", "name", "text", "label"]:
            value = attrs.get(key)
            if value:
                self._append_candidate(candidates, key, value)
        if name and not candidates:
            self._append_candidate(candidates, "name", name)
        return candidates
