"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations


from mms_commands.command_predicates import (
    CONFIG_HELP_TOPICS,
    is_config_help_request,
    is_help_request,
    is_setup_web_request,
    is_session_prune_dry_run,
)


from mms_commands.command_metadata import (
    resolve_ui_language,
    extract_global_lang,
    current_command,
    display_title,
)


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


from mms_commands.config_guard_helpers import (
    confirm_guard_accept_from_tui,
    load_json_file,
    save_json_file,
    render_mms_config_agents_guard,
    render_mms_config_claude_guard,
    snapshot_diff_lines,
)


from mms_commands.display_labels import (
    model_source_label,
    ttfb_label,
    tps_label,
)


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
    ensure_probe_async_executor,
    schedule_probe_refresh,
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
    detect_working_base_url,
    http_status_is_success,
    validate_proxy_url,
    test_proxy_connectivity,
    prompt_validated_proxy_fields,
    prompt_validated_timezone,
)


from mms_commands.config_normalizers import (
    normalize_ui_config,
    normalize_user_role,
    normalize_preset_entry,
    normalize_presets_config,
    normalize_user_config,
    normalize_cache_config,
    normalize_config_sections,
    load_runtime_config,
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


from mms_commands.broker_helpers import (
    available_broker_profiles_for_cli,
    broker_enabled_by_cli,
    select_broker_profile_interactive,
    launch_broker_experiment_interactive,
)


from mms_commands.opencode_helpers import (
    opencode_default_profile_from_config,
    build_opencode_resolver_deps,
    find_opencode_model_route,
)


from mms_commands.launch_trace import (
    trace_runtime_provider_id,
    trace_runtime_account_id,
    trace_runtime_bridge,
    runtime_source_kind_label,
    trace_runtime_choice,
)


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
