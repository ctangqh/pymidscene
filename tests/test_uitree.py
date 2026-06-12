import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from common.config import settings
from core.locator import ElementLocator
from core.uitree import UIElement, UITREE_SCHEMA_VERSION, UITreeManager
from core.uitree.debug import capture_debug_tree
from core.uitree.registry import iter_matching_adapters
from core.uitree.normalize import extract_jsonable_payload, normalize_jsonable_data


def test_uitree_manager_parses_windows_xml_payload():
    manager = UITreeManager()
    raw_data = {
        "content": """
        <Window Name="MainWindow" AutomationId="root" BoundingRectangle="[0,0][400,800]">
            <Button Name="确定" AutomationId="confirm-btn" BoundingRectangle="[10,20][110,60]" />
        </Window>
        """
    }

    tree = manager.parse(raw_data, device_type="windows")

    assert isinstance(tree, UIElement)
    assert tree.name == "MainWindow"
    assert tree.automation_id == "root"
    assert tree.bounds == (0.0, 0.0, 400.0, 800.0)
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "确定"
    assert child.tag == "Button"
    assert child.automation_id == "confirm-btn"
    assert child.path == ["MainWindow", "确定"]
    assert child.bounds == (10.0, 20.0, 100.0, 40.0)
    assert child.element_ref is not None
    assert child.element_ref.ref_kind == "selector"
    assert child.element_ref.source == "uitree_derived"
    assert child.element_ref.selector_type == "accessibility id"
    assert child.element_ref.selector_value == "confirm-btn"
    assert child.element_ref.actionable is True
    assert child.element_ref.persistable is True
    assert child.element_ref.requires_resolution is True
    assert child.element_ref.resolved is False


def test_uitree_manager_parses_windows_dict_payload():
    manager = UITreeManager()
    raw_data = {
        "content": {
            "Name": "桌面",
            "AutomationId": "desktop-root",
            "children": [
                {
                    "Name": "输入框",
                    "AutomationId": "search-box",
                    "controlType": "Edit",
                    "left": 20,
                    "top": 30,
                    "width": 200,
                    "height": 40,
                    "children": [],
                }
            ],
        }
    }

    tree = manager.parse(raw_data, device_type="windows")

    assert isinstance(tree, UIElement)
    assert tree.name == "桌面"
    assert tree.automation_id == "desktop-root"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "输入框"
    assert child.automation_id == "search-box"
    assert child.control_type == "Edit"
    assert child.bounds == (20.0, 30.0, 200.0, 40.0)


