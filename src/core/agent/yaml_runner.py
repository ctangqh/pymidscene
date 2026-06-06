import asyncio
import yaml
from typing import Optional, List, Dict, Any

from common.logger import logger
from common.exceptions import YAMLParseError, TaskError


class YamlTask:
    """A single task in a YAML script"""

    def __init__(self, name: str, flow: Optional[List[Dict]] = None):
        self.name = name
        self.flow = flow or []
        self.status: str = "pending"  # pending, running, completed, error
        self.error: Optional[Exception] = None
        self.result: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "flow": self.flow,
            "status": self.status,
            "error": str(self.error) if self.error else None,
            "result": self.result,
        }


class YamlScript:
    """Parsed YAML script containing multiple tasks"""

    def __init__(self, tasks: Optional[List[YamlTask]] = None):
        self.tasks = tasks or []

    @classmethod
    def from_string(cls, yaml_string: str, source: str = "yaml") -> "YamlScript":
        """Parse a YAML string into a YamlScript"""
        try:
            data = yaml.safe_load(yaml_string)
        except yaml.YAMLError as e:
            raise YAMLParseError(f"Failed to parse YAML: {e}")

        if not isinstance(data, dict):
            raise YAMLParseError("YAML root must be an object")

        tasks = []
        for task_data in data.get("tasks", []):
            if not isinstance(task_data, dict):
                continue
            name = task_data.get("name", "Unnamed")
            flow = task_data.get("flow", [])
            if isinstance(flow, list):
                tasks.append(YamlTask(name=name, flow=flow))

        return cls(tasks=tasks)

    @classmethod
    def from_file(cls, file_path: str) -> "YamlScript":
        """Load and parse a YAML file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            raise YAMLParseError(f"YAML file not found: {file_path}")
        except IOError as e:
            raise YAMLParseError(f"Failed to read YAML file: {e}")

        return cls.from_string(content, source=file_path)


class ScriptPlayer:
    """Executes a YamlScript using an Agent"""

    def __init__(self, script: YamlScript, context_provider):
        """
        Args:
            script: The YamlScript to execute
            context_provider: Async callable that returns {agent, freeFn}
        """
        self.script = script
        self.context_provider = context_provider
        self.status: str = "pending"  # pending, running, completed, error
        self.result: Dict[str, Any] = {}
        self.task_status_list: List[YamlTask] = script.tasks

    async def run(self) -> None:
        """Execute all tasks in the script"""
        self.status = "running"

        provider_result = self.context_provider()
        if asyncio.iscoroutine(provider_result):
            context = await provider_result
        else:
            context = provider_result
        agent = context.get("agent")

        if not agent:
            self.status = "error"
            raise TaskError("No agent provided in context for YAML execution")

        for task in self.task_status_list:
            task.status = "running"
            try:
                for step in task.flow:
                    step_type = step.get("type", "")
                    if step_type == "Tap":
                        await agent.ai_tap(step.get("locate", step.get("prompt", "")))
                    elif step_type == "Input":
                        await agent.ai_input(
                            step.get("locate", step.get("prompt", "")),
                            {"value": step.get("value", "")},
                        )
                    elif step_type == "Scroll":
                        await agent.ai_scroll(
                            step.get("locate"),
                            step.get("param", {}),
                        )
                    elif step_type == "Hover":
                        await agent.ai_hover(step.get("locate", step.get("prompt", "")))
                    elif step_type == "Finished":
                        pass
                    elif step_type == "Sleep":
                        time_ms = step.get("param", {}).get("timeMs", 1000)
                        await asyncio.sleep(time_ms / 1000)
                    else:
                        logger.warning(f"Unknown step type in YAML: {step_type}")

                task.status = "completed"

            except Exception as e:
                task.status = "error"
                task.error = e
                self.status = "error"
                raise

        self.status = "completed"


def build_detailed_locate_param(
    locate_prompt, opt: Optional[Dict] = None
) -> Dict[str, Any]:
    """Build a detailed locate parameter from prompt and options"""
    from ..types import DetailedLocateParam

    if isinstance(locate_prompt, DetailedLocateParam):
        return locate_prompt.model_dump()
    elif isinstance(locate_prompt, dict):
        return locate_prompt
    elif isinstance(locate_prompt, str):
        param = DetailedLocateParam(prompt=locate_prompt)
        if opt:
            for key in ("deep_locate", "cacheable", "xpath"):
                if key in opt:
                    setattr(param, key, opt[key])
        return param.model_dump()
    return {"prompt": str(locate_prompt)}


def parse_yaml_script(content: str, source: str = "yaml") -> YamlScript:
    """Parse a YAML script from string content"""
    return YamlScript.from_string(content, source)
