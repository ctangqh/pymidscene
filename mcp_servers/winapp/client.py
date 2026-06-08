"""WinAppDriver HTTP API 客户端封装"""
import json
import base64
import os
import sys
import subprocess
import time
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

# 确保打包后能正确导入同目录模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import httpx
from loguru import logger

from config import winapp_settings


class WinAppDriverClient:
    """WinAppDriver HTTP API 客户端"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        auto_start: bool = True,
    ):
        self.host = host or winapp_settings.WINAPPDRIVER_HOST
        self.port = port or winapp_settings.WINAPPDRIVER_PORT
        self.base_url = f"http://{self.host}:{self.port}"
        self.auto_start = auto_start

        self.session_id: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=float(winapp_settings.WINAPPDRIVER_HTTP_TIMEOUT))
        return self._client

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        session: bool = True,
    ) -> Dict[str, Any]:
        """发送请求到 WinAppDriver"""
        url = self.base_url + path
        if session and self.session_id:
            url = url.replace(":sessionId", self.session_id)

        headers = {"Content-Type": "application/json"}
        json_data = json.dumps(data) if data else None

        try:
            response = self._get_client().request(
                method=method,
                url=url,
                content=json_data,
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()
            if result.get("status") != 0:
                raise RuntimeError(f"WinAppDriver error: {result.get('value', {}).get('message', 'Unknown error')}")
            return result.get("value", {})
        except httpx.HTTPError as e:
            raise RuntimeError(f"HTTP request failed: {e}") from e

    def start_winappdriver(self) -> bool:
        """启动 WinAppDriver 进程"""
        # 常见的 WinAppDriver 路径
        possible_paths = [
            r"C:\Program Files (x86)\Windows Application Driver\WinAppDriver.exe",
            r"C:\Program Files\Windows Application Driver\WinAppDriver.exe",
            "WinAppDriver.exe",  # PATH 中
        ]

        for path in possible_paths:
            if Path(path).exists() or (path == "WinAppDriver.exe"):
                try:
                    self._process = subprocess.Popen(
                        [path, self.host, str(self.port)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    time.sleep(2)  # 等待服务启动
                    logger.info(f"WinAppDriver started: {path}")
                    return True
                except Exception as e:
                    logger.warning(f"Failed to start WinAppDriver from {path}: {e}")
                    continue

        raise RuntimeError(
            "WinAppDriver not found. Please install from: "
            "https://github.com/microsoft/WinAppDriver/releases"
        )

    def stop_winappdriver(self) -> None:
        """停止 WinAppDriver 进程"""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
            logger.info("WinAppDriver stopped")

    # ==================== Session 管理 ====================

    def create_session(
        self,
        app: str,
        app_args: Optional[str] = None,
        platform_name: str = "Windows",
        device_name: str = "WindowsPC",
    ) -> str:
        """创建新 session"""
        if self.auto_start and not self._process:
            self.start_winappdriver()

        capabilities = {
            "platformName": platform_name,
            "deviceName": device_name,
            "app": app,
        }
        if app_args:
            capabilities["appArguments"] = app_args

        data = {"desiredCapabilities": capabilities}
        result = self._request("POST", "/session", data, session=False)

        # 从响应头或 body 中获取 session id
        if "sessionId" in result:
            self.session_id = result["sessionId"]
        else:
            # 尝试从响应中解析
            self.session_id = result.get("sessionId", "")

        logger.info(f"Session created: {self.session_id}")
        return self.session_id

    def delete_session(self) -> None:
        """删除 session"""
        if self.session_id:
            self._request("DELETE", "/session/:sessionId")
            logger.info(f"Session deleted: {self.session_id}")
            self.session_id = None

    def get_sessions(self) -> List[Dict[str, Any]]:
        """获取所有活跃 sessions"""
        return self._request("GET", "/sessions", session=False)

    def get_status(self) -> Dict[str, Any]:
        """获取 WinAppDriver 状态"""
        return self._request("GET", "/status", session=False)

    # ==================== 元素定位 ====================

    def find_element(self, using: str, value: str) -> str:
        """查找单个元素

        Args:
            using: 定位策略 (id, name, class name, xpath, accessibility id)
            value: 定位值
        Returns:
            元素 ID
        """
        data = {"using": using, "value": value}
        result = self._request("POST", "/session/:sessionId/element", data)
        element_id = result.get("ELEMENT") or result.get("element-6066-11e4-a52e-4f735466cecf")
        return element_id

    def find_elements(self, using: str, value: str) -> List[str]:
        """查找多个元素"""
        data = {"using": using, "value": value}
        result = self._request("POST", "/session/:sessionId/elements", data)
        element_ids = []
        for item in result:
            eid = item.get("ELEMENT") or item.get("element-6066-11e4-a52e-4f735466cecf")
            if eid:
                element_ids.append(eid)
        return element_ids

    def find_element_from_element(self, parent_id: str, using: str, value: str) -> str:
        """从父元素内查找单个元素"""
        data = {"using": using, "value": value}
        result = self._request(
            "POST", f"/session/:sessionId/element/{parent_id}/element", data
        )
        element_id = result.get("ELEMENT") or result.get("element-6066-11e4-a52e-4f735466cecf")
        return element_id

    # ==================== 元素操作 ====================

    def click_element(self, element_id: str) -> None:
        """点击元素"""
        self._request("POST", f"/session/:sessionId/element/{element_id}/click")

    def clear_element(self, element_id: str) -> None:
        """清空元素内容"""
        self._request("POST", f"/session/:sessionId/element/{element_id}/clear")

    def send_keys_to_element(self, element_id: str, text: str) -> None:
        """向元素发送文本"""
        data = {"value": list(text)}
        self._request("POST", f"/session/:sessionId/element/{element_id}/value", data)

    def get_element_text(self, element_id: str) -> str:
        """获取元素文本"""
        return self._request("GET", f"/session/:sessionId/element/{element_id}/text")

    def get_element_attribute(self, element_id: str, name: str) -> str:
        """获取元素属性"""
        return self._request(
            "GET", f"/session/:sessionId/element/{element_id}/attribute/{name}"
        )

    def get_element_name(self, element_id: str) -> str:
        """获取元素标签名"""
        return self._request("GET", f"/session/:sessionId/element/{element_id}/name")

    def is_element_displayed(self, element_id: str) -> bool:
        """检查元素是否可见"""
        return self._request(
            "GET", f"/session/:sessionId/element/{element_id}/displayed"
        )

    def is_element_enabled(self, element_id: str) -> bool:
        """检查元素是否可用"""
        return self._request("GET", f"/session/:sessionId/element/{element_id}/enabled")

    def is_element_selected(self, element_id: str) -> bool:
        """检查元素是否选中"""
        return self._request(
            "GET", f"/session/:sessionId/element/{element_id}/selected"
        )

    def get_element_location(self, element_id: str) -> Dict[str, int]:
        """获取元素位置"""
        return self._request(
            "GET", f"/session/:sessionId/element/{element_id}/location"
        )

    def get_element_size(self, element_id: str) -> Dict[str, int]:
        """获取元素大小"""
        return self._request("GET", f"/session/:sessionId/element/{element_id}/size")

    # ==================== 键盘操作 ====================

    def send_keys(self, text: str) -> None:
        """向当前焦点发送按键"""
        data = {"value": list(text)}
        self._request("POST", "/session/:sessionId/keys", data)

    # ==================== 鼠标操作 ====================

    def mouse_move(self, x: int, y: int) -> None:
        """移动鼠标到坐标"""
        data = {"xoffset": x, "yoffset": y}
        self._request("POST", "/session/:sessionId/moveto", data)

    def mouse_click(self, button: str = "left") -> None:
        """鼠标点击"""
        button_map = {"left": 0, "middle": 1, "right": 2}
        data = {"button": button_map.get(button, 0)}
        self._request("POST", "/session/:sessionId/click", data)

    def mouse_double_click(self) -> None:
        """鼠标双击"""
        self._request("POST", "/session/:sessionId/doubleclick")

    def mouse_button_down(self, button: str = "left") -> None:
        """按下鼠标键"""
        button_map = {"left": 0, "middle": 1, "right": 2}
        data = {"button": button_map.get(button, 0)}
        self._request("POST", "/session/:sessionId/buttondown", data)

    def mouse_button_up(self, button: str = "left") -> None:
        """释放鼠标键"""
        button_map = {"left": 0, "middle": 1, "right": 2}
        data = {"button": button_map.get(button, 0)}
        self._request("POST", "/session/:sessionId/buttonup", data)

    # ==================== 窗口操作 ====================

    def get_window_handle(self) -> str:
        """获取当前窗口句柄"""
        return self._request("GET", "/session/:sessionId/window_handle")

    def get_window_handles(self) -> List[str]:
        """获取所有窗口句柄"""
        return self._request("GET", "/session/:sessionId/window_handles")

    def set_window_size(self, width: int, height: int) -> None:
        """设置窗口大小"""
        data = {"width": width, "height": height}
        self._request("POST", "/session/:sessionId/window/size", data)

    def get_window_size(self) -> Dict[str, int]:
        """获取窗口大小"""
        return self._request("GET", "/session/:sessionId/window/size")

    def set_window_position(self, x: int, y: int) -> None:
        """设置窗口位置"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/window/position", data)

    def get_window_position(self) -> Dict[str, int]:
        """获取窗口位置"""
        return self._request("GET", "/session/:sessionId/window/position")

    def maximize_window(self) -> None:
        """最大化窗口"""
        self._request("POST", "/session/:sessionId/window/maximize")

    def close_window(self) -> None:
        """关闭当前窗口"""
        self._request("DELETE", "/session/:sessionId/window")

    # ==================== 截图 & 源码 ====================

    def get_screenshot(self) -> bytes:
        """获取截图（返回 bytes）"""
        b64_data = self._request("GET", "/session/:sessionId/screenshot")
        return base64.b64decode(b64_data)

    def get_element_screenshot(self, element_id: str) -> bytes:
        """获取元素截图"""
        b64_data = self._request(
            "GET", f"/session/:sessionId/element/{element_id}/screenshot"
        )
        return base64.b64decode(b64_data)

    def get_page_source(self) -> str:
        """获取页面源码（XML）"""
        return self._request("GET", "/session/:sessionId/source")

    # ==================== 超时设置 ====================

    def set_timeout(self, timeout_type: str, ms: int) -> None:
        """设置超时

        Args:
            timeout_type: 'implicit', 'script', 'command'
            ms: 毫秒数
        """
        data = {"type": timeout_type, "ms": ms}
        self._request("POST", "/session/:sessionId/timeouts", data)

    # ==================== 导航 ====================

    def navigate_back(self) -> None:
        """后退"""
        self._request("POST", "/session/:sessionId/back")

    def navigate_forward(self) -> None:
        """前进"""
        self._request("POST", "/session/:sessionId/forward")

    # ==================== Touch 操作（触屏） ====================

    def touch_click(self, x: int, y: int) -> None:
        """触摸点击"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/click", data)

    def touch_double_click(self, x: int, y: int) -> None:
        """触摸双击"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/doubleclick", data)

    def touch_long_click(self, x: int, y: int) -> None:
        """触摸长按"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/longclick", data)

    def touch_down(self, x: int, y: int) -> None:
        """按下触摸"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/down", data)

    def touch_up(self, x: int, y: int) -> None:
        """释放触摸"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/up", data)

    def touch_move(self, x: int, y: int) -> None:
        """移动触摸"""
        data = {"x": x, "y": y}
        self._request("POST", "/session/:sessionId/touch/move", data)

    def touch_scroll(self, x: int, y: int, xoffset: int, yoffset: int) -> None:
        """触摸滚动"""
        data = {"x": x, "y": y, "xoffset": xoffset, "yoffset": yoffset}
        self._request("POST", "/session/:sessionId/touch/scroll", data)

    def touch_flick(self, xspeed: int, yspeed: int) -> None:
        """触摸滑动"""
        data = {"xspeed": xspeed, "yspeed": yspeed}
        self._request("POST", "/session/:sessionId/touch/flick", data)

    def close(self) -> None:
        """关闭客户端"""
        if self.session_id:
            try:
                self.delete_session()
            except Exception:
                pass
        if self._client:
            self._client.close()
            self._client = None
        self.stop_winappdriver()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
