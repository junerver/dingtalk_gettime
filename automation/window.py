# automation/window.py
import subprocess
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_dingtalk_window():
    """查找钉钉窗口句柄。返回窗口对象或None。"""
    try:
        import pywinctl
        windows = pywinctl.getWindowsWithTitle("钉钉")
        if windows:
            return windows[0]
        windows = pywinctl.getWindowsWithTitle("DingTalk")
        if windows:
            return windows[0]
    except Exception as e:
        logger.warning(f"pywinctl查找失败: {e}")
    return None


def is_dingtalk_running() -> bool:
    """检查钉钉进程是否在运行。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq DingTalk.exe"],
            capture_output=True, text=True, timeout=5
        )
        return "DingTalk.exe" in result.stdout
    except Exception:
        return False


def launch_dingtalk(exe_path: str, wait_seconds: int = 10) -> bool:
    """启动钉钉客户端。"""
    if not Path(exe_path).exists():
        logger.error(f"钉钉路径不存在: {exe_path}")
        return False
    try:
        subprocess.Popen([exe_path])
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
        if not is_dingtalk_running():
            if not launch_dingtalk(exe_path, launch_wait):
                return None
            time.sleep(2)
        window = find_dingtalk_window()

    if window is None:
        logger.error("无法找到钉钉窗口")
        return None

    try:
        window.activate()
        time.sleep(0.5)
        logger.info(f"钉钉窗口已激活: {window.title}")
        return window
    except Exception as e:
        logger.error(f"激活窗口失败: {e}")
        return None
