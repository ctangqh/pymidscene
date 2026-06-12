# PyMidscene SDK 文档

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基本使用

```python
from sdk.pymidscene import create_client

# 初始化 SDK
ms = create_client(
    device_provider="mcp_winapp",
    mcp_name="winapp",
    debug=True
)

# 启动设备
ms.launch()

# 打开应用/跳转到页面
ms.goto("notepad.exe", platform_name="Windows", device_name="WindowsPC")

# 操作
ms.ai_input("文本编辑区域", "Hello PyMidscene!")
ms.ai_click("菜单栏的文件按钮")
ms.ai_click("退出菜单")
ms.ai_click("不保存按钮")

# 关闭
ms.close()
```

## API 参考

### 1. create_client

创建 PyMidscene 客户端实例。

**参数：**
- `device_provider`: 设备类型
  - `mcp_winapp`: Windows 桌面应用
  - `mcp_hypium`: HarmonyOS/OpenHarmony
  - `mcp_android`: Android
  - `mcp_ios`: iOS
  - `mcp_playwright`: Playwright 浏览器
  - `browser`: 原生 Playwright 浏览器
- `llm_provider`: LLM 提供方（如 `openai`, `deepseek`）
- `vision_provider`: 视觉模型提供方（如 `openai`, `deepseek`）
- `mcp_name`: MCP 服务器配置名称
- `mcp_server_url`: 可选，覆盖配置中的 MCP 服务器地址
- `debug`: 是否启用调试模式（打印 bbox 和操作日志）
- `device_options`: 设备特定选项字典
- `llm_options`: LLM 特定选项字典
- `vision_options`: 视觉模型特定选项字典

**返回值：**
- `PyMidscene`: 初始化后的客户端实例

**示例：**

```python
# 最小化配置
ms = create_client(device_provider="mcp_winapp", mcp_name="winapp")

# 完整配置
ms = create_client(
    device_provider="mcp_winapp",
    llm_provider="deepseek",
    vision_provider="deepseek",
    mcp_name="winapp",
    debug=True,
    device_options={"some_param": "value"},
    llm_options={"api_key": "xxx", "base_url": "yyy"},
    vision_options={"api_key": "xxx", "base_url": "yyy"},
)
```

### 2. 设备管理

#### launch()

启动设备。

**示例：**

```python
ms.launch()
```

#### close(**kwargs)

关闭应用（如果是原生设备）并关闭设备。

**参数：**
- `**kwargs`: 设备特定参数

**示例：**

```python
ms.close()
```

### 3. 应用/页面管理

#### goto(target: str, **kwargs)

跳转到指定目标：
- 浏览器设备 → 跳转到 URL
- 原生设备 → 启动应用

**参数：**
- `target`: URL 或应用路径/标识符
- `**kwargs`: 设备特定参数

**返回值：**
- 操作结果

**示例：**

```python
# Windows 原生应用
ms.goto(
    "notepad.exe",
    platform_name="Windows",
    device_name="WindowsPC"
)

# 浏览器
ms.goto("https://www.example.com")
```

### 4. AI 操作

#### ai_click(element_description: str, **kwargs) / ai_tap(element_description: str, **kwargs)

通过自然语言描述点击元素。

**参数：**
- `element_description`: 元素描述
- `**kwargs`: 其他参数

**示例：**

```python
ms.ai_click("蓝色的提交按钮")
```

#### ai_input(element_description: str, text: str, **kwargs)

通过自然语言描述输入文本。

**参数：**
- `element_description`: 元素描述
- `text`: 要输入的文本
- `**kwargs`: 其他参数

**示例：**

```python
ms.ai_input("邮箱输入框", "user@example.com")
```

#### ai_extract(extract_description: str, **kwargs) / ai_query(extract_description: str, **kwargs)

提取页面信息。

**参数：**
- `extract_description`: 提取信息的描述
- `**kwargs`: 其他参数

**返回值：**
- 提取结果

**示例：**

```python
result = ms.ai_extract("提取页面的标题")
print(result)
```

#### ai_act(task_prompt: str, **kwargs)

自主规划并执行任务。

**参数：**
- `task_prompt`: 任务描述
- `**kwargs`: 其他参数

