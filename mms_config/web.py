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


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}



def _delegate(module_name: str, target_name: str, *, local_name: str | None = None):
    export_name = local_name or target_name

    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        module = __import__(module_name, fromlist=[target_name])
        return getattr(module, target_name)(*args, **kwargs)

    _wrapped.__name__ = export_name
    _wrapped.__qualname__ = export_name
    _wrapped.__module__ = __name__
    return _wrapped


_DELEGATE_TARGETS = {
    'mms_config.web_accounts': (
        '_account_by_id',
        '_account_defaults',
        '_account_review_fields',
        '_account_summaries',
        '_account_summary',
        '_apply_account_draft',
        '_copy_existing_account',
    ),
    'mms_config.web_apply': (
        '_append_audit',
        '_atomic_write_preferences_toml',
        '_bak_path_for_backup',
        '_copy_backup_file',
        '_copy_preferences_backup',
        '_diff_text',
        '_expand_reveal_path',
        '_fallback_toml_dumps',
        '_latest_audit_rows',
        '_load_preferences_raw',
        '_merge_asset_preferences',
        '_normalize_asset_preferences_payload',
        '_preferences_lock_path',
        '_preferences_target_path',
        '_pretty_json',
        '_registry_v2_restore_db_candidate',
        '_registry_v2_restore_generated_bundle',
        '_registry_v2_restore_webui_credential_backend',
        '_registry_v2_snapshot_generated_bundle',
        '_rollback_registry_v2_preview_apply',
        '_save_provider_credentials_audited',
        '_toml_dumps',
        '_toml_key',
        '_toml_scalar',
        '_toml_text',
        '_write_model_policy_audited',
        'apply_config_plan',
        'apply_preferences_plan',
        'apply_registry_v2_preview_plan',
        'build_preferences_plan',
        'reveal_local_path',
    ),
    'mms_config.web_capabilities': (
        '_fetch_openrouter_catalog_payload',
        '_index_truth_payload',
        '_latest_openrouter_catalog_payload',
        '_load_capability_truth_payloads',
        '_model_capability_defaults',
        '_openrouter_catalog_to_truth_payload',
        '_openrouter_model_page_url',
        '_truth_caps_from_row',
        '_truth_evidence_urls',
        '_truth_field_source',
        '_truth_first_provider_ref',
        '_truth_int',
        '_truth_model_ids_from_provider',
        '_truth_model_index_key',
        '_truth_model_index_keys',
        '_truth_normalize_model_key',
        '_truth_supported_parameters',
        'capability_truth_refresh_fields',
        'refresh_model_capability_truth',
    ),
    'mms_config.web_migration': (
        '_build_migration_import_plan',
        '_merge_model_policy_import',
        '_migration_collect_credentials',
        '_migration_config_from_snapshot',
        '_migration_crypto_available',
        '_migration_cryptography_available',
        '_migration_decrypt_json',
        '_migration_decrypt_json_aesgcm',
        '_migration_decrypt_json_openssl',
        '_migration_decrypted_credentials',
        '_migration_derive_key',
        '_migration_draft_from_bundle',
        '_migration_encrypt_json',
        '_migration_encrypt_json_aesgcm',
        '_migration_encrypt_json_openssl',
        '_migration_openssl_available',
        '_migration_openssl_mac_payload',
        '_migration_openssl_passfile',
        '_migration_payload_config_from_cfg',
        '_migration_preferences_apply_payload',
        '_migration_preferences_payload',
        '_migration_provider_payload',
        '_migration_run_openssl_enc',
        '_migration_secret_crypto_backend',
        '_migration_start_status_from_snapshot',
        '_parse_migration_bundle',
        '_safe_local_command_name',
        'apply_migration_import',
        'build_migration_export',
        'build_migration_import_preview',
        'build_migration_start_status',
        'start_migration_work_session',
    ),
    'mms_config.web_plan': (
        '_build_model_policy_from_draft',
        '_build_registry_v2_save_plan',
        '_expected_bundle_revision_from_payload',
        '_route_refresh_provider_ids_from_payload',
        '_route_scope_provider_ids_from_payload',
        'build_config_plan',
    ),
    'mms_config.web_preview': (
        '_attach_preview_secret_refs',
        '_config_root_for_snapshot',
        '_config_v2_promotion_plan_for_snapshot',
        '_config_v2_release_readiness_for_snapshot',
        '_consumer_bundle_status_for_snapshot',
        '_hydrate_preview_config_from_latest_bundle',
        '_is_placeholder_provider_config',
        '_is_preview_config_root',
        '_model_source_status_for_snapshot',
        '_policy_path_for_config',
        '_preview_bundle_config_from_verified_files',
        '_preview_cached_provider_url',
        '_preview_secret_refs_by_provider',
        '_preview_secret_values_by_ref',
        '_read_json_from_verified_file',
        '_resolve_preview_provider_secret',
        '_version_info_for_snapshot',
    ),
    'mms_config.web_probe': (
        '_join_anthropic_messages_url',
        '_join_openai_chat_url',
        '_provider_from_payload',
        'probe_provider_models',
        'run_model_smoke',
        'test_provider_models',
    ),
    'mms_config.web_provider': (
        '_copy_existing_provider',
        '_extract_draft',
        '_mapping_digest',
        '_provider_by_id',
        '_provider_default_id',
        '_provider_urls',
        '_route_model_rows_from_payload',
        '_strip_implicit_provider_timezone_defaults',
    ),
    'mms_config.web_review': (
        ('_build_review_summary', 'build_review_summary'),
    ),
    'mms_config.web_opencode': (
        '_normalize_agent_model_overrides',
        '_normalize_opencode_agent_roster',
        '_opencode_agent_catalog',
        '_opencode_agent_preset',
        '_opencode_roster_defaults',
        '_strip_empty_provider_model_lists',
    ),
    'mms_config.web_provider_snapshot': (
        '_provider_credentials_status',
        '_provider_derived_model_aliases',
        '_provider_effective_model_rows',
        '_provider_stale_hidden_models',
        '_provider_summary',
        '_runtime_usage_rows',
        '_sanitized_mapping',
        '_usage_summary',
    ),
    'mms_config.web_snapshot': (
        'build_config_snapshot',
    ),
    'mms_config.web_docs': (
        'build_config_snippets',
        'build_reference_cards',
        'build_setup_flow',
        'build_setup_markdown',
        'build_test_contracts',
    ),
}


for _module_name, _exports in _DELEGATE_TARGETS.items():
    for _export in _exports:
        if isinstance(_export, tuple):
            _local_name, _target_name = _export
        else:
            _local_name = _target_name = _export
        globals()[_local_name] = _delegate(_module_name, _target_name, local_name=_local_name)

del _module_name, _exports, _export, _local_name, _target_name
