from __future__ import annotations

import json
from types import SimpleNamespace


class _FakeConsole:
    def __init__(self):
        self.items = []

    def print(self, *args, **kwargs):
        self.items.append(args[0] if args else "")


def test_split_cli_prefixed_resume_ref():
    import mms_core

    assert mms_core._split_cli_prefixed_resume_ref("codex:abc") == ("codex", "abc")
    assert mms_core._split_cli_prefixed_resume_ref("Claude: session-1 ") == ("claude", "session-1")
    assert mms_core._split_cli_prefixed_resume_ref("other:abc") == ("", "other:abc")


def test_resolve_codex_resume_ref_from_bounded_index(monkeypatch, tmp_path):
    import mms_core

    root = tmp_path / "codex-root"
    root.mkdir()
    (root / "session_index.jsonl").write_text(
        json.dumps({"id": "019e3990-4e86-7591-abca-d59641c6173a", "thread_name": "demo"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MMS_CODEX_RESUME_WRITEBACK_ROOT", str(root))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(mms_core, "resolve_real_user_home", lambda env=None: str(tmp_path / "home"))

    session_id, record, error = mms_core._resolve_codex_resume_ref("019e3990")

    assert error is None
    assert session_id == "019e3990-4e86-7591-abca-d59641c6173a"
    assert record["_root"] == str(root)


def test_resolve_claude_resume_ref_from_index(monkeypatch):
    import mms_core
    import mms_session_index

    monkeypatch.setattr(
        mms_session_index,
        "list_indexed_sessions",
        lambda cli_name="claude": [
            {"session_id": "session-a", "project_path": "/tmp/a", "resume_model": "claude-sonnet-4-6"},
            {"session_id": "session-b", "project_path": "/tmp/b", "resume_model": "gpt-5.5"},
        ],
    )

    session_id, record, error = mms_core._resolve_claude_resume_ref("2")

    assert error is None
    assert session_id == "session-b"
    assert record["resume_model"] == "gpt-5.5"


def test_resolve_resume_target_requires_prefix_when_ambiguous(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_resolve_codex_resume_ref",
        lambda ref, allow_passthrough=False: ("same-id", {"id": "same-id"}, None),
    )
    monkeypatch.setattr(
        mms_core,
        "_resolve_claude_resume_ref",
        lambda ref, allow_passthrough=False: ("same-id", {"session_id": "same-id"}, None),
    )

    cli, session_id, record, error = mms_core._resolve_resume_target("same")

    assert cli is None
    assert session_id is None
    assert record is None
    assert "codex:same" in error
    assert "claude:same" in error


def test_resolve_resume_target_uses_uuid_version_hint_when_unindexed(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_resolve_codex_resume_ref",
        lambda ref, allow_passthrough=False: (None, None, f"找不到 Codex session: {ref}"),
    )
    monkeypatch.setattr(
        mms_core,
        "_resolve_claude_resume_ref",
        lambda ref, allow_passthrough=False: (None, None, f"找不到 Claude session: {ref}"),
    )

    cli, session_id, record, error = mms_core._resolve_resume_target(
        "2ea6c1bc-8632-4d5c-94ba-672b4a744871"
    )
    assert error is None
    assert cli == "claude"
    assert session_id == "2ea6c1bc-8632-4d5c-94ba-672b4a744871"
    assert record["_unindexed"] is True

    cli, session_id, record, error = mms_core._resolve_resume_target(
        "019e3990-4e86-7591-abca-d59641c6173a"
    )
    assert error is None
    assert cli == "codex"
    assert session_id == "019e3990-4e86-7591-abca-d59641c6173a"
    assert record["_unindexed"] is True


def test_handle_resume_command_passes_codex_resume_args(monkeypatch):
    import mms_core

    captured = {}
    console = _FakeConsole()
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(
        mms_core,
        "_resolve_resume_target",
        lambda session_ref, cli_hint="auto": ("codex", "codex-session", {"id": "codex-session"}, None),
    )
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda cfg=None, cli_override=None: "zh-CN")
    monkeypatch.setattr(mms_core, "set_language", lambda language: None)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda cfg: {"id": "provider-a"})
    monkeypatch.setattr(
        mms_core,
        "ensure_models_ready",
        lambda cfg, provider: (provider, [{"model": "gpt-5.5"}, {"model": "gpt-5.4"}]),
    )

    def fake_resolve_runtime(cfg, cli, args, default_provider, default_models, session_record):
        captured["requested_model"] = args.model
        return (
            {"id": "provider-a", "runtime_kind": "provider", "auth_mode": "api_key"},
            default_models,
            "codex",
            {"model": args.model},
        )

    def fake_launch(cli, model_info, runtime, once=False, extra_args=None):
        captured.update(
            {
                "cli": cli,
                "model_info": model_info,
                "runtime": runtime,
                "once": once,
                "extra_args": extra_args,
            }
        )

    monkeypatch.setattr(mms_core, "_resolve_resume_runtime_and_model", fake_resolve_runtime)
    monkeypatch.setattr(mms_core, "_launch_with_tracking", fake_launch)

    mms_core.handle_resume_command(
        ["codex-session", "--model", "gpt-5.4", "--once", "continue work"],
        preloaded_command_cfg={"recommend": {"models": ["gpt-5.5"]}},
    )

    assert captured["requested_model"] == "gpt-5.4"
    assert captured["cli"] == "codex"
    assert captured["once"] is True
    assert captured["model_info"] == {"model": "gpt-5.4"}
    assert captured["extra_args"] == ["resume", "codex-session", "continue work"]


def test_handle_resume_command_passes_claude_resume_args_and_project(monkeypatch, tmp_path):
    import mms_core

    captured = {}
    project = tmp_path / "project"
    project.mkdir()
    console = _FakeConsole()
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(
        mms_core,
        "_resolve_resume_target",
        lambda session_ref, cli_hint="auto": (
            "claude",
            "claude-session",
            {"session_id": "claude-session", "project_path": str(project), "resume_model": "gpt-5.5"},
            None,
        ),
    )
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda cfg: cfg)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda cfg=None, cli_override=None: "zh-CN")
    monkeypatch.setattr(mms_core, "set_language", lambda language: None)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda cfg: {"id": "provider-a"})
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda cfg, provider: (provider, ["gpt-5.5"]))
    monkeypatch.setattr(mms_core.os, "chdir", lambda path: captured.setdefault("chdir", path))
    monkeypatch.setattr(
        mms_core,
        "_resolve_resume_runtime_and_model",
        lambda *args, **kwargs: (
            {"id": "provider-a", "runtime_kind": "provider", "auth_mode": "api_key"},
            ["gpt-5.5"],
            "claude",
            {"model": "gpt-5.5"},
        ),
    )
    monkeypatch.setattr(
        mms_core,
        "_launch_with_tracking",
        lambda cli, model_info, runtime, once=False, extra_args=None: captured.update(
            {
                "cli": cli,
                "model_info": model_info,
                "runtime": runtime,
                "once": once,
                "extra_args": extra_args,
            }
        ),
    )

    mms_core.handle_resume_command(
        ["--cli", "claude", "claude-session", "hello"],
        preloaded_command_cfg={"recommend": {"models": ["gpt-5.5"]}},
    )

    assert captured["chdir"] == str(project)
    assert captured["cli"] == "claude"
    assert captured["extra_args"] == ["--resume", "claude-session", "hello"]


