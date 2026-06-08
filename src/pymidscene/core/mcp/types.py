"""
MCP 连接池 - 类型定义与配置
"""
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta


class SessionStatus(Enum):
    """会话状态枚举"""
    IDLE = "idle"           # 空闲，可使用
    BUSY = "busy"           # 正在使用
    ERROR = "error"         # 错误状态，需要销毁重建
    EXPIRED = "expired"     # 已过期，需要清理


@dataclass
class PoolConfig:
    """
    连接池配置

    第一阶段基础配置，后续扩展第三阶段分布式配置
    """
    device_type: str

    # 基础配置（第一阶段）
    min_size: int = 1           # 最小连接数
    max_size: int = 5           # 最大连接数
    acquire_timeout: int = 30   # 获取会话超时时间（秒）

    # 高级配置（第一阶段 +）
    max_idle_time: int = 300    # 最大空闲时间（秒）
    max_session_age: int = 3600  # 会话最大存活时间（秒）
    max_errors_per_session: int = 5  # 单个会话最大错误数
    auto_scale: bool = True      # 是否自动扩缩容

    # 健康检查配置
    health_check_interval: int = 60  # 健康检查间隔（秒）

    # 第三阶段：分布式配置
    distributed: bool = False      # 是否启用分布式模式
    coordinator_url: Optional[str] = None  # 协调器地址
    worker_id: Optional[str] = None       # 当前工作节点 ID
    heartbeat_interval: int = 30          # 心跳间隔（秒）

    # 扩展字段
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_distributed(self) -> bool:
        """是否为分布式模式"""
        return self.distributed and bool(self.coordinator_url)

    def validate(self) -> None:
        """验证配置有效性"""
        if self.min_size < 0:
            raise ValueError("min_size 不能为负数")
        if self.max_size < self.min_size:
            raise ValueError("max_size 不能小于 min_size")
        if self.acquire_timeout <= 0:
            raise ValueError("acquire_timeout 必须为正数")
        if self.is_distributed and not self.coordinator_url:
            raise ValueError("分布式模式需要配置 coordinator_url")


@dataclass
class SessionStats:
    """会话统计信息"""
    session_id: str
    device_type: str
    status: SessionStatus
    created_at: float
    last_used_at: float
    usage_count: int
    error_count: int
    last_error: Optional[str] = None


@dataclass
class PoolStats:
    """连接池统计信息"""
    device_type: str
    total_sessions: int
    idle_sessions: int
    busy_sessions: int
    error_sessions: int
    min_size: int
    max_size: int
    total_acquired: int
    total_released: int
    total_created: int
    total_destroyed: int
    avg_wait_ms: float
    utilization: float  # 0-100

    # 分布式模式额外统计
    distributed: bool = False
    worker_count: int = 0
    pending_tasks: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


# 类型别名
SessionFactory = Callable[[], Any]  # 创建 MCP 会话的工厂函数
