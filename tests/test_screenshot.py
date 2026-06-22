# tests/test_screenshot.py
import os
import tempfile
from pathlib import Path
from capture.screenshot import ScreenshotManager


def test_save_screenshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ScreenshotManager(save_dir=tmpdir)
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="red")
        path = mgr.save(img, prefix="test")
        assert os.path.exists(path)
        assert "test_" in Path(path).name


def test_image_to_base64():
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="blue")
    mgr = ScreenshotManager(save_dir=".")
    b64 = mgr.to_base64(img)
    assert isinstance(b64, str)
    assert len(b64) > 0
