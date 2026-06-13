import time
from typing import Any, Dict, Optional

from report import ReportGenerator


class ScreenshotItem:
    """Represents a screenshot with metadata"""
    
    def __init__(self, base64_data: str, captured_at: float, filename: Optional[str] = None):
        self.base64_data = base64_data
        self.captured_at = captured_at
        self.filename = filename
    
    @classmethod
    def create(
        cls,
        base64_data: str,
        captured_at: Optional[float] = None,
        filename: Optional[str] = None,
    ) -> "ScreenshotItem":
        return cls(base64_data, captured_at or time.time(), filename=filename)
    
    def serialize(self) -> str:
        """Serialize for report - returns reference path"""
        # In a full implementation, save to disk and return path
        return f"screenshot_{int(self.captured_at)}"
    
    def to_dict(self) -> Dict[str, Any]:
        data = {
            "captured_at": self.captured_at,
            "data_length": len(self.base64_data) if self.base64_data else 0,
            "base64_data": self.base64_data,
        }
        if self.filename:
            data["filename"] = self.filename
        return data
