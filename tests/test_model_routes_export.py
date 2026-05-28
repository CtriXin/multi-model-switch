from __future__ import annotations

import json
import os
import re
import stat

import pytest


def _write_latest_approved_route_bundle(tmp_path, mms_router, *, routes):
    import mms_registry

    generated = tmp_path / "generated"
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    mms_registry.write_json_atomic(router, {"version": 1, "generated_at": "2026-05-23T00:00:00.000Z", "routes": routes})
    router_payload = json.loads(router.read_text(encoding="utf-8"))
    mms_registry.write_json_atomic(
        lineup,
        {
            "version": 1,
            "generated_at": "2026-05-23T00:00:00.000Z",
            "source_routes_hash": mms_router._content_hash({"version": 1, "routes": router_payload["routes"]}),
            "routes": {
                name: {"primary": {"provider_id": info["primary"]["provider_id"], "model_id": name}, "fallbacks": []}
                for name, info in routes.items()
            },
        },
    )
    mms_registry.write_json_atomic(profile, {"schema_version": 1, "profiles": {}})
    mms_registry.write_json_atomic(policy, {"version": 1, "models": {}})
    mms_registry.export_latest_approved_bundle_manifest(
        generated / "model-registry.latest-approved.json",
        bundle_revision="bundle_route_test_001",
        capability_revision="cap_route_test_001",
        route_revision="route_test_001",
        policy_revision="policy_test_001",
        profile_revision="profile_test_001",
        generated_at="2026-05-23T00:00:00.000Z",
        files={
            "router": {
                "path": router,
                "canonical_path": "generated/model-routes.json",
                "legacy_alias_path": "model-routes.json",
                "sensitivity": "secret",
                "legacy_alias_compat": True,
            },
            "lineup": {
                "path": lineup,
                "canonical_path": "generated/model-routes.lineup.json",
                "legacy_alias_path": "model-routes.lineup.json",
                "sensitivity": "non-secret",
                "legacy_alias_compat": True,
            },
            "profile": {
                "path": profile,
                "canonical_path": "generated/provider-profiles.generated.json",
                "sensitivity": "non-secret",
                "legacy_alias_compat": False,
            },
            "policy": {
                "path": policy,
                "canonical_path": "generated/model-policy.effective.json",
                "legacy_alias_path": "model-policy.json",
                "sensitivity": "non-secret",
                "legacy_alias_compat": True,
            },
        },
    )


def _patch_export_dependencies(monkeypatch, *, contexts):
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "resolve_provider_context",
        lambda _cfg, provider_id: dict(contexts[provider_id]),
    )
    monkeypatch.setattr(
        mms_core,
        "_probe_models",
        lambda ctx, emit_output=False: {"models": list(ctx.get("models", []))},
    )
    monkeypatch.setattr(
        mms_core,
        "_probe_models_for_startup",
        lambda _cfg, ctx, emit_output=False: {"models": list(ctx.get("models", []))},
    )
    monkeypatch.setattr(
        mms_core,
        "_provider_effective_models",
        lambda provider_def, cached_models, _cfg: list(cached_models or provider_def.get("models", [])),
    )
    monkeypatch.setattr(mms_core, "_provider_label", lambda ctx: str(ctx.get("provider_name") or ctx.get("id") or "provider"))


def _patch_export_paths(monkeypatch, tmp_path):
    import mms_router

    monkeypatch.setattr(mms_router, "MODEL_ROUTES_PATH", str(tmp_path / "model-routes.json"))
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_LINEUP_PATH", str(tmp_path / "model-routes.lineup.json"))
    monkeypatch.setattr(mms_router, "MODEL_POLICY_PATH", str(tmp_path / "model-policy.json"))
    monkeypatch.setattr(mms_router, "MODEL_CONFIG_AUDIT_PATH", str(tmp_path / "model-config.audit.ndjson"))
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_SNAPSHOTS_DIR", str(tmp_path / "model-routes.snapshots"))
    monkeypatch.setattr(mms_router, "MODEL_ROUTES_LINEUP_SNAPSHOTS_DIR", str(tmp_path / "model-routes.lineup.snapshots"))


