from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys


def _import_mms_launchers(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path / "mms-config"))
    monkeypatch.delitem(sys.modules, "mms_core", raising=False)
    monkeypatch.delitem(sys.modules, "mms_launchers", raising=False)
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


def test_overlay_auto_github_contributor_session_entries_merges_symlinked_skill_and_commands(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    existing_commands = tmp_path / "existing-commands"
    vendor_root = tmp_path / "vendor" / "auto-github-contributor"
    skill_root = vendor_root / "skills" / "auto-github-contributor"
    installed_root = tmp_path / "installed-skills" / "auto-github-contributor"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    existing_commands.mkdir(parents=True)
    (existing_commands / "keep.toml").write_text("description = \"keep\"\n", encoding="utf-8")
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# auto-github-contributor\n", encoding="utf-8")
    (vendor_root / "commands").mkdir()
    (vendor_root / "commands" / "auto-contribute.md").write_text("# auto contribute\n", encoding="utf-8")
    installed_root.parent.mkdir(parents=True)
    os.symlink(skill_root, installed_root)
    os.symlink(existing_skills, parent_dir / "skills")
    os.symlink(existing_commands, parent_dir / "commands")

    monkeypatch.setenv("MMS_AUTO_GITHUB_CONTRIBUTOR_ROOT", str(installed_root))

    mms_launchers._overlay_auto_github_contributor_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "auto-github-contributor")
    assert (parent_dir / "skills" / "auto-github-contributor" / "SKILL.md").read_text(encoding="utf-8") == "# auto-github-contributor\n"
    assert os.path.islink(parent_dir / "commands")
    assert os.path.islink(parent_dir / "commands" / "keep.toml")
    assert os.path.islink(parent_dir / "commands" / "auto-contribute.md")


