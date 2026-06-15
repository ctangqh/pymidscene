from types import SimpleNamespace

from core.agent.task_builder import TaskBuilder
from core.types import LocateResultElement, Rect


class _RetryDevice:
    interface_type = "windows"

    def __init__(self):
        self.position_clicks = []
        self.raw_tree = {
            "content": {
                "Name": "桌面",
                "AutomationId": "desktop-root",
                "children": [
                    {
                        "Name": "确定",
                        "AutomationId": "new-btn",
                        "controlType": "Button",
                        "left": 10,
                        "top": 20,
                        "width": 80,
                        "height": 30,
                        "children": [],
                    }
                ],
            }
        }

    def get_dom_tree(self):
        return self.raw_tree

    def click(self, selector=None, position=None, **kwargs):
        self.position_clicks.append({"selector": selector, "position": position, "kwargs": kwargs})


class _StubService:
    llm = None


def _make_element() -> LocateResultElement:
    return LocateResultElement(
        center=(50.0, 60.0),
        rect=Rect(left=10.0, top=20.0, width=80.0, height=30.0),
        description="确定",
        element_ref={
            "platform": "windows",
            "ref_kind": "selector",
            "selector_type": "accessibility id",
            "selector_value": "old-btn",
            "actionable": True,
            "persistable": True,
            "requires_resolution": True,
            "resolved": False,
            "extra": {},
        },
        locator_candidates=[
            {
                "platform": "windows",
                "ref_kind": "selector",
                "selector_type": "accessibility id",
                "selector_value": "old-btn",
                "actionable": True,
                "persistable": True,
                "requires_resolution": True,
                "resolved": False,
                "extra": {},
            }
        ],
    )


def test_task_builder_retries_with_refreshed_uitree_target():
    device = _RetryDevice()
    builder = TaskBuilder(device, _StubService())
    element = _make_element()
    attempts = []

    def run_action(target):
        attempts.append(target.get("selector"))
        if target.get("selector") == "old-btn":
            raise RuntimeError("stale selector")

    builder._execute_action_with_retry(
        action_type="Tap",
        element=element,
        action_target={
            "selector": "old-btn",
            "selector_type": "accessibility id",
            "selector_ref": element.element_ref,
            "position": element.center,
        },
        run_action=run_action,
        allow_position_fallback=True,
    )

    assert attempts == ["old-btn", "new-btn"]


def test_task_builder_falls_back_to_position_after_retry_failure():
    device = _RetryDevice()
    builder = TaskBuilder(device, _StubService())
    element = _make_element()
    task = SimpleNamespace(log={})

    def run_action(_target):
        raise RuntimeError("always fail")

    builder._execute_action_with_retry(
        action_type="Tap",
        element=element,
        action_target={
            "selector": "old-btn",
            "selector_type": "accessibility id",
            "selector_ref": element.element_ref,
            "position": element.center,
        },
        run_action=run_action,
        allow_position_fallback=True,
        task=task,
    )

    assert len(device.position_clicks) == 1
    assert device.position_clicks[0]["selector"] is None
    assert device.position_clicks[0]["position"] == (50.0, 35.0)
    assert [item["stage"] for item in task.log["action_recovery"]] == [
        "initial_failure",
        "refresh_retry",
        "refresh_retry_failure",
        "position_fallback",
    ]


def test_task_builder_records_refresh_retry_log():
    device = _RetryDevice()
    builder = TaskBuilder(device, _StubService())
    element = _make_element()
    task = SimpleNamespace(log={})
    attempts = []

    def run_action(target):
        attempts.append(target.get("selector"))
        if target.get("selector") == "old-btn":
            raise RuntimeError("stale selector")

    builder._execute_action_with_retry(
        action_type="Tap",
        element=element,
        action_target={
            "selector": "old-btn",
            "selector_type": "accessibility id",
            "selector_ref": element.element_ref,
            "position": element.center,
        },
        run_action=run_action,
        allow_position_fallback=True,
        task=task,
    )

    assert attempts == ["old-btn", "new-btn"]
    assert [item["stage"] for item in task.log["action_recovery"]] == [
        "initial_failure",
        "refresh_retry",
    ]
    assert task.log["action_recovery"][1]["selector_ref"]["selector_value"] == "new-btn"


