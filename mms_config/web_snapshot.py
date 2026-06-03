# -*- coding: utf-8 -*-
"""Snapshot and summary builders for the MMS config WebUI."""

from __future__ import annotations

import copy
from typing import Any

from mms_session.inventory import build_session_assets_snapshot

from mms_config.web_accounts import (
    _account_by_id,
    _account_defaults,
    _account_review_fields,
    _account_summaries,
    _account_summary,
    _apply_account_draft,
    _copy_existing_account,
)

from mms_config.web_opencode import (
    _normalize_agent_model_overrides,
    _normalize_opencode_agent_roster,
    _opencode_agent_catalog,
    _opencode_agent_preset,
    _opencode_required_builder_agents,
    _opencode_roster_defaults,
    _opencode_roster_presets,
    _strip_empty_provider_model_lists,
)

from mms_config.web_docs import (
    build_config_snippets,
    build_reference_cards,
    build_setup_flow,
    build_setup_markdown,
    build_test_contracts,
)


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _backend_web_wrapper(name: str) -> bool:
    func = getattr(_backend(), name, None)
    return callable(func) and getattr(func, "__module__", "") == "mms_config.web" and getattr(func, "__name__", "") == name


def _call_backend_override(name: str, default: Any, *args: Any, **kwargs: Any) -> Any:
    func = getattr(_backend(), name, None)
    if callable(func) and not _backend_web_wrapper(name):
        return func(*args, **kwargs)
    return default(*args, **kwargs)


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _redact(value: Any) -> str:
    return _call_backend("_redact", value)


def _slug(value: Any, fallback: str = "") -> str:
    return _call_backend("_slug", value, fallback)


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _normalize_priority(value: Any, default: int = 100) -> int:
    return _call_backend("_normalize_priority", value, default)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _call_backend("_normalize_family_priority_overrides", value)


def _known_model_families() -> list[str]:
    return _call_backend("_known_model_families")


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend("_policy_path_for_config", config_path)


