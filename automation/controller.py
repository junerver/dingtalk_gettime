# automation/controller.py
import time
import logging
import pyautogui

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.1
pyautogui.FAILSAFE = True


def click_at(x: int, y: int, delay: float = 1.0):
    """在指定坐标点击。"""
    logger.debug(f"点击坐标: ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(delay)


def scroll_up(amount: int = 5, delay: float = 2.0):
    """向上滚动（查看更早的消息）。正值=向上。"""
    logger.debug(f"向上滚动 {amount} 格")
    pyautogui.scroll(amount)
    time.sleep(delay)


def scroll_down(amount: int = 5, delay: float = 2.0):
    """向下滚动。"""
    logger.debug(f"向下滚动 {amount} 格")
    pyautogui.scroll(-amount)
    time.sleep(delay)


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
