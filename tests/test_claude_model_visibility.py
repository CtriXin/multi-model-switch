from __future__ import annotations


def test_filter_visible_models_hides_claude_family():
    import mms_core

    models = [
        "claude-sonnet-4-6",
        "gpt-5.4",
        "qwen3-coder-plus",
        "claude-opus-4-6",
    ]

    assert mms_core._filter_visible_models(models) == ["gpt-5.4", "qwen3-coder-plus"]


def test_builtin_scene_catalog_keeps_claude_cli_with_non_claude_variants():
    import mms_core

    catalog = mms_core._builtin_scene_catalog()

    assert "主力编码" in catalog
    assert catalog["主力编码"]["cli"] == "claude"
    variants = mms_core._scene_visible_variants(catalog["主力编码"])
    models = [variant["model_info"]["model"] for variant in variants]
    assert "claude-sonnet-4-6" not in models
    assert "gpt-5.3-codex" in models
    assert "glm-5" in models


def test_preset_visibility_hides_claude_only_preset():
    import mms_core

    assert mms_core._preset_has_visible_model_options(
        {
            "cli": "claude",
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        }
    ) is False
    assert mms_core._preset_has_visible_model_options(
        {"cli": "claude", "model": "gpt-5.4"}
    ) is True


def test_aggregate_provider_models_omits_claude_family(monkeypatch):
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

    assert [entry["model"] for entry in aggregated] == ["gpt-5.4", "qwen3-coder-plus"]


def test_build_model_families_for_cli_omits_claude_family(monkeypatch):
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
    assert "Claude" not in family_names
    assert "GPT" in family_names
    assert "Kimi" in family_names
