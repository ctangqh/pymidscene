from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .types import ReportFile, ReportMeta


def write_report_json(report_path: Path, meta: ReportMeta, executions: List[Dict[str, Any]]) -> Path:
    data = ReportFile(meta=meta, executions=executions).model_dump()
    out_path = report_path.parent / "report.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out_path


def write_execution_json(report_path: Path, index: int, payload: Dict[str, Any]) -> Path:
    dir_path = report_path.parent / "executions"
    dir_path.mkdir(parents=True, exist_ok=True)
    out_path = dir_path / f"{index:03d}.execution.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out_path

