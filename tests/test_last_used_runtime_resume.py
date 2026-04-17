from __future__ import annotations


def test_record_usage_persists_runtime_hint(monkeypatch):
    import mms_core

    saved = {}

    def _fake_update_usage_stats(mutator):
        stats = {"sources": {}, "last_by_cli": {}}
        mutator(stats)
        saved.update(stats)

    monkeypatch.setattr(mms_core, "_update_usage_stats", _fake_update_usage_stats)
    monkeypatch.setattr(mms_core, "_iso_now", lambda: "2026-04-15T18:00:00Z")

    runtime = {
        "id": "preferred-provider",
        "name": "Preferred Provider",
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "priority": 100,
    }

    mms_core._record_usage(runtime, "claude", {"model": "gpt-5.4"})

    assert saved["last_by_cli"]["claude"]["runtime_hint"] == {
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "provider_id": "preferred-provider",
        "runtime_id": "preferred-provider",
    }


def test_resolve_last_used_runtime_prefers_saved_provider(monkeypatch):
    import mms_core

    contexts = {
        "preferred-provider": {
            "id": "preferred-provider",
            "name": "Preferred Provider",
            "runtime_kind": "provider",
            "auth_mode": "api_key",
            "priority": 100,
            "supported_clis": ["claude"],
            "base_url": "https://preferred.example.com",
            "api_key": "sk-preferred",
            "models": ["gpt-5.4"],
        },
        "xin": {
            "id": "xin",
            "name": "Xin",
            "runtime_kind": "provider",
            "auth_mode": "api_key",
            "priority": 200,
            "supported_clis": ["claude"],
            "base_url": "https://xin.example.com",
            "api_key": "sk-xin",
            "models": ["gpt-5.4"],
        },
    }

    monkeypatch.setattr(mms_core, "resolve_provider_context", lambda _cfg, provider_id=None: dict(contexts[provider_id]))
    monkeypatch.setattr(mms_core, "_probe_models", lambda provider, emit_output=False: {"models": list(provider.get("models", []))})
    monkeypatch.setattr(mms_core, "_provider_supports_model_for_cli", lambda provider, cli_name, model_name=None: True)
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda provider, cached_models, _cfg: list(cached_models or provider.get("models", [])),
    )

    last_item = {
        "cli": "claude",
        "model": "gpt-5.4",
        "model_info": {"model": "gpt-5.4"},
        "runtime_hint": {
            "runtime_kind": "provider",
            "auth_mode": "api_key",
            "provider_id": "preferred-provider",
            "runtime_id": "preferred-provider",
        },
    }

    runtime, models, choice = mms_core._resolve_last_used_runtime({}, "claude", last_item, ["gpt-5.4"])

    assert runtime["id"] == "preferred-provider"
    assert models == ["gpt-5.4"]
    assert choice == "last used provider:preferred-provider"


def test_get_scene_usage_backfills_runtime_hint_from_sources(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_usage_stats",
        lambda: {
            "sources": {
                "provider:claude:preferred-provider": {
                    "runtime_kind": "provider",
                    "id": "preferred-provider",
                    "cli": "claude",
                    "last_used_at": "2026-04-15T18:05:00Z",
                    "last_model": "gpt-5.4",
                },
                "provider:claude:xin": {
                    "runtime_kind": "provider",
                    "id": "xin",
                    "cli": "claude",
                    "last_used_at": "2026-04-15T18:00:00Z",
                    "last_model": "gpt-5.4",
                },
            },
            "last_by_cli": {
                "claude": {
                    "cli": "claude",
                    "model": "gpt-5.4",
                    "model_info": {"model": "gpt-5.4"},
                    "last_used_at": "2026-04-15T18:05:00Z",
                }
            },
        },
    )

    last_by_cli, scene_counts = mms_core._get_scene_usage()

    assert scene_counts == {}
    assert last_by_cli["claude"]["runtime_hint"] == {
        "runtime_kind": "provider",
        "runtime_id": "preferred-provider",
        "auth_mode": "api_key",
        "provider_id": "preferred-provider",
    }
