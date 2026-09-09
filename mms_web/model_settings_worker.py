"""Isolated adapter to the existing MMF Config Web editor/publisher.

Read/probe/plan run on a private snapshot. Only a reviewed, human-confirmed
apply is pointed at the configured source root. Never returns credentials.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mms_web.errors import WebError


def load(root, *, standalone=False):
    import mms_config_web as web
    from mms_registry_cli import verify_approved_bundle
    if standalone and not (root / "generated/model-registry.latest-approved.json").exists():
        from mms_web.standalone_config import unpublished_settings
        return unpublished_settings(root)
    try:
        verified = verify_approved_bundle(config_dir=str(root))
    except Exception as exc:
        raise WebError("INVALID_BUNDLE", "MMF 模型目录校验失败，请先修复配置来源。", 409) from exc
    if not verified.get("verified"):
        raise WebError("INVALID_BUNDLE", "MMF 模型目录校验失败，请先修复配置来源。", 409)
    path = root / "config.toml"
    cfg = tomllib.loads(path.read_text()) if path.exists() else {}
    # Use the same editor hydration and preservation rules as MMF Config Web.
    cfg = web._hydrate_preview_config_from_latest_bundle(cfg, config_path=str(path), command_name="mmf")
    # The legacy editor keeps non-placeholder config.toml providers unchanged.
    # Rebase editor model rows on the approved routes, which are what launches
    # consume. Retain non-model fields, then overlay published provider settings.
    approved = web._preview_bundle_config_from_verified_files(verified.get("verified_files") or {}, config_root=str(root))
    existing = {p["id"]: p for p in cfg.get("providers", [])}
    cfg["providers"] = [{**existing.get(p["id"], {}), **p, "models": [], "_mms_bundle_runtime": True} for p in approved.get("providers", [])]
    cfg["provider"] = approved.get("provider", cfg.get("provider", {}))
    # Config Web's legacy policy accessor otherwise misses defaults that exist
    # only in the approved v2 policy. Bind it to the verified canonical file in
    # this short-lived worker, so plan/apply preserve the same policy consumers use.
    verified_files = verified.get("verified_files") or {}
    policy = web._read_json_from_verified_file(verified_files, "policy")
    manifest_data = json.loads((root / "generated/model-registry.latest-approved.json").read_text())
    policy_path = root / manifest_data["files"]["policy"]["canonical_path"]
    web._policy_path_for_config = lambda config_path="": str(policy_path)
    rows = [web._provider_summary(p, policy_payload=policy) for p in cfg.get("providers", [])]
    legacy_path = root / "model-policy.json"
    legacy = json.loads(legacy_path.read_text()) if legacy_path.is_file() else {}
    for provider in rows:
        for model in provider["models"]:
            entry = legacy.get("models", {}).get(model["id"], {})
            entry_policy = policy.get("models", {}).get(model["id"], {})
            model["policyEffort"] = str(entry_policy.get("capabilities", {}).get("reasoning_effort") or entry_policy.get("reasoning_effort") or "")
            model["legacyEffort"] = str(entry.get("capabilities", {}).get("reasoning_effort") or entry.get("reasoning_effort") or "")
    manifest = json.loads((root / "generated/model-registry.latest-approved.json").read_text())
    return cfg, rows, manifest["bundle_revision"]


def public_rows(rows):
    import mms_core
    from mms_web.launch_options import public_options
    cfg = mms_core._load_preview_runtime_config_from_latest_bundle()
    if not cfg and not (Path(os.environ["MMS_CONFIG_ROOT"]) / "generated/model-registry.latest-approved.json").exists():
        from mms_web.standalone_config import unpublished_config
        cfg = unpublished_config(Path(os.environ["MMS_CONFIG_ROOT"]))
    cfg = mms_core.apply_local_overrides(mms_core._merge_preview_local_launch_preferences(cfg))
    result = []
    for p in rows:
        models = []
        runtime = None
        try:
            import mms_launchers
            candidate = mms_core.resolve_provider_context(cfg, p["id"])
            if os.environ.get("MMS_WEB_STANDALONE") == "1":
                approved = next((v for v in cfg.get("providers", []) if v.get("id") == p["id"] and v.get("_mms_bundle_runtime")), None)
                if approved:
                    for field in ("api_key", "openai_api_key", "base_url", "openai_base_url", "anthropic_base_url"):
                        candidate[field] = approved.get(field, "")
            mms_launchers.validate_provider_for_cli("pi", candidate)
            runtime = mms_core._runtime_with_launch_preferences(cfg, candidate, "pi")
        except (Exception, SystemExit):
            pass
        for m in p["models"]:
            caps = m.get("capabilities") or {}
            effort = m.get("policyEffort", "")
            options = {}
            if runtime:
                try:
                    if (Path(os.environ["MMS_CONFIG_ROOT"]) / "generated/model-registry.latest-approved.json").exists():
                        options = public_options(runtime, m["id"])
                    else:
                        from mms_web.standalone_config import unpublished_options
                        options = unpublished_options(runtime, m["id"])
                except (Exception, SystemExit):
                    pass
            # MMF policy cannot represent Pi's off/minimal as distinct defaults.
            # Publish only levels that this exact route can execute without
            # silently clamping the user's selection to another level.
            levels = [v for v in options.get("supportedThinkingLevels", []) if v in {"low", "medium", "high", "xhigh", "max"}]
            effective = str(options.get("defaultThinkingLevel") or "")
            models.append({"id": m["id"], "visible": m.get("visible", True),
                           "effort": effort, "effortLevels": [] if m.get("legacyEffort") else levels,
                           "legacyEffort": m.get("legacyEffort", ""),
                           "effectiveEffort": effective,
                           "contextWindow": options.get("model", {}).get("contextWindow") or caps.get("context_window_tokens"),
                           "vision": "image" in options.get("model", {}).get("input", []),
                           "launchOverride": str(runtime.get("reasoning_effort") or "") if runtime else ""})
        from mms_web.channel_connection import public_connection
        result.append({"id": p["id"], "name": p["name"], "models": models,
                       "connection": public_connection(p, runtime),
                       "canDiscover": p["models_endpoint"] not in {"manual", "none", "off"}
                       and "openai_chat_completions" in p["protocols"]})
    return result


def draft_for(rows, request, revision):
    provider_id = request.get("providerId")
    rows = copy.deepcopy(rows)
    target = next((p for p in rows if p["id"] == provider_id), None)
    if target is None:
        raise WebError("PROVIDER_NOT_FOUND", "这个通道已不存在，请刷新。", 404)
    selected = request.get("models")
    if not isinstance(selected, list) or len(selected) > 5000 or not all(isinstance(m, str) and m.strip() == m and 0 < len(m) <= 200 and not any(ord(c) < 32 for c in m) for m in selected):
        raise WebError("INVALID_MODELS", "请填写有效的模型 ID。", 400)
    selected = list(dict.fromkeys(selected))
    original = {m["id"] for m in target["models"] if m.get("visible", True)}
    known = {m["id"]: m for m in public_rows([target])[0]["models"]}
    changes = []
    efforts = request.get("efforts") or {}
    if not isinstance(efforts, dict):
        raise WebError("INVALID_EFFORT", "effort 格式无效。", 400)
    for model, value in efforts.items():
        if model not in known or not isinstance(value, str) or not known[model]["effortLevels"] or (value != "" and value not in known[model]["effortLevels"]):
            raise WebError("INVALID_EFFORT", "所选 effort 不在这个模型的配置选项中。", 400)
        if value != known[model]["effort"]:
            affected = [p["name"] for p in rows if any(m["id"] == model for m in p["models"])]
            changes.append({"kind": "effort", "model": model, "before": known[model]["effort"] or "自动", "after": value, "channels": affected})
    for model in sorted(set(selected) - original):
        changes.append({"kind": "add", "model": model})
    for model in sorted(original - set(selected)):
        changes.append({"kind": "remove", "model": model})
    for p in rows:
        # Keep every published route, including hidden historical entries, when
        # that channel model list is not being edited. Visibility is not deletion.
        p["fallback_models"] = list(p.get("approved_route_models") or p.get("fallback_models") or [])
        # Snapshot display capabilities must not become implicit policy writes.
        p["models"] = [{"id": m["id"], "visible": m.get("visible", True)} for m in p["models"]]
    changed_routes = set(selected) != original
    if changed_routes:
        # Unchanged hidden routes remain published. Only explicitly deselected
        # visible models are removed; adding one model must not prune history.
        retained = set(target.get("approved_route_models") or []) - (original - set(selected))
        target["models"] = [{"id": m, "visible": True} for m in sorted(retained | set(selected))]
        target["hidden_models"] = sorted((set(target.get("hidden_models", [])) | (original - set(selected))) - set(selected))
        target["extra_models"] = []
        target["fallback_models"] = []
    # Capability edits are model-level; never set policy_touched/visible here.
    target["model_capabilities"] = {c["model"]: {"reasoning_effort": c["after"]} for c in changes if c["kind"] == "effort"}
    from mms_web.channel_connection import edit_connection
    connection, connection_changes = edit_connection(target, request.get("connection"))
    target.update(connection)
    changes.extend(connection_changes)
    payload = {"draft": {"providers": rows}, "expected_bundle_revision": revision, "route_scope_provider_ids": [provider_id]}
    if changed_routes:
        payload.update(route_scope_provider_ids=[provider_id], route_refresh_provider_ids=[provider_id])
    if not revision:
        # No published baseline exists yet: import every legacy channel once.
        ids = [p["id"] for p in rows]
        payload.update(route_scope_provider_ids=ids, route_refresh_provider_ids=ids)
    return payload, changes


def run(request):
    import mms_config_web as web
    root = Path(request["root"])
    cfg, rows, revision = load(root, standalone=request.get("standalone") is True)
    action = request["action"]
    if action == "read":
        return {"revision": revision, "providers": public_rows(rows)}
    if request.get("revision") != revision:
        raise WebError("CONFIG_STALE", "MMF 配置已更新，请重新加载后再保存。", 409)
    if action in {"discover", "check"}:
        target = next((p for p in rows if p["id"] == request.get("providerId")), None)
        if not target or not public_rows([target])[0]["canDiscover"]:
            raise WebError("MANUAL_MODELS", "该通道使用手工模型目录，请直接添加模型 ID。", 409)
        # The private snapshot intentionally excludes the secret backend. Resolve
        # selected credentials from the verified Router, as the launcher does.
        import mms_core
        runtime_cfg = mms_core._load_preview_runtime_config_from_latest_bundle()
        runtime = mms_core.resolve_provider_context(runtime_cfg, target["id"])
        from mms_web.channel_connection import edit_connection
        connection, _ = edit_connection(target, request.get("connection"))
        runtime.update(connection)
        # Runtime field has precedence over provider defaults in the probe.
        if connection.get("api_key"):
            runtime["openai_api_key"] = connection["api_key"]
        result = web.test_provider_models(cfg, {"provider_id": target["id"], "provider": runtime, "force_refresh": True}, config_path=str(root / "config.toml"), command_name="mmf")
        if not result.get("ok") or result.get("base_source") != "remote":
            raise WebError("MODEL_DISCOVERY_FAILED", "拉取失败，请检查通道地址、Key 和模型列表权限。已有模型未改变。", 502)
        models = result.get("raw_models") or result.get("models") or []
        if action == "check":
            return {"connected": True, "modelCount": len(models), "latencyMs": result.get("latency_ms", 0),
                    "message": "模型列表接口已连通。尚未验证模型生成能力。"}
        return {"models": models, "latencyMs": result.get("latency_ms", 0)}
    payload, changes = draft_for(rows, request, revision)
    if action == "plan":
        if not changes:
            raise WebError("NO_CHANGES", "还没有需要保存的修改。", 409)
        plan = web.build_config_plan(cfg, payload, config_path=str(root / "config.toml"), command_name="mmf")
        guard = plan.get("registry_v2_save_plan", {}).get("blocked_reasons", [])
        if not plan.get("ok") or guard:
            raise WebError("CONFIG_PLAN_BLOCKED", "MMF 未允许这组修改，未保存。请检查是否移除了全部可用模型，或重新加载配置后再试。", 409)
        return {"changes": changes}
    if action != "apply" or request.get("confirmPhrase") != "写入预览DB":
        raise WebError("CONFIRM_REQUIRED", "请先检查变更并输入确认文字。", 409)
    payload.update(confirm_v2_preview=True, confirm_phrase=request["confirmPhrase"])
    result = web.apply_registry_v2_preview_plan(cfg, payload, config_path=str(root / "config.toml"))
    if not result.get("ok"):
        raise WebError("CONFIG_APPLY_FAILED", "MMF 配置保存未通过，请重新加载配置检查。失败详情已保留在本地记录。", 409)
    return {"applied": True, "runtimeReady": result.get("runtime_ready", False), "changes": changes}


if __name__ == "__main__":
    from mms_web.catalog_worker import _result_stream, _emit
    stream = _result_stream()
    try:
        _emit(stream, {"ok": True, **run(json.load(sys.stdin))})
    except WebError as error:
        _emit(stream, {"ok": False, "code": error.code, "message": error.message, "status": error.status})
    except Exception:
        _emit(stream, {"ok": False, "code": "SETTINGS_FAILED", "message": "读取或保存 MMF 配置失败，请刷新后重试。", "status": 500})
