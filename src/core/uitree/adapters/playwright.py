"""
Playwright / Browser UI Tree 适配器
"""
import re
from typing import Any, Dict, List, Optional

import yaml

from ..models import ElementRef, UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class PlaywrightUITreeAdapter(BaseUITreeAdapter):
    """Playwright (浏览器) UI 树适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        if device_type and ("web" in device_type.lower() or "browser" in device_type.lower() or "playwright" in device_type.lower()):
            return True
        if isinstance(raw_data, dict) and "tagName" in raw_data:
            return True
        return isinstance(raw_data, dict) and isinstance(raw_data.get("content"), str) and "```yaml" in raw_data.get("content", "")

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        if isinstance(raw_data, dict):
            content = raw_data.get("content")
            if isinstance(content, dict):
                return self._parse_dict_element(content, path=[], depth=0)
            if isinstance(content, str):
                snapshot_tree = self._parse_snapshot_content(content)
                if snapshot_tree:
                    return snapshot_tree
            return self._parse_dict_element(raw_data, path=[], depth=0)
        return None

    def _parse_snapshot_content(self, content: str) -> Optional[UIElement]:
        yaml_match = re.search(r"```yaml\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
        if not yaml_match:
            return None

        yaml_text = yaml_match.group(1).strip()
        if not yaml_text:
            return None

        try:
            parsed = yaml.safe_load(yaml_text)
        except Exception:
            return None

        page_title_match = re.search(r"- Page Title:\s*(.+)", content)
        page_title = page_title_match.group(1).strip() if page_title_match else ""
        page_url_match = re.search(r"- Page URL:\s*(.+)", content)
        page_url = page_url_match.group(1).strip() if page_url_match else ""

        root = UIElement(
            platform="playwright",
            name=page_title,
            tag="page",
            control_type="document",
            path=[page_title] if page_title else [],
            depth=0,
            attributes={
                "page_title": page_title,
                "page_url": page_url,
                "snapshot_content": content,
            },
            action_capabilities={"click": False, "input": False},
        )

        root_children = parsed if isinstance(parsed, list) else [parsed]
        for item in root_children:
            child = self._parse_snapshot_node(item, root.path.copy(), 1)
            if child:
                root.children.append(child)
        return root

    def _parse_snapshot_node(self, item: Any, path: List[str], depth: int) -> Optional[UIElement]:
        if isinstance(item, str):
            descriptor = item.strip()
            if not descriptor:
                return None
            parsed = self._parse_snapshot_descriptor(descriptor)
            attrs = dict(parsed)
            locator_candidates = self._build_locator_candidates(
                name=parsed["name"],
                tag=parsed["tag"],
                attrs=attrs,
            )
            element_ref = locator_candidates[0] if locator_candidates else None
            return UIElement(
                platform="playwright",
                name=parsed["name"],
                tag=parsed["tag"],
                control_type=parsed["control_type"],
                automation_id=str(attrs.get("id") or ""),
                class_name=str(attrs.get("class") or attrs.get("className") or ""),
                bounds=extract_bounds(attrs),
                path=path.copy() + ([parsed["name"]] if parsed["name"] else []),
                depth=depth,
                attributes=attrs,
                element_ref=element_ref,
                locator_candidates=locator_candidates,
                action_capabilities=self._build_action_capabilities(attrs),
            )

        if isinstance(item, list):
            container = UIElement(
                platform="playwright",
                tag="group",
                control_type="group",
                path=path.copy(),
                depth=depth,
                action_capabilities={"click": False, "input": False},
            )
            for sub_item in item:
                child = self._parse_snapshot_node(sub_item, path.copy(), depth + 1)
                if child:
                    container.children.append(child)
            return container if container.children else None

        if not isinstance(item, dict) or not item:
            return None

        if len(item) != 1:
            return None

        descriptor, value = next(iter(item.items()))
        if not isinstance(descriptor, str):
            return None

        parsed = self._parse_snapshot_descriptor(descriptor)
        attrs = dict(parsed)
        locator_candidates = self._build_locator_candidates(
            name=parsed["name"],
            tag=parsed["tag"],
            attrs=attrs,
        )
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="playwright",
            name=parsed["name"],
            tag=parsed["tag"],
            control_type=parsed["control_type"],
            automation_id=str(attrs.get("id") or ""),
            class_name=str(attrs.get("class") or attrs.get("className") or ""),
            bounds=extract_bounds(attrs),
            path=path.copy() + ([parsed["name"]] if parsed["name"] else []),
            depth=depth,
            attributes=attrs,
            element_ref=element_ref,
            locator_candidates=locator_candidates,
            action_capabilities=self._build_action_capabilities(attrs),
        )

        child_items = value if isinstance(value, list) else ([value] if value is not None else [])
        for child_item in child_items:
            metadata = self._parse_snapshot_metadata(child_item)
            if metadata is not None:
                element.attributes.update(metadata)
                continue
            child = self._parse_snapshot_node(child_item, element.path.copy(), depth + 1)
            if child:
                element.children.append(child)

        return element

    @staticmethod
    def _parse_snapshot_descriptor(descriptor: str) -> Dict[str, Any]:
        text = descriptor.strip()
        quoted_match = re.search(r'"([^"]+)"', text)
        if not quoted_match:
            quoted_match = re.search(r"'([^']+)'", text)
        name = quoted_match.group(1).strip() if quoted_match else ""

        tag_match = re.match(r"^([^\s\[]+)", text)
        tag = tag_match.group(1).strip() if tag_match else "node"

        if not name:
            remainder = text[len(tag):].strip()
            remainder = re.sub(r"\[[^\]]+\]", " ", remainder).strip()
            remainder = remainder.strip('"').strip("'").strip()
            if remainder:
                name = remainder

        attrs: Dict[str, Any] = {
            "tag": tag,
            "tagName": tag,
            "role": tag,
        }
        if name:
            attrs["text"] = name
            attrs["name"] = name
            if tag in {"textbox", "searchbox", "combobox"} and "aria-label" not in attrs:
                attrs["aria-label"] = name

        for bracket_content in re.findall(r"\[([^\]]+)\]", text):
            content = bracket_content.strip()
            if "=" in content:
                key, raw_value = content.split("=", 1)
                attrs[key.strip()] = raw_value.strip().strip('"').strip("'")
            else:
                attrs[content] = True

        return {
            "tag": tag,
            "name": name,
            "control_type": tag,
            **attrs,
        }

    @staticmethod
    def _parse_snapshot_metadata(item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict) or len(item) != 1:
            return None

        key, value = next(iter(item.items()))
        if not isinstance(key, str):
            return None

        if key.startswith("/"):
            return {key[1:]: value}
        if key == "text":
            return {"text": value}
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
            "input": any(keyword in searchable for keyword in ["input", "textarea", "textbox", "searchbox", "combobox"]),
        }
