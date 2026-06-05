# 基础镜像使用Python3.11 slim，体积小包含完整Python环境
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 安装系统依赖：curl、ca-certificates、必要的浏览器依赖（供Playwright使用）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 复制项目代码到镜像
COPY . /app

# 安装Python依赖
RUN pip install --no-cache-dir -e .

# 暴露MCP服务端HTTP端口
EXPOSE 8765

# 启动命令：默认启动MCP HTTP服务端
CMD ["python", "src/device/mcp/server.py", "--mode", "http", "--host", "0.0.0.0", "--port", "8765"]
