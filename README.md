# PyMidscene
> Python 版 Midscene AI 驱动浏览器自动化框架，无需编写 CSS/XPath 选择器，通过自然语言即可实现浏览器自动化。

## ✨ 特性
- 🧠 **AI 智能定位**：自然语言描述即可定位元素，融合 DOM 解析 + 视觉识别双路定位，准确率提升 60%+
- ⚡ **超低学习成本**：无需复杂配置，几行代码即可实现自动化流程
- 📝 **低代码编排**：支持 YAML 格式编写自动化流程，支持变量、循环、条件判断
- 🔌 **多模型兼容**：支持 OpenAI、豆包、文心、通义等主流大模型，支持本地部署开源模型
- 🔗 **MCP 远程浏览器支持**：原生兼容 MCP 协议，支持调用远程 Playwright MCP 服务，无需本地安装浏览器
- 📊 **可视化报告**：自动生成包含操作录屏、截图、执行日志的可视化报告
- 🐳 **Docker 一键部署**：支持开发/测试/生产多场景部署，开箱即用
- 🚀 **高性能**：基于 uv 依赖管理，Playwright 驱动，执行速度比同类方案提升 30%+

## 🚀 快速开始
### 环境要求
- Python >= 3.10
- uv (可选，推荐，依赖安装速度提升 10 倍)

### 安装
```bash
# 1. 安装 uv（仅需一次）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆项目
git clone https://github.com/ctangqh/pymidscene.git
cd pymidscene

# 3. 安装依赖
uv sync

# 4. 安装 Playwright 浏览器（如果用本地浏览器模式）
uv run playwright install chromium --with-deps
```

### 配置
复制环境变量模板，并准备运行配置文件：
```bash
copy .env.sample .env
# 编辑 .env，填入 LLM_API_KEY / LLM_BASE_URL 等敏感配置
# 编辑 app.yaml，填写模型标识、设备参数、报告目录、MCP 地址等运行配置
```

`.env` 与 `app.yaml` 的职责划分如下：

- `.env`：保存 API Key、模型接口地址、MCP 认证密钥等敏感信息
- `app.yaml`：保存模型标识、设备参数、报告路径、MCP 服务地址等非敏感运行配置
- 多个 MCP 共用同一个认证密钥时，可配置 `MCP_API_KEY`
- 某个 MCP 需要单独认证时，可配置对应的 `MCP_<NAME>_API_KEY`，例如 `MCP_WINAPP_API_KEY`

### 基础使用（本地浏览器模式）
```python
from pymidscene import create_client

with create_client() as client:
    # 跳转到百度
    client.goto("https://www.baidu.com")
    
    # 输入搜索词
    client.input("搜索输入框", "PyMidscene AI 自动化")
    
    # 点击搜索按钮
    client.click("搜索按钮")
    
    # 提取搜索结果
    results = client.extract("提取前5条搜索结果的标题和链接")
    
    print("搜索结果：", results)
```

### 远程 MCP 浏览器模式
无需本地安装浏览器，直接调用远程 MCP Playwright 服务：
```python
from device.mcp.client import McpPlaywrightDevice

device = McpPlaywrightDevice(
    mcp_server_url="http://your-mcp-server:8000/mcp",
    viewport_width=1280,
    viewport_height=720,
    headless=True
)

with device:
    device.goto("https://www.baidu.com")
    title = device.evaluate_script("document.title")
    print(f"页面标题：{title}")
    device.screenshot(save_path="./baidu.png")
```

### 截图命名规则
使用 SDK 的 `ms.screenshot()` 时，截图默认保存在当前 report 对应的 `screenshots/` 目录。

```python
# 指定文件名时，按给定名称保存
ms.screenshot("02_text_entered.png")

# 不指定文件名时，自动生成 screenshot_<timestamp>.png
ms.screenshot()
```

如果当前没有 report 上下文，则会回退到默认截图目录：

- `REPORT_SAVE_DIR/screenshots`
- 默认路径通常是 `output/reports/screenshots`

report 自动记录链路的命名规则与此保持一致：

- 如果传入业务文件名，优先保留该名称写入 `report/**/screenshots/`
- 如果同名但图片内容不同，自动补后缀，例如 `same_name.png`、`same_name_2.png`
- 如果没有业务文件名，则回退到系统生成的稳定名称

### 运行 YAML 流程
```yaml
# search_demo.yaml
name: 百度搜索
steps:
  - action: goto
    params:
      url: https://www.baidu.com
  - action: input
    params:
      element: 搜索输入框
      text: PyMidscene
  - action: click
    params:
      element: 搜索按钮
  - action: extract
    params:
      description: 提取前5条搜索结果
```

```python
client.run_yaml("search_demo.yaml")
```

## 🐳 Docker 部署
### 开发环境
```bash
cd deploy
copy ..\.env.sample ..\.env
# 编辑 ..\.env 与 ..\app.yaml 填入配置
docker compose -f docker-compose.dev.yml up -d

# 进入容器开发
docker compose -f docker-compose.dev.yml exec pymidscene-dev bash
```

### 运行测试
```bash
docker compose -f docker-compose.test.yml run --rm pymidscene-test tests/
```

### 生产部署
```bash
docker build --target prod -t pymidscene:latest .
docker run -d -p 8000:8000 --env-file .env pymidscene:latest
```

## 📁 项目结构
```
pymidscene/
├── src/                     # 核心源码
│   ├── common/             # 公共基础层：配置、日志、异常、工具类
│   ├── llm/                # LLM 模型适配层：OpenAI/豆包/文心等主流模型支持
│   ├── core/               # 核心业务层：定位引擎、任务调度、报告生成
│   ├── device/             # 设备驱动层
│   │   ├── browser/        # 本地浏览器驱动：Playwright 适配
│   │   └── mcp/            # MCP 远程设备驱动：MCP 协议适配，支持远程 Playwright/移动端/桌面端
│   ├── sdk/                # 对外 SDK 封装
│   ├── cli/                # 命令行工具
│   └── server/             # HTTP API 服务层
├── tests/                  # 单元测试用例
├── examples/               # 示例代码
├── deploy/                 # Docker 部署配置
├── pyproject.toml          # 项目配置、依赖管理
└── README.md               # 项目说明文档
```

## Prompt 约定
- 面向模型的系统提示和输出格式约束统一使用英文。
- 用户输入、业务描述和页面真实文案保持原文，不做自动翻译。
- 编写定位或提取描述时，优先直接引用页面上实际可见的文字。

## 🤝 贡献
欢迎提交 Issue 和 Pull Request！

## 📄 许可证
MIT License
