"""
MCP 连接池 - 全局管理器

统一管理所有设备类型的连接池
- 按设备类型分组管理
- 配置加载与分发
- 跨设备负载均衡
- 统一监控接口

第三阶段将扩展支持分布式协调
"""
import threading
from typing import Dict, Optional, List, Any
import logging
from contextlib import contextmanager

from .types import PoolConfig
from .pool import MCPConnectionPool
from .config import load_config, MCPGlobalConfig, MCPServerConfig
from .session import MCPSession
from .port_manager import PortManager
from .exceptions import PoolConfigError, PoolClosedError


logger = logging.getLogger(__name__)


class PoolManager:
    """
    全局连接池管理器 - 单例模式

    管理所有设备类型的 MCP 连接池：
    - winapp (Windows 桌面)
    - browser (Playwright 浏览器)
    - hypium (移动端)
    - appium (Appium 协议)
    - 等等...
    """

    _instance: Optional["PoolManager"] = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        with self._lock:
            if hasattr(self, '_initialized') and self._initialized:
                return

            self._pools: Dict[str, MCPConnectionPool] = {}
            self._session_factories: Dict[str, callable] = {}
            self._config: Optional[MCPGlobalConfig] = None
            self._port_manager = PortManager()
            self._initialized = True

            logger.info("MCP 连接池管理器初始化完成")

    # ==================== 配置加载 ====================

    def load_config(self, config_path: Optional[str] = None) -> None:
        """
        加载配置文件

        Args:
            config_path: 配置文件路径，None 表示使用默认配置
        """
        self._config = load_config(config_path)

        # 配置端口管理器
        self._port_manager.configure(
            base_port=self._config.port_range_start,
            max_port=self._config.port_range_end,
        )

        logger.info(
            f"配置已加载: {len(self._config.servers)} 个 MCP 服务器, "
            f"端口范围 {self._config.port_range_start}-{self._config.port_range_end}"
        )

    def get_config(self) -> MCPGlobalConfig:
        """获取全局配置"""
        if self._config is None:
            self.load_config()
        return self._config

    # ==================== 会话工厂注册 ====================

    def register_session_factory(
        self,
        device_type: str,
        factory: callable,
    ) -> None:
        """
        注册会话工厂函数

        Args:
            device_type: 设备类型 (winapp, browser, hypium, etc.)
            factory: 工厂函数，接收 MCPServerConfig 并返回 MCPSession 实例
        """
        with self._lock:
            self._session_factories[device_type] = factory
            logger.info(f"已注册设备类型工厂: {device_type}")

    # ==================== 连接池管理 ====================

    def create_pool(
        self,
        device_type: str,
        pool_config: Optional[PoolConfig] = None,
    ) -> MCPConnectionPool:
        """
        创建指定设备类型的连接池

        Args:
            device_type: 设备类型
            pool_config: 连接池配置，None 表示使用默认配置

        Returns:
            连接池实例

        Raises:
            PoolConfigError: 未找到设备工厂或配置
        """
        with self._lock:
            if device_type in self._pools:
                logger.warning(f"连接池已存在，将使用现有连接池: {device_type}")
                return self._pools[device_type]

            if device_type not in self._session_factories:
                raise PoolConfigError(
                    f"未找到设备类型 '{device_type}' 的会话工厂，"
                    f"请先调用 register_session_factory()"
                )

            # 使用默认配置或自定义配置
            if pool_config is None:
                pool_config = PoolConfig(device_type=device_type)

            # 从配置中获取该类型的所有服务器配置
            servers = []
            if self._config:
                servers = self._config.get_servers_by_type(device_type)

            if not servers:
                logger.warning(
                    f"设备类型 '{device_type}' 未在配置文件中定义服务器，"
                    f"将使用默认连接配置"
                )
                # 创建一个默认的服务器配置
                default_server = MCPServerConfig(
                    name=f"{device_type}-default",
                    device_type=device_type,
                )
                servers = [default_server]

            # 创建会话工厂（轮询使用多个服务器配置）
            server_index = 0
            server_lock = threading.Lock()

            def pooled_factory():
                nonlocal server_index
                with server_lock:
                    server = servers[server_index % len(servers)]
                    server_index += 1
                factory = self._session_factories[device_type]
                return factory(server)

            # 创建连接池
            pool = MCPConnectionPool(pool_config, pooled_factory)
            pool.initialize()

            self._pools[device_type] = pool
            logger.info(
                f"连接池创建完成 [{device_type}]: "
                f"min={pool_config.min_size}, max={pool_config.max_size}, "
                f"servers={len(servers)}"
            )

            return pool

    def get_pool(self, device_type: str) -> MCPConnectionPool:
        """
        获取指定设备类型的连接池

        Args:
            device_type: 设备类型

        Returns:
            连接池实例

        Raises:
            PoolConfigError: 连接池不存在
        """
        with self._lock:
            if device_type not in self._pools:
                # 尝试自动创建
                logger.info(f"连接池不存在，尝试自动创建: {device_type}")
                return self.create_pool(device_type)
            return self._pools[device_type]

    def has_pool(self, device_type: str) -> bool:
        """检查是否存在指定设备类型的连接池"""
        with self._lock:
            return device_type in self._pools

    def close_pool(self, device_type: str, force: bool = False) -> None:
        """关闭指定设备类型的连接池"""
        with self._lock:
            if device_type in self._pools:
                self._pools[device_type].close(force=force)
                del self._pools[device_type]
                logger.info(f"连接池已关闭: {device_type}")

    def close_all(self, force: bool = False) -> None:
        """关闭所有连接池"""
        with self._lock:
            device_types = list(self._pools.keys())

        for device_type in device_types:
            try:
                self.close_pool(device_type, force=force)
            except Exception as e:
                logger.error(f"关闭连接池失败 [{device_type}]: {e}")

        logger.info("所有连接池已关闭")

    # ==================== 会话快捷 API ====================

    def acquire(
        self,
        device_type: str,
        timeout: Optional[float] = None,
    ) -> MCPSession:
        """
        快捷方式：获取指定设备类型的会话

        Args:
            device_type: 设备类型
            timeout: 超时时间（秒）

        Returns:
            MCP 会话
        """
        pool = self.get_pool(device_type)
        return pool.acquire(timeout=timeout)

    def release(self, device_type: str, session: MCPSession) -> None:
        """
        快捷方式：归还会话

        Args:
            device_type: 设备类型
            session: 要归还的会话
        """
        pool = self.get_pool(device_type)
        pool.release(session)

    @contextmanager
    def session(self, device_type: str, timeout: Optional[float] = None):
        """
        快捷方式：上下文管理器获取会话

        Usage:
            with PoolManager().session("winapp") as s:
                s.call_tool(...)
        """
        session = self.acquire(device_type, timeout=timeout)
        try:
            yield session
        finally:
            self.release(device_type, session)

    # ==================== 监控与统计 ====================

    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有连接池的统计信息"""
        with self._lock:
            stats = {}
            for device_type, pool in self._pools.items():
                stats[device_type] = pool.get_stats().to_dict()
            return stats

    def get_session_details(self, device_type: Optional[str] = None) -> Dict[str, Any]:
        """获取会话详细信息"""
        with self._lock:
            if device_type:
                return {
                    device_type: self.get_pool(device_type).get_session_details()
                }
            return {
                dt: pool.get_session_details()
                for dt, pool in self._pools.items()
            }

    def health_check(self) -> Dict[str, Any]:
        """全局健康检查"""
        stats = self.get_all_stats()

        total_sessions = sum(s["total_sessions"] for s in stats.values())
        busy_sessions = sum(s["busy_sessions"] for s in stats.values())
        error_sessions = sum(s["error_sessions"] for s in stats.values())

        overall_health = "healthy"
        if error_sessions > 0:
            overall_health = "degraded"
        if error_sessions > total_sessions * 0.5 and total_sessions > 0:
            overall_health = "critical"

        return {
            "overall_health": overall_health,
            "total_pools": len(self._pools),
            "total_sessions": total_sessions,
            "busy_sessions": busy_sessions,
            "error_sessions": error_sessions,
            "pools": stats,
            "port_manager": self._port_manager.stats,
        }

    # ==================== 属性 ====================

    @property
    def device_types(self) -> List[str]:
        """获取所有已注册的设备类型"""
        with self._lock:
            return list(self._pools.keys())

    @property
    def port_manager(self) -> PortManager:
        """获取端口管理器"""
        return self._port_manager


# 便捷函数 - 全局单例访问
def get_pool_manager() -> PoolManager:
    """获取连接池管理器单例"""
    return PoolManager()


def get_session(device_type: str, timeout: Optional[float] = None) -> MCPSession:
    """快捷方式：获取会话"""
    return get_pool_manager().acquire(device_type, timeout)


def release_session(device_type: str, session: MCPSession) -> None:
    """快捷方式：归还会话"""
    get_pool_manager().release(device_type, session)


@contextmanager
def session_context(device_type: str, timeout: Optional[float] = None):
    """快捷方式：会话上下文管理器"""
    with get_pool_manager().session(device_type, timeout) as s:
        yield s
