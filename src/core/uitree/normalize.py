"""
UITree 通用标准化函数
"""
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from .models import Bounds, UIElement

COMMON_PAYLOAD_KEYS = ["content", "xml", "value", "source", "pageSource", "page_source"]


def try_get_float(attrs: Dict[str, Any], keys: List[str]) -> Optional[float]:
    """尝试从多个键中读取浮点值"""
    for key in keys:
        if key not in attrs:
            continue

        value = attrs[key]
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def extract_bounds(attrs: Dict[str, Any]) -> Optional[Bounds]:
    """从属性中提取统一边界框，格式为 left/top/width/height"""
    left = try_get_float(attrs, ["left", "x"])
    top = try_get_float(attrs, ["top", "y"])
    width = try_get_float(attrs, ["width", "w"])
    height = try_get_float(attrs, ["height", "h"])

    if left is not None and top is not None and width is not None and height is not None:
        return (left, top, width, height)

    bounds_str = attrs.get("bounds", attrs.get("BoundingRectangle", ""))
    if isinstance(bounds_str, str):
        match = re.match(r"\[([\d\-\.]+),([\d\-\.]+)\]\[([\d\-\.]+),([\d\-\.]+)\]", bounds_str.strip())
        if match:
            try:
                x1, y1, x2, y2 = map(float, match.groups())
                return (x1, y1, max(0, x2 - x1), max(0, y2 - y1))
            except (TypeError, ValueError):
                pass

    right = try_get_float(attrs, ["right"])
    bottom = try_get_float(attrs, ["bottom"])
    if left is not None and top is not None and right is not None and bottom is not None:
        return (left, top, max(0, right - left), max(0, bottom - top))

    rect = attrs.get("rect")
    if isinstance(rect, dict):
        return extract_bounds(rect)

    return None


def flatten_tree(tree: UIElement) -> List[UIElement]:
    """展开整棵树"""
    return tree.to_flat_list()


def xml_element_to_dict(elem: ET.Element) -> Dict[str, Any]:
    """把 XML 元素转换为 JSON 友好的 dict 结构"""
    result: Dict[str, Any] = {
        "tag": elem.tag,
        "attributes": dict(elem.attrib),
        "children": [xml_element_to_dict(child) for child in elem],
    }
    text = (elem.text or "").strip()
    if text:
        result["text"] = text
    return result


def normalize_jsonable_data(raw_data: Any) -> Any:
    """把原始 payload 归一化为 JSON 友好的数据结构"""
    if isinstance(raw_data, dict):
        return {key: normalize_jsonable_data(value) for key, value in raw_data.items()}

    if isinstance(raw_data, list):
        return [normalize_jsonable_data(item) for item in raw_data]

    if isinstance(raw_data, tuple):
        return [normalize_jsonable_data(item) for item in raw_data]

    if isinstance(raw_data, str):
        text = raw_data.strip().lstrip("\ufeff")
        if not text:
            return ""

        if text.startswith("{") or text.startswith("["):
            try:
                return normalize_jsonable_data(json.loads(text))
            except Exception:
                return raw_data

        if text.startswith("<"):
            try:
                root = ET.fromstring(text)
                return xml_element_to_dict(root)
            except Exception:
                return raw_data

        return raw_data

    return raw_data


def extract_jsonable_payload(raw_data: Any) -> Any:
    """提取最接近真实树结构的 payload，并归一化为 JSON 友好结构"""
    current = raw_data
    while isinstance(current, dict):
        next_value = None
        for key in COMMON_PAYLOAD_KEYS:
            value = current.get(key)
            if value:
                next_value = value
                break
        if next_value is None:
            break
        current = next_value

    return normalize_jsonable_data(current)
