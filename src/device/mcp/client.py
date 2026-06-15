"""
MCP Device Implementation - Unified architecture for multiple device types.

Supported transports:
  1. stdio: launch a local MCP server via command line
  2. streamable HTTP: connect to a remote MCP HTTP endpoint
  3. SSE: connect to a remote MCP SSE endpoint
"""
import asyncio
import base64
import json
import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

import httpx
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    try:
        from mcp.client.streamable_http import streamable_http_client as streamablehttp_client
    except ImportError:
        streamablehttp_client = None

from ..base import BaseDevice
from common.config import settings
from common.logger import logger
from common.exceptions import (
    BrowserLaunchError as DeviceConnectionError,
    ActionExecutionError,
    BrowserError as DeviceError,
)


class BaseMcpDevice(BaseDevice):
    """
    Unified base class for all MCP-backed devices.
    Provides automatic tool mapping and async-sync bridging.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 1. MCP Connection settings
        mcp_name = kwargs.get("mcp_name")
        mcp_config = None
        
        if mcp_name and mcp_name in settings.MCP_SERVERS:
            mcp_config = settings.MCP_SERVERS[mcp_name]
            logger.debug(f"Using MCP config for '{mcp_name}'")

        self.mcp_server_url: str = kwargs.get(
            "mcp_server_url", 
            mcp_config.url if mcp_config else getattr(settings, "MCP_SERVER_URL", "")
        )
        self.mcp_transport: str = kwargs.get(
            "mcp_transport", 
            mcp_config.transport if mcp_config else ("sse" if "/sse" in self.mcp_server_url else "http")
        )
        self.mcp_api_key: str = kwargs.get(
            "mcp_api_key", 
            mcp_config.api_key if mcp_config else getattr(settings, "MCP_API_KEY", "")
        )
        self.mcp_timeout: int = kwargs.get(
            "mcp_timeout", 
            mcp_config.timeout if mcp_config else getattr(settings, "MCP_TIMEOUT", 60)
        )
        self.mcp_stdio_command: Optional[List[str]] = kwargs.get(
            "mcp_stdio_command",
            mcp_config.command if mcp_config else None
        )
        self.mcp_env: Optional[Dict[str, str]] = kwargs.get(
            "mcp_env",
            mcp_config.env if mcp_config else None
        )

        # 2. Tool Mapping - Subclasses should populate this
        # Format: { "action_name": {"tool": "mcp_tool_name", "mapper": callable_to_transform_args} }
        self._tool_map: Dict[str, Dict[str, Any]] = {}

        # 3. Internal State
        self._session: Optional[ClientSession] = None
        self._session_cm = None
        self._transport_cm = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._close_event: Optional[asyncio.Event] = None
        self._launch_ready = threading.Event()
        self._launch_error: Optional[Exception] = None

    # ==================== MCP Infrastructure ====================

    def _ensure_loop(self) -> None:
        if self._loop and self._thread and self._thread.is_alive():
            return
        loop = asyncio.new_event_loop()
        ready = threading.Event()

        def runner():
            asyncio.set_event_loop(loop)
            ready.set()
            loop.run_forever()

        t = threading.Thread(target=runner, name=f"mcp-{self.interface_type}-loop", daemon=True)
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

        self._launch_ready.clear()
        self._launch_error = None

        async def _connection_main():
            url = self.mcp_server_url
            self._close_event = asyncio.Event()

            try:
                if url and (url.startswith("http://") or url.startswith("https://")):
                    if "/sse" in url or self.mcp_transport == "sse":
                        logger.info(f"MCP connect (SSE): {url}")
                        self._transport_cm = sse_client(url)
                    else:
                        logger.info(f"MCP connect (HTTP): {url}")
                        if streamablehttp_client is None:
                            raise DeviceConnectionError("streamable_http_client not available")
                        self._transport_cm = streamablehttp_client(url)

                    streams = await self._transport_cm.__aenter__()
                    read_stream, write_stream = streams[0], streams[1]
                else:
                    cmd = self.mcp_stdio_command or ["npx", "-y", "@playwright/mcp@latest", "--headless"]
                    logger.info(f"MCP connect (stdio): {' '.join(cmd)}")
                    executable = shutil.which(cmd[0]) or cmd[0]
                    params = StdioServerParameters(command=executable, args=cmd[1:], env=self.mcp_env)
                    self._transport_cm = stdio_client(params)
                    streams = await self._transport_cm.__aenter__()
                    read_stream, write_stream = streams[0], streams[1]

                self._session_cm = ClientSession(read_stream, write_stream)
                self._session = await self._session_cm.__aenter__()
                init_result = await self._session.initialize()
                logger.info(f"MCP initialize ok: server={init_result.serverInfo.name} v{init_result.serverInfo.version}")
                self._launch_ready.set()

                await self._close_event.wait()
            except Exception as e:
                self._launch_error = e
                self._launch_ready.set()
                raise
            finally:
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
                self._close_event = None

        def _start_connection_task():
            assert self._loop is not None
            self._connection_task = self._loop.create_task(_connection_main())

        try:
            assert self._loop is not None
            self._loop.call_soon_threadsafe(_start_connection_task)
            if not self._launch_ready.wait(timeout=120):
                raise DeviceConnectionError("MCP launch timed out")
            if self._launch_error is not None:
                raise self._launch_error
        except Exception as e:
            logger.error(f"MCP launch failed: {e}")
            raise DeviceConnectionError(f"MCP launch failed: {e}") from e

    def close(self) -> None:
        async def _close():
            if self._close_event is not None:
                self._close_event.set()
            if self._connection_task is not None:
                await self._connection_task

        try:
            if self._loop and self._thread and self._thread.is_alive():
                self._submit(_close(), timeout=30)
        finally:
            self._connection_task = None
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=5)
            self._loop = None
            self._thread = None

    async def _call_mcp(self, tool_name: str, arguments: Dict[str, Any]):
        if self._session is None:
            raise DeviceError("MCP session not initialized")
        return await self._session.call_tool(tool_name, arguments=arguments)

    # ==================== Generic Action Execution ====================

    def _execute_mcp_action(self, action_name: str, **kwargs) -> Any:
        """
        Generic execution logic: looks up action in tool map and calls MCP server.
        """
        if action_name not in self._tool_map:
            raise NotImplementedError(f"Action '{action_name}' not supported by {self.__class__.__name__}")
        
        config = self._tool_map[action_name]
        tool_name = config["tool"]
        mapper = config.get("mapper")
        
        # Transform arguments if a mapper is provided
        args = mapper(**kwargs) if mapper else kwargs
        
        try:
            result = self._submit(self._call_mcp(tool_name, args))
            error_text = self._parse_tool_error(result)
            if error_text:
                raise DeviceError(error_text)
            return result
        except Exception as e:
            raise ActionExecutionError(f"MCP action '{action_name}' (tool: {tool_name}) failed: {e}") from e

    @staticmethod
    def _parse_text(result) -> str:
        if not result or not getattr(result, "content", None): return ""
        for part in result.content:
            if getattr(part, "type", "") == "text": return part.text
            if hasattr(part, "text"): return part.text
        return ""

    @staticmethod
    def _parse_image_b64(result) -> Optional[str]:
        if not result or not getattr(result, "content", None): return None
        for part in result.content:
            if getattr(part, "type", "") == "image" or getattr(part, "data", None):
                return getattr(part, "data", None) or getattr(part, "text", None)
        return None

    @classmethod
    def _parse_tool_error(cls, result) -> Optional[str]:
        text = cls._parse_text(result).strip()
        if not text:
            return None
        if text.startswith("ERROR:"):
            return text
        return None

    @staticmethod
    def _selector_ref(selector: Optional[str], **kwargs) -> Dict[str, Any]:
        ref = kwargs.get("selector_ref")
        if isinstance(ref, dict):
            normalized_ref = dict(ref)
        else:
            normalized_ref = {
                "ref_kind": "selector",
                "source": "device_call",
                "selector_value": selector,
                "selector_type": kwargs.get("selector_type"),
                "actionable": bool(selector),
                "persistable": True,
                "requires_resolution": False,
                "resolved": False,
                "extra": {},
            }
        normalized_ref.setdefault("ref_kind", "selector")
        normalized_ref.setdefault("source", "device_call")
        normalized_ref.setdefault("selector_value", selector)
        normalized_ref.setdefault("selector_type", kwargs.get("selector_type"))
        normalized_ref.setdefault("actionable", bool(normalized_ref.get("selector_value")))
        normalized_ref.setdefault("persistable", True)
        normalized_ref.setdefault("requires_resolution", False)
        normalized_ref.setdefault("resolved", False)
        normalized_ref.setdefault("extra", {})
        return normalized_ref

    def resolve_selector_ref(
        self,
        selector: Optional[str] = None,
        *,
        action_type: str = "tap",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        ref = self._selector_ref(selector, **kwargs)
        if not ref.get("selector_value"):
            return None
        return ref

    @staticmethod
    def _selector_value(selector: Optional[str], resolved_ref: Optional[Dict[str, Any]]) -> Optional[str]:
        if resolved_ref and resolved_ref.get("selector_value"):
            return resolved_ref.get("selector_value")
        return selector

    # ==================== BaseDevice Implementation (Unified) ====================

    def goto(self, url: str, **kwargs) -> None:
        self._execute_mcp_action("goto", url=url, **kwargs)
        self.current_url = url

    def get_page_content(self) -> str:
        result = self._execute_mcp_action("get_page_content")
        return self._parse_text(result)

    def get_dom_tree(self) -> Dict[str, Any]:
        result = self._execute_mcp_action("get_dom_tree")
        return {"content": self._parse_text(result)}

    def screenshot(self, save_path: Optional[Path] = None, full_page: bool = True) -> bytes:
        result = self._execute_mcp_action("screenshot", full_page=full_page)
        error_text = self._parse_tool_error(result)
        if error_text:
            raise DeviceError(error_text)
        image_b64 = self._parse_image_b64(result)
        if image_b64:
            b64 = image_b64.strip()
        else:
            b64 = self._parse_text(result).strip()
        if not b64:
            raise DeviceError("Screenshot tool returned empty data")
        if b64.startswith("ERROR:"):
            raise DeviceError(b64)
        try:
            # Pad base64 if needed
            padded = b64 + "=" * (4 - len(b64) % 4) if len(b64) % 4 else b64
            img = base64.b64decode(padded, validate=True)
            if save_path and img:
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(img)
            return img
        except Exception as e:
            raise DeviceError(f"Failed to decode screenshot: {e} (data preview: {b64[:50]})") from e

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        self._execute_mcp_action("click", selector=selector, position=position, **kwargs)

    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None:
        self._execute_mcp_action("input", text=text, selector=selector, position=position, clear_before=clear_before, **kwargs)

    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None:
        self._execute_mcp_action("scroll", direction=direction, distance=distance, **kwargs)

    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool:
        try:
            self._execute_mcp_action("wait_for_selector", selector=selector, timeout=timeout, **kwargs)
            return True
        except Exception:
            return False

    def evaluate_script(self, script: str, *args) -> Any:
        result = self._execute_mcp_action("evaluate", script=script, args=args)
        txt = self._parse_text(result).strip()
        try:
            return json.loads(txt)
        except Exception:
            pass

        result_section_match = re.search(
            r"###\s*Result\s*([\s\S]*?)(?:\n###\s|\Z)",
            txt,
            re.IGNORECASE,
        )
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt, re.IGNORECASE)
        candidates = []
        if result_section_match:
            candidates.append(result_section_match.group(1).strip())
        if fenced_match:
            candidates.append(fenced_match.group(1).strip())

        bracket_match = re.search(r"(\{[\s\S]*?\}|\[[\s\S]*?\])", txt)
        if bracket_match:
            candidates.append(bracket_match.group(1).strip())

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception:
                continue

        return txt

    def keyboard_press(self, key_name: str, **kwargs) -> None:
        self._execute_mcp_action("keyboard_press", key=key_name, **kwargs)

    # ==================== AI Action Methods (Unified) ====================

    def ai_click(self, prompt: str, **kwargs) -> None:
        """使用服务器端 AI 能力点击元素"""
        self._execute_mcp_action("ai_click", prompt=prompt, **kwargs)

    def ai_input(self, prompt: str, text: str, **kwargs) -> None:
        """使用服务器端 AI 能力输入文本"""
        self._execute_mcp_action("ai_input", prompt=prompt, text=text, **kwargs)

    def ai_extract(self, prompt: str, **kwargs) -> Any:
        """使用服务器端 AI 能力提取信息"""
        result = self._execute_mcp_action("ai_extract", prompt=prompt, **kwargs)
        return self._parse_text(result)

    def ai_assert(self, prompt: str, **kwargs) -> None:
        """使用服务器端 AI 能力进行断言"""
        self._execute_mcp_action("ai_assert", prompt=prompt, **kwargs)

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ==================== Concrete Device Implementations ====================

class McpPlaywrightDevice(BaseMcpDevice):
    """
    Official @playwright/mcp mapping.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "playwright")
        super().__init__(**kwargs)
        
        # Tool Mapping for Playwright
        self._tool_map = {
            "goto": {"tool": "browser_navigate"},
            "get_page_content": {"tool": "browser_evaluate", "mapper": lambda **k: {"function": "() => document.documentElement.outerHTML"}},
            "get_dom_tree": {"tool": "browser_snapshot"},
            "screenshot": {"tool": "browser_take_screenshot", "mapper": lambda **k: {"type": "png", "fullPage": k.get("full_page", True)}},
            "click": {"tool": "browser_click", "mapper": lambda **k: {"element": k.get("selector"), "target": k.get("selector")}},
            "input": {"tool": "browser_type", "mapper": lambda **k: {"element": k.get("selector"), "text": k.get("text")}},
            "scroll": {"tool": "browser_evaluate", "mapper": self._pw_scroll_mapper},
            "evaluate": {"tool": "browser_evaluate", "mapper": lambda **k: {"function": k.get("script")}},
            "keyboard_press": {"tool": "browser_press_key"},
            # AI Actions (assuming @playwright/mcp or our server supports them)
            "ai_click": {"tool": "playwright_ai_click"},
            "ai_input": {"tool": "playwright_ai_input"},
            "ai_extract": {"tool": "playwright_ai_extract"},
            "ai_assert": {"tool": "playwright_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "browser"

    def size(self) -> Tuple[int, int]:
        try:
            viewport = self.evaluate_script(
                """
() => ({
  width: window.innerWidth || document.documentElement.clientWidth || 0,
  height: window.innerHeight || document.documentElement.clientHeight || 0
})
""".strip()
            )
            if isinstance(viewport, dict):
                width = int(round(float(viewport.get("width") or 0)))
                height = int(round(float(viewport.get("height") or 0)))
                if width > 0 and height > 0:
                    return (width, height)
        except Exception:
            pass
        return super().size()

    def _pw_scroll_mapper(self, **k):
        dist = k.get("distance") or self.viewport_height * 0.8
        direction = k.get("direction", "down")
        sign = {"down": ("0", str(dist)), "up": ("0", str(-dist))}.get(direction, ("0", str(dist)))
        return {"function": f"() => window.scrollBy({sign[0]}, {sign[1]})"}

    @staticmethod
    def _normalize_playwright_selector(selector: Optional[str], **kwargs) -> Dict[str, Any]:
        ref = BaseMcpDevice._selector_ref(selector, **kwargs)
        selector_type = ref.get("selector_type") or ""
        selector_value = ref.get("selector_value") or selector
        extra = ref.get("extra") or {}

        if not selector_value:
            return {}
        if selector_type == "playwright-ref":
            return {"element": selector_value, "ref": selector_value}
        if selector_type == "role" and extra.get("role") and extra.get("name"):
            return {"target": f'{extra["role"]}="{extra["name"]}"'}
        return {"target": selector_value}

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        resolved_selector = self._selector_value(selector, resolved_ref)
        if resolved_selector:
            normalize_kwargs = dict(kwargs)
            normalize_kwargs.pop("selector_ref", None)
            args = self._normalize_playwright_selector(
                resolved_selector,
                selector_ref=resolved_ref,
                **normalize_kwargs,
            )
            self._submit(self._call_mcp("browser_click", args))
            return
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        resolved_selector = self._selector_value(selector, resolved_ref)
        if resolved_selector:
            normalize_kwargs = dict(kwargs)
            normalize_kwargs.pop("selector_ref", None)
            args = self._normalize_playwright_selector(
                resolved_selector,
                selector_ref=resolved_ref,
                **normalize_kwargs,
            )
            args["text"] = text
            self._submit(self._call_mcp("browser_type", args))
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)

    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)


