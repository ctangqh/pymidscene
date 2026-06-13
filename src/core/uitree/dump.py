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
from .normalize import extract_jsonable_payload, flatten_tree

UITREE_SCHEMA_VERSION = "1.0.0"
SCREENSHOT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
RECENT_SCREENSHOT_WINDOW_SECONDS = 30.0


def _build_execution_notes(element_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ref = element_ref or {}
    return {
        "ref_kind": ref.get("ref_kind"),
        "actionable": ref.get("actionable"),
        "persistable": ref.get("persistable"),
        "requires_resolution": ref.get("requires_resolution"),
        "resolved": ref.get("resolved"),
    }


def _resolve_save_dir(save_dir: Optional[Path] = None) -> Path:
    target_dir = save_dir or settings.report_screenshot_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def build_debug_prefix(element_description: str) -> str:
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", element_description).strip("_") or "element"
    timestamp = int(time.time() * 1000)
    return f"{timestamp}_{safe_name}"


def _normalize_prefix(prefix: str) -> str:
    return Path(prefix).stem or prefix


def _find_recent_screenshot_stem(target_dir: Path) -> Optional[str]:
    try:
        now = time.time()
        candidates = [
            path
            for path in target_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SCREENSHOT_SUFFIXES
        ]
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            if now - path.stat().st_mtime <= RECENT_SCREENSHOT_WINDOW_SECONDS:
                return path.stem
    except Exception:
        return None
    return None


def resolve_artifact_basename(
    element_description: str,
    target_dir: Path,
    prefix: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> str:
    if screenshot_path:
        return screenshot_path.stem

    if prefix:
        return _normalize_prefix(prefix)

    recent_screenshot_stem = _find_recent_screenshot_stem(target_dir)
    if recent_screenshot_stem:
        return recent_screenshot_stem

    return build_debug_prefix(element_description)


def _build_artifact_filename(base_name: str, *, variant: str) -> str:
    if variant == "parsed":
        return f"{base_name}.json"
    if variant == "raw":
        return f"{base_name}_raw.json"
    raise ValueError(f"Unknown artifact variant: {variant}")


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
    device_type: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> Optional[Path]:
    """保存原始 UI 树"""
    target_dir = _resolve_save_dir(save_dir)
    base_name = resolve_artifact_basename(
        element_description,
        target_dir,
        prefix=prefix,
        screenshot_path=screenshot_path,
    )
    filepath = target_dir / _build_artifact_filename(base_name, variant="raw")

    try:
        normalized_payload = extract_jsonable_payload(raw_data)
        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "schema_version": UITREE_SCHEMA_VERSION,
                    "description": element_description,
                    "device_type": device_type,
                    "source_data_type": type(raw_data).__name__,
                    "payload": normalized_payload,
                },
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
    device_type: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> Optional[Path]:
    """保存解析后的平铺 UI 树"""
    target_dir = _resolve_save_dir(save_dir)
    base_name = resolve_artifact_basename(
        element_description,
        target_dir,
        prefix=prefix,
        screenshot_path=screenshot_path,
    )
    filepath = target_dir / _build_artifact_filename(base_name, variant="parsed")

    try:
        flat_list = flatten_tree(tree)
        simplified_list = []
        for elem in flat_list:
            serialized_ref = elem.element_ref.to_dict() if elem.element_ref else None
            simplified_list.append(
                {
                    "platform": elem.platform,
                    "name": elem.name,
                    "tag": elem.tag,
                    "control_type": elem.control_type,
                    "automation_id": elem.automation_id,
                    "class_name": elem.class_name,
                    "path": elem.path,
                    "depth": elem.depth,
                    "bounds": elem.bounds,
                    "element_ref": serialized_ref,
                    "preferred_action_ref": serialized_ref,
                    "locator_candidates": [candidate.to_dict() for candidate in elem.locator_candidates],
                    "action_capabilities": elem.action_capabilities,
                    "execution_notes": _build_execution_notes(serialized_ref),
                }
            )

        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "schema_version": UITREE_SCHEMA_VERSION,
                    "description": element_description,
                    "device_type": device_type,
                    "nodes_count": len(simplified_list),
                    "tree": tree.to_dict(),
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
    device_type: Optional[str] = None,
    screenshot_path: Optional[Path] = None,
) -> Dict[str, Optional[Path]]:
    """保存原始与解析后 UI 树"""
    result = {"raw": None, "parsed": None}
    result["raw"] = dump_raw_tree(
        raw_data,
        element_description,
        save_dir,
        prefix=prefix,
        device_type=device_type,
        screenshot_path=screenshot_path,
    )
    if tree:
        result["parsed"] = dump_parsed_tree(
            tree,
            element_description,
            save_dir,
            prefix=prefix,
            device_type=device_type,
            screenshot_path=screenshot_path,
        )
    return result
