"""
UITree 调试辅助能力
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.config import settings
from common.image import format_box_label, save_debug_screenshot
from common.logger import logger

from .dump import dump_tree_bundle
from .normalize import flatten_tree
from .service import uitree_manager


def capture_debug_tree(
    device: Any,
    element_description: str,
    raw_tree: Any = None,
    device_type: Optional[str] = None,
    save_dir: Optional[Path] = None,
    screenshot_path: Optional[Path] = None,
    prefix: Optional[str] = None,
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
        parsed_tree = uitree_manager.parse(raw_tree, resolved_device_type)
        result = dump_tree_bundle(
            raw_tree,
            element_description,
            save_dir=save_dir,
            tree=parsed_tree,
            prefix=prefix,
            device_type=resolved_device_type,
            screenshot_path=screenshot_path,
        )

        logger.info(
            f"UITree debug artifacts saved: raw={result.get('raw')}, parsed={result.get('parsed')}"
        )
        return result
    except Exception as exc:
        logger.warning(f"capture_debug_tree failed: {exc}")
        return {"raw": None, "parsed": None}


def capture_full_page_control_debug(
    device: Any,
    element_description: str,
    raw_tree: Any = None,
    device_type: Optional[str] = None,
    save_dir: Optional[Path] = None,
    prefix: Optional[str] = None,
    max_annotations: int = 80,
) -> Dict[str, Optional[Path]]:
    """
    保存整页截图，并为当前 UITree 可识别到的控件生成 bbox 标注图。

    该能力主要用于浏览器/页面定位分析，对比“整页控件几何分布”和当前 locate 结果的差异。
    不参与实际动作执行，也不会回写 locate 的 bbox。
    """
    if not settings.DEBUG:
        return {"raw": None, "annotated": None, "summary": None}

    if raw_tree is None and device is None:
        return {"raw": None, "annotated": None, "summary": None}

    try:
        if raw_tree is None:
            raw_tree = device.get_dom_tree()
        if raw_tree is None:
            return {"raw": None, "annotated": None, "summary": None}

        resolved_device_type = device_type or getattr(device, "interface_type", None)
        tree = uitree_manager.parse(raw_tree, resolved_device_type)
        if not tree:
            return {"raw": None, "annotated": None, "summary": None}

        screenshot_b64 = device.screenshot_base64()
        if not screenshot_b64:
            return {"raw": None, "annotated": None, "summary": None}

        nodes = flatten_tree(tree)
        annotations = _build_full_page_annotations(
            device,
            nodes,
            device_type=resolved_device_type,
            max_annotations=max_annotations,
        )
        safe_prefix = prefix or "page_controls"
        paths = save_debug_screenshot(
            screenshot_b64,
            safe_prefix,
            annotations=annotations,
            save_raw=True,
            save_dir=save_dir,
        )

        summary_path = None
        if annotations and paths.get("raw"):
            summary_path = paths["raw"].with_name(paths["raw"].stem.replace("_raw", "_controls") + ".json")
            summary_payload = {
                "description": element_description,
                "device_type": resolved_device_type,
                "annotations": annotations,
            }
            summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            f"UITree full-page control debug saved: raw={paths.get('raw')}, annotated={paths.get('annotated')}, summary={summary_path}"
        )
        return {"raw": paths.get("raw"), "annotated": paths.get("annotated"), "summary": summary_path}
    except Exception as exc:
        logger.warning(f"capture_full_page_control_debug failed: {exc}")
        return {"raw": None, "annotated": None, "summary": None}


def _build_full_page_annotations(
    device: Any,
    nodes: List[Any],
    *,
    device_type: Optional[str] = None,
    max_annotations: int = 80,
) -> List[Dict[str, Any]]:
    annotations: List[Dict[str, Any]] = []
    browser_nodes: List[Dict[str, Any]] = []

    for index, node in enumerate(nodes):
        rect = _node_rect(node)
        label = _node_label(node, rect)
        if rect:
            annotations.append({"rect": rect, "label": label})
            continue
        if (device_type or "").lower() in ("browser", "web", "playwright"):
            candidates = _node_candidates(node)
            if candidates:
                browser_nodes.append(
                    {
                        "index": index,
                        "name": (getattr(node, "name", None) or "").strip(),
                        "el_type": (
                            getattr(node, "control_type", None)
                            or getattr(node, "tag", None)
                            or "element"
                        ),
                        "candidates": candidates,
                    }
                )

    if browser_nodes and getattr(device, "evaluate_script", None):
        browser_rects = _resolve_browser_node_rects(device, browser_nodes)
        annotations.extend(browser_rects)

    return annotations[:max_annotations]


def _node_rect(node: Any) -> Optional[Dict[str, float]]:
    bounds = getattr(node, "bounds", None)
    if not bounds:
        return None
    left, top, width, height = bounds
    return {
        "left": float(left),
        "top": float(top),
        "width": float(width),
        "height": float(height),
    }


def _node_label(node: Any, rect_override: Optional[Dict[str, float]] = None) -> str:
    name = (getattr(node, "name", None) or "").strip()
    el_type = (
        getattr(node, "control_type", None)
        or getattr(node, "tag", None)
        or "element"
    )
    rect = rect_override or _node_rect(node) or {"left": 0, "top": 0, "width": 0, "height": 0}
    label = format_box_label(rect, str(el_type))
    if name:
        return f"{name}\n{label}"
    return label


def _node_candidates(node: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    primary = getattr(node, "element_ref", None)
    if primary and hasattr(primary, "to_dict"):
        candidates.append(primary.to_dict())
    elif isinstance(primary, dict):
        candidates.append(dict(primary))

    for item in getattr(node, "locator_candidates", None) or []:
        if hasattr(item, "to_dict"):
            candidates.append(item.to_dict())
        elif isinstance(item, dict):
            candidates.append(dict(item))

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        selector_type = (candidate.get("selector_type") or "").strip().lower()
        selector_value = candidate.get("selector_value") or ""
        if selector_type not in {"css", "role", "text"} or not selector_value:
            continue
        key = (selector_type, selector_value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(candidate)
    return normalized


def _resolve_browser_node_rects(device: Any, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    metadata_by_index = {
        int(entry.get("index", -1)): {
            "name": (entry.get("name") or "").strip(),
            "el_type": entry.get("el_type") or "element",
        }
        for entry in entries
        if isinstance(entry, dict)
    }
    script = f"""
