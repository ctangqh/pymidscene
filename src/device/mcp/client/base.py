"""
MCP Device Implementation - Unified architecture for multiple device types.
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
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    try:
        from mcp.client.streamable_http import streamable_http_client as streamablehttp_client
    except ImportError:
        streamablehttp_client = None

from ...base import BaseDevice
from common.config import settings
from common.logger import logger
from common.exceptions import (
    BrowserLaunchError as DeviceConnectionError,
    ActionExecutionError,
    BrowserError as DeviceError,
)


class BaseMcpDevice(BaseDevice):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

        self._tool_map: Dict[str, Dict[str, Any]] = {}

        self._session: Optional[ClientSession] = None
        self._session_cm = None
        self._transport_cm = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connection_task: Optional[asyncio.Task] = None
        self._close_event: Optional[asyncio.Event] = None
        self._launch_ready = threading.Event()
        self._launch_error: Optional[Exception] = None

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

    def _hook_before_launch(self) -> None:
        return

    def _hook_after_launch(self) -> None:
        return

    def _hook_before_close(self) -> None:
        return

    def _hook_after_close(self) -> None:
        return

    def launch(self) -> None:
        self._ensure_loop()
        self._hook_before_launch()

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
            self._hook_after_launch()
        except Exception as e:
            logger.error(f"MCP launch failed: {e}")
            raise DeviceConnectionError(f"MCP launch failed: {e}") from e

    def close(self) -> None:
        had_session = self._session is not None
        if had_session:
            self._hook_before_close()

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
            if had_session:
                self._hook_after_close()

    async def _call_mcp(self, tool_name: str, arguments: Dict[str, Any]):
        if self._session is None:
            raise DeviceError("MCP session not initialized")
        return await self._session.call_tool(tool_name, arguments=arguments)

    def _execute_mcp_action(self, action_name: str, **kwargs) -> Any:
        if action_name not in self._tool_map:
            raise NotImplementedError(f"Action '{action_name}' not supported by {self.__class__.__name__}")
        
        config = self._tool_map[action_name]
        tool_name = config["tool"]
        mapper = config.get("mapper")
        
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
        if not result or not getattr(result, "content", None):
            return ""
        for part in result.content:
            if getattr(part, "type", "") == "text":
                return part.text
            if hasattr(part, "text"):
                return part.text
        return ""

    @staticmethod
    def _parse_image_b64(result) -> Optional[str]:
        if not result or not getattr(result, "content", None):
            return None
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

    def ai_click(self, prompt: str, **kwargs) -> None:
        self._execute_mcp_action("ai_click", prompt=prompt, **kwargs)

    def ai_input(self, prompt: str, text: str, **kwargs) -> None:
        self._execute_mcp_action("ai_input", prompt=prompt, text=text, **kwargs)

    def ai_extract(self, prompt: str, **kwargs) -> Any:
        result = self._execute_mcp_action("ai_extract", prompt=prompt, **kwargs)
        return self._parse_text(result)

    def ai_assert(self, prompt: str, **kwargs) -> None:
        self._execute_mcp_action("ai_assert", prompt=prompt, **kwargs)

    def __enter__(self):
        self.launch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

