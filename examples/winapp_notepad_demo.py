"""
Example: Use PyMidscene to control Windows Notepad via WinApp MCP Server.

This demo demonstrates:
1. Connecting to a remote WinApp MCP Server via SSE.
2. Creating a Notepad session via the MCP tool.
3. Locating the editor with the unified SDK locator and inputting text.
4. Taking a screenshot.
"""
import os
import sys
import time
import json
import base64
import xml.etree.ElementTree as ET
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sdk.pymidscene import PyMidscene
from common.logger import logger
from common.config import settings
from core.anomaly_guard import UIAnomalyGuard
from core.visualizer import annotate_screenshot, format_box_label

CURRENT_PROVIDER = "openai"
CURRENT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
CURRENT_LLM_MODEL = "Doubao-Seed-2.0-pro"


def extract_source_xml(source_text: str) -> str:
    if not source_text:
        return ""
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError:
        return source_text
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, str):
            return value
    return source_text


def find_named_element_center(source_text: str, target_name: str):
    xml_text = extract_source_xml(source_text)
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    for node in root.iter():
        if node.attrib.get("Name") != target_name:
            continue
        try:
            x = float(node.attrib["x"])
            y = float(node.attrib["y"])
            width = float(node.attrib["width"])
            height = float(node.attrib["height"])
        except (KeyError, ValueError):
            continue
        return (x + width / 2.0, y + height / 2.0)
    return None


def find_root_window_center(source_text: str):
    xml_text = extract_source_xml(source_text)
    if not xml_text:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    try:
        x = float(root.attrib["x"])
        y = float(root.attrib["y"])
        width = float(root.attrib["width"])
        height = float(root.attrib["height"])
    except (KeyError, ValueError):
        return None
    return (x + width / 2.0, y + height / 2.0)


def has_unsaved_dialog_controls(source_text: str) -> bool:
    xml_text = extract_source_xml(source_text)
    if not xml_text:
        return False
    return any(name in xml_text for name in ("不保存", "保存", "取消"))


def collect_all_element_annotations(source_text: str):
    xml_text = extract_source_xml(source_text)
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    annotations = []
    for node in root.iter():
        try:
            x = float(node.attrib["x"])
            y = float(node.attrib["y"])
            width = float(node.attrib["width"])
            height = float(node.attrib["height"])
        except (KeyError, ValueError):
            continue

        if width <= 0 or height <= 0:
            continue

        rect = {
            "left": x,
            "top": y,
            "width": width,
            "height": height,
        }
        control_type = node.attrib.get("LocalizedControlType") or node.tag or "element"
        name = (node.attrib.get("Name") or "").strip()
        label = format_box_label(rect, control_type)
        if name:
            label = f"{label}\n{name}"
        annotations.append({"rect": rect, "label": label})
    return annotations


def save_ui_snapshot_artifacts(midscene: PyMidscene, artifact_prefix: str):
    source_text = midscene.device.get_page_content()
    xml_text = extract_source_xml(source_text)
    screenshot_b64 = midscene.device.screenshot_base64()
    annotations = collect_all_element_annotations(source_text)

    output_dir = project_root / "output" / "ui_debug"
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / f"{artifact_prefix}_raw.png"
    annotated_path = output_dir / f"{artifact_prefix}_all_controls.png"
    source_path = output_dir / f"{artifact_prefix}_source.xml"

    raw_path.write_bytes(base64.b64decode(screenshot_b64))
    source_path.write_text(xml_text, encoding="utf-8")
    annotate_screenshot(screenshot_b64, annotations, str(annotated_path))

    logger.info(
        f"Saved UI snapshot artifacts: raw={raw_path}, "
        f"annotated={annotated_path}, source={source_path}, controls={len(annotations)}"
    )

    return {
        "raw_path": raw_path,
        "annotated_path": annotated_path,
        "source_path": source_path,
        "control_count": len(annotations),
    }


def record_report_checkpoint(midscene: PyMidscene, title: str, content: str = ""):
    try:
        midscene._run_async(midscene.agent.record_to_report(title, {"content": content}))
        report_path = getattr(midscene.agent, "report_file", None)
        if report_path:
            logger.info(f"Report checkpoint saved: {title} -> {report_path}")
    except Exception as e:
        logger.warning(f"Failed to record report checkpoint '{title}': {e}")


