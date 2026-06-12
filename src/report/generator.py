from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.logger import logger

from .renderer_html import insert_dump_into_html, report_html_template
from .renderer_json import write_execution_json, write_report_json
from .screenshot_store import ScreenshotStore
from .types import ReportMeta
from .utils import sanitize_obj


@dataclass
class _PendingExecution:
    execution: Dict[str, Any]
    meta: ReportMeta
    attributes: Optional[Dict[str, Any]]


class ReportGenerator:
    def __init__(
        self,
        report_file_name: str,
        *,
        generate_report: bool = True,
        persist_execution_dump: bool = False,
        output_format: Optional[str] = None,
        auto_print_report_msg: bool = True,
        reuse_existing_report: bool = False,
    ) -> None:
        self.report_file_name = report_file_name
        self.generate_report = generate_report
        self.persist_execution_dump = persist_execution_dump
        self.output_format = output_format or "html-and-external-assets"
        self.auto_print_report_msg = auto_print_report_msg
        self.reuse_existing_report = reuse_existing_report

        self._lock = asyncio.Lock()
        self._pending: List[_PendingExecution] = []
        self._execution_by_id: Dict[str, Dict[str, Any]] = {}
        self._meta: Optional[ReportMeta] = None
        self._initialized = False
        self._destroyed = False
        self._execution_write_index = 0

        root = Path("./output/reports")
        root.mkdir(parents=True, exist_ok=True)

        if self.output_format == "single-html":
            self._report_path = root / f"{self.report_file_name}.html"
        else:
            report_dir = root / self.report_file_name
            report_dir.mkdir(parents=True, exist_ok=True)
            self._report_path = report_dir / "index.html"

        self._screenshot_store = ScreenshotStore(
            self._report_path,
            mode="inline" if self.output_format == "single-html" else "directory",
        )

    @classmethod
    def create(cls, report_file_name: str, options: Optional[Dict[str, Any]] = None) -> "ReportGenerator":
        options = options or {}
        return cls(
            report_file_name,
            generate_report=options.get("generate_report", True),
            persist_execution_dump=options.get("persist_execution_dump", False),
            output_format=options.get("output_format"),
            auto_print_report_msg=options.get("auto_print_report_msg", True),
            reuse_existing_report=options.get("reuse_existing_report", False),
        )

    def on_execution_update(
        self,
        execution: Optional[Dict[str, Any]],
        report_meta: Optional[Any] = None,
        report_attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.generate_report or self._destroyed:
            return
        if not execution:
            return

        meta = self._coerce_meta(report_meta)
        self._pending.append(_PendingExecution(execution=execution, meta=meta, attributes=report_attributes))

    async def flush(self) -> None:
        if not self.generate_report or self._destroyed:
            return

        async with self._lock:
            if not self._pending:
                return

            await self._init_if_needed()

            batch = self._pending
            self._pending = []
            for item in batch:
                sanitized_execution = self._process_execution(item.execution)
                exec_id = str(sanitized_execution.get("id") or "")
                if not exec_id:
                    exec_id = f"no-id-{int(time.time() * 1000)}"
                    sanitized_execution["id"] = exec_id

                self._execution_by_id[exec_id] = sanitized_execution
                self._meta = item.meta
                await self._append_execution_dump(sanitized_execution, item.meta)

                if self.persist_execution_dump:
                    self._execution_write_index += 1
                    write_execution_json(
                        self._report_path,
                        self._execution_write_index,
                        {"meta": item.meta.model_dump(), "execution": sanitized_execution},
                    )

            if self._meta is not None:
                write_report_json(
                    self._report_path,
                    self._meta,
                    list(self._execution_by_id.values()),
                )

    async def finalize(self) -> Optional[str]:
        await self.flush()
        self._destroyed = True
        return str(self._report_path) if self._report_path.exists() else None

    def get_report_path(self) -> Optional[str]:
        return str(self._report_path) if self._report_path else None

    async def _init_if_needed(self) -> None:
        if self._initialized and self.reuse_existing_report:
            return
        if self._initialized:
            return
        if self.output_format == "single-html":
            if not self._report_path.exists() or not self.reuse_existing_report:
                self._report_path.write_text(report_html_template(self.report_file_name), encoding="utf-8")
        else:
            if not self._report_path.exists() or not self.reuse_existing_report:
                self._report_path.write_text(report_html_template(self.report_file_name), encoding="utf-8")
        self._initialized = True
        if self.auto_print_report_msg:
            logger.info(f"Report generated at: {self._report_path}")

    async def _append_execution_dump(self, execution: Dict[str, Any], meta: ReportMeta) -> None:
        payload = {"meta": meta.model_dump(), "executions": [execution]}
        html = self._report_path.read_text(encoding="utf-8")
        self._report_path.write_text(insert_dump_into_html(html, payload), encoding="utf-8")

    def _coerce_meta(self, report_meta: Any) -> ReportMeta:
        if isinstance(report_meta, ReportMeta):
            return report_meta
        if hasattr(report_meta, "model_dump"):
            try:
                return ReportMeta(**report_meta.model_dump())
            except Exception:
                pass
        if isinstance(report_meta, dict):
            try:
                return ReportMeta(**report_meta)
            except Exception:
                pass
        return ReportMeta()

    def _process_execution(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        execution_copy = copy.deepcopy(execution)
        tasks = execution_copy.get("tasks")
        if isinstance(tasks, list):
            for task in tasks:
                if not isinstance(task, dict):
                    continue
                self._process_task_screenshot(task)

        sanitized = sanitize_obj(execution_copy, max_text_len=2000)
        if not isinstance(sanitized, dict):
            return {"id": str(execution.get("id") or ""), "raw": sanitized}
        return sanitized

    def _process_task_screenshot(self, task: Dict[str, Any]) -> None:
        log = task.get("log")
        if isinstance(log, dict):
            ui_context = log.get("ui_context")
            if isinstance(ui_context, dict):
                base64_data = ui_context.get("screenshot_base64") or ui_context.get("screenshot")
                if isinstance(base64_data, str) and base64_data.strip():
                    ref = self._screenshot_store.persist_base64(base64_data)
                    ui_context.pop("screenshot_base64", None)
                    ui_context.pop("screenshot", None)
                    ui_context["screenshot"] = ref.model_dump()

        recorder = task.get("recorder")
        if isinstance(recorder, list):
            for item in recorder:
                if not isinstance(item, dict):
                    continue
                shot = item.get("screenshot")
                if not isinstance(shot, dict):
                    continue
                base64_data = shot.get("base64_data") or shot.get("screenshot_base64")
                if isinstance(base64_data, str) and base64_data.strip():
                    captured_at = shot.get("captured_at")
                    ref = self._screenshot_store.persist_base64(base64_data, captured_at=captured_at)
                    shot.pop("base64_data", None)
                    shot.pop("screenshot_base64", None)
                    shot.update(ref.model_dump())
