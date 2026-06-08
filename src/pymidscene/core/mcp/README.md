# MCP 连接池模块

## 概述

MCP 连接池模块为 pymidscene 提供多 MCP Server 的会话管理能力，支持：

- ✅ **第一阶段功能** - 本地连接池
  - 会话池管理（自动扩缩容）
  - 健康检查与自动清理
  - 负载均衡调度
  - 完整统计监控
  - 线程安全并发访问
- 🚧 **第三阶段功能** - 分布式协调（待实现）
  - 多节点协调
  - 全局任务调度
  - 故障转移

## 目录结构

```
src/pymidscene/core/mcp/
├── __init__.py       # 模块统一导出
├── types.py          # 类型定义、数据类
├── exceptions.py     # 异常体系
├── port_manager.py   # 通用端口管理器
├── session.py        # MCP 会话封装
├── config.py         # 多 MCP Server 配置加载
├── pool.py           # 单设备类型连接池
├── manager.py        # 全局连接池管理器
└── distributed/      # 第三阶段分布式模块（预留）
```

## 快速开始

### 1. 基础使用

```python
from pymidscene.core.mcp import (
    PoolManager,
    get_pool_manager,
    PoolConfig,
    MCPServerConfig,
    session_context,
)

# 1. 注册会话工厂
def create_my_mcp_session(config: MCPServerConfig):
    # 创建你的 MCP 客户端
    client = MyMCPClient(config)
    return MCPSession(
        mcp_client=client,
        device_type=config.device_type,
        config=config.to_dict(),
    )

manager = get_pool_manager()
manager.register_session_factory("winapp", create_my_mcp_session)

# 2. 加载配置（可选）
manager.load_config("config/mcp-servers.example.yaml")

# 3. 创建连接池
pool = manager.create_pool(
    "winapp",
    PoolConfig(
        device_type="winapp",
        min_size=2,
        max_size=10,
        auto_scale=True,
        acquire_timeout=30,
    )
)

# 4. 使用会话
with pool.session() as session:
    result = session.call_tool("winapp_click_element", {
        "element_id": "btn-login"
    })
```

### 2. 快捷 API

```python
# 使用全局快捷方式
from pymidscene.core.mcp import get_session, release_session

# 方式 1: 显式获取/归还
session = get_session("winapp", timeout=10)
try:
    session.call_tool("...")
finally:
    release_session("winapp", session)

# 方式 2: 上下文管理器
from pymidscene.core.mcp import session_context

with session_context("winapp") as session:
    session.call_tool("...")
```

### 3. 并发示例

```python
import threading

def worker(worker_id):
    with session_context("winapp", timeout=30) as session:
        session.call_tool("do_work", {"worker_id": worker_id})

# 启动 100 个并发任务
threads = []
for i in range(100):
    t = threading.Thread(target=worker, args=(i,))
    t.start()
    threads.append(t)

for t in threads:
    t.join()
```

## 配置说明

### PoolConfig 连接池配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| device_type | str | 必填 | 设备类型：winapp/browser/hypium/appium |
| min_size | int | 1 | 最小会话数（预热） |
| max_size | int | 5 | 最大会话数（并发上限） |
| acquire_timeout | int | 30 | 获取会话超时时间（秒） |
| auto_scale | bool | True | 是否自动扩缩容 |
| health_check_interval | int | 60 | 健康检查间隔（秒） |
| max_idle_time | int | 300 | 会话最大空闲时间（秒） |
| max_usage_count | int | 1000 | 会话最大使用次数 |

### 配置文件格式

```yaml
# config/mcp-servers.yaml
port_range_start: 4724
port_range_end: 4999
servers:
  - name: winapp-01
    device_type: winapp
    host: localhost
    port: 4724
    capacity: 5
    tags: ["primary", "fast"]

  - name: winapp-02
    device_type: winapp
    host: localhost
    port: auto  # 自动分配端口
    capacity: 5

  - name: browser-01
    device_type: browser
    url: http://localhost:9222
    tags: ["chrome", "headless"]
```

## 监控与统计

### 获取单个连接池统计

```python
pool = manager.get_pool("winapp")
stats = pool.get_stats()

print(f"总会话数: {stats.total_sessions}")
print(f"空闲会话: {stats.idle_sessions}")
print(f"忙碌会话: {stats.busy_sessions}")
print(f"利用率: {stats.utilization}%")
print(f"平均等待: {stats.avg_wait_ms}ms")
```

### 全局健康检查

```python
health = manager.health_check()

print(f"整体状态: {health['overall_health']}")
print(f"连接池数量: {health['total_pools']}")
print(f"总会话数: {health['total_sessions']}")
print(f"错误会话: {health['error_sessions']}")
```

### 会话详细信息

```python
details = manager.get_session_details("winapp")
for sess in details["winapp"]:
    print(f"  {sess['session_id']}: {sess['status']} "
          f"(使用={sess['usage_count']}, 错误={sess['error_count']})")
```

## 端口管理器

通用端口分配组件，支持所有需要独立端口的场景：

```python
port_mgr = manager.port_manager

# 分配端口
port = port_mgr.allocate("winapp", worker_id="worker-001")

# 释放端口
port_mgr.release(port)

# 查看统计
stats = port_mgr.stats
print(f"已分配: {stats['total_allocated']}")
print(f"可用: {stats['available']}")
```

## 异常处理

完整的异常层次结构：

```
MCPError (基类)
├── PoolError (连接池异常)
│   ├── PoolClosedError (连接池已关闭)
│   ├── PoolTimeoutError (获取会话超时)
│   ├── PoolFullError (连接池已满)
│   └── PoolConfigError (配置错误)
├── SessionError (会话异常)
│   ├── SessionNotFoundError (会话不存在)
│   ├── SessionBusyError (会话忙碌)
│   └── SessionInvalidError (会话无效)
├── PortError (端口异常)
│   ├── PortAllocationError (端口分配失败)
│   └── PortReleaseError (端口释放失败)
└── DistributedError (分布式异常)
    ├── CoordinatorConnectionError (协调器连接失败)
    ├── WorkerRegistrationError (Worker 注册失败)
    └── TaskDispatchError (任务分发失败)
```

使用示例：

```python
from pymidscene.core.mcp import PoolTimeoutError, PoolClosedError

try:
    with session_context("winapp", timeout=5) as session:
        session.call_tool("...")
except PoolTimeoutError:
    print("获取会话超时，请稍后重试")
except PoolClosedError:
    print("连接池已关闭")
```

## 线程安全

- 所有 API 都是线程安全的
- `MCPConnectionPool` 使用 `threading.Lock` 保护内部状态
- `PoolManager` 是线程安全的单例
- 空闲队列使用 `threading.Condition` 实现等待通知机制

## 最佳实践

1. **总是使用上下文管理器**：确保会话正确归还
2. **合理设置超时**：避免长时间阻塞
3. **配置合适的池大小**：
   - `min_size`: 根据预期并发基线设置
   - `max_size`: 根据服务器负载能力设置
4. **定期监控**：关注利用率、等待时间、错误率
5. **优雅关闭**：程序退出时调用 `manager.close_all()`

## 运行示例

```bash
# 运行连接池演示
cd /app/tis/pymidscene
python -c "
import sys
sys.path.insert(0, 'src')
exec(open('examples/mcp_pool_demo.py').read())
"
```

## 下一步

- [ ] 实现第三阶段分布式协调器
- [ ] 实现 Worker 节点注册与心跳
- [ ] 实现全局任务调度算法
- [ ] 实现故障转移机制
- [ ] 添加更多单元测试
- [ ] 集成 WinApp MCP Server 实现
