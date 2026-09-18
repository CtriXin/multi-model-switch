"""Windows encoding contract: system tools decode by system codepage, workers speak UTF-8.

Regression source: on a GBK (cp936) Windows host, ``text=True`` decodes
subprocess output with the locale codepage. netstat / powershell CIM output
crashed ``mms web start/status/stop``; the UTF-8-writing catalog and
model-settings workers crashed the send/configure conversation path.
"""
import base64
import io
import json
import locale
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_windows_command_output_decodes_gbk_without_crashing(monkeypatch):
    from mms_web import service

    text = "活动 TCP 连接 中文目录\\pi.CMD"
    gbk_bytes = text.encode("gbk")
    monkeypatch.setattr(service, "_windows_console_codepages", lambda: ["cp936"])
    assert service._decode_windows_command_output(gbk_bytes) == text
    # UTF-8 output (pwsh 7 / UTF-8 systems) is preferred when it decodes cleanly.
    assert service._decode_windows_command_output(text.encode("utf-8")) == text
    # Undecodable junk must never raise — the lifecycle path depends on it.
    assert service._decode_windows_command_output(b"\xff\xfe garbage \x80")


def test_windows_decoder_ignores_locale_under_pythonutf8(monkeypatch):
    """PYTHONUTF8=1 makes getpreferredencoding answer utf-8 while console tools
    still write cp936; the decoder must follow the Win32 codepage, not locale."""
    from mms_web import service

    text = "中文进程命令行"
    gbk_bytes = text.encode("gbk")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "utf-8")
    monkeypatch.setattr(service, "_windows_console_codepages", lambda: ["cp936"])
    assert service._decode_windows_command_output(gbk_bytes) == text
    # No codepage answer at all (off-Windows or API failure) still never raises.
    monkeypatch.setattr(service, "_windows_console_codepages", lambda: [])
    decoded = service._decode_windows_command_output(gbk_bytes)
    assert isinstance(decoded, str) and decoded


def test_windows_netstat_bytes_are_parsed_after_safe_decode(monkeypatch):
    from mms_web import service

    netstat = "  TCP    127.0.0.1:8765     0.0.0.0:0    监听  中文 4321\r\n" \
              "  TCP    0.0.0.0:8765       0.0.0.0:0    LISTENING         9876\r\n"
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service, "_windows_console_codepages", lambda: ["cp936"])
    monkeypatch.setattr(service.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=netstat.encode("gbk"), returncode=0))
    # The non-ASCII state text must not break PID extraction.
    assert service._listening_pids(8765) == [9876]


def test_windows_cim_command_line_with_chinese_path_decodes(monkeypatch):
    from mms_web import service

    command_line = '"C:\\用户\\中文目录\\python.exe" -m mms_web --state-root "D:\\状态 目录"'
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service, "_windows_console_codepages", lambda: ["cp936"])
    monkeypatch.setattr(service.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=base64.b64encode(command_line.encode("utf-8")), returncode=0))
    argv = service._command_line(1234)
    assert argv == ["C:\\用户\\中文目录\\python.exe", "-m", "mms_web", "--state-root", "D:\\状态 目录"]


def test_windows_cim_preserves_paths_whose_gbk_bytes_also_decode_as_utf8(monkeypatch):
    """GBK output can be valid UTF-8 bytes and must not become mojibake."""
    from mms_web import service

    command_line = r'"C:\Users\Admin\mms.exe" --state-root "D:\状态 目录"'
    assert command_line.encode("gbk").decode("utf-8") != command_line
    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=base64.b64encode(command_line.encode("utf-8")), returncode=0))
    assert service._command_line(1234) == [
        r"C:\Users\Admin\mms.exe", "--state-root", r"D:\状态 目录"
    ]


