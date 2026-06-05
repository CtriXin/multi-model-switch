"""Runtime source selection helpers for command flows."""

from __future__ import annotations

from mms_commands.launch_selection import resolve_model_name


def resolve_best_provider(
    cfg,
    model_name,
    default_provider,
    default_models,
    *,
    cli_name=None,
    protocol=None,
    provider_candidates,
    provider_supports_model_for_cli,
    provider_has_configured_base_url,
    provider_effective_models,
    normalize_role,
    runtime_priority_for_model,
    provider_label,
    runtime_with_priority,
    role_weights,
):
    model_lower = str(model_name or "").strip().lower()
    if not model_lower:
        return None, None

    scored = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        if not provider.get("enabled", True):
            continue
        if cli_name and not provider_supports_model_for_cli(provider, cli_name, model_name):
            continue
        if not provider_has_configured_base_url(provider):
            continue
        if not provider.get("api_key"):
            continue
        if protocol:
            protocols = provider.get("protocols", [])
            if protocol not in protocols:
                continue

        models = provider_effective_models(provider, cached_models, cfg)
        model_names_lower = [str(item or "").strip().lower() for item in models]
        if model_lower not in model_names_lower:
            continue

        role = normalize_role(provider.get("role", "auto"))
        priority = runtime_priority_for_model(provider, model_name)
        scored.append((role_weights.get(role, 1), -priority, provider, provider_label(provider)))

    if not scored:
        return None, None

    scored.sort(key=lambda item: (item[0], item[1]))
    return runtime_with_priority(scored[0][2], model_name=model_name), scored[0][3]


