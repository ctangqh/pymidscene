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

from core.agent.agent import Agent
from report import ReportGenerator


def _png_base64(size=(20, 12), color="red") -> str:
    img = Image.new("RGB", size, color=color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class _FakeDevice:
    interface_type = "test-device"

    def action_space(self):
        return []

    def screenshot_base64(self):
        return _png_base64(color="orange")


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


def test_report_generator_prefers_business_filename_for_recorder_screenshot():
    name = f"test-report-named-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    screenshot_b64 = _png_base64(color="green")
    execution = {
        "id": "exec-named",
        "log_time": time.time(),
        "name": "demo-named",
        "tasks": [
            {
                "task_id": "t-named",
                "type": "Log",
                "sub_type": "Screenshot",
                "status": "finished",
                "recorder": [
                    {
                        "type": "screenshot",
                        "ts": time.time(),
                        "screenshot": {
                            "captured_at": time.time(),
                            "base64_data": screenshot_b64,
                            "filename": "02_text_entered.png",
                        },
                    }
                ],
            }
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.finalize())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    assert (rp.parent / "screenshots" / "02_text_entered.png").exists()
    assert len(list((rp.parent / "screenshots").glob("*.png"))) == 1

    report_json = (rp.parent / "report.json").read_text(encoding="utf-8")
    assert "02_text_entered.png" in report_json

    shutil.rmtree(rp.parent, ignore_errors=True)


def test_report_generator_adds_suffix_when_business_filename_conflicts():
    name = f"test-report-conflict-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    execution = {
        "id": "exec-conflict",
        "log_time": time.time(),
        "name": "demo-conflict",
        "tasks": [
            {
                "task_id": "t-conflict",
                "type": "Log",
                "sub_type": "Screenshot",
                "status": "finished",
                "recorder": [
                    {
                        "type": "screenshot",
                        "ts": time.time(),
                        "screenshot": {
                            "captured_at": time.time(),
                            "base64_data": _png_base64(color="purple"),
                            "filename": "same_name.png",
                        },
                    },
                    {
                        "type": "screenshot",
                        "ts": time.time(),
                        "screenshot": {
                            "captured_at": time.time(),
                            "base64_data": _png_base64(color="yellow"),
                            "filename": "same_name.png",
                        },
                    },
                ],
            }
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.finalize())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    assert (rp.parent / "screenshots" / "same_name.png").exists()
    assert (rp.parent / "screenshots" / "same_name_2.png").exists()
    assert len(list((rp.parent / "screenshots").glob("*.png"))) == 2

    shutil.rmtree(rp.parent, ignore_errors=True)


def test_report_generator_adopts_manual_screenshot_name_for_existing_report_file():
    name = f"test-report-adopt-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    screenshot_b64 = _png_base64(color="pink")
    execution = {
        "id": "exec-adopt",
        "log_time": time.time(),
        "name": "demo-adopt",
        "tasks": [
            {
                "task_id": "t-adopt",
                "type": "Action Space",
                "sub_type": "Input",
                "status": "finished",
                "log": {"ui_context": {"shot_size": {"width": 20, "height": 12}, "screenshot_base64": screenshot_b64}},
            }
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.flush())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    initial_files = list((rp.parent / "screenshots").glob("*.png"))
    assert len(initial_files) == 1
    auto_named_file = initial_files[0]

    manual_file = rp.parent / "screenshots" / "02_text_entered.png"
    manual_file.write_bytes(base64.b64decode(screenshot_b64))
    gen.adopt_saved_screenshot(manual_file)

    assert manual_file.exists()
    assert not auto_named_file.exists()

    report_json = (rp.parent / "report.json").read_text(encoding="utf-8")
    assert "02_text_entered.png" in report_json
    assert auto_named_file.name not in report_json

    report_html = rp.read_text(encoding="utf-8")
    assert "02_text_entered.png" in report_html
    assert auto_named_file.name not in report_html

    shutil.rmtree(rp.parent, ignore_errors=True)


def test_report_generator_replaces_latest_auto_screenshots_with_manual_named_file():
    name = f"test-report-replace-latest-{int(time.time() * 1000)}"
    gen = ReportGenerator.create(
        name,
        {
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
        },
    )

    execution = {
        "id": "exec-replace-latest",
        "log_time": time.time(),
        "name": "demo-replace-latest",
        "tasks": [
            {
                "task_id": "t-plan",
                "type": "Planning",
                "sub_type": "Locate",
                "status": "finished",
                "log": {"ui_context": {"shot_size": {"width": 20, "height": 12}, "screenshot_base64": _png_base64(color="red")}},
            },
            {
                "task_id": "t-action",
                "type": "Action Space",
                "sub_type": "Tap",
                "status": "finished",
                "log": {"ui_context": {"shot_size": {"width": 20, "height": 12}, "screenshot_base64": _png_base64(color="blue")}},
            },
        ],
    }

    gen.on_execution_update(execution, {"group_name": "g", "sdk_version": "0.1.0", "device_type": "win"})

    import asyncio

    asyncio.run(gen.flush())
    report_path = gen.get_report_path()
    assert report_path is not None

    rp = Path(report_path)
    initial_auto_files = sorted(path.name for path in (rp.parent / "screenshots").glob("*.png"))
    assert len(initial_auto_files) == 2

    manual_file = rp.parent / "screenshots" / "02_text_entered.png"
    manual_file.write_bytes(base64.b64decode(_png_base64(color="green")))
    gen.adopt_saved_screenshot(manual_file)

    final_pngs = sorted(path.name for path in (rp.parent / "screenshots").glob("*.png"))
    assert final_pngs == ["02_text_entered.png"]

    report_json = (rp.parent / "report.json").read_text(encoding="utf-8")
    assert report_json.count("02_text_entered.png") == 2
    for old_name in initial_auto_files:
        assert old_name not in report_json

    shutil.rmtree(rp.parent, ignore_errors=True)


def test_agent_record_to_report_keeps_business_filename():
    report_name = f"test-agent-report-{int(time.time() * 1000)}"
    agent = Agent(
        _FakeDevice(),
        opts={
            "generate_report": True,
            "persist_execution_dump": False,
            "output_format": "html-and-external-assets",
            "auto_print_report_msg": False,
            "report_file_name": report_name,
        },
        llm=None,
        vision_llm=None,
    )

    import asyncio

    asyncio.run(agent.record_to_report("named-shot", {"filename": "03_final_state.png"}))
    asyncio.run(agent.destroy())

    report_path = agent.report_file
    assert report_path is not None

    rp = Path(report_path)
    assert (rp.parent / "screenshots" / "03_final_state.png").exists()

    shutil.rmtree(rp.parent, ignore_errors=True)


if __name__ == "__main__":
    test_report_generator_writes_directory_mode_html_json_and_screenshots()
    test_report_generator_handles_large_base64_screenshot_without_truncation()
    test_report_generator_prefers_business_filename_for_recorder_screenshot()
    test_report_generator_adds_suffix_when_business_filename_conflicts()
    test_report_generator_adopts_manual_screenshot_name_for_existing_report_file()
    test_report_generator_replaces_latest_auto_screenshots_with_manual_named_file()
    test_agent_record_to_report_keeps_business_filename()
    print("test_report_generator.py: ok")
