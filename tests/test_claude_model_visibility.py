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


def test_default_mms_hides_openrouter_private_opus():
    import mms_core

    assert mms_core._mms_model_visible("anthropic/claude-opus-4.7") is False
    assert mms_core._filter_visible_models(["anthropic/claude-opus-4.7", "claude-opus-4-6"]) == [
        "claude-opus-4-6"
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


def test_cold_cache_provider_uses_configured_fallback_models(monkeypatch):
    import mms_core

    scheduled = []
    provider = {
        "id": "cold-relay",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["claude"],
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "models_endpoint": "/models",
        "fallback_models": ["qwen3.6-plus", "kimi-for-coding"],
    }
    monkeypatch.setattr(
        mms_core,
        "_schedule_probe_refresh",
        lambda runtime, _cfg=None, reason="": scheduled.append((runtime["id"], reason)) or True,
    )

    assert mms_core._provider_effective_models(provider, None, {}) == [
        "qwen3.6-plus",
        "kimi-for-coding",
    ]
    assert scheduled == [("cold-relay", "cache_miss")]


def test_cold_cache_provider_fallback_models_keep_qwen_kimi_families(monkeypatch):
    import mms_core

    provider = {
        "id": "cold-relay",
        "enabled": True,
        "api_key": "sk-demo",
        "role": "auto",
        "supported_clis": ["claude"],
        "protocols": ["anthropic_messages"],
        "anthropic_base_url": "https://relay.example.com/anthropic",
        "models_endpoint": "/models",
        "fallback_models": ["qwen3.6-plus", "kimi-for-coding"],
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_schedule_probe_refresh", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(mms_core, "_load_usage_stats", lambda: {"sources": {}})

    families = mms_core._build_model_families_for_cli({}, "claude", {}, [])

    family_names = [entry["family"] for entry in families]
    assert "Qwen" in family_names
    assert "Kimi" in family_names


def test_cold_cache_provider_without_static_models_stays_empty(monkeypatch):
    import mms_core

    scheduled = []
    provider = {
        "id": "remote-only",
        "enabled": True,
        "models_endpoint": "/models",
    }
    monkeypatch.setattr(
        mms_core,
        "_schedule_probe_refresh",
        lambda runtime, _cfg=None, reason="": scheduled.append((runtime["id"], reason)) or True,
    )

    assert mms_core._provider_effective_models(provider, None, {}) == []
    assert scheduled == [("remote-only", "cache_miss")]


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
    assert [item["provider_id"] for item in options["kimi-for-coding"]] == ["relay", "direct-kimi"]


def test_qwen_and_kimi_models_bridge_through_claude_not_direct_cli():
    import mms_core

    provider = {
        "id": "mixed-provider",
        "enabled": True,
        "api_key": "sk-demo",
        "supported_clis": ["claude"],
    }

    assert mms_core._native_clis_for_model("qwen3-coder-plus") == []
    assert mms_core._native_clis_for_model("kimi-k2.5") == []
    assert mms_core._provider_supports_model_for_cli(provider, "claude", "qwen3-coder-plus") is True
    assert mms_core._provider_supports_model_for_cli(provider, "claude", "kimi-k2.5") is True


def test_legacy_qwen_kimi_supported_clis_are_normalized_to_real_clis():
    import mms_core

    normalized = mms_core.resolve_provider_context(
        {
            "providers": [
                {
                    "id": "legacy",
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["qwen", "kimi"],
                }
            ]
        },
        "legacy",
    )

    assert normalized["supported_clis"] == ["claude", "codex"]


def test_runtime_with_vision_sidecar_auto_uses_direct_kimi(monkeypatch):
    import mms_core

    cfg = {"providers": [{"id": "direct-kimi", "enabled": True}]}
    direct_kimi = {
        "id": "direct-kimi",
        "enabled": True,
        "api_key": "sk-kimi",
        "anthropic_base_url": "https://api.kimi.com/coding/",
        "supported_clis": ["claude"],
        "models_endpoint": "manual",
        "fallback_models": ["K2.6"],
    }
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _cfg, _pid: direct_kimi)
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda *_args, **_kwargs: None)

    runtime = mms_core._runtime_with_vision_sidecar(cfg, {"id": "mimo", "auth_mode": "api_key"})

    assert runtime["vision_sidecar"]["provider_id"] == "direct-kimi"
    assert runtime["vision_sidecar"]["model"] == "K2.6"
    assert runtime["vision_sidecar"]["anthropic_base_url"] == "https://api.kimi.com/coding"


def test_runtime_with_vision_sidecar_prefers_direct_mimo_before_kimi(monkeypatch):
    import mms_core

    cfg = {
        "providers": [
            {"id": "mimo-direct-anthropic", "enabled": True},
            {"id": "direct-kimi", "enabled": True},
        ]
    }
    providers = {
        "mimo-direct-anthropic": {
            "id": "mimo-direct-anthropic",
            "enabled": True,
            "api_key": "sk-mimo",
            "anthropic_base_url": "https://token-plan-cn.xiaomimimo.com/anthropic/",
            "supported_clis": ["claude"],
        },
        "direct-kimi": {
            "id": "direct-kimi",
            "enabled": True,
            "api_key": "sk-kimi",
            "anthropic_base_url": "https://api.kimi.com/coding/",
            "supported_clis": ["claude"],
        },
    }
    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _cfg, pid: providers[pid])
    monkeypatch.setattr(mms_core, "_load_probe_file_cache", lambda *_args, **_kwargs: None)

    runtime = mms_core._runtime_with_vision_sidecar(cfg, {"id": "glm", "auth_mode": "api_key"})

    assert runtime["vision_sidecar"]["provider_id"] == "mimo-direct-anthropic"
    assert runtime["vision_sidecar"]["model"] == "mimo-v2.5"
    assert runtime["vision_sidecar"]["anthropic_base_url"] == "https://token-plan-cn.xiaomimimo.com/anthropic"


def test_confirm_context_lines_show_claude_vision_sidecar():
    import mms_core

    lines = mms_core._confirm_context_lines(
        "claude",
        {
            "id": "mimo",
            "auth_mode": "api_key",
            "vision_sidecar": {
                "enabled": True,
                "provider_id": "mimo-direct-anthropic",
                "model": "mimo-v2.5",
            },
        },
    )

    assert ("Vision", "mimo-direct-anthropic/mimo-v2.5") in lines
