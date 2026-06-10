from typing import List, Dict, Any
from openai import OpenAI
from .base import BaseLLM
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
    
    def _chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            temperature=kwargs.get("temperature", 0.1),
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        return response.choices[0].message.content.strip()
