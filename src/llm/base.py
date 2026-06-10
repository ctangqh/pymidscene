from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type
import json
from copy import deepcopy
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from common.config import settings
from common.exceptions import ModelTimeoutError, ModelResponseError
from common.logger import logger
from .image_preprocessor import DefaultImagePreprocessor
from .types import (
    DEFAULT_IMAGE_CONSTRAINTS,
    DEFAULT_IMAGE_POLICY,
    ImageConstraints,
    ImagePreprocessPolicy,
    ImagePreprocessResult,
    ModelCapabilities,
    UnifiedImage,
)


class BaseLLM(ABC):
    """LLM 模型抽象基类"""

    image_preprocessor_cls = DefaultImagePreprocessor
    
    def __init__(
        self,
        api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = kwargs.get("timeout", settings.MODEL_TIMEOUT)
        self.max_retries = kwargs.get("max_retries", settings.MODEL_MAX_RETRIES)
        self.image_preprocessor = kwargs.get("image_preprocessor") or self.image_preprocessor_cls()
        self._image_policy = kwargs.get("image_policy")

    @property
    def capabilities(self) -> ModelCapabilities:
        """默认能力声明，子类可按需覆盖。"""
        return ModelCapabilities(supports_text=True)

    @property
    def image_constraints(self) -> ImageConstraints:
        return self.capabilities.image_constraints or DEFAULT_IMAGE_CONSTRAINTS

    @property
    def image_policy(self) -> ImagePreprocessPolicy:
        return self._image_policy or DEFAULT_IMAGE_POLICY

    def prepare_image(self, image: UnifiedImage) -> ImagePreprocessResult:
        return self.image_preprocessor.prepare(
            image=image,
            constraints=self.image_constraints,
            policy=self.image_policy,
        )

    def prepare_images(self, images: List[UnifiedImage]) -> List[ImagePreprocessResult]:
        return self.image_preprocessor.prepare_many(
            images=images,
            constraints=self.image_constraints,
            policy=self.image_policy,
        )

    def encode_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """默认直接透传消息；子类可覆盖以编码统一多模态结构。"""
        return messages
    
    @abstractmethod
    def _chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """底层聊天接口，子类实现"""
        pass
    
    @retry(
        stop=stop_after_attempt(settings.MODEL_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ModelTimeoutError, ConnectionError)),
        before_sleep=lambda retry_state: logger.warning(f"模型调用第 {retry_state.attempt_number} 次失败，正在重试..."),
    )
    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        """
        通用聊天接口，带重试机制
        :param messages: 消息列表，格式为 [{"role": "user", "content": "xxx"}, ...]
        :return: 模型返回的文本结果
        """
        try:
            logger.debug(f"调用 {self.__class__.__name__} 模型，消息长度：{len(str(messages))} 字符")
            response = self._chat(self.encode_messages(messages), **kwargs)
            logger.debug(f"模型返回结果：{response[:200]}{'...' if len(response) > 200 else ''}")
            return response
        except TimeoutError as e:
            raise ModelTimeoutError(f"模型调用超时: {str(e)}") from e
        except Exception as e:
            logger.error(f"模型调用失败: {str(e)}")
            raise ModelResponseError(f"模型调用失败: {str(e)}") from e
    
    def structured_chat(
        self, messages: List[Dict[str, Any]], output_schema: Type[BaseModel], **kwargs
    ) -> BaseModel:
        """
        结构化输出聊天接口，返回指定的结果符合指定的 Pydantic 模型
        :param messages: 消息列表
        :param output_schema: 输出的 Pydantic 模型类
        :return: 解析后的 Pydantic 模型实例
        """
        schema_prompt = "请严格按照以下 JSON Schema 返回结果，只返回合法 JSON，不要添加任何其他内容：\n"
        schema_prompt += "```json\n"
        schema_prompt += json.dumps(output_schema.model_json_schema(), ensure_ascii=False)
        schema_prompt += "\n```\n"
        
        # 插入到最后一条消息前面
        messages = deepcopy(messages)
        last_msg = dict(messages[-1])
        content = last_msg.get("content")
        if isinstance(content, str):
            last_msg["content"] = content + "\n" + schema_prompt
        elif isinstance(content, list):
            if content and isinstance(content[-1], dict) and content[-1].get("type") == "text":
                content[-1] = dict(content[-1])
                content[-1]["text"] = str(content[-1].get("text") or "") + "\n" + schema_prompt
            else:
                content.append({"type": "text", "text": schema_prompt})
            last_msg["content"] = content
        else:
            last_msg["content"] = schema_prompt
        messages[-1] = last_msg
        
        response = self.chat(messages, **kwargs)
        
        # 解析 JSON 结果
        try:
            try:
                import json_repair
                json_data = json_repair.loads(response)
            except ImportError:
                import json as _json
                import re
                json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
                json_str = json_match.group(1) if json_match else response
                json_data = _json.loads(json_str)
            return output_schema.model_validate(json_data)
        except Exception as e:
            logger.error(f"结构化输出解析失败: {str(e)}, 原始返回: {response}")
            raise ModelResponseError(f"结构化输出解析失败: {str(e)}") from e
