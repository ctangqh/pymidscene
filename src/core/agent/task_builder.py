import time
from typing import Optional, List, Dict, Any, Callable

from ..types import (
    PlanningAction, DetailedLocateParam, LocateResultElement,
    ExecutionTaskApply, ExecutionTaskPlanningLocateApply,
    ElementCacheFeature, ExecutionTaskHitBy, Rect, LocateCache
)
from ..uitree.debug import capture_debug_tree, capture_full_page_control_debug
from ..uitree.dump import build_debug_prefix
from ..uitree.service import uitree_manager
from .conversation_history import ConversationHistory
from common.config import settings
from common.exceptions import ActionExecutionError
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

    @staticmethod
    def _serialize_element_ref(element_ref: Any) -> Optional[Dict[str, Any]]:
        if not element_ref:
            return None
        if hasattr(element_ref, "to_dict"):
            return element_ref.to_dict()
        if isinstance(element_ref, dict):
            return dict(element_ref)
        return None

    @classmethod
    def _serialize_locator_candidates(cls, candidates: Any) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for candidate in candidates or []:
            item = cls._serialize_element_ref(candidate)
            if item:
                serialized.append(item)
        return serialized

    @staticmethod
    def _resolve_action_target(
        element: Optional[LocateResultElement],
        *,
        device_type: Optional[str] = None,
        action_type: str = "Tap",
    ) -> Dict[str, Any]:
        if not element:
            return {"selector": None, "selector_type": None, "selector_ref": None, "position": None}

        candidates = []
        if element.element_ref:
            candidates.append(element.element_ref)
        candidates.extend(element.locator_candidates or [])

        selector_ref = uitree_manager.select_best_candidate(
            candidates,
            device_type=device_type,
            action_type=action_type.lower(),
            actionable_only=True,
        )
        selector = selector_ref.get("selector_value") if selector_ref else None
        selector_type = selector_ref.get("selector_type") if selector_ref else None

        return {
            "selector": selector,
            "selector_type": selector_type,
            "selector_ref": selector_ref,
            "position": element.center,
        }

    @staticmethod
    def _position_to_device_space(
        position: Optional[tuple],
        *,
        coordinate_space: str = "logical",
        ratio: float = 1.0,
    ) -> Optional[tuple]:
        if not position:
            return position
        if coordinate_space == "screenshot" and ratio and ratio != 1.0:
            return (position[0] / ratio, position[1] / ratio)
        return position

    @classmethod
    def _build_locate_result_from_node(
        cls,
        matched_node: Any,
        description: str,
        fallback_element: Optional[LocateResultElement] = None,
    ) -> Optional[LocateResultElement]:
        if not matched_node:
            return None

        bounds = getattr(matched_node, "bounds", None)
        if bounds:
            left, top, width, height = bounds
        elif fallback_element:
            left = fallback_element.rect.left
            top = fallback_element.rect.top
            width = fallback_element.rect.width
            height = fallback_element.rect.height
        else:
            return None

        rect = Rect(left=left, top=top, width=width, height=height)
        return LocateResultElement(
            center=(rect.left + rect.width / 2, rect.top + rect.height / 2),
            rect=rect,
            el_type=getattr(matched_node, "control_type", None) or getattr(matched_node, "tag", None) or "element",
            description=getattr(matched_node, "name", None) or description,
            element_ref=cls._serialize_element_ref(getattr(matched_node, "element_ref", None)),
            locator_candidates=cls._serialize_locator_candidates(getattr(matched_node, "locator_candidates", None)),
        )

    @staticmethod
    def _stringify_prompt(prompt: Any) -> str:
        if isinstance(prompt, str):
            return prompt.strip()
        if prompt is None:
            return ""
        return str(prompt).strip()

    @classmethod
    def _extract_prompt_from_locate_param(cls, locate_param: Any) -> str:
        if isinstance(locate_param, DetailedLocateParam):
            return cls._stringify_prompt(locate_param.prompt)
        if isinstance(locate_param, dict):
            return cls._stringify_prompt(locate_param.get("prompt"))
        if isinstance(locate_param, str):
            return locate_param.strip()
        return cls._stringify_prompt(locate_param)

    @staticmethod
    def _bounds_to_screenshot_bbox(bounds: Any, *, ratio: float = 1.0) -> Optional[List[float]]:
        if not bounds or len(bounds) != 4:
            return None
        left, top, width, height = [float(v) for v in bounds]
        if ratio and ratio != 1.0:
            left *= ratio
            top *= ratio
            width *= ratio
            height *= ratio
        return [left, top, left + width, top + height]

    @classmethod
    def _populate_structural_anchor_metadata(
        cls,
        locate_param_obj: DetailedLocateParam,
        raw_tree: Any,
        prompt_text: str,
        *,
        device_type: Optional[str] = None,
        ratio: float = 1.0,
    ) -> None:
        if not raw_tree or not prompt_text:
            return
        try:
            matched_node = uitree_manager.find_best_match(raw_tree, prompt_text, device_type=device_type)
            if not matched_node:
                return
            if locate_param_obj.structural_anchor_available is None:
                locate_param_obj.structural_anchor_available = True
            if not locate_param_obj.structural_anchor_bbox:
                anchor_bbox = cls._bounds_to_screenshot_bbox(
                    getattr(matched_node, "bounds", None),
                    ratio=ratio,
                )
                if anchor_bbox:
                    locate_param_obj.structural_anchor_bbox = anchor_bbox
            if not locate_param_obj.structural_anchor_description:
                locate_param_obj.structural_anchor_description = (
                    getattr(matched_node, "name", None) or prompt_text
                )
        except Exception as exc:
            logger.debug(f"populate structural anchor metadata failed: prompt={prompt_text}, error={exc}")

    def _refresh_action_target(
        self,
        element: Optional[LocateResultElement],
        *,
        device_type: Optional[str] = None,
        action_type: str = "Tap",
    ) -> Optional[Dict[str, Any]]:
        if not element or not getattr(self.device, "get_dom_tree", None):
            return None
        description = (element.description or "").strip()
        if not description:
            return None
        try:
            raw_tree = self.device.get_dom_tree()
            matched_node = uitree_manager.find_best_match(raw_tree, description, device_type=device_type)
            refreshed_element = self._build_locate_result_from_node(
                matched_node,
                description,
                fallback_element=element,
            )
            if not refreshed_element:
                return None
            refreshed_target = self._resolve_action_target(
                refreshed_element,
                device_type=device_type,
                action_type=action_type,
            )
            if not refreshed_target.get("selector_ref") and not refreshed_target.get("position"):
                return None
            return refreshed_target
        except Exception as exc:
            logger.debug(f"refresh action target failed: action={action_type}, description={description}, error={exc}")
            return None

    @classmethod
    def _enrich_element_with_uitree_metadata(
        cls,
        element: Optional[LocateResultElement],
        raw_tree: Any,
        description: str,
        *,
        device_type: Optional[str] = None,
    ) -> Optional[LocateResultElement]:
        if not element or not raw_tree or not description:
            return element
        if element.element_ref and element.locator_candidates:
            return element
        try:
            matched_node = uitree_manager.find_best_match(raw_tree, description, device_type=device_type)
            if not matched_node:
                return element
            if not element.element_ref and getattr(matched_node, "element_ref", None):
                element.element_ref = cls._serialize_element_ref(matched_node.element_ref)
            if not element.locator_candidates and getattr(matched_node, "locator_candidates", None):
                element.locator_candidates = cls._serialize_locator_candidates(matched_node.locator_candidates)
        except Exception as exc:
            logger.debug(f"enrich element with uitree metadata failed: description={description}, error={exc}")
        return element

    @staticmethod
    def _append_action_recovery_log(task: Any, record: Dict[str, Any]) -> None:
        if task is None:
            return
        current_log = getattr(task, "log", None)
        if not isinstance(current_log, dict):
            current_log = {}
            setattr(task, "log", current_log)
        recovery_log = current_log.setdefault("action_recovery", [])
        if isinstance(recovery_log, list):
            recovery_log.append(record)

    def _execute_action_with_retry(
        self,
        *,
        action_type: str,
        element: Optional[LocateResultElement],
        action_target: Dict[str, Any],
        run_action: Callable[[Dict[str, Any]], None],
        allow_position_fallback: bool = False,
        task: Any = None,
    ) -> None:
        device_type = getattr(self.device, "interface_type", None)
        try:
            run_action(action_target)
            return
        except Exception as first_error:
            self._append_action_recovery_log(
                task,
                {
                    "stage": "initial_failure",
                    "action_type": action_type,
                    "selector_ref": action_target.get("selector_ref"),
                    "position": action_target.get("position"),
                    "error": str(first_error),
                },
            )
            logger.debug(
                f"action execution failed, try refresh and retry: action={action_type}, "
                f"selector_ref={action_target.get('selector_ref')}, error={first_error}"
            )

        refreshed_target = self._refresh_action_target(
            element,
            device_type=device_type,
            action_type=action_type,
        )
        if refreshed_target:
            try:
                self._append_action_recovery_log(
                    task,
                    {
                        "stage": "refresh_retry",
                        "action_type": action_type,
                        "selector_ref": refreshed_target.get("selector_ref"),
                        "position": refreshed_target.get("position"),
                    },
                )
                logger.debug(
                    f"retry action with refreshed target: action={action_type}, "
                    f"selector_ref={refreshed_target.get('selector_ref')}"
                )
                run_action(refreshed_target)
                return
            except Exception as retry_error:
                self._append_action_recovery_log(
                    task,
                    {
                        "stage": "refresh_retry_failure",
                        "action_type": action_type,
                        "selector_ref": refreshed_target.get("selector_ref"),
                        "position": refreshed_target.get("position"),
                        "error": str(retry_error),
                    },
                )
                logger.debug(
                    f"refreshed action target retry failed: action={action_type}, "
                    f"selector_ref={refreshed_target.get('selector_ref')}, error={retry_error}"
                )

        fallback_position = None
        if allow_position_fallback:
            fallback_position = refreshed_target.get("position") if refreshed_target else None
            if not fallback_position:
                fallback_position = action_target.get("position")
        if allow_position_fallback and fallback_position:
            try:
                self._append_action_recovery_log(
                    task,
                    {
                        "stage": "position_fallback",
                        "action_type": action_type,
                        "position": fallback_position,
                    },
                )
                logger.debug(f"fallback action to position: action={action_type}, position={fallback_position}")
                if action_type == "Tap":
                    self.device.click(position=fallback_position)
                elif action_type == "ClearInput":
                    self.device.click(position=fallback_position)
                else:
                    raise ActionExecutionError(
                        f"Unsupported position fallback action: {action_type}",
                        data={"action_type": action_type},
                    )
                return
            except Exception as fallback_error:
                raise ActionExecutionError(
                    f"Action recovery failed after refresh and position fallback: {fallback_error}",
                    data={
                        "action_type": action_type,
                        "selector_ref": action_target.get("selector_ref"),
                        "refreshed_selector_ref": refreshed_target.get("selector_ref") if refreshed_target else None,
                        "position": fallback_position,
                    },
                ) from fallback_error

        raise ActionExecutionError(
            f"Action recovery failed after refresh retry: {action_type}",
            data={
                "selector_ref": action_target.get("selector_ref"),
                "refreshed_selector_ref": refreshed_target.get("selector_ref") if refreshed_target else None,
                "position": action_target.get("position"),
            },
        )
    
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
            title="Finished",
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
        task_title = ""
        
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
                task_title = task_title or self._extract_prompt_from_locate_param(param[field])
                locate_plan = locate_plan_for_locate(param[field])
                logger.debug(
                    f"will prepend locate param for field action.type={plan_type} "
                    f"param={param[field]}"
                )
                locate_task = self._create_locate_task(
                    locate_plan, param[field], default_model, cacheable, deep_locate,
                    on_result=lambda result, f=field, p=param: p.update({f: result}),
                    action_type=plan_type,
                )
                tasks.append(locate_task)
            elif field in required_locate_fields:
                raise ValueError(f"Required locate field '{field}' is not provided for action {plan_type}")
        
        task = ExecutionTaskApply(
            type="Action Space",
            sub_type=plan_type,
            title=task_title or plan_type,
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
        action_type: Optional[str] = None,
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
        if action_type and not locate_param.action_type:
            locate_param.action_type = action_type
        if not locate_param.device_type:
            locate_param.device_type = getattr(self.device, "interface_type", None)
        
        task = ExecutionTaskPlanningLocateApply(
            type="Planning",
            sub_type="Locate",
            title=self._extract_prompt_from_locate_param(locate_param),
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
            raw_tree = None
            device_type = getattr(self.device, "interface_type", None)
            prompt_text = ""
            
            # Try plan direct hit
            locate_param_obj = param
            if isinstance(param, dict):
                locate_param_obj = DetailedLocateParam(**param) if param.get("prompt") else locate_param
            if not locate_param_obj.device_type:
                locate_param_obj.device_type = device_type
            prompt_text = (
                locate_param_obj.prompt
                if isinstance(locate_param_obj.prompt, str)
                else str(locate_param_obj.prompt)
            )

            if settings.DEBUG:
                try:
                    raw_tree = self.device.get_dom_tree()
                    save_dir = None
                    screenshot_dir_resolver = getattr(self.device, "_pymidscene_report_screenshot_dir_resolver", None)
                    if callable(screenshot_dir_resolver):
                        try:
                            save_dir = screenshot_dir_resolver()
                        except Exception as e:
                            logger.debug(f"resolve report screenshot dir failed: {e}")
                    capture_debug_tree(
                        self.device,
                        prompt_text,
                        raw_tree=raw_tree,
                        device_type=device_type,
                        save_dir=save_dir,
                        prefix=build_debug_prefix(prompt_text),
                    )
                    if device_type in ("browser", "web"):
                        capture_full_page_control_debug(
                            self.device,
                            prompt_text,
                            raw_tree=raw_tree,
                            device_type=device_type,
                            save_dir=save_dir,
                            prefix=f"{build_debug_prefix(prompt_text)}_fullpage",
                        )
                except Exception as e:
                    logger.debug(f"capture_debug_tree error: {e}")

            if locate_param_obj.structural_anchor_available is None and device_type in ("browser", "web", "windows"):
                if raw_tree is None:
                    try:
                        raw_tree = self.device.get_dom_tree()
                    except Exception:
                        raw_tree = None
                locate_param_obj.structural_anchor_available = raw_tree is not None
            if raw_tree is not None:
                self._populate_structural_anchor_metadata(
                    locate_param_obj,
                    raw_tree,
                    prompt_text,
                    device_type=device_type,
                    ratio=shrunk_shot_to_logical_ratio,
                )
            
            if locate_param_obj.located_pixel_bbox and not locate_param_obj.deep_locate:
                bbox = locate_param_obj.located_pixel_bbox
                rect = Rect(left=bbox[0], top=bbox[1], width=bbox[2]-bbox[0], height=bbox[3]-bbox[1])
                center_x = rect.left + rect.width / 2
                center_y = rect.top + rect.height / 2
                element = LocateResultElement(
                    center=(center_x, center_y),
                    rect=rect,
                    description=locate_param_obj.prompt if isinstance(locate_param_obj.prompt, str) else str(locate_param_obj.prompt),
                    coordinate_space="screenshot",
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
                                    coordinate_space="logical",
                                )
                                cache_entry = cache_result.cache_content.cache.model_dump() if hasattr(cache_result.cache_content.cache, 'model_dump') else cache_result.cache_content.cache
                                hit_by = ExecutionTaskHitBy(**{"from": "Cache", "context": {"cacheEntry": cache_entry}})
                        except Exception as e:
                            logger.debug(f"rectMatchesCacheFeature error: {e}")

            # Try native UI tree hit for non-web devices before AI vision locate
            if not element and device_type not in ("web", "browser"):
                try:
                    if raw_tree is None:
                        raw_tree = self.device.get_dom_tree()
                    matched_node = uitree_manager.find_best_match(raw_tree, prompt_text, device_type=device_type)
                    if matched_node and matched_node.bounds:
                        left, top, width, height = matched_node.bounds
                        rect = Rect(left=left, top=top, width=width, height=height)
                        element = LocateResultElement(
                            center=(rect.left + rect.width / 2, rect.top + rect.height / 2),
                            rect=rect,
                            el_type=matched_node.control_type or matched_node.tag or "element",
                            description=matched_node.name or prompt_text,
                            coordinate_space="logical",
                            element_ref=self._serialize_element_ref(matched_node.element_ref),
                            locator_candidates=self._serialize_locator_candidates(matched_node.locator_candidates),
                        )
                        hit_by = ExecutionTaskHitBy(
                            **{
                                "from": "UI Tree",
                                "context": {
                                    "path": matched_node.path,
                                    "tag": matched_node.tag,
                                    "controlType": matched_node.control_type,
                                    "elementRef": self._serialize_element_ref(matched_node.element_ref),
                                    "locatorCandidates": self._serialize_locator_candidates(matched_node.locator_candidates),
                                },
                            }
                        )
                        logger.debug(
                            f"ui tree locate hit: prompt={prompt_text}, path={matched_node.path}, bounds={matched_node.bounds}"
                        )
                except Exception as e:
                    logger.debug(f"ui tree locate failed: {e}")
            
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
                        if raw_tree is None:
                            try:
                                raw_tree = self.device.get_dom_tree()
                            except Exception:
                                raw_tree = None
                        element = self._enrich_element_with_uitree_metadata(
                            element,
                            raw_tree,
                            prompt_text,
                            device_type=device_type,
                        )
                except Exception as e:
                    error_dump = getattr(e, 'dump', None)
                    if error_dump:
                        task.log = {"dump": error_dump}
                    raise
            
            if not element:
                raise ValueError(f"Element not found: {locate_param_obj.prompt}")

            prompt_text = (
                locate_param_obj.prompt
                if isinstance(locate_param_obj.prompt, str)
                else str(locate_param_obj.prompt)
            )
            if device_type in ("web", "browser"):
                if raw_tree is None:
                    try:
                        raw_tree = self.device.get_dom_tree()
                    except Exception:
                        raw_tree = None
                element = self._enrich_element_with_uitree_metadata(
                    element,
                    raw_tree,
                    prompt_text,
                    device_type=device_type,
                )
            
            # Write cache if element found and not a cache hit
            if element and self.task_cache and hit_by is None:
                cache_prompt = locate_param_obj.prompt
                if hasattr(self.device, 'cache_feature_for_point') and self.device.cache_feature_for_point:
                    try:
                        point_for_cache = element.center
                        point_for_cache = self._position_to_device_space(
                            point_for_cache,
                            coordinate_space=getattr(element, "coordinate_space", "logical"),
                            ratio=shrunk_shot_to_logical_ratio,
                        )
                        if point_for_cache:
                            point_for_cache = (
                                round(point_for_cache[0]),
                                round(point_for_cache[1]),
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
            from ..anomaly_guard import UIAnomalyGuard
            param = param or {}
            element = None
            for value in param.values():
                if isinstance(value, LocateResultElement):
                    element = value
                    break
            action_target = self._resolve_action_target(
                element,
                device_type=getattr(self.device, "interface_type", None),
                action_type=action_type,
            )
            position = action_target["position"]
            ui_context = task_context.get("ui_context")
            ratio = getattr(ui_context, "shrunk_shot_to_logical_ratio", 1.0) if ui_context else 1.0
            position = self._position_to_device_space(
                position,
                coordinate_space=getattr(element, "coordinate_space", "logical") if element else "logical",
                ratio=ratio,
            )
            selector = action_target["selector"]
            selector_type = action_target["selector_type"]
            selector_ref = action_target["selector_ref"]
            if action_type == "Finished":
                return {"output": param}
            if action_type == "Sleep":
                import asyncio
                await asyncio.sleep((param.get("timeMs") or param.get("time_ms") or 1000) / 1000)
                return {"output": None}

            guard = UIAnomalyGuard(self.device, llm=getattr(self.service, "llm", None))
            try:
                await guard.handle(f"before_{action_type}")
            except Exception:
                raise

            if action_type == "Tap":
                self._execute_action_with_retry(
                    action_type=action_type,
                    element=element,
                    action_target={
                        "selector": selector,
                        "selector_type": selector_type,
                        "selector_ref": selector_ref,
                        "position": position,
                    },
                    allow_position_fallback=True,
                    task=task_context.get("task"),
                    run_action=lambda target: self.device.click(
                        selector=target.get("selector"),
                        selector_type=target.get("selector_type"),
                        selector_ref=target.get("selector_ref"),
                        position=target.get("position"),
                    ),
                )
            elif action_type == "RightClick":
                self.device.right_click(position=position)
            elif action_type == "DoubleClick":
                self.device.double_click(position=position)
            elif action_type == "Hover":
                self.device.hover(position=position)
            elif action_type == "Input":
                self._execute_action_with_retry(
                    action_type=action_type,
                    element=element,
                    action_target={
                        "selector": selector,
                        "selector_type": selector_type,
                        "selector_ref": selector_ref,
                        "position": position,
                    },
                    task=task_context.get("task"),
                    run_action=lambda target: self.device.input(
                        str(param.get("value", "")),
                        selector=target.get("selector"),
                        selector_type=target.get("selector_type"),
                        selector_ref=target.get("selector_ref"),
                        position=target.get("position"),
                        clear_before=param.get("mode", "replace") in ("replace", "clear"),
                    ),
                )
            elif action_type == "KeyboardPress":
                key_name = param.get("key_name") or param.get("keyName")
                self.device.keyboard_press(key_name)
            elif action_type == "Scroll":
                self.device.scroll(direction=param.get("direction", "down"), distance=param.get("distance"))
            elif action_type == "LongPress":
                self.device.long_press(position=position, duration=param.get("duration", 500))
            elif action_type == "ClearInput":
                if position:
                    self._execute_action_with_retry(
                        action_type=action_type,
                        element=element,
                        action_target={
                            "selector": selector,
                            "selector_type": selector_type,
                            "selector_ref": selector_ref,
                            "position": position,
                        },
                        allow_position_fallback=True,
                        task=task_context.get("task"),
                        run_action=lambda target: self.device.click(
                            selector=target.get("selector"),
                            selector_type=target.get("selector_type"),
                            selector_ref=target.get("selector_ref"),
                            position=target.get("position"),
                        ),
                    )
                self.device.keyboard_press("Control+A")
                self.device.keyboard_press("Backspace")
            elif action_type == "Pinch":
                return {"output": None}
            else:
                raise ValueError(f"Unsupported action type: {action_type}")

            try:
                await guard.handle(f"after_{action_type}")
            except Exception:
                raise
            return {"output": None}
        return executor
