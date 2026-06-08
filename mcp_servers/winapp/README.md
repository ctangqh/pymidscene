# WinAppDriver MCP Server

基于 WinAppDriver 的 Windows 桌面应用自动化 MCP 服务器，支持 x86 / x64 / ARM64 全平台。

---

## 快速开始

### 1. 前置要求

- Windows 10 / Windows 11
- 已安装 [WinAppDriver](https://github.com/microsoft/WinAppDriver/releases)（v1.2.1+）
- Windows 已开启**开发者模式**（设置 → 隐私和安全性 → 开发者选项）

### 2. 启动服务

**最简单的方式：双击 `start.bat`**

脚本会自动：
- ✓ 检测系统架构（x86/x64/ARM64）
- ✓ 选择对应 exe 启动
- ✓ 自动复制 `.env.sample` → `.env`
- ✓ 检查管理员权限

或手动启动：
```batch
# x64 系统
winapp-mcp-x64.exe

# ARM64 系统
winapp-mcp-arm64.exe

# x86 系统
winapp-mcp-x86.exe
```

---

## 配置说明

编辑 `.env` 文件可自定义配置：

```env
# WinAppDriver 地址（默认本地，无需修改）
WINAPPDRIVER_HOST=127.0.0.1
WINAPPDRIVER_PORT=4723

# 日志级别
LOG_LEVEL=INFO

# 是否自动启动 WinAppDriver
WINAPPDRIVER_AUTO_START=true
```

---

## 使用示例

### 启动计算器并操作

```typescript
// 1. 创建会话 - 启动计算器
await mcp.callTool("winapp_create_session", {
  app: "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"
});

// 2. 查找数字 "1" 按钮
await mcp.callTool("winapp_find_element", {
  using: "name",
  value: "1"
});

// 3. 点击按钮
await mcp.callTool("winapp_click_element", {
  element_id: "..."
});

// 4. 截图
await mcp.callTool("winapp_get_screenshot");
```

### 启动记事本

```typescript
await mcp.callTool("winapp_create_session", {
  app: "C:\\Windows\\System32\\notepad.exe"
});
```

---

## 元素定位策略

| 策略 | 说明 | 示例 |
|------|------|------|
| `accessibility id` | 推荐，自动化 ID | `winapp_find_element("accessibility id", "num1Button")` |
| `name` | 控件名称 | `winapp_find_element("name", "1")` |
| `class name` | 控件类名 | `winapp_find_element("class name", "Button")` |
| `xpath` | XML 路径 | `winapp_find_element("xpath", "//Button[@Name='1']")` |
| `id` | 元素 ID | `winapp_find_element("id", "...")` |

---

## 工具列表（46 个）

### Session 管理 (5)
- `winapp_create_session` - 创建会话
- `winapp_delete_session` - 关闭会话
- `winapp_get_sessions` - 获取所有会话
- `winapp_get_status` - 获取服务状态
- `winapp_set_timeout` - 设置超时

### 元素操作 (15)
- `winapp_find_element` - 查找单个元素
- `winapp_find_elements` - 查找多个元素
- `winapp_find_element_from_element` - 从父元素内查找
- `winapp_click_element` - 点击元素
- `winapp_clear_element` - 清空元素
- `winapp_send_keys_to_element` - 输入文本
- `winapp_get_element_text` - 获取文本
- `winapp_get_element_attribute` - 获取属性
- `winapp_get_element_name` - 获取标签名
- `winapp_is_element_displayed` - 是否可见
- `winapp_is_element_enabled` - 是否可用
- `winapp_is_element_selected` - 是否选中
- `winapp_get_element_location` - 获取位置
- `winapp_get_element_size` - 获取尺寸
- `winapp_get_element_screenshot` - 元素截图

### 鼠标操作 (6)
- `winapp_mouse_move` - 移动鼠标
- `winapp_mouse_click` - 鼠标点击
- `winapp_mouse_double_click` - 鼠标双击
- `winapp_mouse_button_down` - 按下鼠标键
- `winapp_mouse_button_up` - 释放鼠标键

### 键盘操作 (1)
- `winapp_send_keys` - 发送按键

### 窗口操作 (8)
- `winapp_get_window_handle` - 获取当前窗口句柄
- `winapp_get_window_handles` - 获取所有窗口句柄
- `winapp_set_window_size` - 设置窗口大小
- `winapp_get_window_size` - 获取窗口大小
- `winapp_set_window_position` - 设置窗口位置
- `winapp_get_window_position` - 获取窗口位置
- `winapp_maximize_window` - 最大化窗口
- `winapp_close_window` - 关闭窗口

### 截图 & 源码 (2)
- `winapp_get_screenshot` - 全屏截图（base64）
- `winapp_get_page_source` - 获取 XML 源码

### 导航 (2)
- `winapp_navigate_back` - 后退
- `winapp_navigate_forward` - 前进

### 触摸操作 (8)
- `winapp_touch_click` - 触摸点击
- `winapp_touch_double_click` - 触摸双击
- `winapp_touch_long_click` - 触摸长按
- `winapp_touch_down` - 按下触摸
- `winapp_touch_up` - 释放触摸
- `winapp_touch_move` - 触摸移动（拖拽）
- `winapp_touch_scroll` - 触摸滚动
- `winapp_touch_flick` - 触摸快速滑动

---

## 常见问题

### Q: 启动失败，提示找不到 WinAppDriver？

A: 请先安装 WinAppDriver.msi，默认安装路径：
- `C:\Program Files (x86)\Windows Application Driver\WinAppDriver.exe`
- `C:\Program Files\Windows Application Driver\WinAppDriver.exe`

### Q: 提示需要管理员权限？

A: WinAppDriver 需要管理员权限运行，请**右键 start.bat → 以管理员身份运行**。

### Q: 如何获取 UWP 应用的包名？

A: 在 PowerShell 中执行：
```powershell
Get-AppxPackage *calculator*
```

### Q: 打包后的 exe 有多大？

A: 约 25-30 MB，包含完整 Python 运行时和所有依赖。

---

## 支持的平台

| 平台 | 可执行文件 | 说明 |
|------|-----------|------|
| x64 (AMD64) | `winapp-mcp-x64.exe` | 绝大多数 Windows PC |
| ARM64 | `winapp-mcp-arm64.exe` | Surface Pro X、Windows ARM 平板等 |
| x86 | `winapp-mcp-x86.exe` | 32 位 Windows 系统 |

---

## 技术栈

- **MCP 框架**: `mcp` Python SDK
- **HTTP 客户端**: `httpx`
- **日志**: `loguru`
- **配置**: `pydantic-settings`
- **打包**: `PyInstaller`

---

## 许可证

MIT License
