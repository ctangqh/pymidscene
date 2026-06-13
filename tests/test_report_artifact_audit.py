from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_audit_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "audit_report_artifacts.py"
    spec = importlib.util.spec_from_file_location("audit_report_artifacts", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_report_json(report_dir: Path, screenshot_names: list[str]) -> None:
    executions = []
    for index, screenshot_name in enumerate(screenshot_names, start=1):
        executions.append(
            {
                "id": f"exec-{index}",
                "tasks": [
                    {
                        "log": {
                            "ui_context": {
                                "screenshot_ref": {
                                    "type": "pymidscene_screenshot_ref",
                                    "path": f"./screenshots/{screenshot_name}",
                                }
                            }
                        }
                    }
                ],
            }
        )

    report_data = {
        "meta": {"name": "demo"},
        "executions": executions,
    }
    (report_dir / "report.json").write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_audit_report_dir_passes_when_artifacts_are_complete(tmp_path: Path):
    module = _load_audit_module()
    report_dir = tmp_path / "report-complete"
    screenshot_dir = report_dir / "screenshots"
    screenshot_dir.mkdir(parents=True)

    _write_report_json(report_dir, ["02_text_entered.png"])

    for file_name in [
        "02_text_entered.png",
        "02_text_entered.json",
        "02_text_entered_raw.json",
        "02_text_entered_debug.png",
        "02_text_entered_raw_debug.png",
        "02_text_entered_debug.json",
    ]:
        (screenshot_dir / file_name).write_text("x", encoding="utf-8")

    result = module.audit_report_dir(report_dir)

    assert result["ok"] is True
    assert result["has_missing"] is False
    assert result["has_orphans"] is False
    assert result["orphan_files"] == []
    assert result["steps"][0]["missing"] == []


def test_audit_report_dir_reports_missing_and_orphan_files(tmp_path: Path):
    module = _load_audit_module()
    report_dir = tmp_path / "report-missing"
    screenshot_dir = report_dir / "screenshots"
    screenshot_dir.mkdir(parents=True)

    _write_report_json(report_dir, ["02_text_entered.png"])

    for file_name in [
        "02_text_entered.png",
        "02_text_entered.json",
        "stray_hash.png",
        "01_notepad_started.png",
    ]:
        (screenshot_dir / file_name).write_text("x", encoding="utf-8")

    result = module.audit_report_dir(report_dir)
    summary = module.format_audit_result(result)

    assert result["ok"] is False
    assert result["has_missing"] is True
    assert result["has_orphans"] is True
    assert result["steps"][0]["missing"] == [
        "02_text_entered_raw.json",
        "02_text_entered_debug.png",
        "02_text_entered_raw_debug.png",
        "02_text_entered_debug.json",
    ]
    assert result["orphan_files"] == ["01_notepad_started.png", "stray_hash.png"]
    assert "02_text_entered_raw.json" in summary
    assert "orphan files:" in summary


def run_all_report_artifact_audit_checks():
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        test_audit_report_dir_passes_when_artifacts_are_complete(tmp_path)
        test_audit_report_dir_reports_missing_and_orphan_files(tmp_path)


if __name__ == "__main__":
    run_all_report_artifact_audit_checks()
    print("test_report_artifact_audit.py: ok")
