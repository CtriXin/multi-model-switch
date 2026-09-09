"""Compile a selected manual configuration into MMS's runtime bundle format.

Only private per-launch snapshots use this. No capability claims are invented:
unknown capabilities stay empty and MMS's own conservative defaults apply.
There is exactly one explicitly selected route, no routing or fallback policy.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .runtime import require_private_root


def materialize_manual_runtime_bundle(root: Path, runtime: dict, model: str) -> None:
    import mms_registry
    root = require_private_root(root)
    generated = root / "generated"
    provider_id = runtime["id"]
    protocols = set(runtime.get("protocols") or [])
    base = runtime.get("base_url", "")
    leaf = {"provider_id": provider_id, "model_id": model, "api_key": runtime.get("api_key", ""),
            "openai_api_key": runtime.get("openai_api_key") or runtime.get("api_key", ""),
            "openai_base_url": runtime.get("openai_base_url") or (base if "openai_chat_completions" in protocols else ""),
            "anthropic_base_url": runtime.get("anthropic_base_url") or (base if "anthropic_messages" in protocols else "")}
    profile = {k: runtime[k] for k in ("name", "protocols", "supported_clis", "role", "priority") if k in runtime}
    source = {"source": "mms-web/manual-configuration", "capabilities_verified": False}
    payloads = {
        "router": {"version": 1, **source, "routes": {model: {"primary": leaf, "fallbacks": []}}},
        "lineup": {"version": 1, **source, "routes": {model: {"primary": {"provider_id": provider_id, "model_id": model}, "fallbacks": []}}},
        "profile": {"schema_version": 1, **source, "profiles": {provider_id: profile}},
        "policy": {"version": 1, **source, "models": {}},
        "capabilities": {"schema": "mms.model_capabilities.approved.v1", **source, "models": []},
    }
    names = {"router": "model-routes.json", "lineup": "model-routes.lineup.json",
             "profile": "provider-profiles.generated.json", "policy": "model-policy.effective.json",
             "capabilities": "model-capabilities.approved.json"}
    files = {}
    for key, name in names.items():
        target = generated / name
        mms_registry.write_json_atomic(target, payloads[key])
        files[key] = {"path": target, "canonical_path": "generated/" + name,
                      "sensitivity": "secret" if key == "router" else "non-secret"}
    revision = "manual-" + hashlib.sha256(json.dumps(payloads, sort_keys=True).encode()).hexdigest()[:16]
    mms_registry.export_latest_approved_bundle_manifest(
        generated / "model-registry.latest-approved.json", files=files,
        bundle_revision=revision, capability_revision=revision, route_revision=revision,
        policy_revision=revision, profile_revision=revision)
    mms_registry.verify_latest_approved_bundle(config_dir=root)