def test_export_model_routes_writes_minimal_hive_contract_and_snapshot(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "kimi-direct": {
                "id": "kimi-direct",
                "provider_name": "Kimi Direct",
                "anthropic_base_url": "https://kimi.example.com/anthropic",
                "openai_base_url": "",
                "api_key": "sk-kimi",
                "models": ["kimi-k2.5"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "kimi-direct"},
        "providers": [
            {
                "id": "kimi-direct",
                "role": "auto",
                "priority": 75,
                "enabled": True,
                "protocols": ["anthropic_messages"],
                "supported_clis": ["kimi"],
                "models": ["kimi-k2.5"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["kimi-k2.5"]
    assert list(info) == ["primary", "fallbacks"]
    assert info["primary"] == {
        "provider_id": "kimi-direct",
        "anthropic_base_url": "https://kimi.example.com/anthropic",
        "openai_base_url": "",
        "api_key": "sk-kimi",
        "model_id": "kimi-k2.5",
    }
    assert info["fallbacks"] == []

    latest_path = tmp_path / "model-routes.json"
    written = json.loads(latest_path.read_text(encoding="utf-8"))
    assert list(written) == ["version", "generated_at", "routes"]
    assert written["version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", written["generated_at"])
    assert list(written["routes"]["kimi-k2.5"]) == ["primary", "fallbacks"]
    assert list(written["routes"]["kimi-k2.5"]["primary"]) == [
        "provider_id",
        "anthropic_base_url",
        "openai_base_url",
        "api_key",
        "model_id",
    ]

    lineup = json.loads((tmp_path / "model-routes.lineup.json").read_text(encoding="utf-8"))
    assert list(lineup) == ["version", "generated_at", "source_routes_hash", "routes"]
    assert lineup["routes"]["kimi-k2.5"]["primary"]["provider_id"] == "kimi-direct"
    assert lineup["routes"]["kimi-k2.5"]["primary"]["model_id"] == "kimi-k2.5"
    assert "api_key" not in lineup["routes"]["kimi-k2.5"]["primary"]
    assert (tmp_path / "model-policy.json").exists()
    assert (tmp_path / "model-config.audit.ndjson").exists()

    snapshots = sorted((tmp_path / "model-routes.snapshots").glob("*.json"))
    assert len(snapshots) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", snapshots[0].stem)
    assert json.loads(snapshots[0].read_text(encoding="utf-8")) == written
    assert stat.S_IMODE(latest_path.stat().st_mode) == 0o600


def test_export_model_routes_prefers_verified_latest_approved_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_router

    _patch_export_paths(monkeypatch, tmp_path)
    approved_routes = {
        "approved-model": {
            "primary": {
                "provider_id": "approved-provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://approved.example/v1",
                "api_key": "sk-approved",
                "model_id": "approved-model",
            },
            "fallbacks": [],
        }
    }
    _write_latest_approved_route_bundle(tmp_path, mms_router, routes=approved_routes)

    routes = mms_router.export_model_routes({"providers": []}, force=False)

    assert routes == approved_routes
    assert not (tmp_path / "model-routes.snapshots").exists()


def test_validate_model_config_bundle_uses_verified_latest_approved_or_legacy_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_router

    _patch_export_paths(monkeypatch, tmp_path)
    bad_root = {
        "version": 1,
        "routes": {
            "bad-root": {
                "primary": {"provider_id": "bad-root", "openai_base_url": "https://bad.example/v1", "api_key": ""},
                "fallbacks": [],
            }
        },
    }
    (tmp_path / "model-routes.json").write_text(json.dumps(bad_root), encoding="utf-8")
    (tmp_path / "model-routes.lineup.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_routes_hash": mms_router._content_hash({"version": 1, "routes": bad_root["routes"]}),
                "routes": {"bad-root": {"primary": {"provider_id": "bad-root"}, "fallbacks": []}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "model-policy.json").write_text(json.dumps({"version": 1, "models": {}}), encoding="utf-8")
    approved_routes = {
        "approved-model": {
            "primary": {
                "provider_id": "approved-provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://approved.example/v1",
                "api_key": "sk-approved",
                "model_id": "approved-model",
            },
            "fallbacks": [],
        }
    }
    _write_latest_approved_route_bundle(tmp_path, mms_router, routes=approved_routes)

    assert not [item for item in mms_router.validate_model_config_bundle() if item.get("level") == "error"]

    (tmp_path / "generated" / "model-routes.json").write_text(json.dumps({"version": 1, "routes": {}}), encoding="utf-8")
    error_codes = {item["code"] for item in mms_router.validate_model_config_bundle() if item.get("level") == "error"}
    assert "latest_approved_invalid" in error_codes
    assert "route_missing_primary_provider" not in error_codes
    assert "route_missing_api_key" not in error_codes


def test_export_model_routes_fails_closed_on_invalid_latest_approved_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    import mms_router

    _patch_export_paths(monkeypatch, tmp_path)
    stale_root = {
        "version": 1,
        "routes": {
            "stale-root": {
                "primary": {
                    "provider_id": "stale-root",
                    "openai_base_url": "https://stale.example/v1",
                    "api_key": "sk-stale",
                },
                "fallbacks": [],
            }
        },
    }
    (tmp_path / "model-routes.json").write_text(json.dumps(stale_root), encoding="utf-8")
    (tmp_path / "model-routes.lineup.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_routes_hash": mms_router._content_hash({"version": 1, "routes": stale_root["routes"]}),
                "routes": {"stale-root": {"primary": {"provider_id": "stale-root"}, "fallbacks": []}},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "model-policy.json").write_text(json.dumps({"version": 1, "models": {}}), encoding="utf-8")
    approved_routes = {
        "approved-model": {
            "primary": {
                "provider_id": "approved-provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://approved.example/v1",
                "api_key": "sk-approved",
                "model_id": "approved-model",
            },
            "fallbacks": [],
        }
    }
    _write_latest_approved_route_bundle(tmp_path, mms_router, routes=approved_routes)
    (tmp_path / "generated" / "model-routes.json").write_text(json.dumps({"version": 1, "routes": {}}), encoding="utf-8")

    routes = mms_router.export_model_routes({"providers": []}, force=False)

    assert routes == {}


def test_export_model_routes_reuses_snapshot_when_content_unchanged(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "qwen-openai": {
                "id": "qwen-openai",
                "provider_name": "Qwen OpenAI",
                "anthropic_base_url": "",
                "openai_base_url": "https://qwen.example.com/v1",
                "api_key": "sk-qwen",
                "models": ["qwen3.5-plus"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "qwen-openai"},
        "providers": [
            {
                "id": "qwen-openai",
                "role": "auto",
                "priority": 60,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3.5-plus"],
            }
        ],
    }

    first_routes = mms_router.export_model_routes(cfg, force=True)
    first_written = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))

    second_routes = mms_router.export_model_routes(cfg, force=True)
    second_written = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))

    assert second_routes == first_routes
    assert second_written["generated_at"] == first_written["generated_at"]
    assert len(list((tmp_path / "model-routes.snapshots").glob("*.json"))) == 1


def test_export_model_routes_refreshes_profile_lineup_metadata_without_secrets(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "deepseek-direct": {
                "id": "deepseek-direct",
                "provider_name": "DeepSeek Direct",
                "anthropic_base_url": "https://api.deepseek.com/anthropic",
                "openai_base_url": "https://api.deepseek.com",
                "api_key": "sk-deepseek",
                "models": ["deepseek-v4-pro"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_router, "_route_context_window", lambda _model, _route: 1000000)
    monkeypatch.setattr(mms_router, "_profile_reference_urls", lambda _model, _route: ["https://api-docs.deepseek.com/"])
    (tmp_path / "model-routes.lineup.json").write_text(json.dumps({
        "version": 1,
        "routes": {
            "deepseek-v4-pro": {
                "display_name": "Main DeepSeek",
                "primary": {
                    "max_context_tokens": 654321,
                    "context_reference_url": "https://docs.example/context",
                    "api_key": "must-not-survive",
                    "openai_base_url": "https://must-not-survive",
                },
                "fallbacks": []
            }
        }
    }), encoding="utf-8")

    cfg = {
        "provider": {"default": "deepseek-direct"},
        "providers": [
            {
                "id": "deepseek-direct",
                "role": "auto",
                "priority": 60,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["codex"],
                "models": ["deepseek-v4-pro"],
            }
        ],
    }

    mms_router.export_model_routes(cfg, force=True)

    lineup = json.loads((tmp_path / "model-routes.lineup.json").read_text(encoding="utf-8"))
    entry = lineup["routes"]["deepseek-v4-pro"]
    assert entry["display_name"] == "Main DeepSeek"
    assert entry["primary"]["max_context_tokens"] == 1000000
    assert entry["primary"]["context_reference_url"] == "https://api-docs.deepseek.com/"
    assert entry["primary"]["context_source"] == "provider-profiles.json"
    assert "api_key" not in entry["primary"]
    assert "openai_base_url" not in entry["primary"]


def test_latest_routes_freshness_tracks_provider_profiles(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    _patch_export_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(tmp_path / "missing-config.toml"))
    monkeypatch.setattr(mms_core, "CREDENTIALS_PATH", str(tmp_path / "missing-credentials.sh"))
    monkeypatch.setattr(mms_core, "OVERRIDE_PATHS", [])
    monkeypatch.setattr(mms_router, "_BUILTIN_PROVIDER_PROFILE_PATH", str(tmp_path / "provider-profiles.json"))
    routes = {
        "demo": {
            "primary": {
                "provider_id": "demo",
                "anthropic_base_url": "",
                "openai_base_url": "https://demo.example/v1",
                "api_key": "sk-demo",
                "model_id": "demo",
            },
            "fallbacks": []
        }
    }
    route_payload = {"version": 1, "generated_at": "2026-05-08T00:00:00.000Z", "routes": routes}
    lineup_payload = {
        "version": 1,
        "generated_at": "2026-05-08T00:00:00.000Z",
        "source_routes_hash": mms_router._content_hash({"version": 1, "routes": routes}),
        "routes": {"demo": {"primary": {"provider_id": "demo", "model_id": "demo"}, "fallbacks": []}},
    }
    (tmp_path / "model-routes.json").write_text(json.dumps(route_payload), encoding="utf-8")
    (tmp_path / "model-routes.lineup.json").write_text(json.dumps(lineup_payload), encoding="utf-8")
    profile_path = tmp_path / "provider-profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    old_time = 1_700_000_000
    new_time = old_time + 10
    for path in (tmp_path / "model-routes.json", tmp_path / "model-routes.lineup.json"):
        os.utime(path, (old_time, old_time))
    os.utime(profile_path, (new_time, new_time))

    assert mms_router._latest_routes_is_fresh() is False


def test_validate_model_config_bundle_errors_on_bad_lineup_and_fallback():
    import mms_router

    routes = {
        "version": 1,
        "routes": {
            "demo": {
                "primary": {
                    "provider_id": "demo",
                    "openai_base_url": "https://demo.example/v1",
                    "api_key": "sk-demo",
                },
                "fallbacks": [{
                    "provider_id": "fallback",
                    "openai_base_url": "https://fallback.example/v1",
                    "api_key": "",
                }],
            }
        },
    }
    lineup = {
        "version": 1,
        "source_routes_hash": mms_router._content_hash({"version": 1, "routes": routes["routes"]}),
        "routes": {
            "demo": {"primary": {"provider_id": "demo"}, "fallbacks": [{"provider_id": "fallback"}]},
            "ghost": {"primary": {"provider_id": "ghost"}, "fallbacks": []},
        },
    }

    issues = mms_router.validate_model_config_bundle(routes, lineup, {"models": {}, "projects": {}})
    error_codes = {item["code"] for item in issues if item.get("level") == "error"}
    assert "fallback_missing_api_key" in error_codes
    assert "lineup_extra_model" in error_codes


def test_validate_model_config_bundle_allows_stale_hidden_policy_entries():
    import mms_router

    routes = {
        "version": 1,
        "routes": {
            "demo": {
                "primary": {
                    "provider_id": "demo",
                    "openai_base_url": "https://demo.example/v1",
                    "api_key": "sk-demo",
                },
                "fallbacks": [],
            }
        },
    }
    lineup = {
        "version": 1,
        "source_routes_hash": mms_router._content_hash({"version": 1, "routes": routes["routes"]}),
        "routes": {"demo": {"primary": {"provider_id": "demo"}, "fallbacks": []}},
    }
    policy = {
        "models": {},
        "projects": {
            "mms": {
                "hidden_models": ["retired-hidden"],
                "disabled_models": ["retired-disabled"],
                "allowed_models": ["missing-allowed"],
                "favorite_models": ["missing-favorite"],
            }
        },
    }

    issues = mms_router.validate_model_config_bundle(routes, lineup, policy)
    warnings = [item for item in issues if item.get("level") == "warning"]

    assert {item["model"] for item in warnings} == {"missing-allowed", "missing-favorite"}


def test_export_model_routes_creates_new_snapshot_when_key_changes(monkeypatch, tmp_path):
    import mms_router

    contexts = {
        "qwen-openai": {
            "id": "qwen-openai",
            "provider_name": "Qwen OpenAI",
            "anthropic_base_url": "",
            "openai_base_url": "https://qwen.example.com/v1",
            "api_key": "sk-qwen-old",
            "models": ["qwen3.5-plus"],
        }
    }
    _patch_export_dependencies(monkeypatch, contexts=contexts)
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "qwen-openai"},
        "providers": [
            {
                "id": "qwen-openai",
                "role": "auto",
                "priority": 60,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3.5-plus"],
            }
        ],
    }

    mms_router.export_model_routes(cfg, force=True)
    contexts["qwen-openai"]["api_key"] = "sk-qwen-new"
    mms_router.export_model_routes(cfg, force=True)

    latest = json.loads((tmp_path / "model-routes.json").read_text(encoding="utf-8"))
    snapshots = sorted((tmp_path / "model-routes.snapshots").glob("*.json"))

    assert latest["routes"]["qwen3.5-plus"]["primary"]["api_key"] == "sk-qwen-new"
    assert len(snapshots) == 2


def test_export_model_routes_keeps_only_minimal_fields_for_hive(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "openai-relay-high-priority": {
                "id": "openai-relay-high-priority",
                "provider_name": "OpenAI Relay",
                "anthropic_base_url": "https://crs.example.com/openai",
                "openai_base_url": "https://crs.example.com/openai",
                "api_key": "sk-relay",
                "models": ["kimi-k2.5"],
            },
            "kimi-direct-compatible": {
                "id": "kimi-direct-compatible",
                "provider_name": "Kimi Direct",
                "anthropic_base_url": "https://kimi.example.com/anthropic",
                "openai_base_url": "https://kimi.example.com/v1",
                "api_key": "sk-kimi",
                "models": ["kimi-k2.5"],
            },
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "openai-relay-high-priority"},
        "providers": [
            {
                "id": "openai-relay-high-priority",
                "role": "auto",
                "priority": 110,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["codex"],
                "models": ["kimi-k2.5"],
            },
            {
                "id": "kimi-direct-compatible",
                "role": "auto",
                "priority": 100,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["kimi"],
                "models": ["kimi-k2.5"],
            },
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["kimi-k2.5"]
    assert list(info["primary"]) == ["provider_id", "anthropic_base_url", "openai_base_url", "api_key", "model_id"]
    assert info["primary"]["provider_id"] == "openai-relay-high-priority"
    assert info["fallbacks"][0]["provider_id"] == "kimi-direct-compatible"
    assert "priority" not in info["primary"]
    assert "role" not in info["primary"]


def test_export_model_routes_prefers_higher_priority_before_default_provider(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "default-low-priority": {
                "id": "default-low-priority",
                "provider_name": "Default Low",
                "anthropic_base_url": "",
                "openai_base_url": "https://default.example.com/v1",
                "api_key": "sk-default",
                "models": ["qwen3-coder-plus"],
            },
            "high-priority": {
                "id": "high-priority",
                "provider_name": "High Priority",
                "anthropic_base_url": "",
                "openai_base_url": "https://high.example.com/v1",
                "api_key": "sk-high",
                "models": ["qwen3-coder-plus"],
            },
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "default-low-priority"},
        "providers": [
            {
                "id": "default-low-priority",
                "role": "auto",
                "priority": 10,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
            {
                "id": "high-priority",
                "role": "auto",
                "priority": 90,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    info = routes["qwen3-coder-plus"]
    assert info["primary"]["provider_id"] == "high-priority"
    assert info["fallbacks"][0]["provider_id"] == "default-low-priority"


def test_export_model_routes_keeps_gemini_models_for_gemini_provider(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "us-cpa-local-gemini": {
                "id": "us-cpa-local-gemini",
                "provider_name": "US CPA Gemini",
                "anthropic_base_url": "http://127.0.0.1:18417/v1",
                "openai_base_url": "http://127.0.0.1:18417/v1",
                "api_key": "sk-gemini",
                "models": ["gemini-3.1-pro-preview"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "us-cpa-local-gemini"},
        "providers": [
            {
                "id": "us-cpa-local-gemini",
                "role": "auto",
                "priority": 80,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["gemini"],
                "models": ["gemini-3.1-pro-preview"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    assert routes["gemini-3.1-pro-preview"]["primary"]["provider_id"] == "us-cpa-local-gemini"
    assert routes["gemini-3.1-pro-preview"]["fallbacks"] == []


def test_export_model_routes_keeps_antigravity_bridge_models(monkeypatch, tmp_path):
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "us-cpa-local-antigravity": {
                "id": "us-cpa-local-antigravity",
                "provider_name": "US CPA Antigravity",
                "anthropic_base_url": "http://127.0.0.1:18617/v1",
                "openai_base_url": "http://127.0.0.1:18617/v1",
                "api_key": "sk-antigravity",
                "models": [
                    "gemini-3-flash-agent(high)",
                    "gemini-3.1-flash-lite",
                    "gemini-3.1-pro-low",
                    "claude-opus-4-6-thinking",
                    "claude-sonnet-4-6",
                ],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    cfg = {
        "provider": {"default": "us-cpa-local-antigravity"},
        "providers": [
            {
                "id": "us-cpa-local-antigravity",
                "role": "fallback",
                "priority": 210,
                "enabled": True,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["claude", "codex"],
                "models": [
                    "gemini-3-flash-agent(high)",
                    "gemini-3.1-flash-lite",
                    "gemini-3.1-pro-low",
                    "claude-opus-4-6-thinking",
                    "claude-sonnet-4-6",
                ],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True)

    assert routes["gemini-3-flash-agent(high)"]["primary"]["provider_id"] == "us-cpa-local-antigravity"
    assert routes["gemini-3.1-flash-lite"]["primary"]["provider_id"] == "us-cpa-local-antigravity"
    assert routes["gemini-3.1-pro-low"]["primary"]["provider_id"] == "us-cpa-local-antigravity"
    assert routes["claude-opus-4-6-thinking"]["primary"]["provider_id"] == "us-cpa-local-antigravity"
    assert routes["claude-sonnet-4-6"]["primary"]["provider_id"] == "us-cpa-local-antigravity"


def test_export_model_routes_uses_startup_safe_probe_when_requested(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    calls = []
    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "startup-safe-provider": {
                "id": "startup-safe-provider",
                "provider_name": "Startup Safe Provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://startup.example.com/v1",
                "api_key": "sk-startup",
                "models": ["qwen3-coder-plus"],
            }
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        mms_core,
        "_probe_models",
        lambda ctx, emit_output=False: calls.append(("live", ctx["id"])) or {"models": ["should-not-be-used"]},
    )
    monkeypatch.setattr(
        mms_core,
        "_probe_models_for_startup",
        lambda _cfg, ctx, emit_output=False: calls.append(("startup", ctx["id"])) or {"models": list(ctx.get("models", []))},
    )

    cfg = {
        "provider": {"default": "startup-safe-provider"},
        "providers": [
            {
                "id": "startup-safe-provider",
                "role": "auto",
                "priority": 80,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            }
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True, startup_safe=True)

    assert routes["qwen3-coder-plus"]["primary"]["provider_id"] == "startup-safe-provider"
    assert calls == [("startup", "startup-safe-provider")]


def test_export_model_routes_skips_provider_when_startup_probe_raises(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    _patch_export_dependencies(
        monkeypatch,
        contexts={
            "broken-provider": {
                "id": "broken-provider",
                "provider_name": "Broken Provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://broken.example.com/v1",
                "api_key": "sk-broken",
                "models": ["qwen3-coder-plus"],
            },
            "healthy-provider": {
                "id": "healthy-provider",
                "provider_name": "Healthy Provider",
                "anthropic_base_url": "",
                "openai_base_url": "https://healthy.example.com/v1",
                "api_key": "sk-healthy",
                "models": ["qwen3-coder-plus"],
            },
        },
    )
    _patch_export_paths(monkeypatch, tmp_path)

    def _startup_probe(_cfg, ctx, emit_output=False):
        if ctx["id"] == "broken-provider":
            raise RuntimeError("boom")
        return {"models": list(ctx.get("models", []))}

    monkeypatch.setattr(mms_core, "_probe_models_for_startup", _startup_probe)

    cfg = {
        "provider": {"default": "broken-provider"},
        "providers": [
            {
                "id": "broken-provider",
                "role": "auto",
                "priority": 100,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
            {
                "id": "healthy-provider",
                "role": "auto",
                "priority": 90,
                "enabled": True,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["qwen"],
                "models": ["qwen3-coder-plus"],
            },
        ],
    }

    routes = mms_router.export_model_routes(cfg, force=True, startup_safe=True)

    assert routes["qwen3-coder-plus"]["primary"]["provider_id"] == "healthy-provider"
    assert routes["qwen3-coder-plus"]["fallbacks"] == []


def test_save_provider_credentials_triggers_routes_export(monkeypatch, tmp_path):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_core, "CREDENTIALS_PATH", str(tmp_path / "credentials.sh"))
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)) or {},
    )

    mms_core.save_provider_credentials("demo", "https://demo.example.com/v1", "sk-demo")

    assert (tmp_path / "credentials.sh").exists()
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True, False)
    ]


def test_refresh_routes_export_for_hive_loads_current_config(monkeypatch):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)) or {},
    )

    assert mms_core._refresh_routes_export_for_hive(force=True, quiet=True) is True
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True, False)
    ]


def test_refresh_routes_export_for_hive_supports_startup_safe_probe(monkeypatch):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)) or {},
    )

    assert mms_core._refresh_routes_export_for_hive(force=True, quiet=True, startup_safe=True) is True
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True, True)
    ]


def test_refresh_routes_export_for_hive_skips_startup_safe_probe_for_preview(monkeypatch):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "_config_root_status", lambda: {"mode": "preview"})
    monkeypatch.setattr(
        mms_core,
        "load_config",
        lambda: (_ for _ in ()).throw(AssertionError("preview startup route export must not load legacy config")),
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)) or {},
    )

    assert mms_core._refresh_routes_export_for_hive(force=True, quiet=True, startup_safe=True) is True
    assert calls == []


