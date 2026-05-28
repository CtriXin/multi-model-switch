"""Helpers for MMS TUI launcher flow."""

from __future__ import annotations


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
    build_model_families_for_cli,
    cli_default_family_first,
    family_is_cold_for_tui,
    sort_family_entries_for_tui,
    make_provider_options_loader,
):
    families_by_cli = {}
    families_detail = {}
    provider_options_by_cli = {}
    provider_options_loader_by_cli = {}
    for cli_name in cli_names:
        raw = build_model_families_for_cli(
            cfg, cli_name, current_provider, default_models
        )
        family_entries = []
        preferred_family = cli_default_family_first.get(cli_name)
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
                "is_cold": family_is_cold_for_tui(
                    family["family"],
                    total_use,
                    family_last_used_at,
                    preferred_family=preferred_family,
                ),
            })
        families_by_cli[cli_name] = sort_family_entries_for_tui(
            family_entries,
            preferred_family=preferred_family,
        )
        families_detail[cli_name] = {family["family"]: family["models"] for family in raw}
        provider_options_by_cli[cli_name] = {}
        provider_options_loader_by_cli[cli_name] = make_provider_options_loader(
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


def refresh_tui_runtime_state_after_config_change(
    cfg,
    *,
    probe_cache,
    probe_file_cache_dir,
    rmtree,
    ensure_provider_credentials,
    probe_models,
    resolve_visible_clis,
):
    probe_cache.clear()
    rmtree(probe_file_cache_dir, ignore_errors=True)
    current_provider = ensure_provider_credentials(cfg)
    default_models = probe_models(current_provider, emit_output=False).get("models")
    current_cli_names = resolve_visible_clis(cfg, current_provider, default_models)
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


def confirm_agent_pack(value):
    raw = str(value or "").strip().lower()
    if raw in {"ecc", "omc", "none"}:
        return raw
    return "ecc" if bool(value) else "none"


def normalize_confirm_result(result, default_reasoning_effort):
    disabled_session_surfaces = {}
    agent_pack = "none"
    nsr_enabled = False
    confirm_returned_surfaces = False

    if isinstance(result, tuple):
        if len(result) >= 9:
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
):
    if cli_name == "claude":
        runtime["claude_1m_mode"] = "enable" if claude_1m_enabled else "disable"
        runtime["agent_pack"] = agent_pack if agent_pack in {"ecc", "omc"} else "none"
        runtime["ecc_mode"] = "enable" if agent_pack == "ecc" else "disable"
        runtime["omc_mode"] = "enable" if agent_pack == "omc" else "disable"
    if cli_name in {"claude", "codex", "opencode", "agy"}:
        runtime["caveman_mode"] = "enable" if caveman_enabled else "disable"
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
):
    return {
        "env_vars": env_vars,
        "once": once,
        "context_lines": context_lines,
        "has_caveman": has_caveman,
        "caveman_enabled_default": str(runtime.get("caveman_mode", "enable")).strip().lower() != "disable",
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


def apply_confirm_bypass_flag(runtime, cli_name, bypass):
    if cli_name in {"claude", "codex", "opencode", "agy"}:
        runtime["bypass"] = bool(bypass)
