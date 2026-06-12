"""
智能元素定位引擎
"""
import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field

from device.base import BaseDevice
from llm.base import BaseLLM
from common.logger import logger
from common.config import settings
from common.exceptions import (
    ElementNotFoundError, 
    LocateConfidenceLowError, 
    ModelResponseError
)
from .service import Service
from .agent.context_parser import common_context_parser
from .types import ServiceExtractOption
from .uitree import uitree_manager


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
        """保存调试截图"""
        if not settings.DEBUG:
            return
        
        raw_bbox = result.bounding_box or {}
        if not raw_bbox:
            return
        
        # 准备 bbox
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
    
    def _extract_native_tree_payload(self, raw_data: Any) -> Any:
        """（保留用于向后兼容）"""
        if isinstance(raw_data, dict):
            for key in ["content", "xml", "value", "source", "pageSource", "page_source"]:
                if key in raw_data and raw_data[key]:
                    raw_data = raw_data[key]
                    break
        
        if isinstance(raw_data, str):
            text = raw_data.strip().lstrip("\ufeff")
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
        
        return raw_data
    
    def _extract_bounds_from_attrs(self, attrs: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        """（保留用于向后兼容）"""
        def _to_float(value):
            if value is None or value == "":
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        
        left = _to_float(attrs.get("left", attrs.get("x")))
        top = _to_float(attrs.get("top", attrs.get("y")))
        width = _to_float(attrs.get("width", attrs.get("w")))
        height = _to_float(attrs.get("height", attrs.get("h")))
        
        if left is not None and top is not None and width is not None and height is not None:
            return left, top, width, height
        
        bounds = attrs.get("bounds")
        if isinstance(bounds, str):
            m = re.match(r"\[([\d\-\.]+),([\d\-\.]+)\]\[([\d\-\.]+),([\d\-\.]+)\]", bounds.strip())
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
    
    def _simplify_dom(self, dom: Dict[str, Any], max_depth: int = 5, current_depth: int = 0) -> Dict[str, Any]:
        """简化 DOM 树（用于 Web 定位）"""
        if current_depth >= max_depth:
            return {}
        
        simplified = {
            "tag": dom.get("tagName", ""),
            "text": str(dom.get("text", ""))[:100].strip(),
        }
        
        useful_attrs = ["id", "class", "name", "placeholder", "href", "src", "type", "value", "aria-label", "role"]
        attrs = dom.get("attributes", {})
        filtered_attrs = {k: v for k, v in attrs.items() if k in useful_attrs}
        if filtered_attrs:
            simplified["attrs"] = filtered_attrs
        
        children = dom.get("children", [])
        if children and current_depth < max_depth - 1:
            simplified_children = []
            for child in children:
                simplified_child = self._simplify_dom(child, max_depth, current_depth + 1)
                if simplified_child and simplified_child.get("tag") not in ["script", "style", "noscript", "iframe"]:
                    simplified_children.append(simplified_child)
            if simplified_children:
                simplified["children"] = simplified_children
        
        return simplified
    
    def _get_element_position_by_selector(self, selector: str) -> Optional[Tuple[float, float, Dict[str, float]]]:
        """通过选择器获取元素位置（用于 Web 定位）"""
        try:
            if not self.device.wait_for_selector(selector, timeout=3000):
                return None
            
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
            
            center_x = bbox["x"] + bbox["width"] / 2
            center_y = bbox["y"] + bbox["height"] / 2
            
            return (center_x, center_y, bbox)
        except Exception as e:
            logger.warning(f"获取元素坐标失败: {e}")
            return None
    
    def _locate_by_dom(self, element_description: str, **kwargs) -> Optional[LocateResult]:
        """通过 DOM 结构定位元素（Web）"""
        logger.info(f"通过 DOM 结构分析定位元素: {element_description}")
        
        raw_dom = self.device.get_dom_tree()
        simplified_dom = self._simplify_dom(raw_dom)
        
        dom_json = json.dumps(simplified_dom, ensure_ascii=False, indent=2)
        if len(dom_json) > 8000:
            dom_json = dom_json[:8000] + "...[DOM太长已截断]"
        
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
{dom_json}

需要定位的元素描述：{element_description}

请返回定位结果："""
            }
        ]
        
        try:
            result = self.llm.structured_chat(messages, output_schema=LocateResult)
            logger.debug(f"DOM 定位结果: 选择器={result.selector}, 置信度={result.confidence}, 说明={result.reason}")
            
            if result.confidence <= 0 or not result.selector:
                logger.warning("DOM 定位未找到匹配元素")
                return None
            
            position = self._get_element_position_by_selector(result.selector)
            if not position:
                logger.warning(f"选择器 {result.selector} 未找到对应元素")
                return None
            
            result.x, result.y, result.bounding_box = position
            return result
        except Exception as e:
            logger.error(f"DOM 定位失败: {e}")
            return None
    
    def _locate_by_vision(self, element_description: str, **kwargs) -> Optional[LocateResult]:
        """通过视觉分析定位元素"""
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
            logger.warning(f"视觉定位失败: {e}")
            return None
    
    def _score_native_candidate(self, description: str, tokens: List[str], tag: str, attrs: Dict[str, Any]) -> float:
        """评分候选元素（保留用于向后兼容）"""
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
        
        searchable_fields = [name, automation_id, control_type, class_name, tag]
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
        """从属性生成选择器（保留用于向后兼容）"""
        for key in ("AutomationId", "resource-id", "resourceId", "identifier", "accessibilityIdentifier", "id"):
            value = attrs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    
    def _locate_by_native_tree(self, element_description: str) -> Optional[LocateResult]:
        """通过原生 UI 树定位元素（使用新的 uitree 模块）"""
        if self._is_web_device():
            return None
        
        try:
            raw_tree = self.device.get_dom_tree()
            device_type = getattr(self.device, "interface_type", None)
            
            logger.debug(f"尝试用 uitree 模块解析 UI 树，设备类型: {device_type}")
            parsed_tree = uitree_manager.parse(raw_tree, device_type)
            
            if not parsed_tree:
                logger.debug(f"uitree 模块解析失败，尝试旧逻辑")
                return self._locate_by_native_tree_fallback(element_description)
            
            # 使用解析后的树进行定位
            flat_nodes = parsed_tree.to_flat_list()
            logger.debug(f"解析到 {len(flat_nodes)} 个节点")
            
            description_tokens = [t for t in re.split(r"[\s,，、/]+", element_description) if t]
            best = None
            best_score = 0.0
            
            for node in flat_nodes:
                score = self._score_element_for_description(node, element_description, description_tokens)
                if score <= best_score or not node.bounds:
                    continue
                
                left, top, width, height = node.bounds
                if width <= 0 or height <= 0:
                    continue
                
                best_score = score
                best = LocateResult(
                    selector=self._selector_from_native_attrs(node.attributes),
                    confidence=min(0.99, 0.5 + score / 20.0),
                    x=left + width / 2,
                    y=top + height / 2,
                    bounding_box={
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                    },
                    reason=f"UI 树定位: 路径={' -> '.join(node.path)}, 得分={score:.1f}",
                )
            
            if best:
                logger.debug(f"UI 树定位成功: {best.reason}")
            return best
        except Exception as e:
            logger.warning(f"UI 树定位失败: {e}")
            return self._locate_by_native_tree_fallback(element_description)
    
    def _locate_by_native_tree_fallback(self, element_description: str) -> Optional[LocateResult]:
        """旧的回退定位逻辑（保留用于向后兼容）"""
        if self._is_web_device():
            return None
        
        try:
            raw_dom = self.device.get_dom_tree()
            payload = self._extract_native_tree_payload(raw_dom)
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
                    confidence=min(0.99, 0.5 + score / 20.0),
                    x=left + width / 2,
                    y=top + height / 2,
                    bounding_box={
                        "left": left,
                        "top": top,
                        "width": width,
                        "height": height,
                    },
                    reason=f"本地 UI 树定位: tag={tag}, name={name}",
                )
            
            return best
        except Exception as e:
            logger.warning(f"本地 UI 树定位失败: {e}")
            return None
    
    def _score_element_for_description(self, node, description: str, tokens: List[str]) -> float:
        """给元素节点打分"""
        score = 0.0
        lowered_description = description.lower()
        node_name = node.name.lower()
        
        if lowered_description and lowered_description == node_name:
            score += 10.0
        elif lowered_description and lowered_description in node_name:
            score += 7.0
        
        path_text = " ".join(node.path).lower()
        if lowered_description and lowered_description in path_text:
            score += 5.0
        
        for token in tokens:
            token_lower = token.lower()
            if token_lower == node_name:
                score += 6.0
            elif token_lower in node_name:
                score += 4.0
            elif token_lower in path_text:
                score += 3.0
        
        tag_lower = node.tag.lower()
        type_lower = node.control_type.lower()
        
        if any(k in description for k in ["输入", "编辑", "文本框", "编辑器", "text", "input"]) and (
            "edit" in tag_lower or "edit" in type_lower or "text" in type_lower or "input" in tag_lower
        ):
            score += 3.0
        
        if any(k in description for k in ["按钮", "点击", "button", "tap", "click"]) and (
            "button" in tag_lower or "button" in type_lower or "menuitem" in tag_lower
        ):
            score += 3.0
        
        if any(k in description for k in ["菜单", "menu"]) and (
            "menu" in tag_lower or "menu" in type_lower
        ):
            score += 3.0
        
        return score
    
    def _iter_native_tree_candidates(self, payload: Any):
        """迭代 UI 树候选节点（保留用于向后兼容）"""
        if payload is None:
            return
        
        if isinstance(payload, str):
            text = payload.strip()
            if text.startswith("<"):
                try:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(text)
                    for elem in root.iter():
                        yield {
                            "tag": elem.tag,
                            "attrs": dict(elem.attrib),
                        }
                except Exception:
                    pass
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
        
        child_keys = ["children", "nodes", "elements", "items", "subviews", "views", "child"]
        for key in child_keys:
            child = payload.get(key)
            if isinstance(child, (dict, list)):
                yield from self._iter_native_tree_candidates(child)
    
    def _merge_locate_results(self, dom_result: Optional[LocateResult], vision_result: Optional[LocateResult]) -> LocateResult:
        """合并定位结果"""
        if not dom_result and not vision_result:
            raise ElementNotFoundError("未找到匹配的元素")
        
        if not vision_result:
            return dom_result
        if not dom_result:
            return vision_result
        
        if dom_result.confidence >= vision_result.confidence:
            logger.debug(f"选择 DOM 定位结果，置信度: {dom_result.confidence}")
            return dom_result
        else:
            logger.debug(f"选择视觉定位结果，置信度: {vision_result.confidence}")
            return vision_result
    
    def locate(self, element_description: str, **kwargs) -> Tuple[float, float]:
        """定位元素，返回元素中心点坐标"""
        logger.info(f"开始定位元素: {element_description}")
        
        device_type = getattr(self.device, "interface_type", None)
        
        # 调试模式下保存 UI 树
        if settings.DEBUG:
            try:
                raw_tree = self.device.get_dom_tree()
                uitree_manager.save(
                    raw_tree,
                    element_description,
                    device_type=device_type
                )
            except Exception as e:
                print(f"[DEBUG] 保存 UI 树出错: {e}")
                import traceback
                traceback.print_exc()
        
        if self._is_web_device():
            dom_result = self._locate_by_dom(element_description, **kwargs)
            if dom_result and dom_result.confidence >= self.confidence_threshold:
                final_result = dom_result
            else:
                vision_result = self._locate_by_vision(element_description, **kwargs)
                final_result = self._merge_locate_results(dom_result, vision_result)
        else:
            native_result = self._locate_by_native_tree(element_description)
            if native_result and native_result.confidence >= self.confidence_threshold:
                logger.debug(f"选择 UI 树定位结果，置信度: {native_result.confidence}")
                final_result = native_result
            else:
                vision_result = self._locate_by_vision(element_description, **kwargs)
                if vision_result and vision_result.confidence >= self.confidence_threshold:
                    logger.debug(f"选择视觉定位结果，置信度: {vision_result.confidence}")
                    final_result = vision_result
                else:
                    dom_result = self._locate_by_dom(element_description, **kwargs)
                    final_result = self._merge_locate_results(
                        self._merge_locate_results(native_result, vision_result),
                        dom_result
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
        """提取页面信息"""
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
            logger.error(f"信息提取失败: {e}")
            raise ModelResponseError(f"信息提取失败: {e}") from e
