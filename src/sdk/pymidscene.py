import asyncio
from typing import Optional, Dict, Any, List
from device import get_browser, BaseBrowser
from llm import get_llm
from core.locator import ElementLocator
from core.agent.agent import Agent
from core.types import ServiceExtractOption
from core.agent.yaml_runner import YamlScript, ScriptPlayer
from common.logger import logger
from common.config import settings
from common.exceptions import ActionExecutionError, AssertionError
import time
import json
import re


class PyMidscene:
    """PyMidscene 主 SDK 入口类，完全兼容原Midscene API规范
    
    内部使用新的 Agent 架构，同时保持旧版 API 向后兼容。
    """
    
    def __init__(
        self,
        browser_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        vision_provider: Optional[str] = None,
        **kwargs
    ):
        self.browser: BaseBrowser = get_browser(browser_provider, **kwargs.get("browser_options", {}))
        self.device = self.browser  # 别名，提高兼容性
        self.llm = get_llm(llm_provider, **kwargs.get("llm_options", {}))
        # 视觉模型（可选）
        self.vision_model = None
        if vision_provider:
            # 后续实现视觉模型工厂后替换
            pass
        
        # Legacy locator (still works for backward compat)
        self.locator = ElementLocator(self.browser, self.llm, self.vision_model)
        
        # New Agent-based architecture
        self._agent: Optional[Agent] = None
        self._use_agent = kwargs.get("use_agent", True)
        self._agent_options = kwargs  # 保存所有选项供 Agent 使用
        
        self._launched = False
        # 执行上下文，存储变量、结果等
        self.context: Dict[str, Any] = {}
        
        # 统一的事件循环管理
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        """在统一的事件循环中运行异步协程"""
        loop = self._get_loop()
        if loop.is_running():
            # 如果已经在运行（例如在另一个异步任务中），尝试在当前线程运行
            return self._run_coroutine_same_thread(coro)
        return loop.run_until_complete(coro)

    def _run_coroutine_same_thread(self, coro):
        try:
            coro.send(None)
        except StopIteration as done:
            return done.value
        finally:
            if hasattr(coro, "close"):
                coro.close()
        raise RuntimeError("PyMidscene sync SDK cannot run an async operation that suspends while an event loop is already running")
    
    @property
    def agent(self) -> Agent:
        """Get or create the Agent instance"""
        if not self._use_agent:
            raise RuntimeError("Agent is disabled, set use_agent=True in constructor to enable")
        if self._agent is None:
            self._agent = Agent(self.browser, opts=self._agent_options, llm=self.llm)
        return self._agent
    
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
            if self._loop and not self._loop.is_running():
                self._loop.close()
    
    def goto(self, url: str, **kwargs) -> None:
        """跳转到指定 URL"""
        if not self._launched:
            self.launch()
        self.browser.goto(url, **kwargs)
    
    def click(self, element_description: str, **kwargs) -> None:
        """
        通过自然语言描述点击元素
        """
        logger.info(f"点击元素: {element_description}")
        position = self.locator.locate(element_description, **kwargs)
        self.browser.click(position=position)
    
    def input(self, element_description: str, text: str, **kwargs) -> None:
        """
        通过自然语言描述输入文本
        """
        logger.info(f"向 {element_description} 输入文本: {text}")
        position = self.locator.locate(element_description, **kwargs)
        self.browser.input(text, position=position)
    
    def extract(self, extract_description: str, **kwargs) -> Dict[str, Any]:
        """
        提取页面信息
        """
        logger.info(f"提取信息: {extract_description}")
        return self.locator.extract_info(extract_description, **kwargs)
    
    def run_yaml(self, yaml_path: str, **kwargs) -> Dict[str, Any]:
        """
        运行 YAML 自动化流程
        """
        logger.info(f"运行 YAML 流程: {yaml_path}")
        script = YamlScript.from_file(yaml_path)

        async def _run():
            player = ScriptPlayer(script, lambda: {"agent": self.agent, "freeFn": []})
            await player.run()
            return {"result": player.result, "status": player.status}

        return self._run_async(_run())
    
    def screenshot(self, save_path: Optional[str] = None, **kwargs) -> bytes:
        """截图"""
        from pathlib import Path
        path_obj: Optional[Path] = Path(save_path) if save_path is not None else None
        return self.browser.screenshot(path_obj, **kwargs)
    
    # === New Agent-based methods ===
    
    def ai_tap(self, element_description: str, **kwargs) -> None:
        """使用 Agent AI 点击元素"""
        self._run_async(self.agent.ai_tap(element_description, kwargs))
    
    def ai_click(self, element_description: str, **kwargs) -> None:
        """ai_tap 的别名"""
        self.ai_tap(element_description, **kwargs)
    
    def ai_input(self, element_description: str, text: str, **kwargs) -> None:
        """使用 Agent AI 输入文本"""
        opt = dict(kwargs)
        opt["value"] = text
        self._run_async(self.agent.ai_input(element_description, opt))
    
    def ai_act(self, task_prompt: str, **kwargs) -> Optional[str]:
        """使用 Agent AI 自主规划执行"""
        return self._run_async(self.agent.ai_act(task_prompt, kwargs))
    
    def ai_assert(self, assertion: str, msg: Optional[str] = None, **kwargs) -> None:
        """使用 Agent AI 断言"""
        opt = dict(kwargs)
        self._run_async(self.agent.ai_assert(assertion, msg, opt or None))
    
    def ai_query(self, demand, **kwargs) -> Any:
        """使用 Agent AI 查询页面信息"""
        opt = ServiceExtractOption(**kwargs) if kwargs else None
        return self._run_async(self.agent.ai_query(demand, opt))
    
    def ai_extract(self, demand, **kwargs) -> Any:
        """ai_query 的别名，兼容原 Midscene API"""
        return self.ai_query(demand, **kwargs)
    
    def ai_wait_for(self, assertion: str, **kwargs) -> None:
        """使用 Agent AI 等待断言成立"""
        opt = dict(kwargs)
        self._run_async(self.agent.ai_wait_for(assertion, opt or None))
    
    def ai_locate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """使用 Agent AI 定位元素"""
        return self._run_async(self.agent.ai_locate(prompt, kwargs))

    def __enter__(self):
        self.launch()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 快捷方法
def create_client(**kwargs) -> PyMidscene:
    """创建 PyMidscene 客户端"""
    return PyMidscene(**kwargs)
