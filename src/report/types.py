from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class ScreenshotRef(BaseModel):
    type: Literal["pymidscene_screenshot_ref"] = "pymidscene_screenshot_ref"
    id: str
    captured_at: float
    mime_type: Literal["image/png", "image/jpeg"] = "image/png"
    storage: Literal["inline", "file"] = "file"
    path: Optional[str] = None


class ReportMeta(BaseModel):
    group_name: str = ""
    group_description: str = ""
    sdk_version: str = ""
    model_briefs: list[Dict[str, Any]] = Field(default_factory=list)
    device_type: str = ""
    report_version: str = "1"


class ReportFile(BaseModel):
    meta: ReportMeta
    executions: list[Dict[str, Any]] = Field(default_factory=list)
