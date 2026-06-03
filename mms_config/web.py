# -*- coding: utf-8 -*-
"""Local interactive WebUI for MMS setup, model policy, and audited config saves."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from mms_config.web_assets import _HTML_PAGE
from mms_config.web_common import (
    _ALLOWED_CLIS,
    _ALLOWED_PROTOCOLS,
    _ALLOWED_ROLES,
    _CACHE_SENSITIVE_PREFIXES,
    _CAPABILITY_TRUTH_REFRESH_FIELDS,
    _FALLBACK_MODEL_FAMILIES,
    _KNOWN_VISION_MODELS,
    _MIGRATION_BUNDLE_SCHEMA,
    _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA,
    _MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA,
    _MIGRATION_CREDENTIAL_BOX_SCHEMA,
    _OPENROUTER_MODELS_API_URL,
    _OPENCODE_REQUIRED_BUILDER_AGENTS,
    _OPENCODE_ROSTER_PRESETS,
    _REASONING_HINTS,
    _REGISTRY_V2_GENERATED_FILES,
    _SECRET_KEYS,
    _SENSITIVE_CONFIG_KEYS,
    _SAFE_TOKEN_COUNT_KEYS,
    _canonical_family_name as _canonical_family_name_impl,
    _is_secret_like_key,
    _json_response,
    _known_model_families as _known_model_families_impl,
    _normalize_choice_list,
    _normalize_context_tokens,
    _normalize_family_priority_overrides as _normalize_family_priority_overrides_impl,
    _normalize_model_list,
    _normalize_priority,
    _now_iso,
    _redact,
    _safe_text,
    _sanitize_for_output,
    _slug,
    _split_values,
    _truthy,
)
from mms_session.inventory import build_session_assets_snapshot
from mms_config.web_settings import (
    _settings_action_cards,
    _webui_capability_coverage,
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
    build_settings_report,
)
from mms_config.web_server import (
    ConfigWebApp,
    _SetupWebHandler,
    _html_page,
    run_config_web,
    serve_config_web,
)


def _known_model_families() -> list[str]:
    return _known_model_families_impl(_load_mms_core)


def _canonical_family_name(value: Any) -> str:
    return _canonical_family_name_impl(value, known_model_families_fn=_known_model_families)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _normalize_family_priority_overrides_impl(
        value,
        canonical_family_name_fn=_canonical_family_name,
        normalize_priority_fn=_normalize_priority,
    )


def _load_mms_core():
    import mms_core

    return mms_core


def _version_info_for_snapshot(command_name: str = "mms") -> dict[str, Any]:
    from mms_config.web_preview import _version_info_for_snapshot as version_info_for_snapshot_impl

    return version_info_for_snapshot_impl(command_name)


def _policy_path_for_config(config_path: str = "") -> str:
    from mms_config.web_preview import _policy_path_for_config as policy_path_for_config_impl

    return policy_path_for_config_impl(config_path)


def _config_root_for_snapshot(config_path: str = "") -> str:
    from mms_config.web_preview import _config_root_for_snapshot as config_root_for_snapshot_impl

    return config_root_for_snapshot_impl(config_path)


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    from mms_config.web_preview import _model_source_status_for_snapshot as model_source_status_for_snapshot_impl

    return model_source_status_for_snapshot_impl(config_path, command_name=command_name)


def _consumer_bundle_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    from mms_config.web_preview import _consumer_bundle_status_for_snapshot as consumer_bundle_status_for_snapshot_impl

    return consumer_bundle_status_for_snapshot_impl(config_path, command_name=command_name)


def _is_preview_config_root(config_path: str = "", *, command_name: str = "mms") -> bool:
    from mms_config.web_preview import _is_preview_config_root as is_preview_config_root_impl

    return is_preview_config_root_impl(config_path, command_name=command_name)


def _is_placeholder_provider_config(cfg: dict[str, Any]) -> bool:
    from mms_config.web_preview import _is_placeholder_provider_config as is_placeholder_provider_config_impl

    return is_placeholder_provider_config_impl(cfg)


def _read_json_from_verified_file(verified_files: dict[str, Any], key: str) -> dict[str, Any]:
    from mms_config.web_preview import _read_json_from_verified_file as read_json_from_verified_file_impl

    return read_json_from_verified_file_impl(verified_files, key)


def _preview_secret_refs_by_provider(config_root: str = "") -> dict[str, str]:
    from mms_config.web_preview import _preview_secret_refs_by_provider as preview_secret_refs_by_provider_impl

    return preview_secret_refs_by_provider_impl(config_root)


def _preview_secret_values_by_ref(config_root: str = "") -> dict[str, str]:
    from mms_config.web_preview import _preview_secret_values_by_ref as preview_secret_values_by_ref_impl

    return preview_secret_values_by_ref_impl(config_root)


def _preview_cached_provider_url(provider_id: str) -> str:
    from mms_config.web_preview import _preview_cached_provider_url as preview_cached_provider_url_impl

    return preview_cached_provider_url_impl(provider_id)


def _resolve_preview_provider_secret(
    provider: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_preview import _resolve_preview_provider_secret as resolve_preview_provider_secret_impl

    return resolve_preview_provider_secret_impl(provider, config_path=config_path, command_name=command_name)


def _attach_preview_secret_refs(
    cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_preview import _attach_preview_secret_refs as attach_preview_secret_refs_impl

    return attach_preview_secret_refs_impl(cfg, config_path=config_path, command_name=command_name)


def _preview_bundle_config_from_verified_files(verified_files: dict[str, Any], *, config_root: str = "") -> dict[str, Any]:
    from mms_config.web_preview import _preview_bundle_config_from_verified_files as preview_bundle_config_from_verified_files_impl

    return preview_bundle_config_from_verified_files_impl(verified_files, config_root=config_root)


def _hydrate_preview_config_from_latest_bundle(
    current_cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_preview import _hydrate_preview_config_from_latest_bundle as hydrate_preview_config_from_latest_bundle_impl

    return hydrate_preview_config_from_latest_bundle_impl(current_cfg, config_path=config_path, command_name=command_name)


def _config_v2_promotion_plan_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    from mms_config.web_preview import _config_v2_promotion_plan_for_snapshot as config_v2_promotion_plan_for_snapshot_impl

    return config_v2_promotion_plan_for_snapshot_impl(config_path, command_name=command_name)


def _config_v2_release_readiness_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    from mms_config.web_preview import _config_v2_release_readiness_for_snapshot as config_v2_release_readiness_for_snapshot_impl

    return config_v2_release_readiness_for_snapshot_impl(config_path, command_name=command_name)


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pretty_json(payload: dict[str, Any]) -> str:
    from mms_config.web_apply import _pretty_json as pretty_json_impl

    return pretty_json_impl(payload)


def _toml_key(key: Any) -> str:
    from mms_config.web_apply import _toml_key as toml_key_impl

    return toml_key_impl(key)


def _toml_scalar(value: Any) -> str:
    from mms_config.web_apply import _toml_scalar as toml_scalar_impl

    return toml_scalar_impl(value)


def _fallback_toml_dumps(payload: dict[str, Any]) -> str:
    from mms_config.web_apply import _fallback_toml_dumps as fallback_toml_dumps_impl

    return fallback_toml_dumps_impl(payload)


def _toml_dumps(payload: dict[str, Any]) -> str:
    from mms_config.web_apply import _toml_dumps as toml_dumps_impl

    return toml_dumps_impl(payload)


def _toml_text(payload: dict[str, Any]) -> str:
    from mms_config.web_apply import _toml_text as toml_text_impl

    return toml_text_impl(payload)


def _atomic_write_preferences_toml(path: str, payload: dict[str, Any]) -> None:
    from mms_config.web_apply import _atomic_write_preferences_toml as atomic_write_preferences_toml_impl

    atomic_write_preferences_toml_impl(path, payload)


def _diff_text(before: str, after: str, *, before_name: str, after_name: str) -> str:
    from mms_config.web_apply import _diff_text as diff_text_impl

    return diff_text_impl(before, after, before_name=before_name, after_name=after_name)


def _provider_credentials_status(provider_id: str) -> dict[str, Any]:
    from mms_config.web_snapshot import _provider_credentials_status as provider_credentials_status_impl

    return provider_credentials_status_impl(provider_id)


def _model_capability_defaults(
    model_id: str,
    policy_entry: dict[str, Any] | None = None,
    *,
    provider_id: str = "",
) -> dict[str, Any]:
    from mms_config.web_capabilities import _model_capability_defaults as model_capability_defaults_impl

    return model_capability_defaults_impl(model_id, policy_entry, provider_id=provider_id)


def capability_truth_refresh_fields() -> list[dict[str, str]]:
    from mms_config.web_capabilities import capability_truth_refresh_fields as capability_truth_refresh_fields_impl

    return capability_truth_refresh_fields_impl()


def _truth_normalize_model_key(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_normalize_model_key(*args, **kwargs)


def _truth_model_index_key(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_model_index_key(*args, **kwargs)


def _truth_model_index_keys(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_model_index_keys(*args, **kwargs)


def _truth_model_ids_from_provider(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_model_ids_from_provider(*args, **kwargs)


def _truth_int(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_int(*args, **kwargs)


def _truth_supported_parameters(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_supported_parameters(*args, **kwargs)


def _truth_first_provider_ref(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_first_provider_ref(*args, **kwargs)


def _truth_evidence_urls(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_evidence_urls(*args, **kwargs)


def _truth_field_source(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_field_source(*args, **kwargs)


def _truth_caps_from_row(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._truth_caps_from_row(*args, **kwargs)


def _openrouter_model_page_url(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._openrouter_model_page_url(*args, **kwargs)


def _openrouter_catalog_to_truth_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._openrouter_catalog_to_truth_payload(*args, **kwargs)


def _fetch_openrouter_catalog_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._fetch_openrouter_catalog_payload(*args, **kwargs)


def _latest_openrouter_catalog_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._latest_openrouter_catalog_payload(*args, **kwargs)


def _index_truth_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._index_truth_payload(*args, **kwargs)


def _load_capability_truth_payloads(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_capabilities

    return web_capabilities._load_capability_truth_payloads(*args, **kwargs)


def refresh_model_capability_truth(
    cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_capabilities import refresh_model_capability_truth as refresh_model_capability_truth_impl

    return refresh_model_capability_truth_impl(cfg, payload, config_path=config_path, command_name=command_name)


def _provider_derived_model_aliases(base_models: list[str], provider: dict[str, Any]) -> list[str]:
    from mms_config.web_snapshot import _provider_derived_model_aliases as provider_derived_model_aliases_impl

    return provider_derived_model_aliases_impl(base_models, provider)


def _provider_effective_model_rows(provider: dict[str, Any], policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    from mms_config.web_snapshot import _provider_effective_model_rows as provider_effective_model_rows_impl

    return provider_effective_model_rows_impl(provider, policy_payload)


def _provider_stale_hidden_models(provider: dict[str, Any], model_rows: list[dict[str, Any]]) -> list[str]:
    from mms_config.web_snapshot import _provider_stale_hidden_models as provider_stale_hidden_models_impl

    return provider_stale_hidden_models_impl(provider, model_rows)


def _usage_summary(runtime_kind: str, runtime_id: str) -> dict[str, Any]:
    from mms_config.web_snapshot import _usage_summary as usage_summary_impl

    return usage_summary_impl(runtime_kind, runtime_id)


def _runtime_usage_rows(runtime_kind: str, runtime_id: str) -> list[dict[str, Any]]:
    from mms_config.web_snapshot import _runtime_usage_rows as runtime_usage_rows_impl

    return runtime_usage_rows_impl(runtime_kind, runtime_id)


def _provider_summary(provider: dict[str, Any], *, policy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from mms_config.web_snapshot import _provider_summary as provider_summary_impl

    return provider_summary_impl(provider, policy_payload=policy_payload)


def _sanitized_mapping(payload: Any) -> dict[str, Any]:
    from mms_config.web_snapshot import _sanitized_mapping as sanitized_mapping_impl

    return sanitized_mapping_impl(payload)


def _account_summary(account: dict[str, Any], *, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    from mms_config.web_snapshot import _account_summary as account_summary_impl

    return account_summary_impl(account, defaults=defaults)


def _account_defaults(cfg: dict[str, Any]) -> dict[str, str]:
    from mms_config.web_snapshot import _account_defaults as account_defaults_impl

    return account_defaults_impl(cfg)


def _account_summaries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    from mms_config.web_snapshot import _account_summaries as account_summaries_impl

    return account_summaries_impl(cfg)


def _account_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from mms_config.web_snapshot import _account_by_id as account_by_id_impl

    return account_by_id_impl(cfg)


def _account_review_fields(account: dict[str, Any] | None) -> dict[str, Any]:
    from mms_config.web_snapshot import _account_review_fields as account_review_fields_impl

    return account_review_fields_impl(account)


def _copy_existing_account(existing: dict[str, Any], account_payload: dict[str, Any]) -> dict[str, Any]:
    from mms_config.web_snapshot import _copy_existing_account as copy_existing_account_impl

    return copy_existing_account_impl(existing, account_payload)


def _apply_account_draft(
    *,
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    draft: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    from mms_config.web_snapshot import _apply_account_draft as apply_account_draft_impl

    apply_account_draft_impl(current_cfg=current_cfg, next_cfg=next_cfg, draft=draft, errors=errors, warnings=warnings)


def _load_balance_summary(cfg: dict[str, Any] | None) -> dict[str, Any]:
    from mms_config.web_snapshot import _load_balance_summary as load_balance_summary_impl

    return load_balance_summary_impl(cfg)


def _normalize_load_balance_draft(value: Any, *, errors: list[str] | None = None) -> dict[str, Any]:
    from mms_config.web_snapshot import _normalize_load_balance_draft as normalize_load_balance_draft_impl

    return normalize_load_balance_draft_impl(value, errors=errors)


def _normalize_agent_model_overrides(value: Any) -> dict[str, dict[str, str]]:
    from mms_config.web_snapshot import _normalize_agent_model_overrides as normalize_agent_model_overrides_impl

    return normalize_agent_model_overrides_impl(value)


def _opencode_agent_preset(agent_id: str, category: str = "") -> str:
    from mms_config.web_snapshot import _opencode_agent_preset as opencode_agent_preset_impl

    return opencode_agent_preset_impl(agent_id, category)


def _opencode_roster_defaults(profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    from mms_config.web_snapshot import _opencode_roster_defaults as opencode_roster_defaults_impl

    return opencode_roster_defaults_impl(profile_id)


def _normalize_opencode_agent_roster(value: Any, *, profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    from mms_config.web_snapshot import _normalize_opencode_agent_roster as normalize_opencode_agent_roster_impl

    return normalize_opencode_agent_roster_impl(value, profile_id=profile_id)


def _strip_empty_provider_model_lists(cfg: dict[str, Any]) -> dict[str, Any]:
    from mms_config.web_snapshot import _strip_empty_provider_model_lists as strip_empty_provider_model_lists_impl

    return strip_empty_provider_model_lists_impl(cfg)


def _opencode_agent_catalog(profile_id: str = "agent") -> list[dict[str, Any]]:
    from mms_config.web_snapshot import _opencode_agent_catalog as opencode_agent_catalog_impl

    return opencode_agent_catalog_impl(profile_id)


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_snapshot import build_config_snapshot as build_config_snapshot_impl

    return build_config_snapshot_impl(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def build_config_snippets() -> dict[str, str]:
    from mms_config.web_snapshot import build_config_snippets as build_config_snippets_impl

    return build_config_snippets_impl()


def build_setup_flow() -> list[dict[str, Any]]:
    from mms_config.web_snapshot import build_setup_flow as build_setup_flow_impl

    return build_setup_flow_impl()


def build_test_contracts() -> list[dict[str, str]]:
    from mms_config.web_snapshot import build_test_contracts as build_test_contracts_impl

    return build_test_contracts_impl()


def build_reference_cards() -> list[dict[str, str]]:
    from mms_config.web_snapshot import build_reference_cards as build_reference_cards_impl

    return build_reference_cards_impl()


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    from mms_config.web_snapshot import build_setup_markdown as build_setup_markdown_impl

    return build_setup_markdown_impl(snapshot)


def _migration_cryptography_available() -> bool:
    from mms_config.web_migration import _migration_cryptography_available as migration_cryptography_available_impl

    return migration_cryptography_available_impl()


def _migration_openssl_available() -> bool:
    from mms_config.web_migration import _migration_openssl_available as migration_openssl_available_impl

    return migration_openssl_available_impl()


def _migration_secret_crypto_backend() -> str:
    from mms_config.web_migration import _migration_secret_crypto_backend as migration_secret_crypto_backend_impl

    return migration_secret_crypto_backend_impl()


def _migration_crypto_available() -> bool:
    from mms_config.web_migration import _migration_crypto_available as migration_crypto_available_impl

    return migration_crypto_available_impl()


def _migration_derive_key(password: str, salt: bytes, *, iterations: int) -> bytes:
    from mms_config.web_migration import _migration_derive_key as migration_derive_key_impl

    return migration_derive_key_impl(password, salt, iterations=iterations)


def _migration_encrypt_json_aesgcm(payload: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_encrypt_json_aesgcm as migration_encrypt_json_aesgcm_impl

    return migration_encrypt_json_aesgcm_impl(payload, password)


def _migration_decrypt_json_aesgcm(box: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_decrypt_json_aesgcm as migration_decrypt_json_aesgcm_impl

    return migration_decrypt_json_aesgcm_impl(box, password)


def _migration_openssl_passfile(password: str) -> str:
    from mms_config.web_migration import _migration_openssl_passfile as migration_openssl_passfile_impl

    return migration_openssl_passfile_impl(password)


def _migration_run_openssl_enc(data: bytes, password: str, *, decrypt: bool, iterations: int) -> bytes:
    from mms_config.web_migration import _migration_run_openssl_enc as migration_run_openssl_enc_impl

    return migration_run_openssl_enc_impl(data, password, decrypt=decrypt, iterations=iterations)


def _migration_openssl_mac_payload(box: dict[str, Any]) -> bytes:
    from mms_config.web_migration import _migration_openssl_mac_payload as migration_openssl_mac_payload_impl

    return migration_openssl_mac_payload_impl(box)


def _migration_encrypt_json_openssl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_encrypt_json_openssl as migration_encrypt_json_openssl_impl

    return migration_encrypt_json_openssl_impl(payload, password)


def _migration_decrypt_json_openssl(box: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_decrypt_json_openssl as migration_decrypt_json_openssl_impl

    return migration_decrypt_json_openssl_impl(box, password)


def _migration_encrypt_json(payload: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_encrypt_json as migration_encrypt_json_impl

    return migration_encrypt_json_impl(payload, password)


def _migration_decrypt_json(box: dict[str, Any], password: str) -> dict[str, Any]:
    from mms_config.web_migration import _migration_decrypt_json as migration_decrypt_json_impl

    return migration_decrypt_json_impl(box, password)


def _migration_config_from_snapshot(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_config_from_snapshot(*args, **kwargs)


def _migration_payload_config_from_cfg(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_payload_config_from_cfg(*args, **kwargs)


def _migration_preferences_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_preferences_payload(*args, **kwargs)


def _migration_collect_credentials(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_collect_credentials(*args, **kwargs)


def build_migration_export(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_export as build_migration_export_impl

    return build_migration_export_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def _parse_migration_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._parse_migration_bundle(*args, **kwargs)


def _migration_decrypted_credentials(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_decrypted_credentials(*args, **kwargs)


def _safe_local_command_name(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._safe_local_command_name(*args, **kwargs)


def _migration_start_status_from_snapshot(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_start_status_from_snapshot(*args, **kwargs)


def build_migration_start_status(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_start_status as build_migration_start_status_impl

    return build_migration_start_status_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def start_migration_work_session(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import start_migration_work_session as start_migration_work_session_impl

    return start_migration_work_session_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def _migration_provider_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_provider_payload(*args, **kwargs)


def _migration_preferences_apply_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_preferences_apply_payload(*args, **kwargs)


def _migration_draft_from_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_draft_from_bundle(*args, **kwargs)


def _merge_model_policy_import(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._merge_model_policy_import(*args, **kwargs)


def _build_migration_import_plan(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._build_migration_import_plan(*args, **kwargs)


def build_migration_import_preview(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_import_preview as build_migration_import_preview_impl

    return build_migration_import_preview_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def apply_migration_import(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import apply_migration_import as apply_migration_import_impl

    return apply_migration_import_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def _extract_draft(payload: dict[str, Any]) -> dict[str, Any]:
    from mms_config.web_provider import _extract_draft as extract_draft_impl

    return extract_draft_impl(payload)


def _route_model_rows_from_payload(provider_payload: dict[str, Any]) -> list[dict[str, Any]]:
    from mms_config.web_provider import _route_model_rows_from_payload as route_model_rows_from_payload_impl

    return route_model_rows_from_payload_impl(provider_payload)


def _copy_existing_provider(
    existing: dict[str, Any] | None,
    provider_payload: dict[str, Any],
    *,
    preserve_model_rows: bool = False,
    force_model_rows: bool = False,
    clear_fallback_models: bool = False,
) -> dict[str, Any]:
    from mms_config.web_provider import _copy_existing_provider as copy_existing_provider_impl

    return copy_existing_provider_impl(
        existing,
        provider_payload,
        preserve_model_rows=preserve_model_rows,
        force_model_rows=force_model_rows,
        clear_fallback_models=clear_fallback_models,
    )


def _strip_implicit_provider_timezone_defaults(
    next_cfg: dict[str, Any],
    providers_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    from mms_config.web_provider import _strip_implicit_provider_timezone_defaults as strip_implicit_provider_timezone_defaults_impl

    return strip_implicit_provider_timezone_defaults_impl(next_cfg, providers_payload)


def _build_model_policy_from_draft(policy_before: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    from mms_config.web_plan import _build_model_policy_from_draft as build_model_policy_from_draft_impl

    return build_model_policy_from_draft_impl(policy_before, draft)


def _provider_urls(provider: dict[str, Any] | None) -> dict[str, str]:
    from mms_config.web_provider import _provider_urls as provider_urls_impl

    return provider_urls_impl(provider)


def _provider_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from mms_config.web_provider import _provider_by_id as provider_by_id_impl

    return provider_by_id_impl(cfg)


def _provider_default_id(cfg: dict[str, Any]) -> str:
    from mms_config.web_provider import _provider_default_id as provider_default_id_impl

    return provider_default_id_impl(cfg)


def _mapping_digest(payload: Any) -> str:
    from mms_config.web_provider import _mapping_digest as mapping_digest_impl

    return mapping_digest_impl(payload)


def _build_review_summary(
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    policy_before: dict[str, Any],
    policy_after: dict[str, Any],
    credential_updates: list[dict[str, str]],
) -> dict[str, Any]:
    from mms_config.web_review import build_review_summary

    return build_review_summary(
        current_cfg,
        next_cfg,
        policy_before,
        policy_after,
        credential_updates,
    )


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
    from mms_config.web_plan import _build_registry_v2_save_plan as build_registry_v2_save_plan_impl

    return build_registry_v2_save_plan_impl(
        config_path=config_path,
        plan_summary=plan_summary,
        credential_updates=credential_updates,
        config_payload=config_payload,
        policy_payload=policy_payload,
        expected_bundle_revision=expected_bundle_revision,
        route_scope_provider_ids=route_scope_provider_ids,
        route_refresh_provider_ids=route_refresh_provider_ids,
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
    from mms_config.web_plan import build_config_plan as build_config_plan_impl

    return build_config_plan_impl(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        include_secrets=include_secrets,
        command_name=command_name,
    )


def _expected_bundle_revision_from_payload(payload: dict[str, Any] | None) -> str:
    from mms_config.web_plan import _expected_bundle_revision_from_payload as expected_bundle_revision_from_payload_impl

    return expected_bundle_revision_from_payload_impl(payload)


def _route_scope_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_scope_provider_ids_from_payload as route_scope_provider_ids_from_payload_impl

    return route_scope_provider_ids_from_payload_impl(payload)


def _route_refresh_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_refresh_provider_ids_from_payload as route_refresh_provider_ids_from_payload_impl

    return route_refresh_provider_ids_from_payload_impl(payload)


def _latest_audit_rows(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._latest_audit_rows(*args, **kwargs)


def _copy_backup_file(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._copy_backup_file(*args, **kwargs)


def _bak_path_for_backup(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._bak_path_for_backup(*args, **kwargs)


def _registry_v2_snapshot_generated_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_snapshot_generated_bundle(*args, **kwargs)


def _registry_v2_restore_generated_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_generated_bundle(*args, **kwargs)


def _registry_v2_restore_webui_credential_backend(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_webui_credential_backend(*args, **kwargs)


def _registry_v2_restore_db_candidate(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_db_candidate(*args, **kwargs)


def _rollback_registry_v2_preview_apply(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._rollback_registry_v2_preview_apply(*args, **kwargs)


def _append_audit(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._append_audit(*args, **kwargs)


def _save_provider_credentials_audited(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._save_provider_credentials_audited(*args, **kwargs)


def _write_model_policy_audited(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._write_model_policy_audited(*args, **kwargs)


def _preferences_target_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._preferences_target_path(*args, **kwargs)


def _preferences_lock_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._preferences_lock_path(*args, **kwargs)


def _load_preferences_raw(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._load_preferences_raw(*args, **kwargs)


def _normalize_asset_preferences_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._normalize_asset_preferences_payload(*args, **kwargs)


def _merge_asset_preferences(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._merge_asset_preferences(*args, **kwargs)


def build_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import build_preferences_plan as build_preferences_plan_impl

    return build_preferences_plan_impl(payload, config_path=config_path, preferences_path=preferences_path)


def _copy_preferences_backup(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._copy_preferences_backup(*args, **kwargs)


def apply_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_preferences_plan as apply_preferences_plan_impl

    return apply_preferences_plan_impl(payload, config_path=config_path, preferences_path=preferences_path)


def _expand_reveal_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._expand_reveal_path(*args, **kwargs)


def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    from mms_config.web_apply import reveal_local_path as reveal_local_path_impl

    return reveal_local_path_impl(payload)


def apply_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_config_plan as apply_config_plan_impl

    return apply_config_plan_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def apply_registry_v2_preview_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_registry_v2_preview_plan as apply_registry_v2_preview_plan_impl

    return apply_registry_v2_preview_plan_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def _provider_from_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._provider_from_payload(*args, **kwargs)


def probe_provider_models(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    from mms_config.web_probe import probe_provider_models as probe_provider_models_impl

    return probe_provider_models_impl(provider, force_refresh=force_refresh)


def test_provider_models(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_probe import test_provider_models as test_provider_models_impl

    return test_provider_models_impl(cfg, payload, config_path=config_path, command_name=command_name)


def _join_openai_chat_url(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._join_openai_chat_url(*args, **kwargs)


def _join_anthropic_messages_url(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._join_anthropic_messages_url(*args, **kwargs)


def run_model_smoke(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    chat: bool = False,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_probe import run_model_smoke as run_model_smoke_impl

    return run_model_smoke_impl(cfg, payload, chat=chat, config_path=config_path, command_name=command_name)
