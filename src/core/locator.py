from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from device.base import BaseBrowser
from llm.base import BaseLLM
from common.logger import logger
from common.config import settings
from common.exceptions import ElementNotFoundError, LocateConfidenceLowError, ModelResponseError


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
    
    def __init__(self, browser: BaseBrowser, llm: BaseLLM, vision_model=None):
        self.browser = browser
        self.llm = llm
        self.vision_model = vision_model
        self.confidence_threshold = settings.LOCATE_CONFIDENCE_THRESHOLD
    
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
            if not self.browser.wait_for_selector(selector, timeout=3000):
                return None
            
            # 获取元素边界框
            escaped_selector = selector.replace("'", "\\'")
            bbox = self.browser.evaluate_script(f"""() => {{
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
        raw_dom = self.browser.get_dom_tree()
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
    
    def _locate_by_vision(self, element_description: str, **kwargs) -> Optional[LocateResult]:
        """
        通过视觉分析定位元素（当前预留接口，后续实现）
        :param element_description: 元素描述
        :return: 定位结果
        """
        if not self.vision_model or not settings.LOCATE_USE_VISION:
            return None
        
        try:
            logger.info(f"通过视觉分析定位元素: {element_description}")
            # 截图
            screenshot_bytes = self.browser.screenshot()
            # 调用视觉模型分析
            # 后续实现视觉定位逻辑
            # result = self.vision_model.locate(screenshot_bytes, element_description)
            # return result
            return None
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
        
        # 1. DOM定位
        dom_result = self._locate_by_dom(element_description, **kwargs)
        
        # 2. 视觉定位（可选）
        vision_result = self._locate_by_vision(element_description, **kwargs)
        
        # 3. 融合结果
        final_result = self._merge_locate_results(dom_result, vision_result)
        
        # 4. 校验置信度
        if final_result.confidence < self.confidence_threshold:
            raise LocateConfidenceLowError(
                f"元素定位置信度 {final_result.confidence} 低于阈值 {self.confidence_threshold}",
                data={"result": final_result.model_dump()}
            )
        
        logger.info(
            f"元素定位成功: 坐标=({final_result.x:.2f}, {final_result.y:.2f}), "
            f"置信度={final_result.confidence}, 说明={final_result.reason}"
        )
        return (final_result.x, final_result.y)
    
    def extract_info(self, extract_description: str, **kwargs) -> Dict[str, Any]:
        """
        提取页面信息
        :param extract_description: 提取信息的描述，比如 "提取页面所有商品的标题和价格"
        :return: 提取结果
        """
        logger.info(f"开始提取页面信息: {extract_description}")
        
        # 获取页面内容
        page_content = self.browser.get_page_content()
        # 限制内容长度
        if len(page_content) > 15000:
            page_content = page_content[:15000] + "...[内容太长已截断]"
        
        # 构造prompt
        messages = [
            {
                "role": "system",
                "content": """你是一个专业的页面信息提取专家，根据用户提供的页面HTML内容和提取要求，准确提取所需信息。
请严格按照JSON格式返回结果：
1. data字段：提取到的信息，格式根据用户要求调整，可以是对象、数组等
2. confidence字段：提取结果的置信度，0-1之间
3. reason字段：简单说明提取结果的依据
注意：如果没有找到相关信息，data返回空，confidence返回0。"""
            },
            {
                "role": "user",
                "content": f"""页面HTML内容（已简化）：
```html
{page_content}
```

提取要求：{extract_description}

请返回提取结果："""
            }
        ]
        
        try:
            result = self.llm.structured_chat(messages, output_schema=ExtractResult)
            logger.info(f"信息提取完成，置信度={result.confidence}")
            logger.debug(f"提取结果: {result.data}")
            
            if result.confidence < self.confidence_threshold:
                logger.warning(f"提取结果置信度 {result.confidence} 低于阈值")
            
            return {
                "data": result.data,
                "confidence": result.confidence,
                "reason": result.reason
            }
            
        except Exception as e:
            logger.error(f"信息提取失败: {str(e)}")
            raise ModelResponseError(f"信息提取失败: {str(e)}") from e