class McpWinAppDevice(BaseMcpDevice):
    """
    WinAppDriver MCP mapping.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "winapp")
        super().__init__(**kwargs)
        
        # Tool Mapping for WinAppDriver
        self._tool_map = {
            "create_session": {"tool": "winapp_create_session"},
            "delete_session": {"tool": "winapp_delete_session"},
            "get_status": {"tool": "winapp_get_status"},
            "get_page_content": {"tool": "winapp_get_source"},
            "get_dom_tree": {"tool": "winapp_get_source"},
            "screenshot": {"tool": "winapp_screenshot"},
            "click": {"tool": "winapp_click", "mapper": lambda **k: {"x": int(k.get("position", (0, 0))[0]), "y": int(k.get("position", (0, 0))[1])}},
            "input": {"tool": "winapp_send_keys", "mapper": lambda **k: {"selector": k.get("selector"), "keys": k.get("text")}},
            "keyboard_press": {"tool": "winapp_press_keys", "mapper": lambda **k: {"keys": k.get("key")}},
            "clear": {"tool": "winapp_clear_element"},
            # AI Actions
            "ai_click": {"tool": "winapp_ai_click"},
            "ai_input": {"tool": "winapp_ai_input"},
            "ai_extract": {"tool": "winapp_ai_extract"},
            "ai_assert": {"tool": "winapp_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "windows"

    @staticmethod
    def _winapp_element_args(selector_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ref = selector_ref or {}
        selector_value = ref.get("selector_value")
        if not selector_value:
            return {}
        selector_type = (ref.get("selector_type") or "accessibility id").strip()
        if ref.get("ref_kind") == "handle" or selector_type.lower() == "element_id" or ref.get("resolved"):
            return {"element_id": selector_value}
        return {"selector": selector_value, "using": selector_type}

    def resolve_selector_ref(
        self,
        selector: Optional[str] = None,
        *,
        action_type: str = "tap",
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        ref = super().resolve_selector_ref(selector, action_type=action_type, **kwargs)
        if not ref:
            return None

        selector_value = ref.get("selector_value")
        selector_type = (ref.get("selector_type") or "accessibility id").strip()
        if not selector_value:
            return None
        if ref.get("resolved") and (ref.get("ref_kind") == "handle" or selector_type.lower() == "element_id"):
            return ref
        if not ref.get("requires_resolution", False):
            return ref

        try:
            result = self._submit(
                self._call_mcp(
                    "winapp_find_element",
                    {"selector": selector_value, "using": selector_type},
                )
            )
            element_id = self._parse_text(result).strip()
            if not element_id:
                return ref
            return {
                "platform": ref.get("platform", "windows"),
                "ref_kind": "handle",
                "source": "remote_resolved",
                "selector_type": "element_id",
                "selector_value": element_id,
                "actionable": True,
                "persistable": False,
                "requires_resolution": False,
                "resolved": True,
                "extra": {
                    "resolved_from": {
                        "selector_type": selector_type,
                        "selector_value": selector_value,
                    },
                    **dict(ref.get("extra") or {}),
                },
            }
        except Exception as e:
            logger.debug(
                f"WinApp resolve selector ref failed, keep selector ref: selector={selector_value}, using={selector_type}, error={e}"
            )
            return ref

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        action_args = self._winapp_element_args(resolved_ref)
        if action_args:
            try:
                self._submit(
                    self._call_mcp(
                        "winapp_click_element",
                        action_args,
                    )
                )
                return
            except Exception as e:
                logger.debug(
                    f"WinApp element click failed, fallback to coordinate click: ref={resolved_ref}, error={e}"
                )
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        action_args = self._winapp_element_args(resolved_ref)
        if action_args:
            try:
                if clear_before:
                    self._submit(
                        self._call_mcp(
                            "winapp_clear_element",
                            action_args,
                        )
                    )
                self._submit(
                    self._call_mcp(
                        "winapp_send_keys_to_element",
                        {**action_args, "text": text},
                    )
                )
                return
            except Exception as e:
                logger.debug(
                    f"WinApp element input failed, fallback to generic input: ref={resolved_ref}, error={e}"
                )
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)


class McpHypiumDevice(BaseMcpDevice):
    """
    Hypium (OpenHarmony) MCP mapping.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "hypium")
        super().__init__(**kwargs)
        
        self._tool_map = {
            # Native tree/source placeholders. The remote MCP server should
            # return XML/JSON page structure via `hypium_get_source`.
            "get_page_content": {"tool": "hypium_get_source"},
            "get_dom_tree": {"tool": "hypium_get_source"},
            "screenshot": {"tool": "hypium_screenshot"},
            "click": {"tool": "hypium_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "hypium_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            # AI Actions
            "ai_click": {"tool": "hypium_ai_click"},
            "ai_input": {"tool": "hypium_ai_input"},
            "ai_extract": {"tool": "hypium_ai_extract"},
            "ai_assert": {"tool": "hypium_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "hypium"

    @staticmethod
    def _normalize_mobile_selector(selector: Optional[str], **kwargs) -> Optional[str]:
        ref = BaseMcpDevice._selector_ref(selector, **kwargs)
        selector_value = ref.get("selector_value") or selector
        selector_type = (ref.get("selector_type") or "").strip().lower()
        if not selector_value:
            return None
        if selector_type in {"xpath", "predicate", "css", "text", "name", "label", "identifier", "resource-id", "accessibility-id"}:
            return selector_value
        return selector_value

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        normalized_selector = self._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("click", selector=normalized_selector, **kwargs)
            return
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        normalized_selector = self._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("input", text=text, selector=normalized_selector, clear_before=clear_before, **kwargs)
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)


class McpAndroidDevice(BaseMcpDevice):
    """
    Android MCP mapping.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "android")
        super().__init__(**kwargs)
        
        self._tool_map = {
            # Native tree/source placeholders. The remote MCP server should
            # return XML/JSON page structure via `android_get_source`.
            "get_page_content": {"tool": "android_get_source"},
            "get_dom_tree": {"tool": "android_get_source"},
            "screenshot": {"tool": "android_screenshot"},
            "click": {"tool": "android_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "android_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            # AI Actions
            "ai_click": {"tool": "android_ai_click"},
            "ai_input": {"tool": "android_ai_input"},
            "ai_extract": {"tool": "android_ai_extract"},
            "ai_assert": {"tool": "android_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "android"

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("click", selector=normalized_selector, **kwargs)
            return
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("input", text=text, selector=normalized_selector, clear_before=clear_before, **kwargs)
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)


class McpIosDevice(BaseMcpDevice):
    """
    iOS MCP mapping.
    """
    def __init__(self, **kwargs):
        kwargs.setdefault("mcp_name", "ios")
        super().__init__(**kwargs)
        
        self._tool_map = {
            # Native tree/source placeholders. The remote MCP server should
            # return XML/JSON page structure via `ios_get_source`.
            "get_page_content": {"tool": "ios_get_source"},
            "get_dom_tree": {"tool": "ios_get_source"},
            "screenshot": {"tool": "ios_screenshot"},
            "click": {"tool": "ios_click", "mapper": lambda **k: {"selector": k.get("selector")}},
            "input": {"tool": "ios_input", "mapper": lambda **k: {"text": k.get("text"), "selector": k.get("selector")}},
            # AI Actions
            "ai_click": {"tool": "ios_ai_click"},
            "ai_input": {"tool": "ios_ai_input"},
            "ai_extract": {"tool": "ios_ai_extract"},
            "ai_assert": {"tool": "ios_ai_assert"},
        }

    @property
    def interface_type(self) -> str: return "ios"

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="tap", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("click", selector=normalized_selector, **kwargs)
            return
        super().click(selector=selector, position=position, **kwargs)

    def input(
        self,
        text: str,
        selector: Optional[str] = None,
        position: Optional[Tuple[float, float]] = None,
        clear_before: bool = True,
        **kwargs,
    ) -> None:
        resolved_ref = self.resolve_selector_ref(selector, action_type="input", **kwargs)
        normalized_selector = McpHypiumDevice._normalize_mobile_selector(
            self._selector_value(selector, resolved_ref),
            selector_ref=resolved_ref,
            **kwargs,
        )
        if normalized_selector:
            self._execute_mcp_action("input", text=text, selector=normalized_selector, clear_before=clear_before, **kwargs)
            return
        super().input(text, selector=selector, position=position, clear_before=clear_before, **kwargs)
    
    def action_space(self) -> List[Any]:
        from core.agent.action_space import WEB_ACTION_SPACE
        return list(WEB_ACTION_SPACE)
