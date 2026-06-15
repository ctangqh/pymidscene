from device.mcp.client import McpPlaywrightDevice


def test_mcp_playwright_size_prefers_runtime_viewport():
    device = McpPlaywrightDevice(viewport_width=1440, viewport_height=900)
    device.evaluate_script = lambda script, *args: {"width": 1280, "height": 720}

    assert device.size() == (1280, 720)


def test_mcp_playwright_size_falls_back_to_configured_viewport():
    device = McpPlaywrightDevice(viewport_width=1440, viewport_height=900)
    device.evaluate_script = lambda script, *args: None

    assert device.size() == (1440, 900)


def run_all_mcp_playwright_size_checks():
    test_mcp_playwright_size_prefers_runtime_viewport()
    test_mcp_playwright_size_falls_back_to_configured_viewport()


if __name__ == "__main__":
    run_all_mcp_playwright_size_checks()
    print("all mcp playwright size checks passed")
