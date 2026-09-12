from pathlib import Path

import mms_launchers


def test_real_user_home_unwinds_mms_next_gateway_home(monkeypatch, tmp_path: Path):
    real_home = tmp_path / "real-home"
    session_home = real_home / ".config" / "mms-next" / "claude-gateway" / "s" / "123"
    session_home.mkdir(parents=True)
    monkeypatch.delenv("MMS_REAL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(session_home))

    assert mms_launchers._real_user_home() == str(real_home)


def test_real_user_home_unwinds_legacy_mms_gateway_home(monkeypatch, tmp_path: Path):
    real_home = tmp_path / "real-home"
    session_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "123"
    session_home.mkdir(parents=True)
    monkeypatch.delenv("MMS_REAL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(session_home))

    assert mms_launchers._real_user_home() == str(real_home)
