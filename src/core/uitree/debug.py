"""
UITree 调试辅助能力
"""
from pathlib import Path
from typing import Any, Dict, Optional

from common.config import settings
from common.logger import logger

from .dump import build_debug_prefix, dump_tree_bundle
from .service import uitree_manager


def capture_debug_tree(
    device: Any,
    element_description: str,
    raw_tree: Any = None,
    device_type: Optional[str] = None,
    save_dir: Optional[Path] = None,
) -> Dict[str, Optional[Path]]:
    """
    在 debug 模式下抓取并保存 UI tree。

    该函数面向 agent/locator 调试链路使用，失败时不抛出异常。
    """
    if not settings.DEBUG:
        return {"raw": None, "parsed": None}

    if raw_tree is None and device is None:
        return {"raw": None, "parsed": None}

    try:
        if raw_tree is None:
            raw_tree = device.get_dom_tree()

        if raw_tree is None:
            logger.warning("capture_debug_tree skipped: device.get_dom_tree() returned empty data")
            return {"raw": None, "parsed": None}

        resolved_device_type = device_type or getattr(device, "interface_type", None)
        prefix = build_debug_prefix(element_description)
        parsed_tree = uitree_manager.parse(raw_tree, resolved_device_type)
        result = dump_tree_bundle(
            raw_tree,
            element_description,
            save_dir=save_dir,
            tree=parsed_tree,
            prefix=prefix,
            device_type=resolved_device_type,
        )

        logger.info(
            f"UITree debug artifacts saved: raw={result.get('raw')}, parsed={result.get('parsed')}"
        )
        return result
    except Exception as exc:
        logger.warning(f"capture_debug_tree failed: {exc}")
        return {"raw": None, "parsed": None}
