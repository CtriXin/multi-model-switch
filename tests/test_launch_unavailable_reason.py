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
    # Says both places it looked, so "but my terminal runs pi" has an answer.
    assert "Pi" in seam["reason"] and "缓存" in seam["reason"] and "安装脚本" in seam["reason"]


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


def _warm_cache(root: Path, *, executable=True, manifest=True) -> Path:
    """The shape `scripts/pi-cli-wrapper.sh` looks for in the npx cache."""
    binary = root / "_npx" / "a1b2c3" / "node_modules" / ".bin" / "pi"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/usr/bin/env node\n")
    if executable:
        binary.chmod(0o755)
    if manifest:
        package = binary.parent.parent / "@earendil-works" / "pi-coding-agent"
        package.mkdir(parents=True)
        (package / "package.json").write_text("{}")
    return binary


@pytest.fixture(autouse=True)
def _no_real_npm_cache(tmp_path_factory, monkeypatch):
    """Keep this machine's own ~/.npm out of the cache search."""
    monkeypatch.setenv("NPM_CONFIG_CACHE", str(tmp_path_factory.mktemp("empty-npm")))
    monkeypatch.delenv("npm_config_cache", raising=False)


def test_the_warmed_npx_cache_counts_as_an_installed_pi(tmp_path, monkeypatch):
    """The wrapper a launch goes through accepts it, so the gate must too.

    A colleague's machine ran Pi fine from the terminal while every model in
    Pilot showed 不可用, because only PATH was consulted here.
    """
    import mms_web.drivers.launch_bridge as bridge

    binary = _warm_cache(tmp_path / "pi-npx")
    monkeypatch.setattr(bridge.shutil, "which", lambda name: None if name == "pi" else "/usr/bin/node")
    monkeypatch.setitem(__import__("sys").modules, "mms_pi_support",
                        type("M", (), {"_pi_npx_cache_dir": staticmethod(lambda: str(tmp_path / "pi-npx"))}))
    assert bridge.cached_pi() == str(binary)


def test_an_incomplete_cache_is_not_mistaken_for_an_install(tmp_path, monkeypatch):
    import mms_web.drivers.launch_bridge as bridge

    _warm_cache(tmp_path / "no-manifest", manifest=False)
    _warm_cache(tmp_path / "not-executable", executable=False)
    for name in ("no-manifest", "not-executable", "empty"):
        monkeypatch.setitem(__import__("sys").modules, "mms_pi_support",
                            type("M", (), {"_pi_npx_cache_dir": staticmethod(lambda n=name: str(tmp_path / n))}))
        assert bridge.cached_pi() == "", name


def test_a_global_pi_still_wins(tmp_path, monkeypatch):
    import mms_web.drivers.launch_bridge as bridge

    _warm_cache(tmp_path / "pi-npx")
    monkeypatch.setattr(bridge.shutil, "which", lambda name: "/usr/local/bin/" + name)
    monkeypatch.setattr(bridge, "cached_pi", lambda: pytest.fail("PATH pi must be preferred"))
    executable, _node = bridge.pi_runtime()
    assert executable == "/usr/local/bin/pi"


def test_a_pi_dist_cli_in_npms_own_cache_is_found_too(tmp_path, monkeypatch):
    """The published package may expose dist/cli.js without a .bin shim."""
    import mms_web.drivers.launch_bridge as bridge

    cli = tmp_path / "npm-home" / "_npx" / "hash" / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "cli.js"
    cli.parent.mkdir(parents=True)
    cli.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    cli.chmod(0o755)
    (cli.parents[1] / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NPM_CONFIG_CACHE", str(tmp_path / "npm-home"))
    monkeypatch.setitem(__import__("sys").modules, "mms_pi_support",
                        type("M", (), {"_pi_npx_cache_dir": staticmethod(lambda: str(tmp_path / "absent"))}))
    assert bridge.cached_pi() == str(cli)


def test_a_pi_installed_into_npms_own_cache_is_found_too(tmp_path, monkeypatch):
    """`npx pi` without the wrapper puts it in npm's default cache.

    That machine can run Pi, so the gate has to see it; only the wrapper's own
    cache was consulted before.
    """
    import mms_web.drivers.launch_bridge as bridge

    binary = _warm_cache(tmp_path / "npm-home")
    monkeypatch.setenv("NPM_CONFIG_CACHE", str(tmp_path / "npm-home"))
    monkeypatch.setitem(__import__("sys").modules, "mms_pi_support",
                        type("M", (), {"_pi_npx_cache_dir": staticmethod(lambda: str(tmp_path / "absent"))}))
    assert bridge.cached_pi() == str(binary)


def test_the_installation_cache_is_preferred_over_npms(tmp_path, monkeypatch):
    import mms_web.drivers.launch_bridge as bridge

    mine = _warm_cache(tmp_path / "mms-cache")
    _warm_cache(tmp_path / "npm-home")
    monkeypatch.setenv("NPM_CONFIG_CACHE", str(tmp_path / "npm-home"))
    monkeypatch.setitem(__import__("sys").modules, "mms_pi_support",
                        type("M", (), {"_pi_npx_cache_dir": staticmethod(lambda: str(tmp_path / "mms-cache"))}))
    assert bridge.cached_pi() == str(mine)
