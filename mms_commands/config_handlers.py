"""Config/provider/account command handlers with dependencies injected by core."""

from __future__ import annotations

import os
import sys


def mask_key(value):
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def set_nested(target, parts, value):
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]
    target[parts[-1]] = value


def get_nested(target, parts):
    current = target
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def unset_nested(target, parts):
    current = target
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return False
    current.pop(parts[-1], None)
    return True


def normalize_model_id_list(values):
    if isinstance(values, str):
        values = [chunk.strip() for chunk in values.split(",")]
    normalized = []
    seen = set()
    for item in values or []:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return normalized


def normalize_models_endpoint(value):
    endpoint = str(value or "").strip()
    if not endpoint:
        return "/models"
    if endpoint.lower() in {"manual", "none", "off"}:
        return "manual"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    return endpoint


def handle_config_get(cfg, args_rest, *, command_name, console):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config get <dot.path>[/red]")
        return
    key_path = args_rest[0]
    value, found = get_nested(cfg, key_path.split("."))
    if not found:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    display = mask_key(str(value)) if "key" in key_path.lower() else str(value)
    console.print(f"[cyan]{key_path}[/cyan] = {display}")


def handle_config_set(
    cfg,
    args_rest,
    *,
    command_name,
    coerce_config_value,
    normalize_config_sections,
    save_config,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config set <dot.path> <value>[/red]")
        return
    key_path = args_rest[0]
    raw_value = args_rest[1]
    new_value = coerce_config_value(key_path, raw_value)
    updated_cfg = dict(cfg)
    set_nested(updated_cfg, key_path.split("."), new_value)
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    display = mask_key(str(new_value)) if "key" in key_path.lower() else str(new_value)
    console.print(f"[green]✓ {key_path} = {display}[/green]")


def handle_config_unset(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_config_sections,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config unset <dot.path>[/red]")
        return
    key_path = args_rest[0]
    updated_cfg = dict(cfg)
    removed = unset_nested(updated_cfg, key_path.split("."))
    if not removed:
        console.print(f"[red]配置项 '{key_path}' 不存在[/red]")
        return
    updated_cfg = normalize_config_sections(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已移除 {key_path}[/green]")


def handle_config_validate(cfg, *, validate_config, console):
    errors = validate_config(cfg)
    if errors:
        console.print("[red]配置校验失败:[/red]")
        for item in errors:
            console.print(f"  - {item}")
        sys.exit(1)
    console.print("[green]✓ 配置校验通过[/green]")


def handle_config(
    cfg,
    args_rest,
    *,
    preferences_doc_path,
    preference_paths,
    display_config,
    display_config_help,
    handle_config_migrate,
    handle_config_file,
    handle_config_validate,
    display_preferences_help,
    display_preferences_path,
    display_preferences_example,
    run_config_web,
    command_name,
    config_write_target_path,
    display_human_gate_help,
    handle_config_get,
    handle_config_set,
    handle_config_unset,
    run_connect_wizard,
    handle_openrouter_extension_config,
    display_adapter_registry,
    display_providers,
    handle_provider_default_config,
    handle_provider_add_config,
    handle_provider_edit_config,
    handle_provider_rename_config,
    handle_provider_remove_config,
    handle_provider_credentials_config,
    display_accounts,
    handle_account_default_config,
    handle_account_add_config,
    handle_account_edit_config,
    handle_account_remove_config,
    handle_account_rename_config,
    handle_account_status_config,
    handle_account_login_config,
    display_usage_stats,
    resolve_provider_context,
    setup_provider_credentials,
    handle_api_config,
    console,
):
    if not args_rest:
        display_config(cfg)
        return

    key_path = args_rest[0]
    if key_path in {"-h", "--help", "help"}:
        display_config_help()
        return
    if key_path == "migrate":
        handle_config_migrate()
        return
    if key_path == "file":
        handle_config_file()
        return
    if key_path == "validate":
        handle_config_validate(cfg)
        return
    if key_path in {"preferences", "preferences.help", "preference.help"}:
        display_preferences_help()
        return
    if key_path in {"preferences.path", "preference.path"}:
        display_preferences_path()
        return
    if key_path in {"preferences.example", "preference.example"}:
        display_preferences_example()
        return
    if key_path in {"preferences.doc", "preference.doc"}:
        console.print(preferences_doc_path)
        return
    if key_path in {"web", "webui", "setup.web", "setup-web"}:
        raise SystemExit(run_config_web(
            cfg,
            args_rest[1:],
            command_name=command_name,
            config_path=config_write_target_path(),
            preferences_path=preference_paths[0],
        ))
    if key_path in {"gates", "human-gate", "humangate", "human-gates"}:
        display_human_gate_help()
        return
    if key_path == "get":
        handle_config_get(cfg, args_rest[1:])
        return
    if key_path == "set":
        handle_config_set(cfg, args_rest[1:])
        return
    if key_path == "unset":
        handle_config_unset(cfg, args_rest[1:])
        return
    if key_path == "connect":
        run_connect_wizard(cfg)
        return
    if key_path in {"extension.openrouter", "openrouter"}:
        handle_openrouter_extension_config(cfg, args_rest[1:])
        return
    if key_path in {"adapter.registry", "source.registry", "source.top10"}:
        display_adapter_registry()
        return
    if key_path == "provider.list":
        display_providers(cfg)
        return
    if key_path == "provider.default":
        handle_provider_default_config(cfg, args_rest[1:])
        return
    if key_path == "provider.add":
        handle_provider_add_config(cfg, args_rest[1:])
        return
    if key_path == "provider.edit":
        handle_provider_edit_config(cfg, args_rest[1:])
        return
    if key_path == "provider.rename":
        handle_provider_rename_config(cfg, args_rest[1:])
        return
    if key_path == "provider.remove":
        handle_provider_remove_config(cfg, args_rest[1:])
        return
    if key_path == "provider.credentials":
        handle_provider_credentials_config(cfg, args_rest[1:])
        return
    if key_path == "account.list":
        display_accounts(cfg)
        return
    if key_path == "account.default":
        handle_account_default_config(cfg, args_rest[1:])
        return
    if key_path == "account.add":
        handle_account_add_config(cfg, args_rest[1:])
        return
    if key_path == "account.edit":
        handle_account_edit_config(cfg, args_rest[1:])
        return
    if key_path == "account.remove":
        handle_account_remove_config(cfg, args_rest[1:])
        return
    if key_path == "account.rename":
        handle_account_rename_config(cfg, args_rest[1:])
        return
    if key_path == "account.status":
        handle_account_status_config(cfg, args_rest[1:])
        return
    if key_path == "account.login":
        handle_account_login_config(cfg, args_rest[1:])
        return
    if key_path in {"usage", "stats"}:
        display_usage_stats()
        return
    if key_path in ("api.setup", "api.edit"):
        provider = resolve_provider_context(cfg)
        setup_provider_credentials(
            provider,
            provider.get("base_url", ""),
            provider.get("api_key", ""),
            allow_keep=True,
        )
        return

    if key_path.startswith("api."):
        handle_api_config(key_path, args_rest[1:])
        return

    if len(args_rest) == 1:
        handle_config_get(cfg, [key_path])
        return
    if len(args_rest) == 2:
        handle_config_set(cfg, [key_path, args_rest[1]])
        return


def handle_config_file(*, config_path, console):
    console.print(config_path)


def handle_api_config(
    key_path,
    args_rest,
    *,
    load_api_credentials,
    save_api_credentials,
    credentials_path,
    mask_key,
    console,
):
    base_url, api_key, _ = load_api_credentials()

    if key_path == "api.base_url":
        if not args_rest:
            display = base_url or "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            return
        save_api_credentials(args_rest[0].rstrip("/"), api_key)
        console.print(f"[green]✓ {key_path} = {args_rest[0].rstrip('/')}[/green]")
        return

    if key_path == "api.api_key":
        if not args_rest:
            display = mask_key(api_key) if api_key else "(未设置)"
            console.print(f"[cyan]{key_path}[/cyan] = {display}")
            console.print(f"[dim]真实值保存在 {credentials_path}，这里始终只显示掩码。[/dim]")
            return
        save_api_credentials(base_url, args_rest[0])
        console.print(f"[green]✓ {key_path} = {mask_key(args_rest[0])}[/green]")
        console.print(f"[dim]真实值已保存到 {credentials_path}，这里显示为掩码。[/dim]")
        return

    console.print(f"[red]配置项 '{key_path}' 不存在[/red]")


def handle_config_migrate(
    *,
    backup_config_tree,
    load_config,
    migrate_accounts_dirs,
    save_config,
    config_path,
    active_credentials_path,
    active_usage_path,
    console,
):
    backup_dir = backup_config_tree("config-migrate")
    cfg = load_config()
    if cfg is None:
        console.print("[yellow]未找到可迁移配置，当前无需执行 migrate[/yellow]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts, moved_accounts = migrate_accounts_dirs(cfg)
    if moved_accounts:
        updated_cfg["accounts"] = updated_accounts
    save_config(updated_cfg)

    console.print("[green]✓ 配置迁移完成[/green]")
    console.print(f"[dim]config: {config_path}[/dim]")
    console.print(f"[dim]credentials: {active_credentials_path()}[/dim]")
    console.print(f"[dim]usage: {active_usage_path()}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def handle_provider_default_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    save_config,
    refresh_routes_export_for_hive,
    console,
):
    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    if not args_rest:
        console.print(f"[cyan]provider.default[/cyan] = {default_id}")
        console.print("[dim]当前默认模型源[/dim]")
        return

    requested_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if requested_id not in providers:
        console.print(f"[red]未找到 provider: {requested_id}[/red]")
        console.print(f"[dim]可用 provider: {', '.join(providers.keys())}[/dim]")
        return

    cfg.setdefault("provider", {})
    cfg["provider"]["default"] = requested_id
    save_config(cfg)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ provider.default = {requested_id}[/green]")
    console.print("[dim]默认模型源已更新[/dim]")


def handle_provider_add_config(
    cfg,
    args_rest,
    *,
    quick_connect_gateway,
):
    preset_id = args_rest[0].strip() if args_rest else None
    quick_connect_gateway(cfg, preset_id=preset_id)


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
    updated_cfg = dict(cfg)
    providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != provider_id:
            providers.append(item)
            continue
        updated = dict(item)
        if extra_models is not None:
            updated["extra_models"] = normalize_model_id_list(extra_models)
        if hidden_models is not None:
            updated["hidden_models"] = normalize_model_id_list(hidden_models)
        if models_endpoint is not None:
            updated["models_endpoint"] = normalize_models_endpoint(models_endpoint)
        providers.append(normalize_provider(updated))
    updated_cfg["providers"] = providers
    save_config(updated_cfg)
    invalidate_probe_cache(provider_id)
    return load_config()


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
    ensure_rich()
    changed = False
    current_cfg = cfg
    while True:
        provider = resolve_provider_context(current_cfg, provider_id)
        probe = probe_models(provider, emit_output=False)
        model_count = len(probe.get("models") or [])
        extra_count = len(provider.get("extra_models", []) or [])
        hidden_count = len(provider.get("hidden_models", []) or [])

        info_lines = [
            ("通道", provider.get("name", provider_id)),
            ("模型列表地址", provider.get("models_endpoint", "/models")),
            ("来源", model_source_label(probe.get("base_source", "remote"))),
            ("模型数", str(model_count)),
            ("补丁", f"补充 {extra_count} / 隐藏 {hidden_count}"),
        ]
        actions = [
            ("1", "查看当前模型列表"),
            ("2", "刷新远端模型列表"),
            ("3", "添加补充模型"),
            ("4", "隐藏模型"),
            ("5", "移除补充/取消隐藏"),
            ("6", "恢复默认模型补丁"),
            ("7", "编辑模型列表接口"),
            ("8", "一键刷新全部通道模型默认清单"),
            ("9", "返回"),
        ]

        choice = None
        if use_tui():
            try:
                choice = select_channel_action_tui(f"模型管理 · {provider.get('name', provider_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not use_tui():
            ensure_rich()
            console.print(panel_cls(
                "\n".join(f"[bold]{label}:[/bold]  {value}" for label, value in info_lines),
                title="模型管理", border_style="cyan",
            ))
            for action_id, action_label in actions:
                console.print(f"  {action_id}. {action_label}")
            choice = prompt_ask("选择操作", choices=[action[0] for action in actions], default="9")
        if choice is None:
            return current_cfg, changed
        if choice == "9":
            return current_cfg, changed
        if choice == "1":
            if use_tui():
                try:
                    clear_console()
                except Exception:
                    pass
            display_provider_model_table(provider, probe)
            if use_tui():
                pause_after_tui_report("按 Enter 返回模型管理")
            continue
        if choice == "2":
            probe = probe_models(provider, emit_output=True, force_refresh=True)
            console.print(f"[green]✓ 已刷新远端模型列表，共 {len(probe.get('models') or [])} 个模型[/green]")
            changed = True
            continue
        if choice == "3":
            raw = prompt_ask("输入要补充的模型 ID（逗号分隔）", default="")
            additions = normalize_model_id_list(raw)
            if not additions:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = normalize_model_id_list((provider.get("extra_models") or []) + additions)
            next_hidden = [item for item in provider.get("hidden_models", []) if item not in additions]
            current_cfg = update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已补充模型: {', '.join(additions)}[/green]")
            changed = True
            continue
        if choice == "4":
            raw = prompt_ask("输入要隐藏的模型 ID（逗号分隔）", default="")
            hidden = normalize_model_id_list(raw)
            if not hidden:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = [item for item in provider.get("extra_models", []) if item not in hidden]
            next_hidden = normalize_model_id_list((provider.get("hidden_models") or []) + hidden)
            current_cfg = update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已隐藏模型: {', '.join(hidden)}[/green]")
            changed = True
            continue
        if choice == "5":
            raw = prompt_ask("输入要移除的模型 ID（会同时从 extra/hidden 里清理，逗号分隔）", default="")
            removals = set(normalize_model_id_list(raw))
            if not removals:
                console.print("[yellow]没有输入有效模型，已取消[/yellow]")
                continue
            next_extra = [item for item in provider.get("extra_models", []) if item not in removals]
            next_hidden = [item for item in provider.get("hidden_models", []) if item not in removals]
            current_cfg = update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=next_extra,
                hidden_models=next_hidden,
            )
            console.print(f"[green]✓ 已移除模型补丁: {', '.join(sorted(removals))}[/green]")
            changed = True
            continue
        if choice == "6":
            current_cfg = update_provider_model_overrides(
                current_cfg,
                provider_id,
                extra_models=[],
                hidden_models=[],
            )
            console.print("[green]✓ 已恢复默认模型补丁[/green]")
            changed = True
            continue
        if choice == "7":
            new_endpoint = normalize_models_endpoint(
                prompt_ask("模型列表接口路径（输入 manual 表示仅用手工模型）", default=provider.get("models_endpoint", "/models"))
            )
            current_cfg = update_provider_model_overrides(
                current_cfg,
                provider_id,
                models_endpoint=new_endpoint,
            )
            console.print(f"[green]✓ 已更新模型列表接口: {new_endpoint}[/green]")
            changed = True
            continue
        if choice == "8":
            if not callable(refresh_all_provider_model_defaults):
                return current_cfg, changed
            result = refresh_all_provider_model_defaults(current_cfg, emit_output=True)
            current_cfg = result.get("config") if isinstance(result.get("config"), dict) else current_cfg
            console.print(
                f"[green]✓ 已刷新 {result.get('refreshed_providers', 0)} 个通道默认模型清单，"
                f"失败 {result.get('failed_providers', 0)} 个；人工 extra/hidden/model-policy 不会被覆盖[/green]"
            )
            changed = changed or bool(result.get("refreshed_providers"))
            continue
        return current_cfg, changed


def handle_provider_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    provider_map,
    prompt_provider_metadata,
    upsert_provider,
    save_config,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config provider.edit <id>[/red]")
        return
    provider_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    provider = prompt_provider_metadata(existing=providers[provider_id], preset_id=provider_id)
    updated_cfg = upsert_provider(cfg, provider)
    save_config(updated_cfg)
    invalidate_probe_cache(provider_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已更新模型源: {provider_id}[/green]")


def handle_provider_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    default_provider_id,
    ensure_interactive_terminal,
    provider_map,
    confirm_ask,
    save_config,
    delete_provider_credentials,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config provider.remove <id>[/red]")
        return
    ensure_interactive_terminal("模型源删除确认")
    provider_id = args_rest[0].strip()
    providers = provider_map(cfg)
    if provider_id not in providers:
        console.print(f"[red]未找到模型源: {provider_id}[/red]")
        return
    if len(providers) == 1:
        console.print("[red]至少需要保留一个模型源，无法删除最后一个[/red]")
        return
    if not confirm_ask(f"确认删除模型源 '{provider_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return

    updated_cfg = dict(cfg)
    updated_cfg["providers"] = [
        provider for provider in cfg.get("providers", [])
        if provider.get("id") != provider_id
    ]
    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    if default_id == provider_id:
        updated_cfg["provider"] = {"default": updated_cfg["providers"][0]["id"]}
    save_config(updated_cfg)
    delete_provider_credentials(provider_id)
    invalidate_probe_cache(provider_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已删除模型源: {provider_id}[/green]")


def handle_provider_credentials_config(
    cfg,
    args_rest,
    *,
    default_provider_id,
    provider_map,
    resolve_provider_context,
    setup_provider_credentials,
    console,
):
    target_id = args_rest[0].strip() if args_rest else cfg.get("provider", {}).get("default", default_provider_id)
    providers = provider_map(cfg)
    if target_id not in providers:
        console.print(f"[red]未找到模型源: {target_id}[/red]")
        return
    provider = resolve_provider_context(cfg, target_id)
    setup_provider_credentials(
        provider,
        provider.get("base_url", ""),
        provider.get("api_key", ""),
        allow_keep=True,
    )


def handle_provider_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_provider_id_input,
    provider_map,
    normalize_provider,
    backup_config_tree,
    save_config,
    rename_usage_provider,
    invalidate_probe_cache,
    refresh_routes_export_for_hive,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config provider.rename <old_id> <new_id> [new_name][/red]")
        return
    old_id = args_rest[0].strip()
    new_id = normalize_provider_id_input(args_rest[1].strip())
    providers = provider_map(cfg)
    provider = providers.get(old_id)
    if not provider:
        console.print(f"[red]未找到模型源: {old_id}[/red]")
        return
    if old_id == new_id and len(args_rest) < 3:
        console.print("[yellow]名称和标识都未变化，无需重命名[/yellow]")
        return
    if new_id != old_id and new_id in providers:
        console.print(f"[red]目标模型源标识已存在: {new_id}[/red]")
        return

    new_name = args_rest[2].strip() if len(args_rest) >= 3 else new_id
    backup_dir = backup_config_tree("provider-rename")
    updated_cfg = dict(cfg)
    updated_providers = []
    for item in cfg.get("providers", []):
        if item.get("id") != old_id:
            updated_providers.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_name
        updated_providers.append(normalize_provider(renamed))
    updated_cfg["providers"] = updated_providers

    provider_cfg = dict(cfg.get("provider", {}))
    if provider_cfg.get("default") == old_id:
        provider_cfg["default"] = new_id
    updated_cfg["provider"] = provider_cfg
    save_config(updated_cfg)
    rename_usage_provider(old_id, new_id, new_name)
    invalidate_probe_cache(old_id)
    invalidate_probe_cache(new_id)
    refresh_routes_export_for_hive(force=True, quiet=False)
    console.print(f"[green]✓ 已重命名模型源: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]显示名: {new_name}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")


def handle_account_default_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    account_map,
    save_config,
    command_name,
    console,
):
    defaults = cfg.get("account", {}).get("defaults", {})
    if not args_rest:
        for cli_name in managed_oauth_clis:
            value = defaults.get(cli_name, "(未设置)")
            console.print(f"[cyan]account.default.{cli_name}[/cyan] = {value}")
        console.print("[dim]Claude OAuth 独立入口已下线，不再支持 account.default.claude。[/dim]")
        return
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config account.default <cli> <account_id>[/red]")
        return
    cli_name, account_id = args_rest[0].strip(), args_rest[1].strip()
    if cli_name in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再支持设置 account.default.claude。[/yellow]")
        return
    if cli_name not in managed_oauth_clis:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        return
    accounts = account_map(cfg)
    account = accounts.get(account_id)
    if not account:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if account.get("cli") != cli_name:
        console.print(f"[red]账号档案 '{account_id}' 绑定的是 {account.get('cli')}，不能设为 {cli_name} 默认账号[/red]")
        return
    cfg.setdefault("account", {}).setdefault("defaults", {})
    cfg["account"]["defaults"][cli_name] = account_id
    save_config(cfg)
    console.print(f"[green]✓ account.default.{cli_name} = {account_id}[/green]")


def handle_account_add_config(
    cfg,
    args_rest,
    *,
    managed_oauth_clis,
    delegated_oauth_clis,
    quick_connect_official,
    console,
):
    requested_cli = args_rest[0].strip() if args_rest and args_rest[0].strip() else None
    if requested_cli in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再管理 Claude 官方登录。[/yellow]")
        return
    preset_cli = requested_cli if requested_cli in managed_oauth_clis else None
    quick_connect_official(cfg, preset_cli=preset_cli)


def handle_account_edit_config(
    cfg,
    args_rest,
    *,
    command_name,
    account_map,
    delegated_oauth_clis,
    prompt_account_metadata,
    ensure_account_config,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.edit <id>[/red]")
        return
    account_id = args_rest[0].strip()
    accounts = account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if accounts[account_id].get("cli") in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；MMS 不再编辑 Claude 官方账号。[/yellow]")
        return
    account = prompt_account_metadata(existing=accounts[account_id], preset_id=account_id)
    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        updated_accounts.append(account if item.get("id") == account_id else item)
    updated_cfg["accounts"] = updated_accounts
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已更新账号档案: {account_id}[/green]")


def handle_account_remove_config(
    cfg,
    args_rest,
    *,
    command_name,
    ensure_interactive_terminal,
    account_map,
    confirm_ask,
    ensure_account_config,
    save_config,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.remove <id>[/red]")
        return
    ensure_interactive_terminal("账号档案删除确认")
    account_id = args_rest[0].strip()
    accounts = account_map(cfg)
    if account_id not in accounts:
        console.print(f"[red]未找到账号档案: {account_id}[/red]")
        return
    if not confirm_ask(f"确认删除账号档案 '{account_id}'？", default=False):
        console.print("[yellow]已取消删除[/yellow]")
        return
    updated_cfg = dict(cfg)
    updated_cfg["accounts"] = [
        item for item in cfg.get("accounts", [])
        if item.get("id") != account_id
    ]
    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in list(defaults.items()):
        if value == account_id:
            defaults.pop(cli_name, None)
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = ensure_account_config(updated_cfg)
    save_config(updated_cfg)
    console.print(f"[green]✓ 已删除账号档案: {account_id}[/green]")


def handle_account_status_config(
    cfg,
    args_rest,
    *,
    resolve_account_context,
    probe_account_status,
    display_accounts,
    console,
):
    if args_rest:
        account = resolve_account_context(cfg, account_id=args_rest[0].strip())
        status = probe_account_status(account)
        console.print(f"[cyan]{account['id']}[/cyan] = {status['state']}")
        if status.get("summary"):
            console.print(f"[dim]{status['summary']}[/dim]")
        return
    display_accounts(cfg)


def handle_account_login_config(
    cfg,
    args_rest,
    *,
    command_name,
    delegated_oauth_clis,
    resolve_account_context,
    run_account_login,
    console,
):
    if not args_rest:
        console.print(f"[red]用法: {command_name} config account.login <id>[/red]")
        return
    account = resolve_account_context(cfg, account_id=args_rest[0].strip())
    if account and account.get("cli") in delegated_oauth_clis:
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    run_account_login(account)


def handle_account_rename_config(
    cfg,
    args_rest,
    *,
    command_name,
    normalize_account_id,
    account_map,
    backup_config_tree,
    target_account_home,
    path_exists,
    makedirs,
    move,
    normalize_account,
    ensure_account_config,
    save_config,
    rename_usage_account,
    console,
):
    if len(args_rest) < 2:
        console.print(f"[red]用法: {command_name} config account.rename <old_id> <new_id>[/red]")
        return
    old_id = args_rest[0].strip()
    new_id = normalize_account_id(args_rest[1].strip())
    accounts = account_map(cfg)
    account = accounts.get(old_id)
    if not account:
        console.print(f"[red]未找到账号档案: {old_id}[/red]")
        return
    if old_id == new_id:
        console.print("[yellow]新旧文件夹名相同，无需重命名[/yellow]")
        return
    if new_id in accounts:
        console.print(f"[red]目标文件夹名已存在: {new_id}[/red]")
        return

    backup_dir = backup_config_tree("account-rename")
    old_home = os.path.expanduser(str(account.get("home_dir", "")).strip())
    new_home = target_account_home(old_home, new_id)
    if path_exists(new_home):
        console.print(f"[red]目标目录已存在: {new_home}[/red]")
        console.print(f"[dim]备份目录: {backup_dir}[/dim]")
        return

    updated_cfg = dict(cfg)
    updated_accounts = []
    for item in cfg.get("accounts", []):
        if item.get("id") != old_id:
            updated_accounts.append(item)
            continue
        renamed = dict(item)
        renamed["id"] = new_id
        renamed["name"] = new_id
        renamed["home_dir"] = new_home
        updated_accounts.append(normalize_account(renamed))
    updated_cfg["accounts"] = updated_accounts

    defaults = dict(cfg.get("account", {}).get("defaults", {}))
    for cli_name, value in defaults.items():
        if value == old_id:
            defaults[cli_name] = new_id
    updated_cfg["account"] = {"defaults": defaults}
    updated_cfg, _ = ensure_account_config(updated_cfg)

    if path_exists(old_home):
        makedirs(os.path.dirname(new_home), exist_ok=True)
        move(old_home, new_home)

    save_config(updated_cfg)
    rename_usage_account(old_id, new_id, new_id, account.get("cli", ""))
    console.print(f"[green]✓ 已重命名账号档案: {old_id} -> {new_id}[/green]")
    console.print(f"[dim]新目录: {new_home}[/dim]")
    console.print(f"[dim]备份目录: {backup_dir}[/dim]")

