import asyncio
from types import SimpleNamespace

from device.mcp.client import BaseMcpDevice, McpPlaywrightDevice, McpWinAppDevice


def _text_result(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _StubMcpDevice(BaseMcpDevice):
    @property
    def interface_type(self) -> str:
        return "generic"

    def __init__(self):
        super().__init__(mcp_name=None)

    def _submit(self, coro, timeout=None):
        return asyncio.run(coro)

    async def _call_mcp(self, tool_name: str, arguments):
        return _text_result(f"{tool_name}:{arguments}")


class _StubWinAppDevice(McpWinAppDevice):
    def __init__(self):
        super().__init__(mcp_name="winapp")
        self.calls = []

    def _submit(self, coro, timeout=None):
        return asyncio.run(coro)

    async def _call_mcp(self, tool_name: str, arguments):
        self.calls.append((tool_name, dict(arguments)))
        if tool_name == "winapp_find_element":
            return _text_result("element-123")
        return _text_result("ok")


def test_base_mcp_device_resolve_selector_ref_returns_selector():
    device = _StubMcpDevice()

    ref = device.resolve_selector_ref("submit-btn", selector_type="id", action_type="tap")

    assert ref is not None
    assert ref["ref_kind"] == "selector"
    assert ref["selector_type"] == "id"
    assert ref["selector_value"] == "submit-btn"
    assert ref["resolved"] is False


def test_playwright_resolve_selector_ref_keeps_selector_semantics():
    device = McpPlaywrightDevice(mcp_name="playwright")

    ref = device.resolve_selector_ref(
        "#submit-btn",
        selector_type="css",
        selector_ref={
            "platform": "playwright",
            "selector_type": "css",
            "selector_value": "#submit-btn",
            "actionable": True,
            "persistable": True,
            "requires_resolution": False,
            "resolved": False,
            "extra": {},
        },
        action_type="tap",
    )

    assert ref is not None
    assert ref["ref_kind"] == "selector"
    assert ref["selector_type"] == "css"
    assert ref["selector_value"] == "#submit-btn"
    assert ref["resolved"] is False


def test_winapp_resolve_selector_ref_returns_runtime_handle():
    device = _StubWinAppDevice()

    ref = device.resolve_selector_ref(
        "confirm-btn",
        selector_type="accessibility id",
        selector_ref={
            "platform": "windows",
            "ref_kind": "selector",
            "selector_type": "accessibility id",
            "selector_value": "confirm-btn",
            "actionable": True,
            "persistable": True,
            "requires_resolution": True,
            "resolved": False,
            "extra": {},
        },
        action_type="tap",
    )

    assert ref is not None
    assert ref["ref_kind"] == "handle"
    assert ref["selector_type"] == "element_id"
    assert ref["selector_value"] == "element-123"
    assert ref["persistable"] is False
    assert ref["requires_resolution"] is False
    assert ref["resolved"] is True
    assert device.calls[0][0] == "winapp_find_element"


def test_winapp_click_uses_resolved_element_id():
    device = _StubWinAppDevice()

    device.click(
        selector="confirm-btn",
        selector_type="accessibility id",
        selector_ref={
            "platform": "windows",
            "ref_kind": "selector",
            "selector_type": "accessibility id",
            "selector_value": "confirm-btn",
            "actionable": True,
            "persistable": True,
            "requires_resolution": True,
            "resolved": False,
            "extra": {},
        },
    )

    assert device.calls[0] == (
        "winapp_find_element",
        {"selector": "confirm-btn", "using": "accessibility id"},
    )
    assert device.calls[1] == (
        "winapp_click_element",
        {"element_id": "element-123"},
    )


def run_all_mcp_device_checks():
    test_base_mcp_device_resolve_selector_ref_returns_selector()
    test_playwright_resolve_selector_ref_keeps_selector_semantics()
    test_winapp_resolve_selector_ref_returns_runtime_handle()
    test_winapp_click_uses_resolved_element_id()


if __name__ == "__main__":
    run_all_mcp_device_checks()
    print("all mcp device checks passed")
