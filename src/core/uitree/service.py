"""
UITree 服务入口
"""
from pathlib import Path
import re
from typing import Any, Dict, Iterable, Optional

from common.logger import logger

from .adapters import BaseUITreeAdapter
from .dump import dump_parsed_tree, dump_raw_tree
from .models import UIElement
from .normalize import flatten_tree
from .registry import DEFAULT_ADAPTERS, iter_matching_adapters


class UITreeManager:
    """UI 树统一入口"""

    def __init__(self, adapters: Optional[Iterable[BaseUITreeAdapter]] = None):
        self.adapters = list(adapters or DEFAULT_ADAPTERS)

    def parse(self, raw_data: Any, device_type: Optional[str] = None) -> Optional[UIElement]:
        """解析原始数据为 UIElement 树"""
        for adapter in iter_matching_adapters(raw_data, device_type, self.adapters):
            try:
                logger.debug(f"尝试使用 UITree 适配器: {adapter.__class__.__name__}")
                tree = adapter.parse(raw_data)
                if tree:
                    return tree
            except Exception as exc:
                logger.debug(f"UITree 适配器解析失败: {adapter.__class__.__name__}: {exc}")
        return None

    def save_raw(
        self,
        raw_data: Any,
        element_description: str,
        save_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """保存原始 UI 树"""
        return dump_raw_tree(raw_data, element_description, save_dir)

    def save_parsed(
        self,
        tree: UIElement,
        element_description: str,
        save_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """保存解析后的 UI 树"""
        return dump_parsed_tree(tree, element_description, save_dir)

    def save(
        self,
        raw_data: Any,
        element_description: str,
        device_type: Optional[str] = None,
        save_dir: Optional[Path] = None,
    ) -> Dict[str, Optional[Path]]:
        """保存原始和解析后的 UI 树"""
        result = {"raw": None, "parsed": None}
        result["raw"] = self.save_raw(raw_data, element_description, save_dir)

        try:
            parsed_tree = self.parse(raw_data, device_type)
            if parsed_tree:
                result["parsed"] = self.save_parsed(parsed_tree, element_description, save_dir)
        except Exception as exc:
            logger.warning(f"保存解析后 UI 树失败: {exc}")

        return result

    def find_best_match(
        self,
        raw_data: Any,
        element_description: str,
        device_type: Optional[str] = None,
    ) -> Optional[UIElement]:
        """从 UI 树中找到最匹配的节点"""
        tree = self.parse(raw_data, device_type)
        if not tree:
            return None

        best_node = None
        best_score = 0.0
        description = (element_description or "").strip()
        tokens = [token for token in re.split(r"[\s,，、/]+", description) if token]

        for node in flatten_tree(tree):
            if not node.bounds:
                continue
            score = self._score_node(node, description, tokens)
            if score > best_score:
                best_score = score
                best_node = node

        return best_node

    def _score_node(self, node: UIElement, description: str, tokens) -> float:
        score = 0.0
        lowered_description = description.lower()
        name = (node.name or "").lower()
        path_text = " ".join(node.path or []).lower()
        tag = (node.tag or "").lower()
        control_type = (node.control_type or "").lower()
        class_name = (node.class_name or "").lower()
        automation_id = (node.automation_id or "").lower()
        searchable_text = " ".join(filter(None, [name, path_text, tag, control_type, class_name, automation_id]))

        if not searchable_text:
            return 0.0

        if lowered_description and lowered_description == name:
            score += 12.0
        elif lowered_description and lowered_description in searchable_text:
            score += 8.0

        for token in tokens:
            lowered_token = token.lower()
            if lowered_token == name:
                score += 6.0
            elif lowered_token in name:
                score += 4.0
            elif lowered_token in path_text:
                score += 3.0
            elif lowered_token in searchable_text:
                score += 1.5

        if any(key in description for key in ["菜单", "menu"]) and any(
            key in f"{tag} {control_type}" for key in ["menu", "菜单"]
        ):
            score += 2.5

        if any(key in description for key in ["按钮", "click", "tap"]) and any(
            key in f"{tag} {control_type}" for key in ["button", "按钮", "menuitem", "菜单项目"]
        ):
            score += 2.5

        if "文件" in description and "文件" in searchable_text:
            score += 2.0
        if "退出" in description and "退出" in searchable_text:
            score += 4.0

        return score


uitree_manager = UITreeManager()
