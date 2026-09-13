"""Windows subprocess handoff for the Pi Web worker."""

import pytest


def test_windows_launcher_does_not_overlay_a_piped_worker(monkeypatch):
    import mms_launchers

    calls = []

    class Child:
        pid = 4242

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            return 17

    monkeypatch.setattr(mms_launchers.os, "name", "nt")
    monkeypatch.setattr(
        mms_launchers,
        "prepare_cli_command",
        lambda cmd, env: (list(cmd), dict(env), cmd[0]),
    )
    monkeypatch.setattr(
        mms_launchers.subprocess,
        "Popen",
        lambda cmd, env=None: calls.append(("popen", cmd, env)) or Child(),
    )

    with pytest.raises(SystemExit) as exc:
        mms_launchers._exec_or_run(["pi", "--mode", "rpc"], {"MMS_WEB_WORKER": "1"}, False)

    assert exc.value.code == 17
    assert calls[0][0] == "popen"
    assert calls[1] == ("wait", None)
