from __future__ import annotations

import json
from pathlib import Path

import mms_registry
from mms_capability_resolver import resolve_model_capabilities


def _write_bundle(
    config_dir: Path,
    *,
    profile_payload: dict | None = None,
    capabilities_payload: dict | None = None,
) -> Path:
    generated = config_dir / "generated"
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    capabilities = generated / "model-capabilities.approved.json"

    mms_registry.write_json_atomic(router, {"version": 1, "routes": {}})
    mms_registry.write_json_atomic(lineup, {"version": 1, "routes": {}})
    mms_registry.write_json_atomic(
        profile,
        profile_payload
        or {
            "schema_version": 1,
            "profiles": {},
        },
    )
    mms_registry.write_json_atomic(policy, {"version": 1, "models": {}})
    files = {
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
    }
    if capabilities_payload is not None:
        mms_registry.write_json_atomic(capabilities, capabilities_payload)
        files["capabilities"] = {
            "path": capabilities,
            "canonical_path": "generated/model-capabilities.approved.json",
            "sensitivity": "non-secret",
            "legacy_alias_compat": False,
        }

    manifest_path = generated / "model-registry.latest-approved.json"
    mms_registry.export_latest_approved_bundle_manifest(
        manifest_path,
        bundle_revision="bundle_test_001",
        capability_revision="cap_test_001",
        route_revision="route_test_001",
        policy_revision="policy_test_001",
        profile_revision="profile_test_001",
        generated_at="2026-05-22T00:00:00.000Z",
        files=files,
    )
    return manifest_path


def test_provider_profiles_use_verified_latest_approved_before_legacy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    legacy_profile = {
        "schema_version": 1,
        "profiles": {
            "approved-test": {
                "match": {"provider_id_contains": ["approved-provider"]},
                "context_windows": {"approved-model": 111_000},
            }
        },
    }
    approved_profile = {
        "schema_version": 1,
        "profiles": {
            "approved-test": {
                "match": {"provider_id_contains": ["approved-provider"]},
                "context_windows": {"approved-model": 222_000},
            }
        },
    }
    mms_registry.write_json_atomic(tmp_path / "provider-profiles.json", legacy_profile)
    _write_bundle(tmp_path, profile_payload=approved_profile)

    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()
    assert (
        mms_provider_profiles.profile_context_window(
            "approved-model",
            provider_id="approved-provider",
        )
        == 222_000
    )

    generated_profile = tmp_path / "generated" / "provider-profiles.generated.json"
    generated_profile.write_text(json.dumps(legacy_profile), encoding="utf-8")
    mms_provider_profiles.load_provider_profiles.cache_clear()
    assert (
        mms_provider_profiles.profile_context_window(
            "approved-model",
            provider_id="approved-provider",
        )
        == 111_000
    )


def test_capability_resolver_uses_verified_latest_approved_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    approved_caps = {
        "schema": "mms.model_capabilities.approved.v1",
        "models": [
            {
                "alias": "approved-model",
                "official_context_window_tokens": 333_000,
                "official_max_output_tokens": 44_000,
                "supports_thinking": True,
                "thinking_control": {
                    "control_type": "thinkingBudget",
                    "path": "thinkingConfig.thinkingBudget",
                    "numeric_budget_tokens": 8192,
                },
            }
        ],
    }
    _write_bundle(tmp_path, capabilities_payload=approved_caps)

    caps = resolve_model_capabilities("approved-model")

    assert caps["context_window_tokens"] == 333_000
    assert caps["max_output_tokens"] == 44_000
    assert caps["thinking_control"]["path"] == "thinkingConfig.thinkingBudget"
    assert caps["sources"]["context_window_tokens"] == "approved_facts"

    generated_caps = tmp_path / "generated" / "model-capabilities.approved.json"
    generated_caps.write_text(json.dumps({"models": []}), encoding="utf-8")
    fallback = resolve_model_capabilities("approved-model")

    assert fallback["context_window_tokens"] == 8_192
    assert fallback["sources"]["context_window_tokens"] == "conservative_fallback"


def test_runtime_context_helpers_accept_only_approved_context_facts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    _write_bundle(
        tmp_path,
        capabilities_payload={
            "schema": "mms.model_capabilities.approved.v1",
            "models": [
                {
                    "alias": "runtime-approved-model",
                    "official_context_window_tokens": 555_000,
                }
            ],
        },
    )

    import mms_core
    import mms_launchers
    import mms_provider_profiles

    mms_provider_profiles.load_provider_profiles.cache_clear()

    assert mms_launchers._lookup_context_window("runtime-approved-model") == 555_000
    assert mms_core._model_context_window("runtime-approved-model") == 555_000
