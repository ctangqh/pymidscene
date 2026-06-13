"""
UITree 子包入口与使用说明。

该子包负责把不同设备返回的原始页面结构数据统一解析为 `UIElement` 树，
并提供调试落盘能力，供 `locator`、`agent` 或其他核心模块复用。

对外推荐只从本模块导入，不要直接依赖内部文件结构。这样后续即使 adapter、
dump、registry 等模块继续重构，调用方的导入方式也可以保持稳定。

推荐导入方式
------------

最常见的调用方式：

```python
from core.uitree import uitree_manager
```

如果需要直接使用统一模型：

```python
from core.uitree import UIElement
```

如果需要在 debug 模式下抓取并保存 UI tree：

```python
from core.uitree import capture_debug_tree
```

核心导出
--------

- `UIElement`
  统一节点模型。不同设备解析完成后，最终都会落到该结构。

- `Bounds`
  统一边界框类型，格式为 `(left, top, width, height)`。

- `UITreeManager`
  UITree 统一服务入口，适合在需要自定义实例时使用。

- `uitree_manager`
  默认单例实例。大部分场景直接使用它即可。

- `capture_debug_tree`
  面向调试链路的辅助函数。会在 `settings.DEBUG` 开启时抓取并保存原始/解析后 UI tree。

- `UITREE_SCHEMA_VERSION`
  当前 UITree 调试文件与完整树结构所对应的 schema 版本。

常见使用场景
------------

1. 解析设备返回的原始 UI tree

```python
from core.uitree import uitree_manager

raw_tree = device.get_dom_tree()
device_type = getattr(device, "interface_type", None)
tree = uitree_manager.parse(raw_tree, device_type)

if tree:
    flat_nodes = tree.to_flat_list()
```

适用场景：

- `locator` 做原生树定位
- 其他模块需要从 UI tree 中读取结构信息
- 调试时查看统一后的节点结构

2. 直接从 UI tree 中找最匹配节点

```python
from core.uitree import uitree_manager

best_node = uitree_manager.find_best_match(
    raw_data=device.get_dom_tree(),
    element_description="确定按钮",
    device_type=getattr(device, "interface_type", None),
)

if best_node and best_node.bounds:
    left, top, width, height = best_node.bounds
```

适用场景：

- 需要快速从原生树中找候选节点
- 不希望在调用方重复写打分或遍历逻辑

3. 保存调试产物

```python
from core.uitree import uitree_manager

result = uitree_manager.save(
    raw_data=device.get_dom_tree(),
    element_description="登录按钮",
    device_type=getattr(device, "interface_type", None),
)

raw_path = result["raw"]
parsed_path = result["parsed"]
```

输出内容：

- 原始设备返回的 UI tree
- 统一解析后的平铺节点列表

适用场景：

- 失败排查
- 报告留档
- 线下对比不同设备返回差异

4. 在 agent / locator 调试链路中无侵入抓取

```python
from core.uitree import capture_debug_tree

capture_debug_tree(
    device=device,
    element_description="设置按钮",
    device_type=getattr(device, "interface_type", None),
    screenshot_path=raw_screenshot_path,
)
```

特点：

- 仅在 `settings.DEBUG` 为 `True` 时真正落盘
- 内部兜底，不把调试失败向外抛出
- 适合 `agent`、`task_builder`、`locator` 这类核心链路
- 如果传入 `screenshot_path`，会优先与该截图做严格同 basename 绑定

对调用方的建议
--------------

1. 优先使用 `uitree_manager`

除非你明确需要注入自定义 adapter 列表，否则默认应优先使用：

```python
from core.uitree import uitree_manager
```

这能保证全项目使用一致的适配器顺序与解析行为。

2. 调用时始终传入 `device_type`

建议统一传：

```python
device_type = getattr(device, "interface_type", None)
```

因为不同 adapter 的选择会依赖该字段；显式传入能减少误判。

3. 调用方只依赖统一模型，不依赖底层字段名

推荐使用：

- `node.name`
- `node.tag`
- `node.control_type`
- `node.automation_id`
- `node.class_name`
- `node.bounds`
- `node.path`
- `node.depth`

不建议在上层逻辑中直接依赖各平台原始字段名，例如：

- `AutomationId`
- `XCUIElementType`
- `@type`
- `LocalizedControlType`

这些差异应尽量由 adapter 层吸收。

4. 调试保存不要阻断主链路

如果在核心业务链路里需要保存 UITree，优先用：

```python
capture_debug_tree(...)
```

而不是自己额外包一层复杂异常处理，因为该函数本身就是为“失败不影响主流程”设计的。

调试文件格式说明
----------------

当前 UITree 调试输出统一为两类 JSON 文件：

- `<screenshot_name>.json`
- `<screenshot_name>_raw.json`

命名规则：

- 如果当前 `report/**/screenshots` 目录中存在最近生成的截图文件，`parsed` 结果会直接复用该截图文件名，只把后缀改成 `.json`
- 同一次保存的 `raw` 结果会使用同样的 basename，并追加 `_raw.json`
- 如果调用方显式传入 `screenshot_path`，则优先使用该路径的 basename，而不是推断最近截图
- 如果当前没有可对齐的截图文件，则回退到时间戳前缀命名

### 1. `<screenshot_name>_raw.json`

该文件保存“归一化后的原始树结构”。

设计目标：

- 保留设备返回的结构信息
- 去掉调用协议外壳
- 不再直接混入 XML 字符串
- 保证后续模块拿到的是 JSON 结构

当前结构示意：

```json
{
  "schema_version": "1.0.0",
  "description": "文本编辑区域",
  "device_type": "windows",
  "source_data_type": "dict",
  "payload": {
    "tag": "Window",
    "attributes": {
      "Name": "MainWindow",
      "AutomationId": "root"
    },
    "children": [
      {
        "tag": "Edit",
        "attributes": {
          "Name": "文本编辑区域"
        },
        "children": []
      }
    ]
  }
}
```

字段说明：

- `schema_version`
  当前调试文件使用的 schema 版本。后续如果结构演进，应优先通过该字段做兼容判断

- `description`
  触发这次抓取时的元素描述

- `device_type`
  当前设备类型，例如 `windows`、`browser`、`ios`、`hypium`

- `source_data_type`
  原始输入的 Python 类型名，例如 `dict`、`str`

- `payload`
  已归一化后的结构化树数据

注意：

- 如果设备原始返回是 XML，`payload` 中会变成 JSON 结构
- 如果设备原始返回是 JSON 字符串，也会先解析再落盘
- 常见包装壳如 `content`、`xml`、`value`、`source` 会被自动剥离

### 2. `<screenshot_name>.json`

该文件保存“统一领域模型后的结果”，用于后续模块直接消费。

设计目标：

- 提供稳定的统一结构
- 同时兼顾树形查看和节点平铺遍历
- 方便定位、调试、统计和二次分析

当前结构示意：

```json
{
  "schema_version": "1.0.0",
  "description": "文本编辑区域",
  "device_type": "windows",
  "nodes_count": 2,
  "tree": {
    "name": "MainWindow",
    "tag": "Window",
    "control_type": "Window",
    "automation_id": "root",
    "class_name": "",
    "bounds": [0.0, 0.0, 400.0, 800.0],
    "path": ["MainWindow"],
    "depth": 0,
    "attributes": {
      "Name": "MainWindow",
      "AutomationId": "root"
    },
    "children": [
      {
        "name": "文本编辑区域",
        "tag": "Edit",
        "control_type": "Edit",
        "automation_id": "",
        "class_name": "",
        "bounds": [10.0, 20.0, 200.0, 40.0],
        "path": ["MainWindow", "文本编辑区域"],
        "depth": 1,
        "attributes": {
          "Name": "文本编辑区域"
        },
        "children": []
      }
    ]
  },
  "nodes": [
    {
      "name": "MainWindow",
      "tag": "Window",
      "control_type": "Window",
      "automation_id": "root",
      "class_name": "",
      "path": ["MainWindow"],
      "depth": 0,
      "bounds": [0.0, 0.0, 400.0, 800.0]
    },
    {
      "name": "文本编辑区域",
      "tag": "Edit",
      "control_type": "Edit",
      "automation_id": "",
      "class_name": "",
      "path": ["MainWindow", "文本编辑区域"],
      "depth": 1,
      "bounds": [10.0, 20.0, 200.0, 40.0]
    }
  ]
}
```

字段说明：

- `schema_version`
  当前解析结果文件的 schema 版本

- `description`
  当前抓取对应的元素描述

- `device_type`
  当前设备类型

- `nodes_count`
  平铺节点总数

- `tree`
  完整统一树结构，对应 `UIElement.to_dict()`

- `nodes`
  平铺后的节点列表，适合快速检索和统计

对后续模块的建议：

- 如果你需要完整父子关系，用 `tree`
- 如果你需要快速筛选、遍历、查找候选节点，用 `nodes`
- 如果你需要稳定消费调试数据，优先读取 `parsed_debug.json`

### 推荐读取策略

如果其他模块要读取调试产物，建议优先级如下：

1. 优先读取与截图同名的 `.json`
2. 仅在需要分析设备原始返回差异时，再读取同 basename 的 `_raw.json`

原因是：

- `parsed` 文件结构更稳定
- `raw` 文件仍然保留设备差异
- 上层业务更适合依赖统一结构而不是底层差异

与其他模块的推荐衔接方式
------------------------

与 `locator` 的衔接：

- `locator` 应优先通过 `uitree_manager.parse()` 或 `find_best_match()` 获取统一节点
- 定位逻辑只围绕 `UIElement` 工作，不直接解析设备原始 payload

与 `agent` / `task_builder` 的衔接：

- 调试场景下优先调用 `capture_debug_tree()`
- 不建议在 agent 规划层直接依赖具体 adapter

与 `device` 的衔接：

- 输入统一来自 `device.get_dom_tree()`
- 设备类型统一来自 `device.interface_type`

边界说明
--------

本模块当前负责：

- 跨设备 UI tree 解析
- 统一节点模型
- 调试落盘
- 原生树上的轻量匹配能力

本模块当前不负责：

- 视觉定位
- LLM 决策
- 设备点击/输入执行
- 高层动作规划

如果以后其他模块需要接入 UITree，请优先把这里当成唯一入口使用。
"""
from .debug import capture_debug_tree
from .dump import UITREE_SCHEMA_VERSION
from .models import Bounds, UIElement
from .service import UITreeManager, uitree_manager

__all__ = [
    "Bounds",
    "UIElement",
    "UITreeManager",
    "UITREE_SCHEMA_VERSION",
    "capture_debug_tree",
    "uitree_manager",
]
