# 官方uv+Python3.12基础镜像，预装uv，体积小构建快
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# 设置工作目录
WORKDIR /app

# 仅安装最小系统依赖，完全移除所有浏览器/Playwright相关依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 配置uv国内镜像源（可选，加速依赖下载）
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# 安装依赖阶段
COPY pyproject.toml README.md ./

COPY --chown=app:app uv.lock* ./

# 如果 lock 文件损坏或不兼容，使用 --no-lockfile 重新生成
RUN if [ -f uv.lock ]; then \
        uv sync --no-dev --no-install-project || (rm uv.lock && uv lock && uv sync --no-dev --no-install-project); \
    else \
        uv sync --no-dev --no-install-project --no-lockfile; \
    fi

# 先安装依赖（不安装项目本身）
RUN uv sync --no-dev --no-install-project

# 优先复制依赖配置，利用Docker分层缓存

# 复制项目源代码
COPY src/ src/
COPY examples ./examples
COPY .env ./

# 安装生产依赖，自动跳过dev依赖，包含fastapi/uvicorn等API服务依赖
RUN uv sync --no-dev 


# 暴露服务端口：8000为HTTP API端口，8765为MCP服务端口
EXPOSE 8000
EXPOSE 8765

# ============== 启动命令检查修正 ==============
# ✅ 你提供的启动命令路径完全正确，适配现有项目结构：
# 项目包路径为`src/pymidscene/`，server入口为`src/pymidscene/server/main.py`中的`app`对象
# 已通过`uv sync`安装了tis-pymidscene包到环境中，可直接通过`pymidscene.server.main:app`导入
CMD ["uv", "run", "uvicorn", "pymidscene.server.main:app", "--host", "0.0.0.0", "--port", "8000"]

# 👉 如果需要切换启动MCP服务，替换为以下命令即可：
# CMD ["uv", "run", "python", "src/device/mcp/server.py", "--mode", "http", "--host", "0.0.0.0", "--port", "8765"]
