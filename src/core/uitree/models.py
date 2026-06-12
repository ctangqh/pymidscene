"""
UITree 统一领域模型
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

Bounds = Tuple[float, float, float, float]


@dataclass
class UIElement:
    """统一 UI 节点"""

    name: str = ""
    tag: str = ""
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    bounds: Optional[Bounds] = None  # left, top, width, height
    path: List[str] = field(default_factory=list)
    depth: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List["UIElement"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化"""
        return {
            "name": self.name,
            "tag": self.tag,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "bounds": self.bounds,
            "path": self.path,
            "depth": self.depth,
            "attributes": self.attributes,
            "children": [child.to_dict() for child in self.children],
        }

    def to_flat_list(self) -> List["UIElement"]:
        """转换为平铺列表，包含所有子孙元素"""
        result = [self]
        for child in self.children:
            result.extend(child.to_flat_list())
        return result
