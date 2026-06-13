import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT / ".env"
APP_CONFIG_PATH = PROJECT_ROOT / "app.yaml"
MCP_SERVERS_YAML_PATH = PROJECT_ROOT / "deploy" / "mcp_servers.yaml"


class McpServerConfig(BaseModel):
    """单个 MCP 服务器配置"""
    url: Optional[str] = None
    transport: str = "sse"  # sse, http, stdio
    command: Optional[List[str]] = None  # 仅用于 stdio
    api_key: Optional[str] = None
    timeout: int = 60
    env: Optional[Dict[str, str]] = None


class OpenAICompatibleModelConfig(BaseModel):
    """OpenAI 兼容模型配置"""
    provider: str = "openai"
    api_key: Optional[str] = None
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    timeout: int = 60
    max_retries: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=APP_CONFIG_PATH,
                yaml_file_encoding="utf-8",
            ),
            file_secret_settings,
        )

    # 调试模式
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # 设备默认 provider
    DEFAULT_DEVICE_PROVIDER: str = "mcp_playwright"

    # LLM 配置
    LLM_PROVIDER: str = Field(
        default="openai",
        validation_alias=AliasChoices("LLM_PROVIDER", "DEFAULT_LLM_PROVIDER"),
    )
    LLM_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "OPENAI_API_KEY", "DOUBAN_API_KEY"),
    )
    LLM_BASE_URL: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL", "DOUBAN_BASE_URL"),
    )
    LLM_MODEL: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL", "DOUBAN_MODEL"),
    )

    # 视觉模型配置
    # 未显式配置时，默认复用 LLM 的 OpenAI 兼容配置，适配多模态模型。
    VISION_PROVIDER: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("VISION_PROVIDER", "DEFAULT_VISION_PROVIDER"),
    )
    VISION_API_KEY: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "VISION_API_KEY",
            "OPENAI_VISION_API_KEY",
            "DOUBAN_VISION_API_KEY",
            "VISION_OPENAI_API_KEY",
        ),
    )
    VISION_BASE_URL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "VISION_BASE_URL",
            "OPENAI_VISION_BASE_URL",
            "DOUBAN_VISION_BASE_URL",
            "VISION_OPENAI_BASE_URL",
        ),
    )
    VISION_MODEL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "VISION_MODEL",
            "OPENAI_VISION_MODEL",
            "DOUBAN_VISION_MODEL",
            "VISION_OPENAI_MODEL",
        ),
    )

    # 模型运行时
    DEFAULT_OCR_PROVIDER: str = "paddleocr"
    MODEL_TIMEOUT: int = 60
    MODEL_MAX_RETRIES: int = 3

    # Device runtime
    DEVICE_HEADLESS: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEVICE_HEADLESS", "BROWSER_HEADLESS"),
    )
    DEVICE_TIMEOUT: int = Field(
        default=30000,
        validation_alias=AliasChoices("DEVICE_TIMEOUT", "BROWSER_TIMEOUT"),
    )
    DEVICE_VIEWPORT_WIDTH: int = Field(
        default=1920,
        validation_alias=AliasChoices("DEVICE_VIEWPORT_WIDTH", "BROWSER_VIEWPORT_WIDTH"),
    )
    DEVICE_VIEWPORT_HEIGHT: int = Field(
        default=1080,
        validation_alias=AliasChoices("DEVICE_VIEWPORT_HEIGHT", "BROWSER_VIEWPORT_HEIGHT"),
    )
    DEVICE_USER_AGENT: str = Field(
        default="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        validation_alias=AliasChoices("DEVICE_USER_AGENT", "BROWSER_USER_AGENT"),
    )

    # 定位配置
    LOCATE_CONFIDENCE_THRESHOLD: float = 0.7
    LOCATE_MAX_RETRIES: int = 2
    LOCATE_USE_VISION: bool = True

    ANOMALY_GUARD_ENABLED: bool = Field(
        default=True,
        validation_alias=AliasChoices("ANOMALY_GUARD_ENABLED", "POPUP_GUARD_ENABLED"),
    )
    ANOMALY_DETECT_CONFIDENCE_THRESHOLD: float = Field(
        default=0.7,
        validation_alias=AliasChoices("ANOMALY_DETECT_CONFIDENCE_THRESHOLD", "POPUP_DETECT_CONFIDENCE_THRESHOLD"),
    )
    ANOMALY_DEBUG_SAVE_DIR: str = Field(
        default="./output/anomaly_debug",
        validation_alias=AliasChoices("ANOMALY_DEBUG_SAVE_DIR", "POPUP_DEBUG_SAVE_DIR"),
    )

    # 报告配置
    REPORT_SAVE_DIR: str = "./output/reports"
    REPORT_AUTO_SAVE: bool = True
    
    # 日志配置
    LOG_FILE: str = "./logs/run.log"

    # MCP 配置
    DEFAULT_MCP_NAME: str = Field(
        default="playwright",
        validation_alias=AliasChoices("DEFAULT_MCP_NAME", "DEFAULT_MCP_SERVER"),
    )

    # Key 为实例名称，可通过 deploy/mcp_servers.yaml 扩展
    MCP_SERVERS: Dict[str, McpServerConfig] = Field(default_factory=lambda: {
        "playwright": McpServerConfig(
            url="http://127.0.0.1:55000/sse",
            transport="sse"
        ),
        "winapp": McpServerConfig(
            url="http://127.0.0.1:55001/sse", 
            transport="sse"
        ),
        "hypium": McpServerConfig(
            url="http://127.0.0.1:55002/sse", 
            transport="sse"
        ),
        "android": McpServerConfig(
            url="http://127.0.0.1:55003/sse",
            transport="sse"
        ),
        "ios": McpServerConfig(
            url="http://127.0.0.1:55004/sse",
            transport="sse"
        ),
    })

    # 兼容性字段（保留旧版单配置项）
    MCP_SERVER_URL: str = ""
    MCP_API_KEY: str = ""
    MCP_TIMEOUT: int = 60

    # WinAppDriver 配置
    WINAPPDRIVER_APP: Optional[str] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_mcp_servers_from_yaml()
        self._apply_mcp_server_api_keys_from_env()

    def _load_mcp_servers_from_yaml(self):
        """尝试从 deploy/mcp_servers.yaml 加载配置"""
        yaml_path = MCP_SERVERS_YAML_PATH
        if yaml_path.exists():
            try:
                with yaml_path.open("r", encoding="utf-8") as f:
                    extra_configs = yaml.safe_load(f)
                    if extra_configs and isinstance(extra_configs, dict):
                        for name, config in extra_configs.items():
                            self.MCP_SERVERS[name] = McpServerConfig(**config)
            except Exception as e:
                print(f"Warning: Failed to load MCP servers from {yaml_path}: {e}")

    def _apply_mcp_server_api_keys_from_env(self):
        """按 MCP 实例名从环境变量注入 api_key；未命中时回退到全局 MCP_API_KEY。"""
        shared_api_key = self.MCP_API_KEY or ""
        for name, config in self.MCP_SERVERS.items():
            normalized_name = "".join(ch if ch.isalnum() else "_" for ch in name).upper()
            env_key = f"MCP_{normalized_name}_API_KEY"
            specific_api_key = os.getenv(env_key, "")
            if specific_api_key:
                config.api_key = specific_api_key
            elif not config.api_key and shared_api_key:
                config.api_key = shared_api_key

    @staticmethod
    def _resolve_provider_and_model(
        provider: Optional[str],
        model: Optional[str],
        *,
        fallback_provider: str,
        fallback_model: Optional[str] = None,
    ) -> tuple[str, str]:
        normalized_provider = (provider or "").strip()
        normalized_model = (model or "").strip()
        if normalized_model and "/" in normalized_model:
            inferred_provider, inferred_model = normalized_model.split("/", 1)
            inferred_provider = inferred_provider.strip()
            inferred_model = inferred_model.strip()
            if inferred_provider and inferred_model:
                return inferred_provider, inferred_model
        return normalized_provider or fallback_provider, normalized_model or (fallback_model or "")

    @property
    def report_dir(self) -> Path:
        return Path(self.REPORT_SAVE_DIR)

    @property
    def report_screenshot_dir(self) -> Path:
        return self.report_dir / "screenshots"

    @property
    def REPORT_SCREENSHOT_SAVE_DIR(self) -> str:
        """兼容旧代码，截图目录始终跟随 report 目录。"""
        return str(self.report_screenshot_dir)

    @property
    def LOG_FILE_DEBUG(self) -> str:
        """兼容旧代码，debug 日志文件默认由 LOG_FILE 自动派生。"""
        log_path = Path(self.LOG_FILE)
        suffix = log_path.suffix or ".log"
        if log_path.suffix:
            debug_name = f"{log_path.stem}_debug{suffix}"
        else:
            debug_name = f"{log_path.name}_debug{suffix}"
        return str(log_path.with_name(debug_name))

    @property
    def llm_config(self) -> OpenAICompatibleModelConfig:
        provider, model = self._resolve_provider_and_model(
            self.LLM_PROVIDER,
            self.LLM_MODEL,
            fallback_provider="openai",
        )
        return OpenAICompatibleModelConfig(
            provider=provider,
            api_key=self.LLM_API_KEY,
            base_url=self.LLM_BASE_URL,
            model=model,
            timeout=self.MODEL_TIMEOUT,
            max_retries=self.MODEL_MAX_RETRIES,
        )

    @property
    def vision_config(self) -> OpenAICompatibleModelConfig:
        llm_config = self.llm_config
        provider, model = self._resolve_provider_and_model(
            self.VISION_PROVIDER,
            self.VISION_MODEL,
            fallback_provider=llm_config.provider,
            fallback_model=llm_config.model,
        )
        return OpenAICompatibleModelConfig(
            provider=provider,
            api_key=self.VISION_API_KEY or self.LLM_API_KEY,
            base_url=self.VISION_BASE_URL or self.LLM_BASE_URL,
            model=model,
            timeout=self.MODEL_TIMEOUT,
            max_retries=self.MODEL_MAX_RETRIES,
        )

    @property
    def BROWSER_HEADLESS(self) -> bool:
        return self.DEVICE_HEADLESS

    @property
    def BROWSER_TIMEOUT(self) -> int:
        return self.DEVICE_TIMEOUT

    @property
    def BROWSER_VIEWPORT_WIDTH(self) -> int:
        return self.DEVICE_VIEWPORT_WIDTH

    @property
    def BROWSER_VIEWPORT_HEIGHT(self) -> int:
        return self.DEVICE_VIEWPORT_HEIGHT

    @property
    def BROWSER_USER_AGENT(self) -> str:
        return self.DEVICE_USER_AGENT

    @property
    def DEFAULT_MCP_SERVER(self) -> str:
        return self.DEFAULT_MCP_NAME

    @property
    def DEFAULT_LLM_PROVIDER(self) -> str:
        return self.llm_config.provider

    @property
    def DEFAULT_VISION_PROVIDER(self) -> str:
        return self.vision_config.provider

    @property
    def OPENAI_API_KEY(self) -> Optional[str]:
        return self.LLM_API_KEY

    @property
    def OPENAI_BASE_URL(self) -> str:
        return self.LLM_BASE_URL

    @property
    def OPENAI_MODEL(self) -> str:
        return self.llm_config.model

    @property
    def OPENAI_VISION_MODEL(self) -> str:
        return self.vision_config.model

    @property
    def POPUP_GUARD_ENABLED(self) -> bool:
        return self.ANOMALY_GUARD_ENABLED

    @property
    def POPUP_DETECT_CONFIDENCE_THRESHOLD(self) -> float:
        return self.ANOMALY_DETECT_CONFIDENCE_THRESHOLD

    @property
    def POPUP_DEBUG_SAVE_DIR(self) -> str:
        return self.ANOMALY_DEBUG_SAVE_DIR

    @property
    def DOUBAN_API_KEY(self) -> Optional[str]:
        return self.LLM_API_KEY

    @property
    def DOUBAN_BASE_URL(self) -> str:
        return self.LLM_BASE_URL

    @property
    def DOUBAN_MODEL(self) -> str:
        return self.llm_config.model

    @property
    def DOUBAN_VISION_MODEL(self) -> str:
        return self.vision_config.model


settings = Settings()
