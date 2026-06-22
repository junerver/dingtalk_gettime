# tests/test_window.py
from types import SimpleNamespace

from automation import window as window_module


class FakeWindow:
    def __init__(
        self,
        title="钉钉",
        width=900,
        height=700,
        visible=False,
        active=False,
        minimized=False,
    ):
        self.title = title
        self.left = 0
        self.top = 0
        self.width = width
        self.height = height
        self.visible = visible
        self.isActive = active
        self.isMinimized = minimized
        self.calls = []

    def restore(self, wait=False):
        self.calls.append(("restore", wait))

    def show(self):
        self.calls.append(("show",))

    def raiseWindow(self):
        self.calls.append(("raiseWindow",))

    def activate(self, wait=False):
        self.calls.append(("activate", wait))
        self.isActive = True
        return True


def test_select_best_window_prefers_large_dingtalk_main_window():
    small_helper = FakeWindow(title="钉钉", width=136, height=100, visible=True)
    large_hidden_main = FakeWindow(title="钉钉", width=975, height=794, visible=False)
    unrelated = FakeWindow(title="Visual Studio Code", width=1936, height=1048, visible=True)

    selected = window_module._select_best_window(
        [small_helper, large_hidden_main, unrelated]
    )

    assert selected is large_hidden_main


def test_is_dingtalk_running_reads_tasklist_csv(monkeypatch):
    result = SimpleNamespace(
        stdout='"Code.exe","30116","Console","1","141,944 K"\n'
        '"DingTalk.exe","19788","Console","1","314,112 K"\n'
    )
    monkeypatch.setattr(window_module.subprocess, "run", lambda *args, **kwargs: result)

    assert window_module.is_dingtalk_running() is True


def test_launch_dingtalk_uses_running_process_path_when_config_path_invalid(
    monkeypatch, tmp_path
):
    exe_path = tmp_path / "DingTalk.exe"
    exe_path.write_text("", encoding="utf-8")
    popen_calls = []

    monkeypatch.setattr(
        window_module,
        "_get_running_dingtalk_path",
        lambda: str(exe_path),
    )
    monkeypatch.setattr(
        window_module.subprocess,
        "Popen",
        lambda args: popen_calls.append(args),
    )

    assert window_module.launch_dingtalk("C:\\missing\\DingTalk.exe", 0) is True
    assert popen_calls == [[str(exe_path)]]


def test_activate_dingtalk_reopens_running_app_when_window_missing(monkeypatch):
    target_window = FakeWindow(visible=False, minimized=True)
    find_results = iter([None, target_window])
    launch_calls = []

    monkeypatch.setattr(
        window_module,
        "find_dingtalk_window",
        lambda: next(find_results),
    )
    monkeypatch.setattr(window_module, "is_dingtalk_running", lambda: True)
    monkeypatch.setattr(
        window_module,
        "launch_dingtalk",
        lambda exe_path, wait_seconds: launch_calls.append((exe_path, wait_seconds))
        or True,
    )

    result = window_module.activate_dingtalk("C:\\missing\\DingTalk.exe", 10)

    assert result is target_window
    assert launch_calls == [("C:\\missing\\DingTalk.exe", 2)]
    assert target_window.calls == [
        ("restore", True),
        ("show",),
        ("raiseWindow",),
        ("activate", True),
    ]
