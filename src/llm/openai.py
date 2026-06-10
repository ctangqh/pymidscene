import base64
from typing import List, Dict, Any

from openai import OpenAI
from .base import BaseLLM
from common.config import settings
from common.exceptions import MissingAPIKeyError


def _convert_openai_multimodal_to_deepseek(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted: List[Dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            converted.append(msg)
            continue

        parts: List[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
                continue
            if ptype == "image_url":
                image_url = part.get("image_url") or {}
                url = image_url.get("url") if isinstance(image_url, dict) else None
                url = url if isinstance(url, str) else ""
                if url.startswith("data:") and ";base64," in url:
                    b64 = url.split(";base64,", 1)[1]
                    try:
                        base64.b64decode(b64, validate=False)
                        parts.append(f"![image]({url})")
                        continue
                    except Exception:
                        pass
                if url:
                    parts.append(f"![image]({url})")
                continue

        msg2 = dict(msg)
        msg2["content"] = "\n\n".join(parts).strip()
        converted.append(msg2)
    return converted


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
    
    def _chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        base_url = (self.base_url or "").lower()
        if "api.deepseek.com" in base_url:
            messages = _convert_openai_multimodal_to_deepseek(messages)
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
