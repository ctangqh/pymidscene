import base64
import struct
import time
from typing import Optional, Tuple
from ..types import UIContext
from common.logger import logger

def _get_png_dimensions_from_base64(b64_data: str) -> Tuple[int, int]:
    """Extract PNG dimensions from base64 without full decode"""
    # PNG header: width at bytes 16-19, height at bytes 20-23 (big-endian)
    data = base64.b64decode(b64_data[:100])
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        width = struct.unpack('>I', data[16:20])[0]
        height = struct.unpack('>I', data[20:24])[0]
        return width, height
    raise ValueError("Not a PNG image")

def _get_image_dimensions_from_base64(b64_data: str) -> Tuple[int, int]:
    """Get image dimensions from base64 data - tries PNG then JPEG"""
    try:
        return _get_png_dimensions_from_base64(b64_data)
    except ValueError:
        pass
    # Try JPEG
    data = base64.b64decode(b64_data[:200])
    if data[:2] == b'\xff\xd8':
        # JPEG: scan SOF markers
        idx = 2
        while idx < len(data) - 9:
            if data[idx] != 0xFF:
                break
            marker = data[idx + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                height = struct.unpack('>H', data[idx+5:idx+7])[0]
                width = struct.unpack('>H', data[idx+7:idx+9])[0]
                return width, height
            idx += 2 + struct.unpack('>H', data[idx+2:idx+4])[0]
    raise ValueError("Cannot determine image dimensions (only PNG/JPEG supported)")

async def common_context_parser(device, opt: dict = None) -> UIContext:
    """
    Parse UI context from device - ported from TS commonContextParser
    
    Args:
        device: BaseDevice instance
        opt: Options dict with optional keys:
            - screenshot_shrink_factor: float (default 1.0)
    
    Returns:
        UIContext with screenshot, dimensions, and ratio info
    """
    opt = opt or {}
    user_shrink_factor = opt.get("screenshot_shrink_factor", 1.0)
    
    # Get logical size. For non-web devices, screenshot pixels are the most
    # reliable coordinate system, so we treat them as logical coordinates.
    logical_width, logical_height = device.size()
    interface_type = getattr(device, "interface_type", "")
    
    # Take screenshot
    screenshot_b64 = device.screenshot_base64()
    if not screenshot_b64:
        raise ValueError("screenshot_base64 returned empty data")
    
    # Get physical screenshot dimensions
    img_width, img_height = _get_image_dimensions_from_base64(screenshot_b64)
    
    # Detect orientation mismatch
    logical_is_portrait = logical_width < logical_height
    screenshot_is_portrait = img_width < img_height
    
    final_logical_width = logical_width
    final_logical_height = logical_height

    if interface_type not in ("web", "browser"):
        final_logical_width = img_width
        final_logical_height = img_height
    
    if interface_type in ("web", "browser") and logical_is_portrait != screenshot_is_portrait:
        logger.debug(f"Orientation mismatch: logical {logical_width}x{logical_height} vs screenshot {img_width}x{img_height}. Swapping logical dimensions.")
        final_logical_width = logical_height
        final_logical_height = logical_width
    
    # Calculate DPR and ratio
    dpr = img_width / final_logical_width
    shrunk_shot_to_logical_ratio = dpr / user_shrink_factor
    
    # Apply shrink factor if needed (resize screenshot)
    if user_shrink_factor != 1.0:
        target_width = round(img_width / user_shrink_factor)
        target_height = round(img_height / user_shrink_factor)
        # Resize using Pillow if available, otherwise keep original
        try:
            from PIL import Image
            import io
            img_data = base64.b64decode(screenshot_b64)
            img = Image.open(io.BytesIO(img_data))
            img = img.resize((target_width, target_height))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            screenshot_b64 = base64.b64encode(buf.getvalue()).decode()
            img_width = target_width
            img_height = target_height
        except ImportError:
            logger.warning("Pillow not installed, cannot shrink screenshot. Using original size.")
    
    return UIContext(
        screenshot=screenshot_b64,
        shot_size={"width": img_width, "height": img_height},
        deprecated_dpr=dpr,
        shrunk_shot_to_logical_ratio=shrunk_shot_to_logical_ratio,
    )