def main():
    run_id = int(time.time() * 1000)
    report_name = f"winapp-notepad-demo-{run_id}"

    llm_provider = settings.llm_config.provider or CURRENT_PROVIDER
    llm_options = {
        "base_url": settings.llm_config.base_url or CURRENT_BASE_URL,
        "model": settings.llm_config.model or CURRENT_LLM_MODEL,
        "api_key": settings.llm_config.api_key,
    }

    vision_provider = settings.vision_config.provider or llm_provider
    vision_options = {
        key: value
        for key, value in {
            "model": settings.vision_config.model,
            "base_url": settings.vision_config.base_url,
            "api_key": settings.vision_config.api_key,
        }.items()
        if value
    }

    # 1. Initialize PyMidscene with WinApp MCP provider
    midscene = PyMidscene(
        device_provider="mcp_winapp",
        llm_provider=llm_provider,
        llm_options=llm_options,
        vision_provider=vision_provider,
        vision_options=vision_options,
        device_options={
            "mcp_name": "winapp",  # Matches settings.MCP_SERVERS
            "mcp_server_url": os.getenv("WINAPP_MCP_URL") or (settings.MCP_SERVERS.get("winapp").url if settings.MCP_SERVERS.get("winapp") else ""),
        },
        report_file_name=report_name,
        generate_report=True,
        persist_execution_dump=True,
        auto_print_report_msg=True,
        output_format="html-and-external-assets",
        group_name="WinApp Notepad Demo Report",
        group_description="Formal report generated from examples/winapp_notepad_demo.py",
    )

    final_report_path = None
    try:
        logger.info("Starting WinApp MCP Demo...")
        logger.info(f"LLM model: {llm_options['model']}, Vision model: {vision_options.get('model')}")
        logger.info(f"Report name: {report_name}")

        # 2. Launch the SDK (connects to MCP Server via SSE)
        midscene.launch()

        # 3. Create a Notepad session via MCP tool
        logger.info("Creating Notepad session...")
        result = midscene.device._execute_mcp_action(
            "create_session",
            app="notepad.exe",
            platform_name="Windows",
            device_name="WindowsPC"
        )
        logger.info(f"Session result: {result}")
        time.sleep(2)  # Wait for Notepad to fully start
        record_report_checkpoint(midscene, "Session created", "Notepad session created successfully.")

        # 4. Use the unified SDK locator. For WinApp this now goes through the
        # visual-first locator path instead of hardcoded AutomationId input.
        logger.info("Locating Notepad editor and inputting text via PyMidscene...")
        midscene.input("文本编辑器", "Hello PyMidscene")
        record_report_checkpoint(midscene, "Text input completed", "Text was entered into the Notepad editor.")

        # 5. Take a screenshot via MCP tool
        output_path = project_root / "output" / f"notepad_screenshot_{run_id}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Taking screenshot: {output_path}")
        img_bytes = midscene.screenshot(str(output_path))
        logger.info(f"Screenshot saved: {output_path} ({len(img_bytes)} bytes)")
        record_report_checkpoint(midscene, "Screenshot captured", f"Screenshot saved to {output_path}.")

        try:
            focus_source = midscene.device.get_page_content()
            window_pos = find_root_window_center(focus_source)
            if window_pos:
                midscene.device.click(position=window_pos)
                time.sleep(0.3)
            focus_pos = find_named_element_center(focus_source, "文本编辑器")
            if focus_pos:
                midscene.device.click(position=focus_pos)
                time.sleep(0.5)
        except Exception:
            pass

        logger.info("Sending Alt+F4 to trigger the unsaved-changes dialog...")
        guard_result = midscene.keyboard_press("Alt+F4")
        logger.info(f"Alt+F4 anomaly-guard result: {guard_result}")
        record_report_checkpoint(midscene, "Alt+F4 sent", f"Anomaly guard result: {guard_result}")
        time.sleep(1)

        logger.info("Saving the first close-state UI snapshot with all detected control bounding boxes...")
        first_close_artifacts = save_ui_snapshot_artifacts(midscene, f"{run_id}_notepad_close_state_step1")
        record_report_checkpoint(
            midscene,
            "Close-state snapshot saved",
            f"Saved annotated close-state artifacts to {first_close_artifacts['annotated_path']}.",
        )

        page_source_after_first_close = midscene.device.get_page_content()
        if not has_unsaved_dialog_controls(page_source_after_first_close):
            logger.info("Unsaved-changes dialog not visible after the first Alt+F4, sending Alt+F4 again...")
            midscene.keyboard_press("Alt+F4")
            time.sleep(1)
            logger.info("Saving the second close-state UI snapshot with all detected control bounding boxes...")
            second_close_artifacts = save_ui_snapshot_artifacts(midscene, f"{run_id}_notepad_close_state_step2")
            record_report_checkpoint(
                midscene,
                "Second close-state snapshot saved",
                f"Saved second annotated close-state artifacts to {second_close_artifacts['annotated_path']}.",
            )
        else:
            logger.info(
                f"Unsaved-changes dialog controls detected after the first close click: {first_close_artifacts['source_path']}"
            )

        logger.info("Trying to resolve the unsaved-changes dialog via UIAnomalyGuard...")
        final_guard_result = UIAnomalyGuard(
            midscene.device,
            llm=midscene.llm,
            vision_llm=midscene.vision_model or midscene.llm,
        ).handle_sync("dismiss_unsaved_changes_dialog")
        logger.info(f"Final anomaly-guard result: {final_guard_result}")
        record_report_checkpoint(
            midscene,
            "Final anomaly guard handled dialog",
            f"Final anomaly guard result: {final_guard_result}",
        )
        time.sleep(2)

        logger.info("Demo completed successfully!")
        record_report_checkpoint(midscene, "Demo completed", "WinApp Notepad demo completed successfully.")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        record_report_checkpoint(midscene, "Demo failed", f"Demo failed: {e}")
    finally:
        # 6. Cleanup - close session and MCP connection
        try:
            # Cleanup only: if the save dialog is still present, close it deterministically.
            page_source = midscene.device.get_page_content()
            dont_save_button = find_named_element_center(page_source, "不保存")
            if dont_save_button:
                logger.info("Cleanup: clicking '不保存' to close the remaining save dialog.")
                midscene.device.click(position=dont_save_button)
                time.sleep(1)
        except Exception:
            pass
        try:
            midscene.device._execute_mcp_action("delete_session")
            logger.info("Session closed.")
        except:
            pass
        try:
            if getattr(midscene, "_agent", None) is not None:
                final_report_path = midscene._run_async(midscene.agent._report_generator.finalize())
                logger.info(f"Final report path: {final_report_path}")
        except Exception as e:
            logger.warning(f"Finalize report failed: {e}")
        midscene.close()
        logger.info("MCP connection closed.")


if __name__ == "__main__":
    main()
