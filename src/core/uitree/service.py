"""
UITree 服务入口
"""
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional

from common.logger import logger

from .adapters import BaseUITreeAdapter
from .dump import dump_parsed_tree, dump_raw_tree
from .models import ElementRef, UIElement
from .normalize import flatten_tree
from .registry import DEFAULT_ADAPTERS, iter_matching_adapters


class UITreeManager:
    """UI 树统一入口"""

    TOKEN_SYNONYMS: Dict[str, List[str]] = {
        "搜索": ["search"],
        "搜索框": ["search", "search box", "search field", "searchbar"],
        "搜索输入框": ["search", "search input", "search box", "search field", "searchbar", "combobox"],
        "输入": ["input", "type"],
        "输入框": ["input", "textbox", "text box", "text field", "searchbox", "combobox"],
        "按钮": ["button"],
        "搜索按钮": ["search", "search button", "button", "google search"],
        "点击": ["click", "tap"],
    }

    REMOTE_EXECUTION_CAPABILITY: Dict[str, Dict[str, Dict[str, Any]]] = {
        "windows": {
            "accessibility id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 100,
            },
            "name": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 60,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 40,
            },
        },
        "playwright": {
            "playwright-ref": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": False,
                "resolved": False,
                "stability": 100,
            },
            "selector": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 85,
            },
            "css": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 90,
            },
            "role": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 80,
            },
            "text": {
                "supported_actions": ["tap"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 50,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 45,
            },
        },
        "ios": {
            "identifier": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 100,
            },
            "name": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 75,
            },
            "label": {
                "supported_actions": ["tap"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 60,
            },
            "predicate": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 65,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 40,
            },
        },
        "hypium": {
            "resource-id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 100,
            },
            "accessibility-id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 85,
            },
            "text": {
                "supported_actions": ["tap"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 55,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 45,
            },
        },
        "android": {
            "resource-id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 100,
            },
            "accessibility-id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 85,
            },
            "text": {
                "supported_actions": ["tap"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 55,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": True,
                "persistable": True,
                "resolved": False,
                "stability": 45,
            },
        },
        "generic": {
            "selector": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 70,
            },
            "id": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 80,
            },
            "identifier": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 80,
            },
            "name": {
                "supported_actions": ["tap"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 50,
            },
            "text": {
                "supported_actions": ["tap"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 45,
            },
            "label": {
                "supported_actions": ["tap"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 45,
            },
            "xpath": {
                "supported_actions": ["tap", "input"],
                "requires_resolution": False,
                "persistable": True,
                "resolved": False,
                "stability": 35,
            },
        },
    }

    CANDIDATE_PRIORITY: Dict[str, Dict[str, List[str]]] = {
        "windows": {
            "tap": ["accessibility id", "name", "xpath"],
            "input": ["accessibility id", "name", "xpath"],
        },
        "playwright": {
            "tap": ["playwright-ref", "css", "role", "selector", "text", "xpath"],
            "input": ["css", "role", "selector", "playwright-ref", "xpath", "text"],
        },
        "ios": {
            "tap": ["identifier", "name", "label", "predicate", "xpath"],
            "input": ["identifier", "name", "predicate", "label", "xpath"],
        },
        "hypium": {
            "tap": ["resource-id", "accessibility-id", "text", "xpath"],
            "input": ["resource-id", "accessibility-id", "xpath", "text"],
        },
        "android": {
            "tap": ["resource-id", "accessibility-id", "text", "xpath"],
            "input": ["resource-id", "accessibility-id", "xpath", "text"],
        },
        "generic": {
            "tap": ["selector", "id", "identifier", "name", "text", "label", "xpath"],
            "input": ["selector", "id", "identifier", "name", "label", "text", "xpath"],
        },
    }

    def __init__(self, adapters: Optional[Iterable[BaseUITreeAdapter]] = None):
        self.adapters = list(adapters or DEFAULT_ADAPTERS)

    def parse(self, raw_data: Any, device_type: Optional[str] = None) -> Optional[UIElement]:
        """解析原始数据为 UIElement 树"""
        for adapter in iter_matching_adapters(raw_data, device_type, self.adapters):
            try:
                logger.debug(f"尝试使用 UITree 适配器: {adapter.__class__.__name__}")
                tree = adapter.parse(raw_data)
                if tree:
                    self._apply_preferred_candidates(tree, device_type)
                    return tree
            except Exception as exc:
                logger.debug(f"UITree 适配器解析失败: {adapter.__class__.__name__}: {exc}")
        return None

    def save_raw(
        self,
        raw_data: Any,
        element_description: str,
        device_type: Optional[str] = None,
        save_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """保存原始 UI 树"""
        return dump_raw_tree(raw_data, element_description, save_dir, device_type=device_type)

    def save_parsed(
        self,
        tree: UIElement,
        element_description: str,
        device_type: Optional[str] = None,
        save_dir: Optional[Path] = None,
    ) -> Optional[Path]:
        """保存解析后的 UI 树"""
        return dump_parsed_tree(tree, element_description, save_dir, device_type=device_type)

    def save(
        self,
        raw_data: Any,
        element_description: str,
        device_type: Optional[str] = None,
        save_dir: Optional[Path] = None,
    ) -> Dict[str, Optional[Path]]:
        """保存原始和解析后的 UI 树"""
        result = {"raw": None, "parsed": None}
        result["raw"] = self.save_raw(raw_data, element_description, device_type, save_dir)

        try:
            parsed_tree = self.parse(raw_data, device_type)
            if parsed_tree:
                result["parsed"] = self.save_parsed(parsed_tree, element_description, device_type, save_dir)
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
            if not node.bounds and not node.element_ref and not node.locator_candidates:
                continue
            score = self._score_node(node, description, tokens)
            if score > best_score:
                best_score = score
                best_node = node

        return best_node

    def select_best_candidate(
        self,
        candidates: Iterable[Any],
        device_type: Optional[str] = None,
        action_type: str = "tap",
        actionable_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """按平台和动作类型挑选最佳元素级候选"""
        action_key = (action_type or "tap").strip().lower()
        base_candidates: List[Dict[str, Any]] = []
        for candidate in candidates or []:
            normalized = self._normalize_candidate(candidate)
            if normalized:
                base_candidates.append(normalized)

        if not base_candidates:
            return None

        platform = self._normalize_device_type(device_type or base_candidates[0].get("platform"))
        normalized_candidates = [
            self._apply_capability_metadata(candidate, platform, action_key)
            for candidate in base_candidates
        ]

        if actionable_only:
            normalized_candidates = [
                candidate for candidate in normalized_candidates if candidate.get("actionable", False)
            ]

        if not normalized_candidates:
            return None

        priority = self.CANDIDATE_PRIORITY.get(platform, self.CANDIDATE_PRIORITY["generic"]).get(
            action_key,
            self.CANDIDATE_PRIORITY.get(platform, self.CANDIDATE_PRIORITY["generic"]).get("tap", []),
        )
        priority_index = {candidate_type: index for index, candidate_type in enumerate(priority)}

        def score(candidate: Dict[str, Any]) -> tuple:
            candidate_type = (candidate.get("selector_type") or "").strip().lower()
            stability = int(candidate.get("stability") or 0)
            return (
                0 if candidate.get("actionable", False) else 1,
                priority_index.get(candidate_type, len(priority_index) + 1),
                0 if candidate.get("persistable", True) else 1,
                0 if not candidate.get("requires_resolution", False) else 1,
                -stability,
                0 if candidate.get("selector_value") else 1,
                len(str(candidate.get("selector_value") or "")),
            )

        best = min(normalized_candidates, key=score)
        return best

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

        expanded_tokens = self._expand_tokens(tokens)
        for token in expanded_tokens:
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

        input_keywords = ["输入", "输入框", "textbox", "input", "searchbox", "搜索框", "搜索输入框"]
        input_like_tags = ["input", "textarea", "textbox", "searchbox", "combobox", "edit"]
        if any(keyword in description.lower() for keyword in [keyword.lower() for keyword in input_keywords]):
            input_like_text = f"{tag} {control_type}"
            if any(keyword in input_like_text for keyword in input_like_tags):
                score += 6.0
            elif "search" in input_like_text:
                score += 1.5

        return score

    def _expand_tokens(self, tokens: Iterable[str]) -> List[str]:
        expanded: List[str] = []
        seen = set()
        for token in tokens:
            normalized = (token or "").strip()
            if not normalized:
                continue
            for candidate in [normalized, *self.TOKEN_SYNONYMS.get(normalized, [])]:
                lowered = candidate.lower()
                if lowered and lowered not in seen:
                    seen.add(lowered)
                    expanded.append(candidate)
        return expanded

    def _apply_preferred_candidates(self, tree: UIElement, device_type: Optional[str] = None) -> None:
        platform = self._normalize_device_type(device_type or tree.platform)
        for node in flatten_tree(tree):
            node_platform = self._normalize_device_type(node.platform or platform)
            preferred = self.select_best_candidate(
                node.locator_candidates,
                device_type=node_platform,
                action_type="tap",
                actionable_only=True,
            )
            if not preferred:
                preferred = self.select_best_candidate(
                    node.locator_candidates,
                    device_type=node_platform,
                    action_type="tap",
                    actionable_only=False,
                )
            if preferred:
                node.element_ref = ElementRef(
                    platform=preferred.get("platform") or node_platform,
                    ref_kind=preferred.get("ref_kind") or "selector",
                    source=preferred.get("source") or "uitree_derived",
                    selector_type=preferred.get("selector_type") or "",
                    selector_value=preferred.get("selector_value") or "",
                    actionable=preferred.get("actionable", False),
                    persistable=preferred.get("persistable", True),
                    requires_resolution=preferred.get("requires_resolution", False),
                    resolved=preferred.get("resolved", False),
                    extra=dict(preferred.get("extra") or {}),
                )

    @staticmethod
    def _normalize_candidate(candidate: Any) -> Optional[Dict[str, Any]]:
        if hasattr(candidate, "to_dict"):
            candidate = candidate.to_dict()
        elif isinstance(candidate, dict):
            candidate = dict(candidate)
        else:
            return None

        selector_value = candidate.get("selector_value")
        if not selector_value:
            return None
        candidate.setdefault("ref_kind", "selector")
        candidate.setdefault("source", "uitree_derived")
        candidate.setdefault("actionable", False)
        candidate.setdefault("persistable", True)
        candidate.setdefault("requires_resolution", False)
        candidate.setdefault("resolved", False)
        return candidate

    def _apply_capability_metadata(
        self,
        candidate: Dict[str, Any],
        platform: str,
        action_type: str,
    ) -> Dict[str, Any]:
        enriched = dict(candidate)
        selector_type = (enriched.get("selector_type") or "").strip().lower()
        capability = self.REMOTE_EXECUTION_CAPABILITY.get(platform, self.REMOTE_EXECUTION_CAPABILITY["generic"]).get(
            selector_type
        )
        if capability is None and platform != "generic":
            capability = self.REMOTE_EXECUTION_CAPABILITY["generic"].get(selector_type)

        supported_actions = list(capability.get("supported_actions", [])) if capability else []
        actionable = bool(capability and action_type in supported_actions)
        enriched["actionable"] = actionable
        enriched["persistable"] = capability.get("persistable", True) if capability else enriched.get("persistable", True)
        enriched["requires_resolution"] = (
            capability.get("requires_resolution", False)
            if capability
            else enriched.get("requires_resolution", False)
        )
        enriched["resolved"] = capability.get("resolved", False) if capability else enriched.get("resolved", False)
        enriched["supported_actions"] = supported_actions
        enriched["stability"] = capability.get("stability", 0) if capability else 0
        return enriched

    @staticmethod
    def _normalize_device_type(device_type: Optional[str]) -> str:
        value = (device_type or "generic").strip().lower()
        mapping = {
            "browser": "playwright",
            "web": "playwright",
            "windows": "windows",
            "winapp": "windows",
            "ios": "ios",
            "android": "android",
            "hypium": "hypium",
        }
        return mapping.get(value, value or "generic")


uitree_manager = UITreeManager()
