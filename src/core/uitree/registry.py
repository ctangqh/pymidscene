"""
UITree 适配器注册与选择
"""
from typing import Any, Iterable, List, Optional

from common.logger import logger

from .adapters import (
    BaseUITreeAdapter,
    GenericUITreeAdapter,
    HypiumUITreeAdapter,
    IOSUITreeAdapter,
    PlaywrightUITreeAdapter,
    WindowsUITreeAdapter,
)


def get_default_adapters() -> List[BaseUITreeAdapter]:
    """返回默认适配器列表，顺序即优先级"""
    return [
        WindowsUITreeAdapter(),
        PlaywrightUITreeAdapter(),
        IOSUITreeAdapter(),
        HypiumUITreeAdapter(),
        GenericUITreeAdapter(),
    ]


DEFAULT_ADAPTERS = get_default_adapters()


def iter_matching_adapters(
    raw_data: Any,
    device_type: Optional[str] = None,
    adapters: Optional[Iterable[BaseUITreeAdapter]] = None,
):
    """按顺序返回可处理当前数据的适配器"""
    candidates = list(adapters or DEFAULT_ADAPTERS)
    for adapter in candidates:
        try:
            if adapter.can_parse(device_type, raw_data):
                yield adapter
        except Exception as exc:
            logger.debug(f"UITree 适配器 can_parse 失败: {adapter.__class__.__name__}: {exc}")
