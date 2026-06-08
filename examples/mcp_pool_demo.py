"""
MCP 连接池使用示例 - 多 MCP Server 并发场景

演示如何：
1. 加载配置文件
2. 注册多个设备类型的会话工厂
3. 并发获取和使用会话
4. 监控连接池状态
"""
import sys
from pathlib import Path

# 添加项目路径 - src 目录
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

import threading
import time
from typing import Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from pymidscene.core.mcp import (
    PoolManager,
    get_pool_manager,
    session_context,
    MCPServerConfig,
    MCPSession,
)


# ==================== 示例 1: Mock MCP 客户端（用于演示）====================

class MockMCPClient:
    """Mock MCP 客户端，用于演示"""

    def __init__(self, server_config: MCPServerConfig):
        self.config = server_config
        self._healthy = True

    def call_tool(self, tool_name: str, arguments: Dict):
        """模拟调用工具"""
        if not self._healthy:
            raise RuntimeError("MCP Client is unhealthy")

        # 模拟执行时间
        time.sleep(0.1)
        return {
            "status": "success",
            "tool": tool_name,
            "server": self.config.name,
            "arguments": arguments,
        }

    def close(self):
        pass


def create_mock_session(server_config: MCPServerConfig) -> MCPSession:
    """创建 Mock 会话的工厂函数"""
    client = MockMCPClient(server_config)
    session = MCPSession(
        mcp_client=client,
        device_type=server_config.device_type,
        config={},
        session_id=f"{server_config.name}-{id(client)}",
    )
    return session


# ==================== 示例 2: 基本使用 ====================

def example_basic_usage():
    """基本使用方式"""
    print("\n" + "=" * 60)
    print("示例 1: 基本使用")
    print("=" * 60)

    # 1. 获取管理器单例
    manager = get_pool_manager()

    # 2. 加载配置（可选，如果不调用则使用默认配置）
    # manager.load_config("config/mcp-servers.example.yaml")

    # 3. 注册会话工厂
    manager.register_session_factory("winapp", create_mock_session)
    manager.register_session_factory("browser", create_mock_session)

    # 4. 创建连接池（可以自定义配置）
    from pymidscene.core.mcp import PoolConfig

    winapp_pool = manager.create_pool(
        "winapp",
        PoolConfig(
            device_type="winapp",
            min_size=2,
            max_size=5,
            auto_scale=True,
        )
    )

    browser_pool = manager.create_pool(
        "browser",
        PoolConfig(
            device_type="browser",
            min_size=3,
            max_size=8,
            auto_scale=True,
        )
    )

    print(f"\nWinApp 池大小: {len(winapp_pool)}")
    print(f"Browser 池大小: {len(browser_pool)}")

    # 5. 使用会话（方式一：显式 acquire/release）
    print("\n--- 方式一: 显式 acquire/release ---")
    session = winapp_pool.acquire()
    print(f"获取会话: {session.session_id}")
    result = session.call_tool("winapp_click_element", {"element_id": "btn-123"})
    print(f"工具调用结果: {result}")
    winapp_pool.release(session)
    print(f"会话已归还")

    # 6. 使用会话（方式二：上下文管理器）
    print("\n--- 方式二: 上下文管理器 ---")
    with winapp_pool.session() as session:
        print(f"获取会话: {session.session_id}")
        result = session.call_tool("winapp_send_keys", {"text": "Hello MCP!"})
        print(f"工具调用结果: {result}")

    # 7. 使用会话（方式三：全局快捷方式）
    print("\n--- 方式三: 全局快捷方式 ---")
    with session_context("browser") as session:
        print(f"获取 Browser 会话: {session.session_id}")
        result = session.call_tool("browser_navigate", {"url": "https://example.com"})
        print(f"工具调用结果: {result}")


# ==================== 示例 3: 并发访问 ====================

