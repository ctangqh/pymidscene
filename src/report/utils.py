from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Sequence


_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|cookie|set-cookie|token|access[_-]?token|refresh[_-]?token|secret)",
    re.IGNORECASE,
)


def ensure_relative_path(path: str) -> str:
    if path.startswith("./"):
        return path
    if path.startswith("/"):
        return "." + path
    return "./" + path


def safe_script_json(obj: Any) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    return text.replace("</", "<\\/")


def extract_raw_base64(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("data:image/") and ";base64," in raw:
        return raw.split(";base64,", 1)[1]
    return raw


def decode_base64_to_bytes(value: str) -> bytes:
    raw = extract_raw_base64(value)
    return base64.b64decode(raw, validate=False)


def sha1_id(data: bytes, length: int = 16) -> str:
    return hashlib.sha1(data).hexdigest()[:length]


def truncate_text(value: Any, max_len: int) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= max_len:
        return value
    return value[:max_len] + "...(truncated)"


def mask_secret_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            return value
        if len(value) <= 6:
            return "***"
        return value[:2] + "***" + value[-2:]
    return "***"


def sanitize_obj(
    obj: Any,
    *,
    max_text_len: int = 2000,
    extra_secret_keys: Iterable[str] | None = None,
) -> Any:
    secret_keys = set(k.lower() for k in (extra_secret_keys or []))

    def is_secret_key(key: str) -> bool:
        k = key.lower()
        return k in secret_keys or _SECRET_KEY_PATTERN.search(k) is not None

    def sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            out: Dict[str, Any] = {}
            for k, v in value.items():
                if not isinstance(k, str):
                    out[str(k)] = sanitize(v)
                    continue
                if is_secret_key(k):
                    out[k] = mask_secret_value(v)
                    continue
                out[k] = sanitize(v)
            return out
        if isinstance(value, (list, tuple)):
            return [sanitize(v) for v in value]
        if isinstance(value, str):
            return truncate_text(value, max_text_len)
        return value

    return sanitize(obj)


def deep_get(d: Mapping[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def deep_set(d: MutableMapping[str, Any], keys: Sequence[str], value: Any) -> None:
    cur: MutableMapping[str, Any] = d
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, MutableMapping):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value
