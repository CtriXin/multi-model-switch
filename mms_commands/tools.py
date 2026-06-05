"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager


CONFIG_HELP_TOPICS = {
    "-h",
    "--help",
    "help",
    "preferences",
    "preferences.help",
    "preference.help",
    "preferences.path",
    "preference.path",
    "preferences.example",
    "preference.example",
    "preferences.doc",
    "preference.doc",
    "web",
    "webui",
    "setup.web",
    "setup-web",
    "gates",
    "human-gate",
    "humangate",
    "human-gates",
}


def normalize_ui_config(cfg, *, normalize_language, default_language="zh"):
    cfg = dict(cfg)
    raw_ui = cfg.get("ui")
    current = raw_ui if isinstance(raw_ui, dict) else {}
    lang = normalize_language(current.get("language", "")) or default_language
    new_cfg = dict(cfg)
    new_cfg["ui"] = {"language": lang}
    return new_cfg, new_cfg != cfg


def resolve_ui_language(
    cfg=None,
    cli_override=None,
    *,
    normalize_language,
    load_version_meta,
    environ=None,
    default_language="zh",
):
    environ = os.environ if environ is None else environ
    cli_lang = normalize_language(cli_override)
    if cli_lang:
        return cli_lang
    env_lang = normalize_language(environ.get("MMS_LANG", ""))
    if env_lang:
        return env_lang
    if isinstance(cfg, dict):
        ui_lang = normalize_language((cfg.get("ui") or {}).get("language", ""))
        if ui_lang:
            return ui_lang
    locale_lang = normalize_language(environ.get("LC_ALL", "") or environ.get("LANG", ""))
    if locale_lang:
        return locale_lang
    version_meta = load_version_meta()
    version_lang = normalize_language(
        version_meta.get("preferred_language", "") if isinstance(version_meta, dict) else ""
    )
    if version_lang:
        return version_lang
    return default_language


def extract_global_lang(argv, *, normalize_language):
    cleaned = []
    lang = ""
    idx = 0
    while idx < len(argv):
        item = argv[idx]
        if item == "--lang" and idx + 1 < len(argv):
            candidate = normalize_language(argv[idx + 1])
            if candidate:
                lang = candidate
                idx += 2
                continue
        cleaned.append(item)
        idx += 1
    return cleaned, lang


def current_command(*, primary_command, environ=None, argv0=None):
    environ = {} if environ is None else environ
    explicit = str(environ.get("MMS_COMMAND_NAME") or "").strip()
    invoked = os.path.basename(str(argv0 if argv0 is not None else (sys.argv[0] if sys.argv else ""))).strip()
    known_entrypoints = {"mms", "mmd", "mmf", "mmg", "mmm"}
    if explicit and (explicit in known_entrypoints or invoked == explicit):
        return explicit
    if invoked in known_entrypoints:
        return invoked
    return primary_command


def display_title(title="MMS", *, current_command_fn=None):
    if current_command_fn is not None and current_command_fn() == "mmf":
        return "MMF"
    return title


def normalize_config_sections(
    cfg,
    *,
    ensure_provider_config,
    ensure_account_config,
    ensure_broker_config,
    normalize_ui_config,
    normalize_presets_config,
    normalize_user_config,
    normalize_cache_config,
):
    cfg, _ = ensure_provider_config(cfg)
    cfg, _ = ensure_account_config(cfg)
    cfg, _ = ensure_broker_config(cfg)
    cfg, _ = normalize_ui_config(cfg)
    cfg, _ = normalize_presets_config(cfg)
    cfg, _ = normalize_user_config(cfg)
    cfg, _ = normalize_cache_config(cfg)
    return cfg


def load_runtime_config(*, load_config, apply_local_overrides):
    cfg = load_config()
    if cfg is None:
        return None
    return apply_local_overrides(cfg)


from mms_config.snapshot_guard import (
    config_write_target_path,
    config_lock_path,
    config_audit_path,
    config_backup_root,
    sha1_file,
    backup_config_file,
    append_config_audit_entry,
    atomic_write_toml,
    config_write_caller,
    locked_file_context,
    locked_config_write,
    locked_state_file,
    config_command_hint,
    export_command_hint,
    base_user_config_path_from_gateway,
    base_user_primary_dir_from_gateway,
    active_sibling_path_from_gateway,
    merge_base_user_broker_profiles,
    config_guard_root_dir,
    config_snapshot_root,
    config_snapshot_path,
    ensure_mms_config_guard_files,
    snapshot_proxy_fingerprint,
    is_snapshot_ignored_file,
    sha256_text,
    snapshot_cli_state,
    normalize_claude_state_snapshot_payload,
    normalize_claude_settings_snapshot_payload,
    snapshot_claude_identity_entry,
    snapshot_account_entry,
    snapshot_provider_entry,
    build_config_guard_snapshot,
    snapshot_file_content_bytes,
    snapshot_file_entry,
    snapshot_digest,
    load_json_snapshot,
    write_json_snapshot,
    snapshot_period_bucket,
    update_periodic_snapshot,
    snapshot_prompt_allowed,
    confirm_startup_snapshot_drift,
    ensure_startup_snapshot_guard,
)


