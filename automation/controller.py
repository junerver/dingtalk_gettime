# automation/controller.py
import ctypes
import time
import logging
import pyautogui

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.03
pyautogui.FAILSAFE = True

WM_MOUSEWHEEL = 0x020A
WHEEL_DELTA = 120
DEFAULT_SCROLL_FOCUS_X_RATIO = 0.94
DEFAULT_SCROLL_FOCUS_Y_RATIO = 0.55
DEFAULT_CONVERSATION_LIST_X_RATIO = 0.27
DEFAULT_CONVERSATION_LIST_Y_RATIO = 0.55
DEFAULT_FIRST_CONVERSATION_X_RATIO = 0.27
DEFAULT_FIRST_CONVERSATION_Y_RATIO = 0.145
DEFAULT_SECOND_CONVERSATION_X_RATIO = 0.27
DEFAULT_SECOND_CONVERSATION_Y_RATIO = 0.22


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


def _read_int(obj, name: str):
    value = _read_attr(obj, name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rect_to_region(rect):
    if rect is None:
        return None

    left = _read_int(rect, "left")
    top = _read_int(rect, "top")
    width = _read_int(rect, "width")
    height = _read_int(rect, "height")

    if width is None:
        right = _read_int(rect, "right")
        if left is not None and right is not None:
            width = right - left

    if height is None:
        bottom = _read_int(rect, "bottom")
        if top is not None and bottom is not None:
            height = bottom - top

    if None in (left, top, width, height):
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height


def get_window_client_region(window) -> tuple[int, int, int, int]:
    """获取窗口客户端区域，返回屏幕坐标 x/y/width/height。"""
    try:
        region = _rect_to_region(_call_method(window, "getClientFrame"))
    except Exception as e:
        logger.debug(f"读取窗口客户端区域失败，使用窗口边界: {e}")
        region = None

    if region is not None:
        return region

    left = _read_int(window, "left")
    top = _read_int(window, "top")
    width = _read_int(window, "width")
    height = _read_int(window, "height")
    if None not in (left, top, width, height) and width > 0 and height > 0:
        return left, top, width, height

    region = _rect_to_region(_read_attr(window, "rect"))
    if region is not None:
        return region

    raise ValueError("无法计算窗口客户端区域")


def get_scroll_focus_point(
    window,
    x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
) -> tuple[int, int]:
    """获取消息内容区的滚动焦点坐标。"""
    x, y, width, height = get_window_client_region(window)
    x_ratio = min(max(x_ratio, 0.0), 1.0)
    y_ratio = min(max(y_ratio, 0.0), 1.0)
    return x + int(width * x_ratio), y + int(height * y_ratio)


def focus_window_for_scroll(
    window,
    x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
    click: bool = True,
):
    """将鼠标移动到钉钉消息内容区，必要时点击聚焦。"""
    if _read_attr(window, "isMinimized", False):
        _call_method(window, "restore", wait=True)
    if _read_attr(window, "visible", True) is False:
        _call_method(window, "show")
    _call_method(window, "raiseWindow")
    _call_method(window, "activate", wait=True)

    x, y = get_scroll_focus_point(window, x_ratio=x_ratio, y_ratio=y_ratio)
    logger.debug(f"滚动焦点坐标: ({x}, {y})")
    pyautogui.moveTo(x, y)
    if click:
        pyautogui.click(x, y)
    return x, y


def click_window_ratio(
    window,
    x_ratio: float,
    y_ratio: float,
    delay: float = 1.0,
) -> tuple[int, int]:
    """按窗口客户端区域比例点击。"""
    if _read_attr(window, "isMinimized", False):
        _call_method(window, "restore", wait=True)
    if _read_attr(window, "visible", True) is False:
        _call_method(window, "show")
    _call_method(window, "raiseWindow")
    _call_method(window, "activate", wait=True)

    x, y = get_scroll_focus_point(window, x_ratio=x_ratio, y_ratio=y_ratio)
    logger.debug(f"按窗口比例点击: ratio=({x_ratio:.3f}, {y_ratio:.3f}), point=({x}, {y})")
    pyautogui.moveTo(x, y)
    pyautogui.click(x, y)
    time.sleep(delay)
    return x, y


def _get_window_handle(window):
    hwnd = _read_attr(window, "hwnd")
    if hwnd:
        return int(hwnd)
    hwnd = _call_method(window, "getHandle")
    return int(hwnd) if hwnd else None


def _pack_signed_word(value: int) -> int:
    return value & 0xFFFF


def _pack_lparam(x: int, y: int) -> int:
    return _pack_signed_word(x) | (_pack_signed_word(y) << 16)


def _pack_wparam(delta: int) -> int:
    return (delta & 0xFFFF) << 16


def scroll_window_wheel_message(
    window,
    amount: int = 5,
    delay: float = 2.0,
    x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
):
    """直接向钉钉窗口发送鼠标滚轮消息。"""
    hwnd = _get_window_handle(window)
    if not hwnd:
        raise ValueError("窗口没有可用句柄，无法发送滚轮消息")

    x, y = get_scroll_focus_point(window, x_ratio=x_ratio, y_ratio=y_ratio)
    wparam = _pack_wparam(amount * WHEEL_DELTA)
    lparam = _pack_lparam(x, y)
    logger.debug(f"发送窗口滚轮消息: hwnd={hwnd}, amount={amount}, point=({x}, {y})")

    sent = ctypes.windll.user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
    if not sent:
        raise RuntimeError("发送窗口滚轮消息失败")
    time.sleep(delay)


def click_at(x: int, y: int, delay: float = 1.0):
    """在指定坐标点击。"""
    logger.debug(f"点击坐标: ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(delay)


def scroll_up(
    amount: int = 5,
    delay: float = 2.0,
    window=None,
    x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
    click: bool = True,
):
    """向上滚动（查看更早的消息）。正值=向上。"""
    logger.debug(f"向上滚动 {amount} 格")
    if window is not None:
        focus_window_for_scroll(window, x_ratio=x_ratio, y_ratio=y_ratio, click=click)
    pyautogui.scroll(amount * WHEEL_DELTA)
    time.sleep(delay)


def scroll_down(
    amount: int = 5,
    delay: float = 2.0,
    window=None,
    x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
    click: bool = True,
):
    """向下滚动。"""
    logger.debug(f"向下滚动 {amount} 格")
    if window is not None:
        focus_window_for_scroll(window, x_ratio=x_ratio, y_ratio=y_ratio, click=click)
    pyautogui.scroll(-amount * WHEEL_DELTA)
    time.sleep(delay)


def prepare_work_notification_view(
    window,
    conversation_list_scrolls: int = 8,
    conversation_list_scroll_amount: int = 1,
    conversation_list_x_ratio: float = DEFAULT_CONVERSATION_LIST_X_RATIO,
    conversation_list_y_ratio: float = DEFAULT_CONVERSATION_LIST_Y_RATIO,
    first_conversation_x_ratio: float = DEFAULT_FIRST_CONVERSATION_X_RATIO,
    first_conversation_y_ratio: float = DEFAULT_FIRST_CONVERSATION_Y_RATIO,
    second_conversation_x_ratio: float = DEFAULT_SECOND_CONVERSATION_X_RATIO,
    second_conversation_y_ratio: float = DEFAULT_SECOND_CONVERSATION_Y_RATIO,
    bottom_reset_scrolls: int = 12,
    bottom_reset_scroll_amount: int = 3,
    content_x_ratio: float = DEFAULT_SCROLL_FOCUS_X_RATIO,
    content_y_ratio: float = DEFAULT_SCROLL_FOCUS_Y_RATIO,
    delay: float = 0.2,
):
    """进入置顶的工作通知会话，并将消息定位到底部。"""
    logger.info("准备工作通知会话：定位置顶会话，切换会话后回到底部")

    # 点击会话列表中的一条消息，使其获得焦点
    click_window_ratio(
        window,
        x_ratio=conversation_list_x_ratio,
        y_ratio=conversation_list_y_ratio,
        delay=delay,
    )

    scroll_step_delay = 0.15
    for _ in range(max(conversation_list_scrolls, 0)):
        pyautogui.scroll(conversation_list_scroll_amount * WHEEL_DELTA)
        time.sleep(scroll_step_delay)

    # 直接点击第一个会话（工作通知），省略点击第二个会话
    click_window_ratio(
        window,
        x_ratio=first_conversation_x_ratio,
        y_ratio=first_conversation_y_ratio,
        delay=delay,
    )

    # 等待会话内容加载
    time.sleep(1.0)

    # 聚焦内容区域一次，后续滚动不再重复聚焦
    focus_window_for_scroll(
        window,
        x_ratio=content_x_ratio,
        y_ratio=content_y_ratio,
        click=False,
    )

    for _ in range(max(bottom_reset_scrolls, 0)):
        pyautogui.scroll(-bottom_reset_scroll_amount * WHEEL_DELTA)
        time.sleep(scroll_step_delay)


def press_key(key: str, delay: float = 0.5):
    """按下指定键。"""
    logger.debug(f"按键: {key}")
    pyautogui.press(key)
    time.sleep(delay)


def hotkey(*keys: str, delay: float = 0.5):
    """组合键。"""
    logger.debug(f"组合键: {'+'.join(keys)}")
    pyautogui.hotkey(*keys)
    time.sleep(delay)


def get_mouse_position() -> tuple[int, int]:
    """获取当前鼠标位置。"""
    return pyautogui.position()


def wait(seconds: float):
    """等待指定秒数。"""
    time.sleep(seconds)
