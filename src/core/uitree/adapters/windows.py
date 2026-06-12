"""
Windows / WinApp UI Tree 适配器
"""
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from common.logger import logger

from ..models import ElementRef, UIElement
from ..normalize import extract_bounds
from .base import BaseUITreeAdapter


class WindowsUITreeAdapter(BaseUITreeAdapter):
    """Windows MCP 设备 UI 树适配器"""

    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        if device_type and ("windows" in device_type.lower() or "winapp" in device_type.lower()):
            return True
        if isinstance(raw_data, dict) and any(k in raw_data for k in ["content", "xml", "value", "source"]):
            return True
        if isinstance(raw_data, str) and raw_data.strip().startswith("<"):
            return True
        return False

    def parse(self, raw_data: Any) -> Optional[UIElement]:
        payload = self._extract_payload(raw_data)
        if not payload:
            return None

        if isinstance(payload, str) and payload.strip().startswith("<"):
            try:
                root = ET.fromstring(payload.strip())
                return self._parse_xml_element(root, path=[], depth=0)
            except Exception as exc:
                logger.debug(f"Windows UI 树 XML 解析失败: {exc}")

        if isinstance(payload, dict):
            return self._parse_dict_element(payload, path=[], depth=0)

        return None

    def _extract_payload(self, raw_data: Any) -> Any:
        if isinstance(raw_data, dict):
            for key in ["content", "xml", "value", "source", "pageSource", "page_source"]:
                if key in raw_data and raw_data[key]:
                    return self._extract_payload(raw_data[key])

        if isinstance(raw_data, list) and raw_data:
            return raw_data

        if isinstance(raw_data, str):
            text = raw_data.strip().lstrip("\ufeff")
            if not text:
                return None
            if text.startswith("{") or text.startswith("["):
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and "value" in payload and payload["value"]:
                        return self._extract_payload(payload["value"])
                    return payload
                except Exception:
                    return text
            return text

        return raw_data

    def _parse_xml_element(self, elem: ET.Element, path: List[str], depth: int) -> UIElement:
        attrs = dict(elem.attrib)
        name = (attrs.get("Name") or attrs.get("name") or attrs.get("label") or attrs.get("text") or "").strip()
        automation_id = attrs.get("AutomationId") or attrs.get("automationId") or attrs.get("resource-id") or attrs.get("id") or ""
        class_name = attrs.get("ClassName") or attrs.get("class") or attrs.get("className") or ""
        locator_candidates = self._build_locator_candidates(
            name=name,
            automation_id=automation_id,
            class_name=class_name,
            control_type=attrs.get("LocalizedControlType") or attrs.get("controlType") or attrs.get("role") or elem.tag,
        )
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="windows",
            name=name,
            tag=elem.tag,
            control_type=attrs.get("LocalizedControlType") or attrs.get("controlType") or attrs.get("role") or elem.tag,
            automation_id=automation_id,
            class_name=class_name,
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
            element_ref=element_ref,
            locator_candidates=locator_candidates,
            action_capabilities=self._build_action_capabilities(attrs, elem.tag),
        )

        if name:
            element.path.append(name)

        for child_elem in elem:
            child = self._parse_xml_element(child_elem, element.path.copy(), depth + 1)
            element.children.append(child)

        return element

    def _parse_dict_element(self, data: Dict[str, Any], path: List[str], depth: int) -> UIElement:
        attrs = dict(data)
        name = (attrs.get("Name") or attrs.get("name") or attrs.get("label") or attrs.get("text") or "").strip()
        automation_id = attrs.get("AutomationId") or attrs.get("resource-id") or attrs.get("id") or ""
        class_name = attrs.get("ClassName") or attrs.get("class") or attrs.get("className") or ""
        control_type = attrs.get("LocalizedControlType") or attrs.get("controlType") or attrs.get("role") or ""
        locator_candidates = self._build_locator_candidates(
            name=name,
            automation_id=automation_id,
            class_name=class_name,
            control_type=control_type,
        )
        element_ref = locator_candidates[0] if locator_candidates else None

        element = UIElement(
            platform="windows",
            name=name,
            tag=attrs.get("tag") or attrs.get("tagName") or attrs.get("type") or attrs.get("role") or "node",
            control_type=control_type,
            automation_id=automation_id,
            class_name=class_name,
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
            element_ref=element_ref,
            locator_candidates=locator_candidates,
            action_capabilities=self._build_action_capabilities(attrs, control_type),
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
                platform="windows",
                selector_type=selector_type,
                selector_value=value,
                extra=extra,
            )
        )

    def _build_locator_candidates(
        self,
        *,
        name: str,
        automation_id: str,
        class_name: str,
        control_type: str,
    ) -> List[ElementRef]:
        candidates: List[ElementRef] = []
        self._append_candidate(candidates, "accessibility id", automation_id)
        self._append_candidate(candidates, "name", name)
        if name and control_type:
            xpath = f"//*[@Name='{name}' and contains(@LocalizedControlType, '{control_type}')]"
            self._append_candidate(candidates, "xpath", xpath)
        elif name:
            self._append_candidate(candidates, "xpath", f"//*[@Name='{name}']")
        if class_name and name:
            xpath = f"//*[@ClassName='{class_name}' and @Name='{name}']"
            self._append_candidate(candidates, "xpath", xpath)
        return candidates

    @staticmethod
    def _build_action_capabilities(attrs: Dict[str, Any], tag_or_type: str) -> Dict[str, bool]:
        searchable = " ".join(
            str(value).lower()
            for value in [tag_or_type, attrs.get("LocalizedControlType"), attrs.get("controlType"), attrs.get("IsEnabled")]
            if value is not None
        )
        input_like = any(keyword in searchable for keyword in ["edit", "textbox", "text box", "输入", "编辑"])
        return {
            "click": True,
            "input": input_like,
        }