from mms_config.preferences import (
    load_toml_file,
    existing_paths,
    load_user_preferences_from_paths,
    apply_local_overrides,
    preference_asset_root,
    merge_dicts,
    pref_bool,
    pref_enable_disable,
    pref_reasoning_effort,
    pref_caveman_level,
    pref_agent_pack,
    sanitize_surface_list,
    sanitize_disabled_session_surfaces,
    sanitize_launch_preferences,
    sanitize_asset_roots,
    sanitize_managed_assets_root,
    sanitize_disabled_clis,
    sanitize_user_preferences,
    managed_assets_enabled,
    managed_assets_root,
    preference_disabled_clis,
    disabled_clis_for_cfg,
    cli_disabled_by_preferences,
    merge_disabled_session_surfaces,
    preference_runtime_overlay,
    runtime_with_launch_preferences,
)


from mms_commands.state_helpers import (
    iso_now,
    local_now_slug,
    load_usage_stats_from_path,
    write_usage_stats_locked,
    load_usage_stats,
    save_usage_stats,
    update_usage_stats,
)


from mms_commands.route_export_helpers import (
    trigger_routes_export_after_usage_write,
    backup_config_tree,
    refresh_routes_export_for_hive,
    trigger_routes_export_after_credentials_write,
)


def confirm_guard_accept_from_tui(
    cfg,
    *,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    confirm_startup_snapshot_drift,
    console,
):
    config_path = config_write_target_path()
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []
    if not diff_lines:
        console.print("[green]当前快照没有 drift，不需要 accept。[/green]")
        return False
    return confirm_startup_snapshot_drift(
        diff_lines,
        accepted_path=accepted_path,
        latest_path=latest_path,
    )


def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else default
    except (OSError, json.JSONDecodeError):
        return default


