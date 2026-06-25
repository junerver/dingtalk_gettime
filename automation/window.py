import logging
import csv
import ctypes
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000
DINGTALK_PROCESS_NAMES = {"dingtalk.exe"}
DINGTALK_TITLE_KEYWORDS = ("钉钉", "DingTalk")
MIN_MAIN_WINDOW_AREA = 600 * 400
# DingTalk Electron 内容窗体的类名，不是主窗口
EXCLUDED_CLASS_NAMES = {"Chrome_WidgetWin_0"}

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9
SW_MINIMIZE = 6
GWL_EXSTYLE = -20
GW_OWNER = 4
WS_EX_TOOLWINDOW = 0x00000080
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


def _get_hwnd_title(hwnd: int) -> str:
    if user32 is None:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_class_name(hwnd: int) -> str:
    if user32 is None:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _is_top_level_main_window(hwnd: int) -> bool:
    """检查窗口是否为真正的顶层主窗口（排除有 Owner 的子窗口和工具窗口）。"""
    if user32 is None:
        return True
    # 有 Owner 的窗口是弹出窗口 / 子窗口，不是主窗口
    if user32.GetWindow(hwnd, GW_OWNER):
        return False
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    cls = _get_class_name(hwnd)
    if cls in EXCLUDED_CLASS_NAMES:
        return False
    return True


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
        return -1
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
            creationflags=CREATE_NO_WINDOW,
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

        if not _is_top_level_main_window(hwnd):
            return True

        window = Win32Window(hwnd)
        title = window.title
        left, top, width, height = _window_geometry(window)
        area = width * height
        if area < MIN_MAIN_WINDOW_AREA:
            return True

        if any(keyword.lower() in title.lower() for keyword in DINGTALK_TITLE_KEYWORDS):
            windows.append(window)
        elif window.visible:
            windows.append(window)
        return True

    user32.EnumWindows(callback, 0)
    return windows


def _get_hwnd(window) -> int | None:
    """从窗口对象中获取原生句柄（兼容 pywinctl 和 Win32Window）。"""
    hwnd = _read_attr(window, "hwnd")
    if hwnd:
        return hwnd
    return _call_method(window, "getHandle")


def _restore_any_dingtalk_window(process_ids: set[int]) -> bool:
    """找到任意一个钉钉主窗口并恢复其可见状态，返回是否执行了恢复。"""
    if user32 is None:
        return False

    # 用 pywinctl 搜索（无面积过滤），找到标题匹配的主窗口
    for title in DINGTALK_TITLE_KEYWORDS:
        try:
            import pywinctl
            for w in pywinctl.getWindowsWithTitle(title):
                hwnd = _get_hwnd(w)
                if not hwnd or not _is_top_level_main_window(hwnd):
                    continue
                cls = _get_class_name(hwnd)
                if cls in EXCLUDED_CLASS_NAMES:
                    continue
                # 找到了，恢复它
                if user32.IsIconic(hwnd):
                    logger.info(f"恢复最小化窗口 hwnd={hwnd:#x} title={w.title!r}")
                    user32.ShowWindow(hwnd, SW_RESTORE)
                elif not user32.IsWindowVisible(hwnd):
                    logger.info(f"显示隐藏窗口 hwnd={hwnd:#x} title={w.title!r}")
                    user32.ShowWindow(hwnd, SW_SHOW)
                else:
                    continue
                return True
        except Exception as e:
            logger.debug(f"pywinctl 搜索失败: {e}")
    return False


def find_dingtalk_window(process_ids: set[int] | None = None):
    """查找钉钉窗口句柄。返回窗口对象或None。"""
    if process_ids is None:
        process_ids = _get_dingtalk_process_ids()
    windows = _find_windows_by_title()
    # 过滤 pywinctl 返回的非主窗口（有 Owner 或工具窗口样式）
    if user32 is not None:
        windows = [
            w for w in windows
            if not (hwnd := _get_hwnd(w)) or _is_top_level_main_window(hwnd)
        ]
    windows.extend(_find_windows_by_process_ids(process_ids))

    window = _select_best_window(windows)
    if window is not None:
        left, top, width, height = _window_geometry(window)
        logger.info(
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
            creationflags=CREATE_NO_WINDOW,
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



def minimize_window(window) -> bool:
    """最小化窗口。"""
    hwnd = _read_attr(window, 'hwnd')
    if not hwnd:
        hwnd = _call_method(window, 'getHandle')
    if not hwnd:
        return False
    if user32 is None:
        return False
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    time.sleep(0.2)
    return True


def close_window(window) -> bool:
    """关闭窗口（钉钉会退到系统托盘，不退出进程）。"""
    hwnd = _read_attr(window, 'hwnd')
    if not hwnd:
        hwnd = _call_method(window, 'getHandle')
    if not hwnd:
        return False
    if user32 is None:
        return False
    WM_CLOSE = 0x0010
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.5)
    return True