def provider_options_for_model(
    cfg,
    cli_name,
    default_provider,
    default_models,
    model_info=None,
    *,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    probe_debug_logger,
    provider_candidates,
    provider_has_configured_base_url,
    provider_effective_models,
    provider_models_for_cli,
    provider_supports_model_for_cli,
    provider_supports_cli_name,
    runtime_with_priority,
    runtime_choice_label,
    provider_label,
    runtime_priority_for_family,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    probe_debug_logger.info("=== _provider_options_for_model(cli=%s, selected_model=%s) ===", cli_name, selected_model)
    options = []
    for provider, cached_models in provider_candidates(cfg, default_provider, default_models):
        provider_id = provider.get("id", "?")
        if not provider.get("enabled", True):
            probe_debug_logger.debug("  %s: SKIP (disabled)", provider_id)
            continue
        if not provider_has_configured_base_url(provider) or not provider.get("api_key"):
            probe_debug_logger.debug(
                "  %s: SKIP (no configured base_url=%s or api_key=%s)",
                provider_id,
                provider_has_configured_base_url(provider),
                bool(provider.get("api_key")),
            )
            continue

        models = cached_models
        if models is None:
            probe_debug_logger.debug("  %s: cached_models=None, schedule async refresh", provider_id)
            models = provider_effective_models(provider, None, cfg)
        else:
            probe_debug_logger.debug("  %s: cached_models=%s (len=%d)", provider_id, type(cached_models).__name__, len(cached_models))
        models = provider_effective_models(provider, models, cfg)
        try:
            cli_models = provider_models_for_cli(cli_name, models, provider=provider)
        except TypeError as exc:
            if "provider" not in str(exc):
                raise
            cli_models = provider_models_for_cli(cli_name, models)

        if selected_model:
            if not provider_supports_model_for_cli(provider, cli_name, selected_model):
                probe_debug_logger.info("  %s: SKIP (cli/model incompatible for %s -> %s)", provider_id, cli_name, selected_model)
                continue
            if selected_model not in models:
                probe_debug_logger.info("  %s: SKIP (model '%s' not in %s)", provider_id, selected_model, models[:5])
                continue
            option_models = [selected_model]
        else:
            if not provider_supports_cli_name(provider, cli_name):
                probe_debug_logger.debug("  %s: SKIP (cli not supported)", provider_id)
                continue
            option_models = cli_models

        if not option_models:
            probe_debug_logger.info("  %s: SKIP (no option models for cli=%s)", provider_id, cli_name)
            continue

        probe_debug_logger.info("  %s: ADDED (option_models=%s)", provider_id, option_models)
        options.append({
            "kind": "provider",
            "id": provider.get("id"),
            "runtime": runtime_with_priority(provider, model_name=selected_model, family_name=selected_family),
            "models": option_models,
            "label": runtime_choice_label(provider),
            "title": provider_label(provider),
            "desc": "网关",
            "icon": "🌐",
            "priority": (
                runtime_priority_for_family(provider, selected_family)
                if selected_family
                else provider.get("priority", default_priority)
            ),
            "priority_family": selected_family,
            "is_default": provider.get("id") == default_provider.get("id"),
            "launch_cli": cli_name,
        })
    return options


def account_options_for_model(
    cfg,
    cli_name,
    default_models,
    model_info=None,
    *,
    allow_selected_model=False,
    resolve_model_name=resolve_model_name,
    infer_model_family,
    oauth_capable_clis,
    model_matches_account_cli,
    resolve_account_context,
    runtime_with_priority,
    runtime_choice_label,
    account_label,
    default_priority,
):
    selected_model = resolve_model_name(model_info) if model_info else ""
    selected_family, _ = infer_model_family(selected_model) if selected_model else ("", "")
    options = []
    defaults = cfg.get("account", {}).get("defaults", {})

    for account_def in cfg.get("accounts", []):
        if not isinstance(account_def, dict) or not account_def.get("enabled", True):
            continue
        account_cli = account_def.get("cli")
        if account_cli not in oauth_capable_clis:
            continue
        bridgeable_to_claude = False
        if account_cli != cli_name and not bridgeable_to_claude:
            continue
        if selected_model and not allow_selected_model and not bridgeable_to_claude:
            continue
        if selected_model and not model_matches_account_cli(account_cli, selected_model):
            continue
        runtime = resolve_account_context(cfg, account_id=account_def["id"], cli_name=account_cli)
        launch_cli = account_cli
        desc = "官方"
        if bridgeable_to_claude:
            bridged = dict(runtime)
            bridged["auth_mode"] = "oauth_bridge"
            bridged["bridge_source_cli"] = account_cli
            bridged["bridge_target_cli"] = "claude"
            bridged["bridge_model"] = selected_model
            bridged["bridge_account_id"] = runtime.get("id")
            runtime = bridged
            launch_cli = "claude"
            desc = "官方桥接"
        runtime = runtime_with_priority(runtime, model_name=selected_model, family_name=selected_family)
        options.append({
            "kind": "account",
            "id": runtime.get("id"),
            "runtime": runtime,
            "models": [selected_model] if selected_model else list(default_models or []),
            "label": runtime_choice_label(runtime),
            "title": account_label(runtime),
            "desc": desc,
            "icon": "🔑",
            "priority": runtime.get("priority", default_priority),
            "priority_family": selected_family,
            "is_default": runtime.get("id") == defaults.get(account_cli),
            "launch_cli": launch_cli,
        })
    return options


def resolve_provider_for_cli(cfg, cli_name, default_provider, default_models, *, provider_options_for_model, cli_model_family_hints):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models)
    for option in options:
        runtime = option["runtime"]
        models = option["models"]
        if cli_name not in cli_model_family_hints:
            return runtime, models
        if models:
            return runtime, models
    return None, []


def resolve_launch_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    account_id=None,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
    managed_oauth_clis,
    resolve_account_context,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    if cli_name in managed_oauth_clis:
        account = resolve_account_context(cfg, account_id=account_id, cli_name=cli_name)
        if account_id and account is not None:
            return account, list(default_models or [])
        if account is not None and account.get("enabled", True):
            return account, list(default_models or [])
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_provider_runtime(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    provider_id=None,
    resolve_provider_context,
    resolve_provider_for_cli,
    probe_models,
):
    if provider_id:
        provider = resolve_provider_context(cfg, provider_id)
        return resolve_provider_for_cli(cfg, cli_name, provider, probe_models(provider, emit_output=False).get("models"))
    return resolve_provider_for_cli(cfg, cli_name, default_provider, default_models)


def resolve_source_default_index(options, preferred_cli):
    if not options:
        return 0
    for idx, option in enumerate(options):
        if option.get("kind") == "provider" and option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli and option.get("is_default"):
            return idx
    for idx, option in enumerate(options):
        if option.get("launch_cli") == preferred_cli:
            return idx
    for idx, option in enumerate(options):
        if option.get("is_default"):
            return idx
    return 0


def runtime_choice_label(runtime, *, account_label, provider_label):
    if runtime.get("auth_mode") == "broker_profile":
        return f"Broker / {runtime.get('name', runtime.get('id', 'broker'))}"
    if runtime.get("auth_mode") == "oauth_bridge":
        return f"官方桥接 / {account_label(runtime)}"
    if runtime.get("auth_mode") == "oauth":
        return f"官方 / {account_label(runtime)}"
    return f"网关 / {provider_label(runtime)}"