**返回值：**
- 任务执行结果

**示例：**

```python
result = ms.ai_act("在电商网站搜索'笔记本电脑'并按价格排序")
print(result)
```

#### ai_assert(assertion: str, msg: Optional[str] = None, **kwargs)

断言页面状态。

**参数：**
- `assertion`: 断言描述
- `msg`: 可选错误提示
- `**kwargs`: 其他参数

**示例：**

```python
ms.ai_assert("按钮显示为'已提交'")
```

#### ai_wait_for(assertion: str, **kwargs)

等待断言成立。

**参数：**
- `assertion`: 等待断言
- `**kwargs`: 其他参数

**示例：**

```python
ms.ai_wait_for("页面加载完成，显示商品列表")
```

#### ai_locate(prompt: str, **kwargs)

定位元素。

**参数：**
- `prompt`: 元素描述
- `**kwargs`: 其他参数

**返回值：**
- 定位结果

**示例：**

```python
position = ms.ai_locate("红色的按钮")
print(position)
```

#### screenshot(filename: Optional[str] = None, **kwargs)

截图。

**参数：**
- `filename`: 文件名（可选，如 "my_screenshot.png"），不指定则自动生成
  - 如果是绝对路径，直接使用
  - 如果是相对路径，保存到配置中的 `REPORT_SCREENSHOT_SAVE_DIR`（默认 `./output/screenshots`）
- `**kwargs`: 其他参数

**返回值：**
- 截图字节

**示例：**

```python
# 自动生成文件名
ms.screenshot()

# 指定文件名
ms.screenshot("my_screenshot.png")

# 指定绝对路径
ms.screenshot("/path/to/screenshot.png")
```

#### keyboard_press(key_name: str, **kwargs)

按下快捷键。

**参数：**
- `key_name`: 按键名称
- `**kwargs`: 其他参数

**返回值：**
- 操作结果

**示例：**

```python
ms.keyboard_press("enter")
```

#### run_yaml(yaml_path: str, **kwargs)

运行 YAML 自动化流程。

**参数：**
- `yaml_path`: YAML 文件路径
- `**kwargs`: 其他参数

**返回值：**
- 流程执行结果

**示例：**

```python
result = ms.run_yaml("examples/search_demo.yaml")
print(result)
```

### 5. 调试模式

启用调试模式（`debug=True`）后，SDK 会：
- 打印操作的详细日志
- 打印元素定位的 bbox（边界框）坐标
- 保存带有 bbox 标注的调试截图（到 `output/visual_debug` 目录）

**示例：**

```python
ms = create_client(device_provider="mcp_winapp", mcp_name="winapp", debug=True)
ms.launch()
ms.goto("notepad.exe", ...)
ms.ai_input("文本编辑区域", "调试测试")
```

## 配置

### MCP 服务器配置

在 `config/mcp-servers.example.yaml` 中定义 MCP 服务器配置，复制为 `config/mcp-servers.yaml` 并修改。

### LLM 配置

在 `.env` 文件中配置 LLM API 信息：

```env
LLM_PROVIDER=deepseek
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat

VISION_PROVIDER=deepseek
VISION_API_KEY=your_api_key
VISION_BASE_URL=https://api.deepseek.com/v1
VISION_MODEL=deepseek-vl
```

## 支持的设备

| 设备类型 | device_provider | 说明 |
|---------|----------------|------|
| Windows 桌面应用 | mcp_winapp | 基于 WinAppDriver |
| Android 应用 | mcp_android | 基于 Appium/Hypium |
| iOS 应用 | mcp_ios | 基于 Appium/Hypium |
| HarmonyOS/OpenHarmony | mcp_hypium | 基于 Hypium |
| 浏览器 | mcp_playwright / browser | 基于 Playwright |

## 示例代码

完整示例代码见 `examples/` 目录。

## 常见问题

### 如何启动 MCP 服务器？

```bash
# 进入 MCP 服务器目录
cd mcp_servers/winapp

# 启动服务器
python server.py
```

### 调试模式下的截图保存在哪里？

默认保存在 `output/visual_debug` 目录。

### 如何查看定位日志？

设置 `debug=True` 即可在控制台看到详细定位日志，包括 bbox 坐标和操作步骤。

