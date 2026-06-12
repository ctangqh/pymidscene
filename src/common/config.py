import os
import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, List


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
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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
    REPORT_SCREENSHOT_SAVE_DIR: str = "./output/reports/screenshots"
    REPORT_AUTO_SAVE: bool = True
    
    # 日志配置
    LOG_FILE: str = "./logs/run.log"
    LOG_FILE_DEBUG: str = "./logs/run_debug.log"

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
        self._normalize_report_paths()

    def _load_mcp_servers_from_yaml(self):
        """尝试从 deploy/mcp_servers.yaml 加载配置"""
        yaml_path = os.path.join(os.getcwd(), "deploy", "mcp_servers.yaml")
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    extra_configs = yaml.safe_load(f)
                    if extra_configs and isinstance(extra_configs, dict):
                        for name, config in extra_configs.items():
                            self.MCP_SERVERS[name] = McpServerConfig(**config)
            except Exception as e:
                print(f"Warning: Failed to load MCP servers from {yaml_path}: {e}")

    def _normalize_report_paths(self):
        """兼容旧配置，保证截图目录始终跟随 report 目录"""
        report_dir = os.path.normpath(self.REPORT_SAVE_DIR or "./output/reports")
        current_screenshot_dir = os.path.normpath(
            self.REPORT_SCREENSHOT_SAVE_DIR or os.path.join(report_dir, "screenshots")
        )
        legacy_dirs = {
            os.path.normpath("./output/screenshots"),
            os.path.normpath("output/screenshots"),
            os.path.normpath(".\\output\\screenshots"),
            os.path.normpath("output\\screenshots"),
        }

        if current_screenshot_dir in legacy_dirs:
            self.REPORT_SCREENSHOT_SAVE_DIR = os.path.join(report_dir, "screenshots")

    @property
    def llm_config(self) -> OpenAICompatibleModelConfig:
        return OpenAICompatibleModelConfig(
            provider=self.LLM_PROVIDER,
            api_key=self.LLM_API_KEY,
            base_url=self.LLM_BASE_URL,
            model=self.LLM_MODEL,
            timeout=self.MODEL_TIMEOUT,
            max_retries=self.MODEL_MAX_RETRIES,
        )

    @property
    def vision_config(self) -> OpenAICompatibleModelConfig:
        return OpenAICompatibleModelConfig(
            provider=self.VISION_PROVIDER or self.LLM_PROVIDER,
            api_key=self.VISION_API_KEY or self.LLM_API_KEY,
            base_url=self.VISION_BASE_URL or self.LLM_BASE_URL,
            model=self.VISION_MODEL or self.LLM_MODEL,
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
        return self.LLM_PROVIDER

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
        return self.LLM_MODEL

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
        return self.LLM_MODEL

    @property
    def DOUBAN_VISION_MODEL(self) -> str:
        return self.vision_config.model


settings = Settings()