() => {{
  const entries = {json.dumps(entries, ensure_ascii=False)};
  const normalize = (value) => (value ?? '').toString().trim().toLowerCase();
  const isVisible = (el) => {{
    if (!el || typeof el.getBoundingClientRect !== 'function') return false;
    const rect = el.getBoundingClientRect();
    return !!rect && rect.width > 0 && rect.height > 0;
  }};
  const scoreNode = (el, candidate) => {{
    if (!isVisible(el)) return -1;
    const selectorType = normalize(candidate.selector_type);
    const selectorValue = candidate.selector_value || '';
    const extra = candidate.extra || {{}};
    const nameNeedle = normalize(extra.name || selectorValue.replace(/^text=/i, ''));
    const roleNeedle = normalize(extra.role || '');
    const tagNeedle = normalize(extra.tag || '');
    const tag = normalize(el.tagName);
    const role = normalize(el.getAttribute && el.getAttribute('role'));
    const ariaLabel = normalize(el.getAttribute && el.getAttribute('aria-label'));
    const placeholder = normalize(el.getAttribute && el.getAttribute('placeholder'));
    const textValue = normalize(el.innerText || el.textContent || el.value || '');
    let score = 0;
    if (selectorType === 'css') score += 10;
    if (roleNeedle && role === roleNeedle) score += 8;
    if (tagNeedle && tag === tagNeedle) score += 4;
    if (nameNeedle && ariaLabel === nameNeedle) score += 10;
    if (nameNeedle && placeholder === nameNeedle) score += 8;
    if (nameNeedle && textValue === nameNeedle) score += 7;
    if (nameNeedle && ariaLabel.includes(nameNeedle)) score += 5;
    if (nameNeedle && placeholder.includes(nameNeedle)) score += 4;
    if (nameNeedle && textValue.includes(nameNeedle)) score += 3;
    return score;
  }};
  const findCandidateNode = (candidate) => {{
    const selectorType = normalize(candidate.selector_type);
    const selectorValue = candidate.selector_value || '';
    const extra = candidate.extra || {{}};
    if (selectorType === 'css') {{
      try {{
        const node = document.querySelector(selectorValue);
        return isVisible(node) ? node : null;
      }} catch (_error) {{
        return null;
      }}
    }}
    let selectors = [];
    if (selectorType === 'role' && extra.role) {{
      selectors.push(`[role="${{extra.role}}"]`);
    }}
    selectors.push('input, textarea, button, a, [role], [aria-label], [placeholder]');
    const visited = new Set();
    let best = null;
    let bestScore = -1;
    for (const selector of selectors) {{
      let nodes = [];
      try {{
        nodes = Array.from(document.querySelectorAll(selector));
      }} catch (_error) {{
        continue;
      }}
      for (const node of nodes) {{
        if (visited.has(node)) continue;
        visited.add(node);
        const score = scoreNode(node, candidate);
        if (score > bestScore) {{
          best = node;
          bestScore = score;
        }}
      }}
    }}
    return bestScore >= 0 ? best : null;
  }};

  return entries.map((entry) => {{
    for (const candidate of entry.candidates || []) {{
      const node = findCandidateNode(candidate);
      if (!node) continue;
      const rect = node.getBoundingClientRect();
      return {{
        index: entry.index,
        label: entry.label,
        rect: {{
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height
        }}
      }};
    }}
    return null;
  }}).filter(Boolean);
}}
""".strip()
    payload = device.evaluate_script(script)
    if not isinstance(payload, list):
        return []

    annotations: List[Dict[str, Any]] = []
    for item in payload:
        rect = item.get("rect") if isinstance(item, dict) else None
        if not isinstance(rect, dict):
            continue
        meta = metadata_by_index.get(int(item.get("index", -1))) if isinstance(item, dict) else None
        el_type = str((meta or {}).get("el_type") or "element")
        name = str((meta or {}).get("name") or "").strip()
        label = format_box_label(rect, el_type)
        annotations.append(
            {
                "rect": rect,
                "label": f"{name}\n{label}" if name else label,
            }
        )
    return annotations
