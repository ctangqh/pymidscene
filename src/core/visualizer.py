import base64
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw
from pathlib import Path
from .types import Rect


def format_box_label(rect: Any, el_type: str = "element") -> str:
    if isinstance(rect, Rect):
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

def annotate_screenshot(
    screenshot_base64: str,
    annotations: List[Dict[str, Any]],
    output_path: str
) -> None:
    """
    Draw bounding boxes on a screenshot and save it.
    
    Args:
        screenshot_base64: Base64 encoded screenshot
        annotations: List of dicts with 'rect' (Rect) and optional 'label' (str), 'color' (str)
        output_path: Path to save the annotated image
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
            if isinstance(rect, Rect):
                box = [rect.left, rect.top, rect.left + rect.width, rect.top + rect.height]
            elif isinstance(rect, dict):
                box = [rect["left"], rect["top"], rect["left"] + rect["width"], rect["top"] + rect["height"]]
            else:
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
        
    except Exception as e:
        from common.logger import logger
        logger.warning(f"Failed to annotate screenshot: {e}")