def save_json_file(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


from mms_commands.launch_trace import (
    record_trace_override,
    trace_source_for,
    format_launch_trace,
    launch_with_tracking,
)


from mms_commands.settings_report_handlers import (
    compact_tui_report_value,
    settings_result_tui_payload,
    settings_result_tui_available,
    select_settings_result_tui,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
    display_settings_result_report,
    model_validation_findings,
    rank_recovery_actions,
    build_model_recovery_actions,
    display_model_probe_details,
    select_provider_interactive,
    pick_recovery_actions,
    run_recovery_action,
    ensure_models_ready,
    rescue_default_fallback_report_payload,
    rescue_hot_fallback_toggle_report_payload,
    rescue_route_fallback_model_candidates,
    rescue_fallback_model_candidates,
    rescue_default_fallback,
    rescue_hot_fallback_enabled_cfg,
    set_rescue_default_fallback,
    set_rescue_hot_fallback_enabled,
    rescue_demo_packet_report_payload,
    rescue_paths_report_payload,
    rescue_handover_report_payload,
    registry_source_staleness_report_payload,
    registry_refresh_sources_report_payload,
    registry_scheduled_refresh_report_payload,
    registry_openrouter_fetch_report_payload,
    registry_openrouter_diff_report_payload,
    registry_publish_approved_report_payload,
    registry_verify_approved_report_payload,
    registry_doctor_report_payload,
)


from mms_commands.about_handlers import (
    short_update_status_label,
    format_cli_about_line,
    format_about_latest_value,
    about_check_error_summary,
    mms_upgrade_shell_command,
    cli_upgrade_shell_command,
    run_about_upgrade,
    about_tui_payload,
    snapshot_guard_tui_payload,
    display_about_version_summary,
    parse_semver_tag,
    normalize_semver_tags,
    fetch_latest_semver_tags,
    fetch_latest_semver_tag,
    extract_semver_text,
    parse_semver_text,
    compare_semver_text,
    detect_cli_version,
    fetch_npm_package_latest_version,
    git_output,
    semver_tag_gap,
    installed_update_semver,
    update_notice,
    major_update_notice,
    start_async_update_check,
    mms_update_status,
    release_track_for_channel,
    release_version_info,
    cli_version_status,
    refresh_update_cache_for_about,
    about_status_snapshot,
)


def render_mms_config_agents_guard():
    return """# AGENTS.md

This folder stores the real MMS user config.

## MMS Config Human Gate

- Any agent, any repo, any automation touching this folder must stop and require human confirmation before write.
- Before every write, create a timestamped backup first. Never overwrite in place without a backup.
- Applies to the whole MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and any account state under this folder.
- Agents may inspect, diff, and propose changes, but must not auto-apply user config edits without human confirmation.
- Any proposed change must show target path, affected fields/files, before/after values, and reason.
- If the process is running inside an isolated HOME or gateway session, still resolve and protect the real user config under `~/.config/mms`.
"""


def render_mms_config_claude_guard():
    return """# CLAUDE.md

This folder stores the real MMS user config.

## Claude Hard Rule

- Claude must treat this folder as human-only config.
- Claude must never auto-write MMS user config without explicit human confirmation.
- Before every write, Claude must create a timestamped backup first.
- Claude may only inspect, explain, and generate manual diffs for changes to this folder until the human confirms.
- This applies to the full MMS config tree, including `config.toml`, `override.toml`, `credentials.sh`, `usage.json`, `accounts/**`, `env/**`, and account state files.
- If Claude is about to touch these files, it must stop and report the exact path, intended change, before/after values, and reason.
"""


from mms_commands.manage_handlers import (
    build_manage_targets,
    select_manage_target_fallback,
    select_manage_target,
    run_manage_channels,
    run_connect_wizard,
    manage_provider_target,
    prompt_account_rename,
    manage_account_target,
    run_account_mgmt_tui,
    run_recommend_mgmt_tui,
    format_rescue_hot_fallback_event,
    latest_rescue_hot_fallback_event,
    rescue_landing_tui_payload,
    registry_truth_tui_payload,
)


def model_source_label(source):
    mapping = {
        "remote": "远端列表",
        "fallback": "内置回退",
        "manual": "手工列表",
        "extra": "手工补充",
        "derived_alias": "本地别名",
    }
    return mapping.get(str(source or "").strip(), str(source or "-").strip() or "-")


def ttfb_label(ttfb_ms):
    if not isinstance(ttfb_ms, (int, float)):
        return "暂无数据"
    if ttfb_ms < 1200:
        return "很快"
    if ttfb_ms < 2500:
        return "正常"
    if ttfb_ms < 4500:
        return "偏慢"
    return "很慢"


def tps_label(tps_value):
    if not isinstance(tps_value, (int, float)):
        return "暂无数据"
    if tps_value >= 80:
        return "很快"
    if tps_value >= 40:
        return "正常"
    if tps_value >= 20:
        return "偏慢"
    return "很慢"


from mms_commands.model_probe import (
    usage_rows_for_runtime,
    usage_summary_for_runtime,
    infer_model_family,
    model_info_looks_domestic,
    mms_model_visible,
    filter_visible_models,
    model_info_has_visible_models,
    vision_sidecar_model_candidates_for_provider,
    vision_sidecar_candidate_pairs,
    runtime_with_vision_sidecar,
    native_clis_for_model,
    model_context_window,
    model_matches_account_cli,
    model_matches_cli_family,
    models_for_cli_family,
    provider_models_for_cli,
    provider_supports_cli_name,
    provider_supports_model_for_cli,
    probe_file_cache_path,
    invalidate_probe_cache,
    probe_cache_age,
    load_probe_file_cache,
    save_probe_file_cache,
    base_probe_result_from_cache,
    probe_models,
    probe_models_for_startup,
    warm_probe_cache_async,
    select_provider_for_warm,
    fetch_models,
    ensure_models_cache_available,
)


from mms_commands.connect_setup import (
    check_cli_installed,
    prompt_provider_credentials,
    quick_connect_official,
    quick_connect_gateway,
    select_cli,
    setup_provider_credentials,
    setup_api_credentials,
    ensure_provider_credentials,
    ensure_api_credentials,
    setup_wizard,
)


from mms_commands.model_probe import (
    provider_supports_mimo_anthropic_selectors,
    derived_model_aliases,
    apply_provider_model_patch,
    provider_candidates,
    provider_effective_models,
    is_installed_mms_layout,
    default_gpt_reasoning_effort,
    default_reasoning_effort_for_model_info,
    bridge_clis_for_model,
    model_supports_vision,
    model_cli_modes,
    model_cli_summary,
    model_capability_tags,
    model_capability_summary,
)


from mms_commands.provider_config import (
    env_file_path,
    shell_quote,
    parse_shell_value,
    load_env_file,
    account_map,
    accounts_for_cli,
    get_provider_definition,
    get_account_definition,
    normalize_provider_id_input,
    sanitize_provider_id,
    normalize_model_id_list,
    unique_runtime_id,
    normalize_models_endpoint,
    provider_env_name,
    provider_map,
    provider_label,
    provider_openai_base_url,
    provider_anthropic_base_url,
    provider_has_configured_base_url,
    provider_id_variants,
    resolve_config_provider_id,
    config_truthy,
    provider_template_payload,
    select_provider_template,
    ensure_interactive_terminal,
    parse_csv_values,
    prompt_csv_values,
    prompt_provider_metadata,
    prompt_account_metadata,
    normalize_supported_clis,
    normalize_role,
    normalize_positive_seconds,
    default_provider,
    normalize_priority,
    canonical_model_family,
    normalize_family_priority_overrides,
    runtime_priority_for_family,
    runtime_priority_for_model,
    runtime_with_priority,
    normalize_claude_1m_mode,
    normalize_timezone_name,
    runtime_force_ipv4,
    normalize_provider,
    default_account_home,
    normalize_account,
    normalize_account_id,
    account_label,
    upsert_provider,
    delete_provider_credentials,
    ensure_provider_config,
    ensure_account_config,
    load_provider_credentials,
    save_provider_credentials,
    load_api_credentials,
    save_api_credentials,
    default_config,
    migrate_legacy_api_config,
    resolve_provider_context,
    resolve_account_context,
    save_provider_credentials_with_probe,
    provider_env_value,
    target_account_home,
    migrate_accounts_dirs,
)


from mms_commands.account_runtime import (
    scrub_account_command_env,
    account_env,
    account_status_command,
    probe_account_status,
    run_account_login,
)


from mms_commands.network_helpers import (
    url_matches_host_suffix,
    runtime_should_disable_ambient_env,
    runtime_httpx_kwargs,
    validate_proxy_url,
    test_proxy_connectivity,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
)


from mms_commands.config_normalizers import (
    normalize_preset_entry,
    normalize_presets_config,
    normalize_user_config,
    normalize_cache_config,
    probe_async_refresh_after,
    probe_async_min_interval,
)


from mms_commands.config_edit_helpers import (
    mask_key,
    set_nested,
    get_nested,
    unset_nested,
    coerce_config_value,
    validate_config,
)


from mms_commands.usage_helpers import (
    usage_key,
    rename_usage_account,
    rename_usage_provider,
    parse_usage_timestamp,
    usage_recency_score,
    sort_family_entries_for_tui,
    family_is_cold_for_tui,
    build_model_families_for_cli,
)


from mms_commands.openrouter_helpers import (
    provider_looks_openrouter,
    openrouter_provider_candidates,
    parse_openrouter_extension_args,
    openrouter_extension_provider,
    handle_openrouter_extension_config,
)


from mms_commands.runtime_source_helpers import (
    resolve_best_provider,
    provider_options_for_model,
    account_options_for_model,
    resolve_provider_for_cli,
    resolve_launch_runtime,
    resolve_provider_runtime,
    resolve_source_default_index,
    runtime_choice_label,
    list_runtime_sources,
    choose_runtime_source,
)


def ensure_probe_async_executor(current_executor, *, set_executor, executor_factory):
    if current_executor is None:
        current_executor = executor_factory()
        set_executor(current_executor)
    return current_executor


def schedule_probe_refresh(
    provider,
    cfg=None,
    *,
    reason="stale",
    default_provider_id,
    probe_async_min_interval,
    lock,
    inflight,
    last_started,
    probe_models,
    ensure_probe_async_executor,
    time_func,
):
    provider_id = provider.get("id", default_provider_id)
    min_interval = probe_async_min_interval(cfg)

    with lock:
        if provider_id in inflight:
            return False
        last_at = last_started.get(provider_id, 0)
        if time_func() - last_at < min_interval:
            return False
        inflight.add(provider_id)
        last_started[provider_id] = time_func()

    def _runner():
        try:
            probe_models(provider, emit_output=False, skip_cache=True)
        except Exception:
            pass
        finally:
            with lock:
                inflight.discard(provider_id)

    ensure_probe_async_executor().submit(_runner)
    return True


def snapshot_diff_lines(previous_snapshot, current_snapshot, *, is_snapshot_ignored_file):
    diffs = []
    previous_snapshot = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    current_snapshot = current_snapshot if isinstance(current_snapshot, dict) else {}

    previous_defaults = previous_snapshot.get("defaults") or {}
    current_defaults = current_snapshot.get("defaults") or {}
    if previous_defaults != current_defaults:
        diffs.append("default route/account changed")

    previous_accounts = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    current_accounts = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("accounts", [])
        if isinstance(item, dict)
    }
    for account_id in sorted(set(previous_accounts) | set(current_accounts)):
        previous_entry = previous_accounts.get(account_id)
        current_entry = current_accounts.get(account_id)
        if previous_entry is None:
            diffs.append(f"account added: {account_id}")
            continue
        if current_entry is None:
            diffs.append(f"account removed: {account_id}")
            continue
        field_labels = {
            "cli": "cli",
            "enabled": "enabled",
            "home_dir": "home_dir",
            "priority": "priority",
            "claude_1m_mode": "claude_1m_mode",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
            "identity_sha256": "identity",
        }
        for field_name, field_label in field_labels.items():
            if field_name == "identity_sha256":
                previous_value = previous_entry.get(field_name, "")
                current_value = current_entry.get(field_name, "")
            else:
                previous_value = previous_entry.get(field_name)
                current_value = current_entry.get(field_name)
            if field_name == "identity_sha256" and field_name not in previous_entry:
                continue
            if previous_value != current_value:
                if field_name == "proxy_sha256":
                    old_value = previous_entry.get("proxy_fingerprint")
                    new_value = current_entry.get("proxy_fingerprint")
                elif field_name == "identity_sha256":
                    old_value = previous_entry.get("identity_fingerprint")
                    new_value = current_entry.get("identity_fingerprint")
                else:
                    old_value = previous_entry.get(field_name)
                    new_value = current_entry.get(field_name)
                diffs.append(f"account {account_id} {field_label}: {old_value} -> {new_value}")

    previous_providers = {
        str(item.get("id") or "").strip(): item
        for item in previous_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    current_providers = {
        str(item.get("id") or "").strip(): item
        for item in current_snapshot.get("providers", [])
        if isinstance(item, dict)
    }
    for provider_id in sorted(set(previous_providers) | set(current_providers)):
        previous_entry = previous_providers.get(provider_id)
        current_entry = current_providers.get(provider_id)
        if previous_entry is None:
            diffs.append(f"provider added: {provider_id}")
            continue
        if current_entry is None:
            diffs.append(f"provider removed: {provider_id}")
            continue
        field_labels = {
            "enabled": "enabled",
            "priority": "priority",
            "models_endpoint": "models_endpoint",
            "timezone": "timezone",
            "force_ipv4": "force_ipv4",
            "no_proxy": "no_proxy",
            "proxy_sha256": "proxy",
        }
        for field_name, field_label in field_labels.items():
            if previous_entry.get(field_name) != current_entry.get(field_name):
                old_value = previous_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else previous_entry.get(field_name)
                new_value = current_entry.get("proxy_fingerprint") if field_name == "proxy_sha256" else current_entry.get(field_name)
                diffs.append(f"provider {provider_id} {field_label}: {old_value} -> {new_value}")

    previous_files = {
        str(item.get("path") or ""): item
        for item in previous_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    current_files = {
        str(item.get("path") or ""): item
        for item in current_snapshot.get("files", [])
        if isinstance(item, dict) and not is_snapshot_ignored_file(item.get("path"))
    }
    for path in sorted(set(previous_files) | set(current_files)):
        if os.path.basename(str(path or "")) == ".claude.json":
            continue
        previous_entry = previous_files.get(path)
        current_entry = current_files.get(path)
        if previous_entry is None:
            diffs.append(f"file added: {path}")
            continue
        if current_entry is None:
            diffs.append(f"file removed: {path}")
            continue
        if bool(previous_entry.get("exists")) != bool(current_entry.get("exists")):
            diffs.append(f"file presence changed: {path}")
            continue
        if previous_entry.get("sha256") != current_entry.get("sha256"):
            diffs.append(f"file changed: {path}")
    return diffs


def normalize_user_role(role, *, mode_all, mode_recommended):
    value = str(role or "").strip()
    if value in {"dev", "all", mode_all}:
        return mode_all
    if value in {"ops", "recommended", mode_recommended}:
        return mode_recommended
    return mode_all


from mms_commands.launch_selection import (
    runtime_usage_key,
    resolve_model_name,
    runtime_hint_from_runtime,
    record_usage,
    record_scene_usage,
    infer_runtime_hint_from_usage_stats,
    get_scene_usage,
    resolve_last_used_runtime,
    all_provider_models_for_cli,
    aggregate_provider_models,
    categorize_models,
    display_models,
    filter_models_for_display,
    group_models_for_custom,
    group_models_by_family_and_provider,
    select_custom_model,
    select_model_interactive,
    build_provider_options_map,
    make_provider_options_loader,
    apply_runtime_priority_changes,
    resolve_visible_clis,
    use_tui,
    clean_model_info,
    uses_native_account_entry,
    uses_broker_entry,
    uses_managed_entry,
    DIRECT_CLI_LAUNCH_DEFAULTS,
    resolve_direct_cli_launch_default,
    resolve_interactive_launch_model,
    preset_model_info,
    save_preset_interactive,
)


def available_broker_profiles_for_cli(_cfg, _cli_name):
    return []


def broker_enabled_by_cli(cfg, cli_names, *, available_broker_profiles_for_cli=available_broker_profiles_for_cli):
    return {
        cli_name: bool(available_broker_profiles_for_cli(cfg, cli_name))
        for cli_name in (cli_names or [])
    }


def select_broker_profile_interactive(
    cfg,
    cli_name,
    *,
    available_broker_profiles_for_cli,
    ensure_rich,
    table_cls,
    prompt_ask,
    console,
):
    profiles = available_broker_profiles_for_cli(cfg, cli_name)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    ensure_rich()
    table = table_cls(title="Broker Experiment", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("设备/工作区", style="yellow")
    table.add_column("Broker", style="blue")
    table.add_column("Remote", style="magenta")
    for idx, profile in enumerate(profiles, 1):
        table.add_row(
            str(idx),
            str(profile.get("id", "")),
            f"{profile.get('device_id', '-')}/{profile.get('workspace_id', '-')}",
            str(profile.get("broker_base_url") or "-"),
            str(profile.get("remote_service_label") or profile.get("remote_service_base_url") or "-"),
        )
    console.print(table)

    while True:
        raw = prompt_ask("选择 broker profile，直接回车取消", default="").strip()
        if not raw:
            return None
        if raw.isdigit():
            picked = int(raw)
            if 1 <= picked <= len(profiles):
                return profiles[picked - 1]
        console.print("[yellow]请输入有效编号[/yellow]")


def launch_broker_experiment_interactive(
    cfg,
    cli_name,
    *,
    select_broker_profile_interactive,
    run_broker_profile_interactive,
    console,
):
    profile = select_broker_profile_interactive(cfg, cli_name)
    if profile is None:
        return False

    console.print(
        f"[cyan]Broker experiment[/cyan] -> {profile['name']} "
        f"[dim]({profile['device_id']}/{profile['workspace_id']})[/dim]"
    )
    console.print("[dim]支持续最近 / 新开 / 切换旧会话；默认直接回车续最近。[/dim]")
    exit_code = run_broker_profile_interactive(cfg, profile["id"])
    if exit_code != 0:
        console.print(f"[red]broker experiment 启动失败，退出码 {exit_code}[/red]")
    return True


def opencode_default_profile_from_config(cfg, *, opencode_profile_selection, default_profile=None):
    opencode = cfg.get("opencode") if isinstance(cfg, dict) and isinstance(cfg.get("opencode"), dict) else {}
    return opencode_profile_selection(opencode.get("default_profile") or opencode.get("profile") or default_profile)


def build_opencode_resolver_deps(
    *,
    resolver_deps_cls,
    provider_candidates,
    provider_effective_models,
    provider_supports_cli_name,
    provider_supports_model_for_cli,
    provider_label,
    provider_openai_base_url,
    provider_anthropic_base_url,
    infer_model_family,
    normalize_role,
    runtime_priority_for_model,
    runtime_with_priority,
    mms_model_visible,
    load_route_health_latest,
    route_health_for_route,
    route_health_allows_route,
    route_health_sort_key,
    apply_profile,
    apply_entrypoint,
    role_weights,
    default_priority,
    default_provider_id,
):
    return resolver_deps_cls(
        provider_candidates=provider_candidates,
        provider_effective_models=provider_effective_models,
        provider_supports_cli_name=provider_supports_cli_name,
        provider_supports_model_for_cli=provider_supports_model_for_cli,
        provider_label=provider_label,
        provider_openai_base_url=provider_openai_base_url,
        provider_anthropic_base_url=provider_anthropic_base_url,
        infer_model_family=infer_model_family,
        normalize_role=normalize_role,
        runtime_priority_for_model=runtime_priority_for_model,
        runtime_with_priority=runtime_with_priority,
        mms_model_visible=mms_model_visible,
        load_route_health_latest=load_route_health_latest,
        route_health_for_route=route_health_for_route,
        route_health_allows_route=route_health_allows_route,
        route_health_sort_key=route_health_sort_key,
        apply_profile=apply_profile,
        apply_entrypoint=apply_entrypoint,
        role_weights=role_weights,
        default_priority=default_priority,
        default_provider_id=default_provider_id,
    )


def find_opencode_model_route(
    cfg,
    default_provider,
    default_models,
    model_names,
    *,
    opencode_resolver_deps,
    find_opencode_model_route_impl,
    route_key="route",
    route_policy="",
    profile_id="agent",
    provider_id="",
):
    return find_opencode_model_route_impl(
        cfg,
        default_provider,
        default_models,
        model_names,
        deps=opencode_resolver_deps(),
        route_key=route_key,
        route_policy=route_policy,
        profile_id=profile_id,
        provider_id=provider_id,
    )


from mms_commands.launch_trace import (
    trace_runtime_provider_id,
    trace_runtime_account_id,
    trace_runtime_bridge,
    runtime_source_kind_label,
    trace_runtime_choice,
)


def http_status_is_success(value):
    try:
        status_code = int(str(value or "").strip())
    except (TypeError, ValueError):
        return False
    return 200 <= status_code < 300


from mms_commands.config_handlers import (
    handle_config_get,
    handle_config_set,
    handle_config_unset,
    handle_config_validate,
    handle_config,
    handle_config_file,
    handle_api_config,
    handle_config_migrate,
    handle_provider_default_config,
    handle_provider_add_config,
)


def update_provider_model_overrides(
    cfg,
    provider_id,
    *,
    extra_models=None,
    hidden_models=None,
    models_endpoint=None,
    normalize_model_id_list=normalize_model_id_list,
    normalize_models_endpoint=normalize_models_endpoint,
    normalize_provider,
    save_config,
    invalidate_probe_cache,
    load_config,
):
    from mms_commands.config_handlers import update_provider_model_overrides as _impl

    return _impl(
        cfg,
        provider_id,
        extra_models=extra_models,
        hidden_models=hidden_models,
        models_endpoint=models_endpoint,
        normalize_model_id_list=normalize_model_id_list,
        normalize_models_endpoint=normalize_models_endpoint,
        normalize_provider=normalize_provider,
        save_config=save_config,
        invalidate_probe_cache=invalidate_probe_cache,
        load_config=load_config,
    )


def manage_provider_models(
    cfg,
    provider_id,
    *,
    ensure_rich,
    resolve_provider_context,
    probe_models,
    model_source_label,
    use_tui,
    select_channel_action_tui,
    clear_console,
    display_provider_model_table,
    pause_after_tui_report,
    prompt_ask,
    update_provider_model_overrides,
    panel_cls,
    console,
    normalize_model_id_list=normalize_model_id_list,
    normalize_models_endpoint=normalize_models_endpoint,
    refresh_all_provider_model_defaults=None,
):
    from mms_commands.config_handlers import manage_provider_models as _impl

    return _impl(
        cfg,
        provider_id,
        ensure_rich=ensure_rich,
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        model_source_label=model_source_label,
        use_tui=use_tui,
        select_channel_action_tui=select_channel_action_tui,
        clear_console=clear_console,
        display_provider_model_table=display_provider_model_table,
        pause_after_tui_report=pause_after_tui_report,
        prompt_ask=prompt_ask,
        update_provider_model_overrides=update_provider_model_overrides,
        panel_cls=panel_cls,
        console=console,
        normalize_model_id_list=normalize_model_id_list,
        normalize_models_endpoint=normalize_models_endpoint,
        refresh_all_provider_model_defaults=refresh_all_provider_model_defaults,
    )


from mms_commands.config_handlers import (
    handle_provider_edit_config,
    handle_provider_remove_config,
    handle_provider_credentials_config,
    handle_provider_rename_config,
    handle_account_default_config,
    handle_account_add_config,
    handle_account_edit_config,
    handle_account_remove_config,
    handle_account_status_config,
    handle_account_login_config,
    handle_account_rename_config,
)


from mms_commands.session_handlers import (
    session_status_label,
    session_display_id,
    handle_session_ls,
    handle_session_info,
    session_gateway_roots,
    session_dir_size_bytes,
    format_bytes,
    list_stale_gateway_sessions,
    split_cli_prefixed_resume_ref,
    codex_resume_roots,
    iter_codex_index_records,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
    resume_resolution_diagnostics,
    first_resume_model,
    session_resume_model,
    handle_resume_command,
    handle_session_prune,
)


def resolve_resume_target(
    session_ref,
    cli_hint="auto",
    *,
    split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
    resolve_codex_resume_ref,
    resolve_claude_resume_ref,
    uuid_resume_cli_hint,
):
    from mms_commands.session_handlers import resolve_resume_target as _impl

    return _impl(
        session_ref,
        cli_hint,
        split_cli_prefixed_resume_ref=split_cli_prefixed_resume_ref,
        resolve_codex_resume_ref=resolve_codex_resume_ref,
        resolve_claude_resume_ref=resolve_claude_resume_ref,
        uuid_resume_cli_hint=uuid_resume_cli_hint,
    )


def resolve_resume_runtime_and_model(
    cfg,
    cli,
    args,
    default_provider,
    default_models,
    session_record,
    *,
    get_scene_usage,
    session_resume_model=session_resume_model,
    resolve_last_used_runtime,
    trace_runtime_choice,
    choose_runtime_source,
    resolve_model_name=resolve_model_name,
    first_resume_model=first_resume_model,
    uses_managed_entry,
    runtime_with_launch_preferences,
):
    from mms_commands.session_handlers import resolve_resume_runtime_and_model as _impl

    return _impl(
        cfg,
        cli,
        args,
        default_provider,
        default_models,
        session_record,
        get_scene_usage=get_scene_usage,
        session_resume_model=session_resume_model,
        resolve_last_used_runtime=resolve_last_used_runtime,
        trace_runtime_choice=trace_runtime_choice,
        choose_runtime_source=choose_runtime_source,
        resolve_model_name=resolve_model_name,
        first_resume_model=first_resume_model,
        uses_managed_entry=uses_managed_entry,
        runtime_with_launch_preferences=runtime_with_launch_preferences,
    )


def is_config_help_request(args_rest):
    if not args_rest:
        return False
    key_path = str(args_rest[0] or "").strip()
    return key_path in CONFIG_HELP_TOPICS


def is_help_request(argv):
    if not argv:
        return False
    if argv[0] == "help":
        return True
    if argv[0] == "config" and is_config_help_request(argv[1:]):
        return True
    return any(str(arg).strip() in {"-h", "--help"} for arg in argv)


def is_setup_web_request(argv):
    if not argv:
        return False
    command = str(argv[0] or "").strip()
    if command in {"setup", "setup-web", "web-setup"}:
        return True
    if command != "config" or len(argv) < 2:
        return False
    return str(argv[1] or "").strip() in {"web", "webui", "setup.web", "setup-web"}


def is_session_prune_dry_run(argv):
    if len(argv) < 2:
        return False
    if argv[0] != "session" or argv[1] != "prune":
        return False
    return "--apply" not in argv


from mms_commands.standalone_handlers import (
    handle_logs_command,
    handle_exposure_command,
    handle_cache_command,
    handle_guard_command,
)


from mms_commands.launcher_handlers import (
    handle_session_command,
    handle_env_command,
    handle_activate_command,
    handle_models_command,
    select_provider_for_models,
    pick_manual_models,
    warm_model_request,
)


def detect_working_base_url(
    configured_url,
    path,
    headers,
    body=None,
    timeout=5,
    runtime=None,
    *,
    ensure_httpx,
    get_httpx,
    runtime_httpx_request,
):
    ensure_httpx()
    if get_httpx() is None:
        return None
    url = configured_url.rstrip("/")
    candidates = [url[:-3], url] if url.endswith("/v1") else [url, url + "/v1"]
    for candidate in candidates:
        try:
            if body is not None:
                resp = runtime_httpx_request(
                    "POST",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    content=body,
                    timeout=timeout,
                )
            else:
                resp = runtime_httpx_request(
                    "GET",
                    f"{candidate}{path}",
                    runtime=runtime,
                    headers=headers,
                    timeout=timeout,
                )
            if resp.status_code == 200:
                return candidate
        except Exception:
            continue
    return None


from mms_commands.launcher_handlers import (
    handle_warm_command,
    handle_export,
    emit_preset_error,
    preset_env_file_path,
    resolve_named_preset,
    infer_preset_auth_mode,
    resolve_preset_export_runtime,
    handle_presets_command,
)


from mms_commands.display_handlers import (
    display_config_help,
    display_preferences_path,
    display_preferences_example,
    display_human_gate_help,
    display_preferences_help,
    display_usage_stats,
    display_adapter_registry,
    display_providers,
    display_accounts,
    recent_models_for_provider,
    display_runtime_usage,
    display_provider_model_table,
    display_openrouter_extension_help,
    display_openrouter_model_rows,
    display_openrouter_video_rows,
    display_openrouter_extension_summary,
    display_config,
)


from mms_commands.standalone_handlers import (
    run_script_subcommand,
    handle_doctor_command,
    handle_test_command,
    handle_opencode_smoke_command,
)
