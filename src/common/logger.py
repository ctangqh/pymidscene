import sys
from loguru import logger
from typing import Optional
from pathlib import Path
from .config import settings


def setup_logger(log_level: Optional[str] = None, log_file: Optional[str] = None) -> None:
    """初始化日志系统"""
    log_level = (log_level or settings.LOG_LEVEL).upper()
    
    # 移除默认 handler
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=True,
    )
    
    # 文件输出（如果配置了日志文件）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_path,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="30 days",
            compression="zip",
            enqueue=True,
        )
    
    logger.info(f"Logger initialized, level: {log_level}")


# 初始化默认日志
setup_logger()

__all__ = ["logger", "setup_logger"]
