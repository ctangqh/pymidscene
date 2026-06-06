from typing import List
from ..types import DeviceAction, DeviceActionParamSchema


def define_action_sleep(time_ms: int = 1000) -> DeviceAction:
    """Define the Sleep action"""
    return DeviceAction(
        name="Sleep",
        description="Wait for a specified duration",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={"timeMs": {"type": "number", "description": "Time to sleep in milliseconds"}},
            required=["timeMs"],
        ),
        delay_before_runner=0,
        delay_after_runner=0,
    )


# Pre-defined action definitions for web browser
WEB_ACTION_SPACE: List[DeviceAction] = [
    DeviceAction(
        name="Tap",
        description="Click on an element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the element to tap"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="RightClick",
        description="Right-click on an element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the element to right-click"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="DoubleClick",
        description="Double-click on an element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the element to double-click"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="Hover",
        description="Hover over an element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the element to hover over"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="Input",
        description="Type text into an input element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the input element"},
                "value": {"type": "string", "description": "Text to input"},
                "mode": {"type": "string", "enum": ["replace", "clear", "typeOnly", "append"], "description": "Input mode"},
            },
            required=["locate", "value"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="KeyboardPress",
        description="Press a keyboard key",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Optional locate parameter for focusing element first"},
                "keyName": {"type": "string", "description": "Key name to press"},
            },
            required=["keyName"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="Scroll",
        description="Scroll the page",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Optional locate for scroll target"},
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "scrollType": {"type": "string", "enum": ["singleAction", "scrollToBottom", "scrollToTop", "scrollToRight", "scrollToLeft"]},
                "distance": {"type": "number"},
            },
        ),
        delay_before_runner=200,
        delay_after_runner=500,
    ),
    DeviceAction(
        name="LongPress",
        description="Long press on an element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the element to long press"},
                "duration": {"type": "number", "description": "Duration in ms"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="ClearInput",
        description="Clear the content of an input element",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the input element"},
            },
            required=["locate"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="Pinch",
        description="Pinch gesture (zoom in/out)",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={
                "locate": {"type": "object", "description": "Locate parameter for the pinch center"},
                "direction": {"type": "string", "enum": ["in", "out"]},
                "distance": {"type": "number"},
                "duration": {"type": "number"},
            },
            required=["direction"],
        ),
        delay_before_runner=200,
        delay_after_runner=300,
    ),
    DeviceAction(
        name="Sleep",
        description="Wait for a specified duration",
        param_schema=DeviceActionParamSchema(
            type="object",
            properties={"timeMs": {"type": "number", "description": "Time to sleep in milliseconds"}},
            required=["timeMs"],
        ),
        delay_before_runner=0,
        delay_after_runner=0,
    ),
]