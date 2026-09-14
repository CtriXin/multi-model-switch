from types import SimpleNamespace
import sys
import subprocess

from mms_web.server import WebApplication


def test_windows_workspace_picker_uses_powershell_and_utf8(monkeypatch, tmp_path):
    app = WebApplication(state_root=tmp_path / "state")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="C:\\Users\\Admin\\下载", stderr="")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "run", run)
    assert app.post(["workspaces", "choose"], {}) == {"path": "C:\\Users\\Admin\\下载"}
    assert calls[0][0][:6] == ["powershell.exe", "-NoProfile", "-STA", "-WindowStyle", "Normal", "-ExecutionPolicy"]
    assert calls[0][1]["encoding"] == "utf-8"
    app.close()
