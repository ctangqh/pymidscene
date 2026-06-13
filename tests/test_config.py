from pathlib import Path

import yaml
import os

from common.config import APP_CONFIG_PATH, Settings


def _read_env_keys(file_path: Path) -> set[str]:
    keys = set()
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_report_screenshot_dir_follows_report_dir():
    settings = Settings()

    assert settings.report_dir == Path(settings.REPORT_SAVE_DIR)
    assert settings.report_screenshot_dir == Path(settings.REPORT_SAVE_DIR) / "screenshots"
    assert Path(settings.REPORT_SCREENSHOT_SAVE_DIR) == settings.report_screenshot_dir
    assert Path(settings.LOG_FILE_DEBUG) == Path("./logs/run_debug.log")
    assert settings.llm_config.provider == "openai"
    assert settings.llm_config.model == "Doubao-Seed-2.0-pro"


def test_app_yaml_contains_non_secret_runtime_config():
    assert APP_CONFIG_PATH.name == "app.yaml"
    assert APP_CONFIG_PATH.exists()

    config_data = yaml.safe_load(APP_CONFIG_PATH.read_text(encoding="utf-8"))

    assert "REPORT_SAVE_DIR" in config_data
    assert "MCP_SERVERS" in config_data
    assert "REPORT_SCREENSHOT_SAVE_DIR" not in config_data
    assert "LOG_FILE_DEBUG" not in config_data
    assert "LLM_BASE_URL" not in config_data
    assert "VISION_BASE_URL" not in config_data
    assert "LLM_PROVIDER" not in config_data
    assert "VISION_PROVIDER" not in config_data
    assert config_data["LLM_MODEL"] == "openai/Doubao-Seed-2.0-pro"
    env_keys = _read_env_keys(Path("d:/code/pymidscene/.env.sample"))
    duplicate_keys = set(config_data.keys()) & env_keys
    assert duplicate_keys == set()


def test_env_sample_contains_model_secret_related_entries():
    env_sample = Path("d:/code/pymidscene/.env.sample").read_text(encoding="utf-8")

    assert "LLM_API_KEY=" in env_sample
    assert "LLM_BASE_URL=" in env_sample
    assert "VISION_API_KEY=" in env_sample
    assert "VISION_BASE_URL=" in env_sample
    assert "MCP_API_KEY=" in env_sample
    assert "MCP_PLAYWRIGHT_API_KEY=" in env_sample
    assert "MCP_WINAPP_API_KEY=" in env_sample


def test_mcp_specific_api_key_overrides_global_default():
    original_global = os.environ.get("MCP_API_KEY")
    original_winapp = os.environ.get("MCP_WINAPP_API_KEY")
    try:
        os.environ["MCP_API_KEY"] = "global-key"
        os.environ["MCP_WINAPP_API_KEY"] = "winapp-key"

        settings = Settings()

        assert settings.MCP_SERVERS["playwright"].api_key == "global-key"
        assert settings.MCP_SERVERS["winapp"].api_key == "winapp-key"
    finally:
        if original_global is None:
            os.environ.pop("MCP_API_KEY", None)
        else:
            os.environ["MCP_API_KEY"] = original_global
        if original_winapp is None:
            os.environ.pop("MCP_WINAPP_API_KEY", None)
        else:
            os.environ["MCP_WINAPP_API_KEY"] = original_winapp


def test_compact_provider_model_format_is_backward_compatible():
    settings = Settings(
        LLM_PROVIDER="deepseek",
        LLM_MODEL="openai/gpt-4o-mini",
        VISION_PROVIDER="qwen",
        VISION_MODEL="doubao/vision-pro",
    )

    assert settings.llm_config.provider == "openai"
    assert settings.llm_config.model == "gpt-4o-mini"
    assert settings.vision_config.provider == "doubao"
    assert settings.vision_config.model == "vision-pro"
