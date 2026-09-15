def test_session_guard_uses_posix_kill_on_posix(monkeypatch):
    import mms_launchers

    called = []
    monkeypatch.setattr(mms_launchers, "_windows_session_guard_pid_alive", lambda _pid: None)
    monkeypatch.setattr(mms_launchers.os, "kill", lambda pid, signal: called.append((pid, signal)))

    assert mms_launchers._session_guard_pid_alive(1234) is True
    assert called == [(1234, 0)]


def test_session_guard_uses_win32_process_query_on_windows(monkeypatch):
    import ctypes
    import mms_launchers

    class FakeCall:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel32:
        def __init__(self):
            self.OpenProcess = FakeCall(lambda _access, _inherit, pid: 99 if pid == 1234 else 0)
            self.GetExitCodeProcess = FakeCall(self._get_exit_code)
            self.CloseHandle = FakeCall(lambda _handle: 1)

        @staticmethod
        def _get_exit_code(_handle, code):
            import ctypes

            ctypes.cast(code, ctypes.POINTER(ctypes.c_ulong)).contents.value = 259  # STILL_ACTIVE
            return 1

    kernel32 = FakeKernel32()
    monkeypatch.setattr(mms_launchers.os, "name", "nt", raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: kernel32, raising=False)
    monkeypatch.setattr(mms_launchers.os, "kill", lambda *_args: (_ for _ in ()).throw(AssertionError("os.kill called")))

    assert mms_launchers._windows_session_guard_pid_alive(1234) is True
    assert mms_launchers._session_guard_pid_alive(1234) is True


def test_windows_session_guard_reports_exited_process(monkeypatch):
    import ctypes
    import mms_launchers

    class FakeCall:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    class FakeKernel32:
        def __init__(self):
            self.OpenProcess = FakeCall(lambda _access, _inherit, _pid: 99)
            self.GetExitCodeProcess = FakeCall(self._get_exit_code)
            self.CloseHandle = FakeCall(lambda _handle: 1)

        @staticmethod
        def _get_exit_code(_handle, code):
            import ctypes

            ctypes.cast(code, ctypes.POINTER(ctypes.c_ulong)).contents.value = 0
            return 1

    monkeypatch.setattr(mms_launchers.os, "name", "nt", raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: FakeKernel32(), raising=False)

    assert mms_launchers._windows_session_guard_pid_alive(1234) is False
    assert mms_launchers._session_guard_pid_alive(1234) is False
