"""
Hypium UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class HypiumUITreeAdapter(BaseUITreeAdapter):
    """Hypium MCP 设备 UI 树适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        if device_type and "hypium" in device_type.lower():
            return True
        return isinstance(raw_data, dict) and any(k in raw_data for k in ["@type", "@class"])

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        if isinstance(raw_data, dict):
            return self._parse_dict_element(raw_data, path=[], depth=0)
        return None

    def _parse_dict_element(self, data: Dict[str, Any], path: List[str], depth: int) -> UIElement:
        attrs = dict(data)
        name = (attrs.get("text") or attrs.get("content-desc") or attrs.get("contentDescription") or attrs.get("id") or "").strip()

        element = UIElement(
            name=name,
            tag=attrs.get("@type") or attrs.get("@class") or attrs.get("tag") or "node",
            control_type=attrs.get("@type") or attrs.get("type") or "",
            automation_id=attrs.get("id") or attrs.get("resource-id") or "",
            class_name=attrs.get("@class") or attrs.get("class") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
        )

        if name:
            element.path.append(name)

        for key in ["children", "nodes", "elements", "child"]:
            children = attrs.get(key)
            if isinstance(children, list):
                for child_data in children:
                    if isinstance(child_data, dict):
                        child = self._parse_dict_element(child_data, element.path.copy(), depth + 1)
                        element.children.append(child)

        return element
