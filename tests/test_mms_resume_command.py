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
