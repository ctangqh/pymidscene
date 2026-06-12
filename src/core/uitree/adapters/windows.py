"""
Windows / WinApp UI Tree 适配器
"""
import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from common.logger import logger

from ..models import UIElement
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

        element = UIElement(
            name=name,
            tag=elem.tag,
            control_type=attrs.get("LocalizedControlType") or attrs.get("controlType") or attrs.get("role") or elem.tag,
            automation_id=attrs.get("AutomationId") or attrs.get("automationId") or attrs.get("resource-id") or attrs.get("id") or "",
            class_name=attrs.get("ClassName") or attrs.get("class") or attrs.get("className") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
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

        element = UIElement(
            name=name,
            tag=attrs.get("tag") or attrs.get("tagName") or attrs.get("type") or attrs.get("role") or "node",
            control_type=attrs.get("LocalizedControlType") or attrs.get("controlType") or attrs.get("role") or "",
            automation_id=attrs.get("AutomationId") or attrs.get("resource-id") or attrs.get("id") or "",
            class_name=attrs.get("ClassName") or attrs.get("class") or attrs.get("className") or "",
            bounds=extract_bounds(attrs),
            path=path.copy(),
            depth=depth,
            attributes=attrs,
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