def test_overlay_auto_github_contributor_session_entries_respects_disabled_skill(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    existing_commands = tmp_path / "existing-commands"
    vendor_root = tmp_path / "vendor" / "auto-github-contributor"
    skill_root = vendor_root / "skills" / "auto-github-contributor"
    installed_root = tmp_path / "installed-skills" / "auto-github-contributor"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    (existing_skills / "auto-github-contributor").mkdir()
    (existing_skills / "auto-github-contributor" / "SKILL.md").write_text("# existing\n", encoding="utf-8")
    existing_commands.mkdir(parents=True)
    (existing_commands / "keep.toml").write_text("description = \"keep\"\n", encoding="utf-8")
    (existing_commands / "auto-contribute.md").write_text("# existing command\n", encoding="utf-8")
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# auto-github-contributor\n", encoding="utf-8")
    (vendor_root / "commands").mkdir()
    (vendor_root / "commands" / "auto-contribute.md").write_text("# auto contribute\n", encoding="utf-8")
    installed_root.parent.mkdir(parents=True)
    os.symlink(skill_root, installed_root)
    os.symlink(existing_skills, parent_dir / "skills")
    os.symlink(existing_commands, parent_dir / "commands")

    monkeypatch.setenv("MMS_AUTO_GITHUB_CONTRIBUTOR_ROOT", str(installed_root))

    mms_launchers._overlay_auto_github_contributor_session_entries(
        str(parent_dir),
        str(session_home),
        disabled_session_surfaces={"skills": ["auto-github-contributor"]},
    )

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert not (parent_dir / "skills" / "auto-github-contributor").exists()
    assert not (parent_dir / "skills" / "auto-github-contributor").is_symlink()
    assert os.path.islink(parent_dir / "commands")
    assert os.path.islink(parent_dir / "commands" / "keep.toml")
    assert not (parent_dir / "commands" / "auto-contribute.md").exists()
    assert not (parent_dir / "commands" / "auto-contribute.md").is_symlink()


def test_resolve_token_saver_root_prefers_bundled_vendor(monkeypatch, tmp_path):
    home = tmp_path / "home"
    install_root = tmp_path / "mms-install"
    bundled_root = install_root / "vendor" / "token-saver"
    shared_root = home / "auto-skills" / "shared-skills" / "token-saver"
    bundled_root.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    (bundled_root / "SKILL.md").write_text("# bundled token saver\n", encoding="utf-8")
    (shared_root / "SKILL.md").write_text("# shared token saver\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_TOKEN_SAVER_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_launchers, "__file__", str(install_root / "mms_launchers.py"))

    assert Path(mms_launchers._resolve_token_saver_root()) == bundled_root


def test_resolve_codegraph_root_prefers_bundled_vendor(monkeypatch, tmp_path):
    home = tmp_path / "home"
    install_root = tmp_path / "mms-install"
    bundled_root = install_root / "vendor" / "codegraph"
    shared_root = home / "auto-skills" / "shared-skills" / "codegraph"
    bundled_root.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    (bundled_root / "SKILL.md").write_text("# bundled codegraph\n", encoding="utf-8")
    (shared_root / "SKILL.md").write_text("# shared codegraph\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_CODEGRAPH_ROOT", raising=False)
    monkeypatch.delenv("MMS_CODEGRAPH_SKILL_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_launchers, "__file__", str(install_root / "mms_launchers.py"))

    assert Path(mms_launchers._resolve_codegraph_root()) == bundled_root


def test_overlay_codegraph_session_entries_merges_existing_session_skills(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    session_home = tmp_path / "session-home"
    parent_dir = session_home / ".codex"
    existing_skills = tmp_path / "existing-skills"
    codegraph_root = tmp_path / "codegraph"
    parent_dir.mkdir(parents=True)
    (existing_skills / "keep-skill").mkdir(parents=True)
    codegraph_root.mkdir()
    (codegraph_root / "SKILL.md").write_text("# codegraph\n", encoding="utf-8")
    os.symlink(existing_skills, parent_dir / "skills")

    monkeypatch.setenv("MMS_CODEGRAPH_ROOT", str(codegraph_root))

    mms_launchers._overlay_codegraph_session_entries(str(parent_dir), str(session_home))

    assert os.path.islink(parent_dir / "skills")
    assert os.path.islink(parent_dir / "skills" / "keep-skill")
    assert os.path.islink(parent_dir / "skills" / "codegraph")
    assert (parent_dir / "skills" / "codegraph" / "SKILL.md").read_text(encoding="utf-8") == "# codegraph\n"


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


def test_resolve_weber_root_prefers_bundled_vendor(monkeypatch, tmp_path):
    home = tmp_path / "home"
    install_root = tmp_path / "mms-install"
    bundled_root = install_root / "vendor" / "weber"
    shared_root = home / "auto-skills" / "shared-skills" / "weber"
    bundled_root.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    (bundled_root / "SKILL.md").write_text("# bundled weber\n", encoding="utf-8")
    (shared_root / "SKILL.md").write_text("# shared weber\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_WEBER_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_launchers, "__file__", str(install_root / "mms_launchers.py"))

    assert Path(mms_launchers._resolve_weber_root()) == bundled_root


def test_resolve_xmem_root_prefers_bundled_vendor(monkeypatch, tmp_path):
    home = tmp_path / "home"
    install_root = tmp_path / "mms-install"
    bundled_root = install_root / "vendor" / "xmem"
    shared_root = home / "auto-skills" / "shared-skills" / "xmem"
    bundled_root.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    (bundled_root / "SKILL.md").write_text("# bundled xmem\n", encoding="utf-8")
    (shared_root / "SKILL.md").write_text("# shared xmem\n", encoding="utf-8")

    monkeypatch.setenv("MMS_REAL_HOME", str(home))
    monkeypatch.delenv("MMS_XMEM_ROOT", raising=False)
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_launchers, "__file__", str(install_root / "mms_launchers.py"))

    assert Path(mms_launchers._resolve_xmem_root()) == bundled_root


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


def test_get_export_env_survives_deleted_current_directory(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)
    import mms_state_io

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    context_script = tmp_path / "mms-context"
    context_script.write_text("#!/bin/sh\nprintf 'context\\n'\n", encoding="utf-8")
    context_script.chmod(0o755)

    def _raise_deleted_cwd():
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setenv("PWD", str(repo_dir))
    monkeypatch.setattr(mms_state_io.os, "getcwd", _raise_deleted_cwd)
    monkeypatch.setattr(mms_launchers, "_mms_toon_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "_mms_context_script_path", lambda: str(context_script))
    monkeypatch.setattr(mms_launchers, "_token_saver_script_path", lambda: "")
    monkeypatch.setattr(mms_launchers, "validate_provider_for_cli", lambda *_args, **_kwargs: None)

    exports = mms_launchers.get_export_env(
        "claude",
        {
            "id": "relay-a",
            "api_key": "sk-runtime",
            "anthropic_base_url": "https://anthropic.example.com",
        },
    )

    assert exports["MMS_CONTEXT_BIN"] == str(context_script)
    assert exports["MMS_CONTEXT_DIR"] == str(repo_dir / ".mms" / "context-store")


def test_resolve_current_workdir_does_not_fallback_to_real_home(monkeypatch, tmp_path):
    import mms_state_io

    real_home = tmp_path / "real-home"
    real_home.mkdir()
    deleted_repo = tmp_path / "deleted-repo"

    def _raise_deleted_cwd():
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(mms_state_io.os, "getcwd", _raise_deleted_cwd)

    resolved = mms_state_io.resolve_current_workdir(
        {
            "PWD": str(deleted_repo),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
        }
    )

    assert resolved == str(deleted_repo)
    assert resolved != str(real_home)


def test_resolve_current_workdir_prefers_pwd_over_stale_mms_cwd(monkeypatch, tmp_path):
    import mms_state_io

    repo_dir = tmp_path / "repo"
    stale_dir = tmp_path / "stale"
    repo_dir.mkdir()
    stale_dir.mkdir()

    def _raise_deleted_cwd():
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(mms_state_io.os, "getcwd", _raise_deleted_cwd)

    resolved = mms_state_io.resolve_current_workdir(
        {
            "PWD": str(repo_dir),
            "MMS_CWD": str(stale_dir),
        }
    )

    assert resolved == str(repo_dir)


def test_resolve_current_workdir_uses_session_home_as_last_safe_fallback(monkeypatch, tmp_path):
    import mms_state_io

    real_home = tmp_path / "real-home"
    session_home = tmp_path / "session-home"
    real_home.mkdir()
    session_home.mkdir()

    def _raise_deleted_cwd():
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(mms_state_io.os, "getcwd", _raise_deleted_cwd)

    resolved = mms_state_io.resolve_current_workdir(
        {
            "MMS_SESSION_HOME": str(session_home),
            "MMS_REAL_HOME": str(real_home),
            "REAL_HOME": str(real_home),
        }
    )

    assert resolved == str(session_home)
    assert resolved != str(real_home)