def _version_info_for_snapshot(command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_version_info_for_snapshot", command_name)


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_model_source_status_for_snapshot", config_path, command_name=command_name)


def _consumer_bundle_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_consumer_bundle_status_for_snapshot", config_path, command_name=command_name)


def _config_v2_promotion_plan_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_config_v2_promotion_plan_for_snapshot", config_path, command_name=command_name)


def _config_v2_release_readiness_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_config_v2_release_readiness_for_snapshot", config_path, command_name=command_name)


def _hydrate_preview_config_from_latest_bundle(current_cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_hydrate_preview_config_from_latest_bundle", current_cfg, config_path=config_path, command_name=command_name)


def _model_capability_defaults(model_id: str, policy_entry: dict[str, Any] | None = None, *, provider_id: str = "") -> dict[str, Any]:
    return _call_backend("_model_capability_defaults", model_id, policy_entry, provider_id=provider_id)


def _mapping_digest(payload: Any) -> str:
    return _call_backend("_mapping_digest", payload)


def _settings_action_cards() -> list[dict[str, Any]]:
    from mms_config.web_settings import _settings_action_cards as settings_action_cards_impl

    return settings_action_cards_impl()


def _webui_capability_coverage() -> list[dict[str, Any]]:
    from mms_config.web_settings import _webui_capability_coverage as webui_capability_coverage_impl

    return webui_capability_coverage_impl()


def _tui_webui_mapping() -> dict[str, Any]:
    from mms_config.web_settings import _tui_webui_mapping as tui_webui_mapping_impl

    return tui_webui_mapping_impl()


def _tui_webui_mapping_summary(mapping: dict[str, Any]) -> dict[str, Any]:
    from mms_config.web_settings import _tui_webui_mapping_summary as tui_webui_mapping_summary_impl

    return tui_webui_mapping_summary_impl(mapping)


def _secret_keys() -> set[str]:
    return set(getattr(_backend(), "_SECRET_KEYS"))


def _allowed_clis() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_CLIS"))


def _provider_credentials_status_impl(provider_id: str) -> dict[str, Any]:
    try:
        mms_core = _load_mms_core()
        creds = mms_core.load_provider_credentials(provider_id)
    except Exception:
        creds = {}
    return {
        "has_api_key": bool(_safe_text((creds or {}).get("api_key") or (creds or {}).get("openai_api_key"))),
        "base_url": _safe_text((creds or {}).get("base_url")),
        "openai_base_url": _safe_text((creds or {}).get("openai_base_url")),
        "anthropic_base_url": _safe_text((creds or {}).get("anthropic_base_url")),
    }


def _provider_credentials_status(provider_id: str) -> dict[str, Any]:
    return _call_backend_override("_provider_credentials_status", _provider_credentials_status_impl, provider_id)


def _provider_derived_model_aliases(base_models: list[str], provider: dict[str, Any]) -> list[str]:
    try:
        mms_core = _load_mms_core()
        return list(mms_core._derived_model_aliases(base_models, provider))  # noqa: SLF001 - mirror runtime model patching
    except Exception:
        return []


def _provider_effective_model_rows(provider: dict[str, Any], policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    model_sources: dict[str, str] = {}
    provider_id = _safe_text(provider.get("id"))
    bundle_runtime = bool(provider.get("_mms_bundle_runtime"))
    cached_raw: list[str] = []
    cached_source = "fallback"
    if not bundle_runtime:
        try:
            mms_core = _load_mms_core()
            cached = mms_core._load_probe_file_cache(provider_id, allow_stale=True)  # noqa: SLF001 - UI snapshot only
            if cached:
                cached_raw = _normalize_model_list(cached.get("raw_models") or cached.get("models") or [])
                cached_source = _safe_text(cached.get("base_source") or "remote") or "remote"
        except Exception:
            cached_raw = []
    row_models: list[str] = []
    row_sources: dict[str, str] = {}
    for item in (provider.get("models") if isinstance(provider.get("models"), list) else []):
        model_id = _safe_text(item.get("id") or item.get("model")) if isinstance(item, dict) else _safe_text(item)
        if not model_id:
            continue
        row_models.append(model_id)
        if isinstance(item, dict):
            row_sources.setdefault(model_id, _safe_text(item.get("source") or "manual") or "manual")
    fallback_models = _normalize_model_list(provider.get("fallback_models"))
    base_models = cached_raw or fallback_models or row_models
    for model in base_models:
        source = "approved" if bundle_runtime else (cached_source if cached_raw else ("fallback" if fallback_models else row_sources.get(model, "manual")))
        model_sources.setdefault(model, source)
    for model in _normalize_model_list(provider.get("extra_models")):
        model_sources.setdefault(model, "extra")
    hidden = set(_normalize_model_list(provider.get("hidden_models")))
    hidden_lower = {model.lower() for model in hidden}
    alias_base_models = [model for model in base_models if model.lower() not in hidden_lower]
    for model in _provider_derived_model_aliases(alias_base_models, provider):
        model_sources.setdefault(model, "derived_alias")
    policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    rows: list[dict[str, Any]] = []
    for model_id in sorted(model_sources.keys(), key=lambda item: item.lower()):
        entry = policy_models.get(model_id) if isinstance(policy_models.get(model_id), dict) else {}
        visible = model_id.lower() not in hidden_lower
        if isinstance(entry, dict) and isinstance(entry.get("visible"), bool):
            visible = bool(entry.get("visible")) and visible
        rows.append(
            {
                "id": model_id,
                "source": model_sources.get(model_id) or "manual",
                "visible": visible,
                "favorite": bool(entry.get("favorite")) if isinstance(entry, dict) else False,
                "capabilities": _model_capability_defaults(
                    model_id,
                    entry if isinstance(entry, dict) else {},
                    provider_id=provider_id,
                ),
                "policy_touched": False,
            }
        )
    return rows


def _provider_stale_hidden_models(provider: dict[str, Any], model_rows: list[dict[str, Any]]) -> list[str]:
    current_ids = {str(row.get("id") or "").strip() for row in model_rows if isinstance(row, dict)}
    return [model for model in _normalize_model_list(provider.get("hidden_models")) if model not in current_ids]


def _usage_summary(runtime_kind: str, runtime_id: str) -> dict[str, Any]:
    """Best-effort local usage summary for WebUI display only."""
    runtime_id = _safe_text(runtime_id)
    if not runtime_id:
        return {"launches": 0, "last_used_at": ""}
    try:
        mms_core = _load_mms_core()
        launches, last_used_at = mms_core._usage_summary_for_runtime(runtime_kind, runtime_id)  # noqa: SLF001 - read-only UI summary
        return {"launches": int(launches or 0), "last_used_at": _safe_text(last_used_at)}
    except Exception:
        return {"launches": 0, "last_used_at": ""}


def _runtime_usage_rows(runtime_kind: str, runtime_id: str) -> list[dict[str, Any]]:
    """Mirror the TUI local usage table without exposing unrelated usage.json data."""
    runtime_id = _safe_text(runtime_id)
    if not runtime_id:
        return []

    def count_value(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    try:
        mms_core = _load_mms_core()
        rows = mms_core._usage_rows_for_runtime(runtime_kind, runtime_id)  # noqa: SLF001 - read-only UI report
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        models = item.get("models") if isinstance(item.get("models"), dict) else {}
        model_usage = [
            {"model": _safe_text(model), "launches": count_value(count)}
            for model, count in sorted(models.items(), key=lambda pair: count_value(pair[1]), reverse=True)
            if _safe_text(model)
        ]
        top_models = model_usage[:8]
        result.append(
            {
                "cli": _safe_text(item.get("cli")),
                "runtime_kind": _safe_text(item.get("runtime_kind") or runtime_kind),
                "id": _safe_text(item.get("id") or runtime_id),
                "name": _safe_text(item.get("name")),
                "launches": count_value(item.get("launches")),
                "last_model": _safe_text(item.get("last_model")),
                "last_used_at": _safe_text(item.get("last_used_at")),
                "top_models": top_models,
                "model_usage": model_usage,
            }
        )
    return result


def _provider_summary(provider: dict[str, Any], *, policy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = provider if isinstance(provider, dict) else {}
    provider_id = _safe_text(provider.get("id"))
    bundle_runtime = bool(provider.get("_mms_bundle_runtime"))
    protocols = provider.get("protocols") if isinstance(provider.get("protocols"), list) else []
    supported_clis = provider.get("supported_clis") if isinstance(provider.get("supported_clis"), list) else []
    models = []
    for key in ("models", "fallback_models", "extra_models"):
        values = provider.get(key)
        if isinstance(values, list):
            models.extend(str(item) for item in values if item)
        elif isinstance(values, dict):
            models.extend(str(item) for item in values.keys() if item)
    creds = _provider_credentials_status(provider_id) if provider_id else {}
    config_openai_base = _safe_text(provider.get("openai_base_url") or provider.get("default_openai_base_url") or provider.get("base_url"))
    config_anthropic_base = _safe_text(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
    credential_openai_base = _safe_text(creds.get("openai_base_url") or creds.get("base_url"))
    credential_anthropic_base = _safe_text(creds.get("anthropic_base_url"))
    openai_base = config_openai_base or credential_openai_base
    anthropic_base = config_anthropic_base or credential_anthropic_base
    api_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key"))
    policy_payload = policy_payload if isinstance(policy_payload, dict) else {}
    model_rows = _provider_effective_model_rows(provider, policy_payload)
    if bundle_runtime:
        for row in model_rows:
            if row.get("source") in {"fallback", "manual"}:
                row["source"] = "approved"
    approved_route_models = _normalize_model_list(provider.get("fallback_models"))
    fallback_models = [] if bundle_runtime else approved_route_models
    extra_models = _normalize_model_list(provider.get("extra_models"))
    return {
        "id": provider_id,
        "original_id": provider_id,
        "name": _safe_text(provider.get("name") or provider_id),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": provider.get("priority", 100),
        "family_priority_overrides": _normalize_family_priority_overrides(provider.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(provider.get("claude_1m_mode") or "auto") or "auto",
        "proxy_configured": bool(_safe_text(provider.get("proxy"))),
        "no_proxy_configured": bool(_safe_text(provider.get("no_proxy"))),
        "timezone": _safe_text(provider.get("timezone")),
        "note": _safe_text(provider.get("note")),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "/models"),
        "protocols": [str(item) for item in protocols if item],
        "supported_clis": [str(item) for item in supported_clis if item],
        "openai_base_url": openai_base,
        "anthropic_base_url": anthropic_base,
        "effective_openai_base_url": openai_base,
        "effective_anthropic_base_url": anthropic_base,
        "config_openai_base_url": config_openai_base,
        "config_anthropic_base_url": config_anthropic_base,
        "openai_base_url_source": "config" if config_openai_base else ("credentials" if credential_openai_base else ""),
        "anthropic_base_url_source": "config" if config_anthropic_base else ("credentials" if credential_anthropic_base else ""),
        "api_key": "",
        "has_api_key": bool(api_key or creds.get("has_api_key") or provider.get("has_api_key")),
        "update_credentials": False,
        "fallback_models": fallback_models,
        "approved_route_models": approved_route_models,
        "extra_models": extra_models,
        "hidden_models": _normalize_model_list(provider.get("hidden_models")),
        "stale_hidden_models": _provider_stale_hidden_models(provider, model_rows),
        "model_count": len(dict.fromkeys(row["id"] for row in model_rows)),
        "models": model_rows,
        "usage": _usage_summary("provider", provider_id),
        "usage_rows": _runtime_usage_rows("provider", provider_id),
    }


def _sanitized_mapping(payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if normalized.lower() in _secret_keys():
            result[normalized] = _redact(value)
        elif isinstance(value, dict):
            result[normalized] = _sanitized_mapping(value)
        elif isinstance(value, list):
            result[normalized] = [_sanitized_mapping(item) if isinstance(item, dict) else item for item in value]
        else:
            result[normalized] = value
    return result


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return a redacted, UI-friendly config snapshot; never mutates config."""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    cfg = _hydrate_preview_config_from_latest_bundle(cfg, config_path=config_path, command_name=command_name)
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    policy_path = _policy_path_for_config(config_path)
    policy_payload = _load_json_file(policy_path)
    provider_rows = [_provider_summary(item, policy_payload=policy_payload) for item in providers if isinstance(item, dict)]
    vision_sidecar = cfg.get("vision_sidecar") if isinstance(cfg.get("vision_sidecar"), dict) else {}
    rescue = cfg.get("rescue") if isinstance(cfg.get("rescue"), dict) else {}
    ui_cfg = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    provider_default = _safe_text((cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}).get("default"))
    presets = cfg.get("presets") if isinstance(cfg.get("presets"), dict) else {}
    coding_preset = presets.get("coding") if isinstance(presets.get("coding"), dict) else {}
    opencode_cfg = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    opencode_agent_models = _normalize_agent_model_overrides(opencode_cfg.get("agent_models") or opencode_cfg.get("agent_model_overrides"))
    opencode_profile = _safe_text(opencode_cfg.get("default_profile") or "agent")
    opencode_agent_catalog = _opencode_agent_catalog("agent")
    opencode = {
        "default_profile": opencode_profile,
        "recommended_profile": "agent",
        "profiles": ["agent", "omo", "raw"],
        "agent_models": opencode_agent_models,
        "agent_roster": _normalize_opencode_agent_roster(opencode_cfg.get("agent_roster"), profile_id="agent"),
        "agent_catalog": opencode_agent_catalog,
        "roster_presets": list(_opencode_roster_presets()),
        "vision_agents": ["mobius-vision-mimo", "mobius-vision-kimi", "mobius-vision-qwen"],
        "executor": "mobius-executor-gpt54",
        "release_gate": "mobius-reviewer-gpt55",
    }
    recommendations = []
    if not provider_rows:
        recommendations.append("先添加至少一个通道，然后再配置模型列表和 fallback。")
    if not vision_sidecar:
        recommendations.append("如果常用模型不直接支持图片，建议配置 vision sidecar。")
    if not _safe_text(rescue.get("fallback_model")):
        recommendations.append("建议先设置 rescue fallback model，失败时可以稳定交接。")
    if not any(row.get("anthropic_base_url") for row in provider_rows):
        recommendations.append("CN / dual-protocol 模型建议保留 Anthropic /v1/messages 路径，避免 cache 退化。")
    tui_webui_mapping = _tui_webui_mapping()
    return {
        "schema": "mms.setup_web.snapshot.v2",
        "mode": "interactive_audited_save",
        "command": command_name,
        "version_info": _version_info_for_snapshot(command_name),
        "setup_flow": build_setup_flow(),
        "test_contracts": build_test_contracts(),
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "providers": provider_rows,
        "provider_default": provider_default or (provider_rows[0]["id"] if provider_rows else ""),
        "model_families": _known_model_families(),
        "accounts": _account_summaries(cfg),
        "account_defaults": _account_defaults(cfg),
        "account_write_policy": {
            "status": "draft_review_confirmed_save",
            "claude": "human_only_locked",
            "allowed_fields": ["name", "enabled", "priority", "family_priority_overrides", "timezone", "note", "claude_1m_mode", "default_non_claude"],
            "blocked_fields": ["login", "remove", "rename/home_dir", "proxy", "no_proxy", "claude_default", "claude_metadata"],
        },
        "settings_actions": _settings_action_cards(),
        "webui_capability_coverage": _webui_capability_coverage(),
        "tui_webui_mapping": tui_webui_mapping,
        "tui_webui_mapping_summary": _tui_webui_mapping_summary(tui_webui_mapping),
        "vision_sidecar": _sanitized_mapping(vision_sidecar),
        "rescue": _sanitized_mapping(rescue),
        "ui": {"language": _safe_text(ui_cfg.get("language") or "zh") or "zh"},
        "runtime": {
            "preferred_cli": _safe_text(coding_preset.get("cli") or "opencode"),
            "coding_preset_model": _safe_text(coding_preset.get("model")),
        },
        "opencode": opencode,
        "policy_summary": {
            "path": policy_path,
            "model_count": len((policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}) or {}),
            "project_count": len((policy_payload.get("projects") if isinstance(policy_payload.get("projects"), dict) else {}) or {}),
        },
        "model_source_status": _model_source_status_for_snapshot(config_path, command_name=command_name),
        "consumer_bundle_status": _consumer_bundle_status_for_snapshot(config_path, command_name=command_name),
        "config_v2_promotion_plan": _config_v2_promotion_plan_for_snapshot(config_path, command_name=command_name),
        "config_v2_release_readiness": _config_v2_release_readiness_for_snapshot(config_path, command_name=command_name),
        "session_assets": build_session_assets_snapshot(
            cfg,
            config_path=config_path,
            preferences_path=preferences_path,
            command_name=command_name,
        ),
        "references": build_reference_cards(),
        "recommendations": recommendations,
        "snippets": build_config_snippets(),
        "save_contract": {
            "requires_diff_preview": True,
            "requires_confirm_save": True,
            "confirm_phrase": "保存配置",
            "preview_confirm_phrase": "写入预览DB",
            "writes": ["config.toml", "credentials.sh(仅当输入新 key 并勾选更新凭据)", "model-policy.json"],
            "stable_legacy_writes": ["config.toml", "credentials.sh(仅当输入新 key 并勾选更新凭据)", "model-policy.json"],
            "preview_v2_writes": [
                "registry/model-registry.sqlite(candidate revisions)",
                "secrets/webui-secrets.json(仅当输入新 key)",
                "generated/model-registry.latest-approved.json",
                "generated/model-routes.json",
                "generated/model-policy.effective.json",
                "generated/provider-profiles.generated.json",
            ],
            "safety": "stable legacy 保存走 lock + backup + audit；preview root 使用 DB candidate + generated bundle 发布并校验；页面不会回显真实 API Key。",
        },
    }
