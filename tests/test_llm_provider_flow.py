from __future__ import annotations

import os
import random
import sys
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from common.config import settings
from core.anomaly_guard import UIAnomalyGuard
from core.service import Service
from core.types import Rect, UIContext
from common.json_utils import parse_relaxed_json_object
from llm import (
    DEFAULT_IMAGE_CONSTRAINTS,
    DeepSeekLLM,
    DefaultImagePreprocessor,
    ImageConstraints,
    MessageBuilder,
    OpenAILLM,
    UnifiedImage,
    get_llm,
)
from common.exceptions import TooManyImagesError


def _build_png_bytes(size: tuple[int, int] = (300, 200), color: str = "red", noisy: bool = False) -> bytes:
    if noisy:
        rng = random.Random(0)
        image = Image.new("RGB", size)
        image.putdata(
            [
                (rng.randrange(256), rng.randrange(256), rng.randrange(256))
                for _ in range(size[0] * size[1])
            ]
        )
    else:
        image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class CaptureLLM:
    def __init__(self) -> None:
        self.last_messages = None

    def chat(self, messages, **kwargs):
        self.last_messages = messages
        return "ok"


class RawCaptureLLM:
    def __init__(self) -> None:
        self.last_messages = None

    def encode_messages(self, messages):
        encoded = []
        for message in messages:
            content = message["content"]
            if isinstance(content, list):
                encoded.append(
                    {
                        "role": message["role"],
                        "content": [
                            {"type": part["type"], "text": part.get("text")}
                            if part.get("type") == "text"
                            else {"type": "image_url", "image_url": {"url": "encoded://image"}}
                            for part in content
                        ],
                    }
                )
            else:
                encoded.append(message)
        return encoded

    def _chat(self, messages, **kwargs):
        self.last_messages = messages
        return "ok"


class JsonTextLLM:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.last_messages = None

    def chat(self, messages, **kwargs):
        self.last_messages = messages
        return self.response_text


def test_default_image_preprocessor_resizes_large_image():
    processor = DefaultImagePreprocessor()
    data = _build_png_bytes((2600, 1800))
    image = UnifiedImage.from_bytes(data, mime_type="image/png")
    constraints = ImageConstraints(
        max_file_bytes=8 * 1024 * 1024,
        max_width=1024,
        max_height=1024,
        max_images=1,
        allowed_mime_types=("image/png", "image/jpeg"),
        auto_resize=True,
        auto_compress=True,
        auto_convert_to_jpeg=True,
    )

    result = processor.prepare(image, constraints=constraints)

    assert result.final_width <= 1024
    assert result.final_height <= 1024
    assert result.resized is True


def test_default_image_preprocessor_converts_unsupported_mime_without_size_trigger():
    processor = DefaultImagePreprocessor()
    data = _build_png_bytes((64, 64))
    image = UnifiedImage.from_bytes(data, mime_type="image/bmp")

    result = processor.prepare(image, constraints=DEFAULT_IMAGE_CONSTRAINTS)

    assert result.converted is True
    assert result.final_mime_type == "image/jpeg"


def test_default_image_preprocessor_can_continue_resize_after_initial_resize():
    processor = DefaultImagePreprocessor()
    data = _build_png_bytes((3000, 2400), noisy=True)
    image = UnifiedImage.from_bytes(data, mime_type="image/png")
    constraints = ImageConstraints(
        max_file_bytes=60 * 1024,
        max_width=2048,
        max_height=2048,
        max_images=1,
        allowed_mime_types=("image/png", "image/jpeg", "image/webp"),
        auto_resize=True,
        auto_compress=True,
        auto_convert_to_jpeg=True,
    )

    result = processor.prepare(image, constraints=constraints)

    assert any("resized for byte reduction" in note for note in result.notes)
    assert result.final_bytes <= constraints.max_file_bytes


