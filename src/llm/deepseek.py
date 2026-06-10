from __future__ import annotations

from typing import Any, Dict, List

from .openai import OpenAILLM
from .types import ModelCapabilities, DEFAULT_IMAGE_CONSTRAINTS


class DeepSeekLLM(OpenAILLM):
    """DeepSeek 模型实现，复用 OpenAI 客户端并覆盖多模态编码。"""

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(
            supports_text=True,
            supports_vision=True,
            supports_structured_output=False,
            supports_system_prompt=True,
            supports_tool_calling=False,
            supports_data_url=True,
            supports_multiple_images=False,
            image_constraints=DEFAULT_IMAGE_CONSTRAINTS,
        )

    def encode_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        encoded: List[Dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list):
                encoded.append(msg)
                continue

            parts: List[str] = []
            images = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    text = str(part.get("text") or "").strip()
                    if text:
                        parts.append(text)
                    continue
                if ptype == "image":
                    image = part.get("image")
                    if image is None:
                        continue
                    images.append(image)
                    continue
                if ptype == "image_url":
                    image_url = part.get("image_url") or {}
                    url = image_url.get("url") if isinstance(image_url, dict) else None
                    if isinstance(url, str) and url.strip():
                        parts.append(f"![image]({url.strip()})")
                    continue

            if images:
                for result in self.prepare_images(images):
                    parts.append(f"![image](data:{result.image.mime_type};base64,{result.image.to_base64()})")

            msg2 = dict(msg)
            msg2["content"] = "\n\n".join(parts).strip()
            encoded.append(msg2)
        return encoded
