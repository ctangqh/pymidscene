import time
import asyncio
import uuid
import json
from pathlib import Path
from collections.abc import Iterable
from typing import Optional, List, Dict, Any, Tuple, Union, Callable, TypeVar, Generic

from ..types import (
    AgentOpt, AiActOptions, DetailedLocateParam, LocateResultElement,
    PlanningAction, ServiceExtractOption, ServiceExtractParam,
    ReportActionDump, ExecutionDump, ReportMeta, DeviceAction,
    UIContext, CacheConfig, ElementCacheFeature, Rect,
)
from ..service import Service
from .context_parser import common_context_parser
from .cache_config import validate_agent_cache_input
from .task_cache import TaskCache
from ..report import ReportGenerator, ScreenshotItem
from .action_space import WEB_ACTION_SPACE, define_action_sleep
from .usage_intent import with_usage_intent
from common.logger import logger
from common.exceptions import ActionExecutionError, AssertionError, ElementNotFoundError, MissingAPIKeyError
from common.config import settings
from llm import get_llm

T = TypeVar("T")


def _build_detailed_locate_param(
    locate_prompt: Union[str, Dict, DetailedLocateParam],
    opt: Optional[Dict] = None,
) -> DetailedLocateParam:
    """Build a DetailedLocateParam from various input types"""
    opt = opt or {}
    
    if isinstance(locate_prompt, DetailedLocateParam):
        result = locate_prompt
    elif isinstance(locate_prompt, dict):
        result = DetailedLocateParam(**locate_prompt)
    elif isinstance(locate_prompt, str):
        result = DetailedLocateParam(prompt=locate_prompt)
    else:
        result = DetailedLocateParam(prompt=str(locate_prompt))
    
    # Merge options
    if opt:
        if opt.get("deep_locate") and not result.deep_locate:
            result.deep_locate = True
        if opt.get("cacheable") is not None and result.cacheable is None:
            result.cacheable = opt["cacheable"]
    
    return result


