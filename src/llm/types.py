from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from PIL import Image


@dataclass
class UnifiedImage:
    """统一图片对象，供多模态消息在进入 provider 前使用。"""

    data: bytes
    mime_type: str
    width: int
    height: int
    source: str = "inline"
    file_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        mime_type: str = "image/png",
        source: str = "inline",
        file_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "UnifiedImage":
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
        return cls(
            data=data,
            mime_type=mime_type,
            width=width,
            height=height,
            source=source,
            file_name=file_name,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_base64(
        cls,
        data: str,
        mime_type: str = "image/png",
        source: str = "inline",
        file_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "UnifiedImage":
        return cls.from_bytes(
            base64.b64decode(data),
            mime_type=mime_type,
            source=source,
            file_name=file_name,
            metadata=metadata,
        )

    @property
    def byte_size(self) -> int:
        return len(self.data)

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("utf-8")


@dataclass
class ImageConstraints:
    max_file_bytes: int | None = None
    max_width: int | None = None
    max_height: int | None = None
    max_images: int | None = 1
    allowed_mime_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp")
    auto_resize: bool = True
    auto_compress: bool = True
    auto_convert_to_jpeg: bool = True


@dataclass
class ImagePreprocessPolicy:
    enable_resize: bool = True
    enable_compress: bool = True
    enable_convert: bool = True
    preferred_output_mime: str | None = "image/jpeg"
    jpeg_quality: int = 85
    min_jpeg_quality: int = 60
    resize_long_edge_step: float = 0.85
    preserve_transparency: bool = False


@dataclass
class ImagePreprocessResult:
    image: UnifiedImage
    original_mime_type: str
    original_width: int
    original_height: int
    original_bytes: int
    final_mime_type: str
    final_width: int
    final_height: int
    final_bytes: int
    resized: bool = False
    compressed: bool = False
    converted: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ModelCapabilities:
    supports_text: bool = True
    supports_vision: bool = False
    supports_structured_output: bool = False
    supports_system_prompt: bool = True
    supports_tool_calling: bool = False
    supports_data_url: bool = False
    supports_multiple_images: bool = False
    image_constraints: ImageConstraints | None = None


DEFAULT_IMAGE_CONSTRAINTS = ImageConstraints(
    max_file_bytes=4 * 1024 * 1024,
    max_width=2048,
    max_height=2048,
    max_images=1,
    allowed_mime_types=("image/png", "image/jpeg", "image/webp"),
    auto_resize=True,
    auto_compress=True,
    auto_convert_to_jpeg=True,
)

DEFAULT_IMAGE_POLICY = ImagePreprocessPolicy(
    enable_resize=True,
    enable_compress=True,
    enable_convert=True,
    preferred_output_mime="image/jpeg",
    jpeg_quality=85,
    min_jpeg_quality=60,
    resize_long_edge_step=0.85,
    preserve_transparency=False,
)


__all__ = [
    "UnifiedImage",
    "ImageConstraints",
    "ImagePreprocessPolicy",
    "ImagePreprocessResult",
    "ModelCapabilities",
    "DEFAULT_IMAGE_CONSTRAINTS",
    "DEFAULT_IMAGE_POLICY",
]
