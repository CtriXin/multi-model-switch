from __future__ import annotations

from mms_launcher.tui_flow import (
    apply_confirm_bypass_flag,
    apply_claude_network_guard_preview,
    apply_confirm_runtime_preferences,
    apply_launch_runtime_preferences,
    apply_opencode_profile_for_launch,
    apply_rescue_clear_default_action,
    apply_rescue_default_from_action,
    apply_rescue_default_fallback_action,
    apply_rescue_default_from_route_selection,
    apply_rescue_demo_packet_action,
    apply_rescue_hot_fallback_toggle_action,
    apply_tui_priority_changes,
    apply_tui_launcher_state_result,
    build_confirm_capability_context,
    confirm_agent_pack,
    confirm_tui_options,
    create_rescue_handover_action,
    create_rescue_handover_from_action,
    create_rescue_handover_from_route_selection,
    enforce_confirm_bypass_network_guard,
    ensure_cli_installed_for_launch,
    execute_confirmed_launch,
    handle_tui_account_mgmt_settings_action,
    handle_tui_about_settings_action,
    handle_tui_broker_action,
    handle_tui_connect_action,
    handle_tui_family_action,
    handle_tui_guard_settings_action,
    handle_tui_last_action,
    handle_tui_last_used_action,
    handle_tui_launch_candidate_action,
    handle_tui_launch_confirmation,
    handle_tui_language_settings_action,
    handle_tui_provider_browse_action,
    handle_tui_profile_action,
    handle_tui_registry_settings_action,
    handle_tui_routes_export_settings_action,
    handle_tui_rescue_settings_action,
    handle_tui_settings_action,
    handle_rescue_packet_action,
    handle_tui_selected_model_action,
    handle_tui_submodel_action,
    handle_rescue_landing_action,
    handle_rescue_view_markdown_action,
    last_used_model_info,
    normalize_confirm_result,
    official_account_profile_context,
    opencode_profile_launch_context,
    prepare_confirm_prompt_inputs,
    provider_browse_launch_context,
    provider_browse_model_options,
    provider_browse_options,
    rescue_landing_action_context,
    rescue_packet_action_menu_context,
    refresh_tui_runtime_state_after_config_change,
    resolve_rescue_action_fallback_model,
    resolve_last_used_launch_context,
    resolve_confirm_launch_action,
    resolve_tui_launch_action_result,
    run_tui_launcher_loop,
    run_confirm_tui_prompt,
    safe_tui_call,
    select_rescue_event_action,
    select_rescue_menu_action,
    select_tui_launcher_family_action,
    select_tui_settings_action,
    selected_model_launch_context,
    select_rescue_route_fallback_model,
    show_rescue_no_packets_report,
    show_rescue_paths_action,
    TuiRuntimeRefreshDeps,
    TuiFamilyPayloadDeps,
    TuiLaunchCandidateDeps,
    TuiLaunchConfirmationDeps,
    TuiLauncherLoopDeps,
    TuiSettingsActionDeps,
)


def test_load_balance_entry_removed_from_launcher_tui() -> None:
    import inspect
    import mms_display.tui as mms_tui
    import mms_launcher.tui_flow as flow

    launcher_source = inspect.getsource(mms_tui.select_family_tui)

    assert "load_balance" not in launcher_source
    assert " 负载" not in launcher_source
    assert not hasattr(flow, "handle_tui_load_balance_action")


def test_config_help_omits_load_balance_commands(monkeypatch) -> None:
    import mms_core

    messages = []

    class Console:
        @staticmethod
        def print(*args, **_kwargs):
            messages.append(" ".join(str(arg) for arg in args))

    monkeypatch.setattr(mms_core, "console", Console())

    mms_core._display_config_help()

    help_text = "\n".join(messages)
    assert "load-balance" not in help_text
    assert "Load Balance" not in help_text


