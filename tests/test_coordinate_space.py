from core.agent.agent import Agent
from core.agent.task_builder import TaskBuilder


def test_rect_to_screenshot_space_scales_logical_rect():
    rect = Agent._rect_to_screenshot_space(
        {"left": 100, "top": 50, "width": 200, "height": 40},
        coordinate_space="logical",
        ratio=2.0,
    )

    assert rect == {
        "left": 200.0,
        "top": 100.0,
        "width": 400.0,
        "height": 80.0,
    }


def test_rect_to_screenshot_space_keeps_screenshot_rect():
    rect = Agent._rect_to_screenshot_space(
        {"left": 100, "top": 50, "width": 200, "height": 40},
        coordinate_space="screenshot",
        ratio=2.0,
    )

    assert rect == {
        "left": 100.0,
        "top": 50.0,
        "width": 200.0,
        "height": 40.0,
    }


def test_position_to_device_space_converts_screenshot_position():
    position = TaskBuilder._position_to_device_space(
        (300.0, 120.0),
        coordinate_space="screenshot",
        ratio=2.0,
    )

    assert position == (150.0, 60.0)


def test_position_to_device_space_keeps_logical_position():
    position = TaskBuilder._position_to_device_space(
        (300.0, 120.0),
        coordinate_space="logical",
        ratio=2.0,
    )

    assert position == (300.0, 120.0)


def run_all_coordinate_space_checks():
    test_rect_to_screenshot_space_scales_logical_rect()
    test_rect_to_screenshot_space_keeps_screenshot_rect()
    test_position_to_device_space_converts_screenshot_position()
    test_position_to_device_space_keeps_logical_position()


if __name__ == "__main__":
    run_all_coordinate_space_checks()
    print("all coordinate space checks passed")
