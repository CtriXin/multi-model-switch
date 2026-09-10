"""Only ~/.config/mms-next is a config source (issue #177).

The legacy ~/.config/mms root is retired: no entrance reads it, no bootstrap
imports it, the stable pin the old mmd/mmm wrappers exported is ignored, and
the maintainer link script no longer writes those wrappers.
"""
import os
import re
import stat
import subprocess
from pathlib import Path

import mms_state_io

ROOT = Path(__file__).resolve().parents[1]


def test_stable_pin_no_longer_switches_the_mode(tmp_path):
    legacy = tmp_path / ".config" / "mms"
    env = {"MMS_CONFIG_ROOT": str(legacy), "MMS_CONFIG_ROOT_MODE": "stable"}
    assert mms_state_io.mms_config_root_mode(str(legacy), env) == "preview"
    assert mms_state_io.mms_config_root_status(config_dir=str(legacy), env=env)["mode"] == "preview"


def test_explicit_pin_at_the_real_legacy_root_is_redirected(tmp_path):
    """`export MMS_CONFIG_ROOT=~/.config/mms` left in a shell rc, or the retired
    mmd/mmm wrapper env, must not read the legacy root; any other explicit
    directory is still honoured."""
    real_home = tmp_path / "home"
    env = {"MMS_REAL_HOME": str(real_home), "MMS_CONFIG_ROOT": str(real_home / ".config" / "mms")}
    assert mms_state_io.resolve_mms_config_dir(env) == str(real_home / ".config" / "mms-next")
    env["MMS_CONFIG_DIR"] = env.pop("MMS_CONFIG_ROOT")
    assert mms_state_io.resolve_mms_config_dir(env) == str(real_home / ".config" / "mms-next")
    other = {"MMS_REAL_HOME": str(real_home), "MMS_CONFIG_ROOT": str(tmp_path / "elsewhere")}
    assert mms_state_io.resolve_mms_config_dir(other) == str(tmp_path / "elsewhere")


def test_default_root_is_mms_next_and_mode_is_preview(tmp_path):
    env = {"MMS_REAL_HOME": str(tmp_path)}
    assert mms_state_io.resolve_mms_config_dir(env) == str(tmp_path / ".config" / "mms-next")
    assert mms_state_io.mms_config_root_mode(env=env) == "preview"


def test_gateway_session_under_the_legacy_directory_resolves_to_the_single_root(tmp_path):
    """Gateway homes still live under ~/.config/mms/*-gateway; a child process
    whose XDG_CONFIG_HOME points inside one must read the shared root, not the
    retired legacy config."""
    session_config = tmp_path / ".config" / "mms" / "claude-gateway" / "s" / "123" / ".config"
    env = {"MMS_REAL_HOME": str(tmp_path), "XDG_CONFIG_HOME": str(session_config)}
    assert mms_state_io.resolve_mms_config_dir(env) == str(tmp_path / ".config" / "mms-next")


def test_core_never_imports_the_legacy_root():
    text = (ROOT / "mms_core.py").read_text(encoding="utf-8")
    assert "_import_legacy_root_into_v2" not in text
    assert "_legacy_root_import_candidate" not in text
    assert "preview prepare --from ~/.config/mms" not in text


def test_config_root_fallbacks_do_not_point_at_the_legacy_root():
    launchers = (ROOT / "mms_launchers.py").read_text(encoding="utf-8")
    for name in ("_model_context_overrides_path", "_selected_mms_config_root"):
        start = launchers.index(f"def {name}(")
        body = launchers[start: launchers.index("\ndef ", start + 1)]
        assert '_real_user_path(".config", "mms")' not in body, name
    bridge = (ROOT / "mms_bridge.py").read_text(encoding="utf-8")
    start = bridge.index("def _incident_log_path(")
    body = bridge[start: bridge.index("\ndef ", start + 1)]
    assert '".config", "mms")' not in body


def test_installer_no_longer_reads_the_legacy_root_for_hints():
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "legacy_config_has_route_candidates" not in text
    # Port holders from any install are stoppable servers.
    assert "listening_on_port" in text
    assert "if pid in port_holders:" in text
    # The reuse probe hashes the shared config root, as the server does.
    assert '"$MMS_HOME" "$CONFIG_ROOT" <<' in text


def test_link_script_writes_no_legacy_wrappers_and_removes_stale_ones(tmp_path):
    home = tmp_path / "home"
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    public = home / ".mms" / "mms"
    public.parent.mkdir(parents=True)
    public.write_text("#!/bin/sh\n")
    dev = tmp_path / "dev"
    canary = tmp_path / "canary"
    for root, entry in ((dev, "mmf"), (canary, "mms")):
        root.mkdir()
        (root / entry).write_text("#!/bin/sh\n")
    # A wrapper this script wrote earlier carries the legacy pin: it goes.
    (bin_dir / "mmd").write_text('#!/bin/sh\nexport MMS_CONFIG_ROOT_MODE="stable"\n')
    # Something the user put there under the same name is not ours to delete.
    (bin_dir / "mmm").write_text("#!/bin/sh\necho mine\n")
    env = {**os.environ, "MMS_REAL_HOME": str(home), "HOME": str(home),
           "MMS_LOCAL_BIN": str(bin_dir), "MMS_PUBLIC_ENTRY": str(public),
           "MMS_DEV_ROOT": str(dev), "MMS_CANARY_ROOT": str(canary),
           "MMS_MANAGED_PYTHON": "/usr/bin/env python3"}
    result = subprocess.run(["bash", str(ROOT / "scripts" / "link_local_channel_commands.sh")],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not (bin_dir / "mmd").exists()
    assert (bin_dir / "mmm").read_text() == "#!/bin/sh\necho mine\n"
    for name in ("mms", "mmf", "mmg"):
        wrapper = (bin_dir / name).read_text()
        assert "MMS_CONFIG_ROOT_MODE=\"stable\"" not in wrapper
        assert ".config/mms\"" not in wrapper, name
    assert 'MMS_CONFIG_ROOT="' + str(home / ".config" / "mms-next") + '"' in (bin_dir / "mmf").read_text()
    assert "mmd / mmm are retired" in result.stdout


def test_retired_legacy_directory_is_still_refused_as_a_v2_root(tmp_path):
    """Mode is always preview now, so the registry guard keys on the directory
    name instead: ~/.config/mms holds gateway session state, never a v2 root."""
    assert mms_state_io.is_retired_legacy_root(tmp_path / ".config" / "mms") is True
    assert mms_state_io.is_retired_legacy_root(tmp_path / ".config" / "mms-next") is False
    status = mms_state_io.mms_config_root_status(config_dir=str(tmp_path / ".config" / "mms"), env={})
    assert status["legacy_root"] is True and status["mode"] == "preview"
