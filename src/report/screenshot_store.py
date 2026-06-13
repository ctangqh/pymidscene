from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Dict, Optional, Set

from .types import ScreenshotRef
from .utils import decode_base64_to_bytes, ensure_relative_path, sha1_id


class ScreenshotStore:
    def __init__(self, report_path: Path, mode: str = "directory"):
        self.report_path = report_path
        self.mode = mode
        self.screenshots_dir = report_path.parent / "screenshots"
        self._written_ids: Set[str] = set()
        self._paths_by_id: Dict[str, str] = {}

    def persist_base64(
        self,
        base64_data: str,
        *,
        captured_at: Optional[float] = None,
        mime_type: str = "image/png",
        preferred_filename: Optional[str] = None,
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

        existing_path = self._paths_by_id.get(sid)
        if existing_path:
            return ScreenshotRef(
                id=sid,
                captured_at=captured_at,
                mime_type=mime_type,
                storage="file",
                path=existing_path,
            )

        ext = "jpeg" if mime_type == "image/jpeg" else "png"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = self._resolve_filename(
            sid=sid,
            ext=ext,
            raw_bytes=raw_bytes,
            preferred_filename=preferred_filename,
        )
        rel = ensure_relative_path(f"screenshots/{filename}")
        abs_path = self.report_path.parent / "screenshots" / filename
        if sid not in self._written_ids and not abs_path.exists():
            abs_path.write_bytes(raw_bytes)
        self._written_ids.add(sid)
        self._paths_by_id[sid] = rel

        return ScreenshotRef(
            id=sid,
            captured_at=captured_at,
            mime_type=mime_type,
            storage="file",
            path=rel,
        )

    def _resolve_filename(
        self,
        *,
        sid: str,
        ext: str,
        raw_bytes: bytes,
        preferred_filename: Optional[str],
    ) -> str:
        normalized_name = self._normalize_preferred_filename(preferred_filename, ext)
        if not normalized_name:
            return f"{sid}.{ext}"

        candidate_path = self.screenshots_dir / normalized_name
        if not candidate_path.exists():
            return normalized_name
        if self._file_matches(candidate_path, raw_bytes):
            return normalized_name

        stem = Path(normalized_name).stem
        suffix = Path(normalized_name).suffix or f".{ext}"
        index = 2
        while True:
            candidate_name = f"{stem}_{index}{suffix}"
            candidate_path = self.screenshots_dir / candidate_name
            if not candidate_path.exists():
                return candidate_name
            if self._file_matches(candidate_path, raw_bytes):
                return candidate_name
            index += 1

    @staticmethod
    def _normalize_preferred_filename(preferred_filename: Optional[str], ext: str) -> Optional[str]:
        if not isinstance(preferred_filename, str):
            return None

        raw_name = preferred_filename.strip()
        if not raw_name:
            return None

        file_name = Path(raw_name).name
        stem = Path(file_name).stem.strip()
        stem = re.sub(r'[<>:"/\\|?*\s]+', "_", stem).strip("._")
        if not stem:
            return None

        return f"{stem}.{ext}"

    @staticmethod
    def _file_matches(path: Path, raw_bytes: bytes) -> bool:
        try:
            return path.read_bytes() == raw_bytes
        except OSError:
            return False

    def register_saved_file(self, file_path: Path) -> tuple[Optional[str], str]:
        raw_bytes = file_path.read_bytes()
        sid = sha1_id(raw_bytes)
        rel = ensure_relative_path(f"screenshots/{file_path.name}")
        old_rel = self._paths_by_id.get(sid)

        if old_rel and old_rel != rel:
            old_abs_path = self._relative_to_abs(old_rel)
            if old_abs_path.exists() and old_abs_path != file_path and self._file_matches(old_abs_path, raw_bytes):
                old_abs_path.unlink()
        else:
            suffix = file_path.suffix.lstrip(".") or "png"
            auto_rel = ensure_relative_path(f"screenshots/{sid}.{suffix}")
            auto_abs_path = self._relative_to_abs(auto_rel)
            if auto_rel != rel and auto_abs_path.exists() and self._file_matches(auto_abs_path, raw_bytes):
                auto_abs_path.unlink()
                old_rel = auto_rel

        self._written_ids.add(sid)
        self._paths_by_id[sid] = rel
        mime_type = "image/jpeg" if file_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        return old_rel, ScreenshotRef(
            id=sid,
            captured_at=time.time(),
            mime_type=mime_type,
            storage="file",
            path=rel,
        )

    def _relative_to_abs(self, rel_path: str) -> Path:
        normalized = rel_path[2:] if rel_path.startswith("./") else rel_path.lstrip("/\\")
        return self.report_path.parent / normalized
