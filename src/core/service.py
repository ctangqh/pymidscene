import asyncio
import base64
import json
import time
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple, Union, Callable

from .types import (
    DetailedLocateParam, LocateResultElement, LocateResultWithDump,
    ServiceExtractOption, ServiceExtractParam, ServiceDump,
    UIContext, AIUsageInfo, Rect, ElementCacheFeature,
)
from common.json_utils import parse_relaxed_json_object
from common.logger import logger
from common.exceptions import ModelResponseError, ElementNotFoundError
from llm import MessageBuilder


class ServiceError(Exception):
    """Error from service operations, includes dump data"""
    def __init__(self, message: str, dump: Optional[ServiceDump] = None):
        super().__init__(message)
        self.dump = dump


class Service:
    """
    AI service layer for locate, extract, and describe operations.
    Wraps LLM calls with proper prompts and result parsing.
    Port of TS Service class.
    """
    
    def __init__(self, context: Union[UIContext, Callable], opt: Optional[Dict] = None, llm=None):
        if callable(context):
            self.context_retriever_fn = context
        else:
            self.context_retriever_fn = lambda: context
        
        self.llm = llm
        self.task_info = opt.get("task_info") if opt else None
    
    async def locate(
        self,
        query: Union[str, DetailedLocateParam],
        opt: Optional[Dict] = None,
        model_runtime=None,
        abort_signal=None,
    ) -> LocateResultWithDump:
        """
        Locate an element using AI.
        
        Args:
            query: Locate parameter (prompt + options)
            opt: Options dict with "context" UIContext
            model_runtime: Model runtime (LLM instance)
            abort_signal: Optional abort signal
        
        Returns:
            LocateResultWithDump with element info and dump
        """
        opt = opt or {}
        
        # Normalize query
        if isinstance(query, str):
            query = DetailedLocateParam(prompt=query)
        elif isinstance(query, dict):
            query = DetailedLocateParam(**query)
        
        query_prompt = query.prompt if isinstance(query.prompt, str) else str(query.prompt)
        if not query_prompt:
            raise ValueError("query prompt is required for locate")
        
        context = opt.get("context") or await self._get_context()
        if not context:
            raise ValueError("context is required for locate")
        
        start_time = time.time()
        
        try:
            # Use the model runtime to locate the element
            if model_runtime and hasattr(model_runtime, 'locate_element'):
                result = await model_runtime.locate_element(context, query_prompt, query)
                element = result.get("element")
            else:
                # Fallback: use LLM structured chat to locate
                element = await self._locate_via_llm(context, query_prompt, model_runtime)
            
            time_cost = int((time.time() - start_time) * 1000)
            
            dump = ServiceDump(task_info={
                "durationMs": time_cost,
                "usage": None,
            })
            
            if element:
                return LocateResultWithDump(
                    element=element,
                    dump=dump,
                )
            
            return LocateResultWithDump(element=None, dump=dump)
            
        except ServiceError:
            raise
        except Exception as e:
            time_cost = int((time.time() - start_time) * 1000)
            dump = ServiceDump(task_info={"durationMs": time_cost})
            raise ServiceError(f"Locate failed: {e}", dump) from e
    
    async def _locate_via_llm(
        self,
        context: UIContext,
        query_prompt: str,
        model_runtime=None,
    ) -> Optional[LocateResultElement]:
        llm = model_runtime or self.llm
        if not llm:
            logger.debug("No LLM configured for locate")
            return None
        if not context.screenshot:
            raise ValueError("screenshot is required for LLM locate")

        width = context.shot_size.get("width", 0) if context.shot_size else 0
        height = context.shot_size.get("height", 0) if context.shot_size else 0
        prompt = (
            "You are a UI element locator. Analyze the screenshot and find the element matching the user query.\n"
            f"Screenshot size: width={width}, height={height}. Coordinates must be in screenshot pixels.\n"
            f"User query: {query_prompt}\n\n"
            "Return only valid JSON in this exact shape: "
            "{\"bbox\": [left, top, right, bottom], \"type\": \"Button/Input/Link/Text/etc\", \"description\": \"short description\"}.\n"
            "If multiple elements match, return the best one.\n"
            "If no element matches, return {\"bbox\": null, \"type\": null, \"description\": \"no match found\"}."
        )
        response = await self._chat_with_screenshot(llm, prompt, context.screenshot, max_tokens=1024)
        payload = self._parse_json_response(response)
        bbox = payload.get("bbox")
        if not bbox:
            return None
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ModelResponseError(f"Invalid locate bbox from model: {bbox}")

        left, top, right, bottom = [float(v) for v in bbox]
        if right < left:
            left, right = right, left
        if bottom < top:
            top, bottom = bottom, top
        rect = Rect(left=left, top=top, width=max(0.0, right - left), height=max(0.0, bottom - top))
        return LocateResultElement(
            center=(rect.left + rect.width / 2, rect.top + rect.height / 2),
            rect=rect,
            el_type=str(payload.get("type") or "element"),
            description=str(payload.get("description") or query_prompt),
        )
    
    async def extract(
        self,
        data_demand: Any,
        model_runtime=None,
        opt: Optional[ServiceExtractOption] = None,
        extra_page_description: str = "",
        multimodal_prompt=None,
        context: Optional[UIContext] = None,
    ) -> Dict[str, Any]:
        """
        Extract information from the page using AI.
        
        Args:
            data_demand: What to extract (string or structured demand)
            model_runtime: Model runtime
            opt: Extract options
            extra_page_description: Additional page description from DOM
            multimodal_prompt: Optional multimodal prompt
            context: UI context
        
        Returns:
            Dict with "data", "thought", "usage", "dump"
        """
        opt = opt or ServiceExtractOption()
        if not context:
            context = await self._get_context()
        
        if not context:
            raise ValueError("context is required for extract")
        
        start_time = time.time()
        
        try:
            if model_runtime and hasattr(model_runtime, 'extract_info'):
                result = await model_runtime.extract_info(context, data_demand, opt)
            else:
                result = await self._extract_via_llm(context, data_demand, opt, model_runtime)
            
            time_cost = int((time.time() - start_time) * 1000)
            
            dump = ServiceDump(task_info={
                "durationMs": time_cost,
                "usage": result.get("usage"),
            })
            
            return {
                "data": result.get("data"),
                "thought": result.get("thought"),
                "usage": result.get("usage"),
                "reasoning_content": result.get("reasoning_content"),
                "dump": dump,
            }
            
        except ServiceError:
            raise
        except Exception as e:
            time_cost = int((time.time() - start_time) * 1000)
            dump = ServiceDump(task_info={"durationMs": time_cost})
            raise ServiceError(f"Extract failed: {e}", dump) from e
    
    async def _extract_via_llm(
        self,
        context: UIContext,
        data_demand: Any,
        opt: ServiceExtractOption,
        model_runtime=None,
    ) -> Dict[str, Any]:
        llm = model_runtime or self.llm
        if not llm:
            logger.debug("No LLM configured for extract")
            return {"data": None, "thought": "", "usage": None}
        if opt.screenshot_included and not context.screenshot:
            raise ValueError("screenshot is required for LLM extract")

        demand_text = self._format_data_demand(data_demand)
        prompt = (
            "You are a UI information extractor. Analyze the current page screenshot and answer the extraction demand.\n"
            f"Demand:\n{demand_text}\n\n"
            "Return only valid JSON in this exact shape: {\"data\": extracted_value, \"thought\": \"brief reasoning\"}.\n"
            "If the demand asks for a boolean/assertion/wait condition, data must be true or false. "
            "If it asks for a string, data must be a string. Preserve the requested structure for schema-like demands."
        )
        if opt.screenshot_included:
            response = await self._chat_with_screenshot(llm, prompt, context.screenshot)
        else:
            response = await self._chat_with_screenshot(llm, prompt, context.screenshot or None)
        payload = self._parse_json_response(response)
        data = payload.get("data")
        return {
            "data": self._coerce_extracted_data(data, data_demand),
            "thought": payload.get("thought", ""),
            "usage": None,
        }
    
    async def describe(
        self,
        target: Union[Rect, Tuple[int, int]],
        model_runtime=None,
        opt: Optional[Dict] = None,
    ) -> Dict[str, str]:
        """
        Describe an element at a given position.
        
        Args:
            target: Rect or center point [x, y]
            model_runtime: Model runtime
            opt: Options with optional "deep_locate"
        
        Returns:
            Dict with "description"
        """
        opt = opt or {}
        context = await self._get_context()
        
        if not context:
            raise ValueError("context is required for describe")
        
        # Convert [x,y] center point to Rect if needed
        default_rect_size = 30
        if isinstance(target, (list, tuple)) and len(target) == 2:
            target_rect = Rect(
                left=target[0] - default_rect_size // 2,
                top=target[1] - default_rect_size // 2,
                width=default_rect_size,
                height=default_rect_size,
            )
        elif isinstance(target, Rect):
            target_rect = target
        else:
            raise ValueError(f"Invalid target type: {type(target)}")
        
        if model_runtime and hasattr(model_runtime, 'describe_element'):
            result = await model_runtime.describe_element(context, target_rect, opt)
            return result
        
        return await self._describe_via_llm(context, target_rect, model_runtime)
    
    async def _describe_via_llm(self, context: UIContext, target_rect: Rect, model_runtime=None) -> Dict[str, str]:
        llm = model_runtime or self.llm
        if not llm:
            logger.debug("No LLM configured for describe")
            return {"description": ""}
        if not context.screenshot:
            raise ValueError("screenshot is required for LLM describe")

        cropped = self._crop_screenshot(context.screenshot, target_rect)
        prompt = (
            "Describe the UI element shown in this cropped screenshot. "
            "Return only valid JSON in this exact shape: {\"description\": \"concise natural language locator\"}."
        )
        response = await self._chat_with_screenshot(llm, prompt, cropped, max_tokens=512)
        payload = self._parse_json_response(response)
        return {"description": str(payload.get("description") or "")}

    async def _get_context(self) -> UIContext:
        context = self.context_retriever_fn()
        if asyncio.iscoroutine(context):
            context = await context
        return context

    async def _chat_with_screenshot(
        self,
        llm,
        prompt: str,
        screenshot_base64: Optional[str],
        **kwargs,
    ) -> str:
        if screenshot_base64:
            messages = [MessageBuilder.user_text_with_image_base64(prompt, screenshot_base64, mime_type="image/png")]
        else:
            messages = [MessageBuilder.user_text(prompt)]
        chat = getattr(llm, "chat", None)
        if callable(chat):
            response = chat(messages, **kwargs)
        else:
            raw_chat = getattr(llm, "_chat", None)
            if not callable(raw_chat):
                raise ValueError("LLM instance does not provide chat or _chat")
            encode_messages = getattr(llm, "encode_messages", None)
            encoded_messages = encode_messages(messages) if callable(encode_messages) else messages
            response = raw_chat(encoded_messages, **kwargs)
        if asyncio.iscoroutine(response):
            response = await response
        return response

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        return parse_relaxed_json_object(response, context="service model response")

    def _format_data_demand(self, data_demand: Any) -> str:
        schema_source = data_demand.get("schema") if isinstance(data_demand, dict) and "schema" in data_demand else data_demand
        if isinstance(data_demand, str):
            return data_demand
        schema_json = getattr(schema_source, "model_json_schema", None)
        if callable(schema_json):
            return json.dumps(schema_json(), ensure_ascii=False)
        model_dump = getattr(data_demand, "model_dump", None)
        if callable(model_dump):
            return json.dumps(model_dump(), ensure_ascii=False, default=str)
        try:
            return json.dumps(data_demand, ensure_ascii=False, default=str)
        except TypeError:
            return str(data_demand)

    def _coerce_extracted_data(self, data: Any, data_demand: Any) -> Any:
        schema_source = data_demand.get("schema") if isinstance(data_demand, dict) and "schema" in data_demand else data_demand
        if isinstance(schema_source, type) and hasattr(schema_source, "model_validate"):
            return schema_source.model_validate(data)
        return data

    def _crop_screenshot(self, screenshot_base64: str, rect: Rect) -> str:
        try:
            image_module = __import__("PIL.Image", fromlist=["Image"])
            image = image_module.open(BytesIO(base64.b64decode(screenshot_base64)))
            left = max(0, int(rect.left))
            top = max(0, int(rect.top))
            right = min(image.width, int(rect.left + rect.width))
            bottom = min(image.height, int(rect.top + rect.height))
            if right <= left or bottom <= top:
                return screenshot_base64
            cropped = image.crop((left, top, right, bottom))
            buf = BytesIO()
            cropped.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            logger.debug(f"Failed to crop screenshot for describe: {e}")
            return screenshot_base64