def test_codex_writeback_callback_prints_mms_resume_hint(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "session"
    session_codex = session_home / ".codex"
    target_codex = tmp_path / "target-codex"
    session_codex.mkdir(parents=True)
    target_codex.mkdir()
    old_record = {"id": "019e0000-0000-7000-8000-000000000000", "updated_at": "2026-05-19T00:00:00Z"}
    (session_codex / "session_index.jsonl").write_text(json.dumps(old_record) + "\n", encoding="utf-8")

    console = _FakeConsole()
    monkeypatch.setattr(mms_launchers, "console", console)
    monkeypatch.setattr(mms_launchers.sys, "argv", ["mms"])
    env = {
        "MMS_SESSION_HOME": str(session_home),
        mms_launchers._CODEX_RESUME_WRITEBACK_ROOT_ENV: str(target_codex),
    }
    callback = mms_launchers._codex_resume_writeback_callback(env)

    new_record = {"id": "019e1111-1111-7000-8000-111111111111", "updated_at": "2026-05-20T00:00:00Z"}
    (session_codex / "session_index.jsonl").write_text(
        json.dumps(old_record) + "\n" + json.dumps(new_record) + "\n",
        encoding="utf-8",
    )

    callback(0)

    assert any("mms resume codex:019e1111-1111-7000-8000-111111111111" in item for item in console.items)
    assert (target_codex / "session_index.jsonl").exists()


def test_finalize_claude_slot_prints_mms_resume_hint(monkeypatch, tmp_path):
    import mms_launchers

    session_home = tmp_path / "12345"
    session_home.mkdir()
    console = _FakeConsole()
    calls = {}
    monkeypatch.setattr(mms_launchers, "console", console)
    monkeypatch.setattr(mms_launchers.sys, "argv", ["mms"])
    monkeypatch.setattr(
        mms_launchers,
        "read_slot_marker",
        lambda _home: {"cwd": str(tmp_path), "account_id": "acct", "account_home": str(tmp_path / "acct")},
    )
    monkeypatch.setattr(mms_launchers, "_sync_claude_session_state_to_account_home", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_launchers, "_record_account_guard_finalize", lambda *_args, **_kwargs: None)

    def fake_finalize(**kwargs):
        calls.update(kwargs)
        return {"session_id": "2ea6c1bc-8632-4d5c-94ba-672b4a744871"}

    monkeypatch.setattr(mms_launchers, "finalize_claude_session", fake_finalize)

    mms_launchers._finalize_claude_slot(str(session_home), exit_code=0)

    assert calls["pid"] == 12345
    assert any("mms resume claude:2ea6c1bc-8632-4d5c-94ba-672b4a744871" in item for item in console.items)


def test_finalize_claude_session_recovers_missing_slot_state_from_project_jsonl(monkeypatch, tmp_path):
    import mms_session_index
    from mms_project_store import claude_raw_entry_path

    real_home = tmp_path / "real-home"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setenv("MMS_REAL_HOME", str(real_home))
    monkeypatch.setenv("REAL_HOME", str(real_home))
    monkeypatch.setenv("ORIGINAL_HOME", str(real_home))

    session_id = "05b53311-036b-41e7-8b94-4f018aabbac8"
    transcript = claude_raw_entry_path("projects", str(workspace), account_id="provider-a") / "-tmp-repo" / f"{session_id}.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps({"type": "last-prompt", "sessionId": session_id}) + "\n",
        encoding="utf-8",
    )

    result = mms_session_index.finalize_claude_session(
        cwd=str(workspace),
        pid=29168,
        account_id="provider-a",
        exit_code=130,
    )

    assert result["session_id"] == session_id
    assert result["exit_code"] == 130
    assert result["recovered_from"].endswith(f"{session_id}.jsonl")
    assert mms_session_index.get_indexed_session(session_id, cli_name="claude")["session_id"] == session_id


def test_claude_session_end_hook_prints_mms_resume_hint():
    import subprocess
    import mms_launchers

    session_id = "05b53311-036b-41e7-8b94-4f018aabbac8"
    result = subprocess.run(
        [mms_launchers._CLAUDE_MMS_RESUME_HINT_HOOK],
        input=json.dumps({"session_id": session_id}),
        text=True,
        capture_output=True,
        check=True,
        env={"MMS_RESUME_COMMAND_NAME": "ccs", "PATH": "/usr/bin:/bin"},
    )

    assert result.stdout.strip() == f"[MMS] resume: mms resume claude:{session_id}"


def test_mms_session_hooks_include_claude_session_end_resume_hint():
    import mms_launchers

    hooks = mms_launchers._merge_mms_session_hooks({})
    commands = [
        hook.get("command")
        for group in hooks.get("SessionEnd", [])
        for hook in group.get("hooks", [])
    ]

    assert mms_launchers._CLAUDE_MMS_RESUME_HINT_HOOK in commands
