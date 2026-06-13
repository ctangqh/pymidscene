"""
图像相关的工具函数
包括截图保存、标注等功能
"""
import base64
import time
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Any, Optional

from PIL import Image, ImageDraw

from common.logger import logger
from common.config import settings

try:
    from core.types import Rect
except ImportError:
    # 处理可能的循环导入问题
    Rect = Any


def format_box_label(rect: Any, el_type: str = "element") -> str:
    """
    格式化边界框标签
    
    Args:
        rect: 边界框，可以是 Rect 对象或字典
        el_type: 元素类型
    
    Returns:
        格式化后的标签字符串
    """
    if hasattr(rect, "left") and hasattr(rect, "top") and hasattr(rect, "width") and hasattr(rect, "height"):
        left, top, right, bottom = (
            rect.left,
            rect.top,
            rect.left + rect.width,
            rect.top + rect.height,
        )
    elif isinstance(rect, dict):
        if "left" in rect and "top" in rect and "width" in rect and "height" in rect:
            left, top, right, bottom = (
                rect["left"],
                rect["top"],
                rect["left"] + rect["width"],
                rect["top"] + rect["height"],
            )
        elif "x" in rect and "y" in rect and "width" in rect and "height" in rect:
            left, top, right, bottom = (
                rect["x"],
                rect["y"],
                rect["x"] + rect["width"],
                rect["y"] + rect["height"],
            )
        elif "left" in rect and "top" in rect and "right" in rect and "bottom" in rect:
            left, top, right, bottom = (
                rect["left"],
                rect["top"],
                rect["right"],
                rect["bottom"],
            )
        else:
            left = top = right = bottom = 0
    else:
        left = top = right = bottom = 0

    return f"{(el_type or 'element').capitalize()}, [{int(left)},{int(top)},{int(right)},{int(bottom)}]"


def get_screenshot_save_dir(save_dir: Optional[Path] = None) -> Path:
    """
    获取截图保存目录
    
    Returns:
        截图保存目录的 Path 对象
    """
    save_dir = save_dir or settings.report_screenshot_dir
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def save_raw_screenshot(
    screenshot_base64: str,
    filename: Optional[str] = None,
    is_debug: bool = False,
    save_dir: Optional[Path] = None,
) -> Path:
    """
    保存原始截图
    
    Args:
        screenshot_base64: Base64 编码的截图数据
        filename: 文件名，不指定则自动生成
        is_debug: 是否为 debug 截图，会添加 _debug 后缀
    
    Returns:
        保存的文件路径
    """
    if not screenshot_base64:
        raise ValueError("screenshot_base64 is empty")
    
    save_dir = get_screenshot_save_dir(save_dir)
    
    if not filename:
        timestamp = int(time.time() * 1000)
        filename = f"screenshot_{timestamp}.png"
    
    # 处理 debug 后缀
    if is_debug:
        path = Path(filename)
        name = path.stem
        ext = path.suffix or ".png"
        filename = f"{name}_debug{ext}"
    
    save_path = save_dir / filename
    
    try:
        save_path.write_bytes(base64.b64decode(screenshot_base64))
        logger.debug(f"Raw screenshot saved: {save_path}")
    except Exception as e:
        logger.error(f"Failed to save raw screenshot: {e}")
        raise
    
    return save_path


def annotate_screenshot(
    screenshot_base64: str,
    annotations: List[Dict[str, Any]],
    output_path: str
) -> None:
    """
    在截图上绘制边界框并保存
    
    Args:
        screenshot_base64: Base64 编码的截图
        annotations: 标注列表，每个包含 'rect' (Rect) 和可选的 'label' (str), 'color' (str)
        output_path: 保存标注后图像的路径
    """
    if not screenshot_base64:
        return

    try:
        # Decode base64 to image
        img_data = base64.b64decode(screenshot_base64)
        img = Image.open(BytesIO(img_data))
        draw = ImageDraw.Draw(img)
        
        colors = ["red", "blue", "green", "orange", "purple", "cyan"]
        
        for i, ann in enumerate(annotations):
            rect = ann.get("rect")
            if not rect:
                continue
                
            # Convert Rect to [left, top, right, bottom]
            box = None
            if hasattr(rect, "left") and hasattr(rect, "top") and hasattr(rect, "width") and hasattr(rect, "height"):
                box = [rect.left, rect.top, rect.left + rect.width, rect.top + rect.height]
            elif isinstance(rect, dict):
                if "left" in rect and "top" in rect and "width" in rect and "height" in rect:
                    box = [rect["left"], rect["top"], rect["left"] + rect["width"], rect["top"] + rect["height"]]
                elif "x" in rect and "y" in rect and "width" in rect and "height" in rect:
                    box = [rect["x"], rect["y"], rect["x"] + rect["width"], rect["y"] + rect["height"]]
                elif "left" in rect and "top" in rect and "right" in rect and "bottom" in rect:
                    box = [rect["left"], rect["top"], rect["right"], rect["bottom"]]
            
            if not box:
                continue
                
            color = ann.get("color") or colors[i % len(colors)]
            label = ann.get("label", "")
            if not label and ann.get("el_type"):
                label = format_box_label(rect, str(ann.get("el_type") or "element"))
            
            # Draw rectangle
            draw.rectangle(box, outline=color, width=3)
            
            # Draw labels (handle multiple lines)
            if label:
                lines = label.split('\n')
                for j, line in enumerate(lines):
                    draw.text((box[0], box[1] - 15 * (len(lines) - j)), line, fill=color)
        
        # Save image
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_file)
        logger.debug(f"Annotated screenshot saved: {output_file}")
        
    except Exception as e:
        logger.warning(f"Failed to annotate screenshot: {e}")


