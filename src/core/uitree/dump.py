"""
UITree 调试落盘能力
"""
import json
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from common.config import settings
from common.logger import logger

from .models import UIElement
from .normalize import flatten_tree


def _resolve_save_dir(save_dir: Optional[Path] = None) -> Path:
    target_dir = save_dir or Path(settings.REPORT_SCREENSHOT_SAVE_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def build_debug_prefix(element_description: str) -> str:
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", element_description).strip("_") or "element"
    timestamp = int(time.time() * 1000)
    return f"{timestamp}_{safe_name}"


def _build_debug_filename(element_description: str, suffix: str, prefix: Optional[str] = None) -> str:
    filename_prefix = prefix or build_debug_prefix(element_description)
    return f"{filename_prefix}_{suffix}.json"


def _json_default_serializer(value: Any):
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return repr(value)


def dump_raw_tree(
    raw_data: Any,
    element_description: str,
    save_dir: Optional[Path] = None,
    prefix: Optional[str] = None,
) -> Optional[Path]:
    """保存原始 UI 树"""
    target_dir = _resolve_save_dir(save_dir)
    filepath = target_dir / _build_debug_filename(element_description, "uitree_debug", prefix=prefix)

    try:
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(
                raw_data,
                file,
                ensure_ascii=False,
                indent=2,
                default=_json_default_serializer,
            )

        logger.info(f"Raw UI tree saved: {filepath}")
        return filepath
    except Exception as exc:
        logger.error(f"保存 UI 树失败: {exc}")
        traceback.print_exc()
        return None


def dump_parsed_tree(
    tree: UIElement,
    element_description: str,
    save_dir: Optional[Path] = None,
    prefix: Optional[str] = None,
) -> Optional[Path]:
    """保存解析后的平铺 UI 树"""
    target_dir = _resolve_save_dir(save_dir)
    filepath = target_dir / _build_debug_filename(
        element_description,
        "uitree_parsed_debug",
        prefix=prefix,
    )

    try:
        flat_list = flatten_tree(tree)
        simplified_list = []
        for elem in flat_list:
            simplified_list.append(
                {
                    "name": elem.name,
                    "tag": elem.tag,
                    "control_type": elem.control_type,
                    "automation_id": elem.automation_id,
                    "class_name": elem.class_name,
                    "path": elem.path,
                    "depth": elem.depth,
                    "bounds": elem.bounds,
                }
            )

        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "description": element_description,
                    "nodes_count": len(simplified_list),
                    "nodes": simplified_list,
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

        logger.info(f"Parsed UI tree saved: {filepath}")
        return filepath
    except Exception as exc:
        logger.error(f"保存解析后 UI 树失败: {exc}")
        traceback.print_exc()
        return None


def dump_tree_bundle(
    raw_data: Any,
    element_description: str,
    save_dir: Optional[Path] = None,
    tree: Optional[UIElement] = None,
    prefix: Optional[str] = None,
) -> Dict[str, Optional[Path]]:
    """保存原始与解析后 UI 树"""
    result = {"raw": None, "parsed": None}
    result["raw"] = dump_raw_tree(raw_data, element_description, save_dir, prefix=prefix)
    if tree:
        result["parsed"] = dump_parsed_tree(tree, element_description, save_dir, prefix=prefix)
    return result
