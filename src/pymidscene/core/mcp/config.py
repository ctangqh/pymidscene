"""
MCP 服务器配置管理

支持多设备类型、多实例的统一配置管理
配置优先级：环境变量 > YAML 文件 > 默认值
"""
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field, asdict
import yaml

from .types import PoolConfig


# ==================== 单服务器配置 ====================

@dataclass
class MCPServerConfig:
    """单个 MCP 服务器的配置"""
    # 基础信息
    name: str
    device_type: str  # winapp, browser, hypium, android, ios, etc.

    # 连接配置
    host: str = "127.0.0.1"
    port: Optional[int] = None  # None 表示动态分配
    auto_start: bool = True  # 是否自动启动服务

    # 启动命令（如果是本地进程）
    start_command: Optional[str] = None
    start_cwd: Optional[str] = None

    # 健康检查
    health_check_url: Optional[str] = None
    health_check_interval: int = 30

    # 池配置
    min_instances: int = 1
    max_instances: int = 5

    # 认证
    api_key: Optional[str] = None

    # 扩展参数（透传给设备实现）
    options: Dict[str, Any] = field(default_factory=dict)

    def to_pool_config(self) -> PoolConfig:
        """转换为连接池配置"""
        return PoolConfig(
            device_type=self.device_type,
            min_size=self.min_instances,
            max_size=self.max_instances,
            metadata={
                "server_name": self.name,
                "host": self.host,
                "port": self.port,
                "auto_start": self.auto_start,
                "options": self.options,
            }
        )


# ==================== 全局配置 ====================

@dataclass
class MCPGlobalConfig:
    """MCP 全局配置"""
    # 通用配置
    log_level: str = "INFO"
    enable_metrics: bool = True

    # 端口管理配置
    port_range_start: int = 4724
    port_range_end: int = 4999

    # 连接池默认配置
    default_pool: Dict[str, Any] = field(default_factory=lambda: {
        "min_size": 1,
        "max_size": 5,
        "acquire_timeout": 30,
        "auto_scale": True,
    })

    # 分布式模式配置
    distributed: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": False,
        "coordinator_url": None,
        "worker_id": None,
        "worker_tags": [],
    })

    # 所有 MCP 服务器配置
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """获取指定服务器配置"""
        return self.servers.get(name)

    def get_servers_by_type(self, device_type: str) -> List[MCPServerConfig]:
        """根据设备类型获取所有服务器配置"""
        return [
            server for server in self.servers.values()
            if server.device_type == device_type
        ]


# ==================== 配置加载器 ====================

class ConfigLoader:
    """配置加载器"""

    _instance: Optional["ConfigLoader"] = None
    _config: Optional[MCPGlobalConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is not None:
            return
        self._config = self._load_default()

    def _load_default(self) -> MCPGlobalConfig:
        """加载默认配置"""
        config = MCPGlobalConfig()

        # 从环境变量覆盖
        if os.getenv("MCP_LOG_LEVEL"):
            config.log_level = os.getenv("MCP_LOG_LEVEL")
        if os.getenv("MCP_PORT_RANGE_START"):
            config.port_range_start = int(os.getenv("MCP_PORT_RANGE_START"))
        if os.getenv("MCP_PORT_RANGE_END"):
            config.port_range_end = int(os.getenv("MCP_PORT_RANGE_END"))

        return config

    def load_yaml(self, config_path: str) -> None:
        """从 YAML 文件加载配置"""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # 加载全局配置
        if "global" in data:
            g = data["global"]
            if "log_level" in g:
                self._config.log_level = g["log_level"]
            if "enable_metrics" in g:
                self._config.enable_metrics = g["enable_metrics"]
            if "port_range" in g:
                pr = g["port_range"]
                if "start" in pr:
                    self._config.port_range_start = pr["start"]
                if "end" in pr:
                    self._config.port_range_end = pr["end"]
            if "default_pool" in g:
                self._config.default_pool.update(g["default_pool"])
            if "distributed" in g:
                self._config.distributed.update(g["distributed"])

        # 加载各个服务器配置
        if "servers" in data:
            for name, server_data in data["servers"].items():
                server = MCPServerConfig(
                    name=name,
                    device_type=server_data.get("device_type", "unknown"),
                    host=server_data.get("host", "127.0.0.1"),
                    port=server_data.get("port"),
                    auto_start=server_data.get("auto_start", True),
                    start_command=server_data.get("start_command"),
                    start_cwd=server_data.get("start_cwd"),
                    health_check_url=server_data.get("health_check_url"),
                    health_check_interval=server_data.get("health_check_interval", 30),
                    min_instances=server_data.get("min_instances", self._config.default_pool["min_size"]),
                    max_instances=server_data.get("max_instances", self._config.default_pool["max_size"]),
                    api_key=server_data.get("api_key"),
                    options=server_data.get("options", {}),
                )
                self._config.servers[name] = server

    def load_env(self) -> None:
        """从环境变量加载（覆盖 YAML 配置）"""
        # TODO: 支持 MCP_SERVER_xxx 格式的环境变量
        pass

    def get_config(self) -> MCPGlobalConfig:
        """获取全局配置"""
        return self._config

    def save_yaml(self, config_path: str) -> None:
        """保存配置到 YAML 文件"""
        data = {
            "global": {
                "log_level": self._config.log_level,
                "enable_metrics": self._config.enable_metrics,
                "port_range": {
                    "start": self._config.port_range_start,
                    "end": self._config.port_range_end,
                },
                "default_pool": self._config.default_pool,
                "distributed": self._config.distributed,
            },
            "servers": {
                name: {
                    "device_type": s.device_type,
                    "host": s.host,
                    "port": s.port,
                    "auto_start": s.auto_start,
                    "start_command": s.start_command,
                    "start_cwd": s.start_cwd,
                    "health_check_url": s.health_check_url,
                    "health_check_interval": s.health_check_interval,
                    "min_instances": s.min_instances,
                    "max_instances": s.max_instances,
                    "api_key": s.api_key,
                    "options": s.options,
                }
                for name, s in self._config.servers.items()
            }
        }

        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)


# 便捷函数
def load_config(config_path: Optional[str] = None) -> MCPGlobalConfig:
    """加载配置"""
    loader = ConfigLoader()
    if config_path and Path(config_path).exists():
        loader.load_yaml(config_path)
    loader.load_env()
    return loader.get_config()


def get_config() -> MCPGlobalConfig:
    """获取当前配置"""
    return ConfigLoader().get_config()
