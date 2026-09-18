"""Windows-style os.replace failures in private_json, and silent update-check paths."""
from __future__ import annotations

import errno
import inspect
import json
import logging
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mms_web.runtime import private_json
from mms_web.sessions import _LiveSession
from mms_web.updates import UpdateService


def _winerror_5():
    err = PermissionError(13, "拒绝访问。")
    err.winerror = 5
    return err


def _updates(tmp_path, fetcher=None):
    return UpdateService(
        SimpleNamespace(state_root=tmp_path),
        fetcher=fetcher or Mock(return_value={"tag": "v99.0.0", "notes": "new"}),
        clock=lambda: 100000,
    )


def test_private_json_retries_transient_replace_then_succeeds(tmp_path, monkeypatch):
    target = tmp_path / "session.json"
    calls = {"n": 0}
    real_replace = os.replace

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _winerror_5()
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    private_json(target, {"ok": True, "n": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True, "n": 1}
    assert calls["n"] == 3
    assert list(tmp_path.glob(".web-*.tmp")) == []


def test_private_json_exhausted_retries_leave_the_target_untouched(tmp_path, monkeypatch):
    target = tmp_path / "session.json"
    target.write_text('{"keep": true}', encoding="utf-8")
    seen_temp = []

    def always_fail(src, dst):
        seen_temp.append(os.path.exists(src))
        raise _winerror_5()

    monkeypatch.setattr(os, "replace", always_fail)
    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    with pytest.raises(PermissionError):
        private_json(target, {"keep": False, "new": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}
    assert seen_temp and all(seen_temp)
    assert len(seen_temp) >= 2
    assert list(tmp_path.glob(".web-*.tmp")) == []


def test_private_json_never_opens_the_destination_for_write():
    import mms_web.runtime as runtime

    source = inspect.getsource(runtime.private_json)
    assert "os.replace(temporary, path)" in source
    assert "os.open(path" not in source
    assert 'open(path' not in source
    assert "open(str(path)" not in source
    assert "path.open(" not in source
    assert "Path(path).write" not in source
    assert "path.write_text" not in source
    assert "path.write_bytes" not in source


def test_update_check_records_an_error_when_private_json_fails(tmp_path, monkeypatch, caplog):
    service = _updates(tmp_path)
    monkeypatch.setattr(
        "mms_web.updates.private_json",
        Mock(side_effect=_winerror_5()),
    )
    with caplog.at_level(logging.ERROR, logger="mms_web.updates"):
        result = service.check(manual=True)
    assert result["error"]
    assert result["checking"] is False
    assert "update check failed" in caplog.text


def test_request_check_logs_exceptions_from_the_background_thread(tmp_path, monkeypatch, caplog):
    service = _updates(tmp_path)
    monkeypatch.setattr(service, "check", Mock(side_effect=RuntimeError("background-boom")))

    def immediate_thread(*args, **kwargs):
        target = kwargs.get("target") or args[0]
        thread_args = kwargs.get("args") or ()
        thread_kwargs = kwargs.get("kwargs") or {}

        class Immediate:
            def start(self):
                target(*thread_args, **thread_kwargs)

        return Immediate()

    monkeypatch.setattr(threading, "Thread", immediate_thread)
    with caplog.at_level(logging.ERROR, logger="mms_web.updates"):
        service.request_check()
    assert "background-boom" in caplog.text


def test_session_persist_logs_then_reraises(tmp_path, monkeypatch, caplog):
    session = _LiveSession({"id": "s-lost"})
    monkeypatch.setattr(
        "mms_web.runtime.private_json",
        Mock(side_effect=_winerror_5()),
    )
    with caplog.at_level(logging.ERROR, logger="mms_web.sessions"):
        with pytest.raises(PermissionError):
            session.persist(tmp_path)
    assert "session persist failed" in caplog.text
    assert "s-lost" in caplog.text
    assert not (tmp_path / "s-lost.json").exists()


def test_sync_update_check_returns_settled_status(tmp_path):
    service = _updates(tmp_path)
    result = service.check(manual=True)
    assert result["checking"] is False
    assert result == service.status()
    assert service._check_lock.acquire(blocking=False)
    service._check_lock.release()


def test_private_json_does_not_retry_a_fatal_replace_error(tmp_path, monkeypatch):
    """A full disk is not a scanner holding the handle; retrying it just wastes
    time and hides the real cause. Only the Windows transient winerrors and
    PermissionError are worth a second attempt."""
    target = tmp_path / "session.json"
    target.write_text('{"keep": true}', encoding="utf-8")
    attempts = []

    def out_of_space(src, dst):
        attempts.append(src)
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", out_of_space)
    monkeypatch.setattr(time, "sleep", lambda _delay: pytest.fail("a fatal error must not back off"))
    with pytest.raises(OSError) as raised:
        private_json(target, {"keep": False})
    assert raised.value.errno == errno.ENOSPC
    assert len(attempts) == 1, "ENOSPC was retried; the transient allowlist is too wide"
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}
    assert list(tmp_path.glob(".web-*.tmp")) == []
