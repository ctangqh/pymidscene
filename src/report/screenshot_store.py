from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Set

from .types import ScreenshotRef
from .utils import decode_base64_to_bytes, ensure_relative_path, sha1_id


class ScreenshotStore:
    def __init__(self, report_path: Path, mode: str = "directory"):
        self.report_path = report_path
        self.mode = mode
        self.screenshots_dir = report_path.parent / "screenshots"
        self._written_ids: Set[str] = set()

    def persist_base64(
        self,
        base64_data: str,
        *,
        captured_at: Optional[float] = None,
        mime_type: str = "image/png",
    ) -> ScreenshotRef:
        captured_at = captured_at or time.time()
        raw_bytes = decode_base64_to_bytes(base64_data)
        sid = sha1_id(raw_bytes)

        if self.mode == "inline":
            return ScreenshotRef(
                id=sid,
                captured_at=captured_at,
                mime_type=mime_type,
                storage="inline",
            )

        ext = "jpeg" if mime_type == "image/jpeg" else "png"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        rel = ensure_relative_path(f"screenshots/{sid}.{ext}")
        abs_path = self.report_path.parent / "screenshots" / f"{sid}.{ext}"
        if sid not in self._written_ids and not abs_path.exists():
            abs_path.write_bytes(raw_bytes)
            self._written_ids.add(sid)

        return ScreenshotRef(
            id=sid,
            captured_at=captured_at,
            mime_type=mime_type,
            storage="file",
            path=rel,
        )
