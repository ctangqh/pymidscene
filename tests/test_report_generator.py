from __future__ import annotations

import base64
import os
import shutil
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from report import ReportGenerator


def _png_base64(size=(20, 12), color="red") -> str:
    img = Image.new("RGB", size, color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_report_generator_writes_directory_mode_html_json_and_screenshots():
    name = f"test-report-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": True,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    screenshot_b64 = _png_base64()
    execution = {
        "id": "exec-1",
        "log_time": time.time(),
        "name": "demo",
        "tasks": [
            {
                "task_id": "t1",
                "type": "Action Space",
                "sub_type": "Click",
                "status": "finished",
                "log": {"ui_context": {"shot_size": {"width": 20, "height": 12}, "screenshot_base64": screenshot_b64}},
                "param": {"api_key": "sk-test-123456"},
            }
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.flush())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    assert rp.exists()
    assert rp.name == "index.html"
    assert (rp.parent / "report.json").exists()
    assert (rp.parent / "screenshots").exists()
    assert len(list((rp.parent / "screenshots").glob("*.png"))) == 1
    assert (rp.parent / "executions" / "001.execution.json").exists()

    report_json = (rp.parent / "report.json").read_text(encoding="utf-8")
    assert "sk-test-123456" not in report_json
    assert "\"api_key\"" in report_json

    shutil.rmtree(rp.parent, ignore_errors=True)


def test_report_generator_handles_large_base64_screenshot_without_truncation():
    name = f"test-report-large-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    screenshot_b64 = _png_base64(size=(420, 240), color="blue")
    execution = {
        "id": "exec-large",
        "log_time": time.time(),
        "name": "demo-large",
        "tasks": [
            {
                "task_id": "t-large",
                "type": "Action Space",
                "sub_type": "Input",
                "status": "finished",
                "log": {"ui_context": {"shot_size": {"width": 420, "height": 240}, "screenshot_base64": screenshot_b64}},
                "param": {"prompt": "x" * 3000},
            }
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.finalize())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    assert rp.exists()
    assert len(list((rp.parent / "screenshots").glob("*.png"))) == 1

    report_json = (rp.parent / "report.json").read_text(encoding="utf-8")
    assert "screenshot_base64" not in report_json
    assert "truncated" in report_json

    shutil.rmtree(rp.parent, ignore_errors=True)


if __name__ == "__main__":
    test_report_generator_writes_directory_mode_html_json_and_screenshots()
    test_report_generator_handles_large_base64_screenshot_without_truncation()
    print("test_report_generator.py: ok")
