from __future__ import annotations

import base64
import os
import sys
from io import BytesIO

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from llm import MessageBuilder, UnifiedImage


def _build_png_bytes(size: tuple[int, int] = (2, 3), color: str = "red") -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_unified_image_from_bytes_preserves_size_and_encoding():
    data = _build_png_bytes((4, 5))

    image = UnifiedImage.from_bytes(data, mime_type="image/png")

    assert image.width == 4
    assert image.height == 5
    assert image.byte_size == len(data)
    assert base64.b64decode(image.to_base64()) == data


def test_message_builder_user_text_returns_plain_text_message():
    message = MessageBuilder.user_text("hello")

    assert message == {"role": "user", "content": "hello"}


def test_message_builder_user_text_with_image_base64_builds_multimodal_message():
    data = _build_png_bytes((3, 2))
    image_b64 = base64.b64encode(data).decode("utf-8")

    message = MessageBuilder.user_text_with_image_base64(
        "describe image",
        image_b64,
        mime_type="image/png",
    )

    assert message["role"] == "user"
    assert isinstance(message["content"], list)
    assert message["content"][0] == {"type": "text", "text": "describe image"}
    assert message["content"][1]["type"] == "image"
    unified_image = message["content"][1]["image"]
    assert isinstance(unified_image, UnifiedImage)
    assert unified_image.width == 3
    assert unified_image.height == 2


def test_message_builder_multimodal_requires_text_or_images():
    try:
        MessageBuilder.multimodal("user")
    except ValueError as exc:
        assert "requires text or images" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty multimodal message")


if __name__ == "__main__":
    test_unified_image_from_bytes_preserves_size_and_encoding()
    test_message_builder_user_text_returns_plain_text_message()
    test_message_builder_user_text_with_image_base64_builds_multimodal_message()
    test_message_builder_multimodal_requires_text_or_images()
    print("test_llm_message_builder.py: ok")
