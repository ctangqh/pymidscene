from core.service import Service
from core.types import DetailedLocateParam, Rect, UIContext


def _context(width: int, height: int) -> UIContext:
    return UIContext(
        screenshot="dummy",
        shot_size={"width": width, "height": height},
        shrunk_shot_to_logical_ratio=1.0,
    )


def test_service_refine_policy_skips_large_desktop_input() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_refine = service._should_run_visual_refine(
        _context(1280, 720),
        Rect(left=272, top=345, width=454, height=66),
        rough_type="Input",
        query_prompt="Google 搜索输入框",
        locate_query=DetailedLocateParam(prompt="Google 搜索输入框"),
    )
    assert should_refine is False


def test_service_refine_policy_keeps_small_screen_refine() -> None:
    service = Service(_context(390, 844), llm=None)
    should_refine = service._should_run_visual_refine(
        _context(390, 844),
        Rect(left=120, top=700, width=44, height=44),
        rough_type="Button",
        query_prompt="底部导航按钮",
        locate_query=DetailedLocateParam(prompt="底部导航按钮"),
    )
    assert should_refine is True


def test_service_refine_policy_deep_locate_forces_refine() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_refine = service._should_run_visual_refine(
        _context(1280, 720),
        Rect(left=300, top=200, width=400, height=80),
        rough_type="Input",
        query_prompt="搜索框",
        locate_query=DetailedLocateParam(prompt="搜索框", deep_locate=True),
    )
    assert should_refine is True


def test_service_refine_policy_skips_anchor_backed_input_without_small_target() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_refine = service._should_run_visual_refine(
        _context(1280, 720),
        Rect(left=320, top=240, width=300, height=60),
        rough_type="Input",
        query_prompt="搜索输入框",
        locate_query=DetailedLocateParam(
            prompt="搜索输入框",
            action_type="Input",
            structural_anchor_available=True,
            device_type="browser",
        ),
    )
    assert should_refine is False


def test_service_refine_policy_keeps_high_precision_tap_with_anchor() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_refine = service._should_run_visual_refine(
        _context(1280, 720),
        Rect(left=900, top=24, width=80, height=80),
        rough_type="Button",
        query_prompt="工具栏更多按钮",
        locate_query=DetailedLocateParam(
            prompt="工具栏更多按钮",
            action_type="Tap",
            structural_anchor_available=True,
            device_type="browser",
        ),
    )
    assert should_refine is True


def test_service_coarse_rescue_policy_triggers_on_large_misaligned_anchor() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_rescue = service._should_run_coarse_rescue(
        _context(1280, 720),
        Rect(left=272, top=343, width=454, height=68),
        locate_query=DetailedLocateParam(
            prompt="搜索输入框",
            action_type="Input",
            structural_anchor_available=True,
            structural_anchor_bbox=[396, 247, 843, 297],
            device_type="browser",
        ),
    )
    assert should_rescue is True


def test_service_coarse_rescue_policy_skips_when_anchor_already_aligned() -> None:
    service = Service(_context(1280, 720), llm=None)
    should_rescue = service._should_run_coarse_rescue(
        _context(1280, 720),
        Rect(left=380, top=245, width=480, height=55),
        locate_query=DetailedLocateParam(
            prompt="搜索输入框",
            action_type="Input",
            structural_anchor_available=True,
            structural_anchor_bbox=[396, 247, 843, 297],
            device_type="browser",
        ),
    )
    assert should_rescue is False


def test_locate_via_llm_skips_refine_for_large_desktop_input() -> None:
    class _Service(Service):
        async def _chat_with_screenshot(self, llm, prompt, screenshot_base64, **kwargs):
            return '{"bbox": [272, 345, 726, 411], "type": "Input", "description": "Google search input field"}'

        async def _refine_locate_via_llm(self, llm, context, query_prompt, rough_rect, **kwargs):
            raise AssertionError("refine should not be called for large desktop input")

    service = _Service(_context(1280, 720), llm=object())
    result = __import__("asyncio").run(
        service._locate_via_llm(
            _context(1280, 720),
            "Google 搜索输入框",
            DetailedLocateParam(prompt="Google 搜索输入框"),
            model_runtime=object(),
        )
    )
    assert result is not None
    assert int(result.rect.top) == 345


