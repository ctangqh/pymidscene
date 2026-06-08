"""
MCP 连接池 - 通用端口管理器

支持所有需要独立端口的场景：
- WinAppDriver (Windows 自动化)
- Appium Server (移动端自动化)
- Playwright Server (分布式浏览器)
- Selenium Grid (分布式测试)

功能：
- 动态分配可用端口
- 端口健康检查
- 端口释放与回收
- 分布式端口冲突检测
"""
import socket
import threading
import time
from typing import Set, Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

from .exceptions import PortAllocationError, PortReleaseError


logger = logging.getLogger(__name__)


@dataclass
class PortInfo:
    """端口信息"""
    port: int
    device_type: str
    worker_id: Optional[str] = None
    allocated_at: datetime = field(default_factory=datetime.now)
    last_health_check: Optional[datetime] = None
    is_healthy: bool = True


class PortManager:
    """
    端口管理器 - 单例模式

    负责:
    - 动态分配可用端口
    - 端口健康检查
    - 端口释放与回收
    - 分布式端口冲突检测
    """

    _instance: Optional["PortManager"] = None
    _lock = threading.RLock()

    # 默认端口范围
    DEFAULT_BASE_PORT = 4724  # WinAppDriver 默认是 4723，从 4724 开始分配
    DEFAULT_MAX_PORT = 4999

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        with self._lock:
            if hasattr(self, '_initialized'):
                return

            self._used_ports: Set[int] = set()
            self._port_info: Dict[int, PortInfo] = {}
            self._base_port = self.DEFAULT_BASE_PORT
            self._max_port = self.DEFAULT_MAX_PORT
            self._initialized = True

            logger.info(f"端口管理器初始化: 端口范围 {self._base_port}-{self._max_port}")

    def configure(self, base_port: int, max_port: int) -> None:
        """配置端口范围"""
        with self._lock:
            self._base_port = base_port
            self._max_port = max_port
            logger.info(f"端口范围已更新: {base_port}-{max_port}")

    @staticmethod
    def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
        """
        检查端口是否可用

        注意：这只是快速检查，不保证绝对可靠（有竞态条件可能）
        """
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                result = s.connect_ex((host, port))
                return result != 0  # 0 表示可以连接（端口被占用）
        except Exception:
            return True  # 出错时假设可用（保守策略）

    def allocate(
        self,
        device_type: str,
        prefer_port: Optional[int] = None,
        worker_id: Optional[str] = None,
        check_available: bool = True,
    ) -> int:
        """
        分配一个端口

        Args:
            device_type: 设备类型（winapp, browser, etc.）
            prefer_port: 优先尝试的端口（如果已占用则分配下一个）
            worker_id: 工作节点 ID（分布式模式）
            check_available: 是否检查端口实际可用

        Returns:
            分配的端口号

        Raises:
            PortAllocationError: 没有可用端口时
        """
        with self._lock:
            # 优先尝试指定端口
            if prefer_port is not None:
                if prefer_port not in self._used_ports:
                    if check_available and not self.is_port_available(prefer_port):
                        pass  # 继续找下一个
                    else:
                        self._mark_allocate_port(prefer_port, device_type, worker_id)
                        return prefer_port

            # 从 base_port 开始查找
            port = self._base_port
            while port <= self._max_port:
                if port not in self._used_ports:
                    if not check_available or self.is_port_available(port):
                        self._mark_allocate_port(port, device_type, worker_id)
                        return port
                else:
                    # 端口被外部进程占用，标记为已用
                    self._used_ports.add(port)
                port += 1

            # 没有找到可用端口
            raise PortAllocationError(
        f"在端口范围内没有可用端口 (范围: {self._base_port}-{self._max_port}, "
        f"已使用: {len(self._used_ports)} 个)"
    )

    def _mark_allocate_port(self, port: int, device_type: str, worker_id: Optional[str]) -> None:
        """标记端口为已分配"""
        self._used_ports.add(port)
        self._port_info[port] = PortInfo(
            port=port,
            device_type=device_type,
            worker_id=worker_id,
        )
        logger.debug(f"端口已分配: {port} ({device_type}, worker={worker_id}")

    def release(self, port: int, force: bool = False) -> None:
        """
        释放端口

        Args:
            port: 要释放的端口
            force: 是否强制释放（即使不存在也不报错）
        """
        with self._lock:
            if port not in self._used_ports:
                if force:
                    return
                raise PortReleaseError(port, "端口未被分配")

            self._used_ports.discard(port)
            self._port_info.pop(port, None)
            logger.debug(f"端口已释放: {port}")

    def release_by_worker(self, worker_id: str) -> List[int]:
        """释放指定工作节点的所有端口"""
        with self._lock:
            to_release = [
                port for port, info in self._port_info.items()
                if info.worker_id == worker_id
            ]
            for port in to_release:
                self.release(port, force=True)
            logger.info(f"已释放工作节点 {worker_id} 的 {len(to_release)} 个端口")
            return to_release

    def get_port_info(self, port: int) -> Optional[PortInfo]:
        """获取端口信息"""
        with self._lock:
            return self._port_info.get(port)

    def list_allocated_ports(self, device_type: Optional[str] = None) -> List[int]:
        """列出已分配的端口"""
        with self._lock:
            if device_type:
                return [
                    port for port, info in self._port_info.items()
                    if info.device_type == device_type
                ]
            return list(self._used_ports)

    def health_check(self) -> Dict[str, Any]:
        """检查所有已分配端口的健康状态
        """
        with self._lock:
            results = {
                "total": len(self._used_ports),
                "healthy": 0,
                "unhealthy": 0,
                "details": {},
            }

            for port, info in self._port_info.items():
                is_healthy = self.is_port_available(port)
                info.is_healthy = is_healthy
                info.last_health_check = datetime.now()

                if is_healthy:
                    results["healthy"] += 1
                else:
                    results["unhealthy"] += 1

                results["details"][port] = {
                    "device_type": info.device_type,
                    "worker_id": info.worker_id,
                    "healthy": is_healthy,
                    "allocated_at": info.allocated_at.isoformat(),
                }

            logger.info(
                f"端口健康检查完成: 总计={results['total']}, "
                f"健康={results['healthy']}, 异常={results['unhealthy']}"
            )

            return results

    def cleanup_unhealthy_ports(self, max_age: int = 3600) -> int:
        """
        清理长时间未使用的端口（可能是泄露的端口

        Args:
            max_age: 最大存活时间（秒）

        Returns:
            清理的端口数量
        """
        with self._lock:
            now = datetime.now()
            to_cleanup = []

            for port, info in self._port_info.items():
                age = (now - info.allocated_at).total_seconds()
                if age > max_age and info.is_healthy:
                    # 端口已分配但长时间未使用，可能泄露了
                    to_cleanup.append(port)

            for port in to_cleanup:
                self.release(port, force=True)

            if to_cleanup:
                logger.warning(f"清理了 {len(to_cleanup)} 个泄露的端口: {to_cleanup}")

            return len(to_cleanup)

    def reset(self) -> None:
        """重置所有端口（谨慎使用）
        """
        with self._lock:
            self._used_ports.clear()
            self._port_info.clear()
            logger.warning("端口管理器已重置")

    @property
    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        with self._lock:
            return {
                "total_allocated": len(self._used_ports),
                "available": self._max_port - self._base_port + 1 - len(self._used_ports),
                "range": f"{self._base_port}-{self._max_port}",
                "by_device_type": {
                    dt: sum(1 for info in self._port_info.values() if info.device_type == dt)
                    for dt in set(info.device_type for info in self._port_info.values())
                },
            }


# 便捷函数式接口
_port_manager = PortManager()

allocate_port = _port_manager.allocate
release_port = _port_manager.release
get_port_stats = lambda: _port_manager.stats
