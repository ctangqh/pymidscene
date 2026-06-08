"""
MCP 连接池 - 异常体系
"""


class MCPError(Exception):
    """MCP 相关异常基类"""
    pass


# ==================== 连接池异常 ====================

class PoolError(MCPError):
    """连接池异常基类"""
    pass


class PoolClosedError(PoolError):
    """连接池已关闭"""
    pass


class PoolTimeoutError(PoolError):
    """获取会话超时"""
    def __init__(self, device_type: str, timeout: int, pool_state: str):
        self.device_type = device_type
        self.timeout = timeout
        self.pool_state = pool_state
        super().__init__(
            f"获取 {device_type} 会话超时 ({timeout}s)。当前状态: {pool_state}"
        )


class PoolFullError(PoolError):
    """连接池已满"""
    def __init__(self, device_type: str, max_size: int):
        self.device_type = device_type
        self.max_size = max_size
        super().__init__(f"{device_type} 连接池已满 (max={max_size})")


class PoolConfigError(PoolError):
    """连接池配置错误"""
    pass


# ==================== 会话异常 ====================

class SessionError(MCPError):
    """会话异常基类"""
    pass


class SessionNotFoundError(SessionError):
    """会话不存在"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"会话不存在: {session_id}")


class SessionBusyError(SessionError):
    """会话正在使用中"""
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(f"会话正在使用中: {session_id}")


class SessionInvalidError(SessionError):
    """会话无效（错误太多或已过期）"""
    def __init__(self, session_id: str, reason: str):
        self.session_id = session_id
        self.reason = reason
        super().__init__(f"会话无效 [{reason}]: {session_id}")


# ==================== 端口管理异常 ====================

class PortError(MCPError):
    """端口管理异常基类"""
    pass


class PortAllocationError(PortError):
    """端口分配失败"""
    def __init__(self, message: str = "没有可用端口"):
        super().__init__(message)


class PortReleaseError(PortError):
    """端口释放失败"""
    def __init__(self, port: int, message: str = ""):
        self.port = port
        super().__init__(f"端口释放失败 [{port}]: {message}")


# ==================== 分布式异常 ====================

class DistributedError(MCPError):
    """分布式模式异常基类"""
    pass


class CoordinatorConnectionError(DistributedError):
    """协调器连接失败"""
    def __init__(self, url: str, original_error: Exception = None):
        self.url = url
        self.original_error = original_error
        super().__init__(f"无法连接到协调器: {url}")


class WorkerRegistrationError(DistributedError):
    """工作节点注册失败"""
    def __init__(self, worker_id: str, message: str = ""):
        self.worker_id = worker_id
        super().__init__(f"工作节点注册失败 [{worker_id}]: {message}")


class TaskDispatchError(DistributedError):
    """任务分发失败"""
    def __init__(self, task_id: str, message: str = ""):
        self.task_id = task_id
        super().__init__(f"任务分发失败 [{task_id}]: {message}")


# ==================== 工具函数 ====================

def wrap_exception(exc: Exception, context: str = "") -> MCPError:
    """包装异常为 MCP 异常类型"""
    if isinstance(exc, MCPError):
        return exc

    msg = f"{context}: {exc}" if context else str(exc)

    if isinstance(exc, TimeoutError):
        return PoolTimeoutError("unknown", 0, msg)
    if isinstance(exc, ConnectionError):
        return CoordinatorConnectionError("unknown", exc)

    return MCPError(msg)
