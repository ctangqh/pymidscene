from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser as PlaywrightBrowser, Page
from ..base import BaseDevice
from common.logger import logger
from common.exceptions import BrowserLaunchError, BrowserNavigationError, ActionExecutionError

class PlaywrightBrowser(BaseDevice):
    """Playwright浏览器实现"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._playwright = None
        self._browser: Optional[PlaywrightBrowser] = None
        self._page: Optional[Page] = None

    def launch(self) -> None:
        try:
            logger.info("启动Playwright浏览器...")
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    f"--user-agent={self.user_agent}",
                ]
            )
            self._page = self._browser.new_page(
                viewport={"width": self.viewport_width, "height": self.viewport_height},
                user_agent=self.user_agent,
            )
            self._page.set_default_timeout(self.timeout)
            logger.info("Playwright浏览器启动成功")
        except Exception as e:
            logger.error(f"Playwright浏览器启动失败: {str(e)}")
            raise BrowserLaunchError(f"浏览器启动失败: {str(e)}") from e

    def close(self) -> None:
        if self._page:
            self._page.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        logger.info("Playwright浏览器已关闭")

    def goto(self, url: str, **kwargs) -> None:
        try:
            logger.info(f"导航到页面: {url}")
            self._page.goto(url, timeout=kwargs.get("timeout", self.timeout))
            self.current_url = self._page.url
            logger.info(f"页面加载完成: {self.current_url}")
        except Exception as e:
            logger.error(f"页面导航失败: {str(e)}")
            raise BrowserNavigationError(f"页面导航失败: {str(e)}") from e

    def get_page_content(self) -> str:
        return self._page.content()

    def get_dom_tree(self) -> Dict[str, Any]:
        dom = self._page.evaluate("""() => {
            function extractElement(el) {
                const result = {
                    tagName: el.tagName.toLowerCase(),
                    attributes: {},
                    text: el.textContent.trim(),
                    children: []
                };
                for (const attr of el.attributes) {
                    result.attributes[attr.name] = attr.value;
                }
                for (const child of el.children) {
                    result.children.push(extractElement(child));
                }
                return result;
            }
            return extractElement(document.body);
        }""")
        return dom

    def screenshot(self, save_path: Optional[Path] = None, full_page: bool = True) -> bytes:
        img_bytes = self._page.screenshot(full_page=full_page)
        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(img_bytes)
            logger.debug(f"截图已保存到: {save_path}")
        return img_bytes

    def click(self, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, **kwargs) -> None:
        try:
            if selector:
                logger.debug(f"点击元素: {selector}")
                self._page.click(selector, timeout=kwargs.get("timeout", self.timeout))
            elif position:
                x, y = position
                logger.debug(f"点击坐标: ({x}, {y})")
                self._page.mouse.click(x, y)
            else:
                raise ValueError("selector 和 position 不能同时为空")
        except Exception as e:
            logger.error(f"点击失败: {str(e)}")
            raise ActionExecutionError(f"点击失败: {str(e)}") from e

    def input(self, text: str, selector: Optional[str] = None, position: Optional[Tuple[float, float]] = None, clear_before: bool = True, **kwargs) -> None:
        try:
            if selector:
                logger.debug(f"输入文本到元素 {selector}: {text}")
                if clear_before:
                    self._page.fill(selector, "")
                self._page.fill(selector, text)
            elif position:
                x, y = position
                logger.debug(f"点击坐标({x}, {y})并输入文本: {text}")
                self.click(position=position)
                if clear_before:
                    self._page.keyboard.press("Control+A")
                    self._page.keyboard.press("Backspace")
                self._page.keyboard.type(text)
            else:
                raise ValueError("selector 和 position 不能同时为空")
        except Exception as e:
            logger.error(f"输入失败: {str(e)}")
            raise ActionExecutionError(f"输入失败: {str(e)}") from e

    def scroll(self, direction: str = "down", distance: Optional[int] = None, **kwargs) -> None:
        try:
            distance = distance or self.viewport_height * 0.8
            if direction == "down":
                self._page.evaluate(f"window.scrollBy(0, {distance})")
            elif direction == "up":
                self._page.evaluate(f"window.scrollBy(0, -{distance})")
            elif direction == "left":
                self._page.evaluate(f"window.scrollBy(-{distance}, 0)")
            elif direction == "right":
                self._page.evaluate(f"window.scrollBy({distance}, 0)")
            else:
                raise ValueError(f"不支持的滚动方向: {direction}")
            logger.debug(f"页面向 {direction} 滚动 {distance} 像素")
        except Exception as e:
            logger.error(f"滚动失败: {str(e)}")
            raise ActionExecutionError(f"滚动失败: {str(e)}") from e

    def wait_for_selector(self, selector: str, timeout: Optional[int] = None, **kwargs) -> bool:
        try:
            timeout = timeout or self.timeout
            self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception as e:
            logger.warning(f"等待元素 {selector} 超时")
            return False

    def evaluate_script(self, script: str, *args) -> Any:
        return self._page.evaluate(script, *args)
