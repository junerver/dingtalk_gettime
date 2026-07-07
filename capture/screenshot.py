# capture/screenshot.py
import base64
import ctypes
import io
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

logger = logging.getLogger(__name__)


class ScreenshotManager:
    FALLBACK_TITLEBAR_HEIGHT = 30
    WINDOW_ACTIVATE_DELAY = 0.2

    def __init__(self, save_dir: str = "./data/screenshots"):
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def capture_region(self, x: int, y: int, width: int, height: int) -> Image.Image:
        """截取屏幕指定区域。"""
        import pyautogui
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        return screenshot

    def _capture_window_by_handle(self, window) -> Image.Image | None:
        hwnd = self._read_attr(window, "hwnd")
        if not hwnd:
            hwnd = self._call_method(window, "getHandle")
        if not hwnd:
            return None

        try:
            import win32con
            import win32gui
            import win32ui
        except ImportError as e:
            logger.debug(f"pywin32不可用，无法按窗口句柄截图: {e}")
            return None

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            raise ValueError("窗口句柄截图区域无效")

        window_dc = win32gui.GetWindowDC(hwnd)
        source_dc = win32ui.CreateDCFromHandle(window_dc)
        memory_dc = source_dc.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source_dc, width, height)
        old_bitmap = memory_dc.SelectObject(bitmap)

        try:
            rendered = ctypes.windll.user32.PrintWindow(
                hwnd,
                memory_dc.GetSafeHdc(),
                0x00000002,
            )
            if rendered != 1:
                rendered = ctypes.windll.user32.PrintWindow(
                    hwnd,
                    memory_dc.GetSafeHdc(),
                    0,
                )
            if rendered != 1:
                raise RuntimeError("PrintWindow未能渲染窗口内容")

            bitmap_info = bitmap.GetInfo()
            bitmap_bytes = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
                bitmap_bytes,
                "raw",
                "BGRX",
                0,
                1,
            ).copy()
        finally:
            memory_dc.SelectObject(old_bitmap)
            win32gui.DeleteObject(bitmap.GetHandle())
            memory_dc.DeleteDC()
            source_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, window_dc)

        try:
            client_left, client_top = win32gui.ClientToScreen(hwnd, (0, 0))
            client_right, client_bottom = win32gui.ClientToScreen(
                hwnd,
                win32gui.GetClientRect(hwnd)[2:],
            )
            crop_box = (
                max(0, client_left - left),
                max(0, client_top - top),
                min(image.width, client_right - left),
                min(image.height, client_bottom - top),
            )
            if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                image = image.crop(crop_box)
        except Exception as e:
            logger.debug(f"裁剪窗口客户端区域失败，保留完整窗口截图: {e}")

        return image

    @staticmethod
    def _read_attr(obj, name: str, default=None):
        try:
            value = getattr(obj, name)
        except Exception:
            return default
        return value() if callable(value) else value

    @staticmethod
    def _call_method(obj, name: str, *args, **kwargs):
        method = getattr(obj, name, None)
        if not callable(method):
            return None
        try:
            return method(*args, **kwargs)
        except TypeError:
            return method()

    @classmethod
    def _read_int(cls, obj, name: str):
        value = cls._read_attr(obj, name)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _rect_to_region(cls, rect):
        if rect is None:
            return None

        left = cls._read_int(rect, "left")
        top = cls._read_int(rect, "top")
        width = cls._read_int(rect, "width")
        height = cls._read_int(rect, "height")

        if width is None:
            right = cls._read_int(rect, "right")
            if left is not None and right is not None:
                width = right - left

        if height is None:
            bottom = cls._read_int(rect, "bottom")
            if top is not None and bottom is not None:
                height = bottom - top

        if None in (left, top, width, height):
            return None

        if width <= 0 or height <= 0:
            return None

        return left, top, width, height

    @classmethod
    def _window_bounds_region(cls, window):
        left = cls._read_int(window, "left")
        top = cls._read_int(window, "top")
        width = cls._read_int(window, "width")
        height = cls._read_int(window, "height")

        if None not in (left, top, width, height):
            if width > 0 and height > 0:
                return left, top, width, height
            return None

        return cls._rect_to_region(cls._read_attr(window, "rect"))

    def _prepare_window_for_capture(self, window) -> None:
        action_performed = False

        if self._read_attr(window, "isMinimized", False):
            self._call_method(window, "restore", wait=True)
            action_performed = True

        if self._read_attr(window, "visible", True) is False:
            self._call_method(window, "show")
            action_performed = True

        if callable(getattr(window, "raiseWindow", None)):
            self._call_method(window, "raiseWindow")
            action_performed = True

        if callable(getattr(window, "activate", None)):
            self._call_method(window, "activate", wait=True)
            action_performed = True

        if action_performed:
            time.sleep(self.WINDOW_ACTIVATE_DELAY)

        if self._read_attr(window, "isActive", True) is False:
            logger.warning("窗口可能未处于前台，截图内容可能被遮挡")

    def _get_capture_region(self, window) -> tuple[int, int, int, int]:
        try:
            client_rect = self._call_method(window, "getClientFrame")
        except Exception as e:
            logger.debug(f"读取窗口客户端区域失败，回退到窗口边界: {e}")
            client_rect = None

        region = self._rect_to_region(client_rect)
        if region is not None:
            return region

        region = self._window_bounds_region(window)
        if region is None:
            raise ValueError("无法计算窗口截图区域")

        x, y, width, height = region
        y += self.FALLBACK_TITLEBAR_HEIGHT
        height -= self.FALLBACK_TITLEBAR_HEIGHT
        if height <= 0:
            raise ValueError("窗口内容区域高度无效")
        return x, y, width, height

    def capture_window(self, window) -> Image.Image:
        """截取指定窗口的内容区域。"""
        try:
            self._prepare_window_for_capture(window)

            image = self._capture_window_by_handle(window)
            if image is not None:
                logger.debug(f"已通过窗口句柄截图: size={image.size}")
                return image

            if self._read_attr(window, "isActive", True) is False:
                raise RuntimeError("窗口未处于前台且无法通过窗口句柄截图，拒绝截取屏幕区域")

            x, y, width, height = self._get_capture_region(window)
            logger.debug(f"窗口截图区域: x={x}, y={y}, width={width}, height={height}")
            return self.capture_region(x, y, width, height)
        except Exception as e:
            logger.error(f"窗口截图失败: {e}")
            raise

    def save(self, image: Image.Image, prefix: str = "dingtalk") -> str:
        """保存截图到文件，返回文件路径。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{timestamp}.png"
        filepath = self.save_dir / filename
        image.save(str(filepath))
        logger.debug(f"截图已保存: {filepath}")
        return str(filepath)

    def stitch_vertical(self, image_paths: list[str], prefix: str = "dingtalk_stitched") -> str:
        """使用 ImageMagick 将多张图片按传入顺序上下拼接。"""
        if not image_paths:
            raise ValueError("拼接图片列表不能为空")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filepath = self.save_dir / f"{prefix}_{timestamp}.png"
        command = [
            "magick",
            "convert",
            "-append",
            *[str(Path(path)) for path in image_paths],
            str(filepath),
        ]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise RuntimeError("未找到 magick 命令，无法拼接截图") from e
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or "").strip()
            raise RuntimeError(f"magick 拼接截图失败: {detail}") from e

        if not filepath.exists():
            raise RuntimeError("magick 执行完成但未生成拼接图片")

        logger.debug(f"拼接截图已保存: {filepath}")
        return str(filepath)

    @staticmethod
    def crop_by_ratios(
        image: Image.Image,
        left_ratio: float = 0.0,
        top_ratio: float = 0.0,
        right_ratio: float = 1.0,
        bottom_ratio: float = 1.0,
    ) -> Image.Image:
        """按图片比例裁剪区域。"""
        left_ratio = min(max(left_ratio, 0.0), 1.0)
        top_ratio = min(max(top_ratio, 0.0), 1.0)
        right_ratio = min(max(right_ratio, 0.0), 1.0)
        bottom_ratio = min(max(bottom_ratio, 0.0), 1.0)

        left = int(image.width * left_ratio)
        top = int(image.height * top_ratio)
        right = int(image.width * right_ratio)
        bottom = int(image.height * bottom_ratio)

        if right <= left or bottom <= top:
            raise ValueError("截图裁剪区域无效")

        return image.crop((left, top, right, bottom))

    @staticmethod
    def to_base64(image: Image.Image) -> str:
        """将图片转为base64字符串。"""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    @staticmethod
    def file_to_base64(image_path: str) -> str:
        """将图片文件转为base64字符串。"""
        return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")

    def is_mostly_blank(self, image: Image.Image, threshold: float = 0.95) -> bool:
        """检测截图是否大部分为空白。"""
        pixels = list(image.getdata())
        total = len(pixels)
        blank_count = sum(1 for p in pixels if all(c > 240 for c in p[:3]))
        ratio = blank_count / total
        return ratio > threshold

    @staticmethod
    def changed_pixel_ratio(
        before: Image.Image,
        after: Image.Image,
        threshold: int = 8,
    ) -> float:
        """计算两张截图显著变化的像素比例。"""
        if before.size != after.size:
            after = after.resize(before.size)

        diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
        pixels = diff.getdata()
        total = before.width * before.height
        changed = sum(1 for pixel in pixels if any(channel > threshold for channel in pixel))
        return changed / total

    @classmethod
    def images_are_similar(
        cls,
        before: Image.Image,
        after: Image.Image,
        max_changed_ratio: float = 0.002,
    ) -> bool:
        """判断两张截图是否几乎没有变化。"""
        return cls.changed_pixel_ratio(before, after) <= max_changed_ratio
