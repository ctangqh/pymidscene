from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing import Optional, Dict, Any, List, Tuple, Union, Literal
from enum import Enum

# --- Rect and Position ---
class Rect(BaseModel):
    left: float
    top: float
    width: float
    height: float

class LocateResultElement(BaseModel):
    center: Tuple[float, float]
    rect: Rect
    el_type: str = "element"  # 控件类型
    description: str = ""
    dpr: Optional[float] = None
    element_ref: Optional[Dict[str, Any]] = None
    locator_candidates: List[Dict[str, Any]] = Field(default_factory=list)

# --- Locate Parameters ---
class DetailedLocateParam(BaseModel):
    prompt: Union[str, "MultimodalPrompt"] = ""
    xpath: Optional[str] = None
    deep_locate: bool = False
    cacheable: Optional[bool] = None
    located_pixel_bbox: Optional[List[float]] = None  # [left, top, right, bottom]

class MultimodalPrompt(BaseModel):
    prompt: str
    images: Optional[List[Dict[str, str]]] = None
    convert_http_image2_base64: bool = False

# --- Planning Types ---
class PlanningAction(BaseModel):
    type: str  # 'Tap', 'Input', 'Scroll', 'Locate', 'Finished', etc.
    param: Dict[str, Any] = Field(default_factory=dict)
    thought: str = ""

class PlanningAIResponse(BaseModel):
    actions: List[PlanningAction] = Field(default_factory=list)
    thought: Optional[str] = None
    log: Optional[str] = None
    memory: Optional[str] = None
    error: Optional[str] = None
    usage: Optional["AIUsageInfo"] = None
    raw_response: Optional[str] = None
    reasoning_content: Optional[str] = None
    finalize_success: Optional[bool] = None
    finalize_message: Optional[str] = None
    should_continue_planning: bool = False
    yaml_flow: Optional[List[Dict[str, Any]]] = None
    update_sub_goals: Optional[List[Dict[str, Any]]] = None
    mark_finished_indexes: Optional[List[int]] = None

# --- AI Usage ---
class AIUsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    intent: Optional[str] = None  # 'planning', 'default', 'insight'

# --- UI Context ---
class UIContext(BaseModel):
    screenshot: str = ""  # base64
    shot_size: Dict[str, int] = Field(default_factory=lambda: {"width": 0, "height": 0})
    deprecated_dpr: float = 1.0
    shrunk_shot_to_logical_ratio: float = 1.0
    _is_frozen: bool = False

    model_config = ConfigDict(arbitrary_types_allowed=True)

# --- Execution Task Types ---
class ExecutionTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    ERROR = "error"

class ExecutionTaskTiming(BaseModel):
    start: float = 0
    end: float = 0
    cost: float = 0
    call_ai_start: Optional[float] = None
    call_ai_end: Optional[float] = None
    before_invoke_action_hook_start: Optional[float] = None
    before_invoke_action_hook_end: Optional[float] = None
    call_action_start: Optional[float] = None
    call_action_end: Optional[float] = None
    after_invoke_action_hook_start: Optional[float] = None
    after_invoke_action_hook_end: Optional[float] = None

class ExecutionTask(BaseModel):
    _executor: Optional[Any] = PrivateAttr(default=None)

    task_id: str = ""
    type: str  # 'Planning', 'Action Space', 'Insight', 'Log'
    sub_type: str = ""
    title: Optional[str] = None
    param: Any = None
    thought: Optional[str] = None
    status: ExecutionTaskStatus = ExecutionTaskStatus.PENDING
    timing: ExecutionTaskTiming = Field(default_factory=ExecutionTaskTiming)
    usage: Optional[AIUsageInfo] = None
    log: Optional[Dict[str, Any]] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    error_message: Optional[str] = None
    reasoning_content: Optional[str] = None
    search_area_usage: Optional[Dict[str, Any]] = None
    hit_by: Optional["ExecutionTaskHitBy"] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

class ExecutionTaskHitBy(BaseModel):
    from_: str = Field(alias="from")  # 'Plan', 'Cache', 'User expected path'
    context: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True)

# --- Task Apply Types (for creating tasks) ---
class ExecutionTaskApply(BaseModel):
    _executor: Optional[Any] = PrivateAttr(default=None)

    type: str
    sub_type: str = ""
    title: Optional[str] = None
    param: Any = None
    thought: Optional[str] = None