def test_task_builder_enriches_browser_element_with_uitree_selector_ref():
    builder = TaskBuilder(_StubService(), _StubService())
    raw_tree = {
        "content": """### Page
- Page URL: https://www.google.com/
- Page Title: Google
### Snapshot
```yaml
- search [ref=e35]:
  - generic [ref=e39]:
    - combobox "Search" [active] [ref=e46]
```
"""
    }
    element = LocateResultElement(
        center=(200.0, 100.0),
        rect=Rect(left=150.0, top=80.0, width=100.0, height=40.0),
        description="Google 搜索输入框",
        coordinate_space="screenshot",
    )

    enriched = builder._enrich_element_with_uitree_metadata(
        element,
        raw_tree,
        "Google 搜索输入框",
        device_type="browser",
    )

    assert enriched is not None
    assert enriched.element_ref is not None
    assert any(candidate["selector_type"] == "playwright-ref" for candidate in enriched.locator_candidates)
    assert any(candidate["selector_type"] == "css" for candidate in enriched.locator_candidates)
    assert any(candidate["selector_type"] == "role" for candidate in enriched.locator_candidates)
    assert enriched.coordinate_space == "screenshot"
    assert enriched.rect.left == 150.0
    assert enriched.rect.top == 80.0
    assert enriched.rect.width == 100.0
    assert enriched.rect.height == 40.0
    assert enriched.center == (200.0, 100.0)


def test_task_builder_refreshes_browser_target_without_bounds():
    builder = TaskBuilder(_StubService(), _StubService())
    builder.device = SimpleNamespace(
        interface_type="browser",
        get_dom_tree=lambda: {
            "content": """### Page
- Page URL: https://www.google.com/
- Page Title: Google
### Snapshot
```yaml
- search [ref=e35]:
  - generic [ref=e39]:
    - combobox "Search" [active] [ref=e46]
```
"""
        },
    )
    element = LocateResultElement(
        center=(200.0, 100.0),
        rect=Rect(left=150.0, top=80.0, width=100.0, height=40.0),
        description="Google search text input field",
        coordinate_space="screenshot",
    )

    refreshed = builder._refresh_action_target(
        element,
        device_type="browser",
        action_type="Input",
    )

    assert refreshed is not None
    assert refreshed["selector_ref"] is not None
    assert refreshed["selector_ref"]["selector_type"] == "css"
    assert refreshed["selector_ref"]["selector_value"] == '[aria-label="Search"]'
    assert refreshed["position"] == (200.0, 100.0)


def test_task_builder_browser_enrichment_keeps_visual_bbox():
    builder = TaskBuilder(_StubService(), _StubService())
    raw_tree = {
        "content": """### Page
- Page URL: https://www.google.com/
- Page Title: Google
### Snapshot
```yaml
- search [ref=e35]:
  - generic [ref=e39]:
    - combobox "Search" [active] [ref=e46]
```
"""
    }
    element = LocateResultElement(
        center=(499.5, 377.0),
        rect=Rect(left=272.0, top=343.0, width=455.0, height=68.0),
        description="Google search text input field",
        coordinate_space="screenshot",
    )

    enriched = builder._enrich_element_with_uitree_metadata(
        element,
        raw_tree,
        "Google search text input field",
        device_type="browser",
    )

    assert enriched is not None
    assert enriched.coordinate_space == "screenshot"
    assert enriched.rect.left == 272.0
    assert enriched.rect.top == 343.0
    assert enriched.rect.width == 455.0
    assert enriched.rect.height == 68.0
    assert enriched.center == (499.5, 377.0)
    assert enriched.element_ref is not None
    assert any(candidate["selector_type"] == "css" for candidate in enriched.locator_candidates)


def run_all_task_builder_retry_checks():
    test_task_builder_retries_with_refreshed_uitree_target()
    test_task_builder_falls_back_to_position_after_retry_failure()
    test_task_builder_records_refresh_retry_log()
    test_task_builder_enriches_browser_element_with_uitree_selector_ref()
    test_task_builder_refreshes_browser_target_without_bounds()
    test_task_builder_browser_enrichment_keeps_visual_bbox()


if __name__ == "__main__":
    run_all_task_builder_retry_checks()
    print("all task builder retry checks passed")
