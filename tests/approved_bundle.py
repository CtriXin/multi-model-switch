"""Real verified local bundles for explicitly opted-in config tests."""
from pathlib import Path
import mms_registry

def write_bundle(
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
    mms_registry.write_json_atomic(
        capabilities,
        capabilities_payload
        or {
            "schema": "mms.model_capabilities.approved.v1",
            "models": [],
        },
    )
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
        "capabilities": {
            "path": capabilities,
            "canonical_path": "generated/model-capabilities.approved.json",
            "sensitivity": "non-secret",
            "legacy_alias_compat": False,
        },
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