def test_openai_llm_encodes_unified_image_to_image_url():
    data = _build_png_bytes((16, 12))
    image = UnifiedImage.from_bytes(data, mime_type="image/png")
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o")

    encoded = llm.encode_messages([MessageBuilder.user_text_with_image("describe", image)])

    content = encoded[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/")


def test_deepseek_llm_encodes_unified_image_to_markdown():
    data = _build_png_bytes((16, 12))
    image = UnifiedImage.from_bytes(data, mime_type="image/png")
    llm = DeepSeekLLM(api_key="test-key", base_url="https://api.deepseek.com/v1", model="deepseek-vl")

    encoded = llm.encode_messages([MessageBuilder.user_text_with_image("describe", image)])

    assert isinstance(encoded[0]["content"], str)
    assert "![image](data:image/" in encoded[0]["content"]


def test_openai_llm_rejects_multiple_images_when_constraints_allow_single_only():
    image1 = UnifiedImage.from_bytes(_build_png_bytes((8, 8)), mime_type="image/png")
    image2 = UnifiedImage.from_bytes(_build_png_bytes((8, 8), color="blue"), mime_type="image/png")
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o")
    message = MessageBuilder.multimodal("user", text="compare", images=[image1, image2])

    try:
        llm.encode_messages([message])
    except TooManyImagesError:
        pass
    else:
        raise AssertionError("expected TooManyImagesError for multi-image input")


def test_factory_routes_deepseek_by_base_url():
    llm = get_llm(
        "openai",
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-vl",
    )

    assert isinstance(llm, DeepSeekLLM)


def test_service_chat_with_screenshot_builds_unified_multimodal_message():
    capture = CaptureLLM()
    service = Service({"screenshot": None}, llm=capture)
    screenshot = UnifiedImage.from_bytes(_build_png_bytes((10, 8)), mime_type="image/png").to_base64()

    import asyncio

    asyncio.run(service._chat_with_screenshot(capture, "describe", screenshot))

    content = capture.last_messages[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    assert isinstance(content[1]["image"], UnifiedImage)


def test_service_chat_with_screenshot_encodes_messages_for_raw_chat_fallback():
    raw_capture = RawCaptureLLM()
    service = Service({"screenshot": None}, llm=raw_capture)
    screenshot = UnifiedImage.from_bytes(_build_png_bytes((10, 8)), mime_type="image/png").to_base64()

    import asyncio

    asyncio.run(service._chat_with_screenshot(raw_capture, "describe", screenshot))

    content = raw_capture.last_messages[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_anomaly_guard_chat_with_screenshot_builds_unified_multimodal_message():
    capture = CaptureLLM()
    guard = UIAnomalyGuard(device=object(), llm=capture, vision_llm=capture)
    screenshot = UnifiedImage.from_bytes(_build_png_bytes((10, 8)), mime_type="image/png").to_base64()

    import asyncio

    asyncio.run(guard._chat_with_screenshot(capture, "detect", screenshot))

    content = capture.last_messages[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image"
    assert isinstance(content[1]["image"], UnifiedImage)


def test_anomaly_guard_chat_with_screenshot_encodes_messages_for_raw_chat_fallback():
    raw_capture = RawCaptureLLM()
    guard = UIAnomalyGuard(device=object(), llm=raw_capture, vision_llm=raw_capture)
    screenshot = UnifiedImage.from_bytes(_build_png_bytes((10, 8)), mime_type="image/png").to_base64()

    import asyncio

    asyncio.run(guard._chat_with_screenshot(raw_capture, "detect", screenshot))

    content = raw_capture.last_messages[0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_openai_capabilities_expose_image_constraints():
    llm = OpenAILLM(api_key="test-key", base_url="https://api.openai.com/v1", model="gpt-4o")
    assert llm.capabilities.supports_vision is True
    assert llm.capabilities.image_constraints == DEFAULT_IMAGE_CONSTRAINTS


def test_parse_relaxed_json_object_handles_wrapped_python_dict():
    text = """Here is the result:

```json
{'decision': 'dismiss', 'target_label': 'Cancel', 'target_bbox': {'left': 10, 'top': 12, 'right': 30, 'bottom': 40}}
```
"""
    parsed = parse_relaxed_json_object(text, context="test")

    assert parsed["decision"] == "dismiss"
    assert parsed["target_bbox"]["right"] == 30


def test_service_parse_json_response_handles_explanatory_text():
    service = Service({"screenshot": None}, llm=None)
    response = (
        "I found the target.\n"
        "Result: {'bbox': [11, 22, 33, 44], 'type': 'Input', 'description': '文本编辑器'}"
    )

    parsed = service._parse_json_response(response)

    assert parsed["bbox"] == [11, 22, 33, 44]
    assert parsed["type"] == "Input"


def test_service_sanitize_rect_to_context_clips_valid_bbox():
    service = Service({"screenshot": None}, llm=None)
    context = UIContext(screenshot="", shot_size={"width": 1280, "height": 720})

    rect = service._sanitize_rect_to_context(
        Rect(left=100, top=100, width=1300, height=700),
        context,
    )

    assert rect is not None
    assert rect.left == 100
    assert rect.top == 100
    assert rect.width == 1180
    assert rect.height == 620


def test_service_sanitize_rect_to_context_rejects_tiny_or_invalid_bbox():
    service = Service({"screenshot": None}, llm=None)
    context = UIContext(screenshot="", shot_size={"width": 1280, "height": 720})

    assert service._sanitize_rect_to_context(
        Rect(left=324, top=738, width=100, height=1),
        context,
    ) is None
    assert service._sanitize_rect_to_context(
        Rect(left=388, top=863, width=105, height=50),
        context,
    ) is None


def test_anomaly_guard_chat_json_handles_python_dict_response():
    llm = JsonTextLLM(
        "{'has_blocking_anomaly': True, 'confidence': 0.96, 'anomaly_kind': 'system_dialog', "
        "'candidate_actions': [{'label': 'Cancel', 'role': 'dismiss', 'bbox': {'left': 1, 'top': 2, 'right': 3, 'bottom': 4}}]}"
    )
    guard = UIAnomalyGuard(device=object(), llm=llm, vision_llm=llm)
    screenshot = UnifiedImage.from_bytes(_build_png_bytes((10, 8)), mime_type="image/png").to_base64()

    import asyncio

    parsed = asyncio.run(guard._chat_json(llm, "detect", screenshot))

    assert parsed["has_blocking_anomaly"] is True
    assert parsed["candidate_actions"][0]["label"] == "Cancel"


if __name__ == "__main__":
    test_default_image_preprocessor_resizes_large_image()
    test_default_image_preprocessor_converts_unsupported_mime_without_size_trigger()
    test_default_image_preprocessor_can_continue_resize_after_initial_resize()
    test_openai_llm_encodes_unified_image_to_image_url()
    test_deepseek_llm_encodes_unified_image_to_markdown()
    test_openai_llm_rejects_multiple_images_when_constraints_allow_single_only()
    test_factory_routes_deepseek_by_base_url()
    test_service_chat_with_screenshot_builds_unified_multimodal_message()
    test_service_chat_with_screenshot_encodes_messages_for_raw_chat_fallback()
    test_anomaly_guard_chat_with_screenshot_builds_unified_multimodal_message()
    test_anomaly_guard_chat_with_screenshot_encodes_messages_for_raw_chat_fallback()
    test_openai_capabilities_expose_image_constraints()
    test_parse_relaxed_json_object_handles_wrapped_python_dict()
    test_service_parse_json_response_handles_explanatory_text()
    test_service_sanitize_rect_to_context_clips_valid_bbox()
    test_service_sanitize_rect_to_context_rejects_tiny_or_invalid_bbox()
    test_anomaly_guard_chat_json_handles_python_dict_response()
    print("test_llm_provider_flow.py: ok")