@pytest.mark.parametrize("output", [b"not base64!", base64.b64encode(b"\xff")])
def test_windows_cim_invalid_output_does_not_create_a_corrupt_path(monkeypatch, output):
    from mms_web import service

    monkeypatch.setattr(service, "_is_windows", lambda: True)
    monkeypatch.setattr(service.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=output, returncode=0))
    assert service._command_line(1234) == []


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows CIM")
def test_native_windows_cim_roundtrips_unicode_state_root(tmp_path):
    from mms_web import service

    state_root = str(tmp_path / "状态 目录 📁")
    # Read the actual Windows process command line through PowerShell 5.1.
    # Neither this test nor the child creates a service or touches real config.
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                           "--state-root", state_root]) as child:
        try:
            argv = service._command_line(child.pid)
            assert service._option(argv, "--state-root") == state_root
        finally:
            child.terminate()
            child.wait(timeout=10)


class _EncodingPipes:
    """sys.stdin stand-in whose text layer uses a non-UTF-8 locale."""

    def __init__(self, data: bytes, encoding: str):
        self.buffer = io.BytesIO(data)
        self._text = io.TextIOWrapper(io.BytesIO(data), encoding=encoding)

    def read(self):
        return self._text.read()


def _run_worker_main(monkeypatch, module, payload: dict, locale_encoding: str):
    """Drive a worker's main() with a non-UTF-8 locale stdin and capture stdout JSON."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", _EncodingPipes(raw, locale_encoding))
    captured = {}

    class FakeStream:
        def write(self, text):
            captured["text"] = text

        def flush(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(module, "_result_stream", lambda: FakeStream())
    monkeypatch.setattr(module, "_cmd_resolve_launch", lambda stream, payload: module._emit(stream, {"ok": True, "echo": payload}))
    code = module.main()
    assert code == 0
    return json.loads(captured["text"])


def test_catalog_worker_reads_stdin_as_utf8_under_gbk_locale(monkeypatch):
    from mms_web import catalog_worker

    payload = {"command": "resolve-launch", "path": "C:\\工作 目录\\项目"}
    result = _run_worker_main(monkeypatch, catalog_worker, payload, "gbk")
    assert result["ok"] is True
    assert result["echo"]["path"] == "C:\\工作 目录\\项目"


def test_model_settings_worker_reads_stdin_as_utf8_under_gbk_locale(tmp_path, monkeypatch):
    worker = ROOT / "mms_web" / "model_settings_worker.py"
    # The settings worker's main is a module-level __main__ guard; exercise the
    # same stdin contract through a real subprocess with a GBK text locale.
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": os.pathsep.join([str(ROOT / "lib"), str(ROOT)]),
        "PYTHONIOENCODING": "gbk",  # stdin text layer decodes GBK like a CN Windows host
        "MMS_WEB_WORKER": "1",
    }
    payload = json.dumps({"root": str(tmp_path / "不存在的中文目录"), "standalone": "1"}, ensure_ascii=False).encode("utf-8")
    proc = subprocess.run([sys.executable, str(worker)], input=payload, capture_output=True,
                          env=env, timeout=60)
    # The worker must read UTF-8 bytes regardless of the locale: it reports a
    # structured result (likely a handled error for the missing root), never a
    # UnicodeDecodeError traceback from stdin decoding.
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")[-1000:]
    last = [line for line in proc.stdout.decode("utf-8", errors="replace").splitlines() if line.strip()][-1]
    parsed = json.loads(last)
    assert "ok" in parsed  # structured contract reached; stdin decoded as UTF-8


def test_run_worker_decodes_utf8_json_under_gbk_locale(tmp_path, monkeypatch):
    """catalog._run_worker must not locale-decode the worker's UTF-8 stdout."""
    from mms_web import catalog

    cat = catalog.CatalogService(config_root=tmp_path, state_root=tmp_path / "state")

    def fake_run(cmd, **kwargs):
        assert kwargs.get("text") is not True  # bytes contract
        assert isinstance(kwargs["input"], bytes)
        return SimpleNamespace(returncode=0,
                               stdout=json.dumps({"ok": True, "路径": "中文值"}, ensure_ascii=False).encode("utf-8"),
                               stderr=b"")

    monkeypatch.setattr(catalog.subprocess, "run", fake_run)
    # Simulate the GBK host locale; the UTF-8 bytes contract must be immune to it.
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "gbk")
    result = cat._run_worker({"command": "ping"})
    assert result == {"ok": True, "路径": "中文值"}
