import time
from typing import Optional, List, Dict, Any, Callable

from ..types import (
    PlanningAction, DetailedLocateParam, LocateResultElement,
    ExecutionTaskApply, ExecutionTaskPlanningLocateApply,
    ElementCacheFeature, ExecutionTaskHitBy, Rect, LocateCache
)
from .conversation_history import ConversationHistory
from common.logger import logger


def locate_plan_for_locate(param) -> PlanningAction:
    """Create a locate plan from a locate parameter"""
    if isinstance(param, str):
        locate = DetailedLocateParam(prompt=param)
    elif isinstance(param, dict):
        locate = DetailedLocateParam(**param)
    else:
        locate = param
    locate_param = locate.model_dump() if hasattr(locate, 'model_dump') else locate
    if not isinstance(locate_param, dict):
        locate_param = {"prompt": str(locate_param)}
    return PlanningAction(type="Locate", param=locate_param, thought="")


class TaskBuilder:
    """
    Converts AI-generated plan actions to executable tasks.
    Port of TS TaskBuilder.
    """
    
    def __init__(
        self,
        device,  # BaseDevice instance
        service,  # Service instance
        task_cache=None,  # Optional TaskCache
        action_space: Optional[List] = None,
        wait_after_action: Optional[int] = None,
    ):
        self.device = device
        self.service = service
        self.task_cache = task_cache
        self.action_space = action_space or []
        self.wait_after_action = wait_after_action
    
    async def build(
        self,
        plans: List[PlanningAction],
        planning_model=None,
        default_model=None,
        options: Optional[Dict] = None,
    ) -> Dict[str, List]:
        """Convert plan actions to executable tasks"""
        options = options or {}
        tasks: List[ExecutionTaskApply] = []
        cacheable = options.get("cacheable")
        deep_locate = options.get("deep_locate")
        
        for plan in plans:
            if plan.type == "Locate":
                await self._handle_locate_plan(plan, tasks, default_model, cacheable, deep_locate)
            elif plan.type == "Finished":
                self._handle_finished_plan(plan, tasks)
            else:
                await self._handle_action_plan(plan, tasks, default_model, cacheable, deep_locate)
        
        return {"tasks": tasks}
    
    def _handle_finished_plan(self, plan: PlanningAction, tasks: List) -> None:
        """Handle a Finished plan action"""
        task = ExecutionTaskApply(
            type="Action Space",
            sub_type="Finished",
            param=None,
            thought=plan.thought,
        )
        tasks.append(task)
    
    async def _handle_locate_plan(
        self, plan: PlanningAction, tasks: List,
        default_model=None, cacheable=None, deep_locate=None,
    ) -> None:
        """Handle a Locate plan action"""
        task = self._create_locate_task(plan, plan.param, default_model, cacheable, deep_locate)
        tasks.append(task)
    
    async def _handle_action_plan(
        self, plan: PlanningAction, tasks: List,
        default_model=None, cacheable=None, deep_locate=None,
    ) -> None:
        """Handle an action plan (Tap, Input, Scroll, etc.)"""
        plan_type = plan.type
        param = plan.param if isinstance(plan.param, dict) else {}
        
        # Find matching action in action space
        action = None
        for a in self.action_space:
            if a.name == plan_type:
                action = a
                break
        
        if not action:
            raise ValueError(f"Action type '{plan_type}' not found in action space")
        
        # Check for locate fields in the action's param schema
        locate_fields = self._find_locate_fields(action)
        required_locate_fields = self._find_locate_fields(action, required_only=True)
        
        # Process locate fields
        for field in locate_fields:
            if param.get(field):
                locate_plan = locate_plan_for_locate(param[field])
                logger.debug(
                    f"will prepend locate param for field action.type={plan_type} "
                    f"param={param[field]}"
                )
                locate_task = self._create_locate_task(
                    locate_plan, param[field], default_model, cacheable, deep_locate,
                    on_result=lambda result, f=field, p=param: p.update({f: result}),
                )
                tasks.append(locate_task)
            elif field in required_locate_fields:
                raise ValueError(f"Required locate field '{field}' is not provided for action {plan_type}")
        
        task = ExecutionTaskApply(
            type="Action Space",
            sub_type=plan_type,
            thought=plan.thought,
            param=param,
        )
        task._executor = self._make_action_executor(plan_type)
        tasks.append(task)
    
    def _find_locate_fields(self, action, required_only: bool = False) -> List[str]:
        """Find locate fields in an action's param schema"""
        if not action or not action.param_schema:
            return []
        
        locate_fields = []
        properties = action.param_schema.properties if hasattr(action.param_schema, 'properties') else action.param_schema.get("properties", {})
        required = action.param_schema.required if hasattr(action.param_schema, 'required') else action.param_schema.get("required", [])
        
        for field_name, field_schema in properties.items():
            if isinstance(field_schema, dict):
                is_locate = field_schema.get("description", "").find("Locate") >= 0 or field_name == "locate"
                if is_locate:
                    if not required_only or field_name in required:
                        locate_fields.append(field_name)
        
        return locate_fields
    
    def _create_locate_task(
        self,
        plan: PlanningAction,
        detailed_locate_param,
        default_model=None,
        cacheable=None,
        deep_locate=None,
        on_result: Optional[Callable] = None,
    ) -> ExecutionTaskPlanningLocateApply:
        """Create a locate task with cache/AI fallback chain"""
        
        # Normalize locate param
        if isinstance(detailed_locate_param, str):
            locate_param = DetailedLocateParam(prompt=detailed_locate_param)
        elif isinstance(detailed_locate_param, dict):
            locate_param = DetailedLocateParam(**detailed_locate_param)
        else:
            locate_param = detailed_locate_param
        
        if cacheable is not None:
            locate_param.cacheable = cacheable
        if deep_locate and not locate_param.deep_locate:
            locate_param.deep_locate = True
        
        task = ExecutionTaskPlanningLocateApply(
            type="Planning",
            sub_type="Locate",
            param=locate_param.model_dump() if hasattr(locate_param, 'model_dump') else locate_param,
            thought=plan.thought,
        )
        
        # Store the executor logic and on_result callback as attributes
        # (The actual executor will be set by TaskExecutor when running)
        task._executor = self._make_locate_executor(locate_param, default_model, on_result)
        
        return task
    
    def _make_locate_executor(self, locate_param, default_model, on_result):
        """Create the executor function for a locate task"""
        
        async def executor(param, task_context):
            task = task_context["task"]
            ui_context = task_context.get("ui_context")
            
            if not ui_context:
                ui_context = await self.service.context_retriever_fn()
            
            assert ui_context, "uiContext is required for Locate task"
            
            shrunk_shot_to_logical_ratio = getattr(ui_context, 'shrunk_shot_to_logical_ratio', 1.0)
            
            # Try locate from various sources in order:
            # 1. Plan direct hit (locatedPixelBbox)
            # 2. XPath hit
            # 3. Cache hit
            # 4. AI locate
            
            element = None
            hit_by = None
            
            # Try plan direct hit
            locate_param_obj = param
            if isinstance(param, dict):
                locate_param_obj = DetailedLocateParam(**param) if param.get("prompt") else locate_param
            
            if locate_param_obj.located_pixel_bbox and not locate_param_obj.deep_locate:
                bbox = locate_param_obj.located_pixel_bbox
                rect = Rect(left=bbox[0], top=bbox[1], width=bbox[2]-bbox[0], height=bbox[3]-bbox[1])
                center_x = rect.left + rect.width / 2
                center_y = rect.top + rect.height / 2
                element = LocateResultElement(
                    center=(center_x, center_y),
                    rect=rect,
                    description=locate_param_obj.prompt if isinstance(locate_param_obj.prompt, str) else str(locate_param_obj.prompt),
                )
                hit_by = ExecutionTaskHitBy(**{"from": "Plan", "context": {"locatedPixelBbox": bbox}})
            
            # Try cache hit (if not already found from plan)
            if not element and self.task_cache and self.task_cache.is_cache_result_used:
                cache_prompt = locate_param_obj.prompt
                cache_result = self.task_cache.match_locate_cache(cache_prompt)
                if cache_result and cache_result.cache_usable and cache_result.cache_content.cache:
                    # Try to match cache using device
                    if hasattr(self.device, 'rect_matches_cache_feature') and self.device.rect_matches_cache_feature:
                        try:
                            cache_feature = cache_result.cache_content.cache
                            rect = self.device.rect_matches_cache_feature(cache_feature.model_dump() if hasattr(cache_feature, 'model_dump') else cache_feature)
                            if rect:
                                if isinstance(rect, dict):
                                    rect = Rect(**rect)
                                element = LocateResultElement(
                                    center=(rect.left + rect.width / 2, rect.top + rect.height / 2),
                                    rect=rect,
                                    description=cache_prompt if isinstance(cache_prompt, str) else str(cache_prompt),
                                )
                                cache_entry = cache_result.cache_content.cache.model_dump() if hasattr(cache_result.cache_content.cache, 'model_dump') else cache_result.cache_content.cache
                                hit_by = ExecutionTaskHitBy(**{"from": "Cache", "context": {"cacheEntry": cache_entry}})
                        except Exception as e:
                            logger.debug(f"rectMatchesCacheFeature error: {e}")
            
            # AI locate (if not found from plan or cache)
            if not element:
                try:
                    locate_result = await self.service.locate(
                        locate_param_obj,
                        {"context": ui_context},
                        default_model,
                    )
                    if locate_result:
                        element = locate_result.element
                except Exception as e:
                    error_dump = getattr(e, 'dump', None)
                    if error_dump:
                        task.log = {"dump": error_dump}
                    raise
            
            if not element:
                raise ValueError(f"Element not found: {locate_param_obj.prompt}")
            
            # Write cache if element found and not a cache hit
            if element and self.task_cache and hit_by is None:
                cache_prompt = locate_param_obj.prompt
                if hasattr(self.device, 'cache_feature_for_point') and self.device.cache_feature_for_point:
                    try:
                        point_for_cache = element.center
                        if shrunk_shot_to_logical_ratio != 1.0:
                            point_for_cache = (
                                round(element.center[0] / shrunk_shot_to_logical_ratio),
                                round(element.center[1] / shrunk_shot_to_logical_ratio),
                            )
                        feature = self.device.cache_feature_for_point(
                            point_for_cache,
                            {"target_description": locate_param_obj.prompt if isinstance(locate_param_obj.prompt, str) else str(locate_param_obj.prompt)}
                        )
                        if feature:
                            self.task_cache.update_or_append_cache_record(
                                LocateCache(
                                    type="locate",
                                    prompt=cache_prompt,
                                    cache=feature,
                                ),
                            )
                    except Exception as e:
                        logger.debug(f"cacheFeatureForPoint failed: {e}")
            
            # Call on_result callback
            if on_result:
                on_result(element)
            
            return {
                "output": {"element": element},
                "hit_by": hit_by,
            }
        
        return executor

    def _make_action_executor(self, action_type: str):
        async def executor(param, task_context):
            param = param or {}
            element = None
            for value in param.values():
                if isinstance(value, LocateResultElement):
                    element = value
                    break
            position = element.center if element else None
            ui_context = task_context.get("ui_context")
            ratio = getattr(ui_context, "shrunk_shot_to_logical_ratio", 1.0) if ui_context else 1.0
            if position and ratio and ratio != 1.0:
                position = (position[0] / ratio, position[1] / ratio)
            if action_type == "Finished":
                return {"output": param}
            if action_type == "Sleep":
                import asyncio
                await asyncio.sleep((param.get("timeMs") or param.get("time_ms") or 1000) / 1000)
                return {"output": None}
            if action_type == "Tap":
                self.device.click(position=position)
            elif action_type == "RightClick":
                self.device.right_click(position=position)
            elif action_type == "DoubleClick":
                self.device.double_click(position=position)
            elif action_type == "Hover":
                self.device.hover(position=position)
            elif action_type == "Input":
                self.device.input(str(param.get("value", "")), position=position, clear_before=param.get("mode", "replace") in ("replace", "clear"))
            elif action_type == "KeyboardPress":
                key_name = param.get("key_name") or param.get("keyName")
                self.device.keyboard_press(key_name)
            elif action_type == "Scroll":
                self.device.scroll(direction=param.get("direction", "down"), distance=param.get("distance"))
            elif action_type == "LongPress":
                self.device.long_press(position=position, duration=param.get("duration", 500))
            elif action_type == "ClearInput":
                if position:
                    self.device.click(position=position)
                self.device.keyboard_press("Control+A")
                self.device.keyboard_press("Backspace")
            elif action_type == "Pinch":
                return {"output": None}
            else:
                raise ValueError(f"Unsupported action type: {action_type}")
            return {"output": None}
        return executor
