from __future__ import annotations

from typing import Any, Iterable

from .types import UnifiedImage


class MessageBuilder:
    """统一消息构造器，输出与现有调用链兼容的消息字典。"""

    @staticmethod
    def text_block(text: str) -> dict[str, Any]:
        return {"type": "text", "text": text}

    @staticmethod
    def image_block(image: UnifiedImage) -> dict[str, Any]:
        return {"type": "image", "image": image}

    @classmethod
    def build_message(cls, role: str, content: str | list[dict[str, Any]]) -> dict[str, Any]:
        return {"role": role, "content": content}

    @classmethod
    def user_text(cls, text: str) -> dict[str, Any]:
        return cls.build_message("user", text)

    @classmethod
    def system_text(cls, text: str) -> dict[str, Any]:
        return cls.build_message("system", text)

    @classmethod
    def assistant_text(cls, text: str) -> dict[str, Any]:
        return cls.build_message("assistant", text)

    @classmethod
    def multimodal(
        cls,
        role: str,
        text: str | None = None,
        images: Iterable[UnifiedImage] | None = None,
    ) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if text is not None:
            content.append(cls.text_block(text))
        if images:
            for image in images:
                content.append(cls.image_block(image))
        if not content:
            raise ValueError("multimodal message requires text or images")
        return cls.build_message(role, content)

    @classmethod
    def user_text_with_image(cls, text: str, image: UnifiedImage) -> dict[str, Any]:
        return cls.multimodal("user", text=text, images=[image])

    @classmethod
    def user_text_with_image_base64(
        cls,
        text: str,
        image_base64: str,
        mime_type: str = "image/png",
        source: str = "inline",
        file_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        image = UnifiedImage.from_base64(
            image_base64,
            mime_type=mime_type,
            source=source,
            file_name=file_name,
            metadata=metadata,
        )
        return cls.user_text_with_image(text, image)
