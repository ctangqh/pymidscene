"""
Playwright / Browser UI Tree 适配器
"""
from typing import Any, Dict, List, Optional

from ..models import ElementRef, UIElement
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

        locator_candidates = self._build_locator_candidates(
            name=name,
            tag=str(attrs.get("tagName") or attrs.get("tag") or attrs.get("type") or "node"),
            attrs=attrs,
        )
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="playwright",
            name=name,
            tag=attrs.get("tagName") or attrs.get("tag") or attrs.get("type") or "node",
            control_type=attrs.get("role") or attrs.get("type") or "element",
            automation_id=attrs.get("id", ""),
            class_name=attrs.get("class") or attrs.get("className", ""),
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
    def _append_candidate(
        candidates: List[ElementRef],
        selector_type: str,
        selector_value: str,
        **extra: Any,
    ) -> None:
        value = str(selector_value or "").strip()
        if not value:
            return
        if any(item.selector_type == selector_type and item.selector_value == value for item in candidates):
            return
        candidates.append(
            ElementRef(
                platform="playwright",
                selector_type=selector_type,
                selector_value=value,
                extra=extra,
            )
        )

    def _build_locator_candidates(self, *, name: str, tag: str, attrs: Dict[str, Any]) -> List[ElementRef]:
        candidates: List[ElementRef] = []
        self._append_candidate(candidates, "playwright-ref", attrs.get("ref"))
        self._append_candidate(candidates, "selector", attrs.get("selector"))
        element_id = attrs.get("id")
        if element_id:
            self._append_candidate(candidates, "css", f"#{element_id}")
        test_id = attrs.get("data-testid") or attrs.get("testid")
        if test_id:
            self._append_candidate(candidates, "css", f'[data-testid="{test_id}"]')
        aria_label = attrs.get("aria-label")
        if aria_label:
            self._append_candidate(candidates, "css", f'[aria-label="{aria_label}"]')
        role = attrs.get("role")
        if role and name:
            self._append_candidate(candidates, "role", f"{role}:{name}", role=role, name=name)
        if tag and name:
            self._append_candidate(candidates, "text", f"text={name}", tag=tag)
        return candidates

    @staticmethod
    def _build_action_capabilities(attrs: Dict[str, Any]) -> Dict[str, bool]:
        searchable = " ".join(
            str(value).lower()
            for value in [attrs.get("role"), attrs.get("type"), attrs.get("tagName"), attrs.get("tag")]
            if value is not None
        )
        return {
            "click": True,
            "input": any(keyword in searchable for keyword in ["input", "textarea", "textbox", "searchbox"]),
        }
