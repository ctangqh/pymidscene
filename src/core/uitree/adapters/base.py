"""
UITree 适配器基类
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..models import UIElement


class BaseUITreeAdapter(ABC):
    """设备 UI Tree 适配器基类"""

    @abstractmethod
    def can_parse(self, device_type: Optional[str], raw_data: Any) -> bool:
        """判断是否能解析当前数据"""
        raise NotImplementedError

    @abstractmethod
    def parse(self, raw_data: Any) -> Optional[UIElement]:
        """把原始数据解析为统一节点树"""
        raise NotImplementedError
