"""
Playwright / Browser UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class PlaywrightUITreeAdapter(BaseUITreeAdapter):
    """Playwright (浏览器) UI 树适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        if device_type and ("web" in device_type.lower() or "browser" in device_type.lower() or "playwright" in device_type.lower()):
            return True
        return isinstance(raw_data, dict) and "tagName" in raw_data

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        if isinstance(raw_data, dict):
            return self._parse_dict_element(raw_data, path=[], depth=0)
        return None

    def _parse_dict_element(self, data: Dict[str, Any], path: List[str], depth: int) -> UIElement:
        raw_attrs = dict(data)
        nested_attrs = raw_attrs.get("attributes")
        attrs = dict(nested_attrs) if isinstance(nested_attrs, dict) else {}
        attrs.update(raw_attrs)

        text_content = attrs.get("text", attrs.get("textContent", ""))
        if isinstance(text_content, list):
            text_content = " ".join([str(text) for text in text_content if text])

        name = text_content.strip()
        if not name:
            name = attrs.get("id", "")

        element = UIElement(
            name=name,
            tag=attrs.get("tagName") or attrs.get("tag") or attrs.get("type") or "node",
            control_type=attrs.get("role") or attrs.get("type") or "element",
            automation_id=attrs.get("id", ""),
            class_name=attrs.get("class") or attrs.get("className", ""),
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