class ExecutionTaskPlanningApply(ExecutionTaskApply):
    type: str = "Planning"
    # executor is a callable, stored separately

class ExecutionTaskActionApply(ExecutionTaskApply):
    type: str = "Action Space"

class ExecutionTaskInsightQueryApply(ExecutionTaskApply):
    type: str = "Insight"

class ExecutionTaskPlanningLocateApply(ExecutionTaskApply):
    type: str = "Planning"
    sub_type: str = "Locate"

# --- Service Types ---
class ServiceExtractOption(BaseModel):
    dom_included: Union[bool, Literal["visible-only"]] = False
    screenshot_included: bool = True

class ServiceExtractParam(BaseModel):
    # Can be a string demand or structured dict
    demand: Any = None

class ServiceDump(BaseModel):
    task_info: Optional[Dict[str, Any]] = None

class LocateResultWithDump(BaseModel):
    element: Optional[LocateResultElement] = None
    dump: Optional[ServiceDump] = None

# --- Scroll ---
class ScrollParam(BaseModel):
    direction: str = "down"  # up, down, left, right
    scroll_type: str = "singleAction"  # singleAction, scrollToBottom, scrollToTop, etc.
    distance: Optional[int] = None

# --- Cache ---
class ElementCacheFeature(BaseModel):
    xpaths: Optional[List[str]] = None
    # Could have other cache features in the future

class CacheConfig(BaseModel):
    id: str
    strategy: Literal["read-only", "read-write", "write-only"] = "read-write"
    cache_dir: Optional[str] = None

class CacheFileContent(BaseModel):
    midscene_version: str = ""
    cache_id: str = ""
    caches: List[Union["PlanningCache", "LocateCache"]] = Field(default_factory=list)

class PlanningCache(BaseModel):
    type: Literal["plan"] = "plan"
    prompt: Any = ""  # Union[str, MultimodalPrompt]
    yaml_workflow: str = ""

class LocateCache(BaseModel):
    type: Literal["locate"] = "locate"
    prompt: Any = ""  # Union[str, MultimodalPrompt]
    cache: Optional[ElementCacheFeature] = None

# --- Agent Options ---
class AgentOpt(BaseModel):
    generate_report: bool = True
    persist_execution_dump: bool = False
    auto_print_report_msg: bool = True
    group_name: str = "Midscene Report"
    group_description: str = ""
    llm_model_config: Optional[Dict[str, Any]] = None
    cache: Optional[CacheConfig] = None
    cache_id: Optional[str] = None
    replanning_cycle_limit: Optional[int] = None
    wait_after_action: Optional[int] = None
    use_device_time: bool = False
    report_file_name: Optional[str] = None
    report_attributes: Optional[Dict[str, Any]] = None
    output_format: Optional[str] = None
    on_task_start_tip: Optional[Any] = None
    ai_act_context: Optional[str] = None
    ai_action_context: Optional[str] = None
    screenshot_shrink_factor: float = 1.0
    visual_debug: bool = False  # 是否保存带标记的调试截图

    model_config = ConfigDict(arbitrary_types_allowed=True)

class AiActOptions(BaseModel):
    cacheable: Optional[bool] = None
    file_chooser_accept: Optional[Union[str, List[str]]] = None
    deep_think: Optional[bool] = None
    deep_locate: Optional[bool] = None
    abort_signal: Optional[Any] = None

# --- Report Types ---
class ReportMeta(BaseModel):
    group_name: str = ""
    group_description: str = ""
    sdk_version: str = ""
    model_briefs: List[Dict[str, Any]] = Field(default_factory=list)
    device_type: str = ""

class ExecutionDump(BaseModel):
    id: str = ""
    log_time: float = 0
    name: str = ""
    description: str = ""
    tasks: List[Dict[str, Any]] = Field(default_factory=list)

class ReportActionDump(BaseModel):
    sdk_version: str = ""
    group_name: str = ""
    group_description: str = ""
    executions: List[Dict[str, Any]] = Field(default_factory=list)
    model_briefs: List[Dict[str, Any]] = Field(default_factory=list)
    device_type: str = ""

# --- Device Action ---
class DeviceActionParamSchema(BaseModel):
    """Schema definition for a device action's parameters"""
    type: str = "object"
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)

class DeviceAction(BaseModel):
    name: str
    description: str = ""
    param_schema: Optional[DeviceActionParamSchema] = None
    delay_before_runner: int = 200
    delay_after_runner: Optional[int] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)
