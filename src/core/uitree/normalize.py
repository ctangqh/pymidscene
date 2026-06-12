"""
UITree 通用标准化函数
"""
import re
from typing import Any, Dict, List, Optional

from .models import Bounds, UIElement


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
