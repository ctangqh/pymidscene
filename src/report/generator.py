from __future__ import annotations

import asyncio
import copy
import re
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

    def adopt_saved_screenshot(self, file_path: Path) -> None:
        if self.output_format == "single-html":
            return
        if not self._meta:
            return
        old_rel, saved_ref = self._screenshot_store.register_saved_file(file_path)
        new_rel = saved_ref.path
        changed = False
        if old_rel and old_rel != new_rel:
            for execution in self._execution_by_id.values():
                self._replace_screenshot_path(execution, old_rel, new_rel)
                changed = True
        if new_rel and self._adopt_recent_execution_screenshots(saved_ref.model_dump()):
            changed = True
        if changed:
            self._cleanup_unreferenced_screenshot_files()
            self._rewrite_report_outputs()

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
                    preferred_filename = self._extract_preferred_screenshot_name(ui_context)
                    ref = self._screenshot_store.persist_base64(
                        base64_data,
                        preferred_filename=preferred_filename,
                    )
                    ui_context.pop("screenshot_base64", None)
                    ui_context.pop("screenshot", None)
                    ui_context.pop("filename", None)
                    ui_context.pop("preferred_filename", None)
                    ui_context.pop("screenshot_filename", None)
                    ui_context.pop("screenshot_path", None)
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
                    preferred_filename = self._extract_preferred_screenshot_name(shot)
                    ref = self._screenshot_store.persist_base64(
                        base64_data,
                        captured_at=captured_at,
                        preferred_filename=preferred_filename,
                    )
                    shot.pop("base64_data", None)
                    shot.pop("screenshot_base64", None)
                    shot.pop("filename", None)
                    shot.pop("preferred_filename", None)
                    shot.pop("screenshot_filename", None)
                    shot.pop("screenshot_path", None)
                    shot.update(ref.model_dump())

    @staticmethod
    def _extract_preferred_screenshot_name(payload: Dict[str, Any]) -> Optional[str]:
        for key in ("filename", "preferred_filename", "screenshot_filename", "screenshot_path", "path"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return Path(value).name
        return None

    def _rewrite_report_outputs(self) -> None:
        if not self._meta:
            return

        executions = list(self._execution_by_id.values())
        write_report_json(self._report_path, self._meta, executions)

        html = report_html_template(self.report_file_name)
        for execution in executions:
            html = insert_dump_into_html(
                html,
                {"meta": self._meta.model_dump(), "executions": [execution]},
            )
        self._report_path.write_text(html, encoding="utf-8")

        if self.persist_execution_dump:
            for index, execution in enumerate(executions, start=1):
                write_execution_json(
                    self._report_path,
                    index,
                    {"meta": self._meta.model_dump(), "execution": execution},
                )

    def _adopt_recent_execution_screenshots(self, saved_ref: Dict[str, Any]) -> bool:
        latest_execution = next(reversed(self._execution_by_id.values()), None)
        if not isinstance(latest_execution, dict):
            return False

        changed = False
        for screenshot in self._iter_screenshot_refs(latest_execution):
            path = screenshot.get("path")
            if not isinstance(path, str) or not self._is_auto_screenshot_path(path):
                continue
            captured_at = screenshot.get("captured_at", saved_ref.get("captured_at"))
            screenshot.clear()
            screenshot.update(saved_ref)
            screenshot["captured_at"] = captured_at
            changed = True
        return changed

    def _cleanup_unreferenced_screenshot_files(self) -> None:
        screenshot_dir = self._report_path.parent / "screenshots"
        if not screenshot_dir.exists():
            return

        referenced = set()
        for execution in self._execution_by_id.values():
            for screenshot in self._iter_screenshot_refs(execution):
                path = screenshot.get("path")
                if isinstance(path, str) and path.strip():
                    referenced.add(Path(path).name)

        for file_path in screenshot_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.name in referenced:
                continue
            if self._is_auto_screenshot_filename(file_path.name):
                file_path.unlink()

    @classmethod
    def _replace_screenshot_path(cls, value: Any, old_rel: str, new_rel: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "path" and item == old_rel:
                    value[key] = new_rel
                    continue
                cls._replace_screenshot_path(item, old_rel, new_rel)
            return
        if isinstance(value, list):
            for item in value:
                cls._replace_screenshot_path(item, old_rel, new_rel)

    @classmethod
    def _iter_screenshot_refs(cls, value: Any) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        cls._collect_screenshot_refs(value, refs)
        return refs

    @classmethod
    def _collect_screenshot_refs(cls, value: Any, refs: List[Dict[str, Any]]) -> None:
        if isinstance(value, dict):
            if value.get("type") == "pymidscene_screenshot_ref":
                refs.append(value)
            for item in value.values():
                cls._collect_screenshot_refs(item, refs)
            return
        if isinstance(value, list):
            for item in value:
                cls._collect_screenshot_refs(item, refs)

    @staticmethod
    def _is_auto_screenshot_path(path: str) -> bool:
        return ReportGenerator._is_auto_screenshot_filename(Path(path).name)

    @staticmethod
    def _is_auto_screenshot_filename(name: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{16,40}\.(png|jpe?g)", name, re.IGNORECASE))
