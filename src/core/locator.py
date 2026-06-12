import asyncio
import base64
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from device.base import BaseDevice
from llm.base import BaseLLM
from common.logger import logger
from common.config import settings
from common.exceptions import ElementNotFoundError, LocateConfidenceLowError, ModelResponseError
from .service import Service
from .agent.context_parser import common_context_parser
from .types import ServiceExtractOption


class LocateResult(BaseModel):
    """定位结果模型"""
    selector: Optional[str] = Field(None, description="元素的CSS选择器")
    confidence: float = Field(description="定位结果置信度，0-1之间")
    x: Optional[float] = Field(None, description="元素中心点X坐标")
    y: Optional[float] = Field(None, description="元素中心点Y坐标")
    bounding_box: Optional[Dict[str, float]] = Field(None, description="元素边界框: x, y, width, height")
    reason: Optional[str] = Field(None, description="定位结果的分析说明")


class ExtractResult(BaseModel):
    """信息提取结果模型"""
    data: Any = Field(description="提取到的信息")
    confidence: float = Field(description="提取结果置信度，0-1之间")
    reason: Optional[str] = Field(None, description="提取结果的说明")


class ElementLocator:
    """智能元素定位引擎"""
    
    def __init__(self, device: BaseDevice, llm: BaseLLM, vision_model=None):
        self.device = device
        self.llm = llm
        self.vision_model = vision_model
        self.model_runtime = vision_model or llm
        self.confidence_threshold = settings.LOCATE_CONFIDENCE_THRESHOLD
        self.service = Service(lambda: self._build_context(), llm=self.model_runtime)
        self.last_result: Optional[LocateResult] = None

    def _run_async(self, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            try:
                coro.send(None)
            except StopIteration as done:
                return done.value
            finally:
                if hasattr(coro, "close"):
                    coro.close()
            raise RuntimeError("ElementLocator 无法在已运行事件循环中执行会挂起的协程")

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            if not loop.is_running():
                loop.close()

    async def _build_context(self, **kwargs):
        opt = {}
        if "screenshot_shrink_factor" in kwargs:
            opt["screenshot_shrink_factor"] = kwargs["screenshot_shrink_factor"]
        return await common_context_parser(self.device, opt)

    @staticmethod
    def _to_logical_point(point: Tuple[float, float], ratio: float) -> Tuple[float, float]:
        if not ratio or ratio == 1.0:
            return point
        return (point[0] / ratio, point[1] / ratio)

    def _is_web_device(self) -> bool:
        return getattr(self.device, "interface_type", "") in ("web", "browser")

    def _save_debug_visualization(self, element_description: str, result: LocateResult) -> None:
        if not settings.DEBUG:
            return

        raw_bbox = result.bounding_box or {}
        if not raw_bbox:
            return

        bbox: Dict[str, Any]
        if "left" in raw_bbox and "top" in raw_bbox and "width" in raw_bbox and "height" in raw_bbox:
            bbox = dict(raw_bbox)
        elif "x" in raw_bbox and "y" in raw_bbox and "width" in raw_bbox and "height" in raw_bbox:
            bbox = {
                "left": raw_bbox["x"],
                "top": raw_bbox["y"],
                "width": raw_bbox["width"],
                "height": raw_bbox["height"],
            }
        else:
            bbox = dict(raw_bbox)

        try:
            from common.image import save_debug_screenshot, format_box_label

            screenshot_b64 = self.device.screenshot_base64()
            if not screenshot_b64:
                return

            safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", element_description).strip("_") or "element"

            el_type = "element"
            reason = result.reason or ""
            m = re.search(r"tag=([^,\\s]+)", reason)
            if m:
                el_type = m.group(1)
            label = format_box_label(bbox, el_type)

            # 使用新的抽象方法保存调试截图
            paths = save_debug_screenshot(
                screenshot_b64,
                safe_name,
                annotations=[{"rect": bbox, "label": label}],
                save_raw=True
            )
            logger.debug(f"定位调试截图已保存: raw={paths.get('raw')}, annotated={paths.get('annotated')}")
        except Exception as e:
            logger.warning(f"保存定位调试截图失败: {e}")
    
    def _simplify_dom(self, dom: Dict[str, Any], max_depth: int = 5, current_depth: int = 0) -> Dict[str, Any]:
        """
        简化DOM树，减少token占用，只保留关键属性
        :param dom: 原始DOM树
        :param max_depth: 最大递归深度
        :param current_depth: 当前递归深度
        :return: 简化后的DOM树
        """
        if current_depth >= max_depth:
            return {}
        
        # 只保留关键属性
        simplified = {
            "tag": dom.get("tagName", ""),
            "text": dom.get("text", "")[:100].strip(),  # 只保留前100个字符的文本
        }
        
        # 保留有用的属性
        useful_attrs = ["id", "class", "name", "placeholder", "href", "src", "type", "value", "aria-label", "role"]
        attrs = dom.get("attributes", {})
        filtered_attrs = {k: v for k, v in attrs.items() if k in useful_attrs}
        if filtered_attrs:
            simplified["attrs"] = filtered_attrs
        
        # 递归处理子元素
        children = dom.get("children", [])
        if children and current_depth < max_depth - 1:
            simplified_children = []
            for child in children:
                simplified_child = self._simplify_dom(child, max_depth, current_depth + 1)
                # 过滤掉空的子元素
                if simplified_child and simplified_child.get("tag") not in ["script", "style", "noscript", "iframe"]:
                    simplified_children.append(simplified_child)
            if simplified_children:
                simplified["children"] = simplified_children
        
        return simplified
    
    def _get_element_position_by_selector(self, selector: str) -> Optional[Tuple[float, float, Dict[str, float]]]:
        """
        根据选择器获取元素坐标
        :param selector: CSS选择器
        :return: (中心点x, 中心点y, 边界框字典)
        """
        try:
            # 先等待元素出现
            if not self.device.wait_for_selector(selector, timeout=3000):
                return None
            
            # 获取元素边界框
            escaped_selector = selector.replace("'", "\\'")
            bbox = self.device.evaluate_script(f"""() => {{
                const el = document.querySelector('{escaped_selector}');
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return {{
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                    top: rect.top,
                    left: rect.left,
                    bottom: rect.bottom,
                    right: rect.right
                }};
            }}""")
            
            if not bbox:
                return None
            
            # 计算中心点坐标
            center_x = bbox["x"] + bbox["width"] / 2
            center_y = bbox["y"] + bbox["height"] / 2
            
            return (center_x, center_y, bbox)
            
        except Exception as e:
            logger.warning(f"获取元素坐标失败: {str(e)}")
            return None
    
    def _locate_by_dom(self, element_description: str, **kwargs) -> Optional[LocateResult]:
        """
        通过DOM结构分析定位元素
        :param element_description: 元素描述
        :return: 定位结果
        """
        logger.info(f"通过DOM结构分析定位元素: {element_description}")
        
        # 获取并简化DOM
        raw_dom = self.device.get_dom_tree()
        simplified_dom = self._simplify_dom(raw_dom)
        
        import json
        dom_json = json.dumps(simplified_dom, ensure_ascii=False, indent=2)
        # 限制DOM长度，避免token过多
        if len(dom_json) > 8000:
            dom_json = dom_json[:8000] + "...[DOM太长已截断]"
        
        # 构造prompt
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的前端元素定位专家，根据用户提供的页面简化DOM结构和元素描述，找到最匹配的元素。
请严格按照要求返回JSON格式的结果，不要输出其他内容：
1. selector字段：返回最准确的CSS选择器，尽量使用id、class、属性等唯一标识
2. confidence字段：返回你对这个定位结果的置信度，0-1之间，1表示完全确定
3. reason字段：简单说明你为什么选择这个选择器
注意：如果没有找到匹配的元素，confidence返回0，selector返回空字符串。"""
            },
            {
                "role": "user",
                "content": f"""页面简化DOM结构：
```json
{dom_json}
```

需要定位的元素描述：{element_description}

请返回定位结果："""
            }
        ]
        
        try:
            result = self.llm.structured_chat(messages, output_schema=LocateResult)
            logger.debug(f"DOM定位结果: 选择器={result.selector}, 置信度={result.confidence}, 说明={result.reason}")
            
            if result.confidence <= 0 or not result.selector:
                logger.warning("DOM定位未找到匹配元素")
                return None
            
            # 获取元素实际坐标
            position = self._get_element_position_by_selector(result.selector)
            if not position:
                logger.warning(f"选择器 {result.selector} 未找到对应元素")
                return None
            
            result.x, result.y, result.bounding_box = position
            return result
            
        except Exception as e:
            logger.error(f"DOM定位失败: {str(e)}")
            return None

    def _extract_native_tree_payload(self, raw_dom: Any) -> Any:
        if isinstance(raw_dom, dict):
            for key in ("content", "xml", "value", "source", "pageSource", "page_source"):
                if key in raw_dom and raw_dom[key]:
                    raw_dom = raw_dom[key]
                    break

        if isinstance(raw_dom, str):
            text = raw_dom.strip().lstrip("\ufeff")
            if not text:
                return None
            if text.startswith("{") or text.startswith("["):
                try:
                    payload = json.loads(text)
                    if isinstance(payload, dict) and "value" in payload and payload["value"]:
                        inner = payload["value"]
                        if isinstance(inner, str):
                            return inner.strip().lstrip("\ufeff")
                        return inner
                    return payload
                except Exception:
                    return text
            return text

        return raw_dom

    def _extract_bounds_from_attrs(self, attrs: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        def _to_float(value):
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        left = _to_float(attrs.get("x", attrs.get("left")))
        top = _to_float(attrs.get("y", attrs.get("top")))
        width = _to_float(attrs.get("width", attrs.get("w")))
        height = _to_float(attrs.get("height", attrs.get("h")))

        if left is not None and top is not None and width is not None and height is not None:
            return left, top, width, height

        bounds = attrs.get("bounds")
        if isinstance(bounds, str):
            m = re.match(r"\[(\-?\d+),(\-?\d+)\]\[(\-?\d+),(\-?\d+)\]", bounds.strip())
            if m:
                x1, y1, x2, y2 = map(float, m.groups())
                return x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1)

        right = _to_float(attrs.get("right"))
        bottom = _to_float(attrs.get("bottom"))
        if left is not None and top is not None and right is not None and bottom is not None:
            return left, top, max(0.0, right - left), max(0.0, bottom - top)

        rect = attrs.get("rect")
        if isinstance(rect, dict):
            return self._extract_bounds_from_attrs(rect)

        return None

    def _iter_native_tree_candidates(self, payload: Any):
        if payload is None:
            return

        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                return
            if text.startswith("<"):
                root = ET.fromstring(text)
                for node in root.iter():
                    yield {
                        "tag": node.tag,
                        "attrs": dict(node.attrib),
                    }
            return

        if isinstance(payload, list):
            for item in payload:
                yield from self._iter_native_tree_candidates(item)
            return

        if not isinstance(payload, dict):
            return

        attrs = dict(payload)
        tag = (
            payload.get("tag")
            or payload.get("tagName")
            or payload.get("type")
            or payload.get("class")
            or payload.get("className")
            or payload.get("nodeName")
            or payload.get("role")
            or "node"
        )
        yield {"tag": str(tag), "attrs": attrs}

        child_keys = (
            "children", "nodes", "elements", "items", "subviews", "views",
            "child", "content", "value",
        )
        for key in child_keys:
            child = payload.get(key)
            if isinstance(child, (dict, list)):
                yield from self._iter_native_tree_candidates(child)

    def _score_native_candidate(self, description: str, tokens: List[str], tag: str, attrs: Dict[str, Any]) -> float:
        name = str(
            attrs.get("Name")
            or attrs.get("name")
            or attrs.get("label")
            or attrs.get("text")
            or attrs.get("content-desc")
            or attrs.get("contentDescription")
            or attrs.get("placeholder")
            or ""
        )
        automation_id = str(
            attrs.get("AutomationId")
            or attrs.get("resource-id")
            or attrs.get("resourceId")
            or attrs.get("identifier")
            or attrs.get("accessibilityIdentifier")
            or attrs.get("id")
            or ""
        )
        control_type = str(
            attrs.get("LocalizedControlType")
            or attrs.get("controlType")
            or attrs.get("role")
            or attrs.get("type")
            or ""
        )
        class_name = str(attrs.get("ClassName") or attrs.get("class") or attrs.get("className") or "")
        item_type = str(attrs.get("ItemType") or attrs.get("itemType") or "")

        searchable_fields = [name, automation_id, control_type, class_name, item_type, tag]
        searchable_text = " ".join([f for f in searchable_fields if f]).lower()
        if not searchable_text:
            return 0.0

        score = 0.0
        lowered_description = description.lower()
        lowered_name = name.lower()

        if lowered_description and lowered_description == lowered_name:
            score += 10.0
        elif lowered_description and lowered_description in searchable_text:
            score += 7.0

        for token in tokens:
            lowered_token = token.lower()
            if lowered_token == lowered_name:
                score += 6.0
            elif lowered_token in lowered_name:
                score += 4.0
            elif lowered_token in searchable_text:
                score += 2.0

        lowered_tag = tag.lower()
        lowered_type = control_type.lower()
        if any(k in description for k in ["输入", "编辑", "文本框", "编辑器"]) and (
            lowered_tag in ("edit", "textfield", "input", "textarea", "android.widget.edittext")
            or any(k in lowered_type for k in ["编辑", "文本", "input", "text"])
        ):
            score += 3.0
        if any(k in description for k in ["按钮", "点击"]) and (
            lowered_tag in ("button", "android.widget.button", "menuitem")
            or any(k in lowered_type for k in ["按钮", "button"])
        ):
            score += 3.0

        return score

    def _selector_from_native_attrs(self, attrs: Dict[str, Any]) -> Optional[str]:
        for key in ("AutomationId", "resource-id", "resourceId", "identifier", "accessibilityIdentifier", "id"):
            value = attrs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _locate_by_native_tree(self, element_description: str) -> Optional[LocateResult]:
        """
        针对非 Web 端的本地 UI 结构回退定位。
        典型输入是 WinAppDriver / Appium 返回的 XML 或 JSON 树。
        """
        if self._is_web_device():
            return None

        try:
            payload = self._extract_native_tree_payload(self.device.get_dom_tree())
            if not payload:
                return None
            description = (element_description or "").strip()
            tokens = [t for t in re.split(r"[\s,，、/]+", description) if t]

            best = None
            best_score = 0.0

            for node in self._iter_native_tree_candidates(payload):
                tag = str(node.get("tag") or "node")
                attrs = node.get("attrs") or {}
                score = self._score_native_candidate(description, tokens, tag, attrs)
                if score <= best_score:
                    continue

                bounds = self._extract_bounds_from_attrs(attrs)
                if not bounds:
                    continue
                left, top, width, height = bounds
                if width <= 0 or height <= 0:
                    continue

                name = str(
                    attrs.get("Name")
                    or attrs.get("name")
                    or attrs.get("label")
                    or attrs.get("text")
                    or self._selector_from_native_attrs(attrs)
                    or attrs.get("LocalizedControlType")
                    or attrs.get("controlType")
                    or ""
                )
                best_score = score
                best = LocateResult(
                    selector=self._selector_from_native_attrs(attrs),
                    confidence=min(0.99, 0.55 + score / 20.0),
                    x=left + width / 2,
                    y=top + height / 2,
                    bounding_box={
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                    },
                    reason=f"本地UI树匹配: tag={tag}, name={name}",
                )

            return best
        except Exception as e:
            logger.warning(f"本地UI树定位失败: {str(e)}")
            return None
    
    def _locate_by_vision(self, element_description: str, **kwargs) -> Optional[LocateResult]:
        """
        通过统一视觉服务定位元素
        :param element_description: 元素描述
        :return: 定位结果
        """
        if not self.model_runtime or not settings.LOCATE_USE_VISION:
            return None
        
        try:
            logger.info(f"通过视觉分析定位元素: {element_description}")
            context = self._run_async(self._build_context(**kwargs))
            locate_result = self._run_async(
                self.service.locate(
                    element_description,
                    {"context": context},
                    model_runtime=self.model_runtime,
                )
            )
            element = locate_result.element if locate_result else None
            if not element:
                return None

            ratio = getattr(context, "shrunk_shot_to_logical_ratio", 1.0)
            logical_x, logical_y = self._to_logical_point(element.center, ratio)
            logical_bbox = {
                "left": element.rect.left / ratio,
                "top": element.rect.top / ratio,
                "width": element.rect.width / ratio,
                "height": element.rect.height / ratio,
            }
            return LocateResult(
                selector=None,
                confidence=0.95,
                x=logical_x,
                y=logical_y,
                bounding_box=logical_bbox,
                reason=f"视觉定位: {element.description}",
            )
        except Exception as e:
            logger.warning(f"视觉定位失败: {str(e)}")
            return None
    
    def _merge_locate_results(self, dom_result: Optional[LocateResult], vision_result: Optional[LocateResult]) -> LocateResult:
        """
        融合DOM定位和视觉定位的结果
        :param dom_result: DOM定位结果
        :param vision_result: 视觉定位结果
        :return: 融合后的最终结果
        """
        if not dom_result and not vision_result:
            raise ElementNotFoundError("未找到匹配的元素")
        
        if not vision_result:
            return dom_result
        if not dom_result:
            return vision_result
        
        # 选择置信度更高的结果
        if dom_result.confidence >= vision_result.confidence:
            logger.debug(f"选择DOM定位结果，置信度: {dom_result.confidence}")
            return dom_result
        else:
            logger.debug(f"选择视觉定位结果，置信度: {vision_result.confidence}")
            return vision_result
    
    def locate(self, element_description: str, **kwargs) -> Tuple[float, float]:
        """
        定位元素，返回元素中心点坐标
        :param element_description: 自然语言描述的元素，比如 "蓝色的搜索按钮"、"用户名输入框"
        :return: (x坐标, y坐标)
        """
        logger.info(f"开始定位元素: {element_description}")

        if self._is_web_device():
            # 浏览器保留原有 DOM/selector 定位主链路，视觉仅作为回退。
            dom_result = self._locate_by_dom(element_description, **kwargs)
            if dom_result and dom_result.confidence >= self.confidence_threshold:
                final_result = dom_result
            else:
                vision_result = self._locate_by_vision(element_description, **kwargs)
                final_result = self._merge_locate_results(dom_result, vision_result)
        else:
            # 非 Web 端默认走视觉定位，模型不可用时回退到本地 UI 树，再退回旧 DOM 逻辑。
            vision_result = self._locate_by_vision(element_description, **kwargs)
            if vision_result and vision_result.confidence >= self.confidence_threshold:
                final_result = vision_result
            else:
                native_result = self._locate_by_native_tree(element_description)
                if native_result and native_result.confidence >= self.confidence_threshold:
                    final_result = native_result
                else:
                    dom_result = self._locate_by_dom(element_description, **kwargs)
                    final_result = self._merge_locate_results(
                        self._merge_locate_results(native_result, dom_result),
                        vision_result,
                    )

        if final_result.confidence < self.confidence_threshold:
            raise LocateConfidenceLowError(
                f"元素定位置信度 {final_result.confidence} 低于阈值 {self.confidence_threshold}",
                data={"result": final_result.model_dump()}
            )

        logger.info(
            f"元素定位成功: 坐标=({final_result.x:.2f}, {final_result.y:.2f}), "
            f"置信度={final_result.confidence}, 说明={final_result.reason}"
        )
        self.last_result = final_result
        self._save_debug_visualization(element_description, final_result)
        return (final_result.x, final_result.y)
    
    def extract_info(self, extract_description: str, **kwargs) -> Dict[str, Any]:
        """
        提取页面信息
        :param extract_description: 提取信息的描述，比如 "提取页面所有商品的标题和价格"
        :return: 提取结果
        """
        logger.info(f"开始提取页面信息: {extract_description}")
        try:
            context = self._run_async(self._build_context(**kwargs))
            result = self._run_async(
                self.service.extract(
                    extract_description,
                    model_runtime=self.model_runtime,
                    opt=ServiceExtractOption(screenshot_included=True, dom_included=False),
                    context=context,
                )
            )
            data = result.get("data")
            reason = result.get("thought") or ""
            confidence = 1.0 if data not in (None, "", [], {}) else 0.0
            logger.info(f"视觉信息提取完成，置信度={confidence}")
            logger.debug(f"提取结果: {data}")
            return {
                "data": data,
                "confidence": confidence,
                "reason": reason,
            }
        except Exception as e:
            logger.error(f"信息提取失败: {str(e)}")
            raise ModelResponseError(f"信息提取失败: {str(e)}") from e
