"""
UITree 统一领域模型
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

Bounds = Tuple[float, float, float, float]


@dataclass
class ElementRef:
    """跨端统一的元素引用。

    注意:
    - ref_kind="selector" 表示这是一个可用于再次查找元素的选择器引用，
      并不代表已经拿到了远端驱动里的真实元素句柄。
    - resolved=False 表示执行动作前仍需要由对应端（如远程 MCP）再次解析。
    """

    platform: str = ""
    ref_kind: str = "selector"
    source: str = "uitree_derived"
    selector_type: str = ""
    selector_value: str = ""
    actionable: bool = True
    persistable: bool = True
    requires_resolution: bool = False
    resolved: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "ref_kind": self.ref_kind,
            "source": self.source,
            "selector_type": self.selector_type,
            "selector_value": self.selector_value,
            "actionable": self.actionable,
            "persistable": self.persistable,
            "requires_resolution": self.requires_resolution,
            "resolved": self.resolved,
            "extra": self.extra,
        }


@dataclass
class UIElement:
    """统一 UI 节点"""

    platform: str = ""
    name: str = ""
    tag: str = ""
    control_type: str = ""
    automation_id: str = ""
    class_name: str = ""
    bounds: Optional[Bounds] = None  # left, top, width, height
    path: List[str] = field(default_factory=list)
    depth: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    element_ref: Optional[ElementRef] = None
    locator_candidates: List[ElementRef] = field(default_factory=list)
    action_capabilities: Dict[str, bool] = field(default_factory=dict)
    children: List["UIElement"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化"""
        return {
            "platform": self.platform,
            "name": self.name,
            "tag": self.tag,
            "control_type": self.control_type,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "bounds": self.bounds,
            "path": self.path,
            "depth": self.depth,
            "attributes": self.attributes,
            "element_ref": self.element_ref.to_dict() if self.element_ref else None,
            "locator_candidates": [candidate.to_dict() for candidate in self.locator_candidates],
            "action_capabilities": self.action_capabilities,
            "children": [child.to_dict() for child in self.children],
        }

    def to_flat_list(self) -> List["UIElement"]:
        """转换为平铺列表，包含所有子孙元素"""
        result = [self]
        for child in self.children:
            result.extend(child.to_flat_list())
        return result
