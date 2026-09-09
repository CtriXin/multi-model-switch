"""Use the native Registry editor for Web-owned configuration roots.

Called only in isolated workers. Legacy reads prepare an in-memory draft;
only an explicit apply publishes to the source, with the native rollback.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import tomllib

from .errors import WebError
from .runtime import require_private_root


def unpublished_options(runtime: dict, model: str) -> dict:
    from .launch_options import public_options
    from .manual_bundle import materialize_manual_runtime_bundle

    # Match the existing legacy launch path: capabilities are resolved against
    # a private manual bundle, never by weakening the selected-root guard.
    original = os.environ["MMS_CONFIG_ROOT"]
    with tempfile.TemporaryDirectory(prefix="manual-options-", dir=os.environ["HOME"]) as directory:
        root = Path(directory)
        materialize_manual_runtime_bundle(root, runtime, model)
        try:
            os.environ["MMS_CONFIG_ROOT"] = str(root)
            return public_options(runtime, model)
        finally:
            os.environ["MMS_CONFIG_ROOT"] = original


def unpublished_config(root: Path) -> dict:
    import mms_core

    path = root / "config.toml"
    cfg = tomllib.loads(path.read_text()) if path.is_file() else {}
    # load_config(persist=False) still performs a legacy migration write. It
    # would also reenter the connection writer's flock. Normalize only in
    # memory, and never manufacture a default provider for an empty Web root.
    if cfg.get("providers"):
        return mms_core._normalize_config_sections(cfg)
    return {**cfg, "providers": []}


def unpublished_settings(root: Path):
    import mms_core
    import mms_config_web as web

    cfg = unpublished_config(root)
    policy_path = root / "model-policy.json"
    policy = json.loads(policy_path.read_text()) if policy_path.is_file() else {}
    rows = []
    for provider in cfg.get("providers", []):
        runtime = mms_core.resolve_provider_context(cfg, provider["id"])
        row = web._provider_summary(provider, policy_payload=policy)
        # First publication imports only this explicitly selected root's keys.
        # Future saves resolve credentials from the verified Router instead.
        if runtime.get("api_key"):
            row.update(api_key=runtime["api_key"], update_credentials=True,
                       openai_base_url=runtime.get("openai_base_url") or "",
                       anthropic_base_url=runtime.get("anthropic_base_url") or "",
                       openai_base_url_source="config", anthropic_base_url_source="config")
            if runtime.get("openai_api_key"):
                row["openai_api_key"] = runtime["openai_api_key"]
        for model in row["models"]:
            entry = policy.get("models", {}).get(model["id"], {})
            model["legacyEffort"] = str(entry.get("capabilities", {}).get("reasoning_effort") or entry.get("reasoning_effort") or "")
        rows.append(row)
    return cfg, rows, ""


def apply_connection(root: Path, request: dict) -> dict:
    import mms_core
    import mms_config_web as web
    from .model_settings_worker import load

    require_private_root(root)
    cfg, rows, revision = load(root, standalone=True)
    rows = copy.deepcopy(rows)
    for row in rows:
        row["fallback_models"] = list(row.get("approved_route_models") or row.get("fallback_models") or [])
        row["models"] = [{"id": m["id"], "visible": m.get("visible", True)} for m in row["models"]]
    service = request["service"]
    pid = request["providerId"]
    target = next((row for row in rows if row["id"] == pid), None)
    created = target is None
    if created:
        protocols = {"openai": ["openai_chat_completions"], "anthropic": ["anthropic_messages"]}.get(
            service.get("protocol"), ["openai_chat_completions", "anthropic_messages"])
        target = {"id": pid, "name": service["name"], "protocols": protocols,
                  "supported_clis": list(mms_core.PROVIDER_CAPABLE_CLIS),
                  "models_endpoint": "manual", "enabled": True}
        rows.append(target)
    else:
        target["name"] = service["name"]
    models = service.get("models") or []
    if created or (models and target.get("models_endpoint") == "manual"):
        target.update(fallback_models=models, models=[{"id": m, "visible": True} for m in models])
    base = service["baseUrl"]
    previous = next((p for p in cfg.get("providers", []) if p.get("id") == pid), {})
    credentials = mms_core.load_provider_credentials(pid) if not revision and not created else {}
    for field, protocol in (("openai_base_url", "openai_chat_completions"),
                            ("anthropic_base_url", "anthropic_messages")):
        # The generic connection form promises to preserve protocol-specific
        # addresses. Published addresses are explicit; edit them through the
        # channel settings form, which previews each protocol separately.
        if not created and (revision or credentials.get(field) or previous.get(field) or previous.get("default_" + field)):
            continue
        if protocol in target["protocols"]:
            target[field] = base
            target[field + "_source"] = "config"
    if service.get("apiKey"):
        target.update(api_key=service["apiKey"], update_credentials=True)
    payload = {"draft": {"providers": rows}, "expected_bundle_revision": revision,
               "route_scope_provider_ids": [pid], "route_refresh_provider_ids": [pid],
               "confirm_v2_preview": True, "confirm_phrase": "写入预览DB"}
    if not revision:
        ids = [row["id"] for row in rows]
        payload.update(route_scope_provider_ids=ids, route_refresh_provider_ids=ids)
    path = root / "config.toml"
    created_config = not path.exists()
    if created_config:
        # The existing MMS launch seam requires a config entry file even when
        # all providers are owned by the approved Registry.
        mms_core._atomic_write_toml(str(path), {})
    try:
        result = web.apply_registry_v2_preview_plan(cfg, payload, config_path=str(path))
    except BaseException:
        if created_config:
            path.unlink(missing_ok=True)
        raise
    if not result.get("ok"):
        if created_config:
            path.unlink(missing_ok=True)
        raise WebError("CONFIG_APPLY_FAILED", "配置保存未通过校验，请检查模型、地址和 Key 后重试。", 409)
    return {"ok": True, "applied": True, "providerId": pid,
            "runtimeReady": result.get("runtime_ready", False), "changed": ["registry"]}
