# -*- coding: utf-8 -*-
"""Save-plan builders for the MMS config WebUI."""

from __future__ import annotations

import copy
from typing import Any


_ALLOWED_CLIS = ("claude", "codex", "opencode", "pi", "agy")


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _mapping_digest(payload: Any) -> str:
    return _call_backend("_mapping_digest", payload)


def _normalize_context_tokens(value: Any) -> int:
    return _call_backend("_normalize_context_tokens", value)


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _now_iso() -> str:
    return _call_backend("_now_iso")


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _call_backend("_config_root_for_snapshot", config_path)


def _extract_draft(payload: dict[str, Any]) -> dict[str, Any]:
    return _call_backend("_extract_draft", payload)


def _hydrate_preview_config_from_latest_bundle(current_cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_hydrate_preview_config_from_latest_bundle", current_cfg, config_path=config_path, command_name=command_name)


def _is_preview_config_root(config_path: str = "", *, command_name: str = "mms") -> bool:
    return _call_backend("_is_preview_config_root", config_path, command_name=command_name)


def _copy_existing_provider(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend("_copy_existing_provider", *args, **kwargs)


def _redact(value: str) -> str:
    return _call_backend("_redact", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _apply_account_draft(*args: Any, **kwargs: Any) -> None:
    _call_backend("_apply_account_draft", *args, **kwargs)


def _normalize_load_balance_draft(value: Any, *, errors: list[str]) -> dict[str, Any]:
    return _call_backend("_normalize_load_balance_draft", value, errors=errors)


def _normalize_agent_model_overrides(value: Any) -> dict[str, Any]:
    return _call_backend("_normalize_agent_model_overrides", value)


def _normalize_opencode_agent_roster(value: Any, *, profile_id: str = "agent") -> dict[str, Any]:
    return _call_backend("_normalize_opencode_agent_roster", value, profile_id=profile_id)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend("_policy_path_for_config", config_path)


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _merge_model_policy_import(policy: dict[str, Any], payload: Any) -> dict[str, Any]:
    return _call_backend("_merge_model_policy_import", policy, payload)


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _strip_implicit_provider_timezone_defaults(next_cfg: dict[str, Any], providers_payload: list[dict[str, Any]]) -> dict[str, Any]:
    return _call_backend("_strip_implicit_provider_timezone_defaults", next_cfg, providers_payload)


def _strip_empty_provider_model_lists(next_cfg: dict[str, Any]) -> dict[str, Any]:
    return _call_backend("_strip_empty_provider_model_lists", next_cfg)


def _toml_text(payload: dict[str, Any]) -> str:
    return _call_backend("_toml_text", payload)


def _sanitize_for_output(value: Any) -> Any:
    return _call_backend("_sanitize_for_output", value)


def _pretty_json(payload: Any) -> str:
    return _call_backend("_pretty_json", payload)


def _diff_text(*args: Any, **kwargs: Any) -> str:
    return _call_backend("_diff_text", *args, **kwargs)


def _build_review_summary(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend("_build_review_summary", *args, **kwargs)


def _build_model_policy_from_draft(policy_before: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    original_policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy.setdefault("version", 1)
    policy.setdefault("description", "User-maintained model visibility and preference policy. MMS never stores provider secrets here.")
    models = policy.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        policy["models"] = models
    providers = draft.get("providers") if isinstance(draft.get("providers"), list) else []

    def sanitize_capability_source(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key in ("source_layer", "source_name", "confidence", "source_path", "checked_at"):
            text = _safe_text(value.get(key))
            if text:
                result[key] = text
        urls = value.get("evidence_urls") if isinstance(value.get("evidence_urls"), list) else []
        clean_urls = [_safe_text(item) for item in urls if _safe_text(item)]
        if clean_urls:
            result["evidence_urls"] = list(dict.fromkeys(clean_urls))[:6]
        return result

    def capability_value(entry: dict[str, Any], field: str) -> Any:
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        return caps.get(field)

    def capability_changed(before_entry: dict[str, Any], after_entry: dict[str, Any], field: str) -> bool:
        return _mapping_digest({"value": capability_value(before_entry, field)}) != _mapping_digest({"value": capability_value(after_entry, field)})

    def source_for_field(source_map: dict[str, Any], field: str) -> dict[str, Any]:
        if not isinstance(source_map, dict):
            return {}
        source = source_map.get(field)
        if source is None and field == "supports_thinking":
            source = source_map.get("thinking")
        if source is None and field == "cache_sensitive_transport":
            source = source_map.get("cache_sensitive")
        if source is None and field == "long_context":
            source = source_map.get("context_window_tokens") or source_map.get("one_m_context")
        return sanitize_capability_source(source)

    for provider in providers:
        if not isinstance(provider, dict):
            continue
        hidden = set(_normalize_model_list(provider.get("hidden_models")))
        caps_map = dict(provider.get("model_capabilities") if isinstance(provider.get("model_capabilities"), dict) else {})
        source_map = dict(provider.get("model_capability_sources") if isinstance(provider.get("model_capability_sources"), dict) else {})
        rows = provider.get("models") if isinstance(provider.get("models"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _safe_text(row.get("id"))
            if not model_id:
                continue
            touched = row.get("policy_touched") is True or row.get("touched") is True
            capability_touched = row.get("capability_touched") is True or row.get("capabilities_touched") is True
            if not touched and not capability_touched:
                continue
            row_policy_caps = row.get("policy_capabilities") if isinstance(row.get("policy_capabilities"), dict) else None
            if row_policy_caps is not None:
                caps_map[model_id] = row_policy_caps
            else:
                caps_map.setdefault(model_id, row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {})
            if capability_touched and not touched:
                if isinstance(row.get("capability_sources"), dict):
                    source_map[model_id] = row.get("capability_sources")
                continue
            if isinstance(row.get("capability_sources"), dict):
                source_map[model_id] = row.get("capability_sources")
            if model_id in hidden or row.get("visible") is False:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = False
            elif row.get("visible") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = True
            if row.get("favorite") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["favorite"] = True
            elif row.get("favorite") is False and isinstance(models.get(model_id), dict) and "favorite" in models[model_id]:
                models[model_id]["favorite"] = False
        for model_id, caps in caps_map.items():
            model_id = _safe_text(model_id)
            if not model_id or not isinstance(caps, dict):
                continue
            entry = models.setdefault(model_id, {})
            if not isinstance(entry, dict):
                entry = {}
                models[model_id] = entry
            before_entry_for_sources = copy.deepcopy(entry)
            cap_payload = entry.setdefault("capabilities", {})
            if not isinstance(cap_payload, dict):
                cap_payload = {}
                entry["capabilities"] = cap_payload
            for key in ("text", "vision", "tool_use", "reasoning", "thinking", "long_context"):
                if isinstance(caps.get(key), bool):
                    cap_payload[key] = bool(caps[key])
            if isinstance(caps.get("one_m_context"), bool):
                cap_payload["one_m_context"] = bool(caps["one_m_context"])
            if isinstance(caps.get("thinking"), bool):
                cap_payload["supports_thinking"] = bool(caps["thinking"])
            if caps.get("text") is False:
                entry["visible"] = False
            if isinstance(caps.get("cache_sensitive"), bool):
                cap_payload["cache_sensitive_transport"] = bool(caps["cache_sensitive"])
            if "context_window_tokens" in caps or "max_context_tokens" in caps or caps.get("one_m_context") is True:
                context_tokens = _normalize_context_tokens(
                    caps.get("context_window_tokens") or caps.get("max_context_tokens") or (1_000_000 if caps.get("one_m_context") is True else None)
                )
                if context_tokens:
                    cap_payload["context_window_tokens"] = context_tokens
                    cap_payload["long_context"] = context_tokens >= 200_000
            if "max_output_tokens" in caps or "official_max_output_tokens" in caps:
                max_output_tokens = _normalize_context_tokens(caps.get("max_output_tokens") or caps.get("official_max_output_tokens"))
                if max_output_tokens:
                    cap_payload["max_output_tokens"] = max_output_tokens
            per_model_sources = source_map.get(model_id) if isinstance(source_map.get(model_id), dict) else {}
            if per_model_sources:
                source_payload = entry.get("capability_sources") if isinstance(entry.get("capability_sources"), dict) else {}
                source_payload = dict(source_payload)
                for field in (
                    "text",
                    "vision",
                    "tool_use",
                    "reasoning",
                    "thinking",
                    "supports_thinking",
                    "one_m_context",
                    "long_context",
                    "context_window_tokens",
                    "max_output_tokens",
                    "cache_sensitive_transport",
                ):
                    source = source_for_field(per_model_sources, field)
                    if source and capability_changed(before_entry_for_sources, entry, field):
                        source_payload[field] = source
                if source_payload:
                    entry["capability_sources"] = source_payload
    def comparable(payload: dict[str, Any]) -> dict[str, Any]:
        copy_payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        copy_payload.pop("updated_at", None)
        return copy_payload

    if _mapping_digest(comparable(policy)) != _mapping_digest(comparable(original_policy)):
        policy["updated_at"] = _now_iso()
    elif isinstance(original_policy, dict) and "updated_at" in original_policy:
        policy["updated_at"] = original_policy["updated_at"]
    return policy

def _build_registry_v2_save_plan(
    *,
    config_path: str,
    plan_summary: dict[str, Any],
    credential_updates: list[dict[str, str]],
    config_payload: dict[str, Any] | None = None,
    policy_payload: dict[str, Any] | None = None,
    expected_bundle_revision: str = "",
    route_scope_provider_ids: list[str] | None = None,
    route_refresh_provider_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Describe the future DB-truth save path without writing anything."""
    from mms_registry.cli import registry_v2_route_publish_guard, registry_v2_save_plan

    route_publish_guard: dict[str, Any] = {}
    try:
        config_root = _config_root_for_snapshot(config_path)
        route_publish_guard = registry_v2_route_publish_guard(
            config_dir=config_root or None,
            config_payload=config_payload if isinstance(config_payload, dict) else {},
            policy_payload=policy_payload if isinstance(policy_payload, dict) else {},
            credential_updates=credential_updates,
            expected_bundle_revision=expected_bundle_revision,
            route_scope_provider_ids=route_scope_provider_ids,
            route_refresh_provider_ids=route_refresh_provider_ids,
        )
    except Exception as exc:
        route_publish_guard = {
            "ok": False,
            "reason": "route_publish_guard_error",
            "message": f"{type(exc).__name__}: {exc}",
        }

    return registry_v2_save_plan(
        config_path=config_path,
        command_name="mms-config-web",
        plan_summary=plan_summary,
        credential_updates=credential_updates,
        route_publish_guard=route_publish_guard,
    )

def build_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    include_secrets: bool = False,
    command_name: str = "mms",
) -> dict[str, Any]:
    current_cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    current_cfg = _hydrate_preview_config_from_latest_bundle(current_cfg, config_path=config_path, command_name=command_name)
    draft = _extract_draft(payload or {})
    providers_payload = draft.get("providers") if isinstance(draft.get("providers"), list) else []
    existing_by_id = {str(item.get("id") or ""): item for item in current_cfg.get("providers", []) if isinstance(item, dict)}
    preserve_model_rows = _is_preview_config_root(config_path, command_name=command_name)
    route_scope_provider_ids = _route_scope_provider_ids_from_payload(payload or {})
    route_refresh_provider_ids = _route_refresh_provider_ids_from_payload(payload or {})
    touched_route_provider_ids = set(route_scope_provider_ids) | set(route_refresh_provider_ids)
    refreshed_provider_ids = set(route_refresh_provider_ids)
    next_providers: list[dict[str, Any]] = []
    credential_updates: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for provider_payload in providers_payload:
        if not isinstance(provider_payload, dict):
            continue
        original_id = _safe_text(provider_payload.get("original_id") or provider_payload.get("id"))
        provider_id = _safe_text(provider_payload.get("id") or original_id)
        provider = _copy_existing_provider(
            existing_by_id.get(original_id),
            provider_payload,
            preserve_model_rows=preserve_model_rows,
            force_model_rows=original_id in touched_route_provider_ids or provider_id in touched_route_provider_ids,
            clear_fallback_models=preserve_model_rows and (original_id in refreshed_provider_ids or provider_id in refreshed_provider_ids),
        )
        next_providers.append(provider)
        if _truthy(provider_payload.get("update_credentials"), False):
            api_key = _safe_text(provider_payload.get("api_key"))
            openai_base = _safe_text(provider_payload.get("openai_base_url") or provider_payload.get("base_url") or provider.get("default_openai_base_url"))
            anthropic_base = _safe_text(provider_payload.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
            if not api_key:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 API Key 为空。")
            if not openai_base and not anthropic_base:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 URL 为空。")
            credential_update = {
                "provider_id": provider["id"],
                "base_url": (openai_base or anthropic_base).rstrip("/"),
                "openai_base_url": openai_base.rstrip("/"),
                "anthropic_base_url": anthropic_base.rstrip("/"),
                "api_key": api_key if include_secrets else _redact(api_key),
            }
            openai_api_key = _safe_text(provider_payload.get("openai_api_key"))
            if openai_api_key:
                credential_update["openai_api_key"] = openai_api_key if include_secrets else _redact(openai_api_key)
            credential_updates.append(credential_update)
        if provider.get("anthropic_base_url") and "anthropic_messages" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 Anthropic URL，但 protocols 未包含 anthropic_messages。")
        if provider.get("openai_base_url") and "openai_chat_completions" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 OpenAI URL，但 protocols 未包含 openai_chat_completions。")

    if providers_payload:
        seen: set[str] = set()
        deduped = []
        for provider in next_providers:
            provider_id = provider.get("id")
            if provider_id in seen:
                errors.append(f"通道 ID 重复: {provider_id}")
                continue
            seen.add(provider_id)
            deduped.append(provider)
        next_providers = deduped
    else:
        next_providers = list(current_cfg.get("providers") or [])

    next_cfg = copy.deepcopy(current_cfg)
    if next_providers:
        next_cfg["providers"] = next_providers
    provider_default = _safe_text(draft.get("provider_default") or (next_cfg.get("provider") if isinstance(next_cfg.get("provider"), dict) else {}).get("default"))
    provider_ids = {provider.get("id") for provider in next_providers if isinstance(provider, dict)}
    if provider_default and provider_default not in provider_ids:
        warnings.append(f"默认通道 {provider_default} 不在通道列表中，保存时会使用第一个通道。")
        provider_default = ""
    if next_providers:
        next_cfg["provider"] = {"default": provider_default or str(next_providers[0].get("id"))}

    _apply_account_draft(
        current_cfg=current_cfg,
        next_cfg=next_cfg,
        draft=draft,
        errors=errors,
        warnings=warnings,
    )

    ui_payload = draft.get("ui") if isinstance(draft.get("ui"), dict) else {}
    if "language" in ui_payload:
        language = _safe_text(ui_payload.get("language") or "zh").lower()
        if language not in {"zh", "en"}:
            errors.append("ui.language 只支持 zh 或 en。")
        else:
            ui_cfg = dict(next_cfg.get("ui") if isinstance(next_cfg.get("ui"), dict) else {})
            ui_cfg["language"] = language
            next_cfg["ui"] = ui_cfg

    rescue_payload = draft.get("rescue") if isinstance(draft.get("rescue"), dict) else {}
    if rescue_payload:
        rescue = dict(next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {})
        fallback_model = _safe_text(rescue_payload.get("fallback_model"))
        fallback_cli = _safe_text(rescue_payload.get("fallback_cli"))
        if fallback_model:
            rescue["fallback_model"] = fallback_model
            if fallback_cli:
                rescue["fallback_cli"] = fallback_cli
            else:
                rescue.pop("fallback_cli", None)
            rescue["hot_fallback_enabled"] = _truthy(rescue_payload.get("hot_fallback_enabled"), False)
        else:
            rescue.pop("fallback_model", None)
            rescue.pop("fallback_cli", None)
            rescue.pop("hot_fallback_enabled", None)
        if rescue:
            next_cfg["rescue"] = rescue
        else:
            next_cfg.pop("rescue", None)

    if isinstance(draft.get("load_balance"), dict):
        load_balance = _normalize_load_balance_draft(draft.get("load_balance"), errors=errors)
        if load_balance:
            next_cfg["load_balance"] = load_balance
        else:
            next_cfg.pop("load_balance", None)

    vision_payload = draft.get("vision_sidecar") if isinstance(draft.get("vision_sidecar"), dict) else {}
    if vision_payload:
        vision = {
            "enabled": _truthy(vision_payload.get("enabled"), True),
            "provider_id": _safe_text(vision_payload.get("provider_id") or vision_payload.get("provider")),
            "model": _safe_text(vision_payload.get("model") or vision_payload.get("vision_model")),
        }
        candidates = []
        for item in vision_payload.get("candidates") or []:
            if not isinstance(item, dict):
                continue
            provider_id = _safe_text(item.get("provider_id") or item.get("provider"))
            model = _safe_text(item.get("model") or item.get("vision_model"))
            if provider_id and model:
                candidates.append({"provider_id": provider_id, "model": model})
        if candidates:
            vision["candidates"] = candidates
        if vision["provider_id"] or vision["model"] or candidates or vision["enabled"] is False:
            next_cfg["vision_sidecar"] = vision

    runtime_payload = draft.get("runtime") if isinstance(draft.get("runtime"), dict) else {}
    preferred_cli = _safe_text(runtime_payload.get("preferred_cli"))
    if preferred_cli:
        if preferred_cli not in _ALLOWED_CLIS:
            errors.append(f"首选 CLI 不支持: {preferred_cli}")
        else:
            presets = dict(next_cfg.get("presets") if isinstance(next_cfg.get("presets"), dict) else {})
            coding = dict(presets.get("coding") if isinstance(presets.get("coding"), dict) else {})
            coding_model = _safe_text(runtime_payload.get("coding_preset_model"))
            if coding or preferred_cli != "opencode" or coding_model:
                coding["cli"] = preferred_cli
            if coding_model:
                coding["model"] = coding_model
            if coding:
                presets["coding"] = coding
                next_cfg["presets"] = presets

    opencode_payload = draft.get("opencode") if isinstance(draft.get("opencode"), dict) else {}
    default_profile = _safe_text(opencode_payload.get("default_profile"))
    agent_model_overrides = _normalize_agent_model_overrides(opencode_payload.get("agent_models") or opencode_payload.get("agent_model_overrides"))
    agent_roster = _normalize_opencode_agent_roster(opencode_payload.get("agent_roster"), profile_id="agent")
    if default_profile or "agent_models" in opencode_payload or "agent_model_overrides" in opencode_payload or "agent_roster" in opencode_payload:
        opencode_cfg = dict(next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {})
        current_default_profile = _safe_text(opencode_cfg.get("default_profile"))
        if default_profile and (current_default_profile or default_profile != "agent"):
            opencode_cfg["default_profile"] = default_profile
        if agent_model_overrides:
            opencode_cfg["agent_models"] = agent_model_overrides
            opencode_cfg.pop("agent_model_overrides", None)
        else:
            opencode_cfg.pop("agent_models", None)
            opencode_cfg.pop("agent_model_overrides", None)
        if agent_roster:
            opencode_cfg["agent_roster"] = agent_roster
        else:
            opencode_cfg.pop("agent_roster", None)
        if opencode_cfg:
            next_cfg["opencode"] = opencode_cfg
        else:
            next_cfg.pop("opencode", None)

    policy_path = _policy_path_for_config(config_path)
    policy_before = _load_json_file(policy_path)
    if not policy_before:
        policy_before = {
            "version": 1,
            "updated_at": _now_iso(),
            "description": "User-maintained model visibility and preference policy. MMS never stores provider secrets here.",
            "models": {},
            "projects": {},
        }
    policy_after = _build_model_policy_from_draft(policy_before, draft)
    policy_after = _merge_model_policy_import(policy_after, draft.get("model_policy_import"))

    try:
        mms_core = _load_mms_core()
        if hasattr(mms_core, "_ensure_provider_config"):
            next_cfg, _ = mms_core._ensure_provider_config(next_cfg)  # noqa: SLF001 - reuse existing normalization
    except Exception:
        pass
    next_cfg = _strip_implicit_provider_timezone_defaults(next_cfg, providers_payload)
    next_cfg = _strip_empty_provider_model_lists(next_cfg)

    before_config_text = _toml_text(_sanitize_for_output(current_cfg))
    after_config_text = _toml_text(_sanitize_for_output(next_cfg))
    before_policy_text = _pretty_json(_sanitize_for_output(policy_before))
    after_policy_text = _pretty_json(_sanitize_for_output(policy_after))
    config_changed = _mapping_digest(current_cfg) != _mapping_digest(next_cfg)
    diffs = {
        "config_toml": _diff_text(before_config_text, after_config_text, before_name="config.toml(before)", after_name="config.toml(after)") if config_changed else "",
        "model_policy_json": _diff_text(before_policy_text, after_policy_text, before_name="model-policy.json(before)", after_name="model-policy.json(after)"),
        "credentials": "\n".join(
            f"credential update: provider {item['provider_id']} (secret hidden; stable credentials.sh / preview secret backend)"
            for item in credential_updates
        ),
    }
    review_summary = _build_review_summary(current_cfg, next_cfg, policy_before, policy_after, credential_updates)
    summary = {
        "providers": len(next_cfg.get("providers") or []),
        "credential_updates": len(credential_updates),
        "policy_models": len((policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}) or {}),
        "will_write_config": bool(diffs["config_toml"]),
        "will_write_policy": bool(diffs["model_policy_json"]),
        "will_write_credentials": bool(credential_updates),
    }
    return {
        "schema": "mms.setup_web.plan.v1",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "expected_bundle_revision": _expected_bundle_revision_from_payload(payload or {}),
        "route_scope_provider_ids": route_scope_provider_ids,
        "route_refresh_provider_ids": route_refresh_provider_ids,
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "config": next_cfg,
        "model_policy": policy_after,
        "credential_updates": credential_updates,
        "diffs": diffs,
        "review_summary": review_summary,
        "registry_v2_save_plan": _build_registry_v2_save_plan(
            config_path=config_path,
            plan_summary=summary,
            credential_updates=credential_updates,
            config_payload=next_cfg,
            policy_payload=policy_after,
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload or {}),
            route_scope_provider_ids=route_scope_provider_ids,
            route_refresh_provider_ids=route_refresh_provider_ids,
        ),
        "summary": summary,
    }

def _expected_bundle_revision_from_payload(payload: dict[str, Any] | None) -> str:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        for key in ("expected_bundle_revision", "bundle_revision", "source_bundle_revision"):
            value = _safe_text(source.get(key))
            if value:
                return value
    return ""

def _route_scope_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        values = source.get("route_scope_provider_ids") or source.get("touched_provider_ids")
        if isinstance(values, list):
            result = []
            seen = set()
            for item in values:
                provider_id = _safe_text(item)
                if provider_id and provider_id not in seen:
                    seen.add(provider_id)
                    result.append(provider_id)
            if result:
                return result
    return []

def _route_refresh_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        values = source.get("route_refresh_provider_ids") or source.get("refreshed_provider_ids")
        if isinstance(values, list):
            result = []
            seen = set()
            for item in values:
                provider_id = _safe_text(item)
                if provider_id and provider_id not in seen:
                    seen.add(provider_id)
                    result.append(provider_id)
            if result:
                return result
    return []
