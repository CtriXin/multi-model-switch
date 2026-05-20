from __future__ import annotations


class _ConsoleCapture:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(item) for item in args))


def test_resolve_launch_runtime_does_not_select_legacy_claude_oauth_account(monkeypatch):
    import mms_core

    provider_runtime = {"id": "provider-a", "auth_mode": "api_key"}
    calls = []

    monkeypatch.setattr(
        mms_core,
        "resolve_account_context",
        lambda *_args, **_kwargs: calls.append("account") or {"id": "claude-oauth", "auth_mode": "oauth"},
    )
    monkeypatch.setattr(
        mms_core,
        "_resolve_provider_for_cli",
        lambda *_args, **_kwargs: (provider_runtime, ["claude-sonnet-4-6"]),
    )

    runtime, models = mms_core._resolve_launch_runtime(
        {"accounts": [{"id": "claude-main", "cli": "claude", "enabled": True}]},
        "claude",
        provider_runtime,
        ["claude-sonnet-4-6"],
        account_id="claude-main",
    )

    assert calls == []
    assert runtime is provider_runtime
    assert models == ["claude-sonnet-4-6"]


def test_handle_account_add_config_rejects_claude(monkeypatch):
    import mms_core

    console = _ConsoleCapture()
    called = []
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(
        mms_core,
        "_quick_connect_official",
        lambda *_args, **_kwargs: called.append(True),
    )

    mms_core._handle_account_add_config({}, ["claude"])

    assert called == []
    assert any("Claude OAuth 已迁移到 mmc" in message for message in console.messages)


def test_handle_account_add_config_accepts_agy(monkeypatch):
    import mms_core

    called = []
    monkeypatch.setattr(
        mms_core,
        "_quick_connect_official",
        lambda cfg, preset_cli=None: called.append((cfg, preset_cli)),
    )

    mms_core._handle_account_add_config({}, ["agy"])

    assert called == [({}, "agy")]


def test_handle_account_login_config_rejects_legacy_claude_account(monkeypatch):
    import mms_core

    console = _ConsoleCapture()
    called = []
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(
        mms_core,
        "resolve_account_context",
        lambda *_args, **_kwargs: {"id": "claude-main", "cli": "claude"},
    )
    monkeypatch.setattr(
        mms_core,
        "_run_account_login",
        lambda _account: called.append(True),
    )

    mms_core._handle_account_login_config({}, ["claude-main"])

    assert called == []
    assert any("请改用 `mmc` 登录和恢复 Claude session" in message for message in console.messages)
