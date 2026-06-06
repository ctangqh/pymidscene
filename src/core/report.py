import time
import uuid
import json
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from .types import ReportActionDump, ExecutionDump, ReportMeta
from common.logger import logger


class ReportGenerator:
    """
    Generates execution reports for agent runs.
    Port of TS ReportGenerator (simplified).
    """
    
    def __init__(
        self,
        report_file_name: Optional[str] = None,
        generate_report: bool = True,
        persist_execution_dump: bool = False,
        output_format: Optional[str] = None,
        auto_print_report_msg: bool = True,
        reuse_existing_report: bool = False,
    ):
        self.report_file_name = report_file_name
        self.generate_report = generate_report
        self.persist_execution_dump = persist_execution_dump
        self.output_format = output_format
        self.auto_print_report_msg = auto_print_report_msg
        self._report_path: Optional[str] = None
        self._execution_dumps: List[Dict] = []
    
    @classmethod
    def create(cls, report_file_name: str, options: Optional[Dict] = None) -> "ReportGenerator":
        """Factory method to create a ReportGenerator"""
        options = options or {}
        return cls(
            report_file_name=report_file_name,
            generate_report=options.get("generate_report", True),
            persist_execution_dump=options.get("persist_execution_dump", False),
            output_format=options.get("output_format"),
            auto_print_report_msg=options.get("auto_print_report_msg", True),
            reuse_existing_report=options.get("reuse_existing_report", False),
        )
    
    def on_execution_update(
        self,
        execution_dump: Optional[Dict],
        report_meta: Optional[ReportMeta] = None,
        report_attributes: Optional[Dict] = None,
    ) -> None:
        """Called when execution dump is updated"""
        if execution_dump:
            self._execution_dumps.append(execution_dump)
    
    async def flush(self) -> None:
        """Flush pending report data to disk"""
        if not self.generate_report or not self.persist_execution_dump:
            return
        
        if not self._execution_dumps:
            return
        
        try:
            report_dir = Path("./output/reports")
            report_dir.mkdir(parents=True, exist_ok=True)
            
            report_file = report_dir / f"{self.report_file_name}.json"
            
            report_data = {
                "meta": {
                    "report_file_name": self.report_file_name,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                "executions": self._execution_dumps,
            }
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
            
            self._report_path = str(report_file)
            
        except Exception as e:
            logger.warning(f"Failed to flush report: {e}")
    
    async def finalize(self) -> Optional[str]:
        """Finalize the report and return the path"""
        await self.flush()
        return self._report_path
    
    def get_report_path(self) -> Optional[str]:
        """Get the current report file path"""
        return self._report_path


class ScreenshotItem:
    """Represents a screenshot with metadata"""
    
    def __init__(self, base64_data: str, captured_at: float):
        self.base64_data = base64_data
        self.captured_at = captured_at
    
    @classmethod
    def create(cls, base64_data: str, captured_at: Optional[float] = None) -> "ScreenshotItem":
        return cls(base64_data, captured_at or time.time())
    
    def serialize(self) -> str:
        """Serialize for report - returns reference path"""
        # In a full implementation, save to disk and return path
        return f"screenshot_{int(self.captured_at)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "data_length": len(self.base64_data) if self.base64_data else 0,
        }
