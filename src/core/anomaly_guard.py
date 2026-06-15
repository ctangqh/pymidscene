import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from common.config import settings
from common.exceptions import ActionExecutionError, SystemDialogDetectedError
from common.json_utils import parse_relaxed_json_object
from common.logger import logger
from llm import MessageBuilder


def _center_from_ltrb(bbox: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    if not bbox:
        return None
    left = bbox.get("left")
    top = bbox.get("top")
    right = bbox.get("right")
    bottom = bbox.get("bottom")
    if left is None or top is None or right is None or bottom is None:
        return None
    try:
        return ((float(left) + float(right)) / 2.0, (float(top) + float(bottom)) / 2.0)
    except Exception:
        return None


def _ensure_ltrb(bbox: Dict[str, Any]) -> Dict[str, Any]:
    if not bbox:
        return {}
    if "left" in bbox and "top" in bbox and "right" in bbox and "bottom" in bbox:
        return bbox
    if "left" in bbox and "top" in bbox and "width" in bbox and "height" in bbox:
        return {
            "left": bbox["left"],
            "top": bbox["top"],
            "right": bbox["left"] + bbox["width"],
            "bottom": bbox["top"] + bbox["height"],
        }
    if "x" in bbox and "y" in bbox and "width" in bbox and "height" in bbox:
        return {
            "left": bbox["x"],
            "top": bbox["y"],
            "right": bbox["x"] + bbox["width"],
            "bottom": bbox["y"] + bbox["height"],
        }
    return bbox


def _get_image_size_from_b64(screenshot_b64: str) -> Tuple[int, int]:
    try:
        image_module = __import__("PIL.Image", fromlist=["Image"])
        image = image_module.open(BytesIO(base64.b64decode(screenshot_b64)))
        return int(getattr(image, "width", 0) or 0), int(getattr(image, "height", 0) or 0)
    except Exception:
        return 0, 0


def _scale_ltrb_if_needed(bbox: Dict[str, Any], width: int, height: int) -> Dict[str, Any]:
    bbox = _ensure_ltrb(bbox)
    if not bbox:
        return {}
    try:
        left = float(bbox.get("left"))
        top = float(bbox.get("top"))
        right = float(bbox.get("right"))
        bottom = float(bbox.get("bottom"))
    except Exception:
        return bbox

    if width <= 0 or height <= 0:
        return {"left": left, "top": top, "right": right, "bottom": bottom}

    max_abs = max(abs(left), abs(top), abs(right), abs(bottom))
    if max_abs <= 1.5:
        left *= width
        right *= width
        top *= height
        bottom *= height
    else:
        if max_abs > max(width, height) * 1.2:
            ref_w = float(getattr(settings, "DEVICE_VIEWPORT_WIDTH", 0) or 0)
            ref_h = float(getattr(settings, "DEVICE_VIEWPORT_HEIGHT", 0) or 0)
            if ref_w > 0 and ref_h > 0:
                sx = width / ref_w
                sy = height / ref_h
                left *= sx
                right *= sx
                top *= sy
                bottom *= sy

    left = max(0.0, min(left, float(width)))
    right = max(0.0, min(right, float(width)))
    top = max(0.0, min(top, float(height)))
    bottom = max(0.0, min(bottom, float(height)))
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def _normalize_candidate_actions(actions: Any) -> List[Dict[str, Any]]:
    if not isinstance(actions, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        bbox = _ensure_ltrb(item.get("bbox") or item.get("rect") or {})
        normalized.append(
            {
                "label": str(item.get("label") or "").strip(),
                "role": str(item.get("role") or "other").strip(),
                "bbox": bbox,
            }
        )
    return normalized


def _safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "_", text).strip("_") or "anomaly"


def _describe_llm(llm: Any) -> str:
    if llm is None:
        return "None"
    model = getattr(llm, "model", None)
    base_url = getattr(llm, "base_url", None)
    return f"{llm.__class__.__name__}(model={model}, base_url={base_url})"


class UIAnomalyGuard:
    def __init__(self, device, llm=None, vision_llm=None, screenshot_dir_resolver=None):
        self.device = device
        self.llm = llm
        self.vision_llm = vision_llm or llm
        self.screenshot_dir_resolver = screenshot_dir_resolver

    def _get_debug_screenshot_dir(self) -> Path:
        resolver = self.screenshot_dir_resolver or getattr(self.device, "_pymidscene_report_screenshot_dir_resolver", None)
        if callable(resolver):
            try:
                save_dir = resolver()
                if isinstance(save_dir, Path):
                    save_dir.mkdir(parents=True, exist_ok=True)
                    return save_dir
            except Exception as e:
                logger.debug(f"获取异常调试截图目录失败，回退到默认目录: {e}")
        save_dir = settings.report_screenshot_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    async def _chat_with_screenshot(self, llm, prompt: str, screenshot_b64: str) -> str:
        if screenshot_b64:
            messages = [MessageBuilder.user_text_with_image_base64(prompt, screenshot_b64, mime_type="image/png")]
        else:
            messages = [MessageBuilder.user_text(prompt)]
        chat = getattr(llm, "chat", None)
        if callable(chat):
            resp = chat(messages, max_tokens=1400)
        else:
            raw_chat = getattr(llm, "_chat", None)
            if not callable(raw_chat):
                raise ValueError("LLM instance does not provide chat or _chat")
            encode_messages = getattr(llm, "encode_messages", None)
            encoded_messages = encode_messages(messages) if callable(encode_messages) else messages
            resp = raw_chat(encoded_messages, max_tokens=1400)
        if hasattr(resp, "__await__"):
            resp = await resp
        return str(resp or "")

    async def _chat_json(self, llm, prompt: str, screenshot_b64: str) -> Dict[str, Any]:
        resp = await self._chat_with_screenshot(llm, prompt, screenshot_b64)
        return parse_relaxed_json_object(resp, context="anomaly guard model response")

    async def detect_page_anomaly(self, action_name: str, screenshot_b64: Optional[str] = None) -> Dict[str, Any]:
        if not settings.ANOMALY_GUARD_ENABLED:
            return {"status": "disabled"}
        llm = self.vision_llm
        if llm is None:
            return {"status": "unavailable", "error": "vision llm not configured"}

        screenshot_b64 = screenshot_b64 or self.device.screenshot_base64()
        shot_w, shot_h = _get_image_size_from_b64(screenshot_b64)
        logger.debug(
            f"[AnomalyGuard] page-detect start: action={action_name}, "
            f"vision_llm={_describe_llm(llm)}, screenshot_bytes={len(screenshot_b64)}"
        )
        prompt = (
            "You are a page-level UI anomaly detector. Analyze the entire current screen, not just one button.\n"
            "Determine whether the whole page is blocked by an abnormal modal/dialog/overlay that interrupts the current task.\n"
            f"Screenshot size: width={shot_w}, height={shot_h}. Coordinates must be in screenshot pixels.\n"
            "Return only valid JSON:\n"
            "{\n"
            "  \"has_blocking_anomaly\": bool,\n"
            "  \"anomaly_kind\": \"none\"|\"web_modal\"|\"native_modal\"|\"system_dialog\"|\"toast\"|\"blocking_overlay\"|\"error_dialog\",\n"
            "  \"confidence\": float,\n"
            "  \"screen_state\": string,\n"
            "  \"dialog_title\": string,\n"
            "  \"dialog_message\": string,\n"
            "  \"anomaly_bbox\": {\"left\": number, \"top\": number, \"right\": number, \"bottom\": number} | null,\n"
            "  \"close_button_bbox\": {\"left\": number, \"top\": number, \"right\": number, \"bottom\": number} | null,\n"
            "  \"candidate_actions\": [\n"
            "    {\"label\": string, \"role\": \"confirm\"|\"dismiss\"|\"cancel\"|\"close\"|\"other\", \"bbox\": {\"left\": number, \"top\": number, \"right\": number, \"bottom\": number}}\n"
            "  ],\n"
            "  \"reason\": string\n"
            "}\n"
            "Rules:\n"
            "- Look at the full page state first. If a modal dialog blocks the main window, set has_blocking_anomaly=true.\n"
            "- Extract all visible actionable buttons on the blocking dialog into candidate_actions.\n"
            "- For browser/system native dialogs, use anomaly_kind=system_dialog.\n"
            "- If there is no blocking anomaly, return has_blocking_anomaly=false.\n"
            f"Current action: {action_name}\n"
        )
        try:
            data = await self._chat_json(llm, prompt, screenshot_b64)
        except Exception as e:
            logger.debug(f"anomaly page-detect llm failed: {e}")
            return {"status": "unavailable", "error": str(e)}

        has_blocking = bool(data.get("has_blocking_anomaly"))
        confidence = float(data.get("confidence") or 0.0)
        if not has_blocking or confidence < settings.ANOMALY_DETECT_CONFIDENCE_THRESHOLD:
            result = {
                "status": "clear",
                "has_blocking_anomaly": False,
                "confidence": confidence,
                "screen_state": str(data.get("screen_state") or ""),
                "reason": str(data.get("reason") or ""),
            }
            logger.debug(
                f"[AnomalyGuard] page-detect clear: action={action_name}, "
                f"confidence={confidence}, screen_state={result['screen_state']}, reason={result['reason']}"
            )
            return result

        result = {
            "status": "detected",
            "has_blocking_anomaly": True,
            "anomaly_kind": str(data.get("anomaly_kind") or "none"),
            "confidence": confidence,
            "screen_state": str(data.get("screen_state") or ""),
            "dialog_title": str(data.get("dialog_title") or ""),
            "dialog_message": str(data.get("dialog_message") or ""),
            "anomaly_bbox": _scale_ltrb_if_needed(data.get("anomaly_bbox") or data.get("bbox") or {}, shot_w, shot_h),
            "close_button_bbox": _scale_ltrb_if_needed(data.get("close_button_bbox") or {}, shot_w, shot_h),
            "candidate_actions": [],
            "reason": str(data.get("reason") or ""),
        }
        for item in _normalize_candidate_actions(data.get("candidate_actions")):
            bbox = _scale_ltrb_if_needed(item.get("bbox") or {}, shot_w, shot_h)
            result["candidate_actions"].append({"label": item.get("label"), "role": item.get("role"), "bbox": bbox})
        logger.info(
            f"[AnomalyGuard] page-detect detected: action={action_name}, kind={result['anomaly_kind']}, "
            f"confidence={result['confidence']}, screen_state={result['screen_state']}, "
            f"dialog_title={result['dialog_title']}, candidate_actions="
            f"{[item.get('label') for item in result['candidate_actions']]}"
        )
        return result

    async def decide_page_anomaly(self, action_name: str, detection: Dict[str, Any], screenshot_b64: str) -> Dict[str, Any]:
        llm = self.llm or self.vision_llm
        if llm is None:
            return {"decision": "ignore", "reason": "decision llm not configured"}

        interface_type = getattr(self.device, "interface_type", "")
        policy = (
            "Policies:\n"
            "- If interface_type is web/browser and anomaly_kind=system_dialog, decision must be fail.\n"
            "- If this is a native blocking anomaly, decision should prefer dismiss so automation can continue.\n"
            "- Prefer buttons that close/dismiss the anomaly while keeping the workflow moving forward, such as "
            "'Close', 'Dismiss', 'Not now', 'Don't Save', or localized equivalents like '关闭', '跳过', '稍后', '不保存', '取消授权'.\n"
            "- Avoid positive confirmation actions like 'Save' unless it is the only action that removes the blocker, including localized variants such as '保存'.\n"
        )
        prompt = (
            "You are a UI anomaly decision maker. The detector has already identified the full-page anomaly state.\n"
            "Decide whether to ignore it, dismiss it, or fail the run.\n"
            "Return only valid JSON:\n"
            "{\n"
            "  \"decision\": \"ignore\"|\"dismiss\"|\"fail\",\n"
            "  \"target_label\": string,\n"
            "  \"target_role\": string,\n"
            "  \"target_bbox\": {\"left\": number, \"top\": number, \"right\": number, \"bottom\": number} | null,\n"
            "  \"reason\": string\n"
            "}\n"
            f"Device interface_type: {interface_type}\n"
            f"Current action: {action_name}\n"
            f"{policy}\n"
            f"Detector output:\n{json.dumps(detection, ensure_ascii=False)}\n"
        )
        logger.debug(
            f"[AnomalyGuard] decision start: action={action_name}, decision_llm={_describe_llm(llm)}, "
            f"kind={detection.get('anomaly_kind')}, candidates="
            f"{[item.get('label') for item in detection.get('candidate_actions') or []]}"
        )
        try:
            data = await self._chat_json(llm, prompt, screenshot_b64)
        except Exception as e:
            logger.debug(f"anomaly decision llm failed: {e}")
            raise ActionExecutionError(f"异常决策模型调用失败: {e}") from e

        result = {
            "decision": str(data.get("decision") or "ignore"),
            "target_label": str(data.get("target_label") or "").strip(),
            "target_role": str(data.get("target_role") or "").strip(),
            "target_bbox": _ensure_ltrb(data.get("target_bbox") or {}),
            "reason": str(data.get("reason") or ""),
        }
        logger.info(
            f"[AnomalyGuard] decision result: action={action_name}, decision={result['decision']}, "
            f"target_label={result['target_label']}, target_role={result['target_role']}, reason={result['reason']}"
        )
        return result

    def _resolve_action_target(self, detection: Dict[str, Any], decision: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        target_bbox = decision.get("target_bbox") or {}
        center = _center_from_ltrb(target_bbox)
        if center:
            logger.info(f"[AnomalyGuard] resolve target by target_bbox: center={center}")
            return center

        target_label = (decision.get("target_label") or "").strip()
        target_role = (decision.get("target_role") or "").strip().lower()
        for action in detection.get("candidate_actions") or []:
            label = (action.get("label") or "").strip()
            role = (action.get("role") or "").strip().lower()
            if target_label and label == target_label:
                center = _center_from_ltrb(action.get("bbox") or {})
                if center:
                    logger.info(f"[AnomalyGuard] resolve target by label match: label={label}, center={center}")
                    return center
            if target_role and role == target_role:
                center = _center_from_ltrb(action.get("bbox") or {})
                if center:
                    logger.info(f"[AnomalyGuard] resolve target by role match: role={role}, center={center}")
                    return center

        fallback = _center_from_ltrb(detection.get("close_button_bbox") or {}) or _center_from_ltrb(detection.get("anomaly_bbox") or {})
        if fallback:
            logger.warning(f"[AnomalyGuard] resolve target fallback to anomaly/close bbox: center={fallback}")
        return fallback

    def _save_debug_artifacts(
        self,
        action_name: str,
        screenshot_b64: str,
        detection: Dict[str, Any],
        decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not settings.DEBUG or not screenshot_b64:
            return
        try:
            from common.image import get_screenshot_save_dir, save_raw_screenshot, annotate_screenshot, format_box_label
            
            out_dir = get_screenshot_save_dir(self._get_debug_screenshot_dir())
            ts = int(time.time() * 1000)
            prefix = f"{ts}_{_safe_name(action_name)}"
            
            # 使用新的抽象方法保存原始截图
            raw_filename = f"{prefix}_raw.png"
            raw_path = save_raw_screenshot(
                screenshot_b64,
                raw_filename,
                is_debug=True,
                save_dir=out_dir,
            )
            
            # 保存标注截图
            ann_filename = f"{prefix}_debug.png"
            ann_path = out_dir / ann_filename

            annotations: List[Dict[str, Any]] = []
            anomaly_bbox = detection.get("anomaly_bbox") or {}
            if anomaly_bbox:
                annotations.append(
                    {
                        "rect": {
                            "left": anomaly_bbox["left"],
                            "top": anomaly_bbox["top"],
                            "width": anomaly_bbox["right"] - anomaly_bbox["left"],
                            "height": anomaly_bbox["bottom"] - anomaly_bbox["top"],
                        },
                        "label": format_box_label(anomaly_bbox, detection.get("anomaly_kind") or "anomaly"),
                        "color": "red",
                    }
                )
            for item in detection.get("candidate_actions") or []:
                bbox = item.get("bbox") or {}
                if not bbox:
                    continue
                annotations.append(
                    {
                        "rect": {
                            "left": bbox["left"],
                            "top": bbox["top"],
                            "width": bbox["right"] - bbox["left"],
                            "height": bbox["bottom"] - bbox["top"],
                        },
                        "label": item.get("label") or item.get("role") or "action",
                        "color": "blue",
                    }
                )
            if decision and decision.get("target_bbox"):
                bbox = decision["target_bbox"]
                annotations.append(
                    {
                        "rect": {
                            "left": bbox["left"],
                            "top": bbox["top"],
                            "width": bbox["right"] - bbox["left"],
                            "height": bbox["bottom"] - bbox["top"],
                        },
                        "label": f"target: {decision.get('target_label') or decision.get('target_role') or 'resolved'}",
                        "color": "green",
                    }
                )
            annotate_screenshot(screenshot_b64, annotations, str(ann_path))
            
            # 保存分析 JSON
            json_filename = f"{prefix}_debug.json"
            json_path = out_dir / json_filename
            json_path.write_text(
                json.dumps({"detection": detection, "decision": decision or {}}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            
            logger.debug(f"anomaly debug save success: raw={raw_path}, annotated={ann_path}, json={json_path}")
        except Exception as e:
            logger.debug(f"anomaly debug save failed: {e}")

    def handle_sync(self, action_name: str) -> Optional[Dict[str, Any]]:
        import asyncio

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return None
        return asyncio.run(self.handle(action_name))

    async def handle(self, action_name: str) -> Optional[Dict[str, Any]]:
        screenshot_b64 = ""
        try:
            screenshot_b64 = self.device.screenshot_base64()
        except Exception as e:
            logger.debug(f"anomaly screenshot failed: {e}")
            return None

        logger.debug(f"[AnomalyGuard] handle start: action={action_name}, interface_type={getattr(self.device, 'interface_type', '')}")
        detection = await self.detect_page_anomaly(action_name, screenshot_b64=screenshot_b64)
        if detection.get("status") != "detected":
            if detection.get("status") == "unavailable":
                logger.warning(f"异常页面检测不可用: {detection.get('error')}")
            else:
                logger.debug(f"[AnomalyGuard] handle end without anomaly: action={action_name}, status={detection.get('status')}")
            return detection if detection else None

        decision = await self.decide_page_anomaly(action_name, detection, screenshot_b64)
        shot_w, shot_h = _get_image_size_from_b64(screenshot_b64)
        if decision and decision.get("target_bbox"):
            decision["target_bbox"] = _scale_ltrb_if_needed(decision.get("target_bbox") or {}, shot_w, shot_h)
        self._save_debug_artifacts(action_name, screenshot_b64, detection, decision)

        interface_type = getattr(self.device, "interface_type", "")
        combined = {"detection": detection, "decision": decision}
        if decision.get("decision") == "ignore":
            logger.info(f"[AnomalyGuard] decision ignored anomaly: action={action_name}")
            return combined

        if decision.get("decision") == "fail":
            if interface_type in ("web", "browser") and detection.get("anomaly_kind") == "system_dialog":
                raise SystemDialogDetectedError(f"检测到异常窗口且策略要求失败: {decision.get('reason') or detection.get('reason')}")
            raise ActionExecutionError(f"检测到异常窗口且策略要求失败: {decision.get('reason') or detection.get('reason')}")

        center = self._resolve_action_target(detection, decision)
        if not center:
            raise ActionExecutionError(
                f"检测到异常状态，但大模型未给出可执行目标: reason={decision.get('reason') or detection.get('reason')}"
            )
        try:
            logger.info(
                f"[AnomalyGuard] execute action: action={action_name}, decision={decision.get('decision')}, "
                f"target_label={decision.get('target_label')}, center={center}"
            )
            self.device.click(position=center)
        except Exception as e:
            raise ActionExecutionError(
                f"基于视觉结果处理异常状态失败: decision={decision.get('decision')}, "
                f"target={decision.get('target_label') or decision.get('target_role')}, error={e}"
            ) from e
        logger.info(f"[AnomalyGuard] execute action done: action={action_name}")
        return combined


PopupGuard = UIAnomalyGuard
