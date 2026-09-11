"""A machine that cannot run sessions says what is missing (colleague report).

Every model showing 不可用 with "Web 会话接入尚未就绪" gave the reader nothing
to act on, while the probe already knew it was a missing pi or a Node too old.
"""
from pathlib import Path

import pytest

from mms_web.drivers.launch_bridge import probe_mms_pi_seam


def test_a_missing_pi_names_pi(monkeypatch):
    monkeypatch.setattr("mms_web.drivers.launch_bridge.pi_runtime", lambda: ("", ""))
    seam = probe_mms_pi_seam()
    assert seam["available"] is False
    assert "pi" in seam["reason"] and "安装脚本" in seam["reason"]


def test_an_old_node_names_the_version_it_needs(monkeypatch):
    """pi installed, Node too old: the usual shape of the colleague's machine."""
    monkeypatch.setattr("mms_web.drivers.launch_bridge.pi_runtime", lambda: ("/usr/local/bin/pi", ""))
    seam = probe_mms_pi_seam()
    assert seam["available"] is False
    assert "22.15" in seam["reason"]


def test_a_healthy_machine_gives_no_reason(monkeypatch):
    monkeypatch.setattr("mms_web.drivers.launch_bridge.pi_runtime",
                        lambda: ("/usr/local/bin/pi", "/usr/local/bin/node"))
    monkeypatch.setattr("mms_web.drivers.launch_bridge._WORKER", Path(__file__))
    seam = probe_mms_pi_seam()
    assert seam["available"] is True and seam["reason"] == ""


def _capabilities(*, real_launch=True, seam=None, catalog=True):
    """A real SessionService with only the fields capabilities() reads.

    Constructing one for real would probe this machine, which is the thing
    being stubbed.
    """
    from mms_web.sessions import SessionService

    service = SessionService.__new__(SessionService)
    service._real_launch = real_launch
    service._seam = seam if seam is not None else {"available": True, "reason": ""}
    service._catalog = type("C", (), {"resolve_launch": lambda self: None})() if catalog else object()
    return service.capabilities()


def test_capabilities_carry_the_blocker_for_each_cause():
    assert _capabilities() == {"launch": True, "launchReason": ""}
    assert _capabilities(real_launch=False)["launchReason"] == "没有选定 MMS 配置根，无法启动会话。"
    seam = {"available": False, "reason": "没有找到符合要求的 Node.js：需要 22.15 以上的版本。升级 Node 后重启 Pilot。"}
    assert _capabilities(seam=seam)["launchReason"] == seam["reason"]
    assert "模型目录" in _capabilities(catalog=False)["launchReason"]


def test_the_snapshot_repeats_the_blocker_instead_of_a_generic_line():
    """What the page actually renders under every model and channel."""
    import mms_web.server as server

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert 'blocker = str(capabilities.get("launchReason")' in source
    assert '"reason": model.get("reason") or blocker' in source
    assert '"reason": preset.get("reason") or blocker' in source
