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


def run_all_task_builder_retry_checks():
    test_task_builder_retries_with_refreshed_uitree_target()
    test_task_builder_falls_back_to_position_after_retry_failure()
    test_task_builder_records_refresh_retry_log()


if __name__ == "__main__":
    run_all_task_builder_retry_checks()
    print("all task builder retry checks passed")
