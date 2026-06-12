"""
视觉化相关工具（已迁移到 common/image.py）
此文件保留用于向后兼容
"""
from common.image import (
    format_box_label,
    annotate_screenshot
)

__all__ = ['format_box_label', 'annotate_screenshot']
