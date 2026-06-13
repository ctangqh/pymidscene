from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


def _load_module(file_name: str, module_name: str):
    module_path = Path(__file__).resolve().parents[1] / "scripts" / file_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_report_json(report_dir: Path, screenshot_name: str) -> None:
    data = {
        "meta": {"name": report_dir.name},
        "executions": [
            {
                "id": f"exec-{report_dir.name}",
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
        ],
    }
    (report_dir / "report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _touch_complete_artifacts(screenshot_dir: Path, stem: str) -> None:
    for name in [
        f"{stem}.png",
        f"{stem}.json",
        f"{stem}_raw.json",
        f"{stem}_debug.png",
        f"{stem}_raw_debug.png",
        f"{stem}_debug.json",
    ]:
        (screenshot_dir / name).write_text("x", encoding="utf-8")


def test_find_latest_report_dir_uses_most_recent_directory(tmp_path: Path):
    module = _load_module("check_latest_report.py", "check_latest_report")

    reports_dir = tmp_path / "reports"
    first = reports_dir / "report-a"
    second = reports_dir / "report-b"
    (first / "screenshots").mkdir(parents=True)
    (second / "screenshots").mkdir(parents=True)
    _write_report_json(first, "01_a.png")
    _write_report_json(second, "02_b.png")

    now = time.time()
    old_time = now - 60
    new_time = now
    first.touch()
    second.touch()
    import os
    os.utime(first, (old_time, old_time))
    os.utime(second, (new_time, new_time))

    latest = module.find_latest_report_dir(reports_dir)

    assert latest == second


def test_check_latest_report_returns_audit_for_latest_directory(tmp_path: Path):
    module = _load_module("check_latest_report.py", "check_latest_report")

    reports_dir = tmp_path / "reports"
    old_report = reports_dir / "report-old"
    new_report = reports_dir / "report-new"
    old_screenshots = old_report / "screenshots"
    new_screenshots = new_report / "screenshots"
    old_screenshots.mkdir(parents=True)
    new_screenshots.mkdir(parents=True)

    _write_report_json(old_report, "01_old.png")
    _write_report_json(new_report, "02_text_entered.png")
    _touch_complete_artifacts(old_screenshots, "01_old")
    _touch_complete_artifacts(new_screenshots, "02_text_entered")

    now = time.time()
    import os
    os.utime(old_report, (now - 60, now - 60))
    os.utime(new_report, (now, now))

    result = module.check_latest_report(reports_dir)

    assert result["latest_report_dir"] == str(new_report.resolve())
    assert result["audit"]["ok"] is True
    assert result["audit"]["referenced_screenshots"] == ["02_text_entered.png"]


def test_format_latest_report_summary_highlights_missing_and_orphans(tmp_path: Path):
    module = _load_module("check_latest_report.py", "check_latest_report")

    reports_dir = tmp_path / "reports"
    report_dir = reports_dir / "report-summary"
    screenshot_dir = report_dir / "screenshots"
    screenshot_dir.mkdir(parents=True)

    _write_report_json(report_dir, "02_text_entered.png")
    (screenshot_dir / "02_text_entered.png").write_text("x", encoding="utf-8")
    (screenshot_dir / "02_text_entered.json").write_text("x", encoding="utf-8")
    (screenshot_dir / "stray.png").write_text("x", encoding="utf-8")

    result = module.check_latest_report(reports_dir)
    summary = module.format_latest_report_summary(result)

    assert "latest report:" in summary
    assert "failed steps: 1" in summary
    assert "orphan files: 1" in summary
    assert "4 missing categories" in summary
    assert "raw_json" in summary
    assert "debug_image" in summary
    assert "stray.png" in summary
    assert "result: FAILED" in summary


def run_all_check_latest_report_checks():
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        test_find_latest_report_dir_uses_most_recent_directory(tmp_path)
        test_check_latest_report_returns_audit_for_latest_directory(tmp_path)
        test_format_latest_report_summary_highlights_missing_and_orphans(tmp_path)


if __name__ == "__main__":
    run_all_check_latest_report_checks()
    print("test_check_latest_report.py: ok")
