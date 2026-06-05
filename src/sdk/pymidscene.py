from typing import Optional, Dict, Any, List
from device import get_browser, BaseBrowser
from llm import get_llm
from core.locator import ElementLocator
from common.logger import logger
from common.config import settings
from common.exceptions import ActionExecutionError, AssertionError, TimeoutError
import time
import json
import re


class PyMidscene:
    """PyMidscene 主 SDK 入口类，完全兼容原Midscene API规范"""
    
    def __init__(
        self,
        browser_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        vision_provider: Optional[str] = None,
        **kwargs
    ):
        self.browser: BaseBrowser = get_browser(browser_provider, **kwargs.get("browser_options", {}))
        self.llm = get_llm(llm_provider, **kwargs.get("llm_options", {}))
        # 视觉模型（可选）
        self.vision_model = None
        if vision_provider:
            # 后续实现视觉模型工厂后替换
            pass
        self.locator = ElementLocator(self.browser, self.llm, self.vision_model)
        self._launched = False
        # 执行上下文，存储变量、结果等
        self.context: Dict[str, Any] = {}
    
    def launch(self) -> None:
        """启动浏览器"""
        if not self._launched:
            self.browser.launch()
            self._launched = True
    
    def close(self) -> None:
        """关闭浏览器"""
        if self._launched:
            self.browser.close()
            self._launched = False
    
    def goto(self, url: str, **kwargs) -> None:
        """跳转到指定 URL"""
        if not self._launched:
            self.launch()
        self.browser.goto(url, **kwargs)
    
    def click(self, element_description: str, **kwargs) -> None:
        """
        通过自然语言描述点击元素
        :param element_description: 元素描述，比如 "搜索按钮"、"登录按钮"
        """
        logger.info(f"点击元素: {element_description}")
        position = self.locator.locate(element_description, **kwargs)
        self.browser.click(position=position)
    
    def input(self, element_description: str, text: str, **kwargs) -> None:
        """
        通过自然语言描述输入文本
        :param element_description: 元素描述，比如 "搜索输入框"、"用户名输入框"
        :param text: 要输入的文本
        """
        logger.info(f"向 {element_description} 输入文本: {text}")
        position = self.locator.locate(element_description, **kwargs)
        self.browser.input(text, position=position)
    
    def extract(self, extract_description: str, **kwargs) -> Dict[str, Any]:
        """
        提取页面信息
        :param extract_description: 提取描述，比如 "提取页面所有商品的标题和价格"
        :return: 提取结果
        """
        logger.info(f"提取信息: {extract_description}")
        return self.locator.extract_info(extract_description, **kwargs)
    
    def run_yaml(self, yaml_path: str, **kwargs) -> Dict[str, Any]:
        """
        运行 YAML 自动化流程
        :param yaml_path: YAML 文件路径
        :return: 执行结果
        """
        from core.yaml_parser import YAMLParser
        from core.task_executor import TaskExecutor
        
        logger.info(f"运行 YAML 流程: {yaml_path}")
        parser = YAMLParser()
        tasks = parser.parse(yaml_path)
        executor = TaskExecutor(self.browser, self.llm)
        result = executor.execute(tasks, **kwargs)
        return result
    
    def screenshot(self, save_path: Optional[str] = None, **kwargs) -> bytes:
        """截图"""
        from pathlib import Path
        save_path = Path(save_path) if save_path else None
        return self.browser.screenshot(save_path, **kwargs)
    
    def __enter__(self):
        self.launch()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 快捷方法
def create_client(**kwargs) -> PyMidscene:
    """创建 PyMidscene 客户端"""
    return PyMidscene(**kwargs)
