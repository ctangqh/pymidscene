import asyncio
import time
import uuid
from typing import Optional, List, Dict, Any, Callable

from ..types import (
    ExecutionTask, ExecutionTaskApply, ExecutionTaskStatus,
    ExecutionTaskTiming, UIContext
)
from .context_parser import common_context_parser
from common.logger import logger
from common.exceptions import TaskError


class TaskExecutionError(Exception):
    """Error raised when a task execution fails"""
    def __init__(self, message: str, error_task: Optional[ExecutionTask] = None):
        super().__init__(message)
        self.error_task = error_task


class TaskRunner:
    """
    Simple task runner that manages and executes a list of tasks sequentially.
    Port of TS TaskRunner (simplified).
    """
    
    def __init__(self, name: str, context_provider: Callable, options: Optional[Dict] = None):
        self.name = name
        self.context_provider = context_provider
        self.options = options or {}
        self.tasks: List[ExecutionTask] = []
        self._runner_id: str = str(uuid.uuid4())
        self._error_state = False
        self._latest_error_task: Optional[ExecutionTask] = None
        self._on_task_update = options.get("on_task_update") if options else None
        self._on_task_start = options.get("on_task_start") if options else None
    
    async def append(self, task_applies, allow_when_error: bool = False) -> None:
        """Append tasks to the runner"""
        if self._error_state and not allow_when_error:
            raise TaskError(f"Runner is in error state, cannot append tasks")
        
        if not isinstance(task_applies, list):
            task_applies = [task_applies]
        
        for task_apply in task_applies:
            if isinstance(task_apply, dict):
                task_apply = ExecutionTaskApply(**task_apply)
            task = ExecutionTask(
                task_id=str(uuid.uuid4()),
                type=task_apply.type,
                sub_type=task_apply.sub_type,
                param=task_apply.param,
                thought=task_apply.thought,
                status=ExecutionTaskStatus.PENDING,
                timing=ExecutionTaskTiming(start=time.time()),
            )
            executor = getattr(task_apply, '_executor', None)
            if executor:
                task._executor = executor
            self.tasks.append(task)
    
    async def append_and_flush(self, task_applies, allow_when_error: bool = False):
        """Append tasks and execute them"""
        await self.append(task_applies, allow_when_error=allow_when_error)
        return await self.flush(allow_when_error=allow_when_error)
    
    async def flush(self, allow_when_error: bool = False):
        """Execute all pending tasks"""
        result = None
        for task in self.tasks:
            if task.status == ExecutionTaskStatus.FINISHED:
                continue
            
            task.status = ExecutionTaskStatus.RUNNING
            task.timing.start = task.timing.start or time.time()
            
            if self._on_task_start:
                try:
                    self._on_task_start(task)
                except Exception as e:
                    logger.debug(f"on_task_start callback error: {e}")
            
            try:
                # Execute the task
                executor = getattr(task, '_executor', None)
                ui_context: Optional[UIContext] = None
                try:
                    ui_context = await self.context_provider()
                except Exception:
                    ui_context = None

                if isinstance(task.log, dict):
                    task_log = task.log
                else:
                    task_log = {}
                    task.log = task_log
                if ui_context is not None:
                    task_log["ui_context"] = {
                        "shot_size": getattr(ui_context, "shot_size", None),
                        "screenshot_base64": getattr(ui_context, "screenshot", "") or "",
                    }

                if executor:
                    exec_result = await executor(task.param, {
                        "task": task,
                        "ui_context": ui_context,
                        "element": None,
                    })
                    
                    if exec_result:
                        if isinstance(exec_result, dict):
                            task.output = exec_result.get("output")
                            if "hit_by" in exec_result:
                                task.hit_by = exec_result["hit_by"]
                        result = exec_result
                
                task.status = ExecutionTaskStatus.FINISHED
                
            except Exception as e:
                task.status = ExecutionTaskStatus.ERROR
                task.error = str(e)
                task.error_message = str(e)
                self._error_state = True
                self._latest_error_task = task
                
                if self._on_task_update:
                    try:
                        result_cb = self._on_task_update(self, TaskExecutionError(str(e), task))
                        if asyncio.iscoroutine(result_cb):
                            await result_cb
                    except Exception:
                        pass
                raise
            
            finally:
                task.timing.end = time.time()
                task.timing.cost = task.timing.end - task.timing.start
            
            if self._on_task_update:
                try:
                    result_cb = self._on_task_update(self)
                    if asyncio.iscoroutine(result_cb):
                        await result_cb
                except Exception:
                    pass
        
        return result
    
    def is_in_error_state(self) -> bool:
        return self._error_state
    
    def latest_error_task(self) -> Optional[ExecutionTask]:
        return self._latest_error_task
    
    def append_error_plan(self, error_msg: str):
        """Append an error plan task"""
        error_task = ExecutionTask(
            task_id=str(uuid.uuid4()),
            type="Error",
            sub_type="ErrorPlan",
            param={"error": error_msg},
            status=ExecutionTaskStatus.ERROR,
            error=error_msg,
            error_message=error_msg,
            timing=ExecutionTaskTiming(start=time.time(), end=time.time()),
        )
        self.tasks.append(error_task)
        self._error_state = True
        self._latest_error_task = error_task
        return {"output": None, "runner": self}
    
    def dump(self) -> Dict[str, Any]:
        """Dump execution state"""
        return {
            "id": self._runner_id,
            "log_time": time.time(),
            "name": self.name,
            "tasks": [t.model_dump() for t in self.tasks],
        }


class ExecutionSession:
    """
    Thin wrapper around TaskRunner that represents a single linear execution run.
    Port of TS ExecutionSession.
    """
    
    def __init__(
        self,
        name: str,
        context_provider: Callable,
        options: Optional[Dict] = None,
    ):
        options = options or {}
        self.runner = TaskRunner(
            name,
            context_provider,
            {
                "on_task_start": options.get("on_task_start"),
                "on_task_update": options.get("on_task_update"),
            }
        )
    
    async def append(self, tasks, options: Optional[Dict] = None) -> None:
        options = options or {}
        await self.runner.append(tasks, allow_when_error=options.get("allow_when_error", False))
    
    async def append_and_run(self, tasks, options: Optional[Dict] = None):
        options = options or {}
        return await self.runner.append_and_flush(tasks, allow_when_error=options.get("allow_when_error", False))
    
    async def run(self, options: Optional[Dict] = None):
        options = options or {}
        return await self.runner.flush(allow_when_error=options.get("allow_when_error", False))
    
    def is_in_error_state(self) -> bool:
        return self.runner.is_in_error_state()
    
    def latest_error_task(self) -> Optional[ExecutionTask]:
        return self.runner.latest_error_task()
    
    def append_error_plan(self, error_msg: str):
        return self.runner.append_error_plan(error_msg)
    
    def get_runner(self) -> TaskRunner:
        return self.runner
