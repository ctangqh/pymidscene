import atexit
import sys
from pathlib import Path
from typing import Optional

from loguru import logger
from .config import settings


def _should_use_enqueue() -> bool:
    """Windows 下多短进程串行执行时，队列日志容易在退出阶段产生反序列化噪音。"""
    return not sys.platform.startswith("win")


def _complete_logger() -> None:
    try:
        completion = logger.complete()
        if hasattr(completion, "__await__"):
            try:
                import asyncio

                asyncio.run(completion)
            except Exception:
                pass
    except Exception:
        pass


def setup_logger(log_level: Optional[str] = None, log_file: Optional[str] = None, debug: Optional[bool] = None) -> None:
    """初始化日志系统"""
    # 如果没有明确指定，根据 settings.DEBUG 确定日志级别
    if debug is None:
        debug = settings.DEBUG
    
    # Debug 模式时默认用 DEBUG 级别，否则用配置的级别
    if debug and not log_level:
        log_level = "DEBUG"
    else:
        log_level = (log_level or settings.LOG_LEVEL).upper()
    
    # 默认使用配置的日志文件路径，debug 模式用不同的文件
    if log_file is None:
        if debug and hasattr(settings, 'LOG_FILE_DEBUG'):
            log_file = settings.LOG_FILE_DEBUG
        elif hasattr(settings, 'LOG_FILE'):
            log_file = settings.LOG_FILE
    
    # 移除默认 handler
    logger.remove()
    
    # 控制台输出
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=_should_use_enqueue(),
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
            enqueue=_should_use_enqueue(),
        )
        logger.info(f"Log file: {log_path}")
    
    logger.info(f"Logger initialized, level: {log_level}, debug: {debug}")


# 初始化默认日志
setup_logger()
atexit.register(_complete_logger)

__all__ = ["logger", "setup_logger"]
