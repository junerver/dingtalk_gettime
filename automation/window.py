import logging
import csv
import ctypes
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DINGTALK_PROCESS_NAMES = {"dingtalk.exe"}
DINGTALK_TITLE_KEYWORDS = ("钉钉", "DingTalk")
MIN_MAIN_WINDOW_AREA = 300 * 200

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


@dataclass
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int


@dataclass
class WindowPoint:
    x: int
    y: int


class Win32Window:
    """pywinctl 找不到隐藏钉钉窗口时使用的最小窗口适配器。"""

    def __init__(self, hwnd: int):
        self.hwnd = hwnd

    @property
    def title(self) -> str:
        if user32 is None:
            return ""
        length = user32.GetWindowTextLengthW(self.hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(self.hwnd, buffer, length + 1)
        return buffer.value

    @property
    def visible(self) -> bool:
        return bool(user32 and user32.IsWindowVisible(self.hwnd))

    @property
    def isMinimized(self) -> bool:
        return bool(user32 and user32.IsIconic(self.hwnd))

    @property
    def isActive(self) -> bool:
        return bool(user32 and user32.GetForegroundWindow() == self.hwnd)

    @property
    def rect(self) -> WindowRect:
        if user32 is None:
            return WindowRect(0, 0, 0, 0)
        rect = wintypes.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return WindowRect(rect.left, rect.top, rect.right, rect.bottom)

    @property
    def left(self) -> int:
        return self.rect.left

    @property
    def top(self) -> int:
        return self.rect.top

    @property
    def width(self) -> int:
        rect = self.rect
        return rect.right - rect.left

    @property
    def height(self) -> int:
        rect = self.rect
        return rect.bottom - rect.top

    def getClientFrame(self) -> WindowRect:
        if user32 is None:
            return self.rect

        client_rect = wintypes.RECT()
        if not user32.GetClientRect(self.hwnd, ctypes.byref(client_rect)):
            return self.rect

        top_left = wintypes.POINT(client_rect.left, client_rect.top)
        bottom_right = wintypes.POINT(client_rect.right, client_rect.bottom)
        user32.ClientToScreen(self.hwnd, ctypes.byref(top_left))
        user32.ClientToScreen(self.hwnd, ctypes.byref(bottom_right))
        return WindowRect(top_left.x, top_left.y, bottom_right.x, bottom_right.y)

    def show(self) -> bool:
        if user32 is None:
            return False
        user32.ShowWindow(self.hwnd, SW_SHOW)
        return True

    def restore(self, wait: bool = False, user: bool = True) -> bool:
        if user32 is None:
            return False
        user32.ShowWindow(self.hwnd, SW_RESTORE)
        if wait:
            time.sleep(0.2)
        return not self.isMinimized

    def raiseWindow(self) -> bool:
        if user32 is None:
            return False
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOP,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
        )
        return True

    def activate(self, wait: bool = False, user: bool = True) -> bool:
        if user32 is None:
            return False

        user32.ShowWindow(self.hwnd, SW_SHOWNORMAL)
        user32.ShowWindow(self.hwnd, SW_RESTORE)
        user32.AllowSetForegroundWindow(-1)

        foreground_hwnd = user32.GetForegroundWindow()
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
        target_thread = user32.GetWindowThreadProcessId(self.hwnd, None)

        attached = []
        for thread_id in {foreground_thread, target_thread}:
            if thread_id and thread_id != current_thread:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)

        try:
            user32.SetWindowPos(
                self.hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.SetWindowPos(
                self.hwnd,
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )
            user32.BringWindowToTop(self.hwnd)
            user32.SetForegroundWindow(self.hwnd)
            user32.SetActiveWindow(self.hwnd)
            user32.SetFocus(self.hwnd)
        finally:
            for thread_id in attached:
                user32.AttachThreadInput(current_thread, thread_id, False)

        if wait:
            time.sleep(0.3)
        return self.isActive


def _read_attr(obj, name: str, default=None):
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return value() if callable(value) else value


def _call_method(obj, name: str, *args, **kwargs):
    method = getattr(obj, name, None)
    if not callable(method):
        return None
    try:
        return method(*args, **kwargs)
    except TypeError:
        return method()


def _window_geometry(window) -> tuple[int, int, int, int]:
    left = _read_attr(window, "left", 0) or 0
    top = _read_attr(window, "top", 0) or 0
    width = _read_attr(window, "width", 0) or 0
    height = _read_attr(window, "height", 0) or 0

    try:
        return int(left), int(top), int(width), int(height)
    except (TypeError, ValueError):
        return 0, 0, 0, 0


def _window_score(window) -> int:
    title = _read_attr(window, "title", "") or ""
    visible = bool(_read_attr(window, "visible", False))
    active = bool(_read_attr(window, "isActive", False))
    left, top, width, height = _window_geometry(window)
    area = max(width, 0) * max(height, 0)

    if area <= 0:
        return -1

    score = area
    if any(keyword.lower() in title.lower() for keyword in DINGTALK_TITLE_KEYWORDS):
        score += 10_000_000
    if visible:
        score += 1_000_000
    if active:
        score += 2_000_000
    if area < MIN_MAIN_WINDOW_AREA:
        score -= 5_000_000
    if left < -10_000 or top < -10_000:
        score -= 1_000_000
    return score


def _select_best_window(windows):
    candidates = [(window, _window_score(window)) for window in windows]
    candidates = [(window, score) for window, score in candidates if score >= 0]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def _get_dingtalk_process_ids() -> set[int]:
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        logger.debug(f"读取进程列表失败: {e}")
        return set()

    pids: set[int] = set()
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 2:
            continue
        image_name = row[0].strip().lower()
        if image_name not in DINGTALK_PROCESS_NAMES:
            continue
        try:
            pids.add(int(row[1]))
        except ValueError:
            continue
    return pids


def _find_windows_by_title():
    windows = []
    try:
        import pywinctl

        for title in DINGTALK_TITLE_KEYWORDS:
            windows.extend(pywinctl.getWindowsWithTitle(title))
    except Exception as e:
        logger.debug(f"pywinctl按标题查找失败: {e}")
    return windows


def _find_windows_by_process_ids(process_ids: set[int]):
    if user32 is None or not process_ids:
        return []

    windows = []
    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_windows_proc
    def callback(hwnd, lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in process_ids:
            return True

        window = Win32Window(hwnd)
        title = window.title
        left, top, width, height = _window_geometry(window)
        area = width * height
        if area <= 0:
            return True

        if any(keyword.lower() in title.lower() for keyword in DINGTALK_TITLE_KEYWORDS):
            windows.append(window)
        elif area >= MIN_MAIN_WINDOW_AREA and window.visible:
            windows.append(window)
        return True

    user32.EnumWindows(callback, 0)
    return windows


def find_dingtalk_window():
    """查找钉钉窗口句柄。返回窗口对象或None。"""
    process_ids = _get_dingtalk_process_ids()
    windows = _find_windows_by_title()
    windows.extend(_find_windows_by_process_ids(process_ids))

    window = _select_best_window(windows)
    if window is not None:
        left, top, width, height = _window_geometry(window)
        logger.debug(
            f"找到钉钉窗口: title={window.title!r}, rect=({left}, {top}, {width}, {height}), "
            f"visible={_read_attr(window, 'visible', None)}, active={_read_attr(window, 'isActive', None)}"
        )
    return window


def is_dingtalk_running() -> bool:
    """检查钉钉进程是否在运行。"""
    return bool(_get_dingtalk_process_ids())


def _get_running_dingtalk_path() -> str | None:
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process -Name DingTalk -ErrorAction SilentlyContinue | "
                "Where-Object { $_.Path } | Select-Object -First 1 -ExpandProperty Path",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as e:
        logger.debug(f"读取钉钉进程路径失败: {e}")
        return None

    path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return path if path and Path(path).exists() else None


def _resolve_dingtalk_executable(exe_path: str) -> str | None:
    if exe_path and Path(exe_path).exists():
        return exe_path

    running_path = _get_running_dingtalk_path()
    if running_path:
        return running_path

    common_paths = [
        Path("C:/Program Files/DingTalk/DingTalk.exe"),
        Path("C:/Program Files (x86)/DingDing/main/current/DingTalk.exe"),
        Path("D:/Program Files (x86)/DingDing/main/current/DingTalk.exe"),
    ]
    for path in common_paths:
        if path.exists():
            return str(path)
    return None


def launch_dingtalk(exe_path: str, wait_seconds: int = 10) -> bool:
    """启动钉钉客户端。"""
    resolved_path = _resolve_dingtalk_executable(exe_path)
    if resolved_path is None:
        logger.error(f"钉钉路径不存在: {exe_path}")
        return False
    try:
        subprocess.Popen([resolved_path])
        logger.info(f"正在启动钉钉，等待 {wait_seconds} 秒...")
        time.sleep(wait_seconds)
        return True
    except Exception as e:
        logger.error(f"启动钉钉失败: {e}")
        return False


def activate_dingtalk(exe_path: str, launch_wait: int = 10) -> object:
    """确保钉钉运行并激活窗口，返回窗口对象。"""
    window = find_dingtalk_window()
    if window is None:
        if not launch_dingtalk(exe_path, launch_wait if not is_dingtalk_running() else 2):
            return None
        window = find_dingtalk_window()

    if window is None:
        logger.error("无法找到钉钉窗口")
        return None

    try:
        if _read_attr(window, "isMinimized", False):
            _call_method(window, "restore", wait=True)

        if _read_attr(window, "visible", True) is False:
            _call_method(window, "show")

        _call_method(window, "raiseWindow")
        activated = _call_method(window, "activate", wait=True)
        time.sleep(0.5)

        if activated is False or _read_attr(window, "isActive", True) is False:
            logger.warning(f"已尝试置前钉钉窗口，但系统未报告为前台: {window.title}")
        else:
            logger.info(f"钉钉窗口已激活: {window.title}")
        return window
    except Exception as e:
        logger.error(f"激活窗口失败: {e}")
        return None
