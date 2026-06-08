"""
MCP 连接池 - 核心实现

负责管理同类型的多个 MCP 会话，提供：
- 会话获取/归还
- 自动扩缩容
- 健康检查
- 负载均衡
- 统计监控
"""
import threading
import time
import logging
from typing import Optional, List, Dict, Any, Callable
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta

from .types import PoolConfig, PoolStats, SessionStatus
from .session import MCPSession
from .exceptions import (
    PoolClosedError,
    PoolTimeoutError,
    PoolFullError,
    SessionInvalidError,
)


logger = logging.getLogger(__name__)


class MCPConnectionPool:
    """
    MCP 连接池 - 管理同类型的多个 MCP 会话

    第一阶段特性：
    - 固定大小或自动扩缩容的会话池
    - FIFO + 健康检查优先的调度策略
    - 会话获取/归还超时处理
    - 自动清理不健康会话
    - 完整统计监控
    """

    def __init__(
        self,
        config: PoolConfig,
        session_factory: Callable[[], MCPSession],
    ):
        """
        初始化连接池

        Args:
            config: 连接池配置
            session_factory: 创建 MCP 会话的工厂函数
                           调用此函数应该返回一个可用的 MCPSession 实例
        """
        self.config = config
        self.session_factory = session_factory

        # 会话存储
        self._sessions: List[MCPSession] = []
        self._idle_queue: deque = deque()  # 空闲会话队列

        # 同步机制
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._closed = False

        # 统计
        self._stats = {
            "total_acquired": 0,
            "total_released": 0,
            "total_created": 0,
            "total_destroyed": 0,
            "wait_times_ms": [],
        }

        # 后台清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()

        logger.info(
            f"连接池初始化 [{config.device_type}]: "
            f"min={config.min_size}, max={config.max_size}, auto_scale={config.auto_scale}"
        )

    # ==================== 生命周期管理 ====================

    def initialize(self) -> None:
        """初始化连接池，创建最小数量的会话"""
        with self._lock:
            if self._closed:
                raise PoolClosedError(self.config.device_type)

            # 创建最小数量的会话
            for _ in range(self.config.min_size):
                try:
                    session = self._create_session()
                    self._idle_queue.append(session)
                except Exception as e:
                    logger.error(f"初始化会话失败: {e}")

            logger.info(
                f"连接池初始化完成 [{self.config.device_type}]: "
                f"已创建 {len(self._idle_queue)} 个会话"
            )

            # 启动后台清理线程
            self._start_cleanup_thread()

    def close(self, force: bool = False) -> None:
        """
        关闭连接池

        Args:
            force: 是否强制关闭（即使有会话正在使用）
        """
        with self._lock:
            if self._closed:
                return

            self._closed = True
            self._stop_cleanup.set()

            # 通知所有等待的线程
            self._condition.notify_all()

        # 等待清理线程结束
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)

        # 关闭所有会话
        sessions_to_close = list(self._sessions)
        for session in sessions_to_close:
            try:
                session.close()
                self._stats["total_destroyed"] += 1
            except Exception as e:
                logger.warning(f"关闭会话时出错: {e}")

        with self._lock:
            self._sessions.clear()
            self._idle_queue.clear()

        logger.info(f"连接池已关闭 [{self.config.device_type}]")

    # ==================== 核心 API ====================

    def acquire(self, timeout: Optional[float] = None) -> MCPSession:
        """
        获取一个可用会话

        Args:
            timeout: 超时时间（秒），None 表示使用配置中的值

        Returns:
            可用的 MCP 会话

        Raises:
            PoolTimeoutError: 超时仍未获取到会话
            PoolClosedError: 连接池已关闭
        """
        if timeout is None:
            timeout = self.config.acquire_timeout

        start_time = time.time()
        deadline = start_time + timeout

        with self._lock:
            while not self._closed:
                # 1. 优先从空闲队列中找健康的会话
                while self._idle_queue:
                    session = self._idle_queue.popleft()
                    if session.is_healthy():
                        session.mark_busy()
                        self._stats["total_acquired"] += 1
                        wait_ms = (time.time() - start_time) * 1000
                        self._stats["wait_times_ms"].append(wait_ms)
                        logger.debug(f"获取会话: {session.session_id}, 等待 {wait_ms:.1f}ms")
                        return session
                    else:
                        # 不健康，销毁它
                        self._destroy_session(session)

                # 2. 可以扩容则创建新会话
                if self.config.auto_scale and len(self._sessions) < self.config.max_size:
                    try:
                        session = self._create_session()
                        session.mark_busy()
                        self._stats["total_acquired"] += 1
                        logger.debug(f"扩容创建新会话: {session.session_id}")
                        return session
                    except Exception as e:
                        logger.warning(f"创建会话失败: {e}")

                # 3. 等待直到超时或有可用会话
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)

        if self._closed:
            raise PoolClosedError(self.config.device_type)

        raise PoolTimeoutError(
            self.config.device_type,
            timeout,
            f"当前状态: 总会话数={len(self._sessions)}, 空闲={len(self._idle_queue)}",
        )

    def release(self, session: MCPSession) -> None:
        """
        归还会话到连接池

        Args:
            session: 要归还的会话
        """
        with self._lock:
            if self._closed:
                # 连接池已关闭，直接销毁会话
                self._destroy_session(session)
                return

            if session not in self._sessions:
                logger.warning(f"归还未知会话: {session.session_id}")
                return

            # 检查会话是否健康
            if session.need_cleanup():
                logger.info(f"会话不健康，将销毁: {session.session_id}")
                self._destroy_session(session)
                self._condition.notify_all()
                return

            # 标记为空闲并加入队列
            session.mark_idle()
            self._idle_queue.append(session)
            self._stats["total_released"] += 1
            logger.debug(f"归还会话: {session.session_id}")

            # 通知等待的线程
            self._condition.notify_all()

    @contextmanager
    def session(self, timeout: Optional[float] = None):
        """
        上下文管理器方式获取会话

        Usage:
            with pool.session() as session:
                session.call_tool(...)
        """
        session = self.acquire(timeout=timeout)
        try:
            yield session
        finally:
            self.release(session)

    # ==================== 内部方法 ====================

    def _create_session(self) -> MCPSession:
        """创建新会话（内部方法，必须在锁内调用）"""
        session = self.session_factory()
        self._sessions.append(session)
        self._stats["total_created"] += 1
        return session

    def _destroy_session(self, session: MCPSession) -> None:
        """销毁会话（内部方法，必须在锁内调用）"""
        try:
            if session in self._sessions:
                self._sessions.remove(session)
            session.close()
            self._stats["total_destroyed"] += 1
            logger.debug(f"销毁会话: {session.session_id}")
        except Exception as e:
            logger.warning(f"销毁会话失败: {e}")

    def _start_cleanup_thread(self) -> None:
        """启动后台清理线程"""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._stop_cleanup.clear()
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True,
                name=f"mcp-pool-cleanup-{self.config.device_type}",
            )
            self._cleanup_thread.start()

    def _cleanup_loop(self) -> None:
        """后台清理循环"""
        check_interval = self.config.health_check_interval
        while not self._stop_cleanup.wait(check_interval):
            try:
                self._cleanup()
            except Exception as e:
                logger.error(f"清理循环异常: {e}", exc_info=True)

    def _cleanup(self) -> None:
        """清理不健康的会话"""
        with self._lock:
            if self._closed:
                return

            # 1. 清理空闲队列中的不健康会话
            healthy_idle = []
            while self._idle_queue:
                session = self._idle_queue.popleft()
                if session.is_healthy():
                    healthy_idle.append(session)
                else:
                    logger.info(f"清理不健康会话: {session.session_id}")
                    self._destroy_session(session)

            self._idle_queue = deque(healthy_idle)

            # 2. 检查当前会话数是否低于最小值
            if self.config.auto_scale:
                while len(self._sessions) < self.config.min_size:
                    try:
                        session = self._create_session()
                        self._idle_queue.append(session)
                    except Exception as e:
                        logger.error(f"自动扩容失败: {e}")
                        break

            # 3. 检查是否有过多的空闲会话（超过最大值的一部分）
            max_idle = max(1, self.config.max_size // 2)
            while len(self._idle_queue) > max_idle and len(self._sessions) > self.config.min_size:
                # 销毁多余的空闲会话
                session = self._idle_queue.pop()
                logger.info(f"缩容，销毁多余的空闲会话: {session.session_id}")
                self._destroy_session(session)

            # 通知等待的线程
            self._condition.notify_all()

    # ==================== 统计与监控 ====================

    def get_stats(self) -> PoolStats:
        """获取连接池统计信息"""
        with self._lock:
            idle_count = sum(1 for s in self._sessions if s.is_idle())
            busy_count = sum(1 for s in self._sessions if s.is_busy())
            error_count = len(self._sessions) - idle_count - busy_count

            avg_wait_ms = 0.0
            if self._stats["wait_times_ms"]:
                avg_wait_ms = sum(self._stats["wait_times_ms"]) / len(self._stats["wait_times_ms"])

            utilization = 0.0
            if self.config.max_size > 0:
                utilization = (busy_count / self.config.max_size) * 100

            return PoolStats(
                device_type=self.config.device_type,
                total_sessions=len(self._sessions),
                idle_sessions=idle_count,
                busy_sessions=busy_count,
                error_sessions=error_count,
                min_size=self.config.min_size,
                max_size=self.config.max_size,
                total_acquired=self._stats["total_acquired"],
                total_released=self._stats["total_released"],
                total_created=self._stats["total_created"],
                total_destroyed=self._stats["total_destroyed"],
                avg_wait_ms=round(avg_wait_ms, 2),
                utilization=round(utilization, 2),
            )

    def get_session_details(self) -> List[Dict[str, Any]]:
        """获取所有会话的详细信息"""
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "status": s.status.value,
                    "usage_count": s.usage_count,
                    "error_count": s.error_count,
                    "last_action": s.last_action,
                    "last_used_at": s.last_used_at.isoformat(),
                    "created_at": s.created_at.isoformat(),
                    "healthy": s.is_healthy(),
                }
                for s in self._sessions
            ]

    @property
    def is_closed(self) -> bool:
        """连接池是否已关闭"""
        with self._lock:
            return self._closed

    def __len__(self) -> int:
        """当前会话总数"""
        with self._lock:
            return len(self._sessions)

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
