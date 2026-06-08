"""
Pymidscene MCP 连接池核心模块

提供多 MCP 服务器统一管理、连接池、会话管理等功能。

第一阶段：
  - 会话状态管理
  - 本地连接池
  - 端口动态分配

第三阶段：
  - 分布式协调
  - 多节点任务分发
  - 负载均衡
"""

# 类型和配置
from .types import (
    SessionStatus,
    PoolConfig,
    SessionStats,
    PoolStats,
)
from .config import (
    MCPServerConfig,
    MCPGlobalConfig,
    ConfigLoader,
    load_config,
    get_config,
)

# 异常
from .exceptions import (
    MCPError,
    PoolError,
    PoolClosedError,
    PoolTimeoutError,
    PoolFullError,
    PoolConfigError,
    SessionError,
    SessionNotFoundError,
    SessionBusyError,
    SessionInvalidError,
    PortError,
    PortAllocationError,
    PortReleaseError,
    DistributedError,
    CoordinatorConnectionError,
    WorkerRegistrationError,
    TaskDispatchError,
)

# 核心组件
from .session import MCPSession
from .port_manager import PortManager, PortInfo
from .pool import MCPConnectionPool
from .manager import (
    PoolManager,
    get_pool_manager,
    get_session,
    release_session,
    session_context,
)

__version__ = "1.0.0"
__all__ = [
    # 类型
    "SessionStatus",
    "PoolConfig",
    "SessionStats",
    "PoolStats",
    # 配置
    "MCPServerConfig",
    "MCPGlobalConfig",
    "ConfigLoader",
    "load_config",
    "get_config",
    # 异常
    "MCPError",
    "PoolError",
    "PoolClosedError",
    "PoolTimeoutError",
    "PoolFullError",
    "PoolConfigError",
    "SessionError",
    "SessionNotFoundError",
    "SessionBusyError",
    "SessionInvalidError",
    "PortError",
    "PortAllocationError",
    "PortReleaseError",
    "DistributedError",
    "CoordinatorConnectionError",
    "WorkerRegistrationError",
    "TaskDispatchError",
    # 核心组件
    "MCPSession",
    "PortManager",
    "PortInfo",
    "MCPConnectionPool",
    "PoolManager",
    "get_pool_manager",
    "get_session",
    "release_session",
    "session_context",
]
