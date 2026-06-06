import time
import asyncio
from typing import Optional, List, Dict, Any, Callable, TypeVar, Generic, Union, Literal, cast

from ..types import (
    PlanningAction, DetailedLocateParam, PlanningAIResponse,
    ExecutionTaskApply, ExecutionTaskPlanningApply,
    ServiceExtractOption, ServiceExtractParam,
    AIUsageInfo, DeviceAction,
)
from .execution_session import ExecutionSession, TaskExecutionError
from .task_builder import TaskBuilder, locate_plan_for_locate
from .conversation_history import ConversationHistory
from .usage_intent import with_usage_intent
from .context_parser import common_context_parser
from common.logger import logger
from common.exceptions import TaskError

T = TypeVar("T")

MAX_ERROR_COUNT_IN_ONE_PLANNING_LOOP = 5


class ExecutionResult(Generic[T]):
    """Result of a task execution"""
    def __init__(self, output: T = None, thought: Optional[str] = None, runner=None):
        self.output = output
        self.thought = thought
        self.runner = runner


class TaskExecutor:
    """
    Task execution engine that manages planning, execution, and replanning.
    Port of TS TaskExecutor.
    """
    
    def __init__(
        self,
        device,  # BaseDevice instance
        service,  # Service instance
        opts: Optional[Dict] = None,
    ):
        opts = opts or {}
        self.device = device
        self.service = service
        self.task_cache = opts.get("task_cache")
        self.on_task_start_callback = opts.get("on_task_start")
        self.replanning_cycle_limit = opts.get("replanning_cycle_limit")
        self.wait_after_action = opts.get("wait_after_action")
        self.use_device_time = opts.get("use_device_time", False)
        self.hooks = opts.get("hooks")
        
        action_space = opts.get("action_space", [])
        self.task_builder = TaskBuilder(
            device=device,
            service=service,
            task_cache=self.task_cache,
            action_space=action_space,
            wait_after_action=self.wait_after_action,
        )
    
    def _create_execution_session(self, title: str, options: Optional[Dict] = None) -> ExecutionSession:
        """Create a new execution session"""
        options = options or {}
        return ExecutionSession(
            title,
            lambda: self.service.context_retriever_fn(),
            {
                "on_task_start": self.on_task_start_callback,
                "on_task_update": self.hooks.get("on_task_update") if self.hooks else None,
                "tasks": options.get("tasks"),
            }
        )
    
    async def convert_plan_to_executable(
        self,
        plans: List[PlanningAction],
        planning_model=None,
        default_model=None,
        options: Optional[Dict] = None,
    ):
        """Convert plan actions to executable tasks"""
        return await self.task_builder.build(plans, planning_model, default_model, options)
    
    async def load_yaml_flow_as_planning(self, user_instruction, yaml_string: str):
        """Load a YAML flow as a planning cache hit"""
        session = self._create_execution_session(f"Act - {user_instruction}")
        
        task: ExecutionTaskPlanningApply = ExecutionTaskPlanningApply(
            type="Planning",
            sub_type="LoadYaml",
            param={"user_instruction": user_instruction},
        )
        
        runner = session.get_runner()
        await session.append_and_run(task)
        
        return {"runner": runner}
    
    async def run_plans(
        self,
        title: str,
        plans: List[PlanningAction],
        planning_model=None,
        default_model=None,
    ) -> ExecutionResult:
        """Execute a list of plan actions"""
        session = self._create_execution_session(title)
        result = await self.convert_plan_to_executable(plans, planning_model, default_model)
        tasks = result.get("tasks", [])
        runner = session.get_runner()
        exec_result = await session.append_and_run(tasks)
        output = exec_result.get("output") if exec_result else None
        
        return ExecutionResult(output=output, runner=runner)
    
    async def action(
        self,
        user_prompt,
        planning_model=None,
        default_model=None,
        include_locate_in_planning: bool = True,
        ai_act_context: Optional[str] = None,
        cacheable: Optional[bool] = None,
        replanning_cycle_limit_override: Optional[int] = None,
        images_include_count: int = 1,
        deep_think: bool = False,
        file_chooser_accept: Optional[List[str]] = None,
        deep_locate: Optional[bool] = None,
        abort_signal=None,
    ) -> ExecutionResult:
        """Execute an AI action with planning and replanning loop"""
        
        # File chooser wrapper
        if file_chooser_accept and hasattr(self.device, 'register_file_chooser_listener'):
            # TODO: implement file chooser wrapping
            pass
        
        return await self._run_action(
            user_prompt=user_prompt,
            planning_model=planning_model,
            default_model=default_model,
            include_locate_in_planning=include_locate_in_planning,
            ai_act_context=ai_act_context,
            cacheable=cacheable,
            replanning_cycle_limit_override=replanning_cycle_limit_override,
            images_include_count=images_include_count,
            deep_think=deep_think,
            deep_locate=deep_locate,
            abort_signal=abort_signal,
        )
    
    async def _run_action(
        self,
        user_prompt,
        planning_model=None,
        default_model=None,
        include_locate_in_planning: bool = True,
        ai_act_context: Optional[str] = None,
        cacheable: Optional[bool] = None,
        replanning_cycle_limit_override: Optional[int] = None,
        images_include_count: int = 1,
        deep_think: bool = False,
        deep_locate: Optional[bool] = None,
        abort_signal=None,
    ) -> Any:
        """Core planning loop - plan, execute, replan"""
        
        conversation_history = ConversationHistory()
        session = self._create_execution_session(f"Act - {user_prompt}")
        runner = session.get_runner()
        
        replan_count = 0
        yaml_flow: List[Dict] = []
        replanning_cycle_limit = replanning_cycle_limit_override or self.replanning_cycle_limit or 5
        error_count_in_one_planning_loop = 0
        output_string: Optional[str] = None
        
        if abort_signal and hasattr(abort_signal, 'is_set') and abort_signal.is_set():
            return session.append_error_plan("Task aborted: signal already set")
        
        # Main planning loop
        while True:
            # Check abort signal
            if abort_signal and hasattr(abort_signal, 'is_set') and abort_signal.is_set():
                return session.append_error_plan("Task aborted: signal received")
            
            # Get sub-goal and memory status
            sub_goal_status = conversation_history.sub_goals_to_text() or None
            memories_status = conversation_history.memories_to_text() or None
            
            # Planning step
            plan_task_param = {
                "user_instruction": user_prompt,
                "ai_act_context": ai_act_context,
                "images_include_count": images_include_count,
                "deep_think": deep_think,
            }
            if sub_goal_status:
                plan_task_param["sub_goal_status"] = sub_goal_status
            if memories_status:
                plan_task_param["memories_status"] = memories_status
            
            plan_task = ExecutionTaskPlanningApply(
                type="Planning",
                sub_type="Plan",
                param=plan_task_param,
            )
            
            try:
                result = await session.append_and_run(plan_task, {"allow_when_error": True})
            except Exception as e:
                error_count_in_one_planning_loop += 1
                conversation_history.pending_feedback_message = f"Error in planning: {e}"
                logger.debug(f"Error in planning, count: {error_count_in_one_planning_loop}")
            
            if error_count_in_one_planning_loop > MAX_ERROR_COUNT_IN_ONE_PLANNING_LOOP:
                return session.append_error_plan("Too many errors in one planning loop")
            
            # Get plan result
            plan_result = None
            for task in runner.tasks:
                if task.type == "Planning" and task.sub_type == "Plan" and task.output:
                    plan_result = task.output
                    break
            
            # Execute planned actions
            plans = plan_result.get("actions", []) if plan_result else []
            yaml_flow.extend(plan_result.get("yaml_flow", []) if plan_result else [])
            output_string = plan_result.get("output") if plan_result else None
            
            if not plans:
                break
            
            # Convert plans to executable tasks
            try:
                executables = await self.convert_plan_to_executable(
                    plans, planning_model, default_model,
                    {"cacheable": cacheable, "deep_locate": deep_locate, "abort_signal": abort_signal},
                )
            except Exception as e:
                return session.append_error_plan(f"Error converting plans to executable tasks: {e}")
            
            # Add time context
            time_string = time.strftime("%Y-%m-%d %H:%M:%S")
            conversation_history.pending_feedback_message += f" Current time: {time_string}"
            
            task_count_before_run = len(runner.tasks)
            try:
                await session.append_and_run(executables.get("tasks", []))
            except Exception as e:
                error_count_in_one_planning_loop += 1
                time_string = time.strftime("%Y-%m-%d %H:%M:%S")
                conversation_history.pending_feedback_message = f"Time: {time_string}, Error executing tasks: {e}"
                logger.debug(f"Error executing tasks, count: {error_count_in_one_planning_loop}")
            
            if error_count_in_one_planning_loop > MAX_ERROR_COUNT_IN_ONE_PLANNING_LOOP:
                return session.append_error_plan("Too many errors in one planning loop")
            
            # Check if task is complete
            should_continue = plan_result.get("should_continue_planning", False) if plan_result else False
            if not should_continue:
                break
            
            # Invalidate failed cache hit locates before replanning
            if self.task_cache:
                for i in range(task_count_before_run, len(runner.tasks)):
                    task = runner.tasks[i]
                    if (task.type == "Planning" and task.sub_type == "Locate" and 
                        task.hit_by and task.hit_by.from_ == "Cache"):
                        prompt = task.param.get("prompt") if isinstance(task.param, dict) else None
                        if prompt:
                            self.task_cache.mark_locate_cache_stale(prompt)
            
            # Increment replan count
            replan_count += 1
            if replan_count > replanning_cycle_limit:
                return session.append_error_plan(
                    f"Replanned {replanning_cycle_limit} times, exceeding the limit. "
                    f"Please configure a larger replanningCycleLimit."
                )
            
            if not conversation_history.pending_feedback_message.strip():
                time_string = time.strftime("%Y-%m-%d %H:%M:%S")
                conversation_history.pending_feedback_message = f"Time: {time_string}, I have finished the action previously planned."
        
        return ExecutionResult(
            output={"yaml_flow": yaml_flow, "output": output_string},
            runner=runner,
        )
    
    async def create_type_query_execution(
        self,
        query_type: str,  # 'Query', 'Boolean', 'Number', 'String', 'Assert'
        demand,
        model_runtime=None,
        opt: Optional[ServiceExtractOption] = None,
        multimodal_prompt=None,
    ) -> ExecutionResult:
        """Execute a type query (Query/Boolean/Number/String/Assert)"""
        opt = opt or ServiceExtractOption()
        demand_for_extract = self._demand_for_query_type(query_type, demand)
        
        session = self._create_execution_session(f"{query_type} - {demand}")
        runner = session.get_runner()
        
        query_task = ExecutionTaskApply(
            type="Insight",
            sub_type=query_type,
            param={"dom_included": opt.dom_included, "data_demand": demand},
        )
        query_task._executor = self._make_extract_executor(demand_for_extract, model_runtime, opt, multimodal_prompt)
        
        result = await session.append_and_run(query_task)
        
        if not result:
            raise TaskError("No result from query execution")
        
        output = result.get("output")
        thought = result.get("thought")
        
        return ExecutionResult(output=output, thought=thought, runner=runner)
    
    def _make_extract_executor(self, demand, model_runtime, opt: ServiceExtractOption, multimodal_prompt):
        async def executor(param, task_context):
            result = await self.service.extract(
                demand,
                model_runtime=model_runtime,
                opt=opt,
                multimodal_prompt=multimodal_prompt,
                context=task_context.get("ui_context"),
            )
            return {"output": result.get("data"), "thought": result.get("thought")}
        return executor

    def _demand_for_query_type(self, query_type: str, demand) -> str:
        if query_type in ("Boolean", "Assert", "WaitFor"):
            return f"Determine whether this statement is true on the page: {demand}. Return JSON data as a boolean."
        if query_type == "Number":
            return f"Answer this question with only a number in JSON data: {demand}"
        if query_type == "String":
            return f"Answer this question with a string in JSON data: {demand}"
        return demand
    
    async def wait_for(
        self,
        assertion,
        opt: Optional[Dict] = None,
        model_runtime=None,
    ) -> Any:
        """Wait for an assertion to become true"""
        opt = opt or {}
        timeout_ms = opt.get("timeout_ms", 15000)
        check_interval_ms = opt.get("check_interval_ms", 3000)
        
        session = self._create_execution_session(f"WaitFor - {assertion}")
        runner = session.get_runner()
        
        dom_included = opt.get("dom_included")
        screenshot_included = opt.get("screenshot_included")
        service_extract_opt = ServiceExtractOption(
            dom_included=cast(Union[bool, Literal["visible-only"]], dom_included if dom_included is not None else False),
            screenshot_included=cast(bool, screenshot_included if screenshot_included is not None else True),
        )
        
        overall_start_time = time.time()
        last_check_start = overall_start_time
        error_thought = ""
        
        while (last_check_start - overall_start_time) * 1000 <= timeout_ms:
            current_check_start = time.time()
            last_check_start = current_check_start
            
            demand_for_extract = self._demand_for_query_type("WaitFor", assertion)
            query_task = ExecutionTaskApply(
                type="Insight",
                sub_type="WaitFor",
                param={"dom_included": service_extract_opt.dom_included, "data_demand": assertion},
            )
            query_task._executor = self._make_extract_executor(demand_for_extract, model_runtime, service_extract_opt, None)
            
            result = await session.append_and_run(query_task)
            
            if result and result.get("output"):
                return ExecutionResult(output=None, runner=runner)
            
            error_thought = (
                result.get("thought", "") if result else 
                f"No result from assertion: {assertion}"
            )
            
            # Wait for check interval (sync sleep: we don't yield to the loop
            # so that this coroutine can be driven by both real event loops
            # and lightweight sync-pumped runners used by PyMidscene SDK).
            now = time.time()
            elapsed_ms = (now - current_check_start) * 1000
            if elapsed_ms < check_interval_ms:
                remaining_ms = check_interval_ms - elapsed_ms
                time.sleep(remaining_ms / 1000)
        
        return session.append_error_plan(f"waitFor timeout: {error_thought}")
