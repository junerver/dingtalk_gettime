# tests/test_controller.py
from types import SimpleNamespace

from automation import controller


class RectOnlyBounds:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeWindow:
    def __init__(self):
        self.rect = RectOnlyBounds(100, 200, 1100, 1000)
        self.visible = True
        self.isMinimized = False
        self.calls = []

    def getClientFrame(self):
        return RectOnlyBounds(120, 240, 1020, 940)

    def raiseWindow(self):
        self.calls.append(("raiseWindow",))

    def activate(self, wait=False):
        self.calls.append(("activate", wait))

    def getHandle(self):
        return 12345


def test_get_scroll_focus_point_uses_client_frame():
    window = FakeWindow()

    point = controller.get_scroll_focus_point(window, x_ratio=0.5, y_ratio=0.25)

    assert point == (570, 415)


def test_scroll_up_focuses_window_and_scrolls(monkeypatch):
    window = FakeWindow()
    calls = []

    monkeypatch.setattr(controller.pyautogui, "moveTo", lambda x, y: calls.append(("moveTo", x, y)))
    monkeypatch.setattr(controller.pyautogui, "click", lambda x, y: calls.append(("click", x, y)))
    monkeypatch.setattr(controller.pyautogui, "scroll", lambda amount: calls.append(("scroll", amount)))
    monkeypatch.setattr(controller.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))

    controller.scroll_up(amount=7, delay=0.1, window=window, x_ratio=0.5, y_ratio=0.25)

    assert window.calls == [("raiseWindow",), ("activate", True)]
    assert calls == [
        ("moveTo", 570, 415),
        ("click", 570, 415),
        ("scroll", 7 * controller.WHEEL_DELTA),
        ("sleep", 0.1),
    ]


def test_scroll_window_wheel_message_posts_to_window(monkeypatch):
    window = FakeWindow()
    posted = []

    class User32:
        def PostMessageW(self, hwnd, message, wparam, lparam):
            posted.append((hwnd, message, wparam, lparam))
            return 1

    monkeypatch.setattr(controller.ctypes, "windll", SimpleNamespace(user32=User32()))
    monkeypatch.setattr(controller.time, "sleep", lambda seconds: None)

    controller.scroll_window_wheel_message(
        window,
        amount=2,
        delay=0,
        x_ratio=0.5,
        y_ratio=0.25,
    )

    assert posted == [
        (
            12345,
            controller.WM_MOUSEWHEEL,
            controller._pack_wparam(2 * controller.WHEEL_DELTA),
            controller._pack_lparam(570, 415),
        )
    ]


def test_prepare_work_notification_view_switches_second_then_first(monkeypatch):
    window = FakeWindow()
    calls = []

    def fake_scroll_up(**kwargs):
        calls.append(("scroll_up", kwargs["x_ratio"], kwargs["y_ratio"], kwargs["amount"]))

    def fake_scroll_down(**kwargs):
        calls.append(("scroll_down", kwargs["x_ratio"], kwargs["y_ratio"], kwargs["amount"]))

    def fake_click_window_ratio(window_arg, x_ratio, y_ratio, delay=1.0):
        assert window_arg is window
        calls.append(("click", x_ratio, y_ratio))

    monkeypatch.setattr(controller, "scroll_up", fake_scroll_up)
    monkeypatch.setattr(controller, "scroll_down", fake_scroll_down)
    monkeypatch.setattr(controller, "click_window_ratio", fake_click_window_ratio)

    controller.prepare_work_notification_view(
        window,
        conversation_list_scrolls=2,
        conversation_list_scroll_amount=1,
        conversation_list_x_ratio=0.27,
        conversation_list_y_ratio=0.55,
        first_conversation_x_ratio=0.27,
        first_conversation_y_ratio=0.145,
        second_conversation_x_ratio=0.27,
        second_conversation_y_ratio=0.22,
        bottom_reset_scrolls=2,
        bottom_reset_scroll_amount=3,
        content_x_ratio=0.94,
        content_y_ratio=0.55,
    )

    assert calls == [
        ("scroll_up", 0.27, 0.55, 1),
        ("scroll_up", 0.27, 0.55, 1),
        ("click", 0.27, 0.22),
        ("click", 0.27, 0.145),
        ("scroll_down", 0.94, 0.55, 3),
        ("scroll_down", 0.94, 0.55, 3),
    ]
