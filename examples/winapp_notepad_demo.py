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
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sdk.pymidscene import PyMidscene
from common.logger import logger

CURRENT_PROVIDER = "openai"
CURRENT_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"
CURRENT_LLM_MODEL = "Doubao-Seed-2.0-pro"


def main():
    llm_provider = CURRENT_PROVIDER
    llm_options = {
        "base_url": os.getenv("LLM_BASE_URL", CURRENT_BASE_URL),
        "model": os.getenv("LLM_MODEL", os.getenv("PYMID_LLM_MODEL", CURRENT_LLM_MODEL)),
        "api_key": os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY")),
    }

    vision_provider = CURRENT_PROVIDER
    vision_options = {
        key: value
        for key, value in {
            # 当前环境未单独配置视觉模型时，默认复用通用模型参数。
            "model": os.getenv("VISION_MODEL", os.getenv("PYMID_VISION_MODEL", llm_options["model"])),
            "base_url": os.getenv("VISION_BASE_URL", os.getenv("PYMID_VISION_BASE_URL", llm_options["base_url"])),
            "api_key": os.getenv("VISION_API_KEY", os.getenv("PYMID_VISION_API_KEY", llm_options["api_key"])),
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
        }
    )

    try:
        logger.info("Starting WinApp MCP Demo...")
        logger.info(f"LLM model: {llm_options['model']}, Vision model: {vision_options.get('model')}")

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

        # 4. Use the unified SDK locator. For WinApp this now goes through the
        # visual-first locator path instead of hardcoded AutomationId input.
        logger.info("Locating Notepad editor and inputting text via PyMidscene...")
        midscene.input("文本编辑器", "Hello PyMidscene")

        # 5. Take a screenshot via MCP tool
        output_path = project_root / "output" / "notepad_screenshot.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Taking screenshot: {output_path}")
        img_bytes = midscene.screenshot(str(output_path))
        logger.info(f"Screenshot saved: {output_path} ({len(img_bytes)} bytes)")

        logger.info("Demo completed successfully!")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
    finally:
        # 6. Cleanup - close session and MCP connection
        try:
            midscene.device._execute_mcp_action("delete_session")
            logger.info("Session closed.")
        except:
            pass
        midscene.close()
        logger.info("MCP connection closed.")


if __name__ == "__main__":
    main()
