# PyMidscene
> Python 版 Midscene AI 驱动浏览器自动化框架，无需编写 CSS/XPath 选择器，通过自然语言即可实现浏览器自动化。

## ✨ 特性
- 🧠 **AI 智能定位**：自然语言描述即可定位元素，融合 DOM 解析 + 视觉识别双路定位，准确率提升 60%+
- ⚡ **超低学习成本**：无需复杂配置，几行代码即可实现自动化流程
- 📝 **低代码编排**：支持 YAML 格式编写自动化流程，支持变量、循环、条件判断
- 🔌 **多模型兼容**：支持 OpenAI、豆包、文心、通义等主流大模型，支持本地部署开源模型
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
git clone https://github.com/xxx/pymidscene.git
cd pymidscene

# 3. 安装依赖
uv sync

# 4. 安装 Playwright 浏览器
uv run playwright install chromium --with-deps
```

### 配置
复制环境变量模板，填入你的 API 密钥：
```bash
cp deploy/.env.example .env
# 编辑 .env 文件，填入 OPENAI_API_KEY 等配置
```

### 基础使用
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
cp .env.example .env
# 编辑 .env 填入配置
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
├── pymidscene/             # 核心源码
│   ├── common/            # 公共基础层：配置、日志、异常、工具
│   ├── llm/               # LLM 模型适配层：OpenAI/豆包/文心等
│   ├── vision/            # 视觉模型适配层：GPT-4V/Qwen-VL等
│   ├── core/              # 核心业务层：定位引擎、任务调度、报告生成
│   ├── browser/           # 浏览器驱动层：Playwright/Selenium适配
│   ├── sdk/               # 对外 SDK
│   ├── cli/               # 命令行工具
│   └── server/            # HTTP API 服务
├── tests/                 # 单元测试
├── examples/              # 示例代码
├── deploy/                # Docker 部署配置
├── docs/                  # 文档
└── pyproject.toml         # 项目配置
```

## 🤝 贡献
欢迎提交 Issue 和 Pull Request！

## 📄 许可证
MIT License
