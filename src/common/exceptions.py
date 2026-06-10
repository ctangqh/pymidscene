from typing import Optional, Any


class PyMidsceneBaseException(Exception):
    """基础异常类"""
    code: int = 10000
    message: str = "系统内部错误"
    
    def __init__(self, message: Optional[str] = None, data: Optional[Any] = None):
        self.message = message or self.message
        self.data = data
        super().__init__(self.message)
    
    def __str__(self) -> str:
        return f"[{self.code}] {self.message}" + (f", data: {self.data}" if self.data else "")


# ========== 配置相关异常 ==========
class ConfigError(PyMidsceneBaseException):
    code = 10001
    message = "配置错误"


class MissingAPIKeyError(ConfigError):
    code = 10002
    message = "缺少 API 密钥配置"


# ========== 模型相关异常 ==========
class ModelError(PyMidsceneBaseException):
    code = 20000
    message = "模型调用错误"


class ModelTimeoutError(ModelError):
    code = 20001
    message = "模型调用超时"


class ModelResponseError(ModelError):
    code = 20002
    message = "模型返回结果异常"


class ModelUnsupportedError(ModelError):
    code = 20003
    message = "不支持的模型提供商"


class ImageConstraintError(ModelError):
    code = 20004
    message = "图片不满足模型约束"


class UnsupportedImageMimeTypeError(ImageConstraintError):
    code = 20005
    message = "不支持的图片格式"


class ImageTooLargeError(ImageConstraintError):
    code = 20006
    message = "图片尺寸或体积超限"


class TooManyImagesError(ImageConstraintError):
    code = 20007
    message = "图片数量超限"


class ImagePreprocessFailedError(ImageConstraintError):
    code = 20008
    message = "图片预处理失败"


# ========== 浏览器相关异常 ==========
class BrowserError(PyMidsceneBaseException):
    code = 30000
    message = "浏览器操作错误"


class BrowserLaunchError(BrowserError):
    code = 30001
    message = "浏览器启动失败"


class BrowserNavigationError(BrowserError):
    code = 30002
    message = "页面导航失败"


class ElementNotFoundError(BrowserError):
    code = 30003
    message = "未找到目标元素"


class ActionExecutionError(BrowserError):
    code = 30004
    message = "动作执行失败"


class SystemDialogDetectedError(BrowserError):
    code = 30005
    message = "检测到 Web 原生系统弹窗"


# ========== 定位相关异常 ==========
class LocatorError(PyMidsceneBaseException):
    code = 40000
    message = "元素定位错误"


class LocateConfidenceLowError(LocatorError):
    code = 40001
    message = "定位结果置信度过低"


# ========== 任务相关异常 ==========
class TaskError(PyMidsceneBaseException):
    code = 50000
    message = "任务执行错误"


class TaskTimeoutError(TaskError):
    code = 50001
    message = "任务执行超时"


class TaskParseError(TaskError):
    code = 50002
    message = "任务解析失败"


class YAMLParseError(TaskParseError):
    code = 50003
    message = "YAML 流程解析失败"


# ========== 断言相关异常 ==========
class AssertionError(PyMidsceneBaseException):
    code = 60000
    message = "断言失败"


class AssertionTimeoutError(AssertionError):
    code = 60001
    message = "断言等待超时"


__all__ = [
    "PyMidsceneBaseException",
    "ConfigError",
    "MissingAPIKeyError",
    "ModelError",
    "ModelTimeoutError",
    "ModelResponseError",
    "ModelUnsupportedError",
    "ImageConstraintError",
    "UnsupportedImageMimeTypeError",
    "ImageTooLargeError",
    "TooManyImagesError",
    "ImagePreprocessFailedError",
    "BrowserError",
    "BrowserLaunchError",
    "BrowserNavigationError",
    "ElementNotFoundError",
    "ActionExecutionError",
    "SystemDialogDetectedError",
    "LocatorError",
    "LocateConfidenceLowError",
    "TaskError",
    "TaskTimeoutError",
    "TaskParseError",
    "YAMLParseError",
    "AssertionError",
    "AssertionTimeoutError",
]
