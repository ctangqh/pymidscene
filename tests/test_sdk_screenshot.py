from pathlib import Path
from types import SimpleNamespace

from common.config import settings
from sdk.pymidscene import PyMidscene


class _FakeDevice:
    interface_type = "test-device"

    def __init__(self):
        self.last_save_path: Path | None = None

    def screenshot(self, save_path: Path, **kwargs):
        self.last_save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = b"fake-image"
        save_path.write_bytes(data)
        return data


def _build_sdk(tmp_path: Path) -> PyMidscene:
    sdk = PyMidscene.__new__(PyMidscene)
    sdk.device = _FakeDevice()
    sdk.debug = False
    sdk._last_screenshot_saved_at = 0.0
    sdk._get_report_screenshot_dir = lambda: tmp_path
    sdk._handle_error = lambda operation, exception, context=None: (_ for _ in ()).throw(exception)
    return sdk


def test_screenshot_uses_given_filename(tmp_path: Path):
    sdk = _build_sdk(tmp_path)

    sdk.screenshot("02_text_entered.png")

    assert (tmp_path / "02_text_entered.png").exists()


def test_screenshot_generates_system_filename_when_missing(tmp_path: Path):
    sdk = _build_sdk(tmp_path)

    sdk.screenshot()

    files = list(tmp_path.glob("screenshot_*.png"))
    assert len(files) == 1


def test_screenshot_uses_current_report_screenshots_dir(tmp_path: Path):
    sdk = PyMidscene.__new__(PyMidscene)
    sdk.device = _FakeDevice()
    sdk.debug = False
    sdk._handle_error = lambda operation, exception, context=None: (_ for _ in ()).throw(exception)
    sdk._last_screenshot_saved_at = 0.0
    sdk._loop = None
    sdk._launched = False
    sdk.context = {}
    sdk.locator = None
    sdk.llm = None
    sdk.vision_model = None
    report_dir = tmp_path / "output" / "reports" / "demo-report"
    report_dir.mkdir(parents=True, exist_ok=True)
    sdk._agent = SimpleNamespace(
        _report_generator=SimpleNamespace(_report_path=report_dir / "index.html")
    )

    sdk.screenshot("02_text_entered.png")

    assert sdk.device.last_save_path is not None
    assert sdk.device.last_save_path == report_dir / "screenshots" / "02_text_entered.png"
    assert (report_dir / "screenshots" / "02_text_entered.png").exists()


def test_screenshot_adopts_recent_debug_artifacts_to_business_name(tmp_path: Path):
    original_report_save_dir = settings.REPORT_SAVE_DIR
    try:
        settings.REPORT_SAVE_DIR = str(tmp_path / "output" / "reports")

        sdk = PyMidscene.__new__(PyMidscene)
        sdk.device = _FakeDevice()
        sdk.debug = False
        sdk._handle_error = lambda operation, exception, context=None: (_ for _ in ()).throw(exception)
        sdk._last_screenshot_saved_at = 0.0
        sdk._loop = None
        sdk._launched = False
        sdk.context = {}
        sdk.locator = None
        sdk.llm = None
        sdk.vision_model = None

        report_dir = tmp_path / "output" / "reports" / "demo-report-adopt"
        report_screenshot_dir = report_dir / "screenshots"
        root_screenshot_dir = Path(settings.REPORT_SAVE_DIR) / "screenshots"
        report_screenshot_dir.mkdir(parents=True, exist_ok=True)
        root_screenshot_dir.mkdir(parents=True, exist_ok=True)

        sdk._agent = SimpleNamespace(
            _report_generator=SimpleNamespace(
                _report_path=report_dir / "index.html",
                adopt_saved_screenshot=lambda path: None,
            )
        )

        (report_screenshot_dir / "123_after_Tap_debug.png").write_bytes(b"debug-image")
        (report_screenshot_dir / "123_after_Tap_raw_debug.png").write_bytes(b"raw-debug-image")
        (report_screenshot_dir / "123_after_Tap_debug.json").write_text("{}", encoding="utf-8")
        (root_screenshot_dir / "123_\u6587\u672c\u7f16\u8f91\u533a.json").write_text("{}", encoding="utf-8")
        (root_screenshot_dir / "123_\u6587\u672c\u7f16\u8f91\u533a_raw.json").write_text("{}", encoding="utf-8")

        sdk.screenshot("02_text_entered.png")

        report_files = sorted(path.name for path in report_screenshot_dir.iterdir() if path.is_file())
        assert (report_screenshot_dir / "02_text_entered_debug.png").exists(), report_files
        assert (report_screenshot_dir / "02_text_entered_raw_debug.png").exists(), report_files
        assert (report_screenshot_dir / "02_text_entered_debug.json").exists(), report_files
        assert (report_screenshot_dir / "02_text_entered.json").exists(), report_files
        assert (report_screenshot_dir / "02_text_entered_raw.json").exists(), report_files
        assert not (root_screenshot_dir / "123_\u6587\u672c\u7f16\u8f91\u533a.json").exists()
        assert not (root_screenshot_dir / "123_\u6587\u672c\u7f16\u8f91\u533a_raw.json").exists()
    finally:
        settings.REPORT_SAVE_DIR = original_report_save_dir


def run_all_sdk_screenshot_checks():
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp_dir:
        tmp_path = Path(temp_dir)
        test_screenshot_uses_given_filename(tmp_path)
        test_screenshot_generates_system_filename_when_missing(tmp_path)
        test_screenshot_uses_current_report_screenshots_dir(tmp_path)
        test_screenshot_adopts_recent_debug_artifacts_to_business_name(tmp_path)


if __name__ == "__main__":
    run_all_sdk_screenshot_checks()
    print("sdk screenshot checks passed")
