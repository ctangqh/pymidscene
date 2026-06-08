"""
MCP 连接池 - 会话封装

封装单个 MCP 会话的生命周期管理
"""
import asyncio
import threading
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime
import uuid
import logging

from .types import SessionStatus, SessionStats
from .exceptions import SessionBusyError, SessionInvalidError


logger = logging.getLogger(__name__)


class MCPSession:
    """
    封装单个 MCP 会话

    负责：
    - 会话状态管理（IDLE/BUSY/ERROR/EXPIRED）
    - 工具调用转发
    - 错误计数与健康检查
    - 使用统计
    """

    def __init__(
        self,
        mcp_client: Any,
        device_type: str,
        config: Dict[str, Any],
        session_id: Optional[str] = None,
    ):
        self.session_id = session_id or f"mcp-{uuid.uuid4().hex[:12]}"
        self.mcp_client = mcp_client  # 实际的 MCP 客户端 (ClientSession 或自定义)
        self.device_type = device_type
        self.config = config

        # 状态
        self.status = SessionStatus.IDLE
        self._status_lock = threading.RLock()

        # 生命周期
        self.created_at = datetime.now()
        self.last_used_at = datetime.now()
        self.max_idle_time = config.get("max_idle_time", 300)
        self.max_session_age = config.get("max_session_age", 3600)
        self.max_errors = config.get("max_errors", 5)

        # 统计
        self.usage_count = 0
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.last_action: Optional[str] = None

        # 异步锁（用于 MCP 调用）
        self._call_lock = threading.Lock()

        # 会话级别的数据存储
        self.context: Dict[str, Any] = {}

        logger.info(f"MCP 会话创建: {self.session_id} ({device_type})")

    # ==================== 状态管理 ====================

    def mark_idle(self) -> None:
        """标记为空闲"""
        with self._status_lock:
            if self.status == SessionStatus.ERROR:
                logger.warning(f"尝试将错误状态的会话标记为空闲: {self.session_id}")
                return
            self.status = SessionStatus.IDLE
            logger.debug(f"会话 {self.session_id} 已标记为空闲")

    def mark_busy(self) -> None:
        """标记为占用"""
        with self._status_lock:
            if self.status == SessionStatus.BUSY:
                raise SessionBusyError(self.session_id)
            if self.status == SessionStatus.ERROR:
                raise SessionInvalidError(self.session_id, "会话处于错误状态")
            self.status = SessionStatus.BUSY
            logger.debug(f"会话 {self.session_id} 已标记为占用")

    def mark_error(self, error: Exception) -> None:
        """标记为错误状态"""
        with self._status_lock:
            self.status = SessionStatus.ERROR
            self.error_count += 1
            self.last_error = str(error)
            logger.error(f"会话 {self.session_id} 进入错误状态: {error}")

    def is_idle(self) -> bool:
        """是否空闲"""
        with self._status_lock:
            return self.status == SessionStatus.IDLE

    def is_busy(self) -> bool:
        """是否占用"""
        with self._status_lock:
            return self.status == SessionStatus.BUSY

    # ==================== 健康检查 ====================

    def is_healthy(self) -> bool:
        """
        检查会话是否健康

        不健康的情况：
        - 状态为 ERROR
        - 错误数超过阈值
        - 会话已过期
        """
        with self._status_lock:
            if self.status == SessionStatus.ERROR:
                return False
            if self.error_count >= self.max_errors:
                return False
            if self._is_expired():
                return False
            return True

    def _is_expired(self) -> bool:
        """检查会话是否过期"""
        age = (datetime.now() - self.created_at).total_seconds()
        if age > self.max_session_age:
            logger.debug(f"会话 {self.session_id} 已过期 (age={age:.0f}s)")
            return True
        return False

    def need_cleanup(self) -> bool:
        """是否需要清理"""
        return not self.is_healthy() or self._is_expired()

    # ==================== 工具调用 ====================

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Any:
        """
        调用 MCP 工具（同步版本）

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            timeout: 超时时间（秒）

        Returns:
            工具返回结果

        Raises:
            SessionInvalidError: 会话无效时
            TimeoutError: 调用超时时
            Exception: 工具执行异常
        """
        if not self.is_healthy():
            raise SessionInvalidError(self.session_id, "会话不健康，无法调用工具")

        with self._call_lock:
            start_time = time.time()
            self.last_action = tool_name
            self.usage_count += 1

            try:
                logger.debug(f"会话 {self.session_id} 调用工具: {tool_name}")

                # 如果 mcp_client 有异步 call_tool 方法，用 asyncio 运行
                if hasattr(self.mcp_client, "call_tool"):
                    if asyncio.iscoroutinefunction(self.mcp_client.call_tool):
                        # 异步转同步
                        loop = asyncio.new_event_loop()
                        try:
                            result = loop.run_until_complete(
                                asyncio.wait_for(
                                    self.mcp_client.call_tool(tool_name, arguments),
                                    timeout=timeout or 30,
                                )
                            )
                        finally:
                            loop.close()
                    else:
                        # 同步调用
                        result = self.mcp_client.call_tool(tool_name, arguments)
                else:
                    # 自定义客户端接口
                    result = self.mcp_client.execute(tool_name, arguments)

                self.last_used_at = datetime.now()
                elapsed = (time.time() - start_time) * 1000
                logger.debug(f"工具 {tool_name} 执行完成: {elapsed:.1f}ms")
                return result

            except asyncio.TimeoutError:
                self.error_count += 1
                raise TimeoutError(f"工具调用超时: {tool_name}")
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                raise

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Any:
        """
        调用 MCP 工具（异步版本）

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            timeout: 超时时间（秒）

        Returns:
            工具返回结果
        """
        if not self.is_healthy():
            raise SessionInvalidError(self.session_id, "会话不健康，无法调用工具")

        async with asyncio.Lock():  # 简单的异步锁
            start_time = time.time()
            self.last_action = tool_name
            self.usage_count += 1

            try:
                logger.debug(f"会话 {self.session_id} 调用工具 (async): {tool_name}")

                if hasattr(self.mcp_client, "call_tool"):
                    result = await asyncio.wait_for(
                        self.mcp_client.call_tool(tool_name, arguments),
                        timeout=timeout or 30,
                    )
                else:
                    result = self.mcp_client.execute(tool_name, arguments)

                self.last_used_at = datetime.now()
                elapsed = (time.time() - start_time) * 1000
                logger.debug(f"工具 {tool_name} 执行完成: {elapsed:.1f}ms")
                return result

            except asyncio.TimeoutError:
                self.error_count += 1
                raise TimeoutError(f"工具调用超时: {tool_name}")
            except Exception as e:
                self.error_count += 1
                self.last_error = str(e)
                raise

    # ==================== 统计信息 ====================

    def get_stats(self) -> SessionStats:
        """获取会话统计信息"""
        with self._status_lock:
            return SessionStats(
                session_id=self.session_id,
                device_type=self.device_type,
                status=self.status,
                created_at=self.created_at.timestamp(),
                last_used_at=self.last_used_at.timestamp(),
                usage_count=self.usage_count,
                error_count=self.error_count,
                last_error=self.last_error,
            )

    # ==================== 生命周期 ====================

    def close(self) -> None:
        """关闭会话"""
        logger.info(f"关闭会话: {self.session_id}")
        try:
            if hasattr(self.mcp_client, "close"):
                if asyncio.iscoroutinefunction(self.mcp_client.close):
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(self.mcp_client.close())
                    finally:
                        loop.close()
                else:
                    self.mcp_client.close()
        except Exception as e:
            logger.warning(f"关闭 MCP 客户端时出错: {e}")

    def __enter__(self):
        self.mark_busy()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            self.mark_error(exc_val)
        else:
            self.mark_idle()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
