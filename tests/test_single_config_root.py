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


# Every place in the runtime that still spells the retired ~/.config/mms, with
# the reason it is allowed to. Anything not listed here is a new legacy-root
# read or write, which is what this contract forbids.
#
# Adding an entry is a deliberate act: say why the retired root belongs there.
_LEGACY_ROOT_ALLOWED = {
    # Detects a dirty legacy install so it can be cleaned up.
    ("mmc_core.py", '"/.config/mms/",'),
    ("mms_launchers.py", 'forbidden_parts = ("/.mms/", "/.config/mms/", "/ccswitch", "/hive")'),
    # Prose describing the retirement.
    ("mms_consumer_bundle.py", "``~/.config/mms`` is opt-in so preview consumers do not silently cross root"),
    ("mms_core.py", "Collects one channel interactively. The legacy ~/.config/mms root is never"),
    ("mms_state_io.py", '"""True for the retired ~/.config/mms directory (or any root named like it).'),
    ("mms_state_io.py", "The legacy stable root (~/.config/mms) is retired as a config source; the"),
    ("mms_web/catalog.py", "real ``~/.config/mms*`` roots stay untouched."),
    ("scripts/local_channel_update.py", "real MMS config tree under ~/.config/mms."),
    # The descriptor that names the retired root so callers can report on it.
    ("mms_state_io.py", '"stable_root": os.path.join(real_home, ".config", "mms"),'),
    # Refuses to write either root, so it has to know both names.
    ("mms_web/catalog.py", '_PROTECTED_ROOT_NAMES = (".config/mms", ".config/mms-next")'),
    ("mms_web/catalog_worker.py", '_PROTECTED_ROOT_NAMES = (".config/mms", ".config/mms-next")'),
    ("scripts/local_channel_update.py", 'for marker in ("/.config/mms-next", "/.config/mms"):'),
    # A version.json an install from before the move left behind.
    ("scripts/local_channel_update.py", 'legacy = real_home() / ".config" / "mms" / "version.json"'),
    # One-time manual import of an old config into the DB. Human-run, never automatic.
    ("mms_registry_cli.py", '"It does not write the retired ~/.config/mms tree, config roots, DB, generated bundles, secret backends, or Claude config.",'),
    ("mms_registry_cli.py", '"command": "./mmf preview import-legacy --from ~/.config/mms --apply --include-secrets --json && ./mmf preview publish --json",'),
    ("mms_registry_cli.py", '"human must approve any stable ~/.config/mms write",'),
    ("mms_registry_cli.py", '"legacy `~/.config/mms`",'),
    ("mms_registry_cli.py", 'command = "./mmf preview prepare --from ~/.config/mms --include-secrets --json"'),
    ("mms_registry_cli.py", 'command = "./mmf preview prepare --from ~/.config/mms --include-secrets --json" if missing_keys > 0 else "./mmf preview prepare --from ~/.config/mms --json"'),
    ("mms_registry_cli.py", 'command = "./mmf preview prepare --from ~/.config/mms --json"'),
    ("mms_registry_cli.py", 'next_action = {"label": "Import legacy config into preview DB", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --json"}'),
    ("mms_registry_cli.py", 'next_actions.append({"label": "Import legacy config into preview DB", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --json"})'),
    ("mms_registry_cli.py", 'next_actions.append({"label": "Optional: import keys into preview secret backend", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --include-secrets --json && ./mmf preview publish --json"})'),
}


def _legacy_root_mentions():
    """Every non-comment line in the runtime that names the retired root."""
    import re

    join = re.compile(r'["\']\.config["\']\s*[,/]\s*(?:\n\s*)?["\']mms["\']')
    literal = re.compile(r"\.config/mms(?![\w-])")
    targets = sorted(
        set(
            list(ROOT.glob("mms_*.py"))
            + list(ROOT.glob("mms_web/**/*.py"))
            + [
                ROOT / "mmc_core.py",
                ROOT / "statusline-command.sh",
                ROOT / "scripts/mms_health_watchdog.py",
                ROOT / "scripts/local_channel_update.py",
            ]
        )
    )
    found = []
    seen = set()
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for pattern in (join, literal):
            for match in pattern.finditer(text):
                number = text[: match.start()].count("\n") + 1
                if (path, number) in seen:
                    continue
                seen.add((path, number))
                line = lines[number - 1].strip()
                # A comment cannot read a directory.
                if line.startswith("#"):
                    continue
                found.append((path.relative_to(ROOT).as_posix(), line, number))
    return found


def test_no_new_code_path_reads_or_writes_the_retired_legacy_root():
    """~/.config/mms is not a config root any more, in any entry point.

    Four places kept using it long after #177 said they should not: the
    OpenCode export config, the health watchdog's whole config directory, the
    public-copy update check, and two opt-in bundle fallbacks. None of them was
    covered, because the old contract only inspected three named functions.
    """
    unexpected = [
        f"{path}:{number}: {line}"
        for path, line, number in _legacy_root_mentions()
        if (path, line) not in _LEGACY_ROOT_ALLOWED
    ]

    assert not unexpected, "new reference(s) to the retired config root:\n  " + "\n  ".join(unexpected)
