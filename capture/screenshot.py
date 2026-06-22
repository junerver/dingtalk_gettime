# capture/screenshot.py
import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class ScreenshotManager:
    def __init__(self, save_dir: str = "./data/screenshots"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """截取屏幕指定区域。"""
        import pyautogui
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        return screenshot

    def capture_window(self, window) -> Image.Image:
        """截取指定窗口的内容区域。"""
        try:
            rect = window.rect
            x = rect.left
            y = rect.top + 30
            width = rect.width
            height = rect.height - 30
            return self.capture_region(x, y, width, height)
        except Exception as e:
            logger.error(f"窗口截图失败: {e}")
            import pyautogui
            return pyautogui.screenshot()

    def save(self, image: Image.Image, prefix: str = "dingtalk") -> str:
        """保存截图到文件，返回文件路径。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = self.save_dir / filename
        image.save(str(filepath))
        logger.debug(f"截图已保存: {filepath}")
        return str(filepath)

    @staticmethod
    def to_base64(image: Image.Image) -> str:
        """将图片转为base64字符串。"""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def is_mostly_blank(self, image: Image.Image, threshold: float = 0.95) -> bool:
        """检测截图是否大部分为空白。"""
        pixels = list(image.getdata())
        total = len(pixels)
        blank_count = sum(1 for p in pixels if all(c > 240 for c in p[:3]))
        ratio = blank_count / total
        return ratio > threshold
