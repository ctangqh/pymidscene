"""
iOS UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import UIElement
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

        element = UIElement(
            name=name,
            tag=attrs.get("elementType") or attrs.get("type") or attrs.get("XCUIElementType") or "node",
            control_type=attrs.get("elementType") or attrs.get("type") or "",
            automation_id=attrs.get("identifier") or attrs.get("id") or "",
            class_name=attrs.get("XCUIElementType") or attrs.get("elementType") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
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
