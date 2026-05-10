from __future__ import annotations


def test_filter_visible_models_keeps_claude_family():
    import mms_core

    models = [
        "claude-sonnet-4-6",
        "gpt-5.4",
        "qwen3-coder-plus",
        "claude-opus-4-6",
    ]

    assert mms_core._filter_visible_models(models) == [
        "claude-sonnet-4-6",
        "gpt-5.4",
        "qwen3-coder-plus",
        "claude-opus-4-6",
    ]


def test_builtin_scene_catalog_keeps_claude_cli_with_claude_and_bridge_variants():
    import mms_core

    catalog = mms_core._builtin_scene_catalog()

    assert "主力编码" in catalog
    assert catalog["主力编码"]["cli"] == "claude"
    variants = mms_core._scene_visible_variants(catalog["主力编码"])
    models = [variant["model_info"]["model"] for variant in variants]
    assert "claude-sonnet-4-6" in models
    assert "gpt-5.3-codex" in models
    assert "glm-5" in models


def test_preset_visibility_keeps_claude_only_preset():
    import mms_core

    assert mms_core._preset_has_visible_model_options(
        {
            "cli": "claude",
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        }
    ) is True
    assert mms_core._preset_has_visible_model_options(
        {"cli": "claude", "model": "gpt-5.4"}
    ) is True


def test_aggregate_provider_models_keeps_claude_family(monkeypatch):
    import mms_core

    provider = {
        "id": "mixed-provider",
        "enabled": True,
        "api_key": "sk-demo",
        "supported_clis": ["claude"],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_provider_has_configured_base_url", lambda _provider: True)
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda _provider, _cached, _cfg=None: ["claude-sonnet-4-6", "gpt-5.4", "qwen3-coder-plus"],
    )
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_provider_label", lambda _provider: "Mixed Provider")

    aggregated = mms_core._aggregate_provider_models({}, "claude", {}, [])

    assert [entry["model"] for entry in aggregated] == [
        "claude-sonnet-4-6",
        "gpt-5.4",
        "qwen3-coder-plus",
    ]


def test_build_model_families_for_cli_keeps_claude_family(monkeypatch):
    import mms_core

    provider = {
        "id": "mixed-provider",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["claude"],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_provider_has_configured_base_url", lambda _provider: True)
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda _provider, _cached, _cfg=None: ["claude-sonnet-4-6", "gpt-5.4", "kimi-k2.5"],
    )
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_provider_label", lambda _provider: "Mixed Provider")
    monkeypatch.setattr(mms_core, "_load_usage_stats", lambda: {"sources": {}})

    families = mms_core._build_model_families_for_cli({}, "claude", {}, [])

    family_names = [entry["family"] for entry in families]
    assert "Claude" in family_names
    assert "GPT" in family_names
    assert "Kimi" in family_names


def test_infer_model_family_recognizes_deepseek():
    import mms_core

    family, category = mms_core._infer_model_family("deepseek-v4-pro")

    assert family == "DeepSeek"
    assert category == "国产系"


def test_build_model_families_for_cli_keeps_deepseek_out_of_other(monkeypatch):
    import mms_core

    provider = {
        "id": "mixed-provider",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["claude"],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_provider_has_configured_base_url", lambda _provider: True)
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda _provider, _cached, _cfg=None: ["deepseek-v4-pro", "qwen3.6-plus"],
    )
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_provider_label", lambda _provider: "Mixed Provider")
    monkeypatch.setattr(mms_core, "_load_usage_stats", lambda: {"sources": {}})

    families = mms_core._build_model_families_for_cli({}, "claude", {}, [])

    family_names = [entry["family"] for entry in families]
    assert "DeepSeek" in family_names
    assert "其他" not in family_names


def test_claude_provider_options_allow_qwen_kimi_anthropic_direct(monkeypatch):
    import mms_core

    relay = {
        "id": "relay",
        "enabled": True,
        "api_key": "sk-relay",
        "role": "auto",
        "priority": 100,
        "supported_clis": ["claude", "qwen", "kimi"],
        "protocols": ["anthropic_messages", "openai_chat_completions"],
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "openai_base_url": "https://relay.example.com/v1",
        "models_endpoint": "manual",
        "fallback_models": ["qwen3.5-plus", "kimi-for-coding"],
    }
    direct_qwen = {
        "id": "direct-qwen",
        "enabled": True,
        "api_key": "sk-qwen",
        "role": "fallback",
        "priority": 200,
        "supported_clis": ["claude"],
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://coding.dashscope.aliyuncs.com/apps/anthropic",
        "models_endpoint": "manual",
        "fallback_models": ["qwen3.5-plus"],
    }
    direct_kimi = {
        "id": "direct-kimi",
        "enabled": True,
        "api_key": "sk-kimi",
        "role": "fallback",
        "priority": 200,
        "supported_clis": ["claude"],
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://api.kimi.com/coding/",
        "models_endpoint": "manual",
        "fallback_models": ["kimi-for-coding"],
    }
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args, **_kwargs: [(relay, None), (direct_qwen, None), (direct_kimi, None)],
    )
    monkeypatch.setattr(mms_core, "_account_options_for_model", lambda *_args, **_kwargs: [])

    options = mms_core._build_provider_options_map(
        {},
        "claude",
        relay,
        [],
        ["qwen3.5-plus", "kimi-for-coding"],
    )

    assert [item["provider_id"] for item in options["qwen3.5-plus"]] == ["relay", "direct-qwen"]
