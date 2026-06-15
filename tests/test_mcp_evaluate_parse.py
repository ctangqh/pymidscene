import asyncio
from types import SimpleNamespace

from device.mcp.client import BaseMcpDevice


def _text_result(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _StubEvaluateDevice(BaseMcpDevice):
    @property
    def interface_type(self) -> str:
        return "browser"

    def __init__(self, response_text: str):
        super().__init__(mcp_name=None)
        self.response_text = response_text
        self._tool_map = {"evaluate": {"tool": "browser_evaluate", "mapper": lambda **k: {"function": k.get("script")}}}

    def _submit(self, coro, timeout=None):
        return asyncio.run(coro)

    async def _call_mcp(self, tool_name: str, arguments):
        return _text_result(self.response_text)


def test_evaluate_script_parses_markdown_wrapped_json_object():
    device = _StubEvaluateDevice(
        '### Result\n{"left":396,"top":247,"width":447,"height":50}\n### Ran Playwright code'
    )
    result = device.evaluate_script("() => ({ left: 396, top: 247, width: 447, height: 50 })")
    assert result == {"left": 396, "top": 247, "width": 447, "height": 50}


def test_evaluate_script_parses_markdown_wrapped_json_array():
    device = _StubEvaluateDevice(
        '### Result\n[\n  {"selector":"[aria-label=\\"Search\\"]","found":true}\n]\n### Ran Playwright code'
    )
    result = device.evaluate_script("() => ([{ selector: '[aria-label=\"Search\"]', found: true }])")
    assert result == [{"selector": '[aria-label="Search"]', "found": True}]


def test_evaluate_script_keeps_plain_text():
    device = _StubEvaluateDevice("Google")
    result = device.evaluate_script("() => document.title")
    assert result == "Google"


def run_all_mcp_evaluate_parse_checks():
    test_evaluate_script_parses_markdown_wrapped_json_object()
    test_evaluate_script_parses_markdown_wrapped_json_array()
    test_evaluate_script_keeps_plain_text()


if __name__ == "__main__":
    run_all_mcp_evaluate_parse_checks()
    print("all mcp evaluate parse checks passed")
