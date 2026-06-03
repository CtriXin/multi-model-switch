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

from mms_config.web_provider_snapshot import (
    _provider_credentials_status,
    _provider_derived_model_aliases,
    _provider_effective_model_rows,
    _provider_stale_hidden_models,
    _provider_summary,
    _runtime_usage_rows,
    _sanitized_mapping,
    _usage_summary,
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