def test_apply_claude_network_guard_preview_sets_preview_or_fallback() -> None:
    calls = []
    runtime = {"auth_mode": "api_key", "bypass": True}

    def loader():
        return (
            lambda runtime_arg, *, require_proxy: calls.append(("preview", runtime_arg, require_proxy)) or {"status": "ok"},
            lambda runtime_arg: calls.append(("requires_proxy", runtime_arg)) or True,
        )

    assert apply_claude_network_guard_preview(
        runtime,
        "claude",
        network_guard_preview_loader=loader,
    ) is runtime
    assert runtime["_network_guard"] == {"status": "ok"}
    assert calls == [
        ("requires_proxy", runtime),
        ("preview", runtime, True),
    ]

    fallback_runtime = {"auth_mode": "oauth", "bypass": False}
    apply_claude_network_guard_preview(
        fallback_runtime,
        "claude",
        network_guard_preview_loader=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    assert fallback_runtime["_network_guard"] == {
        "status": "unknown",
        "dns_mode": "unknown",
        "ipv4_egress": "-",
        "ipv6_egress": "-",
        "targets": [],
        "no_proxy_conflicts": [],
    }


def test_apply_claude_network_guard_preview_skips_non_claude_or_non_auth_mode() -> None:
    for cli_name, runtime in [
        ("codex", {"auth_mode": "api_key"}),
        ("claude", {"auth_mode": "managed"}),
        ("claude", None),
    ]:
        assert apply_claude_network_guard_preview(
            runtime,
            cli_name,
            network_guard_preview_loader=lambda: (_ for _ in ()).throw(AssertionError("unused")),
        ) is runtime


def test_prepare_confirm_prompt_inputs_cleans_exports_and_applies_network_preview() -> None:
    calls = []
    model_info = {"model": "raw"}
    runtime = {"auth_mode": "api_key", "bypass": True}

    def network_guard_loader():
        return (
            lambda runtime_arg, *, require_proxy: calls.append(("preview", runtime_arg, require_proxy)) or {"status": "ok"},
            lambda runtime_arg: calls.append(("requires_proxy", runtime_arg)) or True,
        )

    result = prepare_confirm_prompt_inputs(
        "claude",
        model_info,
        runtime,
        clean_model_info=lambda model_info_arg: calls.append(("clean", model_info_arg)) or {"model": "clean"},
        get_export_env=lambda cli, runtime_arg: calls.append(("env", cli, runtime_arg)) or {"ENV": "1"},
        network_guard_preview_loader=network_guard_loader,
    )

    assert result == {
        "clean_model_info": {"model": "clean"},
        "env_vars": {"ENV": "1"},
        "runtime": runtime,
    }
    assert runtime["_network_guard"] == {"status": "ok"}
    assert calls == [
        ("clean", model_info),
        ("env", "claude", runtime),
        ("requires_proxy", runtime),
        ("preview", runtime, True),
    ]


def test_ensure_cli_installed_for_launch_skips_or_offers_install() -> None:
    calls = []

    assert ensure_cli_installed_for_launch(
        "codex",
        check_cli_installed=lambda cli: calls.append(("check", cli)) or True,
        check_and_offer_install_loader=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    ) == {"status": "continue"}

    assert ensure_cli_installed_for_launch(
        "claude",
        check_cli_installed=lambda cli: calls.append(("check", cli)) or False,
        check_and_offer_install_loader=lambda: (lambda cli: calls.append(("offer", cli)) or True),
    ) == {"status": "continue"}

    assert ensure_cli_installed_for_launch(
        "opencode",
        check_cli_installed=lambda cli: calls.append(("check", cli)) or False,
        check_and_offer_install_loader=lambda: (lambda cli: calls.append(("offer", cli)) or False),
    ) == {"status": "exit"}

    assert calls == [
        ("check", "codex"),
        ("check", "claude"),
        ("offer", "claude"),
        ("check", "opencode"),
        ("offer", "opencode"),
    ]


def test_enforce_confirm_bypass_network_guard_runs_only_for_claude_auth_bypass() -> None:
    calls = []
    runtime = {"auth_mode": "api_key"}

    assert enforce_confirm_bypass_network_guard(
        runtime,
        "claude",
        True,
        network_guard_enforcer_loader=lambda: (
            lambda runtime_arg, *, require_proxy: calls.append(("enforce", runtime_arg, require_proxy)),
            lambda runtime_arg: calls.append(("requires_proxy", runtime_arg)) or True,
        ),
    ) == {"status": "continue"}

    assert calls == [
        ("requires_proxy", runtime),
        ("enforce", runtime, True),
    ]

    skip_cases = [
        ("claude", False, {"auth_mode": "api_key"}),
        ("codex", True, {"auth_mode": "api_key"}),
        ("claude", True, {"auth_mode": "managed"}),
        ("claude", True, None),
    ]
    for cli_name, bypass, case_runtime in skip_cases:
        assert enforce_confirm_bypass_network_guard(
            case_runtime,
            cli_name,
            bypass,
            network_guard_enforcer_loader=lambda: (_ for _ in ()).throw(AssertionError("unused")),
        ) == {"status": "continue"}


def test_apply_opencode_profile_for_launch_only_applies_for_opencode() -> None:
    calls = []
    runtime = {"id": "p1"}
    selected = {"id": "p2"}

    assert apply_opencode_profile_for_launch(
        runtime,
        "codex",
        select_and_apply_opencode_profile=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    ) == {"status": "continue", "runtime": runtime}

    assert apply_opencode_profile_for_launch(
        runtime,
        "opencode",
        select_and_apply_opencode_profile=lambda runtime_arg, *, use_tui: calls.append((runtime_arg, use_tui)) or selected,
    ) == {"status": "continue", "runtime": selected, "cancelled": False}

    assert apply_opencode_profile_for_launch(
        runtime,
        "opencode",
        select_and_apply_opencode_profile=lambda runtime_arg, *, use_tui: calls.append((runtime_arg, use_tui)) or None,
    ) == {"status": "continue", "runtime": None, "cancelled": True}

    assert calls == [
        (runtime, True),
        (runtime, True),
    ]


def test_apply_launch_runtime_preferences_applies_common_and_claude_sidecar() -> None:
    calls = []
    cfg = {"cfg": True}
    runtime = {"id": "p1"}
    preferred_runtime = {"id": "p1", "prefs": True}
    sidecar_runtime = {"id": "p1", "prefs": True, "vision": True}

    assert apply_launch_runtime_preferences(
        cfg,
        runtime,
        "codex",
        runtime_with_launch_preferences=lambda cfg_arg, runtime_arg, cli: calls.append(("prefs", cfg_arg, runtime_arg, cli)) or preferred_runtime,
        runtime_with_vision_sidecar=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
    ) is preferred_runtime

    assert apply_launch_runtime_preferences(
        cfg,
        runtime,
        "claude",
        runtime_with_launch_preferences=lambda cfg_arg, runtime_arg, cli: calls.append(("prefs", cfg_arg, runtime_arg, cli)) or preferred_runtime,
        runtime_with_vision_sidecar=lambda cfg_arg, runtime_arg: calls.append(("vision", cfg_arg, runtime_arg)) or sidecar_runtime,
    ) is sidecar_runtime

    assert calls == [
        ("prefs", cfg, runtime, "codex"),
        ("prefs", cfg, runtime, "claude"),
        ("vision", cfg, preferred_runtime),
    ]


def test_handle_tui_broker_action_delegates_and_maps_status() -> None:
    calls = []
    cfg = {"cfg": True}

    assert handle_tui_broker_action(
        cfg,
        "codex",
        launch_broker_experiment_interactive=lambda cfg_arg, cli: calls.append((cfg_arg, cli, False)) or False,
    ) == {"status": "continue"}
    assert handle_tui_broker_action(
        cfg,
        "claude",
        launch_broker_experiment_interactive=lambda cfg_arg, cli: calls.append((cfg_arg, cli, True)) or True,
    ) == {"status": "exit"}
    assert calls == [
        (cfg, "codex", False),
        (cfg, "claude", True),
    ]


def test_provider_browse_options_filters_and_dedupes_candidates() -> None:
    provider = {"id": "current"}
    default_models = ["gpt-5.4"]
    candidates = [
        (
            {
                "id": "p1",
                "name": "Provider One",
                "api_key": "k",
                "role": "primary",
                "priority": 300,
                "supported_clis": ["codex"],
            },
            False,
        ),
        (
            {"id": "p1", "name": "Provider One Duplicate", "api_key": "k", "supported_clis": ["codex"]},
            False,
        ),
        (
            {
                "id": "disabled",
                "name": "Disabled",
                "api_key": "k",
                "enabled": False,
                "supported_clis": ["codex"],
            },
            False,
        ),
        ({"id": "no-key", "name": "No Key", "supported_clis": ["codex"]}, False),
        (
            {"id": "claude-only", "name": "Claude Only", "api_key": "k", "supported_clis": ["claude"]},
            False,
        ),
        ({"name": "Default Provider", "api_key": "k", "supported_clis": ["codex"]}, False),
    ]

    def provider_candidates(cfg, current_provider, models):
        assert cfg == {"cfg": True}
        assert current_provider is provider
        assert models is default_models
        return candidates

    result = provider_browse_options(
        {"cfg": True},
        provider,
        default_models,
        "codex",
        provider_candidates=provider_candidates,
        default_provider_id="default",
        provider_supports_cli_name=lambda item, cli: cli in item.get("supported_clis", []),
        provider_label=lambda item: item.get("name") or item.get("id"),
    )

    assert result == [
        {"id": "p1", "name": "Provider One", "role": "primary", "priority": 300},
        {"id": "default", "name": "Default Provider", "role": "auto", "priority": 100},
    ]


def test_provider_browse_model_options_resolves_and_filters_models() -> None:
    cfg = {"cfg": True}
    provider = {"id": "p1"}
    calls = []

    def resolve_provider_context(arg_cfg, provider_id):
        calls.append(("resolve", arg_cfg, provider_id))
        return provider

    def probe_models(arg_provider, *, emit_output):
        calls.append(("probe", arg_provider, emit_output))
        return {"models": ["gpt-5.4", "hidden-model"]}

    def filter_visible_models(models):
        calls.append(("filter", models))
        return [model for model in models if model != "hidden-model"]

    selected_provider, models = provider_browse_model_options(
        cfg,
        "p1",
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        filter_visible_models=filter_visible_models,
    )

    assert selected_provider is provider
    assert models == ["gpt-5.4"]
    assert calls == [
        ("resolve", cfg, "p1"),
        ("probe", provider, False),
        ("filter", ["gpt-5.4", "hidden-model"]),
    ]


def test_provider_browse_launch_context_traces_selection() -> None:
    trace_records = []
    trace_choices = []
    provider = {"id": "p1"}
    model_info = {"model": "gpt-5.4"}

    selected_model_info, runtime = provider_browse_launch_context(
        "codex",
        "p1",
        provider,
        model_info,
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert selected_model_info is model_info
    assert runtime is provider
    assert trace_records == [(("provider browse",), {"cli": "codex", "provider": "p1", "model": "gpt-5.4"})]
    assert trace_choices == [(("runtime resolve", provider), {"launch_cli": "codex", "choice": "provider browse"})]


def test_handle_tui_provider_browse_action_reports_no_providers() -> None:
    result = handle_tui_provider_browse_action(
        {},
        "codex",
        {},
        [],
        select_provider_browse_tui=lambda _providers: (_ for _ in ()).throw(AssertionError("unused")),
        select_provider_models_tui=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        provider_candidates=lambda *_args: [],
        default_provider_id="default",
        provider_supports_cli_name=lambda *_args: True,
        provider_label=lambda provider: provider.get("name") or provider.get("id"),
        resolve_provider_context=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        probe_models=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        filter_visible_models=lambda _models: (_ for _ in ()).throw(AssertionError("unused")),
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result == {"status": "continue", "message": "没有可用的 Provider"}


def test_handle_tui_provider_browse_action_launches_selected_model() -> None:
    calls = []
    cfg = {"cfg": True}
    current_provider = {"id": "current"}
    default_models = ["gpt-5.4"]
    selected_provider = {"id": "p1"}
    trace_records = []
    trace_choices = []

    def provider_candidates(arg_cfg, arg_provider, arg_models):
        calls.append(("candidates", arg_cfg, arg_provider, arg_models))
        return [
            (
                {
                    "id": "p1",
                    "name": "Provider One",
                    "api_key": "k",
                    "supported_clis": ["codex"],
                },
                False,
            )
        ]

    def select_provider(providers):
        calls.append(("select_provider", providers))
        return "p1", "Provider One"

    def resolve_provider_context(arg_cfg, provider_id):
        calls.append(("resolve", arg_cfg, provider_id))
        return selected_provider

    def probe_models(provider, *, emit_output):
        calls.append(("probe", provider, emit_output))
        return {"models": ["gpt-5.4", "hidden-model"]}

    def select_model(provider_name, models):
        calls.append(("select_model", provider_name, models))
        return {"model": "gpt-5.4"}

    result = handle_tui_provider_browse_action(
        cfg,
        "codex",
        current_provider,
        default_models,
        select_provider_browse_tui=select_provider,
        select_provider_models_tui=select_model,
        provider_candidates=provider_candidates,
        default_provider_id="default",
        provider_supports_cli_name=lambda provider, cli: cli in provider.get("supported_clis", []),
        provider_label=lambda provider: provider.get("name") or provider.get("id"),
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        filter_visible_models=lambda models: [model for model in models if model != "hidden-model"],
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": selected_provider,
    }
    assert calls == [
        ("candidates", cfg, current_provider, default_models),
        (
            "select_provider",
            [{"id": "p1", "name": "Provider One", "role": "auto", "priority": 100}],
        ),
        ("resolve", cfg, "p1"),
        ("probe", selected_provider, False),
        ("select_model", "Provider One", ["gpt-5.4"]),
    ]
    assert trace_records == [(("provider browse",), {"cli": "codex", "provider": "p1", "model": "gpt-5.4"})]
    assert trace_choices == [(("runtime resolve", selected_provider), {"launch_cli": "codex", "choice": "provider browse"})]


def test_handle_tui_provider_browse_action_exits_on_model_escape() -> None:
    result = handle_tui_provider_browse_action(
        {},
        "codex",
        {},
        [],
        select_provider_browse_tui=lambda _providers: ("p1", "Provider One"),
        select_provider_models_tui=lambda *_args: "__exit__",
        provider_candidates=lambda *_args: [
            ({"id": "p1", "name": "Provider One", "api_key": "k", "supported_clis": ["codex"]}, False)
        ],
        default_provider_id="default",
        provider_supports_cli_name=lambda provider, cli: cli in provider.get("supported_clis", []),
        provider_label=lambda provider: provider.get("name") or provider.get("id"),
        resolve_provider_context=lambda *_args: {"id": "p1"},
        probe_models=lambda *_args, **_kwargs: {"models": ["gpt-5.4"]},
        filter_visible_models=lambda models: models,
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result == {"status": "exit"}


def test_select_tui_launcher_family_action_normalizes_result_shapes() -> None:
    calls = []
    families_by_cli = {"claude": [{"family": "Claude"}]}
    cli_names = ["claude"]
    last_by_cli = {"claude": {"model": "sonnet"}}
    families_detail = {"claude": {"Claude": [{"model": "sonnet"}]}}
    provider_options_by_cli = {"claude": {}}
    provider_options_loader_by_cli = {"claude": lambda: []}
    broker_enabled_by_cli = {"claude": False}
    profile_options_by_cli = {"agy": []}

    def select_family(*args, **kwargs):
        calls.append((args, kwargs))
        return ("family", "claude", "Claude")

    result = select_tui_launcher_family_action(
        select_family_tui=select_family,
        families_by_cli=families_by_cli,
        cli_names=cli_names,
        last_by_cli=last_by_cli,
        families_detail=families_detail,
        provider_options_by_cli=provider_options_by_cli,
        provider_options_loader_by_cli=provider_options_loader_by_cli,
        broker_enabled_by_cli=broker_enabled_by_cli,
        profile_options_by_cli=profile_options_by_cli,
    )

    assert result == {
        "status": "action",
        "action_type": "family",
        "cli": "claude",
        "action_data": "Claude",
    }
    assert calls == [
        (
            (families_by_cli, cli_names),
            {
                "last_used": last_by_cli,
                "families_detail": families_detail,
                "provider_options_by_cli": provider_options_by_cli,
                "provider_options_loader_by_cli": provider_options_loader_by_cli,
                "broker_enabled_by_cli": broker_enabled_by_cli,
                "profile_options_by_cli": profile_options_by_cli,
            },
        )
    ]

    common = {
        "families_by_cli": families_by_cli,
        "cli_names": cli_names,
        "last_by_cli": last_by_cli,
        "families_detail": families_detail,
        "provider_options_by_cli": provider_options_by_cli,
        "provider_options_loader_by_cli": provider_options_loader_by_cli,
        "broker_enabled_by_cli": broker_enabled_by_cli,
        "profile_options_by_cli": profile_options_by_cli,
    }
    assert select_tui_launcher_family_action(
        select_family_tui=lambda *_args, **_kwargs: "fallback",
        **common,
    ) == {"status": "fallback"}
    assert select_tui_launcher_family_action(
        select_family_tui=lambda *_args, **_kwargs: None,
        **common,
    ) == {"status": "exit"}
    assert select_tui_launcher_family_action(
        select_family_tui=lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
        **common,
    ) == {"status": "exit"}


def test_safe_tui_call_normalizes_keyboard_interrupt() -> None:
    def raises_keyboard_interrupt():
        raise KeyboardInterrupt

    assert safe_tui_call(raises_keyboard_interrupt) == "__interrupt__"


def test_safe_tui_call_returns_function_result() -> None:
    assert safe_tui_call(lambda left, right=None: (left, right), "a", right="b") == ("a", "b")



def test_last_used_model_info_preserves_dict_model_info() -> None:
    model_info = {"model": "gpt-5.4", "provider": "p1"}
    assert last_used_model_info({"model": "fallback", "model_info": model_info}) is model_info


def test_last_used_model_info_falls_back_to_model_name() -> None:
    assert last_used_model_info({"model": "gpt-5.4", "model_info": "bad"}) == {"model": "gpt-5.4"}


def test_resolve_last_used_launch_context_uses_restored_runtime() -> None:
    trace_calls = []
    restored_runtime = {"id": "restored"}

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        resolve_last_used_runtime=lambda *_args: (restored_runtime, ["gpt-5.4"], "last used provider:p1"),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is restored_runtime
    assert cli_name == "codex"
    assert trace_calls == [
        (("runtime resolve", restored_runtime), {"launch_cli": "codex", "choice": "last used provider:p1"})
    ]


def test_resolve_last_used_launch_context_uses_best_provider_before_picker() -> None:
    trace_calls = []
    best_runtime = {"id": "best"}

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {},
        "claude",
        {"model": "claude-sonnet-4.5", "model_info": {"model": "claude-sonnet-4.5", "source": "last"}},
        {"id": "current"},
        ["claude-sonnet-4.5"],
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (best_runtime, None),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "claude-sonnet-4.5", "source": "last"}
    assert runtime is best_runtime
    assert cli_name == "claude"
    assert trace_calls == [
        (("runtime resolve", best_runtime), {"launch_cli": "claude", "choice": "best provider"})
    ]


def test_resolve_last_used_launch_context_falls_back_to_runtime_picker() -> None:
    choose_calls = []

    def choose_runtime_source(*args, **kwargs):
        choose_calls.append((args, kwargs))
        return {"id": "chosen"}, ["gpt-5.4"], "opencode"

    model_info, runtime, cli_name = resolve_last_used_launch_context(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        account_id="acct",
        provider_id="prov",
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        choose_runtime_source=choose_runtime_source,
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime == {"id": "chosen"}
    assert cli_name == "opencode"
    assert choose_calls == [
        (
            ({"cfg": True}, "codex", {"id": "current"}, ["gpt-5.4"]),
            {
                "account_id": "acct",
                "provider_id": "prov",
                "model_info": {"model": "gpt-5.4"},
                "allow_selected_model_accounts": True,
            },
        )
    ]


def test_handle_tui_last_used_action_launches_restored_runtime() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "restored"}

    result = handle_tui_last_used_action(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        resolve_last_used_runtime=lambda *_args: (runtime, ["gpt-5.4"], "last used provider:p1"),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": runtime,
        "cli": "codex",
    }
    assert trace_records == [(("last used",), {"cli": "codex", "model": "gpt-5.4"})]
    assert trace_choices == [
        (("runtime resolve", runtime), {"launch_cli": "codex", "choice": "last used provider:p1"})
    ]


def test_handle_tui_last_used_action_reports_missing_runtime() -> None:
    result = handle_tui_last_used_action(
        {},
        "claude",
        {"model": "claude-sonnet-4.5"},
        {},
        [],
        trace_record=lambda *_args, **_kwargs: None,
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        choose_runtime_source=lambda *_args, **_kwargs: (None, [], "claude"),
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert result == {"status": "continue", "message": "claude 没有可用 provider"}


def test_selected_model_launch_context_uses_embedded_provider_context() -> None:
    trace_calls = []
    provider_ctx = {"id": "embedded"}

    model_info, runtime = selected_model_launch_context(
        {},
        "codex",
        {"model": "gpt-5.4", "provider_ctx": provider_ctx},
        {"id": "current"},
        ["gpt-5.4"],
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert runtime is provider_ctx
    assert trace_calls == [
        (("runtime resolve", provider_ctx), {"launch_cli": "codex", "choice": "best provider"})
    ]


def test_selected_model_launch_context_falls_back_to_best_provider() -> None:
    trace_calls = []
    best_provider = {"id": "best"}

    model_info, runtime = selected_model_launch_context(
        {"cfg": True},
        "claude",
        {"model": "claude-sonnet-4.5"},
        {"id": "current"},
        ["claude-sonnet-4.5"],
        resolve_best_provider=lambda *_args, **_kwargs: (best_provider, None),
        trace_runtime_choice=lambda *args, **kwargs: trace_calls.append((args, kwargs)),
    )

    assert model_info == {"model": "claude-sonnet-4.5"}
    assert runtime is best_provider
    assert trace_calls == [
        (("runtime resolve", best_provider), {"launch_cli": "claude", "choice": "best provider"})
    ]


def test_handle_tui_selected_model_action_applies_priority_and_traces_launch() -> None:
    calls = []
    trace_records = []
    trace_choices = []
    runtime = {"id": "provider-a"}
    selected = {"model": "gpt-5.4", "provider_id": "fallback", "priority_changes": [{"id": "provider-a"}]}

    result = handle_tui_selected_model_action(
        {"cfg": True},
        "codex",
        selected,
        "GPT",
        {"id": "current"},
        ["gpt-5.4"],
        apply_priority_changes=lambda cfg, changes: calls.append(("priority", cfg, changes)) or True,
        selected_model_launch_context=selected_model_launch_context,
        resolve_best_provider=lambda *_args, **_kwargs: (runtime, None),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": runtime,
        "families_dirty": True,
    }
    assert selected == {"model": "gpt-5.4", "provider_id": "fallback"}
    assert calls == [("priority", {"cfg": True}, [{"id": "provider-a"}])]
    assert trace_records == [(('family "GPT"',), {"cli": "codex", "model": "gpt-5.4", "provider": "provider-a"})]
    assert trace_choices == [(("runtime resolve", runtime), {"launch_cli": "codex", "choice": "best provider"})]


def test_handle_tui_selected_model_action_reports_missing_runtime() -> None:
    trace_records = []
    result = handle_tui_selected_model_action(
        {},
        "claude",
        {"model": "missing-model"},
        "Claude",
        {},
        [],
        apply_priority_changes=lambda cfg, changes: False,
        selected_model_launch_context=selected_model_launch_context,
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert result == {
        "status": "continue",
        "message": "没有可用 provider 承载 missing-model",
        "families_dirty": False,
    }
    assert trace_records == []


def test_handle_tui_family_action_selects_model_and_applies_priority() -> None:
    calls = []
    traces = []
    runtime = {"id": "p1"}
    selected = {"model": "gpt-5.4", "priority_changes": [{"id": "p1"}]}

    result = handle_tui_family_action(
        {"cfg": True},
        "codex",
        "GPT",
        {"codex": {"GPT": [{"model": "gpt-5.4"}]}},
        {"codex": {"provider": "option"}},
        {"codex": {"model": "last-model"}},
        {"id": "current"},
        ["gpt-5.4"],
        select_submodel_tui=lambda family, models, **kwargs: calls.append(("select", family, models, kwargs)) or selected,
        apply_priority_changes=lambda cfg, changes: calls.append(("priority", cfg, changes)) or True,
        resolve_last_used_runtime=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_best_provider=lambda *_args, **_kwargs: (runtime, None),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_record=lambda *args, **kwargs: traces.append(("record", args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: traces.append(("choice", args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": runtime,
        "families_dirty": True,
    }
    assert calls == [
        (
            "select",
            "GPT",
            [{"model": "gpt-5.4"}],
            {"provider_options": {"provider": "option"}, "last_used": {"model": "last-model"}},
        ),
        ("priority", {"cfg": True}, [{"id": "p1"}]),
    ]
    assert traces == [
        ("choice", ("runtime resolve", runtime), {"launch_cli": "codex", "choice": "best provider"}),
        ("record", ('family "GPT"',), {"cli": "codex", "model": "gpt-5.4", "provider": "p1"}),
    ]


def test_handle_tui_family_action_handles_last_used_selection() -> None:
    traces = []
    runtime = {"id": "restored"}

    result = handle_tui_family_action(
        {"cfg": True},
        "claude",
        "Claude",
        {"claude": {"Claude": [{"model": "claude-sonnet"}]}},
        {},
        {"claude": {"model": "claude-sonnet", "model_info": {"model": "claude-sonnet", "source": "last"}}},
        {"id": "current"},
        ["claude-sonnet"],
        select_submodel_tui=lambda *_args, **_kwargs: "__last__",
        account_id="acc",
        provider_id="prov",
        apply_priority_changes=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_last_used_runtime=lambda cfg, cli, action_data, default_models: (
            runtime,
            default_models,
            "restored-choice",
        ),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_record=lambda *args, **kwargs: traces.append(("record", args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: traces.append(("choice", args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "claude-sonnet", "source": "last"},
        "runtime": runtime,
        "cli": "claude",
        "families_dirty": False,
    }
    assert traces == [
        ("record", ("last used",), {"cli": "claude", "model": "claude-sonnet"}),
        ("choice", ("runtime resolve", runtime), {"launch_cli": "claude", "choice": "restored-choice"}),
    ]


def test_handle_tui_last_action_delegates_to_last_used_resolution() -> None:
    traces = []
    runtime = {"id": "restored"}

    result = handle_tui_last_action(
        {"cfg": True},
        "codex",
        {"model": "gpt-5.4"},
        {"id": "current"},
        ["gpt-5.4"],
        account_id="acc",
        provider_id="provider",
        trace_record=lambda *args, **kwargs: traces.append(("record", args, kwargs)),
        resolve_last_used_runtime=lambda *_args: (runtime, ["gpt-5.4"], "last-used"),
        resolve_best_provider=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        choose_runtime_source=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *args, **kwargs: traces.append(("choice", args, kwargs)),
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": runtime,
        "cli": "codex",
    }
    assert traces == [
        ("record", ("last used",), {"cli": "codex", "model": "gpt-5.4"}),
        ("choice", ("runtime resolve", runtime), {"launch_cli": "codex", "choice": "last-used"}),
    ]


def test_handle_tui_family_action_handles_empty_cancel_interrupt_and_missing_last() -> None:
    assert handle_tui_family_action(
        {},
        "codex",
        "Empty",
        {"codex": {}},
        {},
        {},
        {},
        [],
        select_submodel_tui=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        apply_priority_changes=lambda *_args: False,
        resolve_last_used_runtime=lambda *_args: (None, [], ""),
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        choose_runtime_source=lambda *_args, **_kwargs: (None, [], "codex"),
        trace_record=lambda *_args, **_kwargs: None,
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    ) == {"status": "continue", "message": "Empty 下没有可用模型", "families_dirty": False}

    base_kwargs = {
        "cfg": {},
        "cli_name": "codex",
        "family_name": "GPT",
        "families_detail": {"codex": {"GPT": [{"model": "gpt"}]}},
        "provider_options_by_cli": {},
        "last_by_cli": {},
        "current_provider": {},
        "default_models": [],
        "apply_priority_changes": lambda *_args: False,
        "resolve_last_used_runtime": lambda *_args: (None, [], ""),
        "resolve_best_provider": lambda *_args, **_kwargs: (None, None),
        "choose_runtime_source": lambda *_args, **_kwargs: (None, [], "codex"),
        "trace_record": lambda *_args, **_kwargs: None,
        "trace_runtime_choice": lambda *_args, **_kwargs: None,
    }
    assert handle_tui_family_action(
        **base_kwargs,
        select_submodel_tui=lambda *_args, **_kwargs: None,
    ) == {"status": "continue", "families_dirty": False}
    assert handle_tui_family_action(
        **base_kwargs,
        select_submodel_tui=lambda *_args, **_kwargs: "__last__",
    ) == {"status": "continue", "families_dirty": False}
    assert handle_tui_family_action(
        **base_kwargs,
        select_submodel_tui=lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    ) == {"status": "interrupt", "families_dirty": False}


def test_handle_tui_submodel_action_uses_family_name_and_copies_action_data() -> None:
    trace_records = []
    runtime = {"id": "p1"}
    action_data = {"model": "gpt-5.4", "_family_name": "GPT", "priority_changes": [{"id": "p1"}]}

    result = handle_tui_submodel_action(
        {"cfg": True},
        "codex",
        action_data,
        {"id": "current"},
        ["gpt-5.4"],
        apply_priority_changes=lambda _cfg, changes: bool(changes),
        resolve_best_provider=lambda *_args, **_kwargs: (runtime, None),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": runtime,
        "families_dirty": True,
    }
    assert action_data == {"model": "gpt-5.4", "_family_name": "GPT", "priority_changes": [{"id": "p1"}]}
    assert trace_records == [(('family "GPT"',), {"cli": "codex", "model": "gpt-5.4", "provider": "p1"})]


def test_handle_tui_submodel_action_defaults_family_name() -> None:
    result = handle_tui_submodel_action(
        {},
        "claude",
        {"model": "missing"},
        {},
        [],
        apply_priority_changes=lambda *_args: False,
        resolve_best_provider=lambda *_args, **_kwargs: (None, None),
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    )

    assert result == {
        "status": "continue",
        "message": "没有可用 provider 承载 missing",
        "families_dirty": False,
    }


def test_opencode_profile_launch_context_traces_resolved_runtime() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "provider", "opencode_profile": "agent"}

    model_info, selected_runtime = opencode_profile_launch_context(
        {"cfg": True},
        {"id": "current"},
        ["gpt-5.4"],
        "agent",
        resolve_opencode_profile_runtime=lambda *_args: ({"model": "gpt-5.4"}, runtime),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info == {"model": "gpt-5.4"}
    assert selected_runtime is runtime
    assert trace_records == [
        (
            ("opencode profile",),
            {"cli": "opencode", "profile": "agent", "model": "gpt-5.4", "provider": "provider"},
        )
    ]
    assert trace_choices == [
        (("runtime resolve", runtime), {"launch_cli": "opencode", "choice": "opencode profile"})
    ]


def test_opencode_profile_launch_context_keeps_unresolved_result_untraced() -> None:
    model_info, runtime = opencode_profile_launch_context(
        {},
        {},
        [],
        "raw",
        resolve_opencode_profile_runtime=lambda *_args: (None, None),
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert model_info is None
    assert runtime is None


def test_official_account_profile_context_traces_matching_account() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "agy-main", "cli": "agy"}

    model_info, selected_runtime = official_account_profile_context(
        {},
        "agy",
        "agy-main",
        resolve_account_context=lambda *_args, **_kwargs: runtime,
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert model_info == {}
    assert selected_runtime is runtime
    assert trace_records == [(("official account",), {"cli": "agy", "account": "agy-main"})]
    assert trace_choices == [(("runtime resolve", runtime), {"launch_cli": "agy", "choice": "official account"})]


def test_official_account_profile_context_rejects_wrong_cli() -> None:
    model_info, runtime = official_account_profile_context(
        {},
        "agy",
        "wrong",
        resolve_account_context=lambda *_args, **_kwargs: {"id": "gemini-old", "cli": "gemini"},
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert model_info == {}
    assert runtime is None


def test_handle_tui_profile_action_launches_opencode_profile() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "provider", "opencode_profile": "agent"}

    result = handle_tui_profile_action(
        {"cfg": True},
        "opencode",
        "agent",
        {"id": "current"},
        ["gpt-5.4"],
        agy_connect_profile_id="__connect__",
        connect_action=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_opencode_profile_runtime=lambda *_args: ({"model": "gpt-5.4"}, runtime),
        resolve_account_context=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert result == {"status": "launch", "model_info": {"model": "gpt-5.4"}, "runtime": runtime}
    assert trace_records == [
        (
            ("opencode profile",),
            {"cli": "opencode", "profile": "agent", "model": "gpt-5.4", "provider": "provider"},
        )
    ]
    assert trace_choices == [(("runtime resolve", runtime), {"launch_cli": "opencode", "choice": "opencode profile"})]


def test_handle_tui_profile_action_connects_or_reports_missing_account() -> None:
    connect_result = {
        "cfg": {"updated": True},
        "changed": True,
        "current_provider": {"id": "provider"},
        "default_models": ["gpt-5.4"],
        "current_cli_names": ["agy"],
        "families_dirty": True,
    }
    assert handle_tui_profile_action(
        {"cfg": True},
        "agy",
        "__connect__",
        {},
        [],
        agy_connect_profile_id="__connect__",
        connect_action=lambda cfg, cli: {**connect_result, "called_with": (cfg, cli)},
        resolve_opencode_profile_runtime=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_account_context=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_record=lambda *_args, **_kwargs: None,
        trace_runtime_choice=lambda *_args, **_kwargs: None,
    ) == {"status": "continue", **connect_result, "called_with": ({"cfg": True}, "agy")}

    assert handle_tui_profile_action(
        {},
        "agy",
        "missing",
        {},
        [],
        agy_connect_profile_id="__connect__",
        connect_action=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_opencode_profile_runtime=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_account_context=lambda *_args, **_kwargs: None,
        trace_record=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        trace_runtime_choice=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    ) == {"status": "continue", "message": "未找到 agy 官方账号: missing"}


def test_handle_tui_profile_action_launches_official_account() -> None:
    trace_records = []
    trace_choices = []
    runtime = {"id": "agy-main", "cli": "agy"}

    result = handle_tui_profile_action(
        {"cfg": True},
        "agy",
        "agy-main",
        {},
        [],
        agy_connect_profile_id="__connect__",
        connect_action=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_opencode_profile_runtime=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        resolve_account_context=lambda *_args, **_kwargs: runtime,
        trace_record=lambda *args, **kwargs: trace_records.append((args, kwargs)),
        trace_runtime_choice=lambda *args, **kwargs: trace_choices.append((args, kwargs)),
    )

    assert result == {"status": "launch", "model_info": {}, "runtime": runtime}
    assert trace_records == [(("official account",), {"cli": "agy", "account": "agy-main"})]
    assert trace_choices == [(("runtime resolve", runtime), {"launch_cli": "agy", "choice": "official account"})]


def _launch_candidate_deps(**overrides):
    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    deps = {
        "select_submodel_tui": unused,
        "apply_priority_changes": lambda *_args: False,
        "resolve_last_used_runtime": unused,
        "resolve_best_provider": lambda *_args, **_kwargs: (None, None),
        "choose_runtime_source": unused,
        "trace_record": lambda *_args, **_kwargs: None,
        "trace_runtime_choice": lambda *_args, **_kwargs: None,
        "provider_browse_tui_loader": unused,
        "provider_candidates": unused,
        "default_provider_id": "default",
        "provider_supports_cli_name": lambda *_args: True,
        "provider_label": lambda provider: provider.get("name") or provider.get("id"),
        "resolve_provider_context": unused,
        "probe_models": unused,
        "filter_visible_models": lambda models: models,
        "agy_connect_profile_id": "__connect__",
        "connect_action": unused,
        "resolve_opencode_profile_runtime": unused,
        "resolve_account_context": unused,
    }
    deps.update(overrides)
    return TuiLaunchCandidateDeps(**deps)


def test_handle_tui_launch_candidate_action_dispatches_profile_and_unknown() -> None:
    connect_result = {
        "cfg": {"updated": True},
        "changed": True,
        "current_provider": {"id": "provider"},
        "default_models": ["gpt-5.4"],
        "current_cli_names": ["agy"],
        "families_dirty": True,
    }

    assert handle_tui_launch_candidate_action(
        {"cfg": True},
        "profile",
        "agy",
        "__connect__",
        {},
        [],
        families_detail={},
        provider_options_by_cli={},
        last_by_cli={},
        deps=_launch_candidate_deps(
            connect_action=lambda cfg, cli: {**connect_result, "called_with": (cfg, cli)},
        ),
    ) == {"status": "continue", **connect_result, "called_with": ({"cfg": True}, "agy")}

    assert handle_tui_launch_candidate_action(
        {},
        "profile",
        "claude",
        "ignored",
        {},
        [],
        families_detail={},
        provider_options_by_cli={},
        last_by_cli={},
        deps=_launch_candidate_deps(),
    ) == {"status": "continue"}

    assert handle_tui_launch_candidate_action(
        {},
        "unknown",
        "claude",
        None,
        {},
        [],
        families_detail={},
        provider_options_by_cli={},
        last_by_cli={},
        deps=_launch_candidate_deps(),
    ) == {"status": "continue"}


def test_handle_tui_launch_candidate_action_dispatches_provider_browse_and_family() -> None:
    calls = []
    provider = {"id": "p1", "name": "Provider One", "api_key": "k", "supported_clis": ["codex"]}
    family_runtime = {"id": "family-provider"}

    provider_result = handle_tui_launch_candidate_action(
        {"cfg": True},
        "provider_browse",
        "codex",
        None,
        {"id": "current"},
        ["gpt-5.4"],
        families_detail={},
        provider_options_by_cli={},
        last_by_cli={},
        deps=_launch_candidate_deps(
            provider_browse_tui_loader=lambda: {
                "select_provider_browse_tui": lambda providers: calls.append(("select_provider", providers)) or ("p1", "Provider One"),
                "select_provider_models_tui": lambda name, models: calls.append(("select_model", name, models)) or {"model": "gpt-5.4"},
            },
            provider_candidates=lambda *_args: [(provider, False)],
            provider_supports_cli_name=lambda provider_arg, cli: cli in provider_arg.get("supported_clis", []),
            resolve_provider_context=lambda _cfg, provider_id: calls.append(("resolve", provider_id)) or provider,
            probe_models=lambda provider_arg, *, emit_output: calls.append(("probe", provider_arg, emit_output)) or {"models": ["gpt-5.4"]},
            trace_record=lambda *args, **kwargs: calls.append(("record", args, kwargs)),
            trace_runtime_choice=lambda *args, **kwargs: calls.append(("choice", args, kwargs)),
        ),
    )

    assert provider_result == {"status": "launch", "model_info": {"model": "gpt-5.4"}, "runtime": provider}

    family_result = handle_tui_launch_candidate_action(
        {"cfg": True},
        "family",
        "codex",
        "GPT",
        {"id": "current"},
        ["gpt-5.4"],
        families_detail={"codex": {"GPT": [{"model": "gpt-5.4"}]}},
        provider_options_by_cli={"codex": {}},
        last_by_cli={},
        deps=_launch_candidate_deps(
            select_submodel_tui=lambda *_args, **_kwargs: {"model": "gpt-5.4"},
            resolve_best_provider=lambda *_args, **_kwargs: (family_runtime, None),
            trace_record=lambda *args, **kwargs: calls.append(("family_record", args, kwargs)),
            trace_runtime_choice=lambda *args, **kwargs: calls.append(("family_choice", args, kwargs)),
        ),
    )

    assert family_result == {
        "status": "launch",
        "model_info": {"model": "gpt-5.4"},
        "runtime": family_runtime,
        "families_dirty": False,
    }


def test_refresh_tui_runtime_state_after_config_change_clears_and_rebuilds() -> None:
    calls = []

    class FakeProbeCache:
        def clear(self):
            calls.append(("clear",))

    def fake_rmtree(path, *, ignore_errors):
        calls.append(("rmtree", path, ignore_errors))

    def fake_ensure_provider_credentials(cfg):
        calls.append(("ensure", cfg))
        return {"id": "provider"}

    def fake_probe_models(provider, *, emit_output):
        calls.append(("probe", provider, emit_output))
        return {"models": ["gpt-5.4"]}

    def fake_resolve_visible_clis(cfg, provider, models):
        calls.append(("visible", cfg, provider, models))
        return ["codex"]

    provider, models, clis = refresh_tui_runtime_state_after_config_change(
        {"cfg": True},
        deps=TuiRuntimeRefreshDeps(
            probe_cache=FakeProbeCache(),
            probe_file_cache_dir="/tmp/probe-cache",
            rmtree=fake_rmtree,
            ensure_provider_credentials=fake_ensure_provider_credentials,
            probe_models=fake_probe_models,
            resolve_visible_clis=fake_resolve_visible_clis,
        ),
    )

    assert provider == {"id": "provider"}
    assert models == ["gpt-5.4"]
    assert clis == ["codex"]
    assert calls == [
        ("clear",),
        ("rmtree", "/tmp/probe-cache", True),
        ("ensure", {"cfg": True}),
        ("probe", {"id": "provider"}, False),
        ("visible", {"cfg": True}, {"id": "provider"}, ["gpt-5.4"]),
    ]


def test_handle_tui_connect_action_uses_agy_quick_connect() -> None:
    calls = []

    def quick_connect(cfg, *, preset_cli):
        calls.append(("quick", cfg, preset_cli))
        return {"cfg": "updated"}, False

    result = handle_tui_connect_action(
        {"cfg": "initial"},
        "agy",
        quick_connect_official=quick_connect,
        run_connect_wizard=lambda _cfg: (_ for _ in ()).throw(AssertionError("unused")),
        refresh_runtime_state=lambda _cfg: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result == {
        "cfg": {"cfg": "updated"},
        "changed": False,
        "current_provider": None,
        "default_models": None,
        "current_cli_names": None,
        "families_dirty": False,
    }
    assert calls == [("quick", {"cfg": "initial"}, "agy")]


def test_handle_tui_connect_action_uses_wizard_for_non_agy() -> None:
    calls = []

    def run_wizard(cfg):
        calls.append(("wizard", cfg))
        return {"cfg": "wizard"}, False

    result = handle_tui_connect_action(
        {"cfg": "initial"},
        "codex",
        quick_connect_official=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        run_connect_wizard=run_wizard,
        refresh_runtime_state=lambda _cfg: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result["cfg"] == {"cfg": "wizard"}
    assert result["changed"] is False
    assert result["families_dirty"] is False
    assert calls == [("wizard", {"cfg": "initial"})]


def test_handle_tui_connect_action_refreshes_changed_state() -> None:
    calls = []
    updated_cfg = {"cfg": "updated"}
    provider = {"id": "provider"}
    models = ["gpt-5.4"]
    clis = ["codex", "agy"]

    def run_wizard(cfg):
        calls.append(("wizard", cfg))
        return updated_cfg, True

    def refresh(cfg):
        calls.append(("refresh", cfg))
        return provider, models, clis

    result = handle_tui_connect_action(
        {"cfg": "initial"},
        "codex",
        quick_connect_official=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        run_connect_wizard=run_wizard,
        refresh_runtime_state=refresh,
    )

    assert result == {
        "cfg": updated_cfg,
        "changed": True,
        "current_provider": provider,
        "default_models": models,
        "current_cli_names": clis,
        "families_dirty": True,
    }
    assert calls == [
        ("wizard", {"cfg": "initial"}),
        ("refresh", updated_cfg),
    ]


def test_apply_tui_launcher_state_result_merges_changed_and_unchanged_results() -> None:
    state = (
        {"cfg": "old"},
        {"id": "old-provider"},
        ["old-model"],
        ["claude"],
        False,
    )

    assert apply_tui_launcher_state_result(
        *state,
        {"cfg": {"cfg": "language"}, "changed": False},
    ) == (
        {"cfg": "language"},
        {"id": "old-provider"},
        ["old-model"],
        ["claude"],
        False,
    )

    assert apply_tui_launcher_state_result(
        *state,
        {
            "cfg": {"cfg": "new"},
            "changed": True,
            "current_provider": {"id": "new-provider"},
            "default_models": ["new-model"],
            "families_dirty": True,
        },
    ) == (
        {"cfg": "new"},
        {"id": "new-provider"},
        ["new-model"],
        ["claude"],
        True,
    )


def test_resolve_tui_launch_action_result_prints_and_maps_statuses() -> None:
    messages = []

    class Console:
        @staticmethod
        def print(message):
            messages.append(message)

    assert resolve_tui_launch_action_result(
        {"status": "continue", "message": "missing runtime", "families_dirty": True},
        "claude",
        console=Console(),
    ) == {"status": "continue", "families_dirty": True}
    assert messages == ["[yellow]missing runtime[/yellow]"]

    assert resolve_tui_launch_action_result(
        {"status": "interrupt"},
        "claude",
        console=Console(),
    ) == {"status": "exit", "families_dirty": False}

    runtime = {"id": "runtime"}
    model_info = {"model": "gpt-5.4"}
    assert resolve_tui_launch_action_result(
        {
            "status": "launch",
            "model_info": model_info,
            "runtime": runtime,
            "cli": "codex",
        },
        "claude",
        console=Console(),
    ) == {
        "status": "launch",
        "model_info": model_info,
        "runtime": runtime,
        "cli": "codex",
        "families_dirty": False,
    }


def test_apply_tui_priority_changes_saves_then_exports() -> None:
    calls = []

    def export_model_routes(cfg, *, force):
        calls.append(("export", cfg, force))

    changed = apply_tui_priority_changes(
        {"cfg": True},
        [{"id": "p1"}],
        apply_runtime_priority_changes=lambda cfg, changes: calls.append(("apply", cfg, changes)) or True,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=lambda: export_model_routes,
    )

    assert changed is True
    assert calls == [
        ("apply", {"cfg": True}, [{"id": "p1"}]),
        ("save", {"cfg": True}),
        ("export", {"cfg": True}, True),
    ]


def test_apply_tui_priority_changes_ignores_export_failure() -> None:
    calls = []

    def load_export_model_routes():
        raise RuntimeError("export unavailable")

    changed = apply_tui_priority_changes(
        {},
        ["change"],
        apply_runtime_priority_changes=lambda *_args: True,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=load_export_model_routes,
    )

    assert changed is True
    assert calls == [("save", {})]


def test_apply_tui_priority_changes_skips_save_without_changes() -> None:
    calls = []

    changed = apply_tui_priority_changes(
        {},
        None,
        apply_runtime_priority_changes=lambda *_args: False,
        save_config=lambda cfg: calls.append(("save", cfg)),
        export_model_routes_loader=lambda: calls.append(("load_export",)),
    )

    assert changed is False
    assert calls == []


def test_handle_tui_language_settings_action_saves_supported_language() -> None:
    calls = []
    cfg = {}

    result = handle_tui_language_settings_action(
        cfg,
        select_language_tui=lambda: calls.append(("select",)) or "en",
        save_config=lambda cfg_arg: calls.append(("save", cfg_arg.copy())),
        set_language=lambda lang: calls.append(("set_language", lang)),
    )

    assert result == {"status": "continue", "changed": True}
    assert cfg == {"ui": {"language": "en"}}
    assert calls == [
        ("select",),
        ("save", {"ui": {"language": "en"}}),
        ("set_language", "en"),
    ]


def test_handle_tui_language_settings_action_skips_cancel_invalid_and_interrupt() -> None:
    calls = []

    assert handle_tui_language_settings_action(
        {"ui": {"language": "zh"}},
        select_language_tui=lambda: None,
        save_config=lambda *_args: calls.append(("save",)),
        set_language=lambda *_args: calls.append(("set_language",)),
    ) == {"status": "continue", "changed": False}

    assert handle_tui_language_settings_action(
        {"ui": {"language": "zh"}},
        select_language_tui=lambda: "fr",
        save_config=lambda *_args: calls.append(("save",)),
        set_language=lambda *_args: calls.append(("set_language",)),
    ) == {"status": "continue", "changed": False}

    assert handle_tui_language_settings_action(
        {"ui": {"language": "zh"}},
        select_language_tui=lambda: (_ for _ in ()).throw(KeyboardInterrupt),
        save_config=lambda *_args: calls.append(("save",)),
        set_language=lambda *_args: calls.append(("set_language",)),
    ) == {"status": "interrupt", "changed": False}

    assert calls == []


def test_handle_tui_routes_export_settings_action_exports_and_reports_success() -> None:
    calls = []

    class Console:
        @staticmethod
        def print(message):
            calls.append(("print", message))

    def export_model_routes(cfg, *, force):
        calls.append(("export", cfg, force))

    result = handle_tui_routes_export_settings_action(
        {"cfg": True},
        export_model_routes_loader=lambda: ("/tmp/model-routes.json", export_model_routes),
        console=Console(),
    )

    assert result == {"status": "continue", "success": True}
    assert calls == [
        ("export", {"cfg": True}, True),
        ("print", "[green]✓ 已导出 /tmp/model-routes.json[/green]"),
    ]


def test_handle_tui_routes_export_settings_action_reports_loader_or_export_failure() -> None:
    messages = []

    class Console:
        @staticmethod
        def print(message):
            messages.append(message)

    assert handle_tui_routes_export_settings_action(
        {},
        export_model_routes_loader=lambda: (_ for _ in ()).throw(RuntimeError("loader failed")),
        console=Console(),
    ) == {"status": "continue", "success": False}

    def export_model_routes(_cfg, *, force):
        assert force is True
        raise RuntimeError("export failed")

    assert handle_tui_routes_export_settings_action(
        {},
        export_model_routes_loader=lambda: ("/tmp/model-routes.json", export_model_routes),
        console=Console(),
    ) == {"status": "continue", "success": False}

    assert messages == [
        "[red]导出失败: loader failed[/red]",
        "[red]导出失败: export failed[/red]",
    ]


def test_handle_tui_registry_settings_action_runs_supported_actions() -> None:
    calls = []
    selected_actions = iter(["check_staleness", "refresh_due_sources", "scheduled_dry_run", "diff_openrouter", "doctor"])

    def make_cli():
        return {
            "registry_status": lambda: calls.append(("status",)) or {"ok": True},
            "source_freshness": lambda: calls.append(("freshness",)) or {"action": "freshness"},
            "refresh_source_snapshots": lambda *, if_due: calls.append(("refresh", if_due)) or {"action": "refresh"},
            "scheduled_refresh": lambda *, dry_run, no_network: calls.append(("scheduled", dry_run, no_network)) or {"action": "scheduled"},
            "fetch_openrouter_catalog": lambda: calls.append(("fetch",)) or {"action": "fetch"},
            "diff_openrouter_catalog": lambda *, limit: calls.append(("diff", limit)) or {"action": "diff"},
            "publish_approved_bundle": lambda: calls.append(("publish",)) or {"action": "publish"},
            "verify_approved_bundle": lambda: calls.append(("verify",)) or {"action": "verify"},
        }

    payloads = {
        "source_staleness": lambda summary: ("fresh title", [summary]),
        "refresh_sources": lambda summary: ("refresh title", [summary]),
        "scheduled_refresh": lambda summary: ("scheduled title", [summary]),
        "openrouter_fetch": lambda summary: ("fetch title", [summary]),
        "openrouter_diff": lambda summary: ("diff title", [summary]),
        "publish_approved": lambda summary: ("publish title", [summary]),
        "verify_approved": lambda summary: ("verify title", [summary]),
        "doctor": lambda status: ("doctor title", [status]),
    }

    for _ in range(5):
        assert handle_tui_registry_settings_action(
            registry_cli_loader=make_cli,
            registry_truth_tui_payload=lambda status: calls.append(("payload", status)) or ("Registry", ["info"], []),
            select_channel_action_tui=lambda title, info, actions: calls.append(("select", title, info, actions)) or next(selected_actions),
            print_settings_error_report=lambda title, exc: calls.append(("error", title, str(exc))),
            print_settings_result_report=lambda title, rows, *rest, **kwargs: calls.append(("report", title, rows, rest, kwargs)),
            registry_report_payloads=payloads,
            pause_after_tui_report=lambda message: calls.append(("pause", message)),
            localize=lambda zh, en: zh,
        ) == {"status": "continue"}

    assert ("freshness",) in calls
    assert ("refresh", True) in calls
    assert ("scheduled", True, True) in calls
    assert ("diff", 12) in calls
    assert calls.count(("status",)) == 6
    assert calls.count(("pause", "按 Enter 返回设置")) == 5
    assert ("report", "fresh title", [{"action": "freshness"}], (), {}) in calls
    assert ("report", "doctor title", [{"ok": True}], (), {}) in calls


def test_handle_tui_registry_settings_action_handles_error_interrupt_and_back() -> None:
    calls = []

    def make_cli():
        def fail_refresh(*, if_due):
            calls.append(("refresh", if_due))
            raise RuntimeError("refresh failed")

        return {
            "registry_status": lambda: calls.append(("status",)) or {},
            "source_freshness": lambda: {},
            "refresh_source_snapshots": fail_refresh,
            "scheduled_refresh": lambda *, dry_run, no_network: {},
            "fetch_openrouter_catalog": lambda: {},
            "diff_openrouter_catalog": lambda *, limit: {},
            "publish_approved_bundle": lambda: {},
            "verify_approved_bundle": lambda: {},
        }

    payloads = {
        "source_staleness": lambda summary: ("fresh title", [summary]),
        "refresh_sources": lambda summary: ("refresh title", [summary]),
        "scheduled_refresh": lambda summary: ("scheduled title", [summary]),
        "openrouter_fetch": lambda summary: ("fetch title", [summary]),
        "openrouter_diff": lambda summary: ("diff title", [summary]),
        "publish_approved": lambda summary: ("publish title", [summary]),
        "verify_approved": lambda summary: ("verify title", [summary]),
        "doctor": lambda status: ("doctor title", [status]),
    }

    assert handle_tui_registry_settings_action(
        registry_cli_loader=make_cli,
        registry_truth_tui_payload=lambda status: ("Registry", [], []),
        select_channel_action_tui=lambda *_args: "refresh_sources",
        print_settings_error_report=lambda title, exc: calls.append(("error", title, str(exc))),
        print_settings_result_report=lambda *_args, **_kwargs: calls.append(("report",)),
        registry_report_payloads=payloads,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        localize=lambda zh, en: zh,
    ) == {"status": "continue"}
    assert ("error", "刷新 Sources 失败", "refresh failed") in calls
    assert ("pause", "按 Enter 返回设置") in calls

    assert handle_tui_registry_settings_action(
        registry_cli_loader=make_cli,
        registry_truth_tui_payload=lambda status: ("Registry", [], []),
        select_channel_action_tui=lambda *_args: None,
        print_settings_error_report=lambda *_args: calls.append(("error",)),
        print_settings_result_report=lambda *_args, **_kwargs: calls.append(("report",)),
        registry_report_payloads=payloads,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        localize=lambda zh, en: zh,
    ) == {"status": "continue"}

    assert handle_tui_registry_settings_action(
        registry_cli_loader=make_cli,
        registry_truth_tui_payload=lambda status: ("Registry", [], []),
        select_channel_action_tui=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt),
        print_settings_error_report=lambda *_args: calls.append(("error",)),
        print_settings_result_report=lambda *_args, **_kwargs: calls.append(("report",)),
        registry_report_payloads=payloads,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        localize=lambda zh, en: zh,
    ) == {"status": "interrupt"}


def test_handle_tui_guard_settings_action_runs_status_or_cancelled_accept() -> None:
    calls = []
    cfg = {"cfg": True}

    class Console:
        @staticmethod
        def print(message):
            calls.append(("print", message))

    result = handle_tui_guard_settings_action(
        cfg,
        snapshot_guard_tui_payload=lambda: ("Guard", ["info"], [{"id": "status"}]),
        select_channel_action_tui=lambda title, info, actions: calls.append(("select", title, info, actions)) or "status",
        handle_guard_command=lambda args, *, bootstrap_cfg: calls.append(("guard", args, bootstrap_cfg)),
        confirm_guard_accept_from_tui=lambda _cfg: calls.append(("confirm",)) or False,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=Console(),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("select", "Guard", ["info"], [{"id": "status"}]),
        ("guard", ["status"], cfg),
        ("pause", "按 Enter 返回设置"),
    ]

    calls.clear()
    result = handle_tui_guard_settings_action(
        cfg,
        snapshot_guard_tui_payload=lambda: ("Guard", [], []),
        select_channel_action_tui=lambda *_args: "accept",
        handle_guard_command=lambda *_args, **_kwargs: calls.append(("guard",)),
        confirm_guard_accept_from_tui=lambda cfg_arg: calls.append(("confirm", cfg_arg)) or False,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=Console(),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("confirm", cfg),
        ("print", "[yellow]已取消接受当前快照。[/yellow]"),
        ("pause", "按 Enter 返回设置"),
    ]


def test_handle_tui_guard_settings_action_handles_accept_interrupt_and_back() -> None:
    calls = []
    cfg = {}

    assert handle_tui_guard_settings_action(
        cfg,
        snapshot_guard_tui_payload=lambda: ("Guard", [], []),
        select_channel_action_tui=lambda *_args: "accept",
        handle_guard_command=lambda args, *, bootstrap_cfg: calls.append(("guard", args, bootstrap_cfg)),
        confirm_guard_accept_from_tui=lambda cfg_arg: calls.append(("confirm", cfg_arg)) or True,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=type("Console", (), {"print": staticmethod(lambda message: calls.append(("print", message)))})(),
    ) == {"status": "continue"}

    assert calls == [
        ("confirm", cfg),
        ("guard", ["accept"], cfg),
        ("pause", "按 Enter 返回设置"),
    ]

    calls.clear()
    assert handle_tui_guard_settings_action(
        cfg,
        snapshot_guard_tui_payload=lambda: ("Guard", [], []),
        select_channel_action_tui=lambda *_args: None,
        handle_guard_command=lambda *_args, **_kwargs: calls.append(("guard",)),
        confirm_guard_accept_from_tui=lambda _cfg: calls.append(("confirm",)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=type("Console", (), {"print": staticmethod(lambda message: calls.append(("print", message)))})(),
    ) == {"status": "continue"}
    assert calls == []

    assert handle_tui_guard_settings_action(
        cfg,
        snapshot_guard_tui_payload=lambda: ("Guard", [], []),
        select_channel_action_tui=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt),
        handle_guard_command=lambda *_args, **_kwargs: calls.append(("guard",)),
        confirm_guard_accept_from_tui=lambda _cfg: calls.append(("confirm",)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=type("Console", (), {"print": staticmethod(lambda message: calls.append(("print", message)))})(),
    ) == {"status": "interrupt"}


def test_handle_tui_about_settings_action_handles_back_refresh_and_upgrade() -> None:
    calls = []
    actions = iter(["refresh_versions", "upgrade_codex_cli", "back"])

    class Console:
        @staticmethod
        def print(message):
            calls.append(("print", message))

    def about_status_snapshot(*, force_update):
        calls.append(("snapshot", force_update))
        return {"force": force_update}

    def about_tui_payload(snapshot):
        calls.append(("payload", snapshot))
        return ("About", ["line"], [{"id": "back"}])

    result = handle_tui_about_settings_action(
        about_status_snapshot=about_status_snapshot,
        about_tui_payload=about_tui_payload,
        select_channel_action_tui=lambda title, lines, actions_arg: calls.append(("select", title, lines, actions_arg)) or next(actions),
        run_about_upgrade=lambda *, target: calls.append(("upgrade", target)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=Console(),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("snapshot", False),
        ("payload", {"force": False}),
        ("select", "About", ["line"], [{"id": "back"}]),
        ("print", "[cyan]正在刷新 MMS / Codex / Claude 版本检查...[/cyan]"),
        ("snapshot", True),
        ("snapshot", False),
        ("payload", {"force": False}),
        ("select", "About", ["line"], [{"id": "back"}]),
        ("upgrade", "codex"),
        ("pause", "按 Enter 返回关于"),
        ("snapshot", False),
        ("payload", {"force": False}),
        ("select", "About", ["line"], [{"id": "back"}]),
    ]


def test_handle_tui_about_settings_action_handles_interrupt_and_none() -> None:
    calls = []

    def about_status_snapshot(*, force_update):
        calls.append(("snapshot", force_update))
        return {}

    def about_tui_payload(snapshot):
        calls.append(("payload", snapshot))
        return ("About", [], [])

    assert handle_tui_about_settings_action(
        about_status_snapshot=about_status_snapshot,
        about_tui_payload=about_tui_payload,
        select_channel_action_tui=lambda *_args: None,
        run_about_upgrade=lambda *, target: calls.append(("upgrade", target)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=type("Console", (), {"print": staticmethod(lambda message: calls.append(("print", message)))})(),
    ) == {"status": "continue"}
    assert calls == [("snapshot", False), ("payload", {})]

    assert handle_tui_about_settings_action(
        about_status_snapshot=lambda *, force_update: {},
        about_tui_payload=lambda snapshot: ("About", [], []),
        select_channel_action_tui=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt),
        run_about_upgrade=lambda *, target: calls.append(("upgrade", target)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        console=type("Console", (), {"print": staticmethod(lambda message: calls.append(("print", message)))})(),
    ) == {"status": "interrupt"}


def test_handle_tui_account_mgmt_settings_action_delegates() -> None:
    calls = []
    cfg = {"cfg": True}

    result = handle_tui_account_mgmt_settings_action(
        cfg,
        run_account_mgmt_tui=lambda cfg_arg: calls.append(("account_mgmt", cfg_arg)),
    )

    assert result == {"status": "continue"}
    assert calls == [("account_mgmt", cfg)]


def test_apply_rescue_default_fallback_action_saves_reports_and_pauses() -> None:
    calls = []
    cfg = {"rescue": {}}
    updated_cfg = {"rescue": {"fallback_model": "fallback-model", "hot_fallback_enabled": True}}

    result = apply_rescue_default_fallback_action(
        cfg,
        "fallback-model",
        set_rescue_default_fallback=lambda cfg_arg, *, model: calls.append(("set", cfg_arg, model)) or updated_cfg,
        save_config=lambda cfg_arg, *, reason: calls.append(("save", cfg_arg, reason)),
        rescue_default_fallback_report_payload=lambda model, **kwargs: ("title", [("model", model), ("kwargs", kwargs)]),
        rescue_hot_fallback_enabled_cfg=lambda cfg_arg: calls.append(("hot", cfg_arg)) or True,
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "cfg": updated_cfg}
    assert calls == [
        ("set", cfg, "fallback-model"),
        ("save", updated_cfg, "tui:rescue_default_fallback"),
        ("hot", updated_cfg),
        ("report", ("title", [("model", "fallback-model"), ("kwargs", {"hot_fallback_enabled": True})]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_apply_rescue_default_fallback_action_clears_default() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    cleared_cfg = {"rescue": {}}

    result = apply_rescue_default_fallback_action(
        cfg,
        "",
        cleared=True,
        set_rescue_default_fallback=lambda cfg_arg, *, model: calls.append(("set", cfg_arg, model)) or cleared_cfg,
        save_config=lambda cfg_arg, *, reason: calls.append(("save", cfg_arg, reason)),
        rescue_default_fallback_report_payload=lambda model, **kwargs: ("clear title", [("model", model), ("kwargs", kwargs)]),
        rescue_hot_fallback_enabled_cfg=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "cfg": cleared_cfg}
    assert calls == [
        ("set", cfg, ""),
        ("save", cleared_cfg, "tui:clear_rescue_default_fallback"),
        ("report", ("clear title", [("model", ""), ("kwargs", {"cleared": True})]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_rescue_landing_action_context_collects_state_and_payload() -> None:
    calls = []
    cfg = {"rescue": True}
    events = [{"id": "evt1"}]
    latest = {"note": "rescue_hot_fallback"}

    result = rescue_landing_action_context(
        cfg,
        "/repo",
        rescue_default_fallback=lambda cfg_arg: calls.append(("default", cfg_arg)) or {"model": "fallback-model"},
        rescue_hot_fallback_enabled_cfg=lambda cfg_arg: calls.append(("hot", cfg_arg)) or True,
        rescue_route_fallback_model_candidates=lambda *, limit: calls.append(("routes", limit)) or ["route1"],
        list_rescue_events=lambda *, repo_root, limit: calls.append(("events", repo_root, limit)) or events,
        latest_rescue_hot_fallback_event=lambda: calls.append(("latest",)) or latest,
        rescue_landing_tui_payload=lambda default_label, rescue_events, latest_event, hot_enabled: calls.append(("payload", default_label, rescue_events, latest_event, hot_enabled)) or ([("Default", default_label)], [("view_packets", "View")]),
    )

    assert result == {
        "default_fallback": {"model": "fallback-model"},
        "default_label": "fallback-model",
        "hot_fallback_enabled": True,
        "route_fallback_candidates": ["route1"],
        "rescue_events": events,
        "landing_info": [("Default", "fallback-model")],
        "landing_actions": [("view_packets", "View")],
    }
    assert calls == [
        ("default", cfg),
        ("hot", cfg),
        ("routes", 120),
        ("events", "/repo", 20),
        ("latest",),
        ("payload", "fallback-model", events, latest, True),
    ]


def test_select_rescue_menu_action_returns_action_continue_or_interrupt() -> None:
    info = [("k", "v")]
    actions = [("view_packets", "View")]

    assert select_rescue_menu_action(
        "Rescue",
        info,
        actions,
        select_channel_action_tui=lambda title, info_arg, actions_arg: "view_packets" if (title, info_arg, actions_arg) == ("Rescue", info, actions) else None,
    ) == {"status": "action", "action": "view_packets"}

    assert select_rescue_menu_action(
        "Rescue",
        info,
        actions,
        select_channel_action_tui=lambda *_args: "back",
    ) == {"status": "continue", "action": None}

    assert select_rescue_menu_action(
        "Rescue",
        info,
        actions,
        select_channel_action_tui=lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt),
    ) == {"status": "interrupt", "action": None}


def test_select_tui_settings_action_returns_action_continue_or_interrupt() -> None:
    assert select_tui_settings_action(
        select_settings_tui=lambda: "rescue",
    ) == {"status": "action", "action": "rescue"}

    assert select_tui_settings_action(
        select_settings_tui=lambda: None,
    ) == {"status": "continue", "action": None}

    assert select_tui_settings_action(
        select_settings_tui=lambda: (_ for _ in ()).throw(KeyboardInterrupt),
    ) == {"status": "interrupt", "action": None}


def _settings_action_deps(**overrides):
    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    deps = {
        "select_settings_tui": unused,
        "select_channel_action_tui": unused,
        "select_language_tui": unused,
        "select_rescue_event_tui": unused,
        "save_config": unused,
        "routes_export_loader": unused,
        "registry_cli_loader": unused,
        "registry_truth_tui_payload": unused,
        "print_settings_error_report": unused,
        "print_settings_result_report": unused,
        "registry_report_payloads": {},
        "pause_after_tui_report": unused,
        "localize": lambda zh, _en: zh,
        "about_status_snapshot": unused,
        "about_tui_payload": unused,
        "run_about_upgrade": unused,
        "snapshot_guard_tui_payload": unused,
        "handle_guard_command": unused,
        "confirm_guard_accept_from_tui": unused,
        "run_account_mgmt_tui": unused,
        "rescue_tools_loader": unused,
        "rescue_default_fallback": unused,
        "rescue_hot_fallback_enabled_cfg": unused,
        "rescue_route_fallback_model_candidates": unused,
        "latest_rescue_hot_fallback_event": unused,
        "rescue_landing_tui_payload": unused,
        "set_rescue_default_fallback": unused,
        "rescue_default_fallback_report_payload": unused,
        "select_model_tui_loader": unused,
        "set_rescue_hot_fallback_enabled": unused,
        "rescue_hot_fallback_toggle_report_payload": unused,
        "rescue_demo_packet_report_payload": unused,
        "rescue_fallback_model_candidates": unused,
        "rescue_handover_report_payload": unused,
        "rescue_paths_report_payload": unused,
        "console": object(),
        "ensure_rich": unused,
        "prompt_cls": type("Prompt", (), {"ask": staticmethod(unused)}),
        "set_language": unused,
    }
    deps.update(overrides)
    return TuiSettingsActionDeps(**deps)


def test_handle_tui_settings_action_handles_interrupt_and_cancel() -> None:
    cfg = {"providers": []}

    assert handle_tui_settings_action(
        cfg,
        "/repo",
        deps=_settings_action_deps(select_settings_tui=lambda: (_ for _ in ()).throw(KeyboardInterrupt)),
    ) == {"status": "interrupt", "cfg": cfg, "changed": False}

    assert handle_tui_settings_action(
        cfg,
        "/repo",
        deps=_settings_action_deps(select_settings_tui=lambda: None),
    ) == {"status": "continue", "cfg": cfg, "changed": False}


def test_handle_tui_settings_action_webui_hint_reports_without_change() -> None:
    calls = []
    cfg = {"providers": []}

    result = handle_tui_settings_action(
        cfg,
        "/repo",
        deps=_settings_action_deps(
            select_settings_tui=lambda: "settings_webui",
            print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
            pause_after_tui_report=lambda prompt: calls.append(("pause", prompt)),
        ),
    )

    assert result == {"status": "continue", "cfg": cfg, "changed": False}
    assert calls[0][0] == "report"
    assert calls[0][1][1][0] == ("推荐入口", "mmg config web (canary) / mms config web")
    assert calls[1] == ("pause", "按 Enter 返回设置")


def test_handle_tui_settings_action_retired_settings_actions_are_noops() -> None:
    cfg = {"providers": [{"id": "p1", "role": "auto", "priority": 10}]}

    for retired_action in ("advanced", "provider_mgmt"):
        assert handle_tui_settings_action(
            cfg,
            "/repo",
            deps=_settings_action_deps(select_settings_tui=lambda action=retired_action: action),
        ) == {"status": "continue", "cfg": cfg, "changed": False}

    assert cfg == {"providers": [{"id": "p1", "role": "auto", "priority": 10}]}


def test_handle_tui_settings_action_language_change_does_not_refresh_runtime() -> None:
    calls = []
    cfg = {"ui": {}}

    result = handle_tui_settings_action(
        cfg,
        "/repo",
        deps=_settings_action_deps(
            select_settings_tui=lambda: "language",
            select_language_tui=lambda: calls.append(("select_language",)) or "en",
            save_config=lambda cfg_arg: calls.append(("save", cfg_arg.copy())),
            set_language=lambda lang: calls.append(("set_language", lang)),
        ),
    )

    assert result == {
        "status": "continue",
        "cfg": cfg,
        "changed": False,
        "settings_changed": True,
    }
    assert cfg == {"ui": {"language": "en"}}
    assert calls == [
        ("select_language",),
        ("save", {"ui": {"language": "en"}}),
        ("set_language", "en"),
    ]


def test_apply_rescue_hot_fallback_toggle_action_saves_reports_and_pauses() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "fallback-model"}}
    updated_cfg = {"rescue": {"fallback_model": "fallback-model", "hot_fallback_enabled": True}}

    result = apply_rescue_hot_fallback_toggle_action(
        cfg,
        True,
        set_rescue_hot_fallback_enabled=lambda cfg_arg, *, enabled: calls.append(("set", cfg_arg, enabled)) or (updated_cfg, True),
        save_config=lambda cfg_arg, *, reason: calls.append(("save", cfg_arg, reason)),
        rescue_hot_fallback_toggle_report_payload=lambda enabled, **kwargs: ("title", [("enabled", enabled), ("kwargs", kwargs)]),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "cfg": updated_cfg, "applied": True}
    assert calls == [
        ("set", cfg, True),
        ("save", updated_cfg, "tui:rescue_hot_fallback"),
        ("report", ("title", [("enabled", True), ("kwargs", {})]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_apply_rescue_hot_fallback_toggle_action_reports_blocked_without_save() -> None:
    calls = []
    cfg = {"rescue": {}}

    result = apply_rescue_hot_fallback_toggle_action(
        cfg,
        True,
        set_rescue_hot_fallback_enabled=lambda cfg_arg, *, enabled: calls.append(("set", cfg_arg, enabled)) or (cfg_arg, False),
        save_config=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        rescue_hot_fallback_toggle_report_payload=lambda enabled, **kwargs: ("blocked", [("enabled", enabled), ("kwargs", kwargs)]),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "cfg": cfg, "applied": False}
    assert calls == [
        ("set", cfg, True),
        ("report", ("blocked", [("enabled", False), ("kwargs", {"has_default": False})]), {"ok": False}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_apply_rescue_demo_packet_action_writes_reports_and_pauses() -> None:
    calls = []
    payload = {"artifact": "demo"}

    result = apply_rescue_demo_packet_action(
        "/repo",
        write_demo_rescue_packet=lambda *, repo_root: calls.append(("write", repo_root)) or payload,
        rescue_demo_packet_report_payload=lambda payload_arg: calls.append(("payload", payload_arg)) or ("title", [("artifact", "demo")]),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "payload": payload}
    assert calls == [
        ("write", "/repo"),
        ("payload", payload),
        ("report", ("title", [("artifact", "demo")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_show_rescue_no_packets_report_prints_error_and_pauses() -> None:
    calls = []

    result = show_rescue_no_packets_report(
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue"}
    assert calls == [
        (
            "report",
            ("zh:没有 rescue packet", [("zh:状态", "zh:当前没有可查看记录")]),
            {"ok": False},
        ),
        ("pause", "按 Enter 返回设置"),
    ]


def test_select_rescue_event_action_returns_selected_continue_or_interrupt() -> None:
    rescue_events = [{"id": "evt1"}]
    selected = {"id": "evt1"}

    assert select_rescue_event_action(
        rescue_events,
        select_rescue_event_tui=lambda events: selected if events == rescue_events else None,
    ) == {"status": "selected", "selected_rescue": selected}

    assert select_rescue_event_action(
        rescue_events,
        select_rescue_event_tui=lambda _events: None,
    ) == {"status": "continue", "selected_rescue": None}

    assert select_rescue_event_action(
        rescue_events,
        select_rescue_event_tui=lambda _events: (_ for _ in ()).throw(KeyboardInterrupt),
    ) == {"status": "interrupt", "selected_rescue": None}


def test_handle_rescue_view_markdown_action_prints_content_and_pauses(tmp_path) -> None:
    calls = []
    md_path = tmp_path / "rescue.md"
    md_path.write_text("rescue body", encoding="utf-8")

    class Console:
        @staticmethod
        def clear():
            calls.append(("clear",))

        @staticmethod
        def print(message):
            calls.append(("print", message))

    result = handle_rescue_view_markdown_action(
        {"artifact_markdown": str(md_path)},
        localize=lambda zh, _en: f"zh:{zh}",
        console=Console(),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("clear",),
        ("print", "rescue body"),
        ("pause", "按 Enter 返回设置"),
    ]


def test_handle_rescue_view_markdown_action_reports_read_error_and_pauses(tmp_path) -> None:
    calls = []

    class Console:
        @staticmethod
        def clear():
            raise AssertionError("unused")

        @staticmethod
        def print(_message):
            raise AssertionError("unused")

    result = handle_rescue_view_markdown_action(
        {"artifact_markdown": str(tmp_path / "missing.md")},
        localize=lambda zh, _en: f"zh:{zh}",
        console=Console(),
        print_settings_error_report=lambda title, exc: calls.append(("error", title, type(exc).__name__)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("error", "zh:无法读取 rescue.md", "FileNotFoundError"),
        ("pause", "按 Enter 返回设置"),
    ]


def test_show_rescue_paths_action_reports_paths_and_pauses() -> None:
    calls = []
    selected_rescue = {"artifact_markdown": "/tmp/rescue.md"}

    result = show_rescue_paths_action(
        selected_rescue,
        rescue_paths_report_payload=lambda rescue: calls.append(("payload", rescue)) or ("paths", [("md", rescue["artifact_markdown"])]),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue"}
    assert calls == [
        ("payload", selected_rescue),
        ("report", ("paths", [("md", "/tmp/rescue.md")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_create_rescue_handover_action_writes_reports_and_pauses() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}
    handover = {"path": "/tmp/handover.md"}

    result = create_rescue_handover_action(
        selected_rescue,
        "fallback-model",
        write_fallback_handover=lambda rescue, *, fallback_model: calls.append(("write", rescue, fallback_model)) or handover,
        rescue_handover_report_payload=lambda payload, model: calls.append(("payload", payload, model)) or ("handover", [("model", model)]),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "handover": handover, "error": None}
    assert calls == [
        ("write", selected_rescue, "fallback-model"),
        ("payload", handover, "fallback-model"),
        ("report", ("handover", [("model", "fallback-model")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_create_rescue_handover_action_reports_error_and_pauses() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}
    failure = RuntimeError("boom")

    result = create_rescue_handover_action(
        selected_rescue,
        "fallback-model",
        write_fallback_handover=lambda rescue, *, fallback_model: calls.append(("write", rescue, fallback_model)) or (_ for _ in ()).throw(failure),
        rescue_handover_report_payload=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        print_settings_error_report=lambda title, exc: calls.append(("error", title, exc)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {"status": "continue", "handover": None, "error": failure}
    assert calls == [
        ("write", selected_rescue, "fallback-model"),
        ("error", "zh:生成 fallback handover 失败", failure),
        ("pause", "按 Enter 返回设置"),
    ]


def test_rescue_packet_action_menu_context_builds_info_actions_and_candidates() -> None:
    calls = []
    cfg = {"rescue": True}
    selected_rescue = {
        "created_at": "2026-05-29T01:02:03Z",
        "failed_model": "gpt-5.5",
        "failed_provider_id": "relay",
        "status_code": 429,
        "failure_kind": "rate_limit",
        "repo_path": "/repo",
    }

    result = rescue_packet_action_menu_context(
        cfg,
        selected_rescue,
        "default-model",
        rescue_fallback_model_candidates=lambda cfg_arg, rescue_arg, *, limit: calls.append(("fallbacks", cfg_arg, rescue_arg, limit)) or ["fb1", "fb2"],
        rescue_route_fallback_model_candidates=lambda *, failed_model, limit: calls.append(("routes", failed_model, limit)) or ["route1"],
    )

    assert result == {
        "info_lines": [
            ("时间", "2026-05-29T01:02:03Z"),
            ("模型", "gpt-5.5"),
            ("Provider", "relay"),
            ("状态", 429),
            ("原因", "rate_limit"),
            ("Repo", "/repo"),
            ("全局默认", "default-model"),
        ],
        "fallback_candidates": ["fb1", "fb2"],
        "route_fallback_candidates": ["route1"],
        "actions": [
            ("handover::fb1", "生成 fallback handover -> fb1"),
            ("handover::fb2", "生成 fallback handover -> fb2"),
            ("default::fb1", "设为全局默认 fallback -> fb1"),
            ("default::fb2", "设为全局默认 fallback -> fb2"),
            ("choose_route_handover", "从 routed models 选择 handover"),
            ("choose_route_default", "设置全局默认 fallback（routed models）"),
            ("manual_handover", "手动输入 fallback model"),
            ("manual_default", "手动输入全局默认 fallback"),
            ("clear_default", "清除全局默认 fallback"),
            ("view_md", "查看 rescue.md"),
            ("show_paths", "显示文件路径"),
            ("back", "返回"),
        ],
    }
    assert calls == [
        ("fallbacks", cfg, selected_rescue, 8),
        ("routes", "gpt-5.5", 120),
    ]


def test_select_rescue_route_fallback_model_delegates_to_model_tui() -> None:
    calls = []

    result = select_rescue_route_fallback_model(
        ["route1", "route2"],
        "选择 fallback handover model",
        select_model_tui=lambda candidates, *, title: calls.append(("select", candidates, title)) or "route2",
    )

    assert result == "route2"
    assert calls == [("select", ["route1", "route2"], "选择 fallback handover model")]


def test_resolve_rescue_action_fallback_model_uses_embedded_model_without_prompt() -> None:
    calls = []

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("unused")

    result = resolve_rescue_action_fallback_model(
        "handover::fallback-model",
        prefix="handover::",
        prompt_label="fallback model",
        prompt_default="",
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == "fallback-model"
    assert calls == []


def test_resolve_rescue_action_fallback_model_prompts_and_strips_default() -> None:
    calls = []

    class Prompt:
        @staticmethod
        def ask(label, *, default):
            calls.append(("ask", label, default))
            return "  fallback-model  "

    result = resolve_rescue_action_fallback_model(
        "manual_default",
        prefix="default::",
        prompt_label="全局默认 fallback model",
        prompt_default="old-default",
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == "fallback-model"
    assert calls == [
        ("ensure",),
        ("ask", "全局默认 fallback model", "old-default"),
    ]


def test_apply_rescue_default_from_action_applies_embedded_model() -> None:
    calls = []
    cfg = {"rescue": {}}
    updated_cfg = {"rescue": {"fallback_model": "fallback-model"}}

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("unused")

    result = apply_rescue_default_from_action(
        cfg,
        "default::fallback-model",
        {"model": "old-default"},
        apply_rescue_default_action=lambda model: calls.append(("apply", model)) or {"cfg": updated_cfg},
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == {
        "status": "continue",
        "cfg": updated_cfg,
        "fallback_model": "fallback-model",
        "applied": True,
    }
    assert calls == [("apply", "fallback-model")]


def test_apply_rescue_default_from_action_skips_empty_prompt() -> None:
    calls = []
    cfg = {"rescue": {}}

    class Prompt:
        @staticmethod
        def ask(label, *, default):
            calls.append(("ask", label, default))
            return "  "

    result = apply_rescue_default_from_action(
        cfg,
        "manual_default",
        {"model": "old-default"},
        apply_rescue_default_action=lambda _model: (_ for _ in ()).throw(AssertionError("unused")),
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == {"status": "continue", "cfg": cfg, "fallback_model": "", "applied": False}
    assert calls == [
        ("ensure",),
        ("ask", "全局默认 fallback model", "old-default"),
    ]


def test_apply_rescue_clear_default_action_clears_and_returns_cfg() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    cleared_cfg = {"rescue": {}}

    result = apply_rescue_clear_default_action(
        cfg,
        apply_rescue_default_action=lambda fallback_model, *, cleared: calls.append((fallback_model, cleared)) or {"cfg": cleared_cfg},
    )

    assert result == {"status": "continue", "cfg": cleared_cfg, "cleared": True}
    assert calls == [("", True)]


def test_handle_rescue_landing_action_returns_view_packets_or_continue() -> None:
    cfg = {"cfg": True}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    deps = {
        "apply_rescue_default_action": unused,
        "select_model_tui_loader": unused,
        "set_rescue_hot_fallback_enabled": unused,
        "save_config": unused,
        "rescue_hot_fallback_toggle_report_payload": unused,
        "write_demo_rescue_packet": unused,
        "rescue_demo_packet_report_payload": unused,
        "print_settings_result_report": unused,
        "pause_after_tui_report": unused,
        "ensure_rich": unused,
        "prompt_cls": type("Prompt", (), {"ask": staticmethod(unused)}),
    }

    assert handle_rescue_landing_action(
        cfg,
        "view_packets",
        {"model": "old"},
        [],
        "/repo",
        **deps,
    ) == {"status": "view_packets", "cfg": cfg, "result": None}

    assert handle_rescue_landing_action(
        cfg,
        "unknown",
        {"model": "old"},
        [],
        "/repo",
        **deps,
    ) == {"status": "continue", "cfg": cfg, "result": None}


def test_handle_rescue_landing_action_dispatches_existing_helpers() -> None:
    calls = []
    cfg = {"cfg": True}
    route_cfg = {"cfg": "route"}
    clear_cfg = {"cfg": "clear"}
    hot_cfg = {"cfg": "hot"}

    def apply_default(model, *, cleared=False):
        calls.append(("apply_default", model, cleared))
        return {"cfg": clear_cfg if cleared else route_cfg}

    def select_model_tui_loader():
        calls.append(("loader",))
        return lambda candidates, *, title: calls.append(("select", candidates, title)) or "route-model"

    common = {
        "apply_rescue_default_action": apply_default,
        "select_model_tui_loader": select_model_tui_loader,
        "set_rescue_hot_fallback_enabled": lambda cfg_arg, *, enabled: calls.append(("set_hot", cfg_arg, enabled)) or (hot_cfg, enabled),
        "save_config": lambda cfg_arg, *, reason: calls.append(("save", cfg_arg, reason)),
        "rescue_hot_fallback_toggle_report_payload": lambda enabled, **kwargs: ("hot", [("enabled", enabled), ("kwargs", kwargs)]),
        "write_demo_rescue_packet": lambda *, repo_root: calls.append(("demo", repo_root)) or {"repo": repo_root},
        "rescue_demo_packet_report_payload": lambda payload: calls.append(("demo_payload", payload)) or ("demo", [("repo", payload["repo"])]),
        "print_settings_result_report": lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        "pause_after_tui_report": lambda message: calls.append(("pause", message)),
        "ensure_rich": lambda: calls.append(("ensure",)),
        "prompt_cls": type("Prompt", (), {"ask": staticmethod(lambda *_args, **_kwargs: "unused")}),
    }

    assert handle_rescue_landing_action(
        cfg,
        "choose_route_default",
        {"model": "old"},
        ["route-model"],
        "/repo",
        **common,
    ) == {"status": "continue", "cfg": route_cfg, "result": {"status": "continue", "cfg": route_cfg, "fallback_model": "route-model", "applied": True}}

    assert handle_rescue_landing_action(
        cfg,
        "enable_hot_fallback",
        {"model": "old"},
        ["route-model"],
        "/repo",
        **common,
    )["cfg"] == hot_cfg

    assert handle_rescue_landing_action(
        cfg,
        "clear_default",
        {"model": "old"},
        ["route-model"],
        "/repo",
        **common,
    ) == {"status": "continue", "cfg": clear_cfg, "result": {"status": "continue", "cfg": clear_cfg, "cleared": True}}

    demo_result = handle_rescue_landing_action(
        cfg,
        "create_demo",
        {"model": "old"},
        ["route-model"],
        "/repo",
        **common,
    )
    assert demo_result["status"] == "continue"
    assert demo_result["cfg"] == cfg
    assert demo_result["result"]["payload"] == {"repo": "/repo"}

    assert calls == [
        ("loader",),
        ("select", ["route-model"], "选择全局默认 fallback model"),
        ("apply_default", "route-model", False),
        ("set_hot", cfg, True),
        ("save", hot_cfg, "tui:rescue_hot_fallback"),
        ("report", ("hot", [("enabled", True), ("kwargs", {})]), {}),
        ("pause", "按 Enter 返回设置"),
        ("apply_default", "", True),
        ("demo", "/repo"),
        ("demo_payload", {"repo": "/repo"}),
        ("report", ("demo", [("repo", "/repo")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_apply_rescue_default_from_route_selection_applies_selected_model() -> None:
    calls = []
    cfg = {"rescue": {}}
    updated_cfg = {"rescue": {"fallback_model": "route-model"}}

    result = apply_rescue_default_from_route_selection(
        cfg,
        ["route-model"],
        "选择全局默认 fallback model",
        select_model_tui=lambda candidates, *, title: calls.append(("select", candidates, title)) or "route-model",
        apply_rescue_default_action=lambda model: calls.append(("apply", model)) or {"cfg": updated_cfg},
    )

    assert result == {
        "status": "continue",
        "cfg": updated_cfg,
        "fallback_model": "route-model",
        "applied": True,
    }
    assert calls == [
        ("select", ["route-model"], "选择全局默认 fallback model"),
        ("apply", "route-model"),
    ]


def test_apply_rescue_default_from_route_selection_skips_empty_selection() -> None:
    calls = []
    cfg = {"rescue": {}}

    result = apply_rescue_default_from_route_selection(
        cfg,
        ["route-model"],
        "选择全局默认 fallback model",
        select_model_tui=lambda candidates, *, title: calls.append(("select", candidates, title)) or None,
        apply_rescue_default_action=lambda _model: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result == {"status": "continue", "cfg": cfg, "fallback_model": "", "applied": False}
    assert calls == [("select", ["route-model"], "选择全局默认 fallback model")]


def test_create_rescue_handover_from_action_creates_embedded_model() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}
    handover = {"path": "/tmp/handover.md"}

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("unused")

    result = create_rescue_handover_from_action(
        selected_rescue,
        "handover::fallback-model",
        write_fallback_handover=lambda rescue, *, fallback_model: calls.append(("write", rescue, fallback_model)) or handover,
        rescue_handover_report_payload=lambda payload, model: calls.append(("payload", payload, model)) or ("handover", [("model", model)]),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == {
        "status": "continue",
        "handover": handover,
        "error": None,
        "fallback_model": "fallback-model",
        "applied": True,
    }
    assert calls == [
        ("write", selected_rescue, "fallback-model"),
        ("payload", handover, "fallback-model"),
        ("report", ("handover", [("model", "fallback-model")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_create_rescue_handover_from_action_skips_empty_prompt() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}

    class Prompt:
        @staticmethod
        def ask(label, *, default):
            calls.append(("ask", label, default))
            return "  "

    result = create_rescue_handover_from_action(
        selected_rescue,
        "manual_handover",
        write_fallback_handover=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        rescue_handover_report_payload=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda _message: (_ for _ in ()).throw(AssertionError("unused")),
        ensure_rich=lambda: calls.append(("ensure",)),
        prompt_cls=Prompt,
    )

    assert result == {
        "status": "continue",
        "handover": None,
        "fallback_model": "",
        "applied": False,
    }
    assert calls == [
        ("ensure",),
        ("ask", "fallback model", ""),
    ]


def test_create_rescue_handover_from_route_selection_creates_selected_model() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}
    handover = {"path": "/tmp/handover.md"}

    result = create_rescue_handover_from_route_selection(
        selected_rescue,
        ["route-model"],
        "选择 fallback handover model",
        select_model_tui=lambda candidates, *, title: calls.append(("select", candidates, title)) or "route-model",
        write_fallback_handover=lambda rescue, *, fallback_model: calls.append(("write", rescue, fallback_model)) or handover,
        rescue_handover_report_payload=lambda payload, model: calls.append(("payload", payload, model)) or ("handover", [("model", model)]),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
    )

    assert result == {
        "status": "continue",
        "handover": handover,
        "error": None,
        "fallback_model": "route-model",
        "applied": True,
    }
    assert calls == [
        ("select", ["route-model"], "选择 fallback handover model"),
        ("write", selected_rescue, "route-model"),
        ("payload", handover, "route-model"),
        ("report", ("handover", [("model", "route-model")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_create_rescue_handover_from_route_selection_skips_empty_selection() -> None:
    calls = []
    selected_rescue = {"failed_model": "gpt-5.5"}

    result = create_rescue_handover_from_route_selection(
        selected_rescue,
        ["route-model"],
        "选择 fallback handover model",
        select_model_tui=lambda candidates, *, title: calls.append(("select", candidates, title)) or None,
        write_fallback_handover=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        rescue_handover_report_payload=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        localize=lambda zh, _en: f"zh:{zh}",
        print_settings_result_report=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unused")),
        print_settings_error_report=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        pause_after_tui_report=lambda _message: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert result == {
        "status": "continue",
        "handover": None,
        "fallback_model": "",
        "applied": False,
    }
    assert calls == [("select", ["route-model"], "选择 fallback handover model")]


def test_handle_rescue_packet_action_show_paths_keeps_cfg_and_reports() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    selected_rescue = {"artifact_markdown": "/tmp/rescue.md"}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    result = handle_rescue_packet_action(
        cfg,
        selected_rescue,
        "show_paths",
        {"model": "old"},
        [],
        select_model_tui_loader=unused,
        apply_rescue_default_action=unused,
        write_fallback_handover=unused,
        rescue_handover_report_payload=unused,
        rescue_paths_report_payload=lambda rescue: calls.append(("payload", rescue)) or ("paths", [("md", rescue["artifact_markdown"])]),
        localize=lambda zh, _en: zh,
        console=object(),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        print_settings_error_report=unused,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {"status": "continue", "cfg": cfg, "result": {"status": "continue"}}
    assert calls == [
        ("payload", selected_rescue),
        ("report", ("paths", [("md", "/tmp/rescue.md")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_handle_rescue_packet_action_applies_default_and_clear() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    default_cfg = {"rescue": {"fallback_model": "new"}}
    cleared_cfg = {"rescue": {}}

    def apply_default(model, *, cleared=False):
        calls.append(("apply", model, cleared))
        return {"cfg": cleared_cfg if cleared else default_cfg}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    common = {
        "select_model_tui_loader": unused,
        "apply_rescue_default_action": apply_default,
        "write_fallback_handover": unused,
        "rescue_handover_report_payload": unused,
        "rescue_paths_report_payload": unused,
        "localize": lambda zh, _en: zh,
        "console": object(),
        "print_settings_result_report": unused,
        "print_settings_error_report": unused,
        "pause_after_tui_report": unused,
        "ensure_rich": lambda: calls.append(("ensure",)),
        "prompt_cls": type("Prompt", (), {"ask": staticmethod(unused)}),
    }

    assert handle_rescue_packet_action(
        cfg,
        {"failed_model": "gpt-5.5"},
        "default::new",
        {"model": "old"},
        [],
        **common,
    ) == {
        "status": "continue",
        "cfg": default_cfg,
        "result": {
            "status": "continue",
            "cfg": default_cfg,
            "fallback_model": "new",
            "applied": True,
        },
    }

    assert handle_rescue_packet_action(
        cfg,
        {"failed_model": "gpt-5.5"},
        "clear_default",
        {"model": "old"},
        [],
        **common,
    ) == {
        "status": "continue",
        "cfg": cleared_cfg,
        "result": {"status": "continue", "cfg": cleared_cfg, "cleared": True},
    }
    assert calls == [
        ("apply", "new", False),
        ("apply", "", True),
    ]


def test_handle_rescue_packet_action_choose_route_handover_writes_report() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    selected_rescue = {"failed_model": "gpt-5.5"}
    handover = {"path": "/tmp/handover.md"}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    def select_model_tui_loader():
        calls.append(("loader",))
        return lambda candidates, *, title: calls.append(("select", candidates, title)) or "route-model"

    result = handle_rescue_packet_action(
        cfg,
        selected_rescue,
        "choose_route_handover",
        {"model": "old"},
        ["route-model"],
        select_model_tui_loader=select_model_tui_loader,
        apply_rescue_default_action=unused,
        write_fallback_handover=lambda rescue, *, fallback_model: calls.append(("write", rescue, fallback_model)) or handover,
        rescue_handover_report_payload=lambda payload, model: calls.append(("payload", payload, model)) or ("handover", [("model", model)]),
        rescue_paths_report_payload=unused,
        localize=lambda zh, _en: zh,
        console=object(),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        print_settings_error_report=unused,
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {
        "status": "continue",
        "cfg": cfg,
        "result": {
            "status": "continue",
            "handover": handover,
            "error": None,
            "fallback_model": "route-model",
            "applied": True,
        },
    }
    assert calls == [
        ("loader",),
        ("select", ["route-model"], "选择 fallback handover model"),
        ("write", selected_rescue, "route-model"),
        ("payload", handover, "route-model"),
        ("report", ("handover", [("model", "route-model")]), {}),
        ("pause", "按 Enter 返回设置"),
    ]


def test_handle_rescue_packet_action_unknown_is_noop() -> None:
    cfg = {"rescue": {"fallback_model": "old"}}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    result = handle_rescue_packet_action(
        cfg,
        {"failed_model": "gpt-5.5"},
        "back",
        {"model": "old"},
        [],
        select_model_tui_loader=unused,
        apply_rescue_default_action=unused,
        write_fallback_handover=unused,
        rescue_handover_report_payload=unused,
        rescue_paths_report_payload=unused,
        localize=lambda zh, _en: zh,
        console=object(),
        print_settings_result_report=unused,
        print_settings_error_report=unused,
        pause_after_tui_report=unused,
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {"status": "continue", "cfg": cfg, "result": None}


def test_handle_tui_rescue_settings_action_interrupts_from_landing_menu() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    result = handle_tui_rescue_settings_action(
        cfg,
        "/repo",
        rescue_default_fallback=lambda cfg_arg: calls.append(("default", cfg_arg)) or {"model": "old"},
        rescue_hot_fallback_enabled_cfg=lambda cfg_arg: calls.append(("hot", cfg_arg)) or False,
        rescue_route_fallback_model_candidates=lambda **kwargs: calls.append(("routes", kwargs)) or ["route-model"],
        list_rescue_events=lambda *, repo_root, limit: calls.append(("events", repo_root, limit)) or [],
        latest_rescue_hot_fallback_event=lambda: calls.append(("latest",)) or None,
        rescue_landing_tui_payload=lambda *args: calls.append(("payload", args)) or ([("info", "value")], [("back", "返回")]),
        select_channel_action_tui=lambda *args: calls.append(("select", args)) or "__interrupt__",
        set_rescue_default_fallback=unused,
        save_config=unused,
        rescue_default_fallback_report_payload=unused,
        print_settings_result_report=unused,
        pause_after_tui_report=unused,
        select_model_tui_loader=unused,
        set_rescue_hot_fallback_enabled=unused,
        rescue_hot_fallback_toggle_report_payload=unused,
        write_demo_rescue_packet=unused,
        rescue_demo_packet_report_payload=unused,
        localize=lambda zh, _en: zh,
        select_rescue_event_tui=unused,
        rescue_fallback_model_candidates=unused,
        write_fallback_handover=unused,
        rescue_handover_report_payload=unused,
        rescue_paths_report_payload=unused,
        console=object(),
        print_settings_error_report=unused,
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {"status": "interrupt", "cfg": cfg}
    assert calls[-1] == ("select", ("Rescue / Current-session Fallback", [("info", "value")], [("back", "返回")]))


def test_handle_tui_rescue_settings_action_view_packets_without_events_reports() -> None:
    calls = []
    cfg = {"rescue": {}}

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    result = handle_tui_rescue_settings_action(
        cfg,
        "/repo",
        rescue_default_fallback=lambda _cfg: {"model": ""},
        rescue_hot_fallback_enabled_cfg=lambda _cfg: False,
        rescue_route_fallback_model_candidates=lambda **_kwargs: [],
        list_rescue_events=lambda *, repo_root, limit: calls.append(("events", repo_root, limit)) or [],
        latest_rescue_hot_fallback_event=lambda: None,
        rescue_landing_tui_payload=lambda *args: calls.append(("payload", args)) or ([("default", args[0])], [("view_packets", "查看")]),
        select_channel_action_tui=lambda *args: calls.append(("select", args)) or "view_packets",
        set_rescue_default_fallback=unused,
        save_config=unused,
        rescue_default_fallback_report_payload=unused,
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        select_model_tui_loader=unused,
        set_rescue_hot_fallback_enabled=unused,
        rescue_hot_fallback_toggle_report_payload=unused,
        write_demo_rescue_packet=unused,
        rescue_demo_packet_report_payload=unused,
        localize=lambda zh, _en: zh,
        select_rescue_event_tui=unused,
        rescue_fallback_model_candidates=unused,
        write_fallback_handover=unused,
        rescue_handover_report_payload=unused,
        rescue_paths_report_payload=unused,
        console=object(),
        print_settings_error_report=unused,
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {"status": "continue", "cfg": cfg}
    assert ("events", "/repo", 20) in calls
    assert ("report", ("没有 rescue packet", [("状态", "当前没有可查看记录")]), {"ok": False}) in calls
    assert ("pause", "按 Enter 返回设置") in calls


def test_handle_tui_rescue_settings_action_dispatches_packet_and_updates_cfg() -> None:
    calls = []
    cfg = {"rescue": {"fallback_model": "old"}}
    cleared_cfg = {"rescue": {}}
    selected_rescue = {"failed_model": "gpt-5.5"}
    actions = iter(["view_packets", "clear_default"])

    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    def route_candidates(**kwargs):
        calls.append(("routes", kwargs))
        return ["route-model"]

    def set_default(cfg_arg, *, model):
        calls.append(("set_default", cfg_arg, model))
        assert model == ""
        return cleared_cfg

    result = handle_tui_rescue_settings_action(
        cfg,
        "/repo",
        rescue_default_fallback=lambda cfg_arg: calls.append(("default", cfg_arg)) or {"model": "old"},
        rescue_hot_fallback_enabled_cfg=lambda cfg_arg: calls.append(("hot", cfg_arg)) or False,
        rescue_route_fallback_model_candidates=route_candidates,
        list_rescue_events=lambda *, repo_root, limit: calls.append(("events", repo_root, limit)) or [selected_rescue],
        latest_rescue_hot_fallback_event=lambda: calls.append(("latest",)) or None,
        rescue_landing_tui_payload=lambda *args: calls.append(("payload", args)) or ([("default", args[0])], [("view_packets", "查看")]),
        select_channel_action_tui=lambda *args: calls.append(("select", args)) or next(actions),
        set_rescue_default_fallback=set_default,
        save_config=lambda cfg_arg, *, reason: calls.append(("save", cfg_arg, reason)),
        rescue_default_fallback_report_payload=lambda fallback, **kwargs: calls.append(("default_payload", fallback, kwargs)) or ("default", [("fallback", fallback)]),
        print_settings_result_report=lambda *args, **kwargs: calls.append(("report", args, kwargs)),
        pause_after_tui_report=lambda message: calls.append(("pause", message)),
        select_model_tui_loader=unused,
        set_rescue_hot_fallback_enabled=unused,
        rescue_hot_fallback_toggle_report_payload=unused,
        write_demo_rescue_packet=unused,
        rescue_demo_packet_report_payload=unused,
        localize=lambda zh, _en: zh,
        select_rescue_event_tui=lambda events: calls.append(("event_select", events)) or selected_rescue,
        rescue_fallback_model_candidates=lambda cfg_arg, rescue_arg, *, limit: calls.append(("fallbacks", cfg_arg, rescue_arg, limit)) or ["fallback-model"],
        write_fallback_handover=unused,
        rescue_handover_report_payload=unused,
        rescue_paths_report_payload=unused,
        console=object(),
        print_settings_error_report=unused,
        ensure_rich=unused,
        prompt_cls=type("Prompt", (), {"ask": staticmethod(unused)}),
    )

    assert result == {"status": "continue", "cfg": cleared_cfg}
    assert ("select", ("Rescue / Current-session Fallback", [("default", "old")], [("view_packets", "查看")])) in calls
    assert ("event_select", [selected_rescue]) in calls
    assert ("set_default", cfg, "") in calls
    assert ("save", cleared_cfg, "tui:clear_rescue_default_fallback") in calls
    assert ("report", ("default", [("fallback", "")]), {}) in calls
    assert ("pause", "按 Enter 返回设置") in calls


def test_confirm_agent_pack_accepts_new_and_legacy_values() -> None:
    assert confirm_agent_pack("OMC") == "omc"
    assert confirm_agent_pack("none") == "none"
    assert confirm_agent_pack(True) == "ecc"
    assert confirm_agent_pack(False) == "none"


def test_normalize_confirm_result_supports_current_tuple_shape() -> None:
    surfaces = {"xmem": True}
    result = normalize_confirm_result(
        ("", True, True, False, "omc", False, "medium", surfaces, True),
        "high",
    )

    assert result == {
        "action": "",
        "bypass": True,
        "claude_1m_enabled": True,
        "caveman_enabled": False,
        "agent_pack": "omc",
        "thinking_enabled": False,
        "reasoning_effort": "medium",
        "disabled_session_surfaces": surfaces,
        "nsr_enabled": True,
        "caveman_level": "light",
        "confirm_returned_surfaces": True,
    }
    assert normalize_confirm_result(
        ("", True, True, True, "omc", False, "medium", surfaces, True, "full"),
        "high",
    )["caveman_level"] == "full"


def test_normalize_confirm_result_supports_legacy_tuple_shapes() -> None:
    assert normalize_confirm_result(("s", True, False, True, True), "high") == {
        "action": "s",
        "bypass": True,
        "claude_1m_enabled": False,
        "caveman_enabled": True,
        "agent_pack": "ecc",
        "thinking_enabled": True,
        "reasoning_effort": "high",
        "disabled_session_surfaces": {},
        "nsr_enabled": False,
        "caveman_level": "light",
        "confirm_returned_surfaces": False,
    }
    assert normalize_confirm_result(("b", False, True), "low")["caveman_enabled"] is False
    assert normalize_confirm_result("q", "medium")["action"] == "q"


def test_apply_confirm_runtime_preferences_sets_claude_modes() -> None:
    runtime = {"disabled_session_surfaces": {"old": True}}
    apply_confirm_runtime_preferences(
        runtime,
        "claude",
        claude_1m_enabled=True,
        caveman_enabled=True,
        agent_pack="omc",
        thinking_enabled=False,
        reasoning_effort="LOW",
        disabled_session_surfaces={"xmem": True},
        nsr_enabled=True,
        has_nsr=True,
        confirm_returned_surfaces=True,
        merge_disabled_session_surfaces=lambda *_args: {"unexpected": True},
    )

    assert runtime == {
        "claude_1m_mode": "enable",
        "agent_pack": "omc",
        "ecc_mode": "disable",
        "omc_mode": "enable",
        "caveman_mode": "enable",
        "caveman_level": "light",
        "nsr_mode": "enable",
        "disabled_session_surfaces": {"xmem": True},
        "thinking_mode": "disable",
        "reasoning_effort": "low",
    }


def test_apply_confirm_runtime_preferences_merges_legacy_surfaces() -> None:
    runtime = {"disabled_session_surfaces": {"context": True}}
    merge_calls = []

    def merge_disabled_session_surfaces(existing, incoming):
        merge_calls.append((existing, incoming))
        return {"context": True, "toon": True}

    apply_confirm_runtime_preferences(
        runtime,
        "codex",
        claude_1m_enabled=False,
        caveman_enabled=False,
        agent_pack="ecc",
        thinking_enabled=True,
        reasoning_effort="",
        disabled_session_surfaces={"toon": True},
        nsr_enabled=True,
        has_nsr=False,
        confirm_returned_surfaces=False,
        merge_disabled_session_surfaces=merge_disabled_session_surfaces,
    )

    assert runtime == {
        "disabled_session_surfaces": {"context": True, "toon": True},
        "caveman_mode": "disable",
        "caveman_level": "light",
        "nsr_mode": "disable",
        "thinking_mode": "enable",
        "reasoning_effort": "high",
    }
    assert merge_calls == [({"context": True}, {"toon": True})]


def test_build_confirm_capability_context_enables_domestic_claude_addons() -> None:
    runtime = {"reasoning_effort": "LOW"}
    clean_model_info = {"model": "qwen3-max"}
    preview_calls = []

    def build_preview(cli_name, runtime_arg, **kwargs):
        preview_calls.append((cli_name, runtime_arg, kwargs))
        return {"preview": kwargs}

    context = build_confirm_capability_context(
        "claude",
        runtime,
        clean_model_info,
        confirm_context_lines=lambda cli_name, runtime_arg: [cli_name, runtime_arg["reasoning_effort"]],
        caveman_available_for_cli=lambda cli_name: cli_name == "claude",
        nsr_available_for_cli=lambda cli_name: cli_name == "claude",
        ecc_available_for_claude=lambda: True,
        omc_available_for_claude=lambda: True,
        model_info_looks_domestic=lambda model_info: model_info is clean_model_info,
        default_reasoning_effort_for_model_info=lambda _model_info: "high",
        build_confirm_preview_catalog=build_preview,
    )

    assert context == {
        "context_lines": ["claude", "LOW"],
        "has_caveman": True,
        "has_nsr": True,
        "has_ecc": True,
        "has_omc": True,
        "default_reasoning_effort": "low",
        "default_caveman_level": "light",
        "preview_catalog": {
            "preview": {
                "has_caveman": True,
                "has_nsr": True,
                "has_ecc": True,
                "has_omc": True,
            }
        },
    }
    assert preview_calls[0][1] is runtime


def test_build_confirm_capability_context_blocks_non_claude_addons() -> None:
    context = build_confirm_capability_context(
        "codex",
        {},
        {"model": "gpt-5.4"},
        confirm_context_lines=lambda *_args: [],
        caveman_available_for_cli=lambda _cli_name: False,
        nsr_available_for_cli=lambda _cli_name: True,
        ecc_available_for_claude=lambda: True,
        omc_available_for_claude=lambda: True,
        model_info_looks_domestic=lambda _model_info: True,
        default_reasoning_effort_for_model_info=lambda _model_info: "medium",
        build_confirm_preview_catalog=lambda *_args, **kwargs: kwargs,
    )

    assert context["has_ecc"] is False
    assert context["has_omc"] is False
    assert context["has_nsr"] is True
    assert context["default_reasoning_effort"] == "medium"


def test_confirm_tui_options_preserves_confirm_defaults() -> None:
    runtime = {
        "caveman_mode": "disable",
        "nsr_mode": "enable",
        "agent_pack": "omc",
        "thinking_mode": "disable",
    }

    assert confirm_tui_options(
        env_vars={"A": "B"},
        once=True,
        context_lines=["ctx"],
        has_caveman=True,
        has_nsr=True,
        has_ecc=False,
        has_omc=True,
        runtime=runtime,
        default_reasoning_effort="medium",
        preview_catalog={"preview": True},
    ) == {
        "env_vars": {"A": "B"},
        "once": True,
        "context_lines": ["ctx"],
        "has_caveman": True,
        "caveman_enabled_default": False,
        "caveman_level_default": "light",
        "has_nsr": True,
        "nsr_enabled_default": True,
        "has_ecc": False,
        "ecc_enabled_default": False,
        "has_omc": True,
        "agent_pack_default": "omc",
        "thinking_enabled_default": False,
        "reasoning_effort_default": "medium",
        "preview_catalog": {"preview": True},
        "runtime": runtime,
    }


def test_run_confirm_tui_prompt_builds_options_and_normalizes_result() -> None:
    calls = []
    runtime = {"reasoning_effort": "LOW", "nsr_mode": "enable"}
    model_info = {"model": "qwen3-max"}

    def confirm_tui(cli_name, clean_model_info, **kwargs):
        calls.append(("confirm", cli_name, clean_model_info, kwargs))
        return ("", True, True, False, "omc", False, "medium", {"toon": True}, True)

    result = run_confirm_tui_prompt(
        "claude",
        model_info,
        runtime,
        env_vars={"A": "B"},
        once=True,
        confirm_tui=confirm_tui,
        confirm_context_lines=lambda cli_name, runtime_arg: calls.append(("context", cli_name, runtime_arg)) or ["ctx"],
        caveman_available_for_cli=lambda cli_name: cli_name == "claude",
        nsr_available_for_cli=lambda cli_name: cli_name == "claude",
        ecc_available_for_claude=lambda: True,
        omc_available_for_claude=lambda: True,
        model_info_looks_domestic=lambda model_info_arg: model_info_arg is model_info,
        default_reasoning_effort_for_model_info=lambda _model_info: "high",
        build_confirm_preview_catalog=lambda cli_name, runtime_arg, **kwargs: calls.append(("preview", cli_name, runtime_arg, kwargs)) or {"preview": kwargs},
    )

    assert result == {
        "status": "continue",
        "confirm_result": {
            "action": "",
            "bypass": True,
            "claude_1m_enabled": True,
            "caveman_enabled": False,
            "agent_pack": "omc",
            "thinking_enabled": False,
            "reasoning_effort": "medium",
            "disabled_session_surfaces": {"toon": True},
            "nsr_enabled": True,
            "caveman_level": "light",
            "confirm_returned_surfaces": True,
        },
        "has_nsr": True,
    }
    assert calls[0] == ("context", "claude", runtime)
    assert calls[1] == (
        "preview",
        "claude",
        runtime,
        {"has_caveman": True, "has_nsr": True, "has_ecc": True, "has_omc": True},
    )
    assert calls[2][0:3] == ("confirm", "claude", model_info)
    assert calls[2][3]["env_vars"] == {"A": "B"}
    assert calls[2][3]["once"] is True
    assert calls[2][3]["context_lines"] == ["ctx"]
    assert calls[2][3]["reasoning_effort_default"] == "low"
    assert calls[2][3]["caveman_level_default"] == "light"
    assert calls[2][3]["preview_catalog"] == {
        "preview": {"has_caveman": True, "has_nsr": True, "has_ecc": True, "has_omc": True}
    }


def test_run_confirm_tui_prompt_handles_interrupt() -> None:
    assert run_confirm_tui_prompt(
        "codex",
        {"model": "gpt-5.4"},
        {},
        env_vars={},
        once=False,
        confirm_tui=lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
        confirm_context_lines=lambda *_args: [],
        caveman_available_for_cli=lambda _cli: False,
        nsr_available_for_cli=lambda _cli: False,
        ecc_available_for_claude=lambda: False,
        omc_available_for_claude=lambda: False,
        model_info_looks_domestic=lambda _model_info: False,
        default_reasoning_effort_for_model_info=lambda _model_info: "high",
        build_confirm_preview_catalog=lambda *_args, **_kwargs: {},
    ) == {"status": "interrupt"}


def test_resolve_confirm_launch_action_maps_exit_back_and_launch_preferences() -> None:
    assert resolve_confirm_launch_action({"action": "q"}, has_nsr=True) == {"status": "exit"}
    assert resolve_confirm_launch_action({"action": "b"}, has_nsr=False) == {"status": "back"}

    result = resolve_confirm_launch_action(
        {
            "action": "",
            "bypass": True,
            "claude_1m_enabled": True,
            "caveman_enabled": False,
            "caveman_level": "light",
            "agent_pack": "omc",
            "thinking_enabled": True,
            "reasoning_effort": "medium",
            "disabled_session_surfaces": {"toon": True},
            "nsr_enabled": True,
            "confirm_returned_surfaces": True,
        },
        has_nsr=True,
    )

    assert result == {
        "status": "launch",
        "bypass": True,
        "runtime_preferences": {
            "claude_1m_enabled": True,
            "caveman_enabled": False,
            "agent_pack": "omc",
            "thinking_enabled": True,
            "reasoning_effort": "medium",
            "disabled_session_surfaces": {"toon": True},
            "nsr_enabled": True,
            "has_nsr": True,
            "caveman_level": "light",
            "confirm_returned_surfaces": True,
        },
    }


def test_apply_confirm_bypass_flag_only_for_launch_clis() -> None:
    runtime = {}
    apply_confirm_bypass_flag(runtime, "codex", True)
    assert runtime == {"bypass": True}

    runtime = {}
    apply_confirm_bypass_flag(runtime, "chat", True)
    assert runtime == {}


def test_execute_confirmed_launch_applies_flags_preferences_and_launches() -> None:
    calls = []
    runtime = {"auth_mode": "api_key"}
    clean_model_info = {"model": "claude-sonnet"}
    runtime_preferences = {
        "claude_1m_enabled": True,
        "caveman_enabled": True,
        "agent_pack": "ecc",
        "thinking_enabled": False,
        "reasoning_effort": "LOW",
        "disabled_session_surfaces": {"toon": True},
        "nsr_enabled": True,
        "has_nsr": True,
        "confirm_returned_surfaces": True,
        "caveman_level": "full",
    }

    result = execute_confirmed_launch(
        "claude",
        clean_model_info,
        runtime,
        bypass=True,
        runtime_preferences=runtime_preferences,
        once=True,
        network_guard_enforcer_loader=lambda: (
            lambda runtime_arg, *, require_proxy: calls.append(("enforce", runtime_arg, require_proxy)),
            lambda runtime_arg: calls.append(("requires_proxy", runtime_arg)) or True,
        ),
        merge_disabled_session_surfaces=lambda *_args: (_ for _ in ()).throw(AssertionError("unused")),
        launch_with_tracking=lambda cli, model, runtime_arg, *, once: calls.append(("launch", cli, model, runtime_arg, once)),
    )

    assert result == {"status": "launched"}
    assert runtime == {
        "auth_mode": "api_key",
        "bypass": True,
        "claude_1m_mode": "enable",
        "agent_pack": "ecc",
        "ecc_mode": "enable",
        "omc_mode": "disable",
        "caveman_mode": "enable",
        "caveman_level": "full",
        "nsr_mode": "enable",
        "disabled_session_surfaces": {"toon": True},
        "thinking_mode": "disable",
        "reasoning_effort": "low",
    }
    assert calls == [
        ("requires_proxy", runtime),
        ("enforce", runtime, True),
        ("launch", "claude", clean_model_info, runtime, True),
    ]


def _launch_confirmation_deps(**overrides):
    def unused(*_args, **_kwargs):
        raise AssertionError("unused")

    deps = {
        "once": False,
        "check_cli_installed": lambda _cli: True,
        "check_and_offer_install_loader": unused,
        "select_and_apply_opencode_profile": lambda runtime, *, use_tui: runtime,
        "runtime_with_launch_preferences": lambda _cfg, runtime, _cli: runtime,
        "runtime_with_vision_sidecar": lambda _cfg, runtime: runtime,
        "clean_model_info": lambda model_info: dict(model_info),
        "get_export_env": lambda _cli, _runtime: {},
        "network_guard_preview_loader": unused,
        "confirm_tui": lambda *_args, **_kwargs: ("", False, False, False),
        "confirm_context_lines": lambda _cli, _runtime: [],
        "caveman_available_for_cli": lambda _cli: False,
        "nsr_available_for_cli": lambda _cli: False,
        "ecc_available_for_claude": lambda: False,
        "omc_available_for_claude": lambda: False,
        "model_info_looks_domestic": lambda _model_info: False,
        "default_reasoning_effort_for_model_info": lambda _model_info: "high",
        "build_confirm_preview_catalog": lambda *_args, **_kwargs: {},
        "network_guard_enforcer_loader": unused,
        "merge_disabled_session_surfaces": lambda old, new: new or old or {},
        "launch_with_tracking": unused,
    }
    deps.update(overrides)
    return TuiLaunchConfirmationDeps(**deps)


def _family_payload_deps(**overrides):
    deps = {
        "build_model_families_for_cli": lambda *_args, **_kwargs: [
            {"family": "GPT", "models": [{"model": "gpt-5.4"}]},
        ],
        "cli_default_family_first": {},
        "family_is_cold_for_tui": lambda *_args, **_kwargs: False,
        "sort_family_entries_for_tui": lambda entries, **_kwargs: entries,
        "make_provider_options_loader": lambda *_args, **_kwargs: (lambda _model: []),
    }
    deps.update(overrides)
    return TuiFamilyPayloadDeps(**deps)


def test_run_tui_launcher_loop_launches_selected_candidate() -> None:
    calls = []
    cfg = {"cfg": True}
    provider = {"id": "provider"}
    runtime = {"id": "runtime"}

    class Console:
        @staticmethod
        def print(message):
            calls.append(("print", message))

    result = run_tui_launcher_loop(
        cfg,
        provider,
        ["gpt-5.4"],
        ["codex"],
        deps=TuiLauncherLoopDeps(
            select_family_tui=lambda *_args, **_kwargs: ("family", "codex", "GPT"),
            get_scene_usage=lambda: ({}, {}),
            broker_enabled_by_cli=lambda _cfg, cli_names: {cli: False for cli in cli_names},
            opencode_profile_menu_options=lambda: [],
            official_account_menu_options=lambda *_args, **_kwargs: [],
            launch_broker_experiment_interactive=lambda *_args, **_kwargs: False,
            settings_action_deps_loader=lambda: _settings_action_deps(),
            settings_repo_root="/repo",
            family_payload_deps=_family_payload_deps(),
            launch_candidate_deps=_launch_candidate_deps(
                select_submodel_tui=lambda *_args, **_kwargs: {"model": "gpt-5.4"},
                resolve_best_provider=lambda *_args, **_kwargs: (runtime, None),
            ),
            launch_confirmation_deps=_launch_confirmation_deps(
                launch_with_tracking=lambda cli, model, runtime_arg, *, once: calls.append(
                    ("launch", cli, model, runtime_arg["id"], once)
                ),
            ),
            console=Console(),
        ),
    )

    assert result is True
    assert calls == [("launch", "codex", {"model": "gpt-5.4"}, "runtime", False)]


def test_handle_tui_launch_confirmation_returns_continue_for_profile_cancel_and_back() -> None:
    runtime = {"id": "runtime"}

    assert handle_tui_launch_confirmation(
        {},
        "opencode",
        {"model": "gpt-5.4"},
        runtime,
        deps=_launch_confirmation_deps(
            select_and_apply_opencode_profile=lambda _runtime, *, use_tui: None,
        ),
    ) == {"status": "continue"}

    assert handle_tui_launch_confirmation(
        {},
        "codex",
        {"model": "gpt-5.4"},
        runtime,
        deps=_launch_confirmation_deps(
            confirm_tui=lambda *_args, **_kwargs: "b",
        ),
    ) == {"status": "continue"}


def test_handle_tui_launch_confirmation_launches_with_prepared_runtime() -> None:
    calls = []
    cfg = {"cfg": True}
    runtime = {"id": "runtime"}
    preferred_runtime = {"id": "runtime", "preferred": True}
    model_info = {"model": "gpt-5.4", "extra": True}

    result = handle_tui_launch_confirmation(
        cfg,
        "codex",
        model_info,
        runtime,
        deps=_launch_confirmation_deps(
            once=True,
            runtime_with_launch_preferences=lambda cfg_arg, runtime_arg, cli: calls.append(("prefs", cfg_arg, runtime_arg, cli)) or preferred_runtime,
            clean_model_info=lambda model: calls.append(("clean", model)) or {"model": model["model"]},
            get_export_env=lambda cli, runtime_arg: calls.append(("env", cli, runtime_arg)) or {"A": "B"},
            confirm_context_lines=lambda cli, runtime_arg: calls.append(("context", cli, runtime_arg)) or ["ctx"],
            confirm_tui=lambda cli, clean_model, **kwargs: calls.append(("confirm", cli, clean_model, kwargs)) or ("", True, False, True),
            launch_with_tracking=lambda cli, clean_model, runtime_arg, *, once: calls.append(("launch", cli, clean_model, dict(runtime_arg), once)),
        ),
    )

    assert result == {"status": "exit"}
    assert calls[0] == ("prefs", cfg, runtime, "codex")
    assert calls[1] == ("clean", model_info)
    assert calls[2] == ("env", "codex", preferred_runtime)
    assert calls[3] == ("context", "codex", preferred_runtime)
    assert calls[4][0:3] == ("confirm", "codex", {"model": "gpt-5.4"})
    assert calls[4][3]["env_vars"] == {"A": "B"}
    assert calls[4][3]["context_lines"] == ["ctx"]
    assert calls[5] == (
        "launch",
        "codex",
        {"model": "gpt-5.4"},
        {
            "id": "runtime",
            "preferred": True,
            "bypass": True,
            "caveman_mode": "enable",
            "caveman_level": "light",
            "nsr_mode": "disable",
            "disabled_session_surfaces": {},
            "thinking_mode": "enable",
            "reasoning_effort": "high",
        },
        True,
    )
