"""Core adapter for the MMS TUI launcher entrypoint."""

from __future__ import annotations

import os


def handle_tui_launcher_selection(core, cfg, provider, once, cli_names, account_id=None, provider_id=None):
    """Run the TUI launcher flow using dependency hooks from ``mms_core``."""
    from mms_tui import select_family_tui, select_submodel_tui, confirm_tui
    import mms_launcher.tui_flow as tui_flow
    from mms_launchers import (
        _caveman_available_for_cli,
        _ecc_available_for_claude,
        _nsr_available_for_cli,
        _omc_available_for_claude,
        get_export_env,
    )

    current_provider = provider
    current_cli_names = cli_names
    default_models = core._probe_models(current_provider, emit_output=False).get("models")
    if account_id or provider_id:
        core._trace_record("CLI flags", account=account_id, provider=provider_id)

    family_payload_deps = tui_flow.TuiFamilyPayloadDeps(
        build_model_families_for_cli=core._build_model_families_for_cli,
        cli_default_family_first=core._CLI_DEFAULT_FAMILY_FIRST,
        family_is_cold_for_tui=core._family_is_cold_for_tui,
        sort_family_entries_for_tui=core._sort_family_entries_for_tui,
        make_provider_options_loader=core._make_provider_options_loader,
    )

    def _runtime_refresh_deps(rmtree):
        return tui_flow.TuiRuntimeRefreshDeps(
            probe_cache=core._PROBE_CACHE,
            probe_file_cache_dir=core._PROBE_FILE_CACHE_DIR,
            rmtree=rmtree,
            ensure_provider_credentials=core.ensure_provider_credentials,
            probe_models=core._probe_models,
            resolve_visible_clis=core._resolve_visible_clis,
        )

    def _refresh_runtime_state_after_config_change(updated_cfg):
        import shutil as _shutil

        return tui_flow.refresh_tui_runtime_state_after_config_change(
            updated_cfg,
            deps=_runtime_refresh_deps(_shutil.rmtree),
        )

    def _apply_tui_priority_changes(cfg_arg, priority_changes):
        return tui_flow.apply_tui_priority_changes(
            cfg_arg,
            priority_changes,
            apply_runtime_priority_changes=core._apply_runtime_priority_changes,
            save_config=core.save_config,
            export_model_routes_loader=tui_flow.load_export_model_routes,
        )

    launch_candidate_deps = tui_flow.TuiLaunchCandidateDeps(
        select_submodel_tui=select_submodel_tui,
        account_id=account_id,
        provider_id=provider_id,
        apply_priority_changes=_apply_tui_priority_changes,
        resolve_last_used_runtime=core._resolve_last_used_runtime,
        resolve_best_provider=core._resolve_best_provider,
        choose_runtime_source=core._choose_runtime_source,
        trace_record=core._trace_record,
        trace_runtime_choice=core._trace_runtime_choice,
        provider_browse_tui_loader=tui_flow.load_provider_browse_tui_tools,
        provider_candidates=core._provider_candidates,
        default_provider_id=core.DEFAULT_PROVIDER_ID,
        provider_supports_cli_name=core._provider_supports_cli_name,
        provider_label=core._provider_label,
        resolve_provider_context=core.resolve_provider_context,
        probe_models=core._probe_models,
        filter_visible_models=core._filter_visible_models,
        agy_connect_profile_id=core._AGY_CONNECT_PROFILE_ID,
        connect_action=lambda cfg_arg, cli_arg: tui_flow.handle_tui_connect_action(
            cfg_arg,
            cli_arg,
            quick_connect_official=core._quick_connect_official,
            run_connect_wizard=core.run_connect_wizard,
            refresh_runtime_state=_refresh_runtime_state_after_config_change,
        ),
        resolve_opencode_profile_runtime=core._resolve_opencode_profile_runtime,
        resolve_account_context=core.resolve_account_context,
    )

    launch_confirmation_deps = tui_flow.TuiLaunchConfirmationDeps(
        once=once,
        check_cli_installed=core.check_cli_installed,
        check_and_offer_install_loader=tui_flow.load_check_and_offer_install,
        select_and_apply_opencode_profile=core._select_and_apply_opencode_profile,
        runtime_with_launch_preferences=core._runtime_with_launch_preferences,
        runtime_with_vision_sidecar=core._runtime_with_vision_sidecar,
        clean_model_info=core._clean_model_info,
        get_export_env=get_export_env,
        network_guard_preview_loader=tui_flow.load_claude_network_guard_preview,
        confirm_tui=confirm_tui,
        confirm_context_lines=core._confirm_context_lines,
        caveman_available_for_cli=_caveman_available_for_cli,
        nsr_available_for_cli=_nsr_available_for_cli,
        ecc_available_for_claude=_ecc_available_for_claude,
        omc_available_for_claude=_omc_available_for_claude,
        model_info_looks_domestic=core._model_info_looks_domestic,
        default_reasoning_effort_for_model_info=core._default_reasoning_effort_for_model_info,
        build_confirm_preview_catalog=core._build_confirm_preview_catalog,
        network_guard_enforcer_loader=tui_flow.load_claude_network_guard_enforcer,
        merge_disabled_session_surfaces=core._merge_disabled_session_surfaces,
        launch_with_tracking=core._launch_with_tracking,
    )

    def _settings_action_deps():
        from mms_tui import (
            select_channel_action_tui,
            select_language_tui,
            select_rescue_event_tui,
            select_settings_tui,
            select_provider_mgmt_tui,
        )

        return tui_flow.TuiSettingsActionDeps(
            select_settings_tui=select_settings_tui,
            select_channel_action_tui=select_channel_action_tui,
            select_language_tui=select_language_tui,
            select_rescue_event_tui=select_rescue_event_tui,
            select_provider_mgmt_tui=select_provider_mgmt_tui,
            save_config=core.save_config,
            probe_cache=core._PROBE_CACHE,
            ensure_provider_credentials=core.ensure_provider_credentials,
            probe_models=core._probe_models,
            provider_mgmt_export_model_routes_loader=tui_flow.load_export_model_routes,
            routes_export_loader=tui_flow.load_model_routes_exporter,
            registry_cli_loader=tui_flow.load_registry_cli_tools,
            registry_truth_tui_payload=core._registry_truth_tui_payload,
            print_settings_error_report=core._print_settings_error_report,
            print_settings_result_report=core._print_settings_result_report,
            registry_report_payloads={
                "source_staleness": core._registry_source_staleness_report_payload,
                "refresh_sources": core._registry_refresh_sources_report_payload,
                "scheduled_refresh": core._registry_scheduled_refresh_report_payload,
                "openrouter_fetch": core._registry_openrouter_fetch_report_payload,
                "openrouter_diff": core._registry_openrouter_diff_report_payload,
                "publish_approved": core._registry_publish_approved_report_payload,
                "verify_approved": core._registry_verify_approved_report_payload,
                "doctor": core._registry_doctor_report_payload,
            },
            pause_after_tui_report=core._pause_after_tui_report,
            localize=core._L,
            about_status_snapshot=core._about_status_snapshot,
            about_tui_payload=core._about_tui_payload,
            run_about_upgrade=core._run_about_upgrade,
            snapshot_guard_tui_payload=core._snapshot_guard_tui_payload,
            handle_guard_command=core.handle_guard_command,
            confirm_guard_accept_from_tui=core._confirm_guard_accept_from_tui,
            run_account_mgmt_tui=core._run_account_mgmt_tui,
            rescue_tools_loader=tui_flow.load_rescue_tools,
            rescue_default_fallback=core._rescue_default_fallback,
            rescue_hot_fallback_enabled_cfg=core._rescue_hot_fallback_enabled_cfg,
            rescue_route_fallback_model_candidates=core._rescue_route_fallback_model_candidates,
            latest_rescue_hot_fallback_event=core._latest_rescue_hot_fallback_event,
            rescue_landing_tui_payload=core._rescue_landing_tui_payload,
            set_rescue_default_fallback=core._set_rescue_default_fallback,
            rescue_default_fallback_report_payload=core._rescue_default_fallback_report_payload,
            select_model_tui_loader=tui_flow.load_select_model_tui,
            set_rescue_hot_fallback_enabled=core._set_rescue_hot_fallback_enabled,
            rescue_hot_fallback_toggle_report_payload=core._rescue_hot_fallback_toggle_report_payload,
            rescue_demo_packet_report_payload=core._rescue_demo_packet_report_payload,
            rescue_fallback_model_candidates=core._rescue_fallback_model_candidates,
            rescue_handover_report_payload=core._rescue_handover_report_payload,
            rescue_paths_report_payload=core._rescue_paths_report_payload,
            console=core.console,
            ensure_rich=core._ensure_rich,
            prompt_cls=core.Prompt,
            set_language=core.set_language,
        )

    return tui_flow.run_tui_launcher_loop(
        cfg,
        current_provider,
        default_models,
        current_cli_names,
        deps=tui_flow.TuiLauncherLoopDeps(
            select_family_tui=select_family_tui,
            get_scene_usage=core._get_scene_usage,
            broker_enabled_by_cli=core._broker_enabled_by_cli,
            opencode_profile_menu_options=core._opencode_profile_menu_options,
            official_account_menu_options=core._official_account_menu_options,
            launch_broker_experiment_interactive=core._launch_broker_experiment_interactive,
            settings_action_deps_loader=_settings_action_deps,
            settings_repo_root=os.getcwd(),
            family_payload_deps=family_payload_deps,
            launch_candidate_deps=launch_candidate_deps,
            launch_confirmation_deps=launch_confirmation_deps,
            console=core.console,
        ),
    )
