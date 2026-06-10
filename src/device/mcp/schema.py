"""MCP模块常量与通用Schema定义"""
# 支持的MCP工具名称列表
MCP_TOOL_NAMES = [
    "ai_goto", "ai_click", "ai_input", "ai_extract", "ai_assert",
    "ai_screenshot", "ai_scroll", "ai_wait_for", "ai_close"
]

# 原生端源码/节点树工具名称约定
NATIVE_SOURCE_TOOL_NAMES = [
    "winapp_get_source",
    "hypium_get_source",
    "android_get_source",
    "ios_get_source",
]

# 标准Playwright MCP工具Schema（兼容Claude官方Playwright MCP格式）
STANDARD_PLAYWRIGHT_MCP_SCHEMA = {
    "playwright_create_context": {
        "type": "object",
        "properties": {
            "viewport": {"type": "object", "properties": {"width": {"type": "integer"}, "height": {"type": "integer"}}},
            "headless": {"type": "boolean"},
            "user_agent": {"type": "string"}
        }
    },
    "playwright_new_page": {
        "type": "object",
        "properties": {"context_id": {"type": "string"}}
    },
    "playwright_goto": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "url": {"type": "string"}, "timeout": {"type": "integer"}}
    },
    "playwright_click": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "selector": {"type": "string"}, "position": {"type": "object"}, "timeout": {"type": "integer"}}
    },
    "playwright_fill": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "selector": {"type": "string"}, "position": {"type": "object"}, "text": {"type": "string"}, "clear_before": {"type": "boolean"}, "timeout": {"type": "integer"}}
    },
    "playwright_screenshot": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "full_page": {"type": "boolean"}, "encoding": {"type": "string"}}
    },
    "playwright_scroll": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "direction": {"type": "string"}, "distance": {"type": "integer"}}
    },
    "playwright_wait_for_selector": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "selector": {"type": "string"}, "timeout": {"type": "integer"}}
    },
    "playwright_evaluate": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}, "script": {"type": "string"}, "args": {"type": "array"}}
    },
    "playwright_get_page_content": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}}
    },
    "playwright_get_dom_tree": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}}
    },
    "playwright_close_page": {
        "type": "object",
        "properties": {"page_id": {"type": "string"}}
    },
    "playwright_close_context": {
        "type": "object",
        "properties": {"context_id": {"type": "string"}}
    }
}

# 标准原生端源码/节点树工具 Schema。
# 约定这些工具返回 XML / JSON 文本形式的页面结构，供 SDK 的
# get_page_content()/get_dom_tree() 与原生树回退定位逻辑复用。
STANDARD_NATIVE_SOURCE_MCP_SCHEMA = {
    "winapp_get_source": {
        "type": "object",
        "properties": {}
    },
    "hypium_get_source": {
        "type": "object",
        "properties": {}
    },
    "android_get_source": {
        "type": "object",
        "properties": {}
    },
    "ios_get_source": {
        "type": "object",
        "properties": {}
    },
}
