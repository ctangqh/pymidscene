from typing import Optional, Dict, Any
from .base import BaseLLM
from .openai import OpenAILLM
from common.config import settings
from common.exceptions import ModelUnsupportedError


class LLMFactory:
    """LLM 实例工厂"""
    
    _providers: Dict[str, type[BaseLLM]] = {
        "openai": OpenAILLM,
        # 后续可以在这里添加更多模型提供商
        # "doubao": DoubaoLLM,
        # "qwen": QwenLLM,
        # "glm": GLMLLM,
    }
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type[BaseLLM]) -> None:
        """注册新的模型提供商"""
        cls._providers[name.lower()] = provider_class
    
    @classmethod
    def create(
        cls, provider: Optional[str] = None, **kwargs) -> BaseLLM:
        """
        创建 LLM 实例
        :param provider: 模型提供商，不传则使用默认配置
        :param kwargs: 额外参数，会传递给对应模型的构造函数
        :return: LLM 实例
        """
        provider = (provider or settings.DEFAULT_LLM_PROVIDER).lower()
        
        if provider not in cls._providers:
            raise ModelUnsupportedError(f"不支持的 LLM 提供商：{provider}，支持的提供商：{list(cls._providers.keys())}")
        
        return cls._providers[provider](**kwargs)


# 快捷方法
def get_llm(provider: Optional[str] = None, **kwargs) -> BaseLLM:
    """获取 LLM 实例"""
    return LLMFactory.create(provider, **kwargs)