def test_locate_via_llm_uses_coarse_rescue_when_anchor_conflicts() -> None:
    class _Service(Service):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.prompts = []

        async def _chat_with_screenshot(self, llm, prompt, screenshot_base64, **kwargs):
            self.prompts.append(prompt)
            if "correcting a UI element detection" in prompt:
                return '{"bbox": [156, 96, 603, 146], "type": "Input", "description": "rescued search input"}'
            return '{"bbox": [272, 343, 726, 411], "type": "Input", "description": "rough search input"}'

        async def _refine_locate_via_llm(self, llm, context, query_prompt, rough_rect, **kwargs):
            raise AssertionError("refine should not be called after anchor-backed rescue for large input")

    service = _Service(_context(1280, 720), llm=object())
    result = __import__("asyncio").run(
        service._locate_via_llm(
            _context(1280, 720),
            "Google 搜索输入框",
            DetailedLocateParam(
                prompt="Google 搜索输入框",
                action_type="Input",
                structural_anchor_available=True,
                structural_anchor_bbox=[396, 247, 843, 297],
                device_type="browser",
            ),
            model_runtime=object(),
        )
    )
    assert result is not None
    assert int(result.rect.left) == 395
    assert int(result.rect.top) == 247
    assert any("correcting a UI element detection" in prompt for prompt in service.prompts)


def test_locate_via_llm_rejects_weak_coarse_rescue_result() -> None:
    class _Service(Service):
        async def _chat_with_screenshot(self, llm, prompt, screenshot_base64, **kwargs):
            if "correcting a UI element detection" in prompt:
                return '{"bbox": [0, 0, 800, 220], "type": "Input", "description": "too large rescue"}'
            return '{"bbox": [272, 343, 726, 411], "type": "Input", "description": "rough search input"}'

        async def _refine_locate_via_llm(self, llm, context, query_prompt, rough_rect, **kwargs):
            raise AssertionError("refine should not be called for large desktop input")

    service = _Service(_context(1280, 720), llm=object())
    result = __import__("asyncio").run(
        service._locate_via_llm(
            _context(1280, 720),
            "Google 搜索输入框",
            DetailedLocateParam(
                prompt="Google 搜索输入框",
                action_type="Input",
                structural_anchor_available=True,
                structural_anchor_bbox=[396, 247, 843, 297],
                device_type="browser",
            ),
            model_runtime=object(),
        )
    )
    assert result is not None
    assert int(result.rect.left) == 272
    assert int(result.rect.top) == 343


def test_locate_via_llm_rejects_semantically_drifting_coarse_rescue_result() -> None:
    class _Service(Service):
        async def _chat_with_screenshot(self, llm, prompt, screenshot_base64, **kwargs):
            if "correcting a UI element detection" in prompt:
                return (
                    '{"bbox": [117, 0, 403, 197], "type": "Image", '
                    '"description": "Google themed doodle logo on homepage"}'
                )
            return '{"bbox": [272, 343, 726, 411], "type": "Input", "description": "rough search input"}'

        async def _refine_locate_via_llm(self, llm, context, query_prompt, rough_rect, **kwargs):
            raise AssertionError("refine should not be called for large desktop input")

    service = _Service(_context(1280, 720), llm=object())
    result = __import__("asyncio").run(
        service._locate_via_llm(
            _context(1280, 720),
            "Google 搜索输入框",
            DetailedLocateParam(
                prompt="Google 搜索输入框",
                action_type="Input",
                structural_anchor_available=True,
                structural_anchor_bbox=[396, 247, 843, 297],
                structural_anchor_description="Search Combobox",
                device_type="browser",
            ),
            model_runtime=object(),
        )
    )
    assert result is not None
    assert int(result.rect.left) == 272
    assert int(result.rect.top) == 343
    assert result.el_type == "Input"


if __name__ == "__main__":
    test_service_refine_policy_skips_large_desktop_input()
    test_service_refine_policy_keeps_small_screen_refine()
    test_service_refine_policy_deep_locate_forces_refine()
    test_service_refine_policy_skips_anchor_backed_input_without_small_target()
    test_service_refine_policy_keeps_high_precision_tap_with_anchor()
    test_service_coarse_rescue_policy_triggers_on_large_misaligned_anchor()
    test_service_coarse_rescue_policy_skips_when_anchor_already_aligned()
    test_locate_via_llm_skips_refine_for_large_desktop_input()
    test_locate_via_llm_uses_coarse_rescue_when_anchor_conflicts()
    test_locate_via_llm_rejects_weak_coarse_rescue_result()
    test_locate_via_llm_rejects_semantically_drifting_coarse_rescue_result()
    print("service refine policy tests passed")