def launch_dingtalk(exe_path: str, wait_seconds: int = 10) -> bool:
    """启动钉钉客户端。"""
    if not exe_path or not Path(exe_path).exists():
        logger.error(f"钉钉路径不存在: {exe_path}")
        return False
    try:
        subprocess.Popen(
            [exe_path],
            creationflags=CREATE_NO_WINDOW,
        )
        logger.info(f"正在启动钉钉，等待 {wait_seconds} 秒...")
        time.sleep(wait_seconds)
        return True
    except Exception as e:
        logger.error(f"启动钉钉失败: {e}")
        return False


def _shell_activate_dingtalk(exe_path: str) -> bool:
    """通过 ShellExecute 激活已有钉钉实例（和用户双击 exe 效果一致）。"""
    try:
        import win32api
        win32api.ShellExecute(0, "open", exe_path, None, "", 1)  # SW_SHOWNORMAL=1
        return True
    except Exception as e:
        logger.debug(f"ShellExecute 激活失败: {e}")
        return False


def _inject_input_for_foreground():
    """注入一次用户输入信号，使当前进程获得 SetForegroundWindow 权限。"""
    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", INPUT_UNION),
        ]

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MOVE, 0, None)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _force_foreground_window(hwnd: int) -> bool:
    """强制将窗口拉到前台（注入输入 + AttachThreadInput + SetForegroundWindow）。"""
    if user32 is None:
        return False

    _inject_input_for_foreground()

    user32.ShowWindow(hwnd, SW_SHOWNORMAL)
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.AllowSetForegroundWindow(-1)

    foreground_hwnd = user32.GetForegroundWindow()
    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    for thread_id in {foreground_thread, target_thread}:
        if thread_id and thread_id != current_thread:
            if user32.AttachThreadInput(current_thread, thread_id, True):
                attached.append(thread_id)

    try:
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        for thread_id in attached:
            user32.AttachThreadInput(current_thread, thread_id, False)

    return bool(user32.GetForegroundWindow() == hwnd)


def _log_foreground_window(label: str):
    """诊断：记录当前前台窗口信息。"""
    if user32 is None:
        return
    fg_hwnd = user32.GetForegroundWindow()
    if not fg_hwnd:
        logger.info(f"[{label}] 无前台窗口")
        return
    title = _get_hwnd_title(fg_hwnd)
    cls = _get_class_name(fg_hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(fg_hwnd, ctypes.byref(rect))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
    logger.info(
        f"[{label}] 前台: hwnd={fg_hwnd:#x} title={title!r} "
        f"class={cls} rect=({rect.left},{rect.top},{rect.right-rect.left},{rect.bottom-rect.top}) pid={pid.value}"
    )


def activate_dingtalk(exe_path: str, launch_wait: int = 10) -> object:
    """确保钉钉运行并激活窗口，返回窗口对象。"""
    # 先检查进程是否已运行
    process_ids = _get_dingtalk_process_ids()

    if not process_ids:
        # 未运行：启动并等待
        if not launch_dingtalk(exe_path, launch_wait):
            return None
        process_ids = _get_dingtalk_process_ids()

    # 直接查找窗口（不做 ShellExecute，避免激活错误的子窗口）
    window = find_dingtalk_window(process_ids)

    # 首次未找到：可能最小化/隐藏导致面积太小，恢复后重试
    if window is None:
        logger.info("首次搜索未找到钉钉窗口，尝试恢复...")
        if _restore_any_dingtalk_window(process_ids):
            time.sleep(0.5)
            window = find_dingtalk_window(process_ids)

    if window is None:
        logger.error("无法找到钉钉窗口")
        return None

    try:
        hwnd = _read_attr(window, "hwnd")
        if not hwnd:
            hwnd = _call_method(window, "getHandle")

        cls_name = _get_class_name(hwnd) if hwnd else "N/A"
        left, top, width, height = _window_geometry(window)
        visible = user32.IsWindowVisible(hwnd) if hwnd and user32 else None
        hwnd_str = f"{hwnd:#x}" if hwnd else "0"
        logger.info(
            f"选中窗口: hwnd={hwnd_str} title={window.title!r} "
            f"class={cls_name} rect=({left},{top},{width},{height}) visible={visible}"
        )

        # 强制拉到前台
        if hwnd and user32:
            fg = _force_foreground_window(hwnd)
            time.sleep(0.2)
            if fg:
                logger.info(f"钉钉窗口已激活到前台: {window.title}")
            else:
                # 激活失败时记录前台窗口，辅助诊断白色窗体问题
                _log_foreground_window("激活失败")
                logger.warning(f"钉钉窗口未能拉到前台: {window.title}")

        return window
    except Exception as e:
        logger.error(f"激活窗口失败: {e}")
        return None