def save_debug_screenshot(
    screenshot_base64: str,
    filename_prefix: str,
    annotations: Optional[List[Dict[str, Any]]] = None,
    save_raw: bool = True,
    save_dir: Optional[Path] = None,
) -> Dict[str, Path]:
    """
    保存调试截图（包括原始和标注版本）
    
    Args:
        screenshot_base64: Base64 编码的截图
        filename_prefix: 文件名前缀
        annotations: 标注列表（如果提供，会生成标注版本）
        save_raw: 是否保存原始截图
    
    Returns:
        包含文件路径的字典，可能包含 'raw' 和 'annotated' 键
    """
    result = {}
    timestamp = int(time.time() * 1000)
    save_dir = get_screenshot_save_dir(save_dir)
    
    # 保存原始截图
    if save_raw:
        raw_filename = f"{filename_prefix}_{timestamp}_raw.png"
        raw_path = save_raw_screenshot(screenshot_base64, raw_filename, is_debug=True, save_dir=save_dir)
        result['raw'] = raw_path
    
    # 保存标注截图
    if annotations:
        ann_filename = f"{filename_prefix}_{timestamp}_debug.png"
        ann_path = save_dir / ann_filename
        annotate_screenshot(screenshot_base64, annotations, str(ann_path))
        result['annotated'] = ann_path
    
    return result


def compress_image(
    image_data: bytes,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    max_size_kb: Optional[int] = None,
    quality: int = 85,
    format: str = "JPEG"
) -> bytes:
    """
    对图片进行等比压缩，适用于视觉模型预处理
    
    Args:
        image_data: 原始图片的字节数据
        max_width: 最大宽度（像素）
        max_height: 最大高度（像素）
        max_size_kb: 最大文件大小（KB）
        quality: JPEG 压缩质量（1-100），默认 85
        format: 输出格式，默认 "JPEG"，支持 "JPEG", "PNG"
    
    Returns:
        压缩后的图片字节数据
    """
    try:
        img = Image.open(BytesIO(image_data))
        
        # 等比缩放
        original_width, original_height = img.size
        new_width, new_height = original_width, original_height
        
        if max_width and original_width > max_width:
            ratio = max_width / original_width
            new_width = max_width
            new_height = int(original_height * ratio)
        
        if max_height and new_height > max_height:
            ratio = max_height / new_height
            new_height = max_height
            new_width = int(new_width * ratio)
        
        if (new_width, new_height) != (original_width, original_height):
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 如果是 PNG，先转换成 RGB 以避免 alpha 通道问题
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        
        # 压缩图片到指定大小
        if max_size_kb:
            # 尝试逐步降低质量直到满足大小要求
            output_bytes = BytesIO()
            current_quality = quality
            
            while current_quality >= 10:
                output_bytes.seek(0)
                output_bytes.truncate()
                
                if format.upper() == "PNG":
                    img.save(output_bytes, format="PNG", optimize=True)
                else:
                    img.save(output_bytes, format="JPEG", quality=current_quality, optimize=True)
                
                size_kb = len(output_bytes.getvalue()) / 1024
                
                if size_kb <= max_size_kb:
                    break
                
                current_quality -= 10
            
            return output_bytes.getvalue()
        else:
            # 只进行尺寸压缩，不限制大小
            output_bytes = BytesIO()
            if format.upper() == "PNG":
                img.save(output_bytes, format="PNG", optimize=True)
            else:
                img.save(output_bytes, format="JPEG", quality=quality, optimize=True)
            return output_bytes.getvalue()
            
    except Exception as e:
        logger.error(f"Failed to compress image: {e}")
        return image_data


def compress_base64_image(
    screenshot_base64: str,
    max_width: Optional[int] = 1920,
    max_height: Optional[int] = 1080,
    max_size_kb: Optional[int] = 500,
    quality: int = 85,
    format: str = "JPEG"
) -> str:
    """
    对 base64 编码的图片进行等比压缩，适用于视觉模型预处理
    
    Args:
        screenshot_base64: Base64 编码的截图
        max_width: 最大宽度（像素），默认 1920
        max_height: 最大高度（像素），默认 1080
        max_size_kb: 最大文件大小（KB），默认 500
        quality: JPEG 压缩质量（1-100），默认 85
        format: 输出格式，默认 "JPEG"，支持 "JPEG", "PNG"
    
    Returns:
        压缩后的 base64 编码图片
    """
    try:
        # 解码 base64
        import base64
        image_data = base64.b64decode(screenshot_base64)
        
        # 压缩图片
        compressed_data = compress_image(
            image_data,
            max_width=max_width,
            max_height=max_height,
            max_size_kb=max_size_kb,
            quality=quality,
            format=format
        )
        
        # 重新编码为 base64
        compressed_base64 = base64.b64encode(compressed_data).decode('utf-8')
        return compressed_base64
        
    except Exception as e:
        logger.error(f"Failed to compress base64 image: {e}")
        return screenshot_base64
