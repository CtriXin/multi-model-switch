from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys


def _import_mms_launchers(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path / "mms-config"))
    sys.modules.pop("mms_core", None)
    sys.modules.pop("mms_launchers", None)
    import mms_launchers

    return mms_launchers


def test_mms_context_put_search_show_roundtrip(monkeypatch, tmp_path, capsys):
    from mms_context import main

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO("line one\nTraceback: demo failure\nline three\n"),
    )

    assert main(["put", "--title", "build log", "--kind", "tool-output", "--tag", "pytest", "--json"]) == 0
    stored = json.loads(capsys.readouterr().out)
    assert stored["ref"].startswith("mmsctx://ctx_")
    assert stored["title"] == "build log"
    assert stored["kind"] == "tool-output"
    assert stored["chars"] > 0
    assert Path(stored["store_dir"]).is_dir()

    assert main(["search", "Traceback", "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert len(results) == 1
    assert results[0]["ref"] == stored["ref"]
    assert "Traceback" in results[0]["match_snippet"]

    assert main(["show", stored["ref"], "--max-chars", "18", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["text"] == "line one\nTraceback"
    assert shown["truncated"] is True


def test_mms_context_defaults_to_session_home(monkeypatch, tmp_path):
    import mms_context

    session_home = tmp_path / "session-home"
    monkeypatch.delenv("MMS_CONTEXT_DIR", raising=False)
    monkeypatch.setenv("MMS_SESSION_HOME", str(session_home))
    monkeypatch.setenv("HOME", str(tmp_path / "real-home"))

    assert mms_context._store_dir() == session_home / ".mms" / "context-store"


def test_token_saver_run_prints_short_output(monkeypatch, tmp_path, capsys):
    import token_saver

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))

    result = token_saver.main(
        [
            "run",
            "--threshold-chars",
            "1000",
            "--",
            sys.executable,
            "-c",
            "print('small output')",
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "small output\n"
    assert not (tmp_path / "store" / "index.json").exists()


def test_token_saver_run_stores_long_output(monkeypatch, tmp_path, capsys):
    import token_saver

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))

    result = token_saver.main(
        [
            "run",
            "--threshold-chars",
            "20",
            "--title",
            "long demo",
            "--",
            sys.executable,
            "-c",
            "print('x' * 80)",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "token-saver: stored command output" in output
    assert "ref: mmsctx://ctx_" in output
    assert "exit_code: 0" in output
    assert (tmp_path / "store" / "index.json").exists()


def test_token_saver_run_preserves_nonzero_exit_code_when_stored(monkeypatch, tmp_path, capsys):
    import token_saver

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))

    result = token_saver.main(
        [
            "run",
            "--threshold-chars",
            "20",
            "--",
            sys.executable,
            "-c",
            "import sys; print('failure ' * 20); sys.exit(7)",
        ]
    )

    output = capsys.readouterr().out
    assert result == 7
    assert "ref: mmsctx://ctx_" in output
    assert "exit_code: 7" in output


def test_token_saver_run_snippet_keeps_failure_signal(monkeypatch, tmp_path, capsys):
    import token_saver

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))

    code = (
        "for i in range(80): print(f'noise before {i}')\n"
        "print('AssertionError: important failure in the middle')\n"
        "for i in range(80): print(f'noise after {i}')\n"
    )
    result = token_saver.main(
        [
            "run",
            "--threshold-lines",
            "20",
            "--snippet-chars",
            "520",
            "--",
            sys.executable,
            "-c",
            code,
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "token-saver: stored command output" in output
    assert "[token-saver: signal lines]" in output
    assert "AssertionError: important failure in the middle" in output
    assert "mmsctx://ctx_" in output


def test_token_saver_run_shorthand_uses_run_subcommand(monkeypatch, tmp_path, capsys):
    import token_saver

    monkeypatch.setenv("MMS_CONTEXT_DIR", str(tmp_path / "store"))

    result = token_saver.main(
        [
            "--",
            sys.executable,
            "-c",
            "print('short shorthand')",
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "short shorthand\n"

    result = token_saver.main(
        [
            "--threshold-chars",
            "1000",
            "--",
            sys.executable,
            "-c",
            "print('short shorthand with option')",
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "short shorthand with option\n"


def test_overlay_token_saver_session_entries_merges_existing_session_skills_and_commands(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    existing_commands = tmp_path / "existing-commands"
    token_saver_root = tmp_path / "token-saver"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    existing_commands.mkdir(parents=True)
    (existing_commands / "keep.toml").write_text("description = \"keep\"\n", encoding="utf-8")
    token_saver_root.mkdir()
    (token_saver_root / "commands").mkdir()
    (token_saver_root / "SKILL.md").write_text("# token-saver\n", encoding="utf-8")
    (token_saver_root / "commands" / "token-saver.toml").write_text("description = \"token saver\"\n", encoding="utf-8")
    os.symlink(existing_skills, parent_dir / "skills")
    os.symlink(existing_commands, parent_dir / "commands")

    monkeypatch.setenv("MMS_TOKEN_SAVER_ROOT", str(token_saver_root))

    mms_launchers._overlay_token_saver_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "token-saver")
    assert (parent_dir / "skills" / "token-saver" / "SKILL.md").read_text(encoding="utf-8") == "# token-saver\n"
    assert os.path.islink(parent_dir / "commands")
    assert os.path.islink(parent_dir / "commands" / "keep.toml")
    assert os.path.islink(parent_dir / "commands" / "token-saver.toml")


def test_resolve_token_saver_root_prefers_shared_skill(monkeypatch, tmp_path):
    home = tmp_path / "home"
    shared_root = home / "auto-skills" / "shared-skills" / "token-saver"
    shared_root.mkdir(parents=True)
    (shared_root / "SKILL.md").write_text("# shared token saver\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_TOKEN_SAVER_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    assert Path(mms_launchers._resolve_token_saver_root()) == shared_root


def test_overlay_weber_session_entries_merges_existing_session_skills(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    weber_root = tmp_path / "weber"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    weber_root.mkdir()
    (weber_root / "SKILL.md").write_text("# weber\n", encoding="utf-8")
    os.symlink(existing_skills, parent_dir / "skills")

    monkeypatch.setenv("MMS_WEBER_ROOT", str(weber_root))

    mms_launchers._overlay_weber_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "weber")
    assert (parent_dir / "skills" / "weber" / "SKILL.md").read_text(encoding="utf-8") == "# weber\n"


def test_resolve_weber_root_prefers_shared_skill(monkeypatch, tmp_path):
    home = tmp_path / "home"
    shared_root = home / "auto-skills" / "shared-skills" / "weber"
    shared_root.mkdir(parents=True)
    (shared_root / "SKILL.md").write_text("# shared weber\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_WEBER_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    assert Path(mms_launchers._resolve_weber_root()) == shared_root


def test_install_session_command_wrappers_exposes_context_bin(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    context_script = tmp_path / "mms-context"
    context_script.write_text("#!/bin/sh\nprintf 'context\\n'\n", encoding="utf-8")
    context_script.chmod(0o755)
    token_saver_script = tmp_path / "token-saver"
    token_saver_script.write_text("#!/bin/sh\nprintf 'token-saver\\n'\n", encoding="utf-8")
    token_saver_script.chmod(0o755)
    env = {"HOME": str(session_home), "PATH": "/usr/bin"}

    monkeypatch.setenv("HOME", str(session_home))
    monkeypatch.setattr(mms_launchers, "_SESSION_REAL_HOME_WRAPPER_COMMANDS", ())
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: str(context_script))
    monkeypatch.setattr(mms_launchers, "_token_saver_script_path", lambda: str(token_saver_script))

    mms_launchers._install_session_command_wrappers(str(session_home), env)

    wrapper = Path(env["MMS_CONTEXT_BIN"])
    token_saver_wrapper = Path(env["TOKEN_SAVER_BIN"])
    assert wrapper == session_home / ".mms" / "bin" / "mms-context"
    assert wrapper.exists()
    assert f'exec "{context_script}" "$@"' in wrapper.read_text(encoding="utf-8")
    assert token_saver_wrapper == session_home / ".mms" / "bin" / "token-saver"
    assert env["MMS_TOKEN_SAVER_BIN"] == str(token_saver_wrapper)
    assert f'exec "{token_saver_script}" "$@"' in token_saver_wrapper.read_text(encoding="utf-8")
    assert env["MMS_CONTEXT_DIR"] == str(session_home / ".mms" / "context-store")
    assert env["PATH"].startswith(str(wrapper.parent) + os.pathsep)


def test_get_export_env_exposes_context_bin_for_export_only_launch(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    context_script = tmp_path / "mms-context"
    context_script.write_text("#!/bin/sh\nprintf 'context\\n'\n", encoding="utf-8")
    context_script.chmod(0o755)
    token_saver_script = tmp_path / "token-saver"
    token_saver_script.write_text("#!/bin/sh\nprintf 'token-saver\\n'\n", encoding="utf-8")
    token_saver_script.chmod(0o755)

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: str(context_script))
    monkeypatch.setattr(mms_launchers, "_token_saver_script_path", lambda: str(token_saver_script))
    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda *_args, **_kwargs: None)

    runtime = {
        "id": "relay-a",
        "api_key": "sk-runtime",
        "base_url": "https://relay.example.com",
        "anthropic_base_url": "https://anthropic.example.com",
        "openai_base_url": "https://openai.example.com/v1",
    }

    claude_exports = mms_launchers.get_export_env("claude", runtime)
    codex_exports = mms_launchers.get_export_env("codex", runtime)

    assert claude_exports["MMS_CONTEXT_BIN"] == str(context_script)
    assert codex_exports["MMS_CONTEXT_BIN"] == str(context_script)
    assert claude_exports["TOKEN_SAVER_BIN"] == str(token_saver_script)
    assert codex_exports["TOKEN_SAVER_BIN"] == str(token_saver_script)
    assert claude_exports["MMS_TOKEN_SAVER_BIN"] == str(token_saver_script)
    assert codex_exports["MMS_TOKEN_SAVER_BIN"] == str(token_saver_script)
    assert claude_exports["MMS_CONTEXT_DIR"] == str(repo_dir / ".mms" / "context-store")
    assert codex_exports["MMS_CONTEXT_DIR"] == str(repo_dir / ".mms" / "context-store")
    assert claude_exports["PATH"] == f"{context_script.parent}:$PATH"
    assert codex_exports["PATH"] == f"{context_script.parent}:$PATH"
