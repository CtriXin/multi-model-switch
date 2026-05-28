from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import mms_consumer_bundle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_bundle(root: Path, *, schema: str = mms_consumer_bundle.LATEST_APPROVED_SCHEMA, bad_hash: bool = False, escape_path: bool = False) -> dict[str, Path]:
    generated = root / "generated"
    router = generated / "model-routes.json"
    lineup = generated / "model-routes.lineup.json"
    profile = generated / "provider-profiles.generated.json"
    policy = generated / "model-policy.effective.json"
    capabilities = generated / "model-capabilities.approved.json"
    _write_json(router, {"version": 1, "routes": {"gpt-test": {"primary": {"api_key": "sk-test-secret"}}}})
    _write_json(lineup, {"version": 1, "routes": {"gpt-test": {"primary": {"model_id": "gpt-test"}}}})
    _write_json(profile, {"schema_version": 1, "profiles": {"test-provider": {"models_endpoint": "manual"}}})
    _write_json(policy, {"version": 1, "models": {"gpt-test": {"visible": True}}})
    _write_json(capabilities, {"version": 1, "models": {"gpt-test": {"families": ["GPT"]}}})
    hashes = {
        "router": _sha256(router),
        "lineup": _sha256(lineup),
        "profile": _sha256(profile),
        "policy": _sha256(policy),
        "capabilities": _sha256(capabilities),
    }
    if bad_hash:
        hashes["policy"] = "0" * 64
    router_canonical = "../model-routes.json" if escape_path else "generated/model-routes.json"
    manifest = generated / "model-registry.latest-approved.json"
    _write_json(
        manifest,
        {
            "schema": schema,
            "bundle_revision": "bundle_test",
            "model_registry_revision": "bundle_test",
            "route_revision": "route_test",
            "policy_revision": "policy_test",
            "profile_revision": "profile_test",
            "capability_revision": "cap_test",
            "files": {
                "router": {
                    "canonical_path": router_canonical,
                    "legacy_alias_path": "model-routes.json",
                    "sha256": hashes["router"],
                    "sensitivity": "secret",
                },
                "lineup": {
                    "canonical_path": "generated/model-routes.lineup.json",
                    "legacy_alias_path": "model-routes.lineup.json",
                    "sha256": hashes["lineup"],
                    "sensitivity": "non-secret",
                },
                "profile": {
                    "canonical_path": "generated/provider-profiles.generated.json",
                    "sha256": hashes["profile"],
                    "sensitivity": "non-secret",
                },
                "policy": {
                    "canonical_path": "generated/model-policy.effective.json",
                    "legacy_alias_path": "model-policy.json",
                    "sha256": hashes["policy"],
                    "sensitivity": "non-secret",
                },
                "capabilities": {
                    "canonical_path": "generated/model-capabilities.approved.json",
                    "sha256": hashes["capabilities"],
                    "sensitivity": "non-secret",
                },
            },
        },
    )
    return {"manifest": manifest, "router": router, "lineup": lineup, "profile": profile, "policy": policy, "capabilities": capabilities}


def test_load_verified_consumer_bundle_verifies_hashes_and_omits_secrets(tmp_path: Path) -> None:
    root = tmp_path / "mms-next"
    paths = _write_bundle(root)

    bundle = mms_consumer_bundle.load_verified_consumer_bundle(config_root=root)
    encoded = json.dumps(bundle, ensure_ascii=False)

    assert bundle["schema"] == "mms.consumer_bundle.verified.v1"
    assert bundle["verified"] is True
    assert bundle["manifest_path"] == str(paths["manifest"])
    assert bundle["component_revisions"]["route"] == "route_test"
    assert bundle["verified_files"]["router"]["sensitivity"] == "secret"
    assert bundle["payloads"]["policy"]["models"]["gpt-test"]["visible"] is True
    assert "router" not in bundle["payloads"]
    assert bundle["skipped_secret_files"] == ["router"]
    assert "sk-test-secret" not in encoded

    with_secret = mms_consumer_bundle.load_verified_consumer_bundle(config_root=root, include_secret=True)
    assert with_secret["payloads"]["router"]["routes"]["gpt-test"]["primary"]["api_key"] == "sk-test-secret"


def test_load_verified_consumer_bundle_requires_selected_root_without_opt_in(tmp_path: Path) -> None:
    root = tmp_path / "mms-next"
    _write_bundle(root)

    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="MMS_CONFIG_ROOT is required"):
        mms_consumer_bundle.load_verified_consumer_bundle(env={})

    bundle = mms_consumer_bundle.load_verified_consumer_bundle(env={"MMS_CONFIG_ROOT": str(root)})
    assert bundle["config_root"] == str(root)


def test_load_verified_consumer_bundle_fails_closed_for_invalid_manifest(tmp_path: Path) -> None:
    root = tmp_path / "mms-next"
    _write_bundle(root, bad_hash=True)

    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="manifest hash mismatch"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=root)

    wrong_schema = tmp_path / "wrong-schema"
    _write_bundle(wrong_schema, schema="example.bad")
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="unexpected latest-approved schema"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=wrong_schema)

    escaping = tmp_path / "escaping"
    _write_bundle(escaping, escape_path=True)
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="unexpected manifest canonical_path for router"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=escaping)

    incomplete = tmp_path / "incomplete"
    paths = _write_bundle(incomplete)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["files"].pop("profile")
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="missing required files: profile"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=incomplete)

    missing_revision = tmp_path / "missing-revision"
    paths = _write_bundle(missing_revision)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest.pop("route_revision")
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="missing required revisions: route_revision"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=missing_revision)

    wrong_sensitivity = tmp_path / "wrong-sensitivity"
    paths = _write_bundle(wrong_sensitivity)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["files"]["router"]["sensitivity"] = "non-secret"
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="unexpected manifest sensitivity for router"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=wrong_sensitivity)

    wrong_path = tmp_path / "wrong-path"
    paths = _write_bundle(wrong_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    manifest["files"]["router"]["canonical_path"] = "model-routes.json"
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with pytest.raises(mms_consumer_bundle.ConsumerBundleError, match="unexpected manifest canonical_path for router"):
        mms_consumer_bundle.load_verified_consumer_bundle(config_root=wrong_path)
