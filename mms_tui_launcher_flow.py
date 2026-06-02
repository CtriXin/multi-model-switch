"""Helpers for MMS TUI launcher flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mms_session.features import normalize_caveman_level, normalize_caveman_mode


@dataclass(frozen=True)
class TuiFamilyPayloadDeps:
    build_model_families_for_cli: Callable[..., Any]
    cli_default_family_first: Any
    family_is_cold_for_tui: Callable[..., Any]
    sort_family_entries_for_tui: Callable[..., Any]
    make_provider_options_loader: Callable[..., Any]


@dataclass(frozen=True)
class TuiRuntimeRefreshDeps:
    probe_cache: Any
    probe_file_cache_dir: Any
    rmtree: Callable[..., Any]
    ensure_provider_credentials: Callable[..., Any]
    probe_models: Callable[..., Any]
    resolve_visible_clis: Callable[..., Any]


@dataclass(frozen=True)
class TuiLaunchCandidateDeps:
    select_submodel_tui: Callable[..., Any]
    apply_priority_changes: Callable[..., Any]
    resolve_last_used_runtime: Callable[..., Any]
    resolve_best_provider: Callable[..., Any]
    choose_runtime_source: Callable[..., Any]
    trace_record: Callable[..., Any]
    trace_runtime_choice: Callable[..., Any]
    provider_browse_tui_loader: Callable[..., Any]
    provider_candidates: Callable[..., Any]
    default_provider_id: str
    provider_supports_cli_name: Callable[..., Any]
    provider_label: Callable[..., Any]
    resolve_provider_context: Callable[..., Any]
    probe_models: Callable[..., Any]
    filter_visible_models: Callable[..., Any]
    agy_connect_profile_id: str
    connect_action: Callable[..., Any]
    resolve_opencode_profile_runtime: Callable[..., Any]
    resolve_account_context: Callable[..., Any]
    account_id: str | None = None
    provider_id: str | None = None


@dataclass(frozen=True)
class TuiSettingsActionDeps:
    select_settings_tui: Callable[..., Any]
    select_channel_action_tui: Callable[..., Any]
    select_language_tui: Callable[..., Any]
    select_rescue_event_tui: Callable[..., Any]
    select_provider_mgmt_tui: Callable[..., Any]
    save_config: Callable[..., Any]
    probe_cache: Any
    ensure_provider_credentials: Callable[..., Any]
    probe_models: Callable[..., Any]
    provider_mgmt_export_model_routes_loader: Callable[..., Any]
    routes_export_loader: Callable[..., Any]
    registry_cli_loader: Callable[..., Any]
    registry_truth_tui_payload: Callable[..., Any]
    print_settings_error_report: Callable[..., Any]
    print_settings_result_report: Callable[..., Any]
    registry_report_payloads: Any
    pause_after_tui_report: Callable[..., Any]
    localize: Callable[..., Any]
    about_status_snapshot: Callable[..., Any]
    about_tui_payload: Callable[..., Any]
    run_about_upgrade: Callable[..., Any]
    snapshot_guard_tui_payload: Callable[..., Any]
    handle_guard_command: Callable[..., Any]
    confirm_guard_accept_from_tui: Callable[..., Any]
    run_account_mgmt_tui: Callable[..., Any]
    rescue_tools_loader: Callable[..., Any]
    rescue_default_fallback: Callable[..., Any]
    rescue_hot_fallback_enabled_cfg: Callable[..., Any]
    rescue_route_fallback_model_candidates: Callable[..., Any]
    latest_rescue_hot_fallback_event: Callable[..., Any]
    rescue_landing_tui_payload: Callable[..., Any]
    set_rescue_default_fallback: Callable[..., Any]
    rescue_default_fallback_report_payload: Callable[..., Any]
    select_model_tui_loader: Callable[..., Any]
    set_rescue_hot_fallback_enabled: Callable[..., Any]
    rescue_hot_fallback_toggle_report_payload: Callable[..., Any]
    rescue_demo_packet_report_payload: Callable[..., Any]
    rescue_fallback_model_candidates: Callable[..., Any]
    rescue_handover_report_payload: Callable[..., Any]
    rescue_paths_report_payload: Callable[..., Any]
    console: Any
    ensure_rich: Callable[..., Any]
    prompt_cls: Any
    set_language: Callable[..., Any]


@dataclass(frozen=True)
class TuiLaunchConfirmationDeps:
    once: bool
    check_cli_installed: Callable[..., Any]
    check_and_offer_install_loader: Callable[..., Any]
    select_and_apply_opencode_profile: Callable[..., Any]
    runtime_with_launch_preferences: Callable[..., Any]
    runtime_with_vision_sidecar: Callable[..., Any]
    clean_model_info: Callable[..., Any]
    get_export_env: Callable[..., Any]
    network_guard_preview_loader: Callable[..., Any]
    confirm_tui: Callable[..., Any]
    confirm_context_lines: Callable[..., Any]
    caveman_available_for_cli: Callable[..., Any]
    nsr_available_for_cli: Callable[..., Any]
    ecc_available_for_claude: Callable[..., Any]
    omc_available_for_claude: Callable[..., Any]
    model_info_looks_domestic: Callable[..., Any]
    default_reasoning_effort_for_model_info: Callable[..., Any]
    build_confirm_preview_catalog: Callable[..., Any]
    network_guard_enforcer_loader: Callable[..., Any]
    merge_disabled_session_surfaces: Callable[..., Any]
    launch_with_tracking: Callable[..., Any]


@dataclass(frozen=True)
class TuiLauncherLoopDeps:
    select_family_tui: Callable[..., Any]
    get_scene_usage: Callable[..., Any]
    broker_enabled_by_cli: Callable[..., Any]
    opencode_profile_menu_options: Callable[..., Any]
    official_account_menu_options: Callable[..., Any]
    launch_broker_experiment_interactive: Callable[..., Any]
    settings_action_deps_loader: Callable[..., Any]
    settings_repo_root: str
    family_payload_deps: TuiFamilyPayloadDeps
    launch_candidate_deps: TuiLaunchCandidateDeps
    launch_confirmation_deps: TuiLaunchConfirmationDeps
    console: Any


def safe_tui_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyboardInterrupt:
        return "__interrupt__"


def opencode_lite_pro_health_summary_text(
    repo_root=None,
    profile_id="agent",
    *,
    normalize_opencode_profile_id,
    agent_profile_id,
    load_opencode_route_health_latest,
    opencode_lite_pro_specs,
):
    profile_id = normalize_opencode_profile_id(profile_id) or agent_profile_id
    latest = load_opencode_route_health_latest(repo_root)
    expected_roles = {str(spec.get("key") or "").strip() for spec in opencode_lite_pro_specs(profile_id)}
    expected = len(expected_roles)
    counts = {"live_healthy": 0, "degraded": 0, "unhealthy": 0, "blocked": 0, "untested": 0}
    role_rows = {}
    for row in latest.values():
        if not isinstance(row, dict) or row.get("profile") != profile_id:
            continue
        if (
            str(row.get("model") or "").strip().lower().startswith("mimo-")
            and str(row.get("protocol") or "").strip() == "openai_chat_completions"
            and row.get("error_class") == "cache_sensitive_wrong_protocol"
        ):
            continue
        role = str(row.get("role") or row.get("route_id") or "").strip()
        if role not in expected_roles:
            continue
        existing = role_rows.get(role)
        if existing is None or str(row.get("finished_at") or "") >= str(existing.get("finished_at") or ""):
            role_rows[role] = row
    for row in role_rows.values():
        status = str(row.get("status") or "untested")
        counts[status if status in counts else "untested"] += 1
    counts["untested"] += max(0, expected - len(role_rows))
    if counts["live_healthy"] == expected:
        return f"health: {expected}/{expected} healthy"
    parts = [f"{counts['live_healthy']}/{expected} healthy"]
    for status in ("degraded", "unhealthy", "blocked", "untested"):
        if counts[status]:
            parts.append(f"{counts[status]} {status}")
    return "health: " + ", ".join(parts)


def opencode_profile_menu_options(
    *,
    profile_options,
    normalize_opencode_profile_id,
    agent_profile_id,
    health_summary_text,
):
    options = []
    for option in profile_options:
        profile_id = normalize_opencode_profile_id(option.get("profile_id") or option["id"])
        summary = option["summary"]
        if profile_id == agent_profile_id:
            lite_pro_health = health_summary_text(profile_id=profile_id)
        else:
            lite_pro_health = ""
        if lite_pro_health:
            summary = f"{summary} {lite_pro_health}"
        options.append({
            "id": option["id"],
            "label": option["label"],
            "summary": summary,
            "badge": option.get("badge", ""),
        })
    return options


def official_account_menu_options(
    cfg,
    cli_name,
    *,
    accounts_for_cli,
    account_label,
    localize,
    default_priority,
    agy_connect_profile_id,
):
    accounts = list(accounts_for_cli(cfg, cli_name))
    defaults = cfg.get("account", {}).get("defaults", {}) if isinstance(cfg, dict) else {}

    def _sort_key(account):
        account_id = str(account.get("id") or "")
        is_default = account_id == defaults.get(cli_name)
        return (
            0 if is_default else 1,
            -int(account.get("priority", default_priority) or default_priority),
            account_label(account),
            account_id,
        )

    options = []
    for account in sorted(accounts, key=_sort_key):
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            continue
        is_default = account_id == defaults.get(cli_name)
        summary_parts = [localize("官方 OAuth", "Official OAuth"), account_id]
        if is_default:
            summary_parts.append(localize("默认", "default"))
        options.append({
            "id": account_id,
            "label": account_label(account),
            "summary": " / ".join(summary_parts),
            "badge": "*" if is_default else "OAuth",
        })

    if options or cli_name != "agy":
        return options

    legacy_gemini_count = len(accounts_for_cli(cfg, "gemini"))
    if legacy_gemini_count:
        summary = localize(
            "检测到 Gemini CLI 旧账号；Antigravity 需要独立 agy OAuth，按 Enter 或 O 接入。",
            "Legacy Gemini CLI accounts detected; Antigravity needs a separate agy OAuth account. Press Enter or O to connect.",
        )
    else:
        summary = localize(
            "还没有 Antigravity OAuth account，按 Enter 或 O 接入。",
            "No Antigravity OAuth account yet. Press Enter or O to connect.",
        )
    return [{
        "id": agy_connect_profile_id,
        "label": localize("接入 Antigravity OAuth", "Connect Antigravity OAuth"),
        "summary": summary,
        "badge": "O",
    }]


def select_opencode_profile(
    *,
    use_tui=False,
    profile_menu_options,
    ensure_rich,
    table_cls,
    int_prompt_cls,
    console,
):
    options = profile_menu_options()
    if use_tui:
        try:
            from mms_tui import select_channel_action_tui
            return select_channel_action_tui(
                "OpenCode Mode",
                [(option["label"], option["summary"]) for option in options[:4]],
                [(option["id"], option["label"]) for option in options],
            )
        except Exception:
            return None

    ensure_rich()
    table = table_cls()(title="OpenCode Mode")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Mode", style="green")
    table.add_column("说明", style="dim")
    for idx, option in enumerate(options, 1):
        label = f"{option.get('badge')} {option['label']}".strip()
        table.add_row(str(idx), label, option["summary"])
    console.print(table)
    while True:
        try:
            choice = int_prompt_cls().ask("选择 OpenCode mode")
            if 1 <= choice <= len(options):
                return options[choice - 1]["id"]
            console.print(f"[red]请输入 1-{len(options)}[/red]")
        except KeyboardInterrupt:
            return None


def build_tui_family_payloads(
    cfg,
    cli_names,
    current_provider,
    default_models,
    *,
    deps,
):
    families_by_cli = {}
    families_detail = {}
    provider_options_by_cli = {}
    provider_options_loader_by_cli = {}
    for cli_name in cli_names:
        raw = deps.build_model_families_for_cli(
            cfg, cli_name, current_provider, default_models
        )
        family_entries = []
        preferred_family = deps.cli_default_family_first.get(cli_name)
        for family in raw:
            model_entries = [model for model in family["models"] if isinstance(model, dict)]
            total_use = sum(int(model.get("use_count", 0) or 0) for model in model_entries)
            family_last_used_at = max(
                (str(model.get("last_used_at") or "").strip() for model in model_entries),
                default="",
            )
            family_entries.append({
                "family": family["family"],
                "count": len(family["models"]),
                "use_count": total_use,
                "last_used_at": family_last_used_at,
                "is_cold": deps.family_is_cold_for_tui(
                    family["family"],
                    total_use,
                    family_last_used_at,
                    preferred_family=preferred_family,
                ),
            })
        families_by_cli[cli_name] = deps.sort_family_entries_for_tui(
            family_entries,
            preferred_family=preferred_family,
        )
        families_detail[cli_name] = {family["family"]: family["models"] for family in raw}
        provider_options_by_cli[cli_name] = {}
        provider_options_loader_by_cli[cli_name] = deps.make_provider_options_loader(
            cfg, cli_name, current_provider, default_models
        )
    return families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli


def provider_browse_options(
    cfg,
    current_provider,
    default_models,
    cli_name,
    *,
    provider_candidates,
    default_provider_id,
    provider_supports_cli_name,
    provider_label,
):
    browse_providers = []
    seen_ids = set()
    for provider, _cached in provider_candidates(cfg, current_provider, default_models):
        provider_id = provider.get("id", default_provider_id)
        if provider_id in seen_ids:
            continue
        if not provider.get("enabled", True):
            continue
        if not provider_supports_cli_name(provider, cli_name):
            continue
        if not provider.get("api_key"):
            continue
        seen_ids.add(provider_id)
        browse_providers.append({
            "id": provider_id,
            "name": provider_label(provider),
            "role": provider.get("role", "auto"),
            "priority": provider.get("priority", 100),
        })
    return browse_providers


def provider_browse_model_options(
    cfg,
    selected_provider_id,
    *,
    resolve_provider_context,
    probe_models,
    filter_visible_models,
):
    selected_provider = resolve_provider_context(cfg, selected_provider_id)
    selected_probe = probe_models(selected_provider, emit_output=False)
    provider_models = filter_visible_models(selected_probe.get("models") or [])
    return selected_provider, provider_models


def provider_browse_launch_context(
    cli_name,
    selected_provider_id,
    selected_provider,
    model_result,
    *,
    trace_record,
    trace_runtime_choice,
):
    model_info = model_result
    runtime = selected_provider
    trace_record("provider browse", cli=cli_name, provider=selected_provider_id, model=model_info.get("model"))
    trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice="provider browse")
    return model_info, runtime


def handle_tui_provider_browse_action(
    cfg,
    cli_name,
    current_provider,
    default_models,
    *,
    select_provider_browse_tui,
    select_provider_models_tui,
    provider_candidates,
    default_provider_id,
    provider_supports_cli_name,
    provider_label,
    resolve_provider_context,
    probe_models,
    filter_visible_models,
    trace_record,
    trace_runtime_choice,
):
    browse_providers = provider_browse_options(
        cfg,
        current_provider,
        default_models,
        cli_name,
        provider_candidates=provider_candidates,
        default_provider_id=default_provider_id,
        provider_supports_cli_name=provider_supports_cli_name,
        provider_label=provider_label,
    )
    if not browse_providers:
        return {"status": "continue", "message": "没有可用的 Provider"}

    prov_result = safe_tui_call(select_provider_browse_tui, browse_providers)
    if prov_result is None or prov_result == "__interrupt__":
        return {"status": "continue"}
    selected_pid, selected_pname = prov_result

    selected_prov, prov_models = provider_browse_model_options(
        cfg,
        selected_pid,
        resolve_provider_context=resolve_provider_context,
        probe_models=probe_models,
        filter_visible_models=filter_visible_models,
    )
    if not prov_models:
        return {"status": "continue", "message": f"{selected_pname} 没有可用模型"}

    model_result = safe_tui_call(select_provider_models_tui, selected_pname, prov_models)
    if model_result is None:
        return {"status": "continue"}
    if model_result == "__exit__":
        return {"status": "exit"}

    model_info, runtime = provider_browse_launch_context(
        cli_name,
        selected_pid,
        selected_prov,
        model_result,
        trace_record=trace_record,
        trace_runtime_choice=trace_runtime_choice,
    )
    return {"status": "launch", "model_info": model_info, "runtime": runtime}


def select_tui_launcher_family_action(
    *,
    select_family_tui,
    families_by_cli,
    cli_names,
    last_by_cli,
    families_detail,
    provider_options_by_cli,
    provider_options_loader_by_cli,
    broker_enabled_by_cli,
    profile_options_by_cli,
):
    result = safe_tui_call(
        select_family_tui,
        families_by_cli,
        cli_names,
        last_used=last_by_cli,
        families_detail=families_detail,
        provider_options_by_cli=provider_options_by_cli,
        provider_options_loader_by_cli=provider_options_loader_by_cli,
        broker_enabled_by_cli=broker_enabled_by_cli,
        profile_options_by_cli=profile_options_by_cli,
    )

    if result == "fallback":
        return {"status": "fallback"}
    if result == "__interrupt__":
        return {"status": "exit"}
    if result is None:
        return {"status": "exit"}
    action_type, cli_name, action_data = result
    return {
        "status": "action",
        "action_type": action_type,
        "cli": cli_name,
        "action_data": action_data,
    }



def last_used_model_info(action_data):
    return (
        action_data.get("model_info")
        if isinstance(action_data.get("model_info"), dict)
        else {"model": action_data["model"]}
    )


def resolve_last_used_launch_context(
    cfg,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    resolve_last_used_runtime,
    resolve_best_provider,
    choose_runtime_source,
    trace_runtime_choice,
):
    model_info = last_used_model_info(action_data)
    runtime = None
    restored_choice = ""
    runtime, _restored_models, restored_choice = resolve_last_used_runtime(
        cfg, cli_name, action_data, default_models
    )
    runtime_from_best_provider = False
    if runtime is not None:
        trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice=restored_choice)
    else:
        runtime, _ = resolve_best_provider(
            cfg, action_data["model"], current_provider, default_models, cli_name=cli_name
        )
        runtime_from_best_provider = runtime is not None
    if runtime is None:
        runtime, _, cli_name = choose_runtime_source(
            cfg,
            cli_name,
            current_provider,
            default_models,
            account_id=account_id,
            provider_id=provider_id,
            model_info=model_info,
            allow_selected_model_accounts=True,
        )
    if runtime_from_best_provider:
        trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice="best provider")
    return model_info, runtime, cli_name


def handle_tui_last_used_action(
    cfg,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    trace_record,
    resolve_last_used_runtime,
    resolve_best_provider,
    choose_runtime_source,
    trace_runtime_choice,
):
    trace_record("last used", cli=cli_name, model=action_data.get("model"))
    model_info, runtime, selected_cli = resolve_last_used_launch_context(
        cfg,
        cli_name,
        action_data,
        current_provider,
        default_models,
        account_id=account_id,
        provider_id=provider_id,
        resolve_last_used_runtime=resolve_last_used_runtime,
        resolve_best_provider=resolve_best_provider,
        choose_runtime_source=choose_runtime_source,
        trace_runtime_choice=trace_runtime_choice,
    )
    if runtime is None:
        return {"status": "continue", "message": f"{selected_cli} 没有可用 provider"}
    return {
        "status": "launch",
        "model_info": model_info,
        "runtime": runtime,
        "cli": selected_cli,
    }


def handle_tui_last_action(
    cfg,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    trace_record,
    resolve_last_used_runtime,
    resolve_best_provider,
    choose_runtime_source,
    trace_runtime_choice,
):
    return handle_tui_last_used_action(
        cfg,
        cli_name,
        action_data,
        current_provider,
        default_models,
        account_id=account_id,
        provider_id=provider_id,
        trace_record=trace_record,
        resolve_last_used_runtime=resolve_last_used_runtime,
        resolve_best_provider=resolve_best_provider,
        choose_runtime_source=choose_runtime_source,
        trace_runtime_choice=trace_runtime_choice,
    )


def selected_model_launch_context(
    cfg,
    cli_name,
    selected,
    current_provider,
    default_models,
    *,
    resolve_best_provider,
    trace_runtime_choice,
):
    model_info = {"model": selected["model"]}
    runtime = selected.get("provider_ctx")
    runtime_from_best_provider = runtime is not None
    if runtime is None:
        runtime, _ = resolve_best_provider(
            cfg, selected["model"], current_provider, default_models, cli_name=cli_name
        )
        runtime_from_best_provider = runtime is not None
    if runtime_from_best_provider:
        trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice="best provider")
    return model_info, runtime


def handle_tui_selected_model_action(
    cfg,
    cli_name,
    selected,
    family_name,
    current_provider,
    default_models,
    *,
    apply_priority_changes,
    selected_model_launch_context,
    resolve_best_provider,
    trace_record,
    trace_runtime_choice,
):
    priority_changes = selected.pop("priority_changes", None)
    families_dirty = bool(apply_priority_changes(cfg, priority_changes))

    model_info, runtime = selected_model_launch_context(
        cfg,
        cli_name,
        selected,
        current_provider,
        default_models,
        resolve_best_provider=resolve_best_provider,
        trace_runtime_choice=trace_runtime_choice,
    )
    if runtime is None:
        return {
            "status": "continue",
            "message": f"没有可用 provider 承载 {selected['model']}",
            "families_dirty": families_dirty,
        }
    trace_record(
        f'family "{family_name}"',
        cli=cli_name,
        model=selected.get("model"),
        provider=(runtime or {}).get("id") if isinstance(runtime, dict) else selected.get("provider_id"),
    )
    return {
        "status": "launch",
        "model_info": model_info,
        "runtime": runtime,
        "families_dirty": families_dirty,
    }


def handle_tui_family_action(
    cfg,
    cli_name,
    family_name,
    families_detail,
    provider_options_by_cli,
    last_by_cli,
    current_provider,
    default_models,
    *,
    select_submodel_tui,
    account_id=None,
    provider_id=None,
    apply_priority_changes,
    resolve_last_used_runtime,
    resolve_best_provider,
    choose_runtime_source,
    trace_record,
    trace_runtime_choice,
):
    models = families_detail.get(cli_name, {}).get(family_name, [])
    if not models:
        return {
            "status": "continue",
            "message": f"{family_name} 下没有可用模型",
            "families_dirty": False,
        }

    provider_options = provider_options_by_cli.get(cli_name, {})
    selected = safe_tui_call(
        select_submodel_tui,
        family_name,
        models,
        provider_options=provider_options,
        last_used=last_by_cli.get(cli_name),
    )
    if selected == "__interrupt__":
        return {"status": "interrupt", "families_dirty": False}
    if selected is None:
        return {"status": "continue", "families_dirty": False}
    if selected == "__last__":
        action_data = last_by_cli.get(cli_name) or {}
        if not action_data.get("model"):
            return {"status": "continue", "families_dirty": False}
        last_action = handle_tui_last_used_action(
            cfg,
            cli_name,
            action_data,
            current_provider,
            default_models,
            account_id=account_id,
            provider_id=provider_id,
            trace_record=trace_record,
            resolve_last_used_runtime=resolve_last_used_runtime,
            resolve_best_provider=resolve_best_provider,
            choose_runtime_source=choose_runtime_source,
            trace_runtime_choice=trace_runtime_choice,
        )
        return {**last_action, "families_dirty": False}

    return handle_tui_selected_model_action(
        cfg,
        cli_name,
        selected,
        family_name,
        current_provider,
        default_models,
        apply_priority_changes=apply_priority_changes,
        selected_model_launch_context=selected_model_launch_context,
        resolve_best_provider=resolve_best_provider,
        trace_record=trace_record,
        trace_runtime_choice=trace_runtime_choice,
    )


def handle_tui_submodel_action(
    cfg,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    apply_priority_changes,
    resolve_best_provider,
    trace_record,
    trace_runtime_choice,
):
    selected = dict(action_data or {})
    family_name = selected.pop("_family_name", "模型")
    return handle_tui_selected_model_action(
        cfg,
        cli_name,
        selected,
        family_name,
        current_provider,
        default_models,
        apply_priority_changes=apply_priority_changes,
        selected_model_launch_context=selected_model_launch_context,
        resolve_best_provider=resolve_best_provider,
        trace_record=trace_record,
        trace_runtime_choice=trace_runtime_choice,
    )


def opencode_profile_launch_context(
    cfg,
    current_provider,
    default_models,
    profile_id,
    *,
    resolve_opencode_profile_runtime,
    trace_record,
    trace_runtime_choice,
):
    model_info, runtime = resolve_opencode_profile_runtime(
        cfg,
        current_provider,
        default_models,
        profile_id,
    )
    if runtime is None:
        return model_info, runtime
    trace_record(
        "opencode profile",
        cli="opencode",
        profile=runtime.get("opencode_profile"),
        model=model_info.get("model") if isinstance(model_info, dict) else model_info,
        provider=runtime.get("id"),
    )
    trace_runtime_choice("runtime resolve", runtime, launch_cli="opencode", choice="opencode profile")
    return model_info, runtime


def official_account_profile_context(
    cfg,
    cli_name,
    account_id,
    *,
    resolve_account_context,
    trace_record,
    trace_runtime_choice,
):
    runtime = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
    if runtime is None or runtime.get("cli") != cli_name:
        return {}, None
    model_info = {}
    trace_record("official account", cli=cli_name, account=runtime.get("id"))
    trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice="official account")
    return model_info, runtime


def handle_tui_profile_action(
    cfg,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    agy_connect_profile_id,
    connect_action,
    resolve_opencode_profile_runtime,
    resolve_account_context,
    trace_record,
    trace_runtime_choice,
):
    if cli_name == "opencode":
        model_info, runtime = opencode_profile_launch_context(
            cfg,
            current_provider,
            default_models,
            action_data,
            resolve_opencode_profile_runtime=resolve_opencode_profile_runtime,
            trace_record=trace_record,
            trace_runtime_choice=trace_runtime_choice,
        )
        if runtime is None:
            return {
                "status": "continue",
                "message": "OpenCode Lite/Raw 未找到安全的 OpenAI-compatible GPT provider；请用 Heavy/OMO 或先配置 GPT provider。",
            }
        return {"status": "launch", "model_info": model_info, "runtime": runtime}

    if cli_name == "agy":
        if action_data == agy_connect_profile_id:
            connect_result = connect_action(cfg, cli_name)
            return {"status": "continue", **connect_result}

        model_info, runtime = official_account_profile_context(
            cfg,
            cli_name,
            action_data,
            resolve_account_context=resolve_account_context,
            trace_record=trace_record,
            trace_runtime_choice=trace_runtime_choice,
        )
        if runtime is None:
            return {"status": "continue", "message": f"未找到 {cli_name} 官方账号: {action_data}"}
        return {"status": "launch", "model_info": model_info, "runtime": runtime}

    return {"status": "continue"}


def load_provider_browse_tui_tools():
    from mms_tui import select_provider_browse_tui, select_provider_models_tui

    return {
        "select_provider_browse_tui": select_provider_browse_tui,
        "select_provider_models_tui": select_provider_models_tui,
    }


def load_export_model_routes():
    return __import__("mms_registry.router", fromlist=["export_model_routes"]).export_model_routes


def load_model_routes_exporter():
    router = __import__("mms_registry.router", fromlist=["MODEL_ROUTES_PATH", "export_model_routes"])
    return router.MODEL_ROUTES_PATH, router.export_model_routes


def load_check_and_offer_install():
    return __import__("mms_launcher.installer", fromlist=["check_and_offer_install"]).check_and_offer_install


def load_claude_network_guard_preview():
    launchers = __import__(
        "mms_launchers",
        fromlist=["get_claude_network_guard_preview", "_claude_bypass_requires_proxy"],
    )
    return launchers.get_claude_network_guard_preview, launchers._claude_bypass_requires_proxy


def load_claude_network_guard_enforcer():
    launchers = __import__(
        "mms_launchers",
        fromlist=["_enforce_claude_network_guard_or_exit", "_claude_bypass_requires_proxy"],
    )
    return launchers._enforce_claude_network_guard_or_exit, launchers._claude_bypass_requires_proxy


def handle_tui_launch_candidate_action(
    cfg,
    action_type,
    cli_name,
    action_data,
    current_provider,
    default_models,
    *,
    families_detail,
    provider_options_by_cli,
    last_by_cli,
    deps,
):
    if action_type == "profile":
        if cli_name not in {"opencode", "agy"}:
            return {"status": "continue"}
        return handle_tui_profile_action(
            cfg,
            cli_name,
            action_data,
            current_provider,
            default_models,
            agy_connect_profile_id=deps.agy_connect_profile_id,
            connect_action=deps.connect_action,
            resolve_opencode_profile_runtime=deps.resolve_opencode_profile_runtime,
            resolve_account_context=deps.resolve_account_context,
            trace_record=deps.trace_record,
            trace_runtime_choice=deps.trace_runtime_choice,
        )
    if action_type == "provider_browse":
        provider_browse_tui = deps.provider_browse_tui_loader()
        return handle_tui_provider_browse_action(
            cfg,
            cli_name,
            current_provider,
            default_models,
            select_provider_browse_tui=provider_browse_tui["select_provider_browse_tui"],
            select_provider_models_tui=provider_browse_tui["select_provider_models_tui"],
            provider_candidates=deps.provider_candidates,
            default_provider_id=deps.default_provider_id,
            provider_supports_cli_name=deps.provider_supports_cli_name,
            provider_label=deps.provider_label,
            resolve_provider_context=deps.resolve_provider_context,
            probe_models=deps.probe_models,
            filter_visible_models=deps.filter_visible_models,
            trace_record=deps.trace_record,
            trace_runtime_choice=deps.trace_runtime_choice,
        )
    if action_type == "last":
        return handle_tui_last_action(
            cfg,
            cli_name,
            action_data,
            current_provider,
            default_models,
            account_id=deps.account_id,
            provider_id=deps.provider_id,
            trace_record=deps.trace_record,
            resolve_last_used_runtime=deps.resolve_last_used_runtime,
            resolve_best_provider=deps.resolve_best_provider,
            choose_runtime_source=deps.choose_runtime_source,
            trace_runtime_choice=deps.trace_runtime_choice,
        )
    if action_type == "submodel":
        return handle_tui_submodel_action(
            cfg,
            cli_name,
            action_data,
            current_provider,
            default_models,
            apply_priority_changes=deps.apply_priority_changes,
            resolve_best_provider=deps.resolve_best_provider,
            trace_record=deps.trace_record,
            trace_runtime_choice=deps.trace_runtime_choice,
        )
    if action_type == "family":
        return handle_tui_family_action(
            cfg,
            cli_name,
            action_data,
            families_detail,
            provider_options_by_cli,
            last_by_cli,
            current_provider,
            default_models,
            select_submodel_tui=deps.select_submodel_tui,
            account_id=deps.account_id,
            provider_id=deps.provider_id,
            apply_priority_changes=deps.apply_priority_changes,
            resolve_last_used_runtime=deps.resolve_last_used_runtime,
            resolve_best_provider=deps.resolve_best_provider,
            choose_runtime_source=deps.choose_runtime_source,
            trace_record=deps.trace_record,
            trace_runtime_choice=deps.trace_runtime_choice,
        )
    return {"status": "continue"}


def refresh_tui_runtime_state_after_config_change(
    cfg,
    *,
    deps,
):
    deps.probe_cache.clear()
    deps.rmtree(deps.probe_file_cache_dir, ignore_errors=True)
    current_provider = deps.ensure_provider_credentials(cfg)
    default_models = deps.probe_models(current_provider, emit_output=False).get("models")
    current_cli_names = deps.resolve_visible_clis(cfg, current_provider, default_models)
    return current_provider, default_models, current_cli_names


def handle_tui_connect_action(
    cfg,
    cli_name,
    *,
    quick_connect_official,
    run_connect_wizard,
    refresh_runtime_state,
):
    if cli_name == "agy":
        cfg, changed = quick_connect_official(cfg, preset_cli="agy")
    else:
        cfg, changed = run_connect_wizard(cfg)
    if not changed:
        return {
            "cfg": cfg,
            "changed": False,
            "current_provider": None,
            "default_models": None,
            "current_cli_names": None,
            "families_dirty": False,
        }
    current_provider, default_models, current_cli_names = refresh_runtime_state(cfg)
    return {
        "cfg": cfg,
        "changed": True,
        "current_provider": current_provider,
        "default_models": default_models,
        "current_cli_names": current_cli_names,
        "families_dirty": True,
    }


def handle_tui_broker_action(cfg, cli_name, *, launch_broker_experiment_interactive):
    if launch_broker_experiment_interactive(cfg, cli_name):
        return {"status": "exit"}
    return {"status": "continue"}


def apply_tui_launcher_state_result(
    cfg,
    current_provider,
    default_models,
    current_cli_names,
    families_dirty,
    result,
):
    cfg = result.get("cfg", cfg)
    if result.get("changed"):
        current_provider = result.get("current_provider", current_provider)
        default_models = result.get("default_models", default_models)
        current_cli_names = result.get("current_cli_names", current_cli_names)
        families_dirty = result.get("families_dirty", families_dirty)
    return cfg, current_provider, default_models, current_cli_names, families_dirty


def resolve_tui_launch_action_result(result, cli_name, *, console):
    if result.get("message"):
        console.print(f"[yellow]{result['message']}[/yellow]")
    if result.get("status") in {"exit", "interrupt"}:
        return {
            "status": "exit",
            "families_dirty": bool(result.get("families_dirty")),
        }
    if result.get("status") != "launch":
        return {
            "status": "continue",
            "families_dirty": bool(result.get("families_dirty")),
        }
    return {
        "status": "launch",
        "model_info": result["model_info"],
        "runtime": result["runtime"],
        "cli": result.get("cli", cli_name),
        "families_dirty": bool(result.get("families_dirty")),
    }


def run_tui_launcher_loop(
    cfg,
    provider,
    default_models,
    cli_names,
    *,
    deps,
):
    current_cfg = cfg
    current_provider = provider
    current_cli_names = cli_names
    families_dirty = False

    families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = (
        build_tui_family_payloads(
            current_cfg,
            current_cli_names,
            current_provider,
            default_models,
            deps=deps.family_payload_deps,
        )
    )

    cli_name = None

    while True:
        if families_dirty:
            families_by_cli, families_detail, provider_options_by_cli, provider_options_loader_by_cli = (
                build_tui_family_payloads(
                    current_cfg,
                    current_cli_names,
                    current_provider,
                    default_models,
                    deps=deps.family_payload_deps,
                )
            )
            families_dirty = False

        last_by_cli, _ = deps.get_scene_usage()

        family_selection = select_tui_launcher_family_action(
            select_family_tui=deps.select_family_tui,
            families_by_cli=families_by_cli,
            cli_names=current_cli_names,
            last_by_cli=last_by_cli,
            families_detail=families_detail,
            provider_options_by_cli=provider_options_by_cli,
            provider_options_loader_by_cli=provider_options_loader_by_cli,
            broker_enabled_by_cli=deps.broker_enabled_by_cli(current_cfg, current_cli_names),
            profile_options_by_cli={
                "opencode": deps.opencode_profile_menu_options(),
                "agy": deps.official_account_menu_options(current_cfg, "agy"),
            },
        )

        if family_selection["status"] == "fallback":
            return False
        if family_selection["status"] == "exit":
            return True

        action_type = family_selection["action_type"]
        cli_name = family_selection["cli"]
        action_data = family_selection["action_data"]

        if action_type == "connect":
            connect_result = deps.launch_candidate_deps.connect_action(current_cfg, cli_name)
            current_cfg, current_provider, default_models, current_cli_names, families_dirty = (
                apply_tui_launcher_state_result(
                    current_cfg,
                    current_provider,
                    default_models,
                    current_cli_names,
                    families_dirty,
                    connect_result,
                )
            )
            continue

        if action_type == "broker":
            broker_result = handle_tui_broker_action(
                current_cfg,
                cli_name,
                launch_broker_experiment_interactive=deps.launch_broker_experiment_interactive,
            )
            if broker_result["status"] == "exit":
                return True
            continue

        if action_type == "settings":
            settings_result = handle_tui_settings_action(
                current_cfg,
                deps.settings_repo_root,
                deps=deps.settings_action_deps_loader(),
            )
            current_cfg, current_provider, default_models, current_cli_names, families_dirty = (
                apply_tui_launcher_state_result(
                    current_cfg,
                    current_provider,
                    default_models,
                    current_cli_names,
                    families_dirty,
                    settings_result,
                )
            )
            if settings_result["status"] == "interrupt":
                return True
            continue

        launch_candidate = handle_tui_launch_candidate_action(
            current_cfg,
            action_type,
            cli_name,
            action_data,
            current_provider,
            default_models,
            families_detail=families_detail,
            provider_options_by_cli=provider_options_by_cli,
            last_by_cli=last_by_cli,
            deps=deps.launch_candidate_deps,
        )
        current_cfg, current_provider, default_models, current_cli_names, families_dirty = (
            apply_tui_launcher_state_result(
                current_cfg,
                current_provider,
                default_models,
                current_cli_names,
                families_dirty,
                launch_candidate,
            )
        )
        launch_action = resolve_tui_launch_action_result(
            launch_candidate,
            cli_name,
            console=deps.console,
        )
        if launch_action["families_dirty"]:
            families_dirty = True
        if launch_action["status"] == "exit":
            return True
        if launch_action["status"] != "launch":
            continue

        cli_name = launch_action["cli"]
        launch_result = handle_tui_launch_confirmation(
            current_cfg,
            cli_name,
            launch_action["model_info"],
            launch_action["runtime"],
            deps=deps.launch_confirmation_deps,
        )
        if launch_result["status"] == "continue":
            continue
        return True


def apply_tui_priority_changes(
    cfg,
    priority_changes,
    *,
    apply_runtime_priority_changes,
    save_config,
    export_model_routes_loader,
):
    if not apply_runtime_priority_changes(cfg, priority_changes):
        return False
    save_config(cfg)
    try:
        export_model_routes_loader()(cfg, force=True)
    except Exception:
        pass
    return True


def select_tui_settings_action(*, select_settings_tui):
    settings_action = safe_tui_call(select_settings_tui)
    if settings_action == "__interrupt__":
        return {"status": "interrupt", "action": None}
    if settings_action is None:
        return {"status": "continue", "action": None}
    return {"status": "action", "action": settings_action}


def load_registry_cli_tools():
    from mms_registry.cli import diff_openrouter_catalog, fetch_openrouter_catalog, publish_approved_bundle, refresh_source_snapshots, registry_status, scheduled_refresh, source_freshness, verify_approved_bundle

    return {
        "diff_openrouter_catalog": diff_openrouter_catalog,
        "fetch_openrouter_catalog": fetch_openrouter_catalog,
        "publish_approved_bundle": publish_approved_bundle,
        "refresh_source_snapshots": refresh_source_snapshots,
        "registry_status": registry_status,
        "scheduled_refresh": scheduled_refresh,
        "source_freshness": source_freshness,
        "verify_approved_bundle": verify_approved_bundle,
    }


def load_rescue_tools():
    from mms_runtime.rescue import list_rescue_events, write_demo_rescue_packet, write_fallback_handover

    return {
        "list_rescue_events": list_rescue_events,
        "write_demo_rescue_packet": write_demo_rescue_packet,
        "write_fallback_handover": write_fallback_handover,
    }


def load_select_model_tui():
    from mms_tui import select_model_tui

    return select_model_tui


def handle_tui_settings_action(
    cfg,
    repo_root,
    *,
    deps,
):
    settings_result = select_tui_settings_action(
        select_settings_tui=deps.select_settings_tui,
    )
    if settings_result["status"] == "interrupt":
        return {"status": "interrupt", "cfg": cfg, "changed": False}
    if settings_result["status"] != "action":
        return {"status": "continue", "cfg": cfg, "changed": False}

    settings_action = settings_result["action"]
    if settings_action == "provider_mgmt":
        provider_mgmt_result = handle_tui_provider_mgmt_settings_action(
            cfg,
            select_provider_mgmt_tui=deps.select_provider_mgmt_tui,
            save_config=deps.save_config,
            probe_cache=deps.probe_cache,
            ensure_provider_credentials=deps.ensure_provider_credentials,
            probe_models=deps.probe_models,
            export_model_routes_loader=deps.provider_mgmt_export_model_routes_loader,
        )
        return {"cfg": cfg, **provider_mgmt_result}
    if settings_action == "language":
        language_result = handle_tui_language_settings_action(
            cfg,
            select_language_tui=deps.select_language_tui,
            save_config=deps.save_config,
            set_language=deps.set_language,
        )
        return {
            "status": language_result["status"],
            "cfg": cfg,
            "changed": False,
            "settings_changed": language_result.get("changed", False),
        }
    if settings_action == "routes_export":
        result = handle_tui_routes_export_settings_action(
            cfg,
            export_model_routes_loader=deps.routes_export_loader,
            console=deps.console,
        )
        return {"cfg": cfg, **result}
    if settings_action == "registry":
        registry_result = handle_tui_registry_settings_action(
            registry_cli_loader=deps.registry_cli_loader,
            registry_truth_tui_payload=deps.registry_truth_tui_payload,
            select_channel_action_tui=deps.select_channel_action_tui,
            print_settings_error_report=deps.print_settings_error_report,
            print_settings_result_report=deps.print_settings_result_report,
            registry_report_payloads=deps.registry_report_payloads,
            pause_after_tui_report=deps.pause_after_tui_report,
            localize=deps.localize,
        )
        return {"cfg": cfg, **registry_result}
    if settings_action == "about":
        about_result = handle_tui_about_settings_action(
            about_status_snapshot=deps.about_status_snapshot,
            about_tui_payload=deps.about_tui_payload,
            select_channel_action_tui=deps.select_channel_action_tui,
            run_about_upgrade=deps.run_about_upgrade,
            pause_after_tui_report=deps.pause_after_tui_report,
            console=deps.console,
        )
        return {"cfg": cfg, **about_result}
    if settings_action == "guard":
        guard_result = handle_tui_guard_settings_action(
            cfg,
            snapshot_guard_tui_payload=deps.snapshot_guard_tui_payload,
            select_channel_action_tui=deps.select_channel_action_tui,
            handle_guard_command=deps.handle_guard_command,
            confirm_guard_accept_from_tui=deps.confirm_guard_accept_from_tui,
            pause_after_tui_report=deps.pause_after_tui_report,
            console=deps.console,
        )
        return {"cfg": cfg, **guard_result}
    if settings_action == "account_mgmt":
        result = handle_tui_account_mgmt_settings_action(
            cfg,
            run_account_mgmt_tui=deps.run_account_mgmt_tui,
        )
        return {"cfg": cfg, **result}
    if settings_action == "rescue":
        rescue_tools = deps.rescue_tools_loader()
        rescue_result = handle_tui_rescue_settings_action(
            cfg,
            repo_root,
            rescue_default_fallback=deps.rescue_default_fallback,
            rescue_hot_fallback_enabled_cfg=deps.rescue_hot_fallback_enabled_cfg,
            rescue_route_fallback_model_candidates=deps.rescue_route_fallback_model_candidates,
            list_rescue_events=rescue_tools["list_rescue_events"],
            latest_rescue_hot_fallback_event=deps.latest_rescue_hot_fallback_event,
            rescue_landing_tui_payload=deps.rescue_landing_tui_payload,
            select_channel_action_tui=deps.select_channel_action_tui,
            set_rescue_default_fallback=deps.set_rescue_default_fallback,
            save_config=deps.save_config,
            rescue_default_fallback_report_payload=deps.rescue_default_fallback_report_payload,
            print_settings_result_report=deps.print_settings_result_report,
            pause_after_tui_report=deps.pause_after_tui_report,
            select_model_tui_loader=deps.select_model_tui_loader,
            set_rescue_hot_fallback_enabled=deps.set_rescue_hot_fallback_enabled,
            rescue_hot_fallback_toggle_report_payload=deps.rescue_hot_fallback_toggle_report_payload,
            write_demo_rescue_packet=rescue_tools["write_demo_rescue_packet"],
            rescue_demo_packet_report_payload=deps.rescue_demo_packet_report_payload,
            localize=deps.localize,
            select_rescue_event_tui=deps.select_rescue_event_tui,
            rescue_fallback_model_candidates=deps.rescue_fallback_model_candidates,
            write_fallback_handover=rescue_tools["write_fallback_handover"],
            rescue_handover_report_payload=deps.rescue_handover_report_payload,
            rescue_paths_report_payload=deps.rescue_paths_report_payload,
            console=deps.console,
            print_settings_error_report=deps.print_settings_error_report,
            ensure_rich=deps.ensure_rich,
            prompt_cls=deps.prompt_cls,
        )
        return rescue_result
    return {"status": "continue", "cfg": cfg, "changed": False}


def handle_tui_provider_mgmt_settings_action(
    cfg,
    *,
    select_provider_mgmt_tui,
    save_config,
    probe_cache,
    ensure_provider_credentials,
    probe_models,
    export_model_routes_loader,
):
    providers_raw = cfg.get("providers", [])
    result_providers = safe_tui_call(select_provider_mgmt_tui, providers_raw)
    if result_providers == "__interrupt__":
        return {"status": "interrupt"}
    if result_providers is None:
        return {"status": "continue", "changed": False}

    for updated_provider in result_providers:
        provider_id = updated_provider.get("id")
        for original in cfg.get("providers", []):
            if original.get("id") == provider_id:
                original["role"] = updated_provider.get("role", "auto")
                original["priority"] = updated_provider.get("priority", 100)
                break
    save_config(cfg)
    probe_cache.clear()
    current_provider = ensure_provider_credentials(cfg)
    default_models = probe_models(current_provider, emit_output=False).get("models")
    try:
        export_model_routes_loader()(cfg, force=True)
    except Exception:
        pass
    return {
        "status": "continue",
        "changed": True,
        "current_provider": current_provider,
        "default_models": default_models,
        "families_dirty": True,
    }


def handle_tui_language_settings_action(
    cfg,
    *,
    select_language_tui,
    save_config,
    set_language,
):
    chosen_lang = safe_tui_call(select_language_tui)
    if chosen_lang == "__interrupt__":
        return {"status": "interrupt", "changed": False}
    if chosen_lang in {"zh", "en"}:
        cfg.setdefault("ui", {})["language"] = chosen_lang
        save_config(cfg)
        set_language(chosen_lang)
        return {"status": "continue", "changed": True}
    return {"status": "continue", "changed": False}


def handle_tui_routes_export_settings_action(
    cfg,
    *,
    export_model_routes_loader,
    console,
):
    try:
        model_routes_path, export_model_routes = export_model_routes_loader()
        export_model_routes(cfg, force=True)
        console.print(f"[green]✓ 已导出 {model_routes_path}[/green]")
        return {"status": "continue", "success": True}
    except Exception as e:
        console.print(f"[red]导出失败: {e}[/red]")
        return {"status": "continue", "success": False}


def handle_tui_registry_settings_action(
    *,
    registry_cli_loader,
    registry_truth_tui_payload,
    select_channel_action_tui,
    print_settings_error_report,
    print_settings_result_report,
    registry_report_payloads,
    pause_after_tui_report,
    localize,
):
    registry_cli = registry_cli_loader()
    status = registry_cli["registry_status"]()
    registry_title, registry_info, registry_actions = registry_truth_tui_payload(status)
    registry_action = safe_tui_call(
        select_channel_action_tui,
        registry_title,
        registry_info,
        registry_actions,
    )
    if registry_action == "__interrupt__":
        return {"status": "interrupt"}

    registry_call_specs = {
        "check_staleness": (
            registry_cli["source_freshness"],
            {},
            localize("检查 Source Staleness 失败", "Check Source Staleness failed"),
            registry_report_payloads["source_staleness"],
        ),
        "refresh_sources": (
            registry_cli["refresh_source_snapshots"],
            {"if_due": False},
            localize("刷新 Sources 失败", "Refresh Sources failed"),
            registry_report_payloads["refresh_sources"],
        ),
        "refresh_due_sources": (
            registry_cli["refresh_source_snapshots"],
            {"if_due": True},
            localize("刷新 Sources 失败", "Refresh Sources failed"),
            registry_report_payloads["refresh_sources"],
        ),
        "scheduled_dry_run": (
            registry_cli["scheduled_refresh"],
            {"dry_run": True, "no_network": True},
            localize("定时刷新失败", "Scheduled Refresh failed"),
            registry_report_payloads["scheduled_refresh"],
        ),
        "scheduled_no_network": (
            registry_cli["scheduled_refresh"],
            {"dry_run": False, "no_network": True},
            localize("定时刷新失败", "Scheduled Refresh failed"),
            registry_report_payloads["scheduled_refresh"],
        ),
        "fetch_openrouter": (
            registry_cli["fetch_openrouter_catalog"],
            {},
            localize("拉取 OpenRouter Catalog 失败", "Fetch OpenRouter Catalog failed"),
            registry_report_payloads["openrouter_fetch"],
        ),
        "diff_openrouter": (
            registry_cli["diff_openrouter_catalog"],
            {"limit": 12},
            localize("OpenRouter Candidate Diff 失败", "OpenRouter Candidate Diff failed"),
            registry_report_payloads["openrouter_diff"],
        ),
        "publish_approved": (
            registry_cli["publish_approved_bundle"],
            {},
            localize("发布 Approved Bundle 失败", "Publish Approved Bundle failed"),
            registry_report_payloads["publish_approved"],
        ),
        "verify_approved": (
            registry_cli["verify_approved_bundle"],
            {},
            localize("验证 Approved Bundle 失败", "Verify Approved Bundle failed"),
            registry_report_payloads["verify_approved"],
        ),
    }

    if registry_action in registry_call_specs:
        action_func, kwargs, error_title, payload_func = registry_call_specs[registry_action]
        try:
            summary = action_func(**kwargs)
        except Exception as exc:
            print_settings_error_report(error_title, exc)
        else:
            print_settings_result_report(*payload_func(summary))
        pause_after_tui_report("按 Enter 返回设置")
    elif registry_action == "doctor":
        status = registry_cli["registry_status"]()
        print_settings_result_report(*registry_report_payloads["doctor"](status))
        pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue"}


def handle_tui_guard_settings_action(
    cfg,
    *,
    snapshot_guard_tui_payload,
    select_channel_action_tui,
    handle_guard_command,
    confirm_guard_accept_from_tui,
    pause_after_tui_report,
    console,
):
    guard_title, guard_info, guard_actions = snapshot_guard_tui_payload()
    guard_action = safe_tui_call(
        select_channel_action_tui,
        guard_title,
        guard_info,
        guard_actions,
    )
    if guard_action == "__interrupt__":
        return {"status": "interrupt"}
    if guard_action == "status":
        handle_guard_command(["status"], bootstrap_cfg=cfg)
        pause_after_tui_report("按 Enter 返回设置")
    elif guard_action == "accept":
        if confirm_guard_accept_from_tui(cfg):
            handle_guard_command(["accept"], bootstrap_cfg=cfg)
        else:
            console.print("[yellow]已取消接受当前快照。[/yellow]")
        pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue"}


def handle_tui_about_settings_action(
    *,
    about_status_snapshot,
    about_tui_payload,
    select_channel_action_tui,
    run_about_upgrade,
    pause_after_tui_report,
    console,
):
    while True:
        about_snapshot = about_status_snapshot(force_update=False)
        about_title, about_lines, about_actions = about_tui_payload(about_snapshot)
        about_action = safe_tui_call(
            select_channel_action_tui,
            about_title,
            about_lines,
            about_actions,
        )
        if about_action == "__interrupt__":
            return {"status": "interrupt"}
        if about_action in {None, "back"}:
            return {"status": "continue"}
        if about_action == "refresh_versions":
            console.print("[cyan]正在刷新 MMS / Codex / Claude 版本检查...[/cyan]")
            about_status_snapshot(force_update=True)
            continue
        if about_action in {"upgrade_mms", "upgrade_codex_cli", "upgrade_claude_cli"}:
            upgrade_target = {
                "upgrade_mms": "mms",
                "upgrade_codex_cli": "codex",
                "upgrade_claude_cli": "claude",
            }[about_action]
            run_about_upgrade(target=upgrade_target)
            pause_after_tui_report("按 Enter 返回关于")
            continue


def handle_tui_account_mgmt_settings_action(
    cfg,
    *,
    run_account_mgmt_tui,
):
    run_account_mgmt_tui(cfg)
    return {"status": "continue"}


def apply_rescue_default_fallback_action(
    cfg,
    fallback_model,
    *,
    cleared=False,
    save_reason=None,
    set_rescue_default_fallback,
    save_config,
    rescue_default_fallback_report_payload,
    rescue_hot_fallback_enabled_cfg,
    print_settings_result_report,
    pause_after_tui_report,
):
    cfg = set_rescue_default_fallback(cfg, model=fallback_model)
    save_config(
        cfg,
        reason=save_reason
        or ("tui:clear_rescue_default_fallback" if cleared else "tui:rescue_default_fallback"),
    )
    if cleared:
        print_settings_result_report(*rescue_default_fallback_report_payload("", cleared=True))
    else:
        print_settings_result_report(
            *rescue_default_fallback_report_payload(
                fallback_model,
                hot_fallback_enabled=rescue_hot_fallback_enabled_cfg(cfg),
            )
        )
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue", "cfg": cfg}


def rescue_landing_action_context(
    cfg,
    repo_root,
    *,
    rescue_default_fallback,
    rescue_hot_fallback_enabled_cfg,
    rescue_route_fallback_model_candidates,
    list_rescue_events,
    latest_rescue_hot_fallback_event,
    rescue_landing_tui_payload,
):
    default_fallback = rescue_default_fallback(cfg)
    default_label = default_fallback.get("model") or "未设置"
    hot_fallback_enabled = rescue_hot_fallback_enabled_cfg(cfg)
    route_fallback_candidates = rescue_route_fallback_model_candidates(limit=120)
    rescue_events = list_rescue_events(repo_root=repo_root, limit=20)
    landing_info, landing_actions = rescue_landing_tui_payload(
        default_label,
        rescue_events,
        latest_rescue_hot_fallback_event(),
        hot_fallback_enabled,
    )
    return {
        "default_fallback": default_fallback,
        "default_label": default_label,
        "hot_fallback_enabled": hot_fallback_enabled,
        "route_fallback_candidates": route_fallback_candidates,
        "rescue_events": rescue_events,
        "landing_info": landing_info,
        "landing_actions": landing_actions,
    }


def select_rescue_menu_action(title, info_lines, actions, *, select_channel_action_tui):
    action = safe_tui_call(select_channel_action_tui, title, info_lines, actions)
    if action == "__interrupt__":
        return {"status": "interrupt", "action": None}
    if action in {None, "back"}:
        return {"status": "continue", "action": None}
    return {"status": "action", "action": action}


def apply_rescue_hot_fallback_toggle_action(
    cfg,
    enable_hot,
    *,
    set_rescue_hot_fallback_enabled,
    save_config,
    rescue_hot_fallback_toggle_report_payload,
    print_settings_result_report,
    pause_after_tui_report,
):
    cfg, applied = set_rescue_hot_fallback_enabled(cfg, enabled=enable_hot)
    if applied != enable_hot:
        print_settings_result_report(
            *rescue_hot_fallback_toggle_report_payload(False, has_default=False),
            ok=False,
        )
    else:
        save_config(cfg, reason="tui:rescue_hot_fallback")
        print_settings_result_report(*rescue_hot_fallback_toggle_report_payload(enable_hot))
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue", "cfg": cfg, "applied": applied}


def apply_rescue_demo_packet_action(
    repo_root,
    *,
    write_demo_rescue_packet,
    rescue_demo_packet_report_payload,
    print_settings_result_report,
    pause_after_tui_report,
):
    payload = write_demo_rescue_packet(repo_root=repo_root)
    print_settings_result_report(*rescue_demo_packet_report_payload(payload))
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue", "payload": payload}


def show_rescue_no_packets_report(
    *,
    localize,
    print_settings_result_report,
    pause_after_tui_report,
):
    print_settings_result_report(
        localize("没有 rescue packet", "No rescue packet"),
        [(localize("状态", "Status"), localize("当前没有可查看记录", "No records available"))],
        ok=False,
    )
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue"}


def select_rescue_event_action(rescue_events, *, select_rescue_event_tui):
    selected_rescue = safe_tui_call(select_rescue_event_tui, rescue_events)
    if selected_rescue == "__interrupt__":
        return {"status": "interrupt", "selected_rescue": None}
    if not selected_rescue:
        return {"status": "continue", "selected_rescue": None}
    return {"status": "selected", "selected_rescue": selected_rescue}


def handle_rescue_view_markdown_action(
    selected_rescue,
    *,
    localize,
    console,
    print_settings_error_report,
    pause_after_tui_report,
):
    from pathlib import Path

    md_path = Path(str(selected_rescue.get("artifact_markdown") or ""))
    try:
        content = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        print_settings_error_report(localize("无法读取 rescue.md", "Cannot read rescue.md"), exc)
    else:
        try:
            console.clear()
        except Exception:
            pass
        console.print(content)
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue"}


def show_rescue_paths_action(
    selected_rescue,
    *,
    rescue_paths_report_payload,
    print_settings_result_report,
    pause_after_tui_report,
):
    print_settings_result_report(*rescue_paths_report_payload(selected_rescue))
    pause_after_tui_report("按 Enter 返回设置")
    return {"status": "continue"}


def create_rescue_handover_action(
    selected_rescue,
    fallback_model,
    *,
    write_fallback_handover,
    rescue_handover_report_payload,
    localize,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
):
    try:
        handover = write_fallback_handover(
            selected_rescue,
            fallback_model=fallback_model,
        )
    except Exception as exc:
        print_settings_error_report(
            localize("生成 fallback handover 失败", "Create fallback handover failed"),
            exc,
        )
        result = {"status": "continue", "handover": None, "error": exc}
    else:
        print_settings_result_report(*rescue_handover_report_payload(handover, fallback_model))
        result = {"status": "continue", "handover": handover, "error": None}
    pause_after_tui_report("按 Enter 返回设置")
    return result


def rescue_packet_action_menu_context(
    cfg,
    selected_rescue,
    default_label,
    *,
    rescue_fallback_model_candidates,
    rescue_route_fallback_model_candidates,
):
    info_lines = [
        ("时间", selected_rescue.get("created_at") or "-"),
        ("模型", selected_rescue.get("failed_model") or "-"),
        ("Provider", selected_rescue.get("failed_provider_id") or "-"),
        ("状态", selected_rescue.get("status_code") or selected_rescue.get("failure_kind") or "-"),
        ("原因", selected_rescue.get("failure_kind") or "-"),
        ("Repo", selected_rescue.get("repo_path") or "-"),
        ("全局默认", default_label),
    ]
    fallback_candidates = rescue_fallback_model_candidates(cfg, selected_rescue, limit=8)
    route_fallback_candidates = rescue_route_fallback_model_candidates(
        failed_model=selected_rescue.get("failed_model") or "",
        limit=120,
    )
    fallback_actions = [
        (f"handover::{model}", f"生成 fallback handover -> {model}")
        for model in fallback_candidates
    ]
    default_actions = [
        (f"default::{model}", f"设为全局默认 fallback -> {model}")
        for model in fallback_candidates
    ]
    return {
        "info_lines": info_lines,
        "fallback_candidates": fallback_candidates,
        "route_fallback_candidates": route_fallback_candidates,
        "actions": fallback_actions + default_actions + [
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


def select_rescue_route_fallback_model(
    route_fallback_candidates,
    title,
    *,
    select_model_tui,
):
    return safe_tui_call(
        select_model_tui,
        route_fallback_candidates,
        title=title,
    )


def resolve_rescue_action_fallback_model(
    action,
    *,
    prefix,
    prompt_label,
    prompt_default="",
    ensure_rich,
    prompt_cls,
):
    action_text = str(action or "")
    fallback_model = action_text.split("::", 1)[1] if action_text.startswith(prefix) else ""
    if not fallback_model:
        ensure_rich()
        fallback_model = prompt_cls.ask(prompt_label, default=prompt_default).strip()
    return fallback_model


def apply_rescue_default_from_action(
    cfg,
    action,
    default_fallback,
    *,
    apply_rescue_default_action,
    ensure_rich,
    prompt_cls,
):
    fallback_model = resolve_rescue_action_fallback_model(
        action,
        prefix="default::",
        prompt_label="全局默认 fallback model",
        prompt_default=default_fallback.get("model") or "",
        ensure_rich=ensure_rich,
        prompt_cls=prompt_cls,
    )
    if not fallback_model:
        return {"status": "continue", "cfg": cfg, "fallback_model": "", "applied": False}
    result = apply_rescue_default_action(fallback_model)
    return {
        "status": "continue",
        "cfg": result["cfg"],
        "fallback_model": fallback_model,
        "applied": True,
    }


def apply_rescue_clear_default_action(cfg, *, apply_rescue_default_action):
    result = apply_rescue_default_action("", cleared=True)
    return {"status": "continue", "cfg": result["cfg"], "cleared": True}


def handle_rescue_landing_action(
    cfg,
    landing_action,
    default_fallback,
    route_fallback_candidates,
    repo_root,
    *,
    apply_rescue_default_action,
    select_model_tui_loader,
    set_rescue_hot_fallback_enabled,
    save_config,
    rescue_hot_fallback_toggle_report_payload,
    write_demo_rescue_packet,
    rescue_demo_packet_report_payload,
    print_settings_result_report,
    pause_after_tui_report,
    ensure_rich,
    prompt_cls,
):
    if str(landing_action or "").startswith("default::") or landing_action == "manual_default":
        result = apply_rescue_default_from_action(
            cfg,
            landing_action,
            default_fallback,
            apply_rescue_default_action=apply_rescue_default_action,
            ensure_rich=ensure_rich,
            prompt_cls=prompt_cls,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if landing_action == "choose_route_default":
        result = apply_rescue_default_from_route_selection(
            cfg,
            route_fallback_candidates,
            "选择全局默认 fallback model",
            select_model_tui=select_model_tui_loader(),
            apply_rescue_default_action=apply_rescue_default_action,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if landing_action in {"enable_hot_fallback", "disable_hot_fallback"}:
        result = apply_rescue_hot_fallback_toggle_action(
            cfg,
            landing_action == "enable_hot_fallback",
            set_rescue_hot_fallback_enabled=set_rescue_hot_fallback_enabled,
            save_config=save_config,
            rescue_hot_fallback_toggle_report_payload=rescue_hot_fallback_toggle_report_payload,
            print_settings_result_report=print_settings_result_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if landing_action == "clear_default":
        result = apply_rescue_clear_default_action(
            cfg,
            apply_rescue_default_action=apply_rescue_default_action,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if landing_action == "create_demo":
        result = apply_rescue_demo_packet_action(
            repo_root,
            write_demo_rescue_packet=write_demo_rescue_packet,
            rescue_demo_packet_report_payload=rescue_demo_packet_report_payload,
            print_settings_result_report=print_settings_result_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": cfg, "result": result}
    if landing_action == "view_packets":
        return {"status": "view_packets", "cfg": cfg, "result": None}
    return {"status": "continue", "cfg": cfg, "result": None}


def apply_rescue_default_from_route_selection(
    cfg,
    route_fallback_candidates,
    title,
    *,
    select_model_tui,
    apply_rescue_default_action,
):
    fallback_model = select_rescue_route_fallback_model(
        route_fallback_candidates,
        title,
        select_model_tui=select_model_tui,
    )
    if not fallback_model:
        return {"status": "continue", "cfg": cfg, "fallback_model": "", "applied": False}
    result = apply_rescue_default_action(fallback_model)
    return {
        "status": "continue",
        "cfg": result["cfg"],
        "fallback_model": fallback_model,
        "applied": True,
    }


def create_rescue_handover_from_action(
    selected_rescue,
    action,
    *,
    write_fallback_handover,
    rescue_handover_report_payload,
    localize,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
    ensure_rich,
    prompt_cls,
):
    fallback_model = resolve_rescue_action_fallback_model(
        action,
        prefix="handover::",
        prompt_label="fallback model",
        prompt_default="",
        ensure_rich=ensure_rich,
        prompt_cls=prompt_cls,
    )
    if not fallback_model:
        return {"status": "continue", "handover": None, "fallback_model": "", "applied": False}
    result = create_rescue_handover_action(
        selected_rescue,
        fallback_model,
        write_fallback_handover=write_fallback_handover,
        rescue_handover_report_payload=rescue_handover_report_payload,
        localize=localize,
        print_settings_result_report=print_settings_result_report,
        print_settings_error_report=print_settings_error_report,
        pause_after_tui_report=pause_after_tui_report,
    )
    return {
        "status": "continue",
        "handover": result["handover"],
        "error": result["error"],
        "fallback_model": fallback_model,
        "applied": True,
    }


def create_rescue_handover_from_route_selection(
    selected_rescue,
    route_fallback_candidates,
    title,
    *,
    select_model_tui,
    write_fallback_handover,
    rescue_handover_report_payload,
    localize,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
):
    fallback_model = select_rescue_route_fallback_model(
        route_fallback_candidates,
        title,
        select_model_tui=select_model_tui,
    )
    if not fallback_model:
        return {"status": "continue", "handover": None, "fallback_model": "", "applied": False}
    result = create_rescue_handover_action(
        selected_rescue,
        fallback_model,
        write_fallback_handover=write_fallback_handover,
        rescue_handover_report_payload=rescue_handover_report_payload,
        localize=localize,
        print_settings_result_report=print_settings_result_report,
        print_settings_error_report=print_settings_error_report,
        pause_after_tui_report=pause_after_tui_report,
    )
    return {
        "status": "continue",
        "handover": result["handover"],
        "error": result["error"],
        "fallback_model": fallback_model,
        "applied": True,
    }


def handle_rescue_packet_action(
    cfg,
    selected_rescue,
    rescue_action,
    default_fallback,
    route_fallback_candidates,
    *,
    select_model_tui_loader,
    apply_rescue_default_action,
    write_fallback_handover,
    rescue_handover_report_payload,
    rescue_paths_report_payload,
    localize,
    console,
    print_settings_result_report,
    print_settings_error_report,
    pause_after_tui_report,
    ensure_rich,
    prompt_cls,
):
    if rescue_action == "view_md":
        result = handle_rescue_view_markdown_action(
            selected_rescue,
            localize=localize,
            console=console,
            print_settings_error_report=print_settings_error_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": cfg, "result": result}
    if rescue_action == "show_paths":
        result = show_rescue_paths_action(
            selected_rescue,
            rescue_paths_report_payload=rescue_paths_report_payload,
            print_settings_result_report=print_settings_result_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": cfg, "result": result}
    if str(rescue_action or "").startswith("handover::") or rescue_action == "manual_handover":
        result = create_rescue_handover_from_action(
            selected_rescue,
            rescue_action,
            write_fallback_handover=write_fallback_handover,
            rescue_handover_report_payload=rescue_handover_report_payload,
            localize=localize,
            print_settings_result_report=print_settings_result_report,
            print_settings_error_report=print_settings_error_report,
            pause_after_tui_report=pause_after_tui_report,
            ensure_rich=ensure_rich,
            prompt_cls=prompt_cls,
        )
        return {"status": "continue", "cfg": cfg, "result": result}
    if rescue_action == "choose_route_handover":
        result = create_rescue_handover_from_route_selection(
            selected_rescue,
            route_fallback_candidates,
            "选择 fallback handover model",
            select_model_tui=select_model_tui_loader(),
            write_fallback_handover=write_fallback_handover,
            rescue_handover_report_payload=rescue_handover_report_payload,
            localize=localize,
            print_settings_result_report=print_settings_result_report,
            print_settings_error_report=print_settings_error_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": cfg, "result": result}
    if str(rescue_action or "").startswith("default::") or rescue_action == "manual_default":
        result = apply_rescue_default_from_action(
            cfg,
            rescue_action,
            default_fallback,
            apply_rescue_default_action=apply_rescue_default_action,
            ensure_rich=ensure_rich,
            prompt_cls=prompt_cls,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if rescue_action == "choose_route_default":
        result = apply_rescue_default_from_route_selection(
            cfg,
            route_fallback_candidates,
            "选择全局默认 fallback model",
            select_model_tui=select_model_tui_loader(),
            apply_rescue_default_action=apply_rescue_default_action,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    if rescue_action == "clear_default":
        result = apply_rescue_clear_default_action(
            cfg,
            apply_rescue_default_action=apply_rescue_default_action,
        )
        return {"status": "continue", "cfg": result["cfg"], "result": result}
    return {"status": "continue", "cfg": cfg, "result": None}


def handle_tui_rescue_settings_action(
    cfg,
    repo_root,
    *,
    rescue_default_fallback,
    rescue_hot_fallback_enabled_cfg,
    rescue_route_fallback_model_candidates,
    list_rescue_events,
    latest_rescue_hot_fallback_event,
    rescue_landing_tui_payload,
    select_channel_action_tui,
    set_rescue_default_fallback,
    save_config,
    rescue_default_fallback_report_payload,
    print_settings_result_report,
    pause_after_tui_report,
    select_model_tui_loader,
    set_rescue_hot_fallback_enabled,
    rescue_hot_fallback_toggle_report_payload,
    write_demo_rescue_packet,
    rescue_demo_packet_report_payload,
    localize,
    select_rescue_event_tui,
    rescue_fallback_model_candidates,
    write_fallback_handover,
    rescue_handover_report_payload,
    rescue_paths_report_payload,
    console,
    print_settings_error_report,
    ensure_rich,
    prompt_cls,
):
    current_cfg = cfg

    def apply_rescue_default_action(fallback_model, *, cleared=False):
        return apply_rescue_default_fallback_action(
            current_cfg,
            fallback_model,
            cleared=cleared,
            set_rescue_default_fallback=set_rescue_default_fallback,
            save_config=save_config,
            rescue_default_fallback_report_payload=rescue_default_fallback_report_payload,
            rescue_hot_fallback_enabled_cfg=rescue_hot_fallback_enabled_cfg,
            print_settings_result_report=print_settings_result_report,
            pause_after_tui_report=pause_after_tui_report,
        )

    landing_context = rescue_landing_action_context(
        current_cfg,
        repo_root,
        rescue_default_fallback=rescue_default_fallback,
        rescue_hot_fallback_enabled_cfg=rescue_hot_fallback_enabled_cfg,
        rescue_route_fallback_model_candidates=rescue_route_fallback_model_candidates,
        list_rescue_events=list_rescue_events,
        latest_rescue_hot_fallback_event=latest_rescue_hot_fallback_event,
        rescue_landing_tui_payload=rescue_landing_tui_payload,
    )
    default_fallback = landing_context["default_fallback"]
    default_label = landing_context["default_label"]
    route_fallback_candidates = landing_context["route_fallback_candidates"]
    rescue_events = landing_context["rescue_events"]
    landing_result = select_rescue_menu_action(
        "Rescue / Current-session Fallback",
        landing_context["landing_info"],
        landing_context["landing_actions"],
        select_channel_action_tui=select_channel_action_tui,
    )
    if landing_result["status"] == "interrupt":
        return {"status": "interrupt", "cfg": current_cfg}
    if landing_result["status"] != "action":
        return {"status": "continue", "cfg": current_cfg}

    landing_dispatch = handle_rescue_landing_action(
        current_cfg,
        landing_result["action"],
        default_fallback,
        route_fallback_candidates,
        repo_root,
        apply_rescue_default_action=apply_rescue_default_action,
        select_model_tui_loader=select_model_tui_loader,
        set_rescue_hot_fallback_enabled=set_rescue_hot_fallback_enabled,
        save_config=save_config,
        rescue_hot_fallback_toggle_report_payload=rescue_hot_fallback_toggle_report_payload,
        write_demo_rescue_packet=write_demo_rescue_packet,
        rescue_demo_packet_report_payload=rescue_demo_packet_report_payload,
        print_settings_result_report=print_settings_result_report,
        pause_after_tui_report=pause_after_tui_report,
        ensure_rich=ensure_rich,
        prompt_cls=prompt_cls,
    )
    current_cfg = landing_dispatch["cfg"]
    if landing_dispatch["status"] != "view_packets":
        return {"status": "continue", "cfg": current_cfg}
    if not rescue_events:
        show_rescue_no_packets_report(
            localize=localize,
            print_settings_result_report=print_settings_result_report,
            pause_after_tui_report=pause_after_tui_report,
        )
        return {"status": "continue", "cfg": current_cfg}

    selected_result = select_rescue_event_action(
        rescue_events,
        select_rescue_event_tui=select_rescue_event_tui,
    )
    if selected_result["status"] == "interrupt":
        return {"status": "interrupt", "cfg": current_cfg}
    if selected_result["status"] != "selected":
        return {"status": "continue", "cfg": current_cfg}

    selected_rescue = selected_result["selected_rescue"]
    packet_menu = rescue_packet_action_menu_context(
        current_cfg,
        selected_rescue,
        default_label,
        rescue_fallback_model_candidates=rescue_fallback_model_candidates,
        rescue_route_fallback_model_candidates=rescue_route_fallback_model_candidates,
    )
    route_fallback_candidates = packet_menu["route_fallback_candidates"]
    rescue_result = select_rescue_menu_action(
        "Rescue Packet",
        packet_menu["info_lines"],
        packet_menu["actions"],
        select_channel_action_tui=select_channel_action_tui,
    )
    if rescue_result["status"] == "interrupt":
        return {"status": "interrupt", "cfg": current_cfg}
    if rescue_result["status"] != "action":
        return {"status": "continue", "cfg": current_cfg}

    packet_dispatch = handle_rescue_packet_action(
        current_cfg,
        selected_rescue,
        rescue_result["action"],
        default_fallback,
        route_fallback_candidates,
        select_model_tui_loader=select_model_tui_loader,
        apply_rescue_default_action=apply_rescue_default_action,
        write_fallback_handover=write_fallback_handover,
        rescue_handover_report_payload=rescue_handover_report_payload,
        rescue_paths_report_payload=rescue_paths_report_payload,
        localize=localize,
        console=console,
        print_settings_result_report=print_settings_result_report,
        print_settings_error_report=print_settings_error_report,
        pause_after_tui_report=pause_after_tui_report,
        ensure_rich=ensure_rich,
        prompt_cls=prompt_cls,
    )
    return {"status": packet_dispatch["status"], "cfg": packet_dispatch["cfg"]}


def ensure_cli_installed_for_launch(cli_name, *, check_cli_installed, check_and_offer_install_loader):
    if check_cli_installed(cli_name):
        return {"status": "continue"}
    check_and_offer_install = check_and_offer_install_loader()
    if not check_and_offer_install(cli_name):
        return {"status": "exit"}
    return {"status": "continue"}


def apply_opencode_profile_for_launch(runtime, cli_name, *, select_and_apply_opencode_profile):
    if cli_name != "opencode":
        return {"status": "continue", "runtime": runtime}
    runtime = select_and_apply_opencode_profile(runtime, use_tui=True)
    if runtime is None:
        return {"status": "continue", "runtime": None, "cancelled": True}
    return {"status": "continue", "runtime": runtime, "cancelled": False}


def apply_launch_runtime_preferences(
    cfg,
    runtime,
    cli_name,
    *,
    runtime_with_launch_preferences,
    runtime_with_vision_sidecar,
):
    runtime = runtime_with_launch_preferences(cfg, runtime, cli_name)
    if cli_name == "claude":
        runtime = runtime_with_vision_sidecar(cfg, runtime)
    return runtime


def confirm_agent_pack(value):
    raw = str(value or "").strip().lower()
    if raw in {"ecc", "omc", "none"}:
        return raw
    return "ecc" if bool(value) else "none"


def normalize_confirm_result(result, default_reasoning_effort, default_caveman_level="light"):
    disabled_session_surfaces = {}
    agent_pack = "none"
    nsr_enabled = False
    confirm_returned_surfaces = False
    caveman_level = normalize_caveman_level(default_caveman_level, default="light")

    if isinstance(result, tuple):
        if len(result) >= 10:
            (
                action,
                bypass,
                claude_1m_enabled,
                caveman_enabled,
                pack_value,
                thinking_enabled,
                reasoning_effort,
                disabled_session_surfaces,
                nsr_enabled,
                caveman_level,
            ) = result[:10]
            agent_pack = confirm_agent_pack(pack_value)
            caveman_level = normalize_caveman_level(caveman_level, default=default_caveman_level)
            confirm_returned_surfaces = True
        elif len(result) >= 9:
            (
                action,
                bypass,
                claude_1m_enabled,
                caveman_enabled,
                pack_value,
                thinking_enabled,
                reasoning_effort,
                disabled_session_surfaces,
                nsr_enabled,
            ) = result[:9]
            agent_pack = confirm_agent_pack(pack_value)
            confirm_returned_surfaces = True
        elif len(result) >= 8:
            (
                action,
                bypass,
                claude_1m_enabled,
                caveman_enabled,
                pack_value,
                thinking_enabled,
                reasoning_effort,
                disabled_session_surfaces,
            ) = result[:8]
            agent_pack = confirm_agent_pack(pack_value)
            confirm_returned_surfaces = True
        elif len(result) >= 7:
            action, bypass, claude_1m_enabled, caveman_enabled, ecc_enabled, thinking_enabled, reasoning_effort = result[:7]
            agent_pack = confirm_agent_pack(ecc_enabled)
        elif len(result) >= 5:
            action, bypass, claude_1m_enabled, caveman_enabled, ecc_enabled = result[:5]
            agent_pack = confirm_agent_pack(ecc_enabled)
            thinking_enabled = True
            reasoning_effort = default_reasoning_effort
        elif len(result) >= 4:
            action, bypass, claude_1m_enabled, caveman_enabled = result[:4]
            thinking_enabled = True
            reasoning_effort = default_reasoning_effort
        elif len(result) >= 3:
            action, bypass, claude_1m_enabled = result[:3]
            caveman_enabled = False
            thinking_enabled = True
            reasoning_effort = default_reasoning_effort
        else:
            action, bypass = result[:2]
            claude_1m_enabled = False
            caveman_enabled = False
            thinking_enabled = True
            reasoning_effort = default_reasoning_effort
    else:
        action, bypass, claude_1m_enabled, caveman_enabled, thinking_enabled, reasoning_effort = (
            result,
            False,
            False,
            False,
            True,
            default_reasoning_effort,
        )
        disabled_session_surfaces = {}
        nsr_enabled = False

    return {
        "action": action,
        "bypass": bypass,
        "claude_1m_enabled": claude_1m_enabled,
        "caveman_enabled": caveman_enabled,
        "agent_pack": agent_pack,
        "thinking_enabled": thinking_enabled,
        "reasoning_effort": reasoning_effort,
        "disabled_session_surfaces": disabled_session_surfaces,
        "nsr_enabled": nsr_enabled,
        "caveman_level": normalize_caveman_level(caveman_level, default=default_caveman_level),
        "confirm_returned_surfaces": confirm_returned_surfaces,
    }


def apply_confirm_runtime_preferences(
    runtime,
    cli_name,
    *,
    claude_1m_enabled,
    caveman_enabled,
    agent_pack,
    thinking_enabled,
    reasoning_effort,
    disabled_session_surfaces,
    nsr_enabled,
    has_nsr,
    confirm_returned_surfaces,
    merge_disabled_session_surfaces,
    caveman_level="light",
):
    if cli_name == "claude":
        runtime["claude_1m_mode"] = "enable" if claude_1m_enabled else "disable"
        runtime["agent_pack"] = agent_pack if agent_pack in {"ecc", "omc"} else "none"
        runtime["ecc_mode"] = "enable" if agent_pack == "ecc" else "disable"
        runtime["omc_mode"] = "enable" if agent_pack == "omc" else "disable"
    if cli_name in {"claude", "codex", "opencode", "pi", "agy"}:
        runtime["caveman_mode"] = "enable" if caveman_enabled else "disable"
        runtime["caveman_level"] = normalize_caveman_level(caveman_level, default="light")
        runtime["nsr_mode"] = "enable" if (has_nsr and nsr_enabled) else "disable"
        if confirm_returned_surfaces:
            runtime["disabled_session_surfaces"] = (
                disabled_session_surfaces if isinstance(disabled_session_surfaces, dict) else {}
            )
        else:
            runtime["disabled_session_surfaces"] = merge_disabled_session_surfaces(
                runtime.get("disabled_session_surfaces"),
                disabled_session_surfaces if isinstance(disabled_session_surfaces, dict) else {},
            )
    if cli_name in {"claude", "codex"}:
        runtime["thinking_mode"] = "enable" if thinking_enabled else "disable"
        runtime["reasoning_effort"] = str(reasoning_effort or "high").strip().lower() or "high"


def build_confirm_capability_context(
    cli_name,
    runtime,
    clean_model_info,
    *,
    confirm_context_lines,
    caveman_available_for_cli,
    nsr_available_for_cli,
    ecc_available_for_claude,
    omc_available_for_claude,
    model_info_looks_domestic,
    default_reasoning_effort_for_model_info,
    build_confirm_preview_catalog,
):
    context_lines = confirm_context_lines(cli_name, runtime)
    has_caveman = caveman_available_for_cli(cli_name)
    has_nsr = nsr_available_for_cli(cli_name)
    looks_domestic = model_info_looks_domestic(clean_model_info)
    has_ecc = (
        cli_name == "claude"
        and ecc_available_for_claude()
        and looks_domestic
    )
    has_omc = (
        cli_name == "claude"
        and omc_available_for_claude()
        and looks_domestic
    )
    default_reasoning_effort = (
        str(runtime.get("reasoning_effort", "")).strip().lower()
        or default_reasoning_effort_for_model_info(clean_model_info)
    )
    default_caveman_level = normalize_caveman_level(
        runtime.get("caveman_level") or runtime.get("caveman_mode"),
        default="light",
    )
    preview_catalog = build_confirm_preview_catalog(
        cli_name,
        runtime,
        has_caveman=has_caveman,
        has_nsr=has_nsr,
        has_ecc=has_ecc,
        has_omc=has_omc,
    )
    return {
        "context_lines": context_lines,
        "has_caveman": has_caveman,
        "has_nsr": has_nsr,
        "has_ecc": has_ecc,
        "has_omc": has_omc,
        "default_reasoning_effort": default_reasoning_effort,
        "default_caveman_level": default_caveman_level,
        "preview_catalog": preview_catalog,
    }


def confirm_tui_options(
    *,
    env_vars,
    once,
    context_lines,
    has_caveman,
    has_nsr,
    has_ecc,
    has_omc,
    runtime,
    default_reasoning_effort,
    preview_catalog,
    default_caveman_level="light",
):
    return {
        "env_vars": env_vars,
        "once": once,
        "context_lines": context_lines,
        "has_caveman": has_caveman,
        "caveman_enabled_default": normalize_caveman_mode(runtime.get("caveman_mode", "enable"), default="enable") == "enable",
        "caveman_level_default": default_caveman_level,
        "has_nsr": has_nsr,
        "nsr_enabled_default": str(runtime.get("nsr_mode", "enable")).strip().lower() == "enable",
        "has_ecc": has_ecc,
        "ecc_enabled_default": False,
        "has_omc": has_omc,
        "agent_pack_default": str(runtime.get("agent_pack") or "none"),
        "thinking_enabled_default": str(runtime.get("thinking_mode", "enable")).strip().lower() != "disable",
        "reasoning_effort_default": default_reasoning_effort,
        "preview_catalog": preview_catalog,
        "runtime": runtime,
    }


def run_confirm_tui_prompt(
    cli_name,
    clean_model_info,
    runtime,
    *,
    env_vars,
    once,
    confirm_tui,
    confirm_context_lines,
    caveman_available_for_cli,
    nsr_available_for_cli,
    ecc_available_for_claude,
    omc_available_for_claude,
    model_info_looks_domestic,
    default_reasoning_effort_for_model_info,
    build_confirm_preview_catalog,
):
    confirm_context = build_confirm_capability_context(
        cli_name,
        runtime,
        clean_model_info,
        confirm_context_lines=confirm_context_lines,
        caveman_available_for_cli=caveman_available_for_cli,
        nsr_available_for_cli=nsr_available_for_cli,
        ecc_available_for_claude=ecc_available_for_claude,
        omc_available_for_claude=omc_available_for_claude,
        model_info_looks_domestic=model_info_looks_domestic,
        default_reasoning_effort_for_model_info=default_reasoning_effort_for_model_info,
        build_confirm_preview_catalog=build_confirm_preview_catalog,
    )
    result = safe_tui_call(
        confirm_tui,
        cli_name,
        clean_model_info,
        **confirm_tui_options(
            env_vars=env_vars,
            once=once,
            context_lines=confirm_context["context_lines"],
            has_caveman=confirm_context["has_caveman"],
            has_nsr=confirm_context["has_nsr"],
            has_ecc=confirm_context["has_ecc"],
            has_omc=confirm_context["has_omc"],
            runtime=runtime,
            default_reasoning_effort=confirm_context["default_reasoning_effort"],
            default_caveman_level=confirm_context["default_caveman_level"],
            preview_catalog=confirm_context["preview_catalog"],
        ),
    )
    if result == "__interrupt__":
        return {"status": "interrupt"}
    return {
        "status": "continue",
        "confirm_result": normalize_confirm_result(
            result,
            confirm_context["default_reasoning_effort"],
            confirm_context["default_caveman_level"],
        ),
        "has_nsr": confirm_context["has_nsr"],
    }


def resolve_confirm_launch_action(confirm_result, *, has_nsr):
    action = confirm_result["action"]
    if action == "q":
        return {"status": "exit"}
    if action == "b":
        return {"status": "back"}
    return {
        "status": "launch",
        "bypass": confirm_result["bypass"],
        "runtime_preferences": {
            "claude_1m_enabled": confirm_result["claude_1m_enabled"],
            "caveman_enabled": confirm_result["caveman_enabled"],
            "caveman_level": confirm_result.get("caveman_level", "light"),
            "agent_pack": confirm_result["agent_pack"],
            "thinking_enabled": confirm_result["thinking_enabled"],
            "reasoning_effort": confirm_result["reasoning_effort"],
            "disabled_session_surfaces": confirm_result["disabled_session_surfaces"],
            "nsr_enabled": confirm_result["nsr_enabled"],
            "has_nsr": has_nsr,
            "confirm_returned_surfaces": confirm_result["confirm_returned_surfaces"],
        },
    }


def apply_confirm_bypass_flag(runtime, cli_name, bypass):
    if cli_name in {"claude", "codex", "opencode", "pi", "agy"}:
        runtime["bypass"] = bool(bypass)


def apply_claude_network_guard_preview(runtime, cli_name, *, network_guard_preview_loader):
    if not (
        cli_name == "claude"
        and runtime
        and runtime.get("auth_mode") in {"oauth", "api_key"}
    ):
        return runtime
    try:
        get_claude_network_guard_preview, claude_bypass_requires_proxy = network_guard_preview_loader()
        runtime["_network_guard"] = get_claude_network_guard_preview(
            runtime,
            require_proxy=bool(runtime.get("bypass")) and claude_bypass_requires_proxy(runtime),
        )
    except Exception:
        runtime["_network_guard"] = {
            "status": "unknown",
            "dns_mode": "unknown",
            "ipv4_egress": "-",
            "ipv6_egress": "-",
            "targets": [],
            "no_proxy_conflicts": [],
        }
    return runtime


def prepare_confirm_prompt_inputs(
    cli_name,
    model_info,
    runtime,
    *,
    clean_model_info,
    get_export_env,
    network_guard_preview_loader,
):
    clean = clean_model_info(model_info)
    try:
        env_vars = get_export_env(cli_name, runtime, model_info=clean)
    except TypeError as exc:
        if "model_info" not in str(exc):
            raise
        env_vars = get_export_env(cli_name, runtime)
    runtime = apply_claude_network_guard_preview(
        runtime,
        cli_name,
        network_guard_preview_loader=network_guard_preview_loader,
    )
    return {"clean_model_info": clean, "env_vars": env_vars, "runtime": runtime}


def enforce_confirm_bypass_network_guard(runtime, cli_name, bypass, *, network_guard_enforcer_loader):
    if not (
        bypass
        and cli_name == "claude"
        and runtime
        and runtime.get("auth_mode") in {"oauth", "api_key"}
    ):
        return {"status": "continue"}
    enforce_claude_network_guard_or_exit, claude_bypass_requires_proxy = network_guard_enforcer_loader()
    enforce_claude_network_guard_or_exit(
        runtime,
        require_proxy=claude_bypass_requires_proxy(runtime),
    )
    return {"status": "continue"}


def execute_confirmed_launch(
    cli_name,
    clean_model_info,
    runtime,
    *,
    bypass,
    runtime_preferences,
    once,
    network_guard_enforcer_loader,
    merge_disabled_session_surfaces,
    launch_with_tracking,
):
    apply_confirm_bypass_flag(runtime, cli_name, bypass)
    enforce_confirm_bypass_network_guard(
        runtime,
        cli_name,
        bypass,
        network_guard_enforcer_loader=network_guard_enforcer_loader,
    )
    apply_confirm_runtime_preferences(
        runtime,
        cli_name,
        **runtime_preferences,
        merge_disabled_session_surfaces=merge_disabled_session_surfaces,
    )
    launch_with_tracking(cli_name, clean_model_info, runtime, once=once)
    return {"status": "launched"}


def handle_tui_launch_confirmation(
    cfg,
    cli_name,
    model_info,
    runtime,
    *,
    deps,
):
    install_result = ensure_cli_installed_for_launch(
        cli_name,
        check_cli_installed=deps.check_cli_installed,
        check_and_offer_install_loader=deps.check_and_offer_install_loader,
    )
    if install_result["status"] == "exit":
        return {"status": "exit"}

    opencode_profile_result = apply_opencode_profile_for_launch(
        runtime,
        cli_name,
        select_and_apply_opencode_profile=deps.select_and_apply_opencode_profile,
    )
    if opencode_profile_result.get("cancelled"):
        return {"status": "continue"}
    runtime = opencode_profile_result["runtime"]
    runtime = apply_launch_runtime_preferences(
        cfg,
        runtime,
        cli_name,
        runtime_with_launch_preferences=deps.runtime_with_launch_preferences,
        runtime_with_vision_sidecar=deps.runtime_with_vision_sidecar,
    )

    confirm_inputs = prepare_confirm_prompt_inputs(
        cli_name,
        model_info,
        runtime,
        clean_model_info=deps.clean_model_info,
        get_export_env=deps.get_export_env,
        network_guard_preview_loader=deps.network_guard_preview_loader,
    )
    clean = confirm_inputs["clean_model_info"]
    env_vars = confirm_inputs["env_vars"]
    runtime = confirm_inputs["runtime"]

    confirm_prompt = run_confirm_tui_prompt(
        cli_name,
        clean,
        runtime,
        env_vars=env_vars,
        once=deps.once,
        confirm_tui=deps.confirm_tui,
        confirm_context_lines=deps.confirm_context_lines,
        caveman_available_for_cli=deps.caveman_available_for_cli,
        nsr_available_for_cli=deps.nsr_available_for_cli,
        ecc_available_for_claude=deps.ecc_available_for_claude,
        omc_available_for_claude=deps.omc_available_for_claude,
        model_info_looks_domestic=deps.model_info_looks_domestic,
        default_reasoning_effort_for_model_info=deps.default_reasoning_effort_for_model_info,
        build_confirm_preview_catalog=deps.build_confirm_preview_catalog,
    )
    if confirm_prompt["status"] == "interrupt":
        return {"status": "exit"}

    confirm_action = resolve_confirm_launch_action(
        confirm_prompt["confirm_result"],
        has_nsr=confirm_prompt["has_nsr"],
    )
    if confirm_action["status"] == "exit":
        return {"status": "exit"}
    if confirm_action["status"] == "back":
        return {"status": "continue"}

    execute_confirmed_launch(
        cli_name,
        clean,
        runtime,
        bypass=confirm_action["bypass"],
        runtime_preferences=confirm_action["runtime_preferences"],
        once=deps.once,
        network_guard_enforcer_loader=deps.network_guard_enforcer_loader,
        merge_disabled_session_surfaces=deps.merge_disabled_session_surfaces,
        launch_with_tracking=deps.launch_with_tracking,
    )
    return {"status": "exit"}