def list_runtime_sources(
    cfg,
    cli_name,
    default_provider,
    default_models,
    *,
    model_info=None,
    allow_selected_model_accounts=False,
    provider_options_for_model,
    account_options_for_model,
    broker_options_for_cli,
    resolve_source_default_index=resolve_source_default_index,
    default_priority,
):
    options = provider_options_for_model(cfg, cli_name, default_provider, default_models, model_info=model_info)
    options.extend(
        account_options_for_model(
            cfg,
            cli_name,
            default_models,
            model_info=model_info,
            allow_selected_model=allow_selected_model_accounts,
        )
    )
    options.extend(broker_options_for_cli(cfg, cli_name, model_info=model_info))
    options.sort(key=lambda item: (
        -int(item.get("priority", default_priority) or default_priority),
        0 if item.get("launch_cli") == cli_name else 1,
        0 if item["kind"] == "provider" else 1 if item["kind"] == "account" else 2,
        item.get("title", ""),
    ))
    default_choice = resolve_source_default_index(options, cli_name)
    return options, default_choice


def choose_runtime_source(
    cfg,
    cli_name,
    default_provider,
    default_models,
    account_id=None,
    provider_id=None,
    model_info=None,
    allow_selected_model_accounts=False,
    *,
    managed_oauth_clis,
    runtime_with_launch_preferences,
    resolve_launch_runtime,
    trace_runtime_choice,
    list_runtime_sources,
    stdin_isatty,
    ensure_rich,
    table_cls,
    prompt_ask,
    runtime_source_kind_label,
    console,
):
    def with_preferences(runtime, launch_cli):
        return runtime_with_launch_preferences(cfg, runtime, launch_cli)

    if account_id or provider_id or cli_name not in managed_oauth_clis:
        runtime, models = resolve_launch_runtime(
            cfg,
            cli_name,
            default_provider,
            default_models,
            account_id=account_id,
            provider_id=provider_id,
        )
        choice = "single runtime path"
        if provider_id:
            choice = "provider override"
        elif account_id:
            choice = "account override"
        runtime = with_preferences(runtime, cli_name)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=cli_name, choice=choice)
        return runtime, models, cli_name

    options, default_choice = list_runtime_sources(
        cfg,
        cli_name,
        default_provider,
        default_models,
        model_info=model_info,
        allow_selected_model_accounts=allow_selected_model_accounts,
    )

    if not options:
        return None, [], cli_name
    if len(options) == 1:
        chosen = options[0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = with_preferences(chosen["runtime"], launch_cli)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="single option")
        return runtime, chosen["models"], launch_cli

    if not stdin_isatty():
        chosen = options[default_choice or 0]
        launch_cli = chosen.get("launch_cli", cli_name)
        runtime = with_preferences(chosen["runtime"], launch_cli)
        trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice="default(no-tty)")
        return runtime, chosen["models"], launch_cli

    ensure_rich()
    table = table_cls(title=f"{cli_name} 使用入口", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("来源", style="green")
    table.add_column("名称", style="yellow")
    table.add_column("调用", style="cyan")
    table.add_column("说明", style="magenta")
    for idx, option in enumerate(options, 1):
        runtime = option["runtime"]
        source_type = runtime_source_kind_label(runtime)
        desc = option.get("desc", "")
        if idx - 1 == default_choice:
            desc = f"{desc} / 默认"
        table.add_row(
            str(idx),
            source_type,
            runtime.get("name", runtime.get("id", "")),
            option.get("launch_cli", cli_name),
            desc,
        )
    console.print(table)

    default_num = str((default_choice or 0) + 1)
    while True:
        raw = prompt_ask(f"为 {cli_name} 选择这次使用的入口", default=default_num)
        if raw.isdigit():
            selected = int(raw)
            if 1 <= selected <= len(options):
                chosen = options[selected - 1]
                launch_cli = chosen.get("launch_cli", cli_name)
                runtime = with_preferences(chosen["runtime"], launch_cli)
                trace_runtime_choice("runtime resolve", runtime, launch_cli=launch_cli, choice=chosen.get("title"))
                return runtime, chosen["models"], launch_cli
        console.print(f"[red]请输入 1-{len(options)} 的编号[/red]")
