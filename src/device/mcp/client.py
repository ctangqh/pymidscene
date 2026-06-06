"""
MCP Playwright Device - Adapter for the OFFICIAL @playwright/mcp server.

Supports two transports:
  1. stdio: launch a local @playwright/mcp via npx (no remote server needed)
  2. streamable HTTP: connect to a remote @playwright/mcp HTTP endpoint

Tool names follow the official Microsoft schema (browser_navigate, browser_type,
browser_click, browser_evaluate, browser_take_screenshot, browser_snapshot,
browser_press_key, etc.), NOT the custom playwright_* names from earlier drafts.
"""
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path
import asyncio
import base64
import json
import shutil
import threading
import shlex

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    from mcp.client.streamable_http import streamable_http_client as streamablehttp_client

from ..base import BaseDevice
from common.config import settings
from common.logger import logger
from common.exceptions import (
    BrowserLaunchError as DeviceConnectionError,
    ActionExecutionError,
    BrowserError as DeviceError,
)


class McpPlaywrightDevice(BaseDevice):
    """
    Device backed by the official @playwright/mcp server.

    Transport selection:
      - mcp_server_url starts with http:// or https://  ->  streamable HTTP
      - mcp_stdio_command provided                       ->  stdio with that cmd
      - mcp_server_url empty                             ->  stdio with
        `npx -y @playwright/mcp@latest --headless --isolated ...` defaults
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mcp_server_url: str = kwargs.get(
            "mcp_server_url", getattr(settings, "MCP_SERVER_URL", "")
        )
        self.mcp_api_key: str = kwargs.get(
            "mcp_api_key", getattr(settings, "MCP_API_KEY", "")
        )
        self.mcp_timeout: int = kwargs.get(
            "mcp_timeout", getattr(settings, "MCP_TIMEOUT", 60)
        )
        self.mcp_stdio_command: Optional[List[str]] = kwargs.get("mcp_stdio_command")

        self._session: Optional[ClientSession] = None
        self._session_cm = None
        self._transport_cm = None
        # MCP session is bound to the loop that created it (anyio TaskGroup).
        # Dedicate one background thread+loop for all MCP I/O so sync API works.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    def _ensure_loop(self) -> None:
        if self._loop and self._thread and self._thread.is_alive():
            return
        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def runner():
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        t = threading.Thread(target=runner, name="mcp-device-loop", daemon=True)
        t.start()
        ready.wait()
        self._loop = loop
        self._thread = t

    def _submit(self, coro, timeout: Optional[int] = None):
        if not self._loop:
            raise DeviceError("MCP device loop not initialized; call launch() first")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout or self.mcp_timeout)

    def launch(self) -> None:
        self._ensure_loop()

        async def _launch():
            url = self.mcp_server_url
            if url and url.startswith(("http://", "https://")):
                logger.info(f"MCP connect (HTTP): {url}")
                self._transport_cm = streamablehttp_client(url)
                streams = await self._transport_cm.__aenter__()
                read_stream, write_stream = streams[0], streams[1]
            else:
                if self.mcp_stdio_command:
                    cmd = list(self.mcp_stdio_command)
                else:
                    cmd = [
                        "npx",
                        "-y",
                        "@playwright/mcp@latest",
                        "--headless" if self.headless else "--no-headless",
                        "--isolated",
                        "--no-sandbox",
                        "--browser",
                        "chromium",
                    ]
                logger.info(f"MCP connect (stdio): {' '.join(cmd)}")
                executable = shutil.which(cmd[0]) or cmd[0]
                params = StdioServerParameters(
                    command=executable, args=cmd[1:], env=None
                )
                self._transport_cm = stdio_client(params)
                streams = await self._transport_cm.__aenter__()
                read_stream, write_stream = streams[0], streams[1]

            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()
            init_result = await self._session.initialize()
            logger.info(
                f"MCP initialize ok: server={init_result.serverInfo.name} "
                f"v{init_result.serverInfo.version}"
            )

        try:
            self._submit(_launch(), timeout=120)
        except Exception as e:
            logger.error(f"MCP launch failed: {e}")
            raise DeviceConnectionError(f"MCP launch failed: {e}") from e

    def close(self) -> None:
        async def _close():
            try:
                if self._session_cm is not None:
                    await self._session_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"MCP session close warn: {e}")
            try:
                if self._transport_cm is not None:
                    await self._transport_cm.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"MCP transport close warn: {e}")
            self._session = None
            self._session_cm = None
            self._transport_cm = None

        try:
            if self._loop and self._thread and self._thread.is_alive():
                self._submit(_close(), timeout=30)
        finally:
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None

    async def _call(self, tool_name: str, arguments: Dict[str, Any]):
        if self._session is None:
            raise DeviceError("MCP session not initialized")
        return await self._session.call_tool(tool_name, arguments=arguments)

    @staticmethod
    def _first_text(result) -> str:
        if not result or not getattr(result, "content", None):
            return ""
        for part in result.content:
            if getattr(part, "type", "") == "text" and getattr(part, "text", None):
                return part.text
            if hasattr(part, "text") and part.text:
                return part.text
        return ""

    @staticmethod
    def _first_image_b64(result) -> Optional[str]:
        if not result or not getattr(result, "content", None):
            return None
        for part in result.content:
            data = getattr(part, "data", None)
            if data:
                return data
        return None

    @property
    def interface_type(self) -> str:
        return "browser"

    def goto(self, url: str, **kwargs) -> None:
        try:
            self._submit(self._call("browser_navigate", {"url": url}))
            self.current_url = url
        except Exception as e:
            raise ActionExecutionError(f"navigate failed: {e}") from e

    def get_page_content(self) -> str:
        try:
            result = self._submit(
                self._call(
                    "browser_evaluate",
                    {"function": "() => document.documentElement.outerHTML"},
                )
            )
            text = self._first_text(result)
            if text.startswith("### Error"):
                raise DeviceError(f"MCP browser error: {text}")
            return text
        except Exception as e:
            raise ActionExecutionError(f"get_page_content failed: {e}") from e

    def get_dom_tree(self) -> Dict[str, Any]:
        try:
            result = self._submit(self._call("browser_snapshot", {}))
            text = self._first_text(result)
            if text.startswith("### Error"):
                raise DeviceError(f"MCP browser error: {text}")
            return {"snapshot": text}
        except Exception as e:
            raise ActionExecutionError(f"get_dom_tree failed: {e}") from e

    def screenshot(
        self, save_path: Optional[Path] = None, full_page: bool = True
    ) -> bytes:
        try:
            args: Dict[str, Any] = {"type": "png"}
            if full_page:
                args["fullPage"] = True
            result = self._submit(self._call("browser_take_screenshot", args))
            b64 = self._first_image_b64(result)
            if not b64:
                text_content = self._first_text(result).strip()
                if text_content.startswith("### Error"):
                    raise DeviceError(f"MCP browser error: {text_content}")
                b64 = text_content

            try:
                img = base64.b64decode(b64) if b64 else b""
            except Exception as e:
                if b64 and len(b64) < 500:
                    raise DeviceError(f"MCP returned non-image data: {b64}") from e
                raise
            if save_path and img:
                p = Path(save_path) if not isinstance(save_path, Path) else save_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(img)
            return img
        except Exception as e:
            raise ActionExecutionError(f"screenshot failed: {e}") from e

    def click(
        self,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        **kwargs,
    ) -> None:
        if not selector:
            raise ActionExecutionError(
                "@playwright/mcp browser_click requires a selector/target."
            )
        try:
            self._submit(
                self._call(
                    "browser_click",
                    {
                        "element": kwargs.get("element", selector),
                        "target": selector,
                    },
                )
            )
        except Exception as e:
            raise ActionExecutionError(f"click failed: {e}") from e

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        if not selector:
            raise ActionExecutionError(
                "@playwright/mcp browser_type requires a selector/target."
            )
        try:
            args: Dict[str, Any] = {
                "element": kwargs.get("element", selector),
                "target": selector,
                "text": text,
            }
            if kwargs.get("submit"):
                args["submit"] = True
            self._submit(self._call("browser_type", args))
        except Exception as e:
            raise ActionExecutionError(f"input failed: {e}") from e

    def scroll(
        self,
        direction: str = "down",
        distance: Optional[int] = None,
        **kwargs,
    ) -> None:
        dist = int(distance or self.viewport_height * 0.8)
        sign = {
            "down": ("0", str(dist)),
            "up": ("0", str(-dist)),
            "right": (str(dist), "0"),
            "left": (str(-dist), "0"),
        }.get(direction, ("0", str(dist)))
        fn = f"() => window.scrollBy({sign[0]}, {sign[1]})"
        try:
            self._submit(self._call("browser_evaluate", {"function": fn}))
        except Exception as e:
            raise ActionExecutionError(f"scroll failed: {e}") from e

    def wait_for_selector(
        self, selector: str, timeout: Optional[int] = None, **kwargs
    ) -> bool:
        deadline_ms = timeout or self.timeout
        fn = (
            "async () => {"
            f"const sel = {json.dumps(selector)};"
            f"const deadline = Date.now() + {int(deadline_ms)};"
            "while (Date.now() < deadline) {"
            "  if (document.querySelector(sel)) return true;"
            "  await new Promise(r => setTimeout(r, 100));"
            "} return false;"
            "}"
        )
        try:
            result = self._submit(self._call("browser_evaluate", {"function": fn}))
            txt = self._first_text(result).strip().lower()
            return "true" in txt
        except Exception as e:
            logger.warning(f"wait_for_selector({selector}) error: {e}")
            return False

    def keyboard_press(self, key_name: str, **kwargs) -> None:
        try:
            self._submit(self._call("browser_press_key", {"key": key_name}))
        except Exception as e:
            raise ActionExecutionError(f"keyboard_press failed: {e}") from e

    def evaluate_script(self, script: str, *args) -> Any:
        s = script.strip()
        if not (s.startswith("(") or s.startswith("async") or s.startswith("function")):
            fn = f"() => {{ return ({s}); }}"
        else:
            fn = script
        try:
            result = self._submit(self._call("browser_evaluate", {"function": fn}))
            txt = self._first_text(result).strip()
            if not txt:
                return None
            try:
                return json.loads(txt)
            except (json.JSONDecodeError, ValueError):
                return txt
        except Exception as e:
            raise ActionExecutionError(f"evaluate failed: {e}") from e

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
