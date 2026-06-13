#!/usr/bin/env python3
"""
Hypium helper invoked by the Go MCP server.

Each invocation handles one action and returns a single JSON object on stdout.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from hypium.uidriver import BY
from hypium.action.device.uidriver import UiDriver
from hypium.uidriver.uitree import BySelector, UiTree


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "")
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _connect_driver() -> UiDriver:
    kwargs: Dict[str, Any] = {
        "connector": os.getenv("HYPIUM_CONNECTOR", "hdc"),
        "log_level": os.getenv("HYPIUM_LOG_LEVEL", "info"),
    }
    device_sn = os.getenv("HYPIUM_DEVICE_SN", "")
    report_path = os.getenv("HYPIUM_REPORT_PATH", "")
    connector_host = os.getenv("HYPIUM_CONNECTOR_HOST", "")
    connector_port = os.getenv("HYPIUM_CONNECTOR_PORT", "")

    if device_sn:
        kwargs["device_sn"] = device_sn
    if report_path:
        kwargs["report_path"] = report_path
    if connector_host and connector_port:
        kwargs["connector_server"] = (connector_host, int(connector_port))

    return UiDriver.connect(**kwargs)


def _normalize_selector_type(selector_type: Optional[str]) -> str:
    return (selector_type or "").strip().lower().replace("_", "-")


def _parse_prefixed_selector(selector: str) -> Tuple[Optional[str], str]:
    stripped = selector.strip()
    lowered = stripped.lower()
    prefixes = {
        "xpath=": "xpath",
        "text=": "text",
        "id=": "id",
        "key=": "resource-id",
        "resource-id=": "resource-id",
        "accessibility-id=": "accessibility-id",
        "description=": "accessibility-id",
        "type=": "type",
        "hint=": "hint",
    }
    for prefix, selector_kind in prefixes.items():
        if lowered.startswith(prefix):
            return selector_kind, stripped[len(prefix):].strip()
    return None, stripped


def _build_selector(selector: str, selector_type: Optional[str] = None):
    inferred_type, normalized_selector = _parse_prefixed_selector(selector)
    selector_type = _normalize_selector_type(selector_type or inferred_type)

    if not selector_type:
        if normalized_selector.startswith("/") or normalized_selector.startswith(".//"):
            selector_type = "xpath"
        else:
            selector_type = "text"

    if selector_type in {"id", "key", "resource-id", "identifier"}:
        return BY.id(normalized_selector)
    if selector_type in {"accessibility-id", "description", "content-desc", "contentdescription"}:
        return BY.description(normalized_selector)
    if selector_type in {"text", "name", "label"}:
        return BY.text(normalized_selector)
    if selector_type == "type":
        return BY.type(normalized_selector)
    if selector_type == "hint":
        return BY.hint(normalized_selector)
    if selector_type == "xpath":
        return BySelector().xpath(normalized_selector)
    raise ValueError(f"unsupported selector_type: {selector_type}")


def _selector_target(arguments: Dict[str, Any]):
    selector = arguments.get("selector")
    selector_type = arguments.get("selector_type")
    if selector:
        return _build_selector(selector, selector_type)

    x = arguments.get("x")
    y = arguments.get("y")
    if x is not None and y is not None:
        return (int(x), int(y))

    position = arguments.get("position")
    if isinstance(position, (list, tuple)) and len(position) >= 2:
        return (int(position[0]), int(position[1]))

    raise ValueError("selector or coordinates are required")


def _temp_dir() -> Path:
    temp_dir = os.getenv("HYPIUM_TEMP_DIR", "")
    if temp_dir:
        path = Path(temp_dir)
    else:
        path = PROJECT_ROOT / "output" / "hypium_mcp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ok(**payload: Any) -> Dict[str, Any]:
    return {"ok": True, **payload}


def _action_requires_driver(action: str) -> bool:
    return action not in {
        "hypium_ai_click",
        "hypium_ai_input",
        "hypium_ai_extract",
        "hypium_ai_assert",
        "hypium_close",
    }


def _run_action(action: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if action in {"hypium_ai_click", "hypium_ai_input", "hypium_ai_extract", "hypium_ai_assert"}:
        raise ValueError(f"{action} is not implemented by the low-level Hypium MCP helper")
    if action == "hypium_close":
        return _ok(text="close noop")

    driver = _connect_driver() if _action_requires_driver(action) else None
    try:
        if action == "hypium_get_source":
            assert driver is not None
            tree = UiTree(driver).refresh()
            return _ok(text=json.dumps(tree, ensure_ascii=False))

        if action == "hypium_screenshot":
            assert driver is not None
            save_path = arguments.get("save_path")
            if save_path:
                file_path = Path(save_path)
                file_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                fd, temp_name = tempfile.mkstemp(prefix="hypium_", suffix=".jpeg", dir=str(_temp_dir()))
                os.close(fd)
                file_path = Path(temp_name)
            driver.capture_screen(str(file_path))
            image_b64 = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            return _ok(image_base64=image_b64, mime_type="image/jpeg", text=str(file_path))

        if action == "hypium_click":
            assert driver is not None
            target = _selector_target(arguments)
            driver.click(target)
            return _ok(text=f"clicked: {arguments.get('selector') or target}")

        if action == "hypium_input":
            assert driver is not None
            text = str(arguments.get("text", ""))
            target = _selector_target(arguments)
            if arguments.get("clear_before", True):
                try:
                    driver.clear_text(target)
                except Exception:
                    pass
            driver.input_text(target, text)
            return _ok(text=f"input ok: {text[:50]}")

        if action == "hypium_clear_text":
            assert driver is not None
            target = _selector_target(arguments)
            driver.clear_text(target)
            return _ok(text="clear text ok")

        if action == "hypium_go_back":
            assert driver is not None
            driver.go_back()
            return _ok(text="go back ok")

        if action == "hypium_go_home":
            assert driver is not None
            driver.go_home()
            return _ok(text="go home ok")

        if action == "hypium_start_app":
            assert driver is not None
            package_name = arguments.get("package_name")
            if not package_name:
                raise ValueError("package_name is required")
            driver.start_app(
                package_name,
                page_name=arguments.get("page_name"),
                params=arguments.get("params", ""),
                wait_time=float(arguments.get("wait_time", 1)),
            )
            return _ok(text=f"start app ok: {package_name}")

        if action == "hypium_stop_app":
            assert driver is not None
            package_name = arguments.get("package_name")
            if not package_name:
                raise ValueError("package_name is required")
            driver.stop_app(package_name, wait_time=float(arguments.get("wait_time", 0.5)))
            return _ok(text=f"stop app ok: {package_name}")

        if action == "hypium_current_app":
            assert driver is not None
            package_name, page_name = driver.current_app()
            return _ok(text=json.dumps({"package_name": package_name, "page_name": page_name}, ensure_ascii=False))

        if action == "hypium_swipe":
            assert driver is not None
            driver.swipe(
                str(arguments.get("direction", "UP")).upper(),
                distance=int(arguments.get("distance", 60)),
                swipe_time=float(arguments.get("swipe_time", 0.3)),
            )
            return _ok(text="swipe ok")

        if action == "hypium_find_component":
            assert driver is not None
            selector = arguments.get("selector")
            if not selector:
                raise ValueError("selector is required")
            target = _build_selector(selector, arguments.get("selector_type"))
            component = driver.find_component(target)
            bounds = driver.get_component_bound(component)
            payload = {
                "selector": selector,
                "selector_type": arguments.get("selector_type") or "",
                "text": component.getText() if hasattr(component, "getText") else "",
                "id": component.getId() if hasattr(component, "getId") else "",
                "key": component.getKey() if hasattr(component, "getKey") else "",
                "description": component.getDescription() if hasattr(component, "getDescription") else "",
                "type": component.getType() if hasattr(component, "getType") else "",
                "bounds": str(bounds) if bounds is not None else "",
            }
            return _ok(text=json.dumps(payload, ensure_ascii=False))

        raise ValueError(f"unknown action: {action}")
    finally:
        try:
            if driver is not None:
                driver.close()
        except Exception:
            if _bool_env("HYPIUM_MCP_LOG_VERBOSE"):
                print(json.dumps({"warn": "driver.close failed"}, ensure_ascii=False), file=os.sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hypium helper")
    parser.add_argument("action", help="Hypium action name")
    parser.add_argument("--arguments", default="{}", help="JSON string arguments")
    args = parser.parse_args()

    try:
        arguments = json.loads(args.arguments or "{}")
        result = _run_action(args.action, arguments)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
