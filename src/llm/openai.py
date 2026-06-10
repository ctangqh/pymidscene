from typing import List, Dict, Any

from openai import OpenAI
from .base import BaseLLM
from .types import ModelCapabilities, DEFAULT_IMAGE_CONSTRAINTS
from common.config import settings
from common.exceptions import MissingAPIKeyError


class OpenAILLM(BaseLLM):
    """OpenAI 模型实现"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        llm_config = settings.llm_config

        self.api_key = self.api_key or llm_config.api_key
        if not self.api_key:
            raise MissingAPIKeyError("LLM_API_KEY / OPENAI_API_KEY 未配置")
        
        self.base_url = self.base_url or llm_config.base_url
        self.model = self.model or llm_config.model
        
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

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

            encoded_content: List[Dict[str, Any]] = []
            image_slots: List[int] = []
            images = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    encoded_content.append({"type": "text", "text": str(part.get("text") or "")})
                    continue
                if ptype == "image":
                    image = part.get("image")
                    if image is None:
                        continue
                    image_slots.append(len(encoded_content))
                    encoded_content.append({"type": "image_url", "image_url": {"url": ""}})
                    images.append(image)
                    continue
                if ptype == "image_url":
                    encoded_content.append(part)
                    continue
                encoded_content.append(part)

            if images:
                prepared_images = self.prepare_images(images)
                for slot, result in zip(image_slots, prepared_images):
                    encoded_content[slot] = {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{result.image.mime_type};base64,{result.image.to_base64()}"
                        },
                    }

            msg2 = dict(msg)
            msg2["content"] = encoded_content
            encoded.append(msg2)
        return encoded
    
    def _chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            temperature=kwargs.get("temperature", 0.1),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        msg = response.choices[0].message
        content = (getattr(msg, "content", None) or "").strip()
        if not content:
            reasoning = getattr(msg, "reasoning_content", None)
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning.strip()
        return content
