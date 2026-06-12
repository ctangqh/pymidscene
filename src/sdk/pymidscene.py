import asyncio
from typing import Optional, Dict, Any
from device import get_device, BaseDevice
from llm import get_llm
from core.locator import ElementLocator
from core.agent.agent import Agent
from core.types import ServiceExtractOption
from core.agent.yaml_runner import YamlScript, ScriptPlayer
from common.logger import logger
from common.config import settings
import json
import traceback
from core.anomaly_guard import UIAnomalyGuard


class PyMidscene:
    """PyMidscene 主 SDK 入口类"""
    
    def __init__(
        self,
        device_provider: Optional[str] = None,
        llm_provider: Optional[str] = None,
        vision_provider: Optional[str] = None,
        debug: bool = False,
        **kwargs
    ):
        if device_provider is None:
            device_provider = kwargs.pop("device_type", None)

        device_options = kwargs.get("device_options", {})
        llm_options = kwargs.get("llm_options", {})
        vision_options = kwargs.get("vision_options", {})

        self.device: BaseDevice = get_device(device_provider, **device_options)
        self.llm = get_llm(llm_provider, **llm_options)
        self.vision_model = self._init_vision_model(vision_provider, vision_options)
        
        # Debug mode
        self.debug = debug
        if self.debug:
            settings.DEBUG = True
            logger.info("PyMidscene 调试模式已启用")
        
        # Legacy locator (we'll remove this later, but keep it just in case)
        self.locator = ElementLocator(self.device, self.llm, self.vision_model)
        
        # Agent-based architecture (only mode now)
        self._agent: Optional[Agent] = None
        self._agent_options = kwargs
        
        self._launched = False
        self.context: Dict[str, Any] = {}
        
        # Event loop management
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _init_vision_model(self, vision_provider: Optional[str], vision_options: Optional[Dict[str, Any]] = None) -> Any:
        if not settings.LOCATE_USE_VISION:
            return None

        vision_config = settings.vision_config
        provider = vision_provider or vision_config.provider
        options = dict(vision_options or {})

        options.setdefault("model", vision_config.model)
        options.setdefault("base_url", vision_config.base_url)
        options.setdefault("api_key", vision_config.api_key)
        options.setdefault("timeout", vision_config.timeout)
        options.setdefault("max_retries", vision_config.max_retries)

        try:
            vision_llm = get_llm(provider, **options)
            if not getattr(vision_llm.capabilities, "supports_vision", False):
                raise ValueError(f"provider '{provider}' does not support vision")
            return vision_llm
        except Exception as e:
            if vision_provider or vision_options:
                raise
            logger.warning(f"初始化视觉模型失败，回退到通用 LLM: {e}")
            return self.llm
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run_async(self, coro):
        loop = self._get_loop()
        if loop.is_running():
            try:
                coro.send(None)
            except StopIteration as done:
                return done.value
            finally:
                if hasattr(coro, "close"):
                    coro.close()
            raise RuntimeError("PyMidscene sync SDK cannot run an async operation that suspends while an event loop is already running")
        return loop.run_until_complete(coro)
    
    @property
    def agent(self) -> Agent:
        """Get or create the Agent instance"""
        if self._agent is None:
            self._agent = Agent(
                self.device,
                opts=self._agent_options,
                llm=self.llm,
                vision_llm=self.vision_model or self.llm,
            )
        return self._agent
    
    def launch(self) -> None:
        """启动设备"""
        try:
            if not self._launched:
                self.device.launch()
                self._launched = True
        except Exception as e:
            self._handle_error("启动设备", e)
    
    def close(self, **kwargs) -> None:
        """关闭应用（如果是原生设备）并关闭设备"""
        try:
            interface_type = getattr(self.device, "interface_type", "")
            if interface_type not in ("web", "browser"):
                if hasattr(self.device, "_execute_mcp_action"):
                    tool_name = None
                    if interface_type in ("windows", "hypium", "android", "ios"):
                        tool_name = "delete_session"
                    
                    if tool_name:
                        try:
                            self.device._execute_mcp_action(tool_name, **kwargs)
                        except Exception as e:
                            logger.warning(f"关闭应用时发生错误: {e}")
            
            if self._launched:
                self.device.close()
                self._launched = False
                if self._loop and not self._loop.is_running():
                    self._loop.close()
        except Exception as e:
            logger.warning(f"关闭设备时发生错误: {e}")
    
    def goto(self, target: str, **kwargs) -> Any:
        """跳转到指定目标：浏览器 → URL，原生设备 → 启动应用"""
        try:
            if not self._launched:
                self.launch()
            
            interface_type = getattr(self.device, "interface_type", "")
            if interface_type in ("web", "browser"):
                logger.info(f"跳转到 URL: {target}")
                UIAnomalyGuard(self.device, llm=self.llm, vision_llm=self.vision_model or self.llm).handle_sync("goto")
                self.device.goto(target, **kwargs)
                UIAnomalyGuard(self.device, llm=self.llm, vision_llm=self.vision_model or self.llm).handle_sync("goto")
            else:
                logger.info(f"启动应用: {target}")
                if hasattr(self.device, "_execute_mcp_action"):
                    tool_name = "create_session"
                    params = {"app": target}
                    params.update(kwargs)
                    return self.device._execute_mcp_action(tool_name, **params)
                
                raise NotImplementedError(f"goto not fully implemented for device type: {type(self.device).__name__}")
        except Exception as e:
            self._handle_error("跳转/启动应用", e, {"target": target, "kwargs": kwargs})
    
    def ai_click(self, element_description: str, **kwargs) -> None:
        """通过自然语言描述点击元素"""
        try:
            logger.info(f"点击元素: {element_description}")
            self._run_async(self.agent.ai_tap(element_description, kwargs))
            if self.debug:
                logger.debug(f"调试: 点击操作完成")
        except Exception as e:
            self._handle_error("点击元素", e, {"element_description": element_description})
    
    # 保留 ai_tap 作为别名
    def ai_tap(self, element_description: str, **kwargs) -> None:
        self.ai_click(element_description, **kwargs)
    
    def ai_input(self, element_description: str, text: str, **kwargs) -> None:
        """通过自然语言描述输入文本"""
        try:
            logger.info(f"向 {element_description} 输入文本: {text}")
            opt = dict(kwargs)
            opt["value"] = text
            self._run_async(self.agent.ai_input(element_description, opt))
            if self.debug:
                logger.debug(f"调试: 输入操作完成")
        except Exception as e:
            self._handle_error("输入文本", e, {"element_description": element_description, "text": text})
    
    def ai_extract(self, extract_description: str, **kwargs) -> Any:
        """提取页面信息"""
        try:
            logger.info(f"提取信息: {extract_description}")
            opt = ServiceExtractOption(**kwargs) if kwargs else None
            result = self._run_async(self.agent.ai_query(extract_description, opt))
            if self.debug:
                logger.debug(f"调试: 提取结果: {result}")
            return result
        except Exception as e:
            self._handle_error("提取信息", e, {"extract_description": extract_description})
    
    # 保留 ai_query 作为别名
    def ai_query(self, extract_description: str, **kwargs) -> Any:
        return self.ai_extract(extract_description, **kwargs)
    
    def ai_act(self, task_prompt: str, **kwargs) -> Optional[str]:
        """自主规划并执行任务"""
        try:
            return self._run_async(self.agent.ai_act(task_prompt, kwargs))
        except Exception as e:
            self._handle_error("执行任务", e, {"task_prompt": task_prompt})
    
    def ai_assert(self, assertion: str, msg: Optional[str] = None, **kwargs) -> None:
        """断言页面状态"""
        try:
            opt = dict(kwargs)
            self._run_async(self.agent.ai_assert(assertion, msg, opt or None))
        except Exception as e:
            self._handle_error("断言", e, {"assertion": assertion, "msg": msg})
    
    def ai_wait_for(self, assertion: str, **kwargs) -> None:
        """等待断言成立"""
        try:
            opt = dict(kwargs)
            self._run_async(self.agent.ai_wait_for(assertion, opt or None))
        except Exception as e:
            self._handle_error("等待", e, {"assertion": assertion})
    
    def ai_locate(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """定位元素"""
        try:
            return self._run_async(self.agent.ai_locate(prompt, kwargs))
        except Exception as e:
            self._handle_error("定位元素", e, {"prompt": prompt})
    
    def run_yaml(self, yaml_path: str, **kwargs) -> Dict[str, Any]:
        """运行 YAML 自动化流程"""
        try:
            logger.info(f"运行 YAML 流程: {yaml_path}")
            script = YamlScript.from_file(yaml_path)

            async def _run():
                player = ScriptPlayer(script, lambda: {"agent": self.agent, "freeFn": []})
                await player.run()
                return {"result": player.result, "status": player.status}

            return self._run_async(_run())
        except Exception as e:
            self._handle_error("运行 YAML 流程", e, {"yaml_path": yaml_path})
    
    def screenshot(self, filename: Optional[str] = None, **kwargs) -> bytes:
        """截图
        :param filename: 文件名（可选，如 "my_screenshot.png"），不指定则自动生成
        :param kwargs: 其他参数
        :return: 截图字节
        """
        try:
            from pathlib import Path
            from datetime import datetime

            # 获取保存目录
            save_dir = Path(settings.REPORT_SCREENSHOT_SAVE_DIR)
            save_dir.mkdir(parents=True, exist_ok=True)

            # 生成保存路径
            if filename:
                # 如果filename包含路径，使用它；否则使用默认目录
                filename_path = Path(filename)
                if filename_path.is_absolute():
                    save_path = filename_path
                else:
                    save_path = save_dir / filename
            else:
                # 自动生成文件名
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                save_path = save_dir / f"screenshot_{timestamp}.png"

            # 保存截图
            screenshot_bytes = self.device.screenshot(save_path, **kwargs)

            if self.debug:
                logger.debug(f"调试: 截图已保存到 {save_path}")

            return screenshot_bytes
        except Exception as e:
            self._handle_error("截图", e, {"filename": filename})

    def keyboard_press(self, key_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """按下快捷键"""
        try:
            guard = UIAnomalyGuard(self.device, llm=self.llm, vision_llm=self.vision_model or self.llm)
            before_result = guard.handle_sync(f"before_keyboard_press_{key_name}")
            logger.debug(f"[PyMidscene] keyboard_press before-guard result: key={key_name}, result={before_result}")
            self.device.keyboard_press(key_name, **kwargs)
            after_result = guard.handle_sync(f"after_keyboard_press_{key_name}")
            logger.debug(f"[PyMidscene] keyboard_press after-guard result: key={key_name}, result={after_result}")
            return after_result
        except Exception as e:
            self._handle_error("按下快捷键", e, {"key_name": key_name})
    
    def _handle_error(self, operation: str, exception: Exception, context: Optional[Dict[str, Any]] = None) -> None:
        """内部错误处理方法"""
        error_msg = (
            f"PyMidscene 错误: {operation} 失败\n"
            f"异常信息: {str(exception)}\n"
        )
        if context:
            error_msg += f"上下文信息: {json.dumps(context, ensure_ascii=False, indent=2)}\n"
        error_msg += f"堆栈跟踪:\n{traceback.format_exc()}\n"
        logger.error(error_msg)
        raise Exception(error_msg) from exception

    def __enter__(self) -> "PyMidscene":
        self.launch()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def create_client(
    device_provider: Optional[str] = None,
    llm_provider: Optional[str] = None,
    vision_provider: Optional[str] = None,
    mcp_name: Optional[str] = None,
    mcp_server_url: Optional[str] = None,
    debug: bool = False,
    device_options: Optional[Dict[str, Any]] = None,
    llm_options: Optional[Dict[str, Any]] = None,
    vision_options: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PyMidscene:
    """创建 PyMidscene 客户端"""
    try:
        return PyMidscene(
            device_provider=device_provider,
            llm_provider=llm_provider,
            vision_provider=vision_provider,
            mcp_name=mcp_name,
            mcp_server_url=mcp_server_url,
            debug=debug,
            device_options=device_options or {},
            llm_options=llm_options or {},
            vision_options=vision_options or {},
            **kwargs
        )
    except Exception as e:
        error_msg = (
            f"创建 PyMidscene 客户端失败: {str(e)}\n\n"
            f"参数: device_provider={device_provider}, llm_provider={llm_provider}, "
            f"vision_provider={vision_provider}, mcp_name={mcp_name}, "
            f"mcp_server_url={mcp_server_url}, debug={debug}\n\n"
            f"堆栈跟踪:\n{traceback.format_exc()}\n\n"
            f"常见问题:\n"
            f"1. 检查 device_provider 是否正确（支持: mcp_winapp, mcp_hypium, mcp_android, mcp_ios, mcp_playwright, browser）\n"
            f"2. 检查 mcp_name 是否在 config.MCP_SERVERS 中定义\n"
            f"3. 检查对应的 MCP 服务器是否已启动\n"
            f"4. 检查 LLM/VISION 配置是否正确（如 API Key）"
        )
        raise Exception(error_msg) from e
