from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
import asyncio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client as http_connect
from mcp.client.stdio import StdioServerParameters, stdio_client
from ..base import BaseDevice
from common.config import settings
from common.logger import logger
from common.exceptions import BrowserLaunchError as DeviceConnectionError, ActionExecutionError, BrowserError as DeviceError

class McpPlaywrightDevice(BaseDevice):
    """
    MCP协议对接的Playwright设备，支持两种模式：
    1. HTTP模式：对接远程/云浏览器MCP服务，适合分布式部署
    2. STDIO模式：对接本地MCP服务（如Claude Desktop自带的Playwright MCP）
    完全兼容原有BaseDevice接口，业务代码零修改即可切换
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mcp_server_url: str = kwargs.get("mcp_server_url", getattr(settings, "MCP_SERVER_URL", ""))
        self.mcp_api_key: str = kwargs.get("mcp_api_key", getattr(settings, "MCP_API_KEY", ""))
        self.mcp_timeout: int = kwargs.get("mcp_timeout", getattr(settings, "MCP_TIMEOUT", 60))
        self._session: Optional[ClientSession] = None
        self._context_id: Optional[str] = None
        self._page_id: Optional[str] = None
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._http_ctx = None  # 存储HTTP连接上下文，用于关闭
        self._http_client = None  # 存储httpx客户端，用于关闭

    def _run_async(self, coro):
        """同步执行异步代码，适配现有同步架构"""
        return self._loop.run_until_complete(coro)

    def launch(self) -> None:
        """连接MCP服务并初始化浏览器上下文"""
        async def _launch():
            try:
                logger.info(f"连接MCP Playwright服务：{self.mcp_server_url}")
                # 1. 建立MCP连接
                if self.mcp_server_url.startswith(("http://", "https://")):
                    # HTTP模式：对接远程云浏览器MCP服务
                    headers = {}
                    if self.mcp_api_key:
                        headers["X-API-Key"] = self.mcp_api_key
                    # 新版MCP SDK需要自己创建httpx客户端配置headers和超时
                    self._http_client = httpx.AsyncClient(
                        headers=headers,
                        timeout=self.mcp_timeout
                    )
                    # 手动管理连接上下文，避免async with自动关闭
                    self._http_ctx = http_connect(
                        url=self.mcp_server_url,
                        http_client=self._http_client
                    )
                    read_stream, write_stream, _ = await self._http_ctx.__aenter__()
                    # 手动创建ClientSession
                    self._session = ClientSession(read_stream, write_stream)
                    # 完成MCP协议初始化握手
                    await self._session.initialize()
                    logger.info("MCP协议初始化握手完成")
                else:
                    # STDIO模式：对接本地运行的MCP服务（如Claude Playwright MCP）
                    cmd_parts = self.mcp_server_url.split(" ")
                    server_params = StdioServerParameters(
                        command=cmd_parts[0],
                        args=cmd_parts[1:] if len(cmd_parts) > 1 else [],
                        env=None
                    )
                    session_ctx = stdio_client(server_params)
                    self._session = await session_ctx.__aenter__()

                # 2. 初始化浏览器上下文
                create_ctx_resp = await self._session.call_tool(
                    "playwright_create_context",
                    parameters={
                        "viewport": {
                            "width": self.viewport_width,
                            "height": self.viewport_height
                        },
                        "headless": self.headless,
                        "user_agent": self.user_agent
                    }
                )
                self._context_id = create_ctx_resp.content[0].text.strip()
                logger.debug(f"MCP上下文创建成功：{self._context_id}")

                # 3. 新建页面
                create_page_resp = await self._session.call_tool(
                    "playwright_new_page",
                    parameters={"context_id": self._context_id}
                )
                self._page_id = create_page_resp.content[0].text.strip()
                logger.info("MCP Playwright设备初始化成功")

            except Exception as e:
                logger.error(f"连接MCP Playwright服务失败：{str(e)}")
                raise DeviceConnectionError(f"MCP连接失败：{str(e)}") from e

        return self._run_async(_launch())

    def close(self) -> None:
        """关闭MCP连接和浏览器资源"""
        async def _close():
            try:
                if self._page_id:
                    await self._session.call_tool(
                        "playwright_close_page",
                        parameters={"page_id": self._page_id}
                    )
                if self._context_id:
                    await self._session.call_tool(
                        "playwright_close_context",
                        parameters={"context_id": self._context_id}
                    )
                if self._session:
                    await self._session.__aexit__(None, None, None)
                # 关闭HTTP连接上下文
                if self._http_ctx:
                    await self._http_ctx.__aexit__(None, None, None)
                # 关闭httpx客户端
                if self._http_client:
                    await self._http_client.aclose()
                self._loop.close()
                logger.info("MCP Playwright设备已关闭")
            except Exception as e:
                logger.warning(f"关闭MCP设备时出现警告：{str(e)}")

        return self._run_async(_close())

    def goto(self, url: str, **kwargs) -> None:
        """跳转到指定URL"""
        async def _goto():
            try:
                logger.debug(f"MCP导航到：{url}")
                await self._session.call_tool(
                    "playwright_goto",
                    parameters={
                        "page_id": self._page_id,
                        "url": url,
                        "timeout": kwargs.get("timeout", self.timeout)
                    }
                )
                self.current_url = url
            except Exception as e:
                logger.error(f"MCP导航失败：{str(e)}")
                raise ActionExecutionError(f"导航失败：{str(e)}") from e

        return self._run_async(_goto())

    def get_page_content(self) -> str:
        """获取页面HTML内容"""
        async def _get_content():
            resp = await self._session.call_tool(
                "playwright_get_page_content",
                parameters={"page_id": self._page_id}
            )
            return resp.content[0].text.strip()

        return self._run_async(_get_content())

    def get_dom_tree(self) -> Dict[str, Any]:
        """获取结构化DOM树（和本地Playwright返回格式完全一致）"""
        async def _get_dom():
            resp = await self._session.call_tool(
                "playwright_get_dom_tree",
                parameters={"page_id": self._page_id}
            )
            import json
            return json.loads(resp.content[0].text.strip())

        return self._run_async(_get_dom())

    def screenshot(self, save_path: Optional[Path] = None, full_page: bool = True) -> bytes:
        """截图，支持保存到本地路径"""
        async def _screenshot():
            resp = await self._session.call_tool(
                "playwright_screenshot",
                parameters={
                    "page_id": self._page_id,
                    "full_page": full_page,
                    "encoding": "base64"
                }
            )
            import base64
            img_bytes = base64.b64decode(resp.content[0].text.strip())
            if save_path:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(img_bytes)
                logger.debug(f"MCP截图已保存到：{save_path}")
            return img_bytes

        return self._run_async(_screenshot())

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        """点击元素，支持选择器或坐标"""
        async def _click():
            try:
                params = {"page_id": self._page_id, "timeout": kwargs.get("timeout", self.timeout)}
                if selector:
                    logger.debug(f"MCP点击元素：{selector}")
                    params["selector"] = selector
                elif position:
                    x, y = position
                    logger.debug(f"MCP点击坐标：({x}, {y})")
                    params["position"] = {"x": x, "y": y}
                else:
                    raise ValueError("selector和position不能同时为空")

                await self._session.call_tool("playwright_click", parameters=params)
            except Exception as e:
                logger.error(f"MCP点击失败：{str(e)}")
                raise ActionExecutionError(f"点击失败：{str(e)}") from e

        return self._run_async(_click())

    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None:
        """输入文本，支持选择器或点击坐标后输入"""
        async def _input():
            try:
                params = {"page_id": self._page_id, "text": text, "clear_before": clear_before, "timeout": kwargs.get("timeout", self.timeout)}
                if selector:
                    logger.debug(f"MCP输入文本到元素：{selector}，内容：{text[:20]}...")
                    params["selector"] = selector
                elif position:
                    x, y = position
                    logger.debug(f"MCP点击坐标({x}, {y})并输入：{text[:20]}...")
                    params["position"] = {"x": x, "y": y}
                else:
                    raise ValueError("selector和position不能同时为空")

                await self._session.call_tool("playwright_fill", parameters=params)
            except Exception as e:
                logger.error(f"MCP输入失败：{str(e)}")
                raise ActionExecutionError(f"输入失败：{str(e)}") from e

        return self._run_async(_input())

    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None:
        """滚动页面"""
        async def _scroll():
            try:
                distance = distance or self.viewport_height * 0.8
                logger.debug(f"MCP页面向{direction}滚动{distance}像素")
                await self._session.call_tool(
                    "playwright_scroll",
                    parameters={
                        "page_id": self._page_id,
                        "direction": direction,
                        "distance": distance
                    }
                )
            except Exception as e:
                logger.error(f"MCP滚动失败：{str(e)}")
                raise ActionExecutionError(f"滚动失败：{str(e)}") from e

        return self._run_async(_scroll())

    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool:
        """等待元素出现"""
        async def _wait():
            try:
                await self._session.call_tool(
                    "playwright_wait_for_selector",
                    parameters={
                        "page_id": self._page_id,
                        "selector": selector,
                        "timeout": timeout or self.timeout
                    }
                )
                return True
            except Exception as e:
                logger.warning(f"等待元素{selector}超时：{str(e)}")
                return False

        return self._run_async(_wait())

    def evaluate_script(self, script: str, *args) -> Any:
        """执行JavaScript脚本"""
        async def _evaluate():
            resp = await self._session.call_tool(
                "playwright_evaluate",
                parameters={
                    "page_id": self._page_id,
                    "script": script,
                    "args": list(args)
                }
            )
            import json
            return json.loads(resp.content[0].text.strip())

        return self._run_async(_evaluate())

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