def test_refresh_routes_export_for_hive_allows_explicit_preview_legacy_export(monkeypatch):
    import mms_core
    import mms_router

    calls = []
    monkeypatch.setattr(mms_core, "_config_root_status", lambda: {"mode": "preview"})
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(
        mms_core,
        "apply_local_overrides",
        lambda cfg: {**cfg, "local_override_applied": True},
    )
    monkeypatch.setattr(
        mms_router,
        "export_model_routes",
        lambda cfg, force=False, startup_safe=False: calls.append((cfg, force, startup_safe)) or {},
    )

    assert mms_core._refresh_routes_export_for_hive(force=True, quiet=True, startup_safe=False) is True
    assert calls == [
        ({"provider": {"default": "demo"}, "providers": [], "local_override_applied": True}, True, False)
    ]


def test_handle_provider_default_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [{"id": "demo-a"}, {"id": "demo-b"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "save_config", lambda updated_cfg: calls.append(("save", updated_cfg["provider"]["default"])))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_default_config(cfg, ["demo-b"])

    assert cfg["provider"]["default"] == "demo-b"
    assert calls == [
        ("save", "demo-b"),
        ("refresh", True, False),
    ]


def test_handle_provider_remove_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo-a"},
        "providers": [{"id": "demo-a"}, {"id": "demo-b"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "_ensure_interactive_terminal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core.Confirm, "ask", staticmethod(lambda *_args, **_kwargs: True))
    monkeypatch.setattr(mms_core, "save_config", lambda updated_cfg: calls.append(("save", [item["id"] for item in updated_cfg["providers"]])))
    monkeypatch.setattr(mms_core, "_delete_provider_credentials", lambda provider_id: calls.append(("delete_creds", provider_id)))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda provider_id: calls.append(("invalidate", provider_id)))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_remove_config(cfg, ["demo-a"])

    assert calls == [
        ("save", ["demo-b"]),
        ("delete_creds", "demo-a"),
        ("invalidate", "demo-a"),
        ("refresh", True, False),
    ]


def test_handle_provider_edit_config_triggers_routes_refresh(monkeypatch):
    import mms_core

    cfg = {
        "provider": {"default": "demo"},
        "providers": [{"id": "demo", "name": "Demo"}],
    }
    updated_cfg = {
        "provider": {"default": "demo"},
        "providers": [{"id": "demo", "name": "Renamed Demo"}],
    }
    calls = []
    monkeypatch.setattr(mms_core, "_prompt_provider_metadata", lambda **_kwargs: {"id": "demo", "name": "Renamed Demo"})
    monkeypatch.setattr(mms_core, "_upsert_provider", lambda _cfg, _provider: updated_cfg)
    monkeypatch.setattr(mms_core, "save_config", lambda saved_cfg: calls.append(("save", saved_cfg["providers"][0]["name"])))
    monkeypatch.setattr(mms_core, "_invalidate_probe_cache", lambda provider_id: calls.append(("invalidate", provider_id)))
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *args, **kwargs: calls.append(("refresh", kwargs.get("force"), kwargs.get("quiet"))) or True,
    )

    mms_core._handle_provider_edit_config(cfg, ["demo"])

    assert calls == [
        ("save", "Renamed Demo"),
        ("invalidate", "demo"),
        ("refresh", True, False),
    ]


def test_main_refreshes_routes_snapshot_before_subcommand_dispatch(monkeypatch):
    import mms_core

    cfg = {"provider": {"default": "demo"}, "providers": []}
    events = []
    monkeypatch.setattr(mms_core.sys, "argv", ["mms", "ls"])
    monkeypatch.setattr(mms_core, "_extract_global_lang", lambda argv: (argv, None))
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "set_language", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda *_args, **_kwargs: "zh")
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_load_command_config", lambda: cfg)
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda current_cfg=None, **kwargs: events.append(("refresh", current_cfg, kwargs.get("force"))) or True,
    )
    monkeypatch.setattr(
        mms_core,
        "handle_models_command",
        lambda current_cfg, args: events.append(("models", current_cfg, list(args))),
    )

    mms_core.main()

    assert events == [
        ("refresh", cfg, True),
        ("models", cfg, []),
    ]


