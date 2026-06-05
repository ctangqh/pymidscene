from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 调试模式
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # 通用模型配置
    DEFAULT_LLM_PROVIDER: str = "openai"
    DEFAULT_VISION_PROVIDER: str = "openai"
    DEFAULT_OCR_PROVIDER: str = "paddleocr"
    MODEL_TIMEOUT: int = 60
    MODEL_MAX_RETRIES: int = 3

    # OpenAI 配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_VISION_MODEL: str = "gpt-4o"

    # 字节豆包配置
    DOUBAN_API_KEY: Optional[str] = None
    DOUBAN_BASE_URL: str = "https://aquasearch.bytedance.com/api/v3"
    DOUBAN_MODEL: str = "doubao-pro-4k"
    DOUBAN_VISION_MODEL: str = "doubao-vision-pro-128k"

    # 浏览器配置
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 30000
    BROWSER_VIEWPORT_WIDTH: int = 1920
    BROWSER_VIEWPORT_HEIGHT: int = 1080
    BROWSER_USER_AGENT: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

    # 定位配置
    LOCATE_CONFIDENCE_THRESHOLD: float = 0.7
    LOCATE_MAX_RETRIES: int = 2
    LOCATE_USE_VISION: bool = True

    # 报告配置
    REPORT_SAVE_DIR: str = "./output/reports"
    REPORT_SCREENSHOT_SAVE_DIR: str = "./output/screenshots"
    REPORT_AUTO_SAVE: bool = True


settings = Settings()
