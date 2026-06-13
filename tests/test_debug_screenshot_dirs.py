from pathlib import Path
from tempfile import TemporaryDirectory

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.anomaly_guard import UIAnomalyGuard
from core.locator import ElementLocator


class _FakeDevice:
    interface_type = "test-device"


def test_locator_prefers_device_report_screenshot_dir():
    with TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "report" / "screenshots"
        device = _FakeDevice()
        device._pymidscene_report_screenshot_dir_resolver = lambda: target_dir

        locator = ElementLocator(device, llm=None)

        assert locator._get_debug_screenshot_dir() == target_dir
        assert target_dir.exists()


def test_anomaly_guard_prefers_device_report_screenshot_dir():
    with TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "report" / "screenshots"
        device = _FakeDevice()
        device._pymidscene_report_screenshot_dir_resolver = lambda: target_dir

        guard = UIAnomalyGuard(device)

        assert guard._get_debug_screenshot_dir() == target_dir
        assert target_dir.exists()


if __name__ == "__main__":
    test_locator_prefers_device_report_screenshot_dir()
    test_anomaly_guard_prefers_device_report_screenshot_dir()
    print("test_debug_screenshot_dirs.py: ok")