def test_main_help_bypasses_snapshot_guard_and_routes_refresh(monkeypatch):
    import mms_core

    events = []
    monkeypatch.setattr(mms_core.sys, "argv", ["mms", "--help"])
    monkeypatch.setattr(mms_core, "_extract_global_lang", lambda argv: (argv, None))
    monkeypatch.setattr(mms_core, "load_config", lambda: {"provider": {"default": "demo"}, "providers": []})
    monkeypatch.setattr(mms_core, "set_language", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_ui_language", lambda *_args, **_kwargs: "zh")
    monkeypatch.setattr(
        mms_core,
        "_ensure_startup_snapshot_guard",
        lambda *_args, **_kwargs: events.append("guard"),
    )
    monkeypatch.setattr(
        mms_core,
        "_refresh_routes_export_for_hive",
        lambda *_args, **_kwargs: events.append("refresh"),
    )

    with pytest.raises(SystemExit):
        mms_core.main()

    assert events == []


def test_select_provider_template_always_defaults_to_generic(monkeypatch):
    import mms_core

    monkeypatch.setattr(
        mms_core.Prompt,
        "ask",
        staticmethod(lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Prompt.ask should not be called"))),
    )

    assert mms_core._select_provider_template() == "generic"
    assert mms_core._select_provider_template("qwen") == "generic"