class Agent:
    """
    Main Agent class - the public API for AI-driven automation.
    Port of TS Agent class.
    
    Provides methods for:
    - AI actions: ai_tap, ai_input, ai_scroll, ai_hover, etc.
    - AI planning: ai_act (autonomous planning + execution)
    - AI queries: ai_query, ai_boolean, ai_number, ai_string
    - AI assertions: ai_assert, ai_wait_for
    - AI locate: ai_locate
    - Context management: freeze/unfreeze page context
    - Reporting: record_to_report, dump updates
    - Cache: flush_cache
    """
    
    def __init__(self, device, opts: Optional[Union[AgentOpt, Dict]] = None, llm=None, vision_llm=None):
        """
        Initialize the Agent.
        
        Args:
            device: BaseDevice instance (browser, mobile, etc.)
            opts: Agent configuration options
        """
        if isinstance(opts, dict):
            opts = AgentOpt(**opts)
        self.opts = opts or AgentOpt()
        
        self.device = device
        
        if llm is not None:
            self.llm = llm
        else:
            try:
                self.llm = get_llm()
            except MissingAPIKeyError:
                self.llm = None

        self.vision_llm = vision_llm or self.llm
        
        # Service for AI operations
        self.service = Service(lambda: self.get_ui_context(), llm=self.vision_llm)
        
        # Report dump
        self.dump = self._reset_dump()
        self.report_file: Optional[str] = None
        self.report_file_name: Optional[str] = None
        
        # Dry mode flag
        self.dry_mode = False
        
        # Task start tip callback
        self.on_task_start_tip = self.opts.on_task_start_tip
        
        # Cache
        self.task_cache: Optional[TaskCache] = None
        
        # Dump update listeners
        self._dump_update_listeners: List[Callable] = []
        
        # Frozen UI context
        self._frozen_ui_context: Optional[UIContext] = None
        
        # Destroyed flag
        self.destroyed = False
        
        # Model config
        self.model_config = self.opts.llm_model_config
        
        # Process cache configuration
        cache_config_obj = self._process_cache_config(self.opts)
        if cache_config_obj:
            self.task_cache = TaskCache(
                cache_id=cache_config_obj["id"],
                is_cache_result_used=cache_config_obj["enabled"],
                options={
                    "read_only": cache_config_obj["read_only"],
                    "write_only": cache_config_obj["write_only"],
                    "cache_dir": cache_config_obj.get("cache_dir"),
                },
            )
        
        # Full action space
        base_action_space = device.action_space() if hasattr(device, 'action_space') and callable(device.action_space) else []
        if isinstance(base_action_space, list):
            base_list = base_action_space
        elif isinstance(base_action_space, Iterable):
            base_list = list(base_action_space)
        else:
            base_list = []
        self._full_action_space = base_list + [define_action_sleep()]
        
        # Task executor (lazy init - depends on task_executor.py from Phase 2)
        self.task_executor = None  # Will be initialized when task_executor module is available
        self._init_task_executor()
        
        # Report
        self.report_file_name = (
            self.opts.report_file_name or
            f"{getattr(device, 'interface_type', 'web')}-{time.strftime('%Y-%m-%d_%H-%M-%S')}"
        )
        
        self._report_generator = ReportGenerator.create(
            self.report_file_name,
            {
                "generate_report": self.opts.generate_report,
                "persist_execution_dump": self.opts.persist_execution_dump,
                "output_format": self.opts.output_format,
                "auto_print_report_msg": self.opts.auto_print_report_msg,
            },
        )
        
        # Track tasks that have been visualized to avoid duplicates
        self._visualized_tasks = set()

    def _init_task_executor(self):
        """Initialize the task executor (lazy)"""
        try:
            from .task_executor import TaskExecutor
            self.task_executor = TaskExecutor(
                device=self.device,
                service=self.service,
                opts={
                    "task_cache": self.task_cache,
                    "on_task_start": self._callback_on_task_start_tip,
                    "replanning_cycle_limit": self.opts.replanning_cycle_limit,
                    "wait_after_action": self.opts.wait_after_action,
                    "use_device_time": self.opts.use_device_time,
                    "action_space": self._full_action_space,
                    "hooks": {
                        "on_task_update": self._on_task_update,
                    },
                },
            )
        except ImportError:
            logger.debug("TaskExecutor not yet available, will initialize later")
            self.task_executor = None
    
    async def _on_task_update(self, runner, error=None):
        """Called when a task is updated"""
        try:
            execution_dump = runner.dump() if hasattr(runner, 'dump') else None
            if execution_dump:
                self._append_execution_dump(execution_dump, runner)
                self._write_out_action_dumps(execution_dump)
                await self._report_generator.flush()
                
                # Visual Debug
                if self.opts.visual_debug:
                    await self._handle_visual_debug(execution_dump)
                
                # Notify listeners
                dump_string = self._dump_data_string()
                for listener in self._dump_update_listeners:
                    try:
                        listener(dump_string, execution_dump)
                    except Exception as e:
                        logger.error(f"Error in dump update listener: {e}")
        except Exception as e:
            logger.error(f"Error in task update handler: {e}")
    
    def _callback_on_task_start_tip(self, task):
        """Callback when a task starts"""
        # Format task info
        task_type = getattr(task, 'sub_type', None) or getattr(task, 'type', '')
        param = getattr(task, 'param', None)
        tip = f"{task_type}" + (f" - {param}" if param else "")
        
        if self.on_task_start_tip:
            try:
                if asyncio.iscoroutinefunction(self.on_task_start_tip):
                    asyncio.get_event_loop().run_until_complete(self.on_task_start_tip(tip))
                else:
                    self.on_task_start_tip(tip)
            except Exception as e:
                logger.debug(f"on_task_start_tip callback error: {e}")
    
    # ==================== Visual Debug ====================
    
    async def _handle_visual_debug(self, execution_dump: Dict[str, Any]) -> None:
        """Handle visual debugging by saving annotated screenshots"""
        from common.image import annotate_screenshot, format_box_label, get_screenshot_save_dir
        
        tasks = execution_dump.get("tasks", [])
        for task in tasks:
            task_id = task.get('task_id')
            if not task_id or task_id in self._visualized_tasks:
                continue
                
            status = task.get("status")
            status_val = getattr(status, "value", str(status)).lower()
            
            # We are interested in Finished Locate tasks that have a rect
            if task.get("type") == "Planning" and task.get("sub_type") == "Locate" and status_val == "finished":
                output = task.get("output")
                if output and "element" in output:
                    element = output["element"]
                    # If it's a dict from model_dump()
                    rect = element.get("rect")
                    param = task.get("param", {})
                    prompt = param.get("prompt", "element") if isinstance(param, dict) else "element"
                    
                    if rect:
                        # Add to visualized tasks immediately to avoid race condition
                        self._visualized_tasks.add(task_id)
                        
                        # Get current UI context for screenshot
                        context = await self.get_ui_context()
                        if context and context.screenshot:
                            debug_dir = get_screenshot_save_dir()
                            
                            # 文件名添加 _debug 后缀
                            filename = f"debug_{task_id}_{int(time.time())}_debug.png"
                            output_path = debug_dir / filename
                            
                            # Format label with more info: Type and Coordinates
                            # Try to get el_type from AI result
                            el_type = element.get("el_type") or "element"
                            
                            # Coordinates: left, top, right, bottom
                            if isinstance(rect, dict):
                                left, top = rect.get("left", 0), rect.get("top", 0)
                                width, height = rect.get("width", 0), rect.get("height", 0)
                            else: # Rect object
                                left, top, width, height = rect.left, rect.top, rect.width, rect.height
                                
                            right, bottom = left + width, top + height
                            
                            label = format_box_label(rect, el_type)
                            
                            annotate_screenshot(
                                context.screenshot,
                                [{"rect": rect, "label": label}],
                                str(output_path)
                            )
                            logger.info(f"Visual debug screenshot saved with info: {output_path}")
                        else:
                            logger.debug("No screenshot available for visual debug")

    # ==================== UI Context ====================
    
    async def get_ui_context(self, action: Optional[str] = None) -> UIContext:
        """Get the current UI context (with retry support)"""
        # If context is frozen, return frozen context
        if self._frozen_ui_context:
            logger.debug("Using frozen UI context")
            return self._frozen_ui_context
        
        return await common_context_parser(self.device, {
            "screenshot_shrink_factor": self.opts.screenshot_shrink_factor,
        })
    
    async def freeze_page_context(self) -> None:
        """Freeze the current page context for consistent operations"""
        logger.debug("Freezing page context")
        context = await self.get_ui_context()
        self._frozen_ui_context = context
        logger.debug("Page context frozen")
    
    async def unfreeze_page_context(self) -> None:
        """Unfreeze the page context"""
        logger.debug("Unfreezing page context")
        self._frozen_ui_context = None
        logger.debug("Page context unfrozen")
    
    async def set_ai_act_context(self, prompt: str) -> None:
        """Set the AI action context for subsequent operations"""
        if self.opts.ai_act_context:
            logger.warning("ai_act_context already set, will override")
        self.opts.ai_act_context = prompt
    
    # ==================== AI Actions ====================
    
    async def ai_tap(self, locate_prompt: Union[str, Dict, DetailedLocateParam], opt: Optional[Dict] = None) -> None:
        """Click on an element by description"""
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        await self._call_action_in_action_space("Tap", {"locate": detailed_param.model_dump()})
    
    async def ai_right_click(self, locate_prompt: Union[str, Dict, DetailedLocateParam], opt: Optional[Dict] = None) -> None:
        """Right-click on an element by description"""
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        await self._call_action_in_action_space("RightClick", {"locate": detailed_param.model_dump()})
    
    async def ai_double_click(self, locate_prompt: Union[str, Dict, DetailedLocateParam], opt: Optional[Dict] = None) -> None:
        """Double-click on an element by description"""
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        await self._call_action_in_action_space("DoubleClick", {"locate": detailed_param.model_dump()})
    
    async def ai_hover(self, locate_prompt: Union[str, Dict, DetailedLocateParam], opt: Optional[Dict] = None) -> None:
        """Hover over an element by description"""
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        await self._call_action_in_action_space("Hover", {"locate": detailed_param.model_dump()})
    
    async def ai_input(
        self,
        locate_prompt: Union[str, Dict, DetailedLocateParam],
        opt: Optional[Dict] = None,
    ) -> None:
        """Input text into an element by description"""
        opt = opt or {}
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        value = opt.get("value", "")
        mode = opt.get("mode", "replace")
        # Convert append mode to typeOnly for backward compat
        if mode == "append":
            mode = "typeOnly"
        
        await self._call_action_in_action_space("Input", {
            "locate": detailed_param.model_dump(),
            "value": str(value),
            "mode": mode,
        })
    
    async def ai_keyboard_press(
        self,
        locate_prompt: Optional[Union[str, Dict, DetailedLocateParam]] = None,
        opt: Optional[Dict] = None,
    ) -> None:
        """Press a keyboard key"""
        opt = opt or {}
        key_name = opt.get("key_name")
        if not key_name:
            raise ValueError("key_name is required for keyboard press")
        
        detailed_param = _build_detailed_locate_param(locate_prompt, opt) if locate_prompt else None
        
        params = {"key_name": key_name}
        if detailed_param:
            params["locate"] = detailed_param.model_dump()
        
        await self._call_action_in_action_space("KeyboardPress", params)
    
    async def ai_scroll(
        self,
        locate_prompt: Optional[Union[str, Dict, DetailedLocateParam]] = None,
        opt: Optional[Dict] = None,
    ) -> None:
        """Scroll the page"""
        opt = opt or {}
        detailed_param = _build_detailed_locate_param(locate_prompt or "", opt)
        
        # Normalize legacy scroll types
        scroll_type = opt.get("scroll_type", opt.get("scrollType", "singleAction"))
        legacy_map = {
            "once": "singleAction",
            "untilBottom": "scrollToBottom",
            "untilTop": "scrollToTop",
            "untilRight": "scrollToRight",
            "untilLeft": "scrollToLeft",
        }
        scroll_type = legacy_map.get(scroll_type, scroll_type)
        
        await self._call_action_in_action_space("Scroll", {
            **opt,
            "locate": detailed_param.model_dump(),
            "scroll_type": scroll_type,
        })
    
    async def ai_long_press(
        self,
        locate_prompt: Union[str, Dict, DetailedLocateParam],
        opt: Optional[Dict] = None,
    ) -> None:
        """Long press on an element"""
        opt = opt or {}
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        params = {"locate": detailed_param.model_dump()}
        if opt.get("duration"):
            params["duration"] = opt["duration"]
        await self._call_action_in_action_space("LongPress", params)
    
    async def ai_clear_input(
        self,
        locate_prompt: Union[str, Dict, DetailedLocateParam],
        opt: Optional[Dict] = None,
    ) -> None:
        """Clear the content of an input element"""
        detailed_param = _build_detailed_locate_param(locate_prompt, opt)
        await self._call_action_in_action_space("ClearInput", {"locate": detailed_param.model_dump()})
    
    async def ai_pinch(
        self,
        locate_prompt: Optional[Union[str, Dict, DetailedLocateParam]] = None,
        opt: Optional[Dict] = None,
    ) -> None:
        """Pinch gesture"""
        opt = opt or {}
        detailed_param = _build_detailed_locate_param(locate_prompt or "", opt)
        await self._call_action_in_action_space("Pinch", {
            **opt,
            "locate": detailed_param.model_dump(),
        })
    
    # ==================== AI Planning ====================
    
    async def ai_act(
        self,
        task_prompt: Union[str, Dict],
        opt: Optional[Union[AiActOptions, Dict]] = None,
    ) -> Optional[str]:
        """
        Execute an AI action with autonomous planning.
        The AI will plan the steps, execute them, and replan if needed.
        """
        if isinstance(opt, dict):
            opt = AiActOptions(**opt)
        opt = opt or AiActOptions()
        
        task_prompt_text = task_prompt if isinstance(task_prompt, str) else task_prompt.get("prompt", "")
        
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available. Ensure task_executor.py is implemented.")
        
        # Check cache first
        cacheable = opt.cacheable
        matched_cache = None
        if self.task_cache and cacheable is not False:
            matched_cache = self.task_cache.match_plan_cache(task_prompt)
            yaml_workflow = getattr(matched_cache.cache_content, "yaml_workflow", "") if matched_cache else ""
            if (matched_cache and matched_cache.cache_usable and 
                self.task_cache.is_cache_result_used and
                yaml_workflow and
                yaml_workflow.strip()):
                logger.debug("Matched plan cache, will use cached flow")
                # For now, fall through to normal execution
                # Full YAML cache replay will be implemented with yaml_runner
        
        # Execute the action
        result = await self.task_executor.action(
            user_prompt=task_prompt,
            include_locate_in_planning=True,
            ai_act_context=self.opts.ai_act_context,
            cacheable=cacheable,
            deep_think=opt.deep_think or False,
            deep_locate=opt.deep_locate,
            file_chooser_accept=(
                [opt.file_chooser_accept] if isinstance(opt.file_chooser_accept, str) 
                else opt.file_chooser_accept
            ),
            abort_signal=opt.abort_signal,
        )
        
        # Update cache if applicable
        if (self.task_cache and result and result.output and 
            isinstance(result.output, dict) and result.output.get("yaml_flow") and
            cacheable is not False):
            try:
                import yaml
                yaml_content = {
                    "tasks": [{
                        "name": task_prompt_text,
                        "flow": result.output["yaml_flow"],
                    }]
                }
                yaml_str = yaml.dump(yaml_content, allow_unicode=True)
                from ..types import PlanningCache
                self.task_cache.update_or_append_cache_record(
                    PlanningCache(type="plan", prompt=task_prompt, yaml_workflow=yaml_str),
                    matched_cache,
                )
            except Exception as e:
                logger.debug(f"Failed to update plan cache: {e}")
        
        output = result.output if result else None
        if isinstance(output, dict):
            return output.get("output")
        return None
    
    # ==================== AI Queries ====================
    
    async def ai_query(self, demand: Any, opt: Optional[ServiceExtractOption] = None) -> Any:
        """Query information from the page"""
        opt = opt or ServiceExtractOption()
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        result = await self.task_executor.create_type_query_execution("Query", demand, opt=opt)
        return result.output
    
    async def ai_boolean(self, prompt: Union[str, Dict], opt: Optional[ServiceExtractOption] = None) -> bool:
        """Ask a yes/no question about the page"""
        opt = opt or ServiceExtractOption()
        text_prompt = prompt if isinstance(prompt, str) else prompt.get("prompt", "")
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        result = await self.task_executor.create_type_query_execution("Boolean", text_prompt, opt=opt)
        return bool(result.output)
    
    async def ai_number(self, prompt: Union[str, Dict], opt: Optional[ServiceExtractOption] = None) -> float:
        """Ask for a number from the page"""
        opt = opt or ServiceExtractOption()
        text_prompt = prompt if isinstance(prompt, str) else prompt.get("prompt", "")
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        result = await self.task_executor.create_type_query_execution("Number", text_prompt, opt=opt)
        return float(result.output) if result.output is not None else 0
    
    async def ai_string(self, prompt: Union[str, Dict], opt: Optional[ServiceExtractOption] = None) -> str:
        """Ask for a string from the page"""
        opt = opt or ServiceExtractOption()
        text_prompt = prompt if isinstance(prompt, str) else prompt.get("prompt", "")
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        result = await self.task_executor.create_type_query_execution("String", text_prompt, opt=opt)
        return str(result.output) if result.output is not None else ""
    
    async def ai_ask(self, prompt: Union[str, Dict], opt: Optional[ServiceExtractOption] = None) -> str:
        """Ask a question about the page (alias for ai_string)"""
        return await self.ai_string(prompt, opt)
    
    # ==================== AI Assertions ====================
    
    async def ai_assert(
        self,
        assertion: Union[str, Dict],
        msg: Optional[str] = None,
        opt: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Assert a condition about the page.
        
        Args:
            assertion: Natural language assertion
            msg: Optional message on failure
            opt: Options including keep_raw_response
        
        Returns:
            If keep_raw_response is True, returns {"pass", "thought", "message"}
            Otherwise, raises on failure
        """
        opt = opt or {}
        service_opt = ServiceExtractOption(
            dom_included=opt.get("dom_included", False),
            screenshot_included=opt.get("screenshot_included", True),
        )
        
        assertion_text = assertion if isinstance(assertion, str) else assertion.get("prompt", "")
        
        try:
            if not self.task_executor:
                raise RuntimeError("TaskExecutor not available")
            result = await self.task_executor.create_type_query_execution(
                "Assert", assertion_text, opt=service_opt
            )
            passed = bool(result.output)
            message = None if passed else f"Assertion failed: {msg or assertion_text}\nReason: {result.thought or '(no_reason)'}"
            
            if opt.get("keep_raw_response"):
                return {"pass": passed, "thought": result.thought, "message": message}
            
            if not passed:
                raise AssertionError(message or f"Assertion failed: {assertion_text}")
            
        except AssertionError:
            raise
        except Exception as e:
            if opt.get("keep_raw_response"):
                return {"pass": False, "thought": str(e), "message": f"Assertion failed: {msg or assertion_text}"}
            raise
    
    async def ai_wait_for(
        self,
        assertion: Union[str, Dict],
        opt: Optional[Dict] = None,
    ) -> None:
        """Wait for an assertion to become true"""
        opt = opt or {}
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        await self.task_executor.wait_for(
            assertion,
            {
                "timeout_ms": opt.get("timeout_ms", 15000),
                "check_interval_ms": opt.get("check_interval_ms", 3000),
                "dom_included": opt.get("dom_included", False),
                "screenshot_included": opt.get("screenshot_included", True),
            },
        )
    
    # ==================== AI Locate ====================
    
    async def ai_locate(
        self,
        prompt: Union[str, Dict, DetailedLocateParam],
        opt: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Locate an element and return its center and rect"""
        locate_param = _build_detailed_locate_param(prompt, opt)
        
        from .task_builder import locate_plan_for_locate
        locate_plan = locate_plan_for_locate(locate_param)
        plans = [locate_plan]
        
        if not self.task_executor:
            raise RuntimeError("TaskExecutor not available")
        
        result = await self.task_executor.run_plans(
            f"Locate - {locate_param.prompt if isinstance(locate_param.prompt, str) else str(locate_param.prompt)}",
            plans,
        )
        
        output = result.output if result else None
        if output and isinstance(output, dict) and output.get("element"):
            element = output["element"]
            return {
                "rect": element.rect if hasattr(element, 'rect') else element.get("rect"),
                "center": element.center if hasattr(element, 'center') else element.get("center"),
            }
        
        return {"rect": None, "center": None}
    
    # ==================== Describe Element ====================
    
    async def describe_element_at_point(
        self,
        center: Tuple[int, int],
        opt: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Describe the element at a given point"""
        opt = opt or {}
        verify_prompt = opt.get("verify_prompt", True)
        retry_limit = opt.get("retry_limit", 3)
        deep_locate = opt.get("deep_locate", False)
        
        result_prompt = ""
        verify_result = None
        
        for retry_count in range(retry_limit):
            if retry_count >= 2:
                deep_locate = True
            
            try:
                text = await self.service.describe(center, opt={"deep_locate": deep_locate})
                result_prompt = text.get("description", "")
                
                if not result_prompt:
                    raise ElementNotFoundError(f"Failed to describe element at {center}")
                
                if not verify_prompt:
                    break
                
                # Verify the description by re-locating
                verify_result = await self._verify_locator(result_prompt, None, center, opt)
                if verify_result.get("pass"):
                    break
                
            except Exception as e:
                if retry_count == retry_limit - 1:
                    raise
        
        return {"prompt": result_prompt, "deep_locate": deep_locate, "verify_result": verify_result}
    
    async def _verify_locator(
        self,
        prompt: str,
        locate_opt: Optional[Dict],
        expect_center: Tuple[int, int],
        verify_locate_option: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Verify a locator by re-locating and checking distance"""
        verify_locate_option = verify_locate_option or {}
        
        try:
            locate_result = await self.ai_locate(prompt, locate_opt)
            verify_center = locate_result.get("center")
            verify_rect = locate_result.get("rect")
            
            if not verify_center:
                return {"pass": False, "reason": "Could not re-locate element"}
            
            # Calculate distance
            distance = round(
                ((expect_center[0] - verify_center[0]) ** 2 + 
                 (expect_center[1] - verify_center[1]) ** 2) ** 0.5
            )
            
            # Check if point is within rect
            included = False
            if verify_rect:
                included = (
                    expect_center[0] >= verify_rect.left and
                    expect_center[0] <= verify_rect.left + verify_rect.width and
                    expect_center[1] >= verify_rect.top and
                    expect_center[1] <= verify_rect.top + verify_rect.height
                )
            
            threshold = verify_locate_option.get("center_distance_threshold", 20)
            passed = distance <= threshold or included
            
            return {
                "pass": passed,
                "rect": verify_rect,
                "center": verify_center,
                "center_distance": distance,
            }
        except Exception as e:
            return {"pass": False, "reason": str(e)}
    
    # ==================== Action Space ====================
    
    async def _call_action_in_action_space(self, action_type: str, opt: Optional[Dict] = None) -> Any:
        """Execute an action through the action space"""
        opt = opt or {}
        logger.debug(f"call_action_in_action_space: {action_type}")
        
        action_plan = PlanningAction(
            type=action_type,
            param=opt or {},
            thought="",
        )
        
        if not self.task_executor:
            # Fallback: execute directly on device
            return await self._execute_action_directly(action_type, opt)
        
        result = await self.task_executor.run_plans(
            f"{action_type}",
            [action_plan],
        )
        
        return result.output if result else None
    
    async def _execute_action_directly(self, action_type: str, param: Dict) -> Any:
        """Execute an action directly on the device (fallback when TaskExecutor is not available)"""
        from ..anomaly_guard import UIAnomalyGuard
        await UIAnomalyGuard(self.device, llm=self.llm, vision_llm=self.vision_llm).handle(f"before_{action_type}")
        locate_info = param.get("locate", {})
        
        # Get UI context for coordinate conversion
        ui_context = await self.get_ui_context()
        ratio = getattr(ui_context, 'shrunk_shot_to_logical_ratio', 1.0)
        
        if locate_info:
            # If we have locate info with coordinates, use them
            center = locate_info.get("center")
            if center:
                # Convert from screenshot to logical coordinates if needed
                if ratio != 1.0 and isinstance(center, (list, tuple)):
                    center = (center[0] / ratio, center[1] / ratio)
                
                if action_type == "Tap":
                    self.device.click(position=center)
                elif action_type == "RightClick":
                    if hasattr(self.device, 'right_click'):
                        self.device.right_click(position=center)
                    else:
                        self.device.click(position=center)
                elif action_type == "DoubleClick":
                    if hasattr(self.device, 'double_click'):
                        self.device.double_click(position=center)
                    else:
                        self.device.click(position=center)
                elif action_type == "Hover":
                    if hasattr(self.device, 'hover'):
                        self.device.hover(position=center)
                elif action_type == "LongPress":
                    if hasattr(self.device, 'long_press'):
                        self.device.long_press(position=center, duration=param.get("duration", 500))
                elif action_type == "ClearInput":
                    if hasattr(self.device, 'input'):
                        self.device.click(position=center)
                        if hasattr(self.device, 'keyboard_press'):
                            self.device.keyboard_press("Control+A")
                            self.device.keyboard_press("Backspace")
                elif action_type == "Input":
                    value = param.get("value", "")
                    if hasattr(self.device, 'input'):
                        self.device.input(value, position=center, clear_before=(param.get("mode", "replace") == "replace"))
                elif action_type == "Scroll":
                    direction = param.get("direction", "down")
                    if hasattr(self.device, 'scroll'):
                        self.device.scroll(direction=direction, distance=param.get("distance"))
                elif action_type == "KeyboardPress":
                    key_name = param.get("key_name", "")
                    if hasattr(self.device, 'keyboard_press'):
                        self.device.keyboard_press(key_name)

        await UIAnomalyGuard(self.device, llm=self.llm, vision_llm=self.vision_llm).handle(f"after_{action_type}")
        return None
    
    # ==================== Report ====================
    
    def _reset_dump(self) -> ReportActionDump:
        """Reset the report dump"""
        self.dump = ReportActionDump(
            sdk_version="0.1.0",
            group_name=self.opts.group_name,
            group_description=self.opts.group_description,
        )
        return self.dump
    
    def _append_execution_dump(self, execution: Dict, runner=None) -> None:
        """Append an execution dump"""
        if not hasattr(self.dump, 'executions'):
            self.dump.executions = []
        self.dump.executions.append(execution)
    
    def _dump_data_string(self, opt: Optional[Dict] = None) -> str:
        """Serialize dump data to string"""
        return json.dumps(self.dump.model_dump(), default=str, ensure_ascii=False)
    
    def _write_out_action_dumps(self, execution_dump: Optional[Dict] = None) -> None:
        """Write out action dumps for report"""
        if execution_dump:
            self._report_generator.on_execution_update(
                execution_dump,
                self._get_report_meta(),
                self.opts.report_attributes if hasattr(self.opts, 'report_attributes') else None,
            )
        self.report_file = self._report_generator.get_report_path()
    
    def _get_report_meta(self) -> ReportMeta:
        """Get report metadata"""
        return ReportMeta(
            group_name=self.dump.group_name if hasattr(self.dump, 'group_name') else "",
            group_description=self.dump.group_description if hasattr(self.dump, 'group_description') else "",
            sdk_version=self.dump.sdk_version if hasattr(self.dump, 'sdk_version') else "0.1.0",
            device_type=getattr(self.device, 'interface_type', 'unknown'),
        )
    
    async def record_to_report(
        self,
        title: Optional[str] = None,
        opt: Optional[Dict] = None,
    ) -> None:
        """Record a screenshot to the report"""
        opt = opt or {}
        base64_data = opt.get("screenshot_base64") or (
            await self.device.screenshot_base64() if hasattr(self.device, 'screenshot_base64') and asyncio.iscoroutinefunction(self.device.screenshot_base64) 
            else (self.device.screenshot_base64() if hasattr(self.device, 'screenshot_base64') else None)
        )
        now = time.time()
        screenshot = ScreenshotItem.create(base64_data or "", now)
        
        execution_dump = ExecutionDump(
            id=str(uuid.uuid4()),
            log_time=now,
            name=f"Log - {title or 'untitled'}",
            description=opt.get("content", ""),
            tasks=[{
                "task_id": str(uuid.uuid4()),
                "type": "Log",
                "sub_type": "Screenshot",
                "status": "finished",
                "recorder": [{"type": "screenshot", "ts": now, "screenshot": screenshot.to_dict()}],
                "timing": {"start": now, "end": now, "cost": 0},
                "param": {"content": opt.get("content", "")},
            }],
        )
        
        self._append_execution_dump(execution_dump.model_dump())
        self._write_out_action_dumps(execution_dump.model_dump())
        await self._report_generator.flush()
    
    # ==================== Cache ====================
    
    async def flush_cache(self, options: Optional[Dict] = None) -> None:
        """Flush cache to file"""
        if not self.task_cache:
            raise ValueError("Cache is not configured")
        self.task_cache.flush_cache_to_file(options)
    
    # ==================== Lifecycle ====================
    
    async def destroy(self) -> None:
        """Destroy the agent and clean up resources"""
        if self.destroyed:
            return
        
        self.destroyed = True
        
        # Destroy device
        if hasattr(self.device, 'destroy') and callable(self.device.destroy):
            try:
                self.device.destroy()
            except Exception as e:
                logger.warning(f"Error destroying device: {e}")
        
        # Flush report
        await self._report_generator.flush()
        final_path = await self._report_generator.finalize()
        self.report_file = final_path
        
        # Reset dump
        self._reset_dump()
    
    # ==================== Dump Listeners ====================
    
    def add_dump_update_listener(self, listener: Callable) -> Callable:
        """Add a dump update listener, returns remove function"""
        self._dump_update_listeners.append(listener)
        return lambda: self.remove_dump_update_listener(listener)
    
    def remove_dump_update_listener(self, listener: Callable) -> None:
        """Remove a dump update listener"""
        try:
            self._dump_update_listeners.remove(listener)
        except ValueError:
            pass
    
    def clear_dump_update_listeners(self) -> None:
        """Clear all dump update listeners"""
        self._dump_update_listeners = []
    
    # ==================== Internal ====================
    
    def _process_cache_config(self, opts: AgentOpt) -> Optional[Dict]:
        """Process cache configuration and return normalized settings"""
        cache = opts.cache
        if cache is None and opts.cache_id is None:
            return None
        
        # Validate
        cache_dict = cache.model_dump() if isinstance(cache, CacheConfig) else cache
        validate_agent_cache_input(cache_dict)
        
        if not cache_dict:
            return None
        
        strategy = cache_dict.get("strategy", "read-write")
        is_read_only = strategy == "read-only"
        is_write_only = strategy == "write-only"
        
        return {
            "id": cache_dict.get("id", opts.cache_id or "default"),
            "enabled": not is_write_only,
            "read_only": is_read_only,
            "write_only": is_write_only,
            "cache_dir": (cache_dict.get("cache_dir") or "").strip() or None,
        }


def create_agent(device, opts: Optional[Union[AgentOpt, Dict]] = None, llm=None, vision_llm=None) -> Agent:
    """Factory function to create an Agent"""
    return Agent(device, opts, llm=llm, vision_llm=vision_llm)