def test_uitree_manager_parses_playwright_tree():
    manager = UITreeManager()
    raw_data = {
        "tagName": "div",
        "children": [
            {
                "tagName": "button",
                "text": "提交",
                "id": "submit-btn",
                "role": "button",
                "left": 12,
                "top": 16,
                "width": 88,
                "height": 32,
                "children": [],
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="browser")

    assert isinstance(tree, UIElement)
    assert tree.tag == "div"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "提交"
    assert child.tag == "button"
    assert child.control_type == "button"
    assert child.automation_id == "submit-btn"
    assert child.bounds == (12.0, 16.0, 88.0, 32.0)
    assert child.element_ref is not None
    assert child.element_ref.selector_type == "css"
    assert child.element_ref.selector_value == "#submit-btn"
    assert child.element_ref.actionable is True
    assert child.element_ref.persistable is True
    assert child.element_ref.requires_resolution is False
    assert child.element_ref.resolved is False


def test_uitree_manager_parses_playwright_device_dom_shape():
    manager = UITreeManager()
    raw_data = {
        "tagName": "body",
        "attributes": {"id": "root", "class": "page-root"},
        "text": "",
        "children": [
            {
                "tagName": "input",
                "attributes": {
                    "id": "kw",
                    "class": "search-input",
                    "placeholder": "请输入搜索词",
                },
                "text": "",
                "children": [],
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="browser")

    assert isinstance(tree, UIElement)
    assert tree.automation_id == "root"
    assert tree.class_name == "page-root"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "kw"
    assert child.automation_id == "kw"
    assert child.class_name == "search-input"
    assert child.attributes["placeholder"] == "请输入搜索词"


def test_uitree_manager_save_writes_raw_and_parsed_files(tmp_path: Path):
    manager = UITreeManager()
    raw_data = {
        "tagName": "button",
        "text": "保存",
        "id": "save-btn",
        "left": 1,
        "top": 2,
        "width": 30,
        "height": 40,
        "children": [],
    }

    result = manager.save(
        raw_data,
        "保存按钮",
        device_type="browser",
        save_dir=tmp_path,
    )

    assert result["raw"] is not None
    assert result["parsed"] is not None
    assert result["raw"].exists()
    assert result["parsed"].exists()

    raw_payload = json.loads(result["raw"].read_text(encoding="utf-8"))
    parsed_payload = json.loads(result["parsed"].read_text(encoding="utf-8"))

    assert raw_payload["schema_version"] == UITREE_SCHEMA_VERSION
    assert raw_payload["description"] == "保存按钮"
    assert raw_payload["device_type"] == "browser"
    assert raw_payload["payload"]["id"] == "save-btn"
    assert parsed_payload["schema_version"] == UITREE_SCHEMA_VERSION
    assert parsed_payload["description"] == "保存按钮"
    assert parsed_payload["device_type"] == "browser"
    assert parsed_payload["nodes_count"] == 1
    assert parsed_payload["tree"]["name"] == "保存"
    assert parsed_payload["nodes"][0]["name"] == "保存"


def test_uitree_manager_parses_ios_tree():
    manager = UITreeManager()
    raw_data = {
        "elementType": "XCUIElementTypeWindow",
        "label": "首页",
        "children": [
            {
                "elementType": "XCUIElementTypeButton",
                "label": "登录",
                "identifier": "login-btn",
                "x": 15,
                "y": 30,
                "width": 120,
                "height": 44,
                "children": [],
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="ios")

    assert isinstance(tree, UIElement)
    assert tree.name == "首页"
    assert tree.tag == "XCUIElementTypeWindow"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "登录"
    assert child.automation_id == "login-btn"
    assert child.tag == "XCUIElementTypeButton"
    assert child.bounds == (15.0, 30.0, 120.0, 44.0)
    assert child.path == ["首页", "登录"]
    assert child.element_ref is not None
    assert child.element_ref.selector_type == "identifier"
    assert child.element_ref.selector_value == "login-btn"
    assert child.element_ref.actionable is True
    assert child.element_ref.persistable is True
    assert child.element_ref.requires_resolution is True
    assert child.element_ref.resolved is False


def test_uitree_manager_parses_hypium_tree():
    manager = UITreeManager()
    raw_data = {
        "@type": "Page",
        "text": "设置页",
        "children": [
            {
                "@type": "Button",
                "@class": "ohos.Button",
                "content-desc": "确定",
                "id": "confirm",
                "bounds": "[50,60][170,100]",
                "children": [],
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="hypium")

    assert isinstance(tree, UIElement)
    assert tree.tag == "Page"
    assert tree.name == "设置页"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "确定"
    assert child.tag == "Button"
    assert child.class_name == "ohos.Button"
    assert child.automation_id == "confirm"
    assert child.bounds == (50.0, 60.0, 120.0, 40.0)
    assert child.element_ref is not None
    assert child.element_ref.selector_type == "resource-id"
    assert child.element_ref.selector_value == "confirm"
    assert child.element_ref.actionable is True
    assert child.element_ref.persistable is True
    assert child.element_ref.requires_resolution is True
    assert child.element_ref.resolved is False


def test_uitree_manager_selects_best_candidate_by_platform_and_action():
    manager = UITreeManager()
    candidates = [
        {
            "platform": "playwright",
            "selector_type": "text",
            "selector_value": "text=提交",
            "extra": {},
        },
        {
            "platform": "playwright",
            "selector_type": "css",
            "selector_value": "#submit-btn",
            "extra": {},
        },
        {
            "platform": "playwright",
            "selector_type": "role",
            "selector_value": "button:提交",
            "extra": {"role": "button", "name": "提交"},
        },
    ]

    best_for_tap = manager.select_best_candidate(candidates, device_type="browser", action_type="tap")
    best_for_input = manager.select_best_candidate(candidates, device_type="browser", action_type="input")

    assert best_for_tap is not None
    assert best_for_tap["selector_type"] == "css"
    assert best_for_input is not None
    assert best_for_input["selector_type"] == "css"


def test_uitree_manager_skips_non_actionable_candidates_when_needed():
    manager = UITreeManager()
    candidates = [
        {
            "platform": "playwright",
            "selector_type": "text",
            "selector_value": "text=确定",
            "resolved": False,
            "extra": {},
        },
        {
            "platform": "playwright",
            "selector_type": "css",
            "selector_value": "#confirm-btn",
            "resolved": False,
            "extra": {},
        },
    ]

    best = manager.select_best_candidate(
        candidates,
        device_type="browser",
        action_type="input",
        actionable_only=True,
    )

    assert best is not None
    assert best["selector_type"] == "css"
    assert best["requires_resolution"] is False
    assert best["persistable"] is True


def test_uitree_manager_marks_playwright_ref_as_non_persistable():
    manager = UITreeManager()
    candidates = [
        {
            "platform": "playwright",
            "selector_type": "playwright-ref",
            "selector_value": "ref-123",
            "extra": {},
        }
    ]

    best = manager.select_best_candidate(
        candidates,
        device_type="browser",
        action_type="tap",
        actionable_only=True,
    )

    assert best is not None
    assert best["selector_type"] == "playwright-ref"
    assert best["actionable"] is True
    assert best["persistable"] is False
    assert best["requires_resolution"] is False


def test_uitree_manager_falls_back_to_generic_tree():
    manager = UITreeManager()
    raw_data = {
        "title": "通用页面",
        "kind": "screen",
        "nodes": [
            {
                "title": "继续",
                "className": "generic-button",
                "left": 5,
                "top": 8,
                "width": 90,
                "height": 24,
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="android")

    assert isinstance(tree, UIElement)
    assert tree.name == "通用页面"
    assert tree.tag == "node"
    assert len(tree.children) == 1

    child = tree.children[0]
    assert child.name == "继续"
    assert child.class_name == "generic-button"
    assert child.bounds == (5.0, 8.0, 90.0, 24.0)


def test_uitree_manager_keeps_nested_path_and_depth():
    manager = UITreeManager()
    raw_data = {
        "tagName": "div",
        "text": "页面",
        "children": [
            {
                "tagName": "section",
                "text": "表单区",
                "children": [
                    {
                        "tagName": "button",
                        "text": "提交",
                        "left": 100,
                        "top": 120,
                        "width": 88,
                        "height": 36,
                        "children": [],
                    }
                ],
            }
        ],
    }

    tree = manager.parse(raw_data, device_type="browser")

    assert isinstance(tree, UIElement)
    level1 = tree.children[0]
    level2 = level1.children[0]

    assert tree.path == ["页面"]
    assert tree.depth == 0
    assert level1.path == ["页面", "表单区"]
    assert level1.depth == 1
    assert level2.path == ["页面", "表单区", "提交"]
    assert level2.depth == 2
    assert level2.bounds == (100.0, 120.0, 88.0, 36.0)


def test_iter_matching_adapters_uses_expected_order():
    browser_payload = {"tagName": "button", "text": "提交", "children": []}
    browser_adapters = [adapter.__class__.__name__ for adapter in iter_matching_adapters(browser_payload, "browser")]
    assert browser_adapters[0] == "PlaywrightUITreeAdapter"
    assert browser_adapters[-1] == "GenericUITreeAdapter"

    ios_payload = {"elementType": "XCUIElementTypeButton", "label": "登录", "children": []}
    ios_adapters = [adapter.__class__.__name__ for adapter in iter_matching_adapters(ios_payload, "ios")]
    assert ios_adapters[0] == "IOSUITreeAdapter"
    assert ios_adapters[-1] == "GenericUITreeAdapter"


def test_capture_debug_tree_writes_debug_artifacts(tmp_path: Path):
    previous_debug = settings.DEBUG
    settings.DEBUG = True
    try:
        device = _StubNativeDevice()
        result = capture_debug_tree(
            device,
            "确定按钮",
            save_dir=tmp_path,
        )
    finally:
        settings.DEBUG = previous_debug

    assert result["raw"] is not None
    assert result["parsed"] is not None
    assert result["raw"].exists()
    assert result["parsed"].exists()

    raw_payload = json.loads(result["raw"].read_text(encoding="utf-8"))
    parsed_payload = json.loads(result["parsed"].read_text(encoding="utf-8"))
    assert raw_payload["schema_version"] == UITREE_SCHEMA_VERSION
    assert raw_payload["device_type"] == "windows"
    assert raw_payload["payload"]["tag"] == "Window"
    assert raw_payload["payload"]["children"][0]["tag"] == "Button"
    assert parsed_payload["nodes_count"] >= 1
    assert parsed_payload["schema_version"] == UITREE_SCHEMA_VERSION
    assert parsed_payload["device_type"] == "windows"
    assert parsed_payload["tree"]["tag"] == "Window"
    assert parsed_payload["nodes"][0]["name"] == "MainWindow"
    assert parsed_payload["nodes"][1]["preferred_action_ref"]["selector_type"] == "accessibility id"
    assert parsed_payload["nodes"][1]["execution_notes"]["requires_resolution"] is True
    assert parsed_payload["nodes"][1]["execution_notes"]["persistable"] is True


def test_normalize_jsonable_data_converts_xml_to_json_dict():
    raw_xml = """
    <Window Name="MainWindow">
        <Button Name="确定" AutomationId="confirm-btn" />
    </Window>
    """

    normalized = normalize_jsonable_data({"content": raw_xml})

    assert normalized["content"]["tag"] == "Window"
    assert normalized["content"]["attributes"]["Name"] == "MainWindow"
    assert normalized["content"]["children"][0]["tag"] == "Button"
    assert "<Window" not in json.dumps(normalized, ensure_ascii=False)


def test_extract_jsonable_payload_unwraps_common_payload_shell():
    raw_data = {
        "content": """
        <Window Name="MainWindow">
            <Button Name="确定" />
        </Window>
        """
    }

    payload = extract_jsonable_payload(raw_data)

    assert payload["tag"] == "Window"
    assert payload["attributes"]["Name"] == "MainWindow"
    assert payload["children"][0]["tag"] == "Button"


class _StubNativeDevice:
    interface_type = "windows"

    def get_dom_tree(self):
        return {
            "content": """
            <Window Name="MainWindow">
                <Button Name="确定" AutomationId="confirm-btn" BoundingRectangle="[100,200][180,240]" />
            </Window>
            """
        }


def test_locator_native_tree_uses_new_uitree_package():
    locator = ElementLocator(_StubNativeDevice(), Mock())

    result = locator._locate_by_native_tree("确定")

    assert result is not None
    assert result.selector == "confirm-btn"
    assert result.x == 140.0
    assert result.y == 220.0
    assert result.bounding_box == {
        "left": 100.0,
        "top": 200.0,
        "width": 80.0,
        "height": 40.0,
    }
    assert "UI 树定位" in (result.reason or "")


def run_all_uitree_checks():
    test_uitree_manager_parses_windows_xml_payload()
    test_uitree_manager_parses_windows_dict_payload()
    test_uitree_manager_parses_playwright_tree()
    test_uitree_manager_parses_playwright_device_dom_shape()
    test_uitree_manager_parses_ios_tree()
    test_uitree_manager_parses_hypium_tree()
    test_uitree_manager_falls_back_to_generic_tree()
    test_uitree_manager_keeps_nested_path_and_depth()
    test_iter_matching_adapters_uses_expected_order()
    test_normalize_jsonable_data_converts_xml_to_json_dict()
    test_extract_jsonable_payload_unwraps_common_payload_shell()

    with TemporaryDirectory() as temp_dir:
        test_uitree_manager_save_writes_raw_and_parsed_files(Path(temp_dir))
        test_capture_debug_tree_writes_debug_artifacts(Path(temp_dir))

    test_locator_native_tree_uses_new_uitree_package()


if __name__ == "__main__":
    run_all_uitree_checks()
    print("all uitree checks passed")
