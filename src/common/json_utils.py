import ast
import json
import re
from typing import Any, Dict, Iterable

from .exceptions import ModelResponseError
from .logger import logger


def parse_relaxed_json_object(text: Any, *, context: str = "model response") -> Dict[str, Any]:
    raw_text = str(text or "").strip()
    if not raw_text:
        raise ModelResponseError(f"{context} is empty")

    json_repair = _get_json_repair()
    candidates = list(_candidate_json_texts(raw_text))
    seen: set[str] = set()

    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        parsed = _try_parse_candidate(normalized, json_repair)
        if isinstance(parsed, dict):
            return parsed

    preview = raw_text[:500].replace("\n", "\\n")
    logger.warning(f"{context} JSON parse failed, raw preview={preview}")
    raise ModelResponseError(f"Failed to parse JSON object from {context}")


def _get_json_repair():
    try:
        return __import__("json_repair")
    except Exception:
        return None


def _candidate_json_texts(text: str) -> Iterable[str]:
    yield text

    code_block_matches = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    for match in code_block_matches:
        yield match

    object_block = _extract_braced_object(text)
    if object_block:
        yield object_block


def _extract_braced_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape = False
    quote_char = ""

    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == quote_char:
                in_string = False
            continue

        if char in ('"', "'"):
            in_string = True
            quote_char = char
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return text[start:] if depth > 0 else ""


def _try_parse_candidate(text: str, json_repair) -> Any:
    if json_repair is not None:
        try:
            return json_repair.loads(text)
        except Exception:
            pass

    try:
        return json.loads(text)
    except Exception:
        pass

    try:
        parsed = ast.literal_eval(text)
    except Exception:
        return None

    return parsed if isinstance(parsed, dict) else None
