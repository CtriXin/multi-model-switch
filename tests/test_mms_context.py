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


def test_install_session_command_wrappers_exposes_context_bin(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    context_script = tmp_path / "mms-context"
    context_script.write_text("#!/bin/sh\nprintf 'context\\n'\n", encoding="utf-8")
    context_script.chmod(0o755)
    env = {"HOME": str(session_home), "PATH": "/usr/bin"}

    monkeypatch.setenv("HOME", str(session_home))
    monkeypatch.setattr(mms_launchers, "_SESSION_REAL_HOME_WRAPPER_COMMANDS", ())
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: str(context_script))

    mms_launchers._install_session_command_wrappers(str(session_home), env)

    wrapper = Path(env["MMS_CONTEXT_BIN"])
    assert wrapper == session_home / ".mms" / "bin" / "mms-context"
    assert wrapper.exists()
    assert f'exec "{context_script}" "$@"' in wrapper.read_text(encoding="utf-8")
    assert env["MMS_CONTEXT_DIR"] == str(session_home / ".mms" / "context-store")
    assert env["PATH"].startswith(str(wrapper.parent) + os.pathsep)


def test_get_export_env_exposes_context_bin_for_export_only_launch(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    context_script = tmp_path / "mms-context"
    context_script.write_text("#!/bin/sh\nprintf 'context\\n'\n", encoding="utf-8")
    context_script.chmod(0o755)

    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: str(context_script))
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
    assert claude_exports["MMS_CONTEXT_DIR"] == str(repo_dir / ".mms" / "context-store")
    assert codex_exports["MMS_CONTEXT_DIR"] == str(repo_dir / ".mms" / "context-store")
    assert claude_exports["PATH"] == f"{context_script.parent}:$PATH"
    assert codex_exports["PATH"] == f"{context_script.parent}:$PATH"
