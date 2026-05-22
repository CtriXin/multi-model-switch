from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mms_launchers


def _skill(root: Path, body: str = "# xmem\n") -> Path:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(body, encoding="utf-8")
    return root


def test_overlay_xmem_session_entries_merges_existing_skills(monkeypatch, tmp_path):
    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    xmem_root = _skill(tmp_path / "xmem")
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    os.symlink(existing_skills, parent_dir / "skills")

    monkeypatch.setenv("MMS_XMEM_ROOT", str(xmem_root))

    mms_launchers._overlay_xmem_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "xmem")
    assert (parent_dir / "skills" / "xmem" / "SKILL.md").read_text(encoding="utf-8") == "# xmem\n"


def test_overlay_xmem_session_entries_respects_disabled_skill(monkeypatch, tmp_path):
    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    xmem_root = _skill(tmp_path / "xmem")
    parent_dir.mkdir(parents=True)

    monkeypatch.setenv("MMS_XMEM_ROOT", str(xmem_root))

    mms_launchers._overlay_xmem_session_entries(
        str(parent_dir),
        str(session_home),
        disabled_session_surfaces={"skills": ["xmem"]},
    )

    assert not (parent_dir / "skills" / "xmem").exists()


def test_mms_claude_hooks_include_xmem_session_start():
    hooks = mms_launchers._merge_mms_session_hooks({})
    commands = [
        hook.get("command")
        for group in hooks.get("SessionStart", [])
        for hook in group.get("hooks", [])
    ]

    assert mms_launchers._XMEM_SESSION_START_HOOK in commands


def test_mms_claude_hooks_include_xmem_session_end():
    hooks = mms_launchers._merge_mms_session_hooks({})
    commands = [
        hook.get("command")
        for group in hooks.get("Stop", [])
        for hook in group.get("hooks", [])
    ]

    assert mms_launchers._XMEM_SESSION_END_HOOK in commands


def test_codex_hooks_include_xmem_session_start():
    payload = mms_launchers._build_codex_session_hooks({})
    commands = [
        hook.get("command")
        for group in payload.get("hooks", {}).get("SessionStart", [])
        for hook in group.get("hooks", [])
    ]

    assert mms_launchers._XMEM_SESSION_START_HOOK in commands


def test_codex_hooks_include_xmem_session_end():
    payload = mms_launchers._build_codex_session_hooks({})
    commands = [
        hook.get("command")
        for group in payload.get("hooks", {}).get("Stop", [])
        for hook in group.get("hooks", [])
    ]

    assert mms_launchers._XMEM_SESSION_END_HOOK in commands


def test_disabling_xmem_skill_removes_xmem_hooks():
    claude_hooks = mms_launchers._filter_hooks_by_disabled(
        mms_launchers._merge_mms_session_hooks({}),
        {"skills": ["xmem"]},
    )
    claude_commands = [
        hook.get("command")
        for groups in claude_hooks.values()
        for group in groups
        for hook in group.get("hooks", [])
    ]
    assert mms_launchers._XMEM_SESSION_START_HOOK not in claude_commands
    assert mms_launchers._XMEM_SESSION_END_HOOK not in claude_commands

    codex_hooks = mms_launchers._build_codex_session_hooks({}, disabled_session_surfaces={"skills": ["xmem"]})
    codex_commands = [
        hook.get("command")
        for groups in codex_hooks.get("hooks", {}).values()
        for group in groups
        for hook in group.get("hooks", [])
    ]
    assert mms_launchers._XMEM_SESSION_START_HOOK not in codex_commands
    assert mms_launchers._XMEM_SESSION_END_HOOK not in codex_commands


def test_xmem_session_end_hook_is_silent_and_finish_only(tmp_path):
    fake_bin = tmp_path / "xmem"
    log_path = tmp_path / "xmem.log"
    fake_bin.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$XMEM_TEST_LOG\"\n"
        "echo should-not-leak\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    repo = tmp_path / "repo"
    repo.mkdir()

    result = subprocess.run(
        [mms_launchers._XMEM_SESSION_END_HOOK],
        cwd=repo,
        text=True,
        capture_output=True,
        check=True,
        env={
            "MMS_XMEM_BIN": str(fake_bin),
            "XMEM_TEST_LOG": str(log_path),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.stdout == ""
    assert result.stderr == ""
    assert log_path.read_text(encoding="utf-8").strip() == f"hook finish --path {repo}"


def test_session_wrappers_expose_xmem(monkeypatch, tmp_path):
    session_home = tmp_path / "session"
    xmem_bin = tmp_path / "xmem"
    xmem_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    xmem_bin.chmod(0o755)
    env = {"PATH": "/usr/bin"}

    monkeypatch.setattr(mms_launchers, "_xmem_cli_path", lambda: str(xmem_bin))
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_token_saver_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_SESSION_REAL_HOME_WRAPPER_COMMANDS", ())

    mms_launchers._install_session_command_wrappers(str(session_home), env)

    wrapper = session_home / ".mms" / "bin" / "xmem"
    assert wrapper.exists()
    assert f'exec "{xmem_bin}" "$@"' in wrapper.read_text(encoding="utf-8")
    assert env["XMEM_BIN"] == str(wrapper)
    assert env["PATH"].startswith(str(wrapper.parent) + os.pathsep)


def test_opencode_session_assets_include_xmem_skill_and_plugin(monkeypatch, tmp_path):
    config_dir = tmp_path / "opencode"
    session_home = tmp_path / "session"
    xmem_root = _skill(tmp_path / "xmem")

    monkeypatch.setenv("MMS_XMEM_ROOT", str(xmem_root))
    monkeypatch.setattr(mms_launchers, "_xmem_cli_path", lambda: str(tmp_path / "xmem-bin"))
    monkeypatch.setattr(mms_launchers, "_opencode_rtk_plugin_path", lambda runtime=None: "")

    mms_launchers._overlay_opencode_session_assets(str(config_dir), str(session_home), runtime={})

    assert os.path.islink(config_dir / "skills" / "xmem")
    assert os.path.islink(config_dir / "plugins" / "mms-xmem.ts")
