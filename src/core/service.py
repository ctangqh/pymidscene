import asyncio
import base64
import json
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Union, Callable

from .types import (
    DetailedLocateParam, LocateResultElement, LocateResultWithDump,
    ServiceExtractOption, ServiceExtractParam, ServiceDump,
    UIContext, AIUsageInfo, Rect, ElementCacheFeature,
)
from common.json_utils import parse_relaxed_json_object
from common.logger import logger
from common.config import settings
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
    
    def __init__(
        self,
        context: Union[UIContext, Callable],
        opt: Optional[Dict] = None,
        llm=None,
        screenshot_dir_resolver=None,
    ):
        if callable(context):
            self.context_retriever_fn = context
        else:
            self.context_retriever_fn = lambda: context
        
        self.llm = llm
        self.task_info = opt.get("task_info") if opt else None
        self.screenshot_dir_resolver = screenshot_dir_resolver or (opt.get("screenshot_dir_resolver") if opt else None)
    
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
                element = await self._locate_via_llm(context, query_prompt, query, model_runtime)
            
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
        locate_query: Optional[DetailedLocateParam] = None,
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
            f"User query: {query_prompt}\n"
            "Return a tight bounding box around the exact visible border of the target element.\n"
            "Do not shift the box toward nearby labels, whitespace, helper text, or neighboring controls.\n"
            "For input or search fields, box the actual visible input container.\n"
            "For buttons, box only the clickable button body.\n\n"
            "Return only valid JSON in this exact shape: "
            "{\"bbox\": [left, top, right, bottom], \"type\": \"Button/Input/Link/Text/etc\", \"description\": \"short description\"}.\n"
            "If multiple elements match, return the best one.\n"
            "If no element matches, return {\"bbox\": null, \"type\": null, \"description\": \"no match found\"}."
        )
        response = await self._chat_with_screenshot(llm, prompt, context.screenshot, max_tokens=1024)
        payload = self._parse_json_response(response)
        rect = self._rect_from_payload(payload)
        rect = self._sanitize_rect_to_context(rect, context)
        if not rect:
            retry_prompt = (
                f"{prompt}\n"
                f"The previous bbox was invalid. The bbox must stay within screenshot bounds "
                f"0 <= left < right <= {max(width - 1, 0)} and 0 <= top < bottom <= {max(height - 1, 0)}."
            )
            retry_response = await self._chat_with_screenshot(llm, retry_prompt, context.screenshot, max_tokens=1024)
            retry_payload = self._parse_json_response(retry_response)
            rect = self._sanitize_rect_to_context(self._rect_from_payload(retry_payload), context)
            if not rect:
                return None
            payload = retry_payload

        try:
            rough_type = str(payload.get("type") or "element")
            rough_description = str(payload.get("description") or query_prompt)
            rescued = await self._coarse_rescue_locate_via_llm(
                llm,
                context,
                query_prompt,
                rect,
                locate_query=locate_query,
                rough_type=rough_type,
                rough_description=rough_description,
            )
            if rescued:
                rect, rescue_payload = rescued
                rough_type = str(rescue_payload.get("type") or rough_type)
                rough_description = str(rescue_payload.get("description") or rough_description)
            if self._should_run_visual_refine(
                context,
                rect,
                rough_type=rough_type,
                query_prompt=query_prompt,
                locate_query=locate_query,
            ):
                refined_rect = await self._refine_locate_via_llm(
                    llm,
                    context,
                    query_prompt,
                    rect,
                    rough_type=rough_type,
                    rough_description=rough_description,
                )
                if refined_rect:
                    rect = refined_rect
        except Exception as exc:
            logger.debug(f"Locate refine fallback to rough bbox: {exc}")

        return LocateResultElement(
            center=(rect.left + rect.width / 2, rect.top + rect.height / 2),
            rect=rect,
            el_type=str(payload.get("type") or "element"),
            description=str(payload.get("description") or query_prompt),
            coordinate_space="screenshot",
        )

    def _rect_from_payload(self, payload: Dict[str, Any]) -> Optional[Rect]:
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
        return Rect(left=left, top=top, width=max(0.0, right - left), height=max(0.0, bottom - top))

    @staticmethod
    def _rect_to_list(rect: Rect) -> List[float]:
        return [
            float(rect.left),
            float(rect.top),
            float(rect.left + rect.width),
            float(rect.top + rect.height),
        ]

    def _rect_from_bbox(self, bbox: Optional[List[float]], context: UIContext) -> Optional[Rect]:
        if not bbox or len(bbox) != 4:
            return None
        try:
            rect = Rect(
                left=float(bbox[0]),
                top=float(bbox[1]),
                width=float(bbox[2]) - float(bbox[0]),
                height=float(bbox[3]) - float(bbox[1]),
            )
        except (TypeError, ValueError):
            return None
        return self._sanitize_rect_to_context(rect, context)

    @staticmethod
    def _rect_intersection_area(rect_a: Rect, rect_b: Rect) -> float:
        inter_left = max(rect_a.left, rect_b.left)
        inter_top = max(rect_a.top, rect_b.top)
        inter_right = min(rect_a.left + rect_a.width, rect_b.left + rect_b.width)
        inter_bottom = min(rect_a.top + rect_a.height, rect_b.top + rect_b.height)
        if inter_right <= inter_left or inter_bottom <= inter_top:
            return 0.0
        return float((inter_right - inter_left) * (inter_bottom - inter_top))

    def _rect_overlap_ratio(self, rect_a: Rect, rect_b: Rect) -> float:
        area_a = max(rect_a.width * rect_a.height, 0.0)
        if area_a <= 0:
            return 0.0
        return self._rect_intersection_area(rect_a, rect_b) / area_a

    def _rect_iou(self, rect_a: Rect, rect_b: Rect) -> float:
        inter = self._rect_intersection_area(rect_a, rect_b)
        if inter <= 0:
            return 0.0
        area_a = max(rect_a.width * rect_a.height, 0.0)
        area_b = max(rect_b.width * rect_b.height, 0.0)
        union = area_a + area_b - inter
        if union <= 0:
            return 0.0
        return inter / union

    def _anchor_alignment_score(self, rect: Rect, anchor_rect: Rect) -> float:
        target_overlap = self._rect_overlap_ratio(rect, anchor_rect)
        anchor_overlap = self._rect_overlap_ratio(anchor_rect, rect)
        iou = self._rect_iou(rect, anchor_rect)
        return max(
            iou,
            min(target_overlap, anchor_overlap),
            target_overlap * 0.7 + anchor_overlap * 0.3,
        )

    @staticmethod
    def _normalize_element_type(element_type: Optional[str]) -> str:
        normalized = (element_type or "").strip().lower()
        aliases = {
            "textbox": "input",
            "textfield": "input",
            "edittext": "input",
            "combobox": "input",
            "searchbox": "input",
            "search field": "input",
            "searchfield": "input",
            "iconbutton": "button",
            "menuitem": "button",
            "menu item": "button",
            "listitem": "listitem",
            "list item": "listitem",
        }
        return aliases.get(normalized, normalized)

    def _rescue_expected_type(self, locate_query: Optional[DetailedLocateParam], rough_type: str, query_prompt: str) -> str:
        action_type = ((locate_query.action_type if locate_query else None) or "").strip().lower()
        if action_type in {"input", "clearinput"}:
            return "input"
        if action_type in {"tap", "doubleclick", "rightclick", "longpress"}:
            return self._normalize_element_type(rough_type)

        query_lower = (query_prompt or "").strip().lower()
        if any(token in query_lower for token in ("input", "textbox", "text field", "search", "搜索", "输入")):
            return "input"
        if any(token in query_lower for token in ("button", "按钮", "btn")):
            return "button"
        return self._normalize_element_type(rough_type)

    def _is_decorative_description(self, description: str) -> bool:
        text = (description or "").strip().lower()
        if not text:
            return False
        decorative_terms = {
            "logo",
            "doodle",
            "illustration",
            "hero image",
            "banner",
            "mascot",
            "poster",
            "artwork",
            "thumbnail",
        }
        return any(term in text for term in decorative_terms)

    def _is_semantically_compatible_rescue(
        self,
        *,
        locate_query: Optional[DetailedLocateParam],
        query_prompt: str,
        rough_type: str,
        rough_description: str,
        rescued_type: str,
        rescued_description: str,
    ) -> bool:
        expected_type = self._rescue_expected_type(locate_query, rough_type, query_prompt)
        normalized_rough = self._normalize_element_type(rough_type)
        normalized_rescued = self._normalize_element_type(rescued_type)

        if expected_type and normalized_rescued and expected_type != normalized_rescued:
            compatible_pairs = {
                ("button", "link"),
                ("link", "button"),
                ("text", "label"),
                ("label", "text"),
            }
            if (expected_type, normalized_rescued) not in compatible_pairs:
                logger.debug(
                    f"coarse rescue rejected: incompatible rescue type, expected={expected_type}, rescued={normalized_rescued}"
                )
                return False

        if normalized_rough in {"input", "button", "link"} and normalized_rescued == "image":
            logger.debug(
                f"coarse rescue rejected: decorative image conflicts with interactive rough type, "
                f"rough={normalized_rough}, rescued={normalized_rescued}"
            )
            return False

        if self._is_decorative_description(rescued_description) and expected_type in {"input", "button", "link"}:
            logger.debug(
                f"coarse rescue rejected: decorative rescue description conflicts with expected interactive target, "
                f"description={rescued_description}"
            )
            return False

        if rough_description and rescued_description:
            rough_lower = rough_description.strip().lower()
            rescued_lower = rescued_description.strip().lower()
            if "input" in rough_lower and "input" not in rescued_lower and normalized_rescued != "input":
                logger.debug(
                    f"coarse rescue rejected: rescue description drifted away from input semantics, "
                    f"rough={rough_description}, rescued={rescued_description}"
                )
                return False

        return True

    def _is_container_like_target(self, rect: Rect, context: UIContext) -> bool:
        width = int((context.shot_size or {}).get("width") or 0)
        height = int((context.shot_size or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            return min(rect.width, rect.height) >= 48 and (rect.width * rect.height) >= 4000
        width_ratio = rect.width / float(width)
        height_ratio = rect.height / float(height)
        area_ratio = (rect.width * rect.height) / float(width * height)
        return width_ratio >= 0.15 or height_ratio >= 0.05 or area_ratio >= 0.02

    def _get_structural_anchor_rect(
        self,
        context: UIContext,
        locate_query: Optional[DetailedLocateParam],
    ) -> Optional[Rect]:
        if not locate_query:
            return None
        return self._rect_from_bbox(locate_query.structural_anchor_bbox, context)

    def _should_run_coarse_rescue(
        self,
        context: UIContext,
        rough_rect: Rect,
        *,
        locate_query: Optional[DetailedLocateParam],
    ) -> bool:
        if not context.screenshot:
            return False
        anchor_rect = self._get_structural_anchor_rect(context, locate_query)
        if not anchor_rect:
            return False
        if not (
            self._is_container_like_target(rough_rect, context)
            or self._is_container_like_target(anchor_rect, context)
        ):
            return False
        if self._is_small_target(rough_rect, context) and self._is_small_target(anchor_rect, context):
            return False

        alignment = self._anchor_alignment_score(rough_rect, anchor_rect)
        if alignment >= 0.35:
            logger.debug(f"coarse rescue skipped: rough locate already aligned, score={alignment:.3f}")
            return False

        logger.debug(f"coarse rescue enabled: rough locate misaligned, score={alignment:.3f}")
        return True

    def _expand_rect_for_coarse_rescue(self, anchor_rect: Rect, context: UIContext) -> Rect:
        shot_width = context.shot_size.get("width", 0) if context.shot_size else 0
        shot_height = context.shot_size.get("height", 0) if context.shot_size else 0
        margin_x = max(anchor_rect.width * 0.35, 80.0)
        margin_y = max(anchor_rect.height * 1.8, 96.0)

        left = max(0.0, anchor_rect.left - margin_x)
        top = max(0.0, anchor_rect.top - margin_y)
        right = min(
            float(shot_width or (anchor_rect.left + anchor_rect.width)),
            anchor_rect.left + anchor_rect.width + margin_x,
        )
        bottom = min(
            float(shot_height or (anchor_rect.top + anchor_rect.height)),
            anchor_rect.top + anchor_rect.height + margin_y,
        )
        return Rect(left=left, top=top, width=max(1.0, right - left), height=max(1.0, bottom - top))

    def _should_accept_coarse_rescue(
        self,
        rough_rect: Rect,
        rescued_rect: Rect,
        anchor_rect: Rect,
        *,
        locate_query: Optional[DetailedLocateParam],
        query_prompt: str,
        rough_type: str,
        rough_description: str,
        rescued_type: str,
        rescued_description: str,
    ) -> bool:
        rough_score = self._anchor_alignment_score(rough_rect, anchor_rect)
        rescued_score = self._anchor_alignment_score(rescued_rect, anchor_rect)
        rescued_target_overlap = self._rect_overlap_ratio(rescued_rect, anchor_rect)
        rescued_anchor_overlap = self._rect_overlap_ratio(anchor_rect, rescued_rect)

        if not self._is_semantically_compatible_rescue(
            locate_query=locate_query,
            query_prompt=query_prompt,
            rough_type=rough_type,
            rough_description=rough_description,
            rescued_type=rescued_type,
            rescued_description=rescued_description,
        ):
            return False

        if rescued_score < 0.45:
            logger.debug(
                f"coarse rescue rejected: rescued alignment too low, "
                f"rough_score={rough_score:.3f}, rescued_score={rescued_score:.3f}"
            )
            return False
        if rescued_target_overlap < 0.3 or rescued_anchor_overlap < 0.45:
            logger.debug(
                f"coarse rescue rejected: insufficient anchor coverage, "
                f"rescued_target_overlap={rescued_target_overlap:.3f}, "
                f"rescued_anchor_overlap={rescued_anchor_overlap:.3f}"
            )
            return False
        if rescued_score <= rough_score + 0.15:
            logger.debug(
                f"coarse rescue rejected: improvement insufficient, "
                f"rough_score={rough_score:.3f}, rescued_score={rescued_score:.3f}"
            )
            return False
        return True

    def _is_small_screen_context(self, context: UIContext) -> bool:
        width = int((context.shot_size or {}).get("width") or 0)
        height = int((context.shot_size or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            return False
        short_edge = min(width, height)
        long_edge = max(width, height)
        return short_edge <= 600 or long_edge <= 900

    def _is_small_target(self, rect: Rect, context: UIContext) -> bool:
        width = int((context.shot_size or {}).get("width") or 0)
        height = int((context.shot_size or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            return min(rect.width, rect.height) < 56 or (rect.width * rect.height) < 4000
        screen_area = float(width * height)
        target_area = rect.width * rect.height
        short_edge = min(rect.width, rect.height)
        return short_edge < 56 or (screen_area > 0 and target_area / screen_area < 0.015)

    def _is_large_easy_target(self, rect: Rect, context: UIContext, rough_type: str) -> bool:
        width = int((context.shot_size or {}).get("width") or 0)
        height = int((context.shot_size or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            return False
        type_lower = (rough_type or "").strip().lower()
        width_ratio = rect.width / float(width)
        height_ratio = rect.height / float(height)
        is_primary_large_type = type_lower in {"input", "button"}
        return is_primary_large_type and width_ratio >= 0.25 and height_ratio >= 0.05 and min(rect.width, rect.height) >= 48

    def _should_run_visual_refine(
        self,
        context: UIContext,
        rect: Rect,
        *,
        rough_type: str,
        query_prompt: str,
        locate_query: Optional[DetailedLocateParam] = None,
    ) -> bool:
        if not context.screenshot:
            return False

        action_type = ((locate_query.action_type if locate_query else None) or "").strip().lower()
        has_structural_anchor = bool(
            locate_query.structural_anchor_available if locate_query else False
        )
        device_type = ((locate_query.device_type if locate_query else None) or "").strip().lower()
        high_precision_actions = {"tap", "doubleclick", "rightclick", "hover", "longpress", "drag", "pinch"}
        text_entry_actions = {"input", "clearinput"}

        if locate_query and locate_query.deep_locate:
            logger.debug("visual refine enabled: deep_locate=True")
            return True

        if has_structural_anchor and action_type in text_entry_actions and not self._is_small_target(rect, context):
            logger.debug(
                f"visual refine skipped: structural anchor available for text-entry action, "
                f"device={device_type or 'unknown'}, query={query_prompt}"
            )
            return False

        if self._is_small_screen_context(context):
            logger.debug("visual refine enabled: small-screen context")
            return True

        if self._is_small_target(rect, context):
            logger.debug("visual refine enabled: small target")
            return True

        if has_structural_anchor and action_type and action_type not in high_precision_actions:
            logger.debug(
                f"visual refine skipped: structural anchor available for non-high-precision action, "
                f"action={action_type}, device={device_type or 'unknown'}, query={query_prompt}"
            )
            return False

        if self._is_large_easy_target(rect, context, rough_type):
            logger.debug(
                f"visual refine skipped: large easy target, type={rough_type}, query={query_prompt}"
            )
            return False

        logger.debug(f"visual refine enabled: default path, type={rough_type}, query={query_prompt}")
        return True

    def _sanitize_rect_to_context(self, rect: Optional[Rect], context: UIContext) -> Optional[Rect]:
        if not rect:
            return None
        width = int((context.shot_size or {}).get("width") or 0)
        height = int((context.shot_size or {}).get("height") or 0)
        if width <= 0 or height <= 0:
            return rect if self._is_reasonable_rect(rect) else None

        clipped = self._clip_rect(rect, width=width, height=height)
        if not clipped or not self._is_reasonable_rect(clipped):
            return None
        return clipped

    def _clip_rect(self, rect: Rect, *, width: int, height: int) -> Optional[Rect]:
        left = max(0.0, min(rect.left, float(width)))
        top = max(0.0, min(rect.top, float(height)))
        right = max(0.0, min(rect.left + rect.width, float(width)))
        bottom = max(0.0, min(rect.top + rect.height, float(height)))
        if right <= left or bottom <= top:
            return None
        return Rect(left=left, top=top, width=right - left, height=bottom - top)

    def _is_reasonable_rect(self, rect: Rect) -> bool:
        if rect.width < 8 or rect.height < 8:
            return False
        area = rect.width * rect.height
        if area < 120:
            return False
        aspect_ratio = max(rect.width / max(rect.height, 1.0), rect.height / max(rect.width, 1.0))
        if aspect_ratio > 40:
            return False
        return True

    def _expand_rect_for_visual_refine(self, rect: Rect, context: UIContext) -> Rect:
        shot_width = context.shot_size.get("width", 0) if context.shot_size else 0
        shot_height = context.shot_size.get("height", 0) if context.shot_size else 0
        margin_x = max(rect.width * 0.4, 64.0)
        margin_top = max(rect.height * 2.5, 120.0)
        margin_bottom = max(rect.height * 1.6, 80.0)

        left = max(0.0, rect.left - margin_x)
        top = max(0.0, rect.top - margin_top)
        right = min(float(shot_width or (rect.left + rect.width)), rect.left + rect.width + margin_x)
        bottom = min(float(shot_height or (rect.top + rect.height)), rect.top + rect.height + margin_bottom)
        return Rect(left=left, top=top, width=max(1.0, right - left), height=max(1.0, bottom - top))

    def _get_debug_screenshot_dir(self) -> Path:
        resolver = self.screenshot_dir_resolver
        if callable(resolver):
            try:
                save_dir = resolver()
                if isinstance(save_dir, Path):
                    save_dir.mkdir(parents=True, exist_ok=True)
                    return save_dir
            except Exception as exc:
                logger.debug(f"获取 Service 调试截图目录失败，回退到默认目录: {exc}")
        save_dir = settings.report_screenshot_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _make_debug_name(self, query_prompt: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", query_prompt).strip("_") or "locate"

    @staticmethod
    def _rect_to_bbox(rect: Rect) -> Dict[str, float]:
        return {
            "left": float(rect.left),
            "top": float(rect.top),
            "width": float(rect.width),
            "height": float(rect.height),
        }

    def _save_refine_debug_artifacts(
        self,
        *,
        context: UIContext,
        query_prompt: str,
        rough_rect: Rect,
        crop_rect: Rect,
        cropped_screenshot: str,
        rough_type: str,
        rough_description: str,
        refined_local_rect: Optional[Rect] = None,
        refined_global_rect: Optional[Rect] = None,
    ) -> None:
        if not settings.DEBUG or not context.screenshot:
            return

        try:
            from common.image import save_debug_screenshot, format_box_label

            save_dir = self._get_debug_screenshot_dir()
            safe_name = self._make_debug_name(query_prompt)

            rough_label = "rough\n" + format_box_label(self._rect_to_bbox(rough_rect), rough_type or "element")
            save_debug_screenshot(
                context.screenshot,
                f"{safe_name}_rough_full",
                annotations=[{"rect": self._rect_to_bbox(rough_rect), "label": rough_label}],
                save_raw=False,
                save_dir=save_dir,
            )

            local_rough = Rect(
                left=max(0.0, rough_rect.left - crop_rect.left),
                top=max(0.0, rough_rect.top - crop_rect.top),
                width=rough_rect.width,
                height=rough_rect.height,
            )
            crop_paths = save_debug_screenshot(
                cropped_screenshot,
                f"{safe_name}_refine_crop",
                annotations=[{"rect": self._rect_to_bbox(local_rough), "label": rough_label}],
                save_raw=True,
                save_dir=save_dir,
            )

            compare_annotations = [
                {
                    "rect": self._rect_to_bbox(local_rough),
                    "label": rough_label,
                }
            ]
            if refined_local_rect:
                refined_label = "refined\n" + format_box_label(
                    self._rect_to_bbox(refined_local_rect),
                    rough_type or "element",
                )
                save_debug_screenshot(
                    cropped_screenshot,
                    f"{safe_name}_refine_result",
                    annotations=[{"rect": self._rect_to_bbox(refined_local_rect), "label": refined_label}],
                    save_raw=False,
                    save_dir=save_dir,
                )
                compare_annotations.append(
                    {
                        "rect": self._rect_to_bbox(refined_local_rect),
                        "label": refined_label,
                    }
                )
                save_debug_screenshot(
                    cropped_screenshot,
                    f"{safe_name}_refine_compare",
                    annotations=compare_annotations,
                    save_raw=False,
                    save_dir=save_dir,
                )

            trace_payload = {
                "query": query_prompt,
                "rough_type": rough_type,
                "rough_description": rough_description,
                "rough_rect": self._rect_to_bbox(rough_rect),
                "crop_rect": self._rect_to_bbox(crop_rect),
                "rough_rect_in_crop": self._rect_to_bbox(local_rough),
                "refined_rect_in_crop": self._rect_to_bbox(refined_local_rect) if refined_local_rect else None,
                "refined_rect_global": self._rect_to_bbox(refined_global_rect) if refined_global_rect else None,
                "crop_raw_path": str(crop_paths.get("raw")) if crop_paths.get("raw") else None,
            }
            trace_path = save_dir / f"{safe_name}_refine_trace_{int(time.time() * 1000)}.json"
            trace_path.write_text(json.dumps(trace_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"已保存定位精修调试产物: {trace_path}")
        except Exception as exc:
            logger.warning(f"保存定位精修调试产物失败: {exc}")

    def _save_coarse_rescue_debug_artifacts(
        self,
        *,
        context: UIContext,
        query_prompt: str,
        rough_rect: Rect,
        anchor_rect: Rect,
        crop_rect: Rect,
        cropped_screenshot: str,
        rescued_local_rect: Optional[Rect] = None,
        rescued_global_rect: Optional[Rect] = None,
    ) -> None:
        if not settings.DEBUG or not context.screenshot:
            return

        try:
            from common.image import save_debug_screenshot, format_box_label

            save_dir = self._get_debug_screenshot_dir()
            safe_name = self._make_debug_name(query_prompt)

            save_debug_screenshot(
                context.screenshot,
                f"{safe_name}_coarse_rescue_full",
                annotations=[
                    {
                        "rect": self._rect_to_bbox(rough_rect),
                        "label": "rough\n" + format_box_label(self._rect_to_bbox(rough_rect), "rough"),
                    },
                    {
                        "rect": self._rect_to_bbox(anchor_rect),
                        "label": "anchor\n" + format_box_label(self._rect_to_bbox(anchor_rect), "anchor"),
                    },
                ],
                save_raw=False,
                save_dir=save_dir,
            )

            local_anchor = Rect(
                left=max(0.0, anchor_rect.left - crop_rect.left),
                top=max(0.0, anchor_rect.top - crop_rect.top),
                width=anchor_rect.width,
                height=anchor_rect.height,
            )
            save_debug_screenshot(
                cropped_screenshot,
                f"{safe_name}_coarse_rescue_crop",
                annotations=[
                    {
                        "rect": self._rect_to_bbox(local_anchor),
                        "label": "anchor\n" + format_box_label(self._rect_to_bbox(local_anchor), "anchor"),
                    }
                ],
                save_raw=True,
                save_dir=save_dir,
            )
            if rescued_local_rect:
                save_debug_screenshot(
                    cropped_screenshot,
                    f"{safe_name}_coarse_rescue_result",
                    annotations=[
                        {
                            "rect": self._rect_to_bbox(local_anchor),
                            "label": "anchor\n" + format_box_label(self._rect_to_bbox(local_anchor), "anchor"),
                        },
                        {
                            "rect": self._rect_to_bbox(rescued_local_rect),
                            "label": "rescued\n"
                            + format_box_label(self._rect_to_bbox(rescued_local_rect), "rescued"),
                        },
                    ],
                    save_raw=False,
                    save_dir=save_dir,
                )

            trace_payload = {
                "query": query_prompt,
                "rough_rect": self._rect_to_bbox(rough_rect),
                "anchor_rect": self._rect_to_bbox(anchor_rect),
                "crop_rect": self._rect_to_bbox(crop_rect),
                "rescued_rect_global": self._rect_to_bbox(rescued_global_rect) if rescued_global_rect else None,
            }
            trace_path = save_dir / f"{safe_name}_coarse_rescue_trace_{int(time.time() * 1000)}.json"
            trace_path.write_text(json.dumps(trace_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.debug(f"已保存 coarse rescue 调试产物: {trace_path}")
        except Exception as exc:
            logger.warning(f"保存 coarse rescue 调试产物失败: {exc}")

    async def _coarse_rescue_locate_via_llm(
        self,
        llm,
        context: UIContext,
        query_prompt: str,
        rough_rect: Rect,
        *,
        locate_query: Optional[DetailedLocateParam],
        rough_type: str,
        rough_description: str,
    ) -> Optional[Tuple[Rect, Dict[str, Any]]]:
        if not self._should_run_coarse_rescue(context, rough_rect, locate_query=locate_query):
            return None

        anchor_rect = self._get_structural_anchor_rect(context, locate_query)
        if not anchor_rect:
            return None

        crop_rect = self._expand_rect_for_coarse_rescue(anchor_rect, context)
        cropped = self._crop_screenshot(context.screenshot, crop_rect)
        crop_width = int(round(crop_rect.width))
        crop_height = int(round(crop_rect.height))
        self._save_coarse_rescue_debug_artifacts(
            context=context,
            query_prompt=query_prompt,
            rough_rect=rough_rect,
            anchor_rect=anchor_rect,
            crop_rect=crop_rect,
            cropped_screenshot=cropped,
        )
        prompt = (
            "You are correcting a UI element detection that likely landed in the wrong area of the full screenshot.\n"
            f"Cropped screenshot size: width={crop_width}, height={crop_height}. Coordinates must be in cropped screenshot pixels.\n"
            f"User query: {query_prompt}\n"
            f"Initial rough detection type: {rough_type}\n"
            f"Initial rough detection description: {rough_description}\n"
            "This crop is centered around a reliable structural anchor that likely belongs to the target region.\n"
            "Use that anchor as a regional hint, but return the bbox for the exact visible target element only.\n"
            "Do not return the surrounding section, helper text, neighboring buttons, or whitespace.\n"
            "Return only valid JSON in this exact shape: "
            "{\"bbox\": [left, top, right, bottom], \"type\": \"Button/Input/Link/Text/etc\", \"description\": \"short description\"}."
        )
        response = await self._chat_with_screenshot(llm, prompt, cropped, max_tokens=768)
        payload = self._parse_json_response(response)
        rescued_type = str(payload.get("type") or rough_type)
        rescued_description = str(payload.get("description") or query_prompt)
        rescued_local = self._sanitize_rect_to_context(
            self._rect_from_payload(payload),
            UIContext(
                screenshot="",
                shot_size={"width": crop_width, "height": crop_height},
                shrunk_shot_to_logical_ratio=1.0,
            ),
        )
        if not rescued_local:
            return None

        rescued_global = Rect(
            left=crop_rect.left + rescued_local.left,
            top=crop_rect.top + rescued_local.top,
            width=rescued_local.width,
            height=rescued_local.height,
        )
        rescued_global = self._sanitize_rect_to_context(rescued_global, context)
        if not rescued_global:
            return None
        if not self._should_accept_coarse_rescue(
            rough_rect,
            rescued_global,
            anchor_rect,
            locate_query=locate_query,
            query_prompt=query_prompt,
            rough_type=rough_type,
            rough_description=rough_description,
            rescued_type=rescued_type,
            rescued_description=rescued_description,
        ):
            return None

        self._save_coarse_rescue_debug_artifacts(
            context=context,
            query_prompt=query_prompt,
            rough_rect=rough_rect,
            anchor_rect=anchor_rect,
            crop_rect=crop_rect,
            cropped_screenshot=cropped,
            rescued_local_rect=rescued_local,
            rescued_global_rect=rescued_global,
        )
        return rescued_global, payload

    async def _refine_locate_via_llm(
        self,
        llm,
        context: UIContext,
        query_prompt: str,
        rough_rect: Rect,
        *,
        rough_type: str,
        rough_description: str,
    ) -> Optional[Rect]:
        if not context.screenshot:
            return None

        crop_rect = self._expand_rect_for_visual_refine(rough_rect, context)
        cropped = self._crop_screenshot(context.screenshot, crop_rect)
        crop_width = int(round(crop_rect.width))
        crop_height = int(round(crop_rect.height))
        self._save_refine_debug_artifacts(
            context=context,
            query_prompt=query_prompt,
            rough_rect=rough_rect,
            crop_rect=crop_rect,
            cropped_screenshot=cropped,
            rough_type=rough_type,
            rough_description=rough_description,
        )
        prompt = (
            "You are refining a rough UI element detection from a larger screenshot.\n"
            f"Cropped screenshot size: width={crop_width}, height={crop_height}. Coordinates must be in cropped screenshot pixels.\n"
            f"User query: {query_prompt}\n"
            f"Rough detection type: {rough_type}\n"
            f"Rough detection description: {rough_description}\n"
            "The target element is visible in this crop.\n"
            "Return a tighter bbox around the exact visible target element only.\n"
            "Do not shift the box toward whitespace, helper text, neighboring buttons, or icons outside the target.\n"
            "For input or search fields, box the actual visible input container.\n"
            "For buttons, box only the clickable button body.\n\n"
            "Return only valid JSON in this exact shape: "
            "{\"bbox\": [left, top, right, bottom], \"type\": \"Button/Input/Link/Text/etc\", \"description\": \"short description\"}."
        )
        response = await self._chat_with_screenshot(llm, prompt, cropped, max_tokens=768)
        payload = self._parse_json_response(response)
        refined = self._sanitize_rect_to_context(
            self._rect_from_payload(payload),
            UIContext(
                screenshot="",
                shot_size={"width": crop_width, "height": crop_height},
                shrunk_shot_to_logical_ratio=1.0,
            ),
        )
        if not refined:
            return None
        refined_global = Rect(
            left=crop_rect.left + refined.left,
            top=crop_rect.top + refined.top,
            width=refined.width,
            height=refined.height,
        )
        self._save_refine_debug_artifacts(
            context=context,
            query_prompt=query_prompt,
            rough_rect=rough_rect,
            crop_rect=crop_rect,
            cropped_screenshot=cropped,
            rough_type=rough_type,
            rough_description=rough_description,
            refined_local_rect=refined,
            refined_global_rect=refined_global,
        )
        return refined_global
    
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
