from __future__ import annotations


def test_quick_connect_gateway_prompts_name_url_key_before_advanced_fields(monkeypatch):
    import mms_core

    call_order: list[str] = []
    wizard_labels: list[str] = []
    saved_configs: list[dict] = []
    saved_credentials: list[tuple[str, str, str, str, str]] = []

    monkeypatch.setattr(mms_core, "_ensure_interactive_terminal", lambda _label: None)
    monkeypatch.setattr(mms_core, "_select_provider_template", lambda preset_id=None: "generic")
    monkeypatch.setattr(mms_core, "_provider_map", lambda _cfg: {})
    monkeypatch.setattr(mms_core, "_unique_runtime_id", lambda _ids, suggested_id: suggested_id)
    monkeypatch.setattr(mms_core, "_upsert_provider", lambda cfg, provider: {**cfg, "providers": [provider]})
    monkeypatch.setattr(mms_core, "load_config", lambda: {"providers": [{"id": "team-gateway"}]})
    monkeypatch.setattr(mms_core, "_probe_models", lambda _ctx: {"models": ["gpt-5.4"]})
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _cfg, provider_id: {"id": provider_id})

    class _Console:
        @staticmethod
        def print(*_args, **_kwargs):
            return None

    monkeypatch.setattr(mms_core, "console", _Console())
    monkeypatch.setattr(mms_core, "Panel", lambda *args, **kwargs: None)

    wizard_answers = iter(["Team Gateway", "https://relay.example.com/v1", "sk-demo"])

    def _fake_wizard_prompt(label, default="", password=False, required=False):
        call_order.append(f"wizard:{label}")
        wizard_labels.append(label)
        return next(wizard_answers)

    monkeypatch.setattr(mms_core, "_wizard_prompt", _fake_wizard_prompt)

    def _fake_confirm(label, default=False):
        call_order.append(f"confirm:{label}")
        return False

    class _Confirm:
        @staticmethod
        def ask(label, default=False):
            return _fake_confirm(label, default=default)

    monkeypatch.setattr(mms_core, "Confirm", _Confirm)

    def _fake_proxy_prompt(proxy, no_proxy, wizard=False):
        call_order.append("proxy")
        assert wizard is True
        return "http://127.0.0.1:7890", "localhost"

    monkeypatch.setattr(mms_core, "_prompt_validated_proxy_fields", _fake_proxy_prompt)

    def _fake_timezone_prompt(current, wizard=False):
        call_order.append("timezone")
        assert wizard is True
        return "Asia/Shanghai"

    monkeypatch.setattr(mms_core, "_prompt_validated_timezone", _fake_timezone_prompt)
    monkeypatch.setattr(mms_core, "save_config", lambda cfg: saved_configs.append(cfg))
    monkeypatch.setattr(
        mms_core,
        "save_provider_credentials",
        lambda provider_id, base_url, api_key, openai_base_url, anthropic_base_url: saved_credentials.append(
            (provider_id, base_url, api_key, openai_base_url, anthropic_base_url)
        ),
    )

    cfg, changed = mms_core._quick_connect_gateway({"providers": []})

    assert changed is True
    assert cfg == {"providers": [{"id": "team-gateway"}]}
    assert "列表展示名" in wizard_labels[0]
    assert call_order[:6] == [
        f"wizard:{wizard_labels[0]}",
        f"wizard:{wizard_labels[1]}",
        f"wizard:{wizard_labels[2]}",
        "confirm:模型列表地址与请求地址不同？（高级）",
        "proxy",
        "timezone",
    ]
    assert saved_configs[0]["providers"][0]["id"] == "team-gateway"
    assert saved_credentials == [
        (
            "team-gateway",
            "https://relay.example.com/v1",
            "sk-demo",
            "https://relay.example.com/v1",
            "https://relay.example.com/v1",
        )
    ]


def test_run_connect_wizard_tui_escape_cancels_without_text_fallback(monkeypatch):
    import mms_core
    import mms_tui

    messages = []
    cfg = {"providers": []}

    class _Console:
        @staticmethod
        def print(*args, **_kwargs):
            messages.append(" ".join(str(arg) for arg in args))

    class _Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("text fallback prompt should not open after TUI cancel")

    monkeypatch.setattr(mms_core, "_ensure_interactive_terminal", lambda _label: None)
    monkeypatch.setattr(mms_core, "_use_tui", lambda: True)
    monkeypatch.setattr(mms_tui, "select_connect_tui", lambda: None)
    monkeypatch.setattr(mms_core, "console", _Console())
    monkeypatch.setattr(mms_core, "Prompt", _Prompt)

    updated_cfg, changed = mms_core.run_connect_wizard(cfg)

    assert updated_cfg is cfg
    assert changed is False
    assert any("已取消接入" in message for message in messages)


def test_run_connect_wizard_tui_error_still_uses_text_fallback(monkeypatch):
    import mms_core
    import mms_tui

    messages = []

    class _Console:
        @staticmethod
        def print(*args, **_kwargs):
            messages.append(" ".join(str(arg) for arg in args))

    class _Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return "5"

    monkeypatch.setattr(mms_core, "_ensure_interactive_terminal", lambda _label: None)
    monkeypatch.setattr(mms_core, "_use_tui", lambda: True)
    monkeypatch.setattr(mms_tui, "select_connect_tui", lambda: "fallback")
    monkeypatch.setattr(mms_core, "console", _Console())
    monkeypatch.setattr(mms_core, "Prompt", _Prompt)

    _updated_cfg, changed = mms_core.run_connect_wizard({"providers": []})

    assert changed is False
    assert any("接入新通道" in message for message in messages)