def example_concurrent_access():
    """演示并发访问连接池"""
    print("\n" + "=" * 60)
    print("示例 2: 并发访问")
    print("=" * 60)

    manager = get_pool_manager()

    # 确保工厂已注册
    if "winapp" not in manager._session_factories:
        manager.register_session_factory("winapp", create_mock_session)

    # 确保池已创建
    if not manager.has_pool("winapp"):
        from pymidscene.core.mcp import PoolConfig
        manager.create_pool(
            "winapp",
            PoolConfig(
                device_type="winapp",
                min_size=2,
                max_size=5,
            )
        )

    pool = manager.get_pool("winapp")
    print(f"\n初始池状态: {len(pool)} 个会话")

    # 启动多个线程并发访问
    results = []
    threads = []

    def worker(worker_id: int):
        """工作线程"""
        try:
            with pool.session(timeout=10) as session:
                # 模拟工作
                result = session.call_tool(
                    "winapp_do_something",
                    {"worker_id": worker_id}
                )
                results.append((worker_id, "success", session.session_id))
                print(f"  Worker {worker_id}: 使用会话 {session.session_id}")
        except Exception as e:
            results.append((worker_id, "error", str(e)))
            print(f"  Worker {worker_id}: 错误 - {e}")

    # 启动 10 个并发线程（超过 min_size，测试自动扩容）
    print(f"\n启动 10 个并发线程...")
    start_time = time.time()

    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    elapsed = time.time() - start_time
    print(f"\n并发完成: {elapsed:.2f}s")

    # 统计结果
    success = sum(1 for r in results if r[1] == "success")
    errors = sum(1 for r in results if r[1] == "error")
    print(f"成功: {success}, 错误: {errors}")
    print(f"最终池大小: {len(pool)} 个会话")

    # 显示统计
    stats = pool.get_stats()
    print(f"统计: 获取={stats.total_acquired}, 归还={stats.total_released}, "
          f"创建={stats.total_created}, 平均等待={stats.avg_wait_ms}ms")


# ==================== 示例 4: 监控与健康检查 ====================

def example_monitoring():
    """演示连接池监控"""
    print("\n" + "=" * 60)
    print("示例 3: 连接池监控")
    print("=" * 60)

    manager = get_pool_manager()

    # 全局健康检查
    print("\n--- 全局健康状态 ---")
    health = manager.health_check()
    print(f"整体健康状态: {health['overall_health']}")
    print(f"连接池数量: {health['total_pools']}")
    print(f"总会话数: {health['total_sessions']}")
    print(f"忙碌会话: {health['busy_sessions']}")
    print(f"错误会话: {health['error_sessions']}")

    # 各连接池详细统计
    print("\n--- 各连接池统计 ---")
    all_stats = manager.get_all_stats()
    for device_type, stats in all_stats.items():
        print(f"\n  [{device_type.upper()}]")
        print(f"    会话数: {stats['total_sessions']} "
              f"(空闲={stats['idle_sessions']}, "
              f"忙碌={stats['busy_sessions']}, "
              f"错误={stats['error_sessions']})")
        print(f"    利用率: {stats['utilization']}%")
        print(f"    平均等待: {stats['avg_wait_ms']}ms")
        print(f"    获取/归还: {stats['total_acquired']}/{stats['total_released']}")

    # 会话详细信息
    print("\n--- 会话详细信息 ---")
    details = manager.get_session_details()
    for device_type, sessions in details.items():
        print(f"\n  [{device_type.upper()}] 会话列表:")
        for sess in sessions:
            print(f"    - {sess['session_id']}: {sess['status']} "
                  f"(使用={sess['usage_count']}, 错误={sess['error_count']})")


# ==================== 示例 5: 端口管理 ====================

def example_port_manager():
    """演示端口管理器使用"""
    print("\n" + "=" * 60)
    print("示例 4: 端口管理器")
    print("=" * 60)

    manager = get_pool_manager()
    port_mgr = manager.port_manager

    print(f"\n端口范围: {port_mgr._base_port}-{port_mgr._max_port}")

    # 分配端口
    print("\n--- 分配端口 ---")
    port1 = port_mgr.allocate("winapp", worker_id="worker-01")
    port2 = port_mgr.allocate("browser", worker_id="worker-01")
    port3 = port_mgr.allocate("hypium", worker_id="worker-02")

    print(f"分配 WinApp 端口: {port1}")
    print(f"分配 Browser 端口: {port2}")
    print(f"分配 Hypium 端口: {port3}")

    # 查看已分配端口
    print(f"\nWinApp 类型已分配端口: {port_mgr.list_allocated_ports('winapp')}")

    # 端口统计
    stats = port_mgr.stats
    print(f"\n端口统计:")
    print(f"  已分配: {stats['total_allocated']}")
    print(f"  可用: {stats['available']}")
    print(f"  按设备类型: {stats['by_device_type']}")

    # 释放端口
    print("\n--- 释放端口 ---")
    port_mgr.release(port1)
    print(f"已释放端口: {port1}")
    print(f"释放后已分配: {port_mgr.stats['total_allocated']}")


# ==================== 主程序 ====================

def main():
    """运行所有示例"""
    try:
        example_basic_usage()
        example_concurrent_access()
        example_monitoring()
        example_port_manager()

        print("\n" + "=" * 60)
        print("✅ 所有示例运行完成！")
        print("=" * 60)

    finally:
        # 清理：关闭所有连接池
        print("\n清理连接池...")
        get_pool_manager().close_all(force=True)
        print("✅ 所有连接池已关闭")


if __name__ == "__main__":
    main()
