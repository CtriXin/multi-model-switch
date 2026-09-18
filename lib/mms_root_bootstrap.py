"""First-run bootstrap for a v2 DB-truth config root.

A v2 root keeps its truth in the registry DB, the secret backend and the
published latest-approved bundle, so a fresh machine cannot be configured by
writing ``config.toml`` into it. This module turns one collected channel into
the same reviewed-plan write path the WebUI already uses: initialize the root
layout, apply the plan, publish the bundle.

Callers own the interaction. This module never prompts, never reads a real
HOME and never falls back to another root.
"""

import json
import os
import tempfile
from pathlib import Path

BOOTSTRAP_PLAN_SCHEMA = "mms.setup_web.plan.v1"


def v2_root_is_initialized(config_dir):
    """True when the root already carries the v2 layout markers."""
    root = Path(os.path.expanduser(str(config_dir or "")))
    if not str(config_dir or "").strip():
        return False
    return (root / "root-manifest.json").exists() or (root / "model-registry.sqlite").exists()


def _provider_ids(config_payload):
    providers = config_payload.get("providers") if isinstance(config_payload, dict) else []
    result = []
    for provider in providers or []:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id") or "").strip()
        if provider_id and provider_id not in result:
            result.append(provider_id)
    return result


def bootstrap_v2_root(
    *,
    config_dir,
    config_payload,
    credential_updates=None,
    policy_payload=None,
    command_name="mms",
):
    """Initialize ``config_dir`` and apply one plan into DB, secrets and bundle.

    Returns the ``apply-plan`` summary with an added ``init_root`` section.
    """
    from mms_registry_cli import apply_registry_v2_plan, init_config_root

    root = Path(os.path.expanduser(str(config_dir)))
    init_summary = init_config_root(
        config_dir=str(root),
        create_db=True,
        command_name=f"{command_name} registry",
    )

    plan = {
        "schema": BOOTSTRAP_PLAN_SCHEMA,
        "config": config_payload,
        "model_policy": policy_payload if isinstance(policy_payload, dict) else {},
        "credential_updates": [item for item in (credential_updates or []) if isinstance(item, dict)],
        "expected_bundle_revision": "",
        "route_scope_provider_ids": [],
        "route_refresh_provider_ids": [],
    }

    # The plan carries a plaintext key, so it stays inside the root at 0600 and
    # is removed as soon as the apply returns.
    handle, plan_path = tempfile.mkstemp(prefix=".bootstrap-plan-", suffix=".json", dir=str(root))
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False)
        summary = apply_registry_v2_plan(
            config_dir=str(root),
            plan_json=plan_path,
            apply=True,
            confirm_preview_apply=True,
            command_name=f"{command_name} config apply-plan",
        )
    finally:
        try:
            os.remove(plan_path)
        except OSError:
            pass

    summary = dict(summary)
    summary["init_root"] = init_summary
    summary["bootstrap_provider_ids"] = _provider_ids(config_payload)
    return summary
