# tests/test_screenshot.py
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from capture.screenshot import ScreenshotManager


class RectOnlyBounds:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


def test_save_screenshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ScreenshotManager(save_dir=tmpdir)
        img = Image.new("RGB", (100, 100), color="red")
        path = mgr.save(img, prefix="test")
        assert os.path.exists(path)
        assert "test_" in Path(path).name


def test_image_to_base64():
    img = Image.new("RGB", (100, 100), color="blue")
    mgr = ScreenshotManager(save_dir=".")
    b64 = mgr.to_base64(img)
    assert isinstance(b64, str)
    assert len(b64) > 0


def test_stitch_vertical_uses_magick_append_in_given_order(monkeypatch, tmp_path):
    mgr = ScreenshotManager(save_dir=str(tmp_path))
    calls = []

    def fake_run(command, check, capture_output, text):
        calls.append({
            "command": command,
            "check": check,
            "capture_output": capture_output,
            "text": text,
        })
        Path(command[-1]).write_bytes(b"stitched")

    monkeypatch.setattr("capture.screenshot.subprocess.run", fake_run)

    output_path = mgr.stitch_vertical(["3.png", "2.png", "1.png"])

    assert Path(output_path).exists()
    assert calls == [
        {
            "command": [
                "magick",
                "convert",
                "-append",
                "3.png",
                "2.png",
                "1.png",
                output_path,
            ],
            "check": True,
            "capture_output": True,
            "text": True,
        }
    ]


def test_changed_pixel_ratio_detects_identical_and_changed_images():
    img1 = Image.new("RGB", (10, 10), color="black")
    img2 = Image.new("RGB", (10, 10), color="black")
    img3 = Image.new("RGB", (10, 10), color="white")

    assert ScreenshotManager.changed_pixel_ratio(img1, img2) == 0
    assert ScreenshotManager.changed_pixel_ratio(img1, img3) == 1
    assert ScreenshotManager.images_are_similar(img1, img2) is True
    assert ScreenshotManager.images_are_similar(img1, img3) is False


def test_crop_by_ratios_returns_expected_region():
    img = Image.new("RGB", (100, 80), color="black")

    cropped = ScreenshotManager.crop_by_ratios(
        img,
        left_ratio=0.25,
        top_ratio=0.125,
        right_ratio=0.75,
        bottom_ratio=0.875,
    )

    assert cropped.size == (50, 60)


def test_crop_by_ratios_rejects_invalid_region():
    img = Image.new("RGB", (100, 80), color="black")

    with pytest.raises(ValueError, match="截图裁剪区域无效"):
        ScreenshotManager.crop_by_ratios(
            img,
            left_ratio=0.8,
            top_ratio=0.1,
            right_ratio=0.2,
            bottom_ratio=0.9,
        )


def test_capture_window_prefers_client_frame(monkeypatch, tmp_path):
    class Window:
        rect = RectOnlyBounds(0, 0, 1000, 800)

        def getClientFrame(self):
            return RectOnlyBounds(120, 80, 920, 720)

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    expected = Image.new("RGB", (800, 640), color="green")
    calls = []

    def fake_capture_region(x, y, width, height):
        calls.append((x, y, width, height))
        return expected

    monkeypatch.setattr(mgr, "capture_region", fake_capture_region)

    image = mgr.capture_window(Window())

    assert image is expected
    assert calls == [(120, 80, 800, 640)]


def test_capture_window_supports_rect_without_width_height(monkeypatch, tmp_path):
    class Window:
        rect = RectOnlyBounds(10, 20, 310, 420)

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    expected = Image.new("RGB", (300, 370), color="yellow")
    calls = []

    def fake_capture_region(x, y, width, height):
        calls.append((x, y, width, height))
        return expected

    monkeypatch.setattr(mgr, "capture_region", fake_capture_region)

    image = mgr.capture_window(Window())

    assert image is expected
    assert calls == [(10, 50, 300, 370)]


def test_capture_window_falls_back_when_client_frame_fails(monkeypatch, tmp_path):
    class Window:
        rect = RectOnlyBounds(10, 20, 310, 420)

        def getClientFrame(self):
            raise RuntimeError("client frame unavailable")

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    expected = Image.new("RGB", (300, 370), color="orange")
    calls = []

    def fake_capture_region(x, y, width, height):
        calls.append((x, y, width, height))
        return expected

    monkeypatch.setattr(mgr, "capture_region", fake_capture_region)

    image = mgr.capture_window(Window())

    assert image is expected
    assert calls == [(10, 50, 300, 370)]


def test_capture_window_prepares_window_before_screenshot(monkeypatch, tmp_path):
    class Window:
        rect = RectOnlyBounds(10, 20, 310, 420)
        isMinimized = True
        visible = True
        isActive = True

        def __init__(self):
            self.calls = []

        def restore(self, wait=False):
            self.calls.append(("restore", wait))

        def raiseWindow(self):
            self.calls.append(("raiseWindow",))

        def activate(self, wait=False):
            self.calls.append(("activate", wait))
            return True

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    mgr.WINDOW_ACTIVATE_DELAY = 0
    monkeypatch.setattr(
        mgr,
        "capture_region",
        lambda *args: Image.new("RGB", (300, 370), color="purple"),
    )

    window = Window()
    mgr.capture_window(window)

    assert window.calls == [
        ("restore", True),
        ("raiseWindow",),
        ("activate", True),
    ]


def test_capture_window_uses_handle_capture_before_screen_region(monkeypatch, tmp_path):
    class Window:
        hwnd = 123
        rect = RectOnlyBounds(10, 20, 310, 420)
        isActive = False

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    expected = Image.new("RGB", (300, 370), color="cyan")
    screen_calls = []

    monkeypatch.setattr(mgr, "_capture_window_by_handle", lambda window: expected)
    monkeypatch.setattr(
        mgr,
        "capture_region",
        lambda *args: screen_calls.append(args),
    )

    image = mgr.capture_window(Window())

    assert image is expected
    assert screen_calls == []


def test_capture_window_refuses_screen_region_when_inactive_without_handle(
    monkeypatch, tmp_path
):
    class Window:
        rect = RectOnlyBounds(10, 20, 310, 420)
        isActive = False

    mgr = ScreenshotManager(save_dir=str(tmp_path))
    monkeypatch.setattr(mgr, "_capture_window_by_handle", lambda window: None)

    with pytest.raises(RuntimeError, match="窗口未处于前台"):
        mgr.capture_window(Window())


def test_capture_window_raises_instead_of_fullscreen_fallback(monkeypatch, tmp_path):
    class Window:
        rect = RectOnlyBounds(10, 20, 310, 420)

    mgr = ScreenshotManager(save_dir=str(tmp_path))

    def fail_capture_region(*args):
        raise RuntimeError("region capture failed")

    monkeypatch.setattr(mgr, "capture_region", fail_capture_region)

    with pytest.raises(RuntimeError, match="region capture failed"):
        mgr.capture_window(Window())
