from __future__ import annotations

from dataclasses import replace
from io import BytesIO

from PIL import Image

from common.exceptions import (
    ImagePreprocessFailedError,
    ImageTooLargeError,
    TooManyImagesError,
    UnsupportedImageMimeTypeError,
)
from common.logger import logger
from .types import (
    DEFAULT_IMAGE_CONSTRAINTS,
    DEFAULT_IMAGE_POLICY,
    ImageConstraints,
    ImagePreprocessPolicy,
    ImagePreprocessResult,
    UnifiedImage,
)


_MIME_TO_PIL_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


class DefaultImagePreprocessor:
    """默认图片预处理器，负责约束校验与保守压缩。"""

    def prepare(
        self,
        image: UnifiedImage,
        constraints: ImageConstraints | None = None,
        policy: ImagePreprocessPolicy | None = None,
    ) -> ImagePreprocessResult:
        constraints = constraints or DEFAULT_IMAGE_CONSTRAINTS
        policy = policy or DEFAULT_IMAGE_POLICY

        try:
            self._validate_mime(image, constraints)
            processed = replace(image)
            notes: list[str] = []
            resized = False
            compressed = False
            converted = False

            if self._needs_mime_convert(processed, constraints):
                if not (constraints.auto_convert_to_jpeg and policy.enable_convert):
                    raise UnsupportedImageMimeTypeError(
                        "图片 MIME 类型不在 provider 允许范围内，且当前策略不允许自动转码",
                        data={"mime_type": processed.mime_type, "allowed": constraints.allowed_mime_types},
                    )
                processed = self._convert_to_preferred_mime(processed, policy)
                notes.append(f"converted unsupported mime {image.mime_type} -> {processed.mime_type}")
                converted = True

            if self._needs_resize(processed, constraints):
                if not (constraints.auto_resize and policy.enable_resize):
                    raise ImageTooLargeError(
                        "图片尺寸超过 provider 限制且当前策略不允许自动缩放",
                        data={
                            "width": processed.width,
                            "height": processed.height,
                            "max_width": constraints.max_width,
                            "max_height": constraints.max_height,
                        },
                    )
                processed = self._resize_to_constraints(processed, constraints, notes)
                resized = True

            if self._needs_bytes_reduce(processed, constraints):
                if not (constraints.auto_compress and policy.enable_compress):
                    raise ImageTooLargeError(
                        "图片体积超过 provider 限制且当前策略不允许自动压缩",
                        data={
                            "byte_size": processed.byte_size,
                            "max_file_bytes": constraints.max_file_bytes,
                        },
                    )
                processed, compressed, converted = self._reduce_bytes(
                    processed,
                    constraints,
                    policy,
                    notes,
                    resized=resized,
                )

            self._ensure_constraints(processed, constraints)
            result = ImagePreprocessResult(
                image=processed,
                original_mime_type=image.mime_type,
                original_width=image.width,
                original_height=image.height,
                original_bytes=image.byte_size,
                final_mime_type=processed.mime_type,
                final_width=processed.width,
                final_height=processed.height,
                final_bytes=processed.byte_size,
                resized=resized,
                compressed=compressed,
                converted=converted,
                notes=notes,
            )
            self._log_result(result)
            return result
        except (UnsupportedImageMimeTypeError, ImageTooLargeError):
            raise
        except Exception as e:
            raise ImagePreprocessFailedError(f"图片预处理失败: {e}") from e

    def prepare_many(
        self,
        images: list[UnifiedImage],
        constraints: ImageConstraints | None = None,
        policy: ImagePreprocessPolicy | None = None,
    ) -> list[ImagePreprocessResult]:
        constraints = constraints or DEFAULT_IMAGE_CONSTRAINTS
        if constraints.max_images is not None and len(images) > constraints.max_images:
            raise TooManyImagesError(
                "图片数量超过 provider 限制",
                data={"count": len(images), "max_images": constraints.max_images},
            )
        return [self.prepare(image, constraints=constraints, policy=policy) for image in images]

    def _validate_mime(self, image: UnifiedImage, constraints: ImageConstraints) -> None:
        if image.mime_type not in constraints.allowed_mime_types:
            if not constraints.auto_convert_to_jpeg:
                raise UnsupportedImageMimeTypeError(
                    "图片 MIME 类型不在 provider 允许范围内",
                    data={"mime_type": image.mime_type, "allowed": constraints.allowed_mime_types},
                )

    def _needs_mime_convert(self, image: UnifiedImage, constraints: ImageConstraints) -> bool:
        return image.mime_type not in constraints.allowed_mime_types

    def _needs_resize(self, image: UnifiedImage, constraints: ImageConstraints) -> bool:
        if constraints.max_width and image.width > constraints.max_width:
            return True
        if constraints.max_height and image.height > constraints.max_height:
            return True
        return False

    def _needs_bytes_reduce(self, image: UnifiedImage, constraints: ImageConstraints) -> bool:
        return constraints.max_file_bytes is not None and image.byte_size > constraints.max_file_bytes

    def _ensure_constraints(self, image: UnifiedImage, constraints: ImageConstraints) -> None:
        self._validate_mime(image, replace(constraints, auto_convert_to_jpeg=False))
        if self._needs_resize(image, constraints):
            raise ImageTooLargeError(
                "图片尺寸仍超出 provider 限制",
                data={
                    "width": image.width,
                    "height": image.height,
                    "max_width": constraints.max_width,
                    "max_height": constraints.max_height,
                },
            )
        if self._needs_bytes_reduce(image, constraints):
            raise ImageTooLargeError(
                "图片体积仍超出 provider 限制",
                data={"byte_size": image.byte_size, "max_file_bytes": constraints.max_file_bytes},
            )

    def _resize_to_constraints(
        self,
        image: UnifiedImage,
        constraints: ImageConstraints,
        notes: list[str],
    ) -> UnifiedImage:
        target_width = constraints.max_width or image.width
        target_height = constraints.max_height or image.height
        with Image.open(BytesIO(image.data)) as pil_image:
            pil_image = pil_image.copy()
            pil_image.thumbnail((target_width, target_height))
            resized = self._save_image(
                pil_image,
                mime_type=image.mime_type,
                file_name=image.file_name,
                metadata=image.metadata,
            )
        notes.append(
            f"resized {image.width}x{image.height} -> {resized.width}x{resized.height}"
        )
        return resized

    def _reduce_bytes(
        self,
        image: UnifiedImage,
        constraints: ImageConstraints,
        policy: ImagePreprocessPolicy,
        notes: list[str],
        resized: bool,
    ) -> tuple[UnifiedImage, bool, bool]:
        max_bytes = constraints.max_file_bytes or image.byte_size
        converted = False
        compressed = False
        current = image

        if (
            current.mime_type != "image/jpeg"
            and constraints.auto_convert_to_jpeg
            and policy.enable_convert
            and policy.preferred_output_mime == "image/jpeg"
        ):
            current = self._convert_to_jpeg(current, policy.jpeg_quality)
            notes.append("converted image to JPEG for byte reduction")
            converted = True
            compressed = True
            if current.byte_size <= max_bytes:
                return current, compressed, converted

        quality = policy.jpeg_quality
        while current.byte_size > max_bytes and quality >= policy.min_jpeg_quality:
            if current.mime_type != "image/jpeg":
                current = self._convert_to_jpeg(current, quality)
                converted = True
            else:
                current = self._resave_jpeg(current, quality)
            notes.append(f"compressed image with jpeg quality={quality}")
            compressed = True
            if current.byte_size <= max_bytes:
                return current, compressed, converted
            quality -= 5

        while current.byte_size > max_bytes and policy.enable_resize:
            next_width = max(1, int(current.width * policy.resize_long_edge_step))
            next_height = max(1, int(current.height * policy.resize_long_edge_step))
            if next_width == current.width and next_height == current.height:
                break
            with Image.open(BytesIO(current.data)) as pil_image:
                pil_image = pil_image.copy()
                pil_image.thumbnail((next_width, next_height))
                current = self._save_image(
                    pil_image,
                    mime_type=current.mime_type,
                    jpeg_quality=max(policy.min_jpeg_quality, quality),
                    file_name=current.file_name,
                    metadata=current.metadata,
                )
            notes.append(f"resized for byte reduction -> {current.width}x{current.height}")
            compressed = True
            if current.byte_size <= max_bytes:
                break

        return current, compressed, converted

    def _convert_to_preferred_mime(self, image: UnifiedImage, policy: ImagePreprocessPolicy) -> UnifiedImage:
        target_mime = policy.preferred_output_mime or "image/jpeg"
        if target_mime == "image/jpeg":
            return self._convert_to_jpeg(image, policy.jpeg_quality)
        with Image.open(BytesIO(image.data)) as pil_image:
            return self._save_image(
                pil_image.copy(),
                mime_type=target_mime,
                file_name=image.file_name,
                metadata=image.metadata,
            )

    def _convert_to_jpeg(self, image: UnifiedImage, quality: int) -> UnifiedImage:
        with Image.open(BytesIO(image.data)) as pil_image:
            pil_image = self._flatten_if_needed(pil_image)
            return self._save_image(
                pil_image,
                mime_type="image/jpeg",
                jpeg_quality=quality,
                file_name=image.file_name,
                metadata=image.metadata,
            )

    def _resave_jpeg(self, image: UnifiedImage, quality: int) -> UnifiedImage:
        with Image.open(BytesIO(image.data)) as pil_image:
            pil_image = pil_image.convert("RGB")
            return self._save_image(
                pil_image,
                mime_type="image/jpeg",
                jpeg_quality=quality,
                file_name=image.file_name,
                metadata=image.metadata,
            )

    def _save_image(
        self,
        pil_image: Image.Image,
        mime_type: str,
        jpeg_quality: int = 85,
        file_name: str | None = None,
        metadata: dict | None = None,
    ) -> UnifiedImage:
        output = BytesIO()
        format_name = _MIME_TO_PIL_FORMAT.get(mime_type, "PNG")
        save_kwargs = {}
        working = pil_image
        if format_name == "JPEG":
            working = self._flatten_if_needed(working)
            save_kwargs["quality"] = jpeg_quality
            save_kwargs["optimize"] = True
        working.save(output, format=format_name, **save_kwargs)
        return UnifiedImage.from_bytes(
            output.getvalue(),
            mime_type=mime_type,
            source="inline",
            file_name=file_name,
            metadata=dict(metadata or {}),
        )

    def _flatten_if_needed(self, image: Image.Image) -> Image.Image:
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
            return background
        return image.convert("RGB")

    def _log_result(self, result: ImagePreprocessResult) -> None:
        if not (result.resized or result.compressed or result.converted):
            return
        logger.debug(
            "Image preprocessed: {} {}x{}/{}B -> {} {}x{}/{}B notes={}",
            result.original_mime_type,
            result.original_width,
            result.original_height,
            result.original_bytes,
            result.final_mime_type,
            result.final_width,
            result.final_height,
            result.final_bytes,
            result.notes,
        )
