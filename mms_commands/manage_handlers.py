"""Manage/connect TUI command helpers with dependencies injected by core."""

from __future__ import annotations


def build_manage_targets(
    cfg,
    *,
    default_provider_id,
    resolve_provider_context,
    usage_summary_for_runtime,
    probe_account_status,
):
    targets = []
    account_defaults = cfg.get("account", {}).get("defaults", {})

    for provider in cfg.get("providers", []):
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("id", "")).strip()
        if not provider_id:
            continue
        provider_ctx = resolve_provider_context(cfg, provider_id)
        launches, last_used_at = usage_summary_for_runtime("provider", provider_id)
        targets.append({
            "kind": "provider",
            "id": provider_id,
            "title": provider.get("name", provider_id),
            "summary": "默认网关通道" if provider_id == default_provider_id else "网关通道",
            "is_default": provider_id == default_provider_id,
            "default_label": "网关" if provider_id == default_provider_id else "备选",
            "status": "已配置" if provider_ctx.get("base_url") and provider_ctx.get("api_key") else "未配置",
            "launches": launches,
            "last_used_at": last_used_at,
        })

    for account in cfg.get("accounts", []):
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id", "")).strip()
        if not account_id:
            continue
        cli_name = str(account.get("cli", "")).strip()
        launches, last_used_at = usage_summary_for_runtime("account", account_id)
        login_state = probe_account_status(account)
        default_tag = " / 默认" if account_defaults.get(cli_name) == account_id else ""
        targets.append({
            "kind": "account",
            "id": account_id,
            "cli": cli_name,
            "title": account.get("name", account_id),
            "summary": f"官方通道 · {cli_name.upper()}{default_tag}",
            "is_default": account_defaults.get(cli_name) == account_id,
            "default_label": cli_name.upper() if account_defaults.get(cli_name) == account_id else "备选",
            "status": login_state.get("summary") or login_state.get("state", ""),
            "launches": launches,
            "last_used_at": last_used_at,
        })
    targets.sort(
        key=lambda item: (
            0 if item.get("is_default") else 1,
            0 if item.get("kind") == "account" else 1,
            -int(item.get("launches", 0)),
            item.get("last_used_at", ""),
            item.get("title", ""),
        )
    )
    return targets


def select_manage_target_fallback(targets, *, ensure_rich, panel_cls, table_cls, prompt_cls, console):
    ensure_rich()
    console.print(panel_cls(
        f"[bold]通道总数:[/bold] {len(targets)} 个",
        title="管理现有通道",
        border_style="cyan",
    ))
    table = table_cls(show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("类型", style="green")
    table.add_column("显示名", style="yellow")
    table.add_column("默认入口", style="white", width=10)
    table.add_column("状态", style="magenta")
    table.add_column("启动", style="cyan", width=6)
    for index, target in enumerate(targets, 1):
        target_type = "官方" if target.get("kind") == "account" else "网关"
        table.add_row(
            str(index), target_type, target.get("title", ""),
            target.get("default_label", ""), target.get("status", ""),
            str(target.get("launches", 0)),
        )
    console.print(table)

    while True:
        ensure_rich()
        raw = prompt_cls.ask("选择要管理的通道，直接回车返回", default="")
        if not raw:
            return None
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(targets):
                return targets[idx - 1]
        console.print(f"[red]请输入 1-{len(targets)} 的编号[/red]")


def select_manage_target(
    cfg,
    *,
    list_manage_targets,
    use_tui,
    select_manage_target_tui,
    select_manage_target_fallback,
    console,
):
    targets = list_manage_targets(cfg)
    if not targets:
        console.print("[yellow]当前还没有可管理的通道[/yellow]")
        return None

    if use_tui():
        try:
            result = select_manage_target_tui(targets)
            if result is not None:
                return result
            return None
        except (ImportError, Exception):
            pass

    return select_manage_target_fallback(targets)


def run_manage_channels(
    cfg,
    *,
    ensure_interactive_terminal,
    select_manage_target,
    manage_provider_target,
    manage_account_target,
):
    ensure_interactive_terminal("通道管理")
    changed = False
    current_cfg = cfg
    while True:
        target = select_manage_target(current_cfg)
        if target is None:
            return current_cfg, changed
        if target.get("kind") == "provider":
            current_cfg, did_change = manage_provider_target(current_cfg, target["id"])
        else:
            current_cfg, did_change = manage_account_target(current_cfg, target["id"])
        changed = changed or did_change


def run_connect_wizard(
    cfg,
    *,
    ensure_interactive_terminal,
    use_tui,
    load_select_connect_tui,
    prompt_ask,
    quick_connect_gateway,
    quick_connect_official,
    run_manage_channels,
    handle_config_migrate,
    load_config,
    console,
):
    ensure_interactive_terminal("新通道接入")
    action_id = None
    tui_attempted = False
    if use_tui():
        try:
            select_connect_tui = load_select_connect_tui()
        except ImportError:
            select_connect_tui = None
        if select_connect_tui is not None:
            tui_attempted = True
            action_id = select_connect_tui()
    if action_id == "fallback":
        action_id = None
    elif action_id is None and tui_attempted:
        action_id = "cancel"
    if not action_id:
        console.print("\n[bold]接入新通道[/bold]")
        console.print("  1. 添加网关通道")
        console.print("  2. 添加官方通道")
        console.print("  3. 管理现有通道")
        console.print("  4. 迁移配置到 mms")
        console.print("  5. 返回")
        action_id = prompt_ask("选择操作", choices=["1", "2", "3", "4", "5"], default="1")
        action_id = {
            "1": "connect_gateway",
            "2": "connect_official",
            "3": "manage_channels",
            "4": "migrate_config",
            "5": "cancel",
        }[action_id]

    if action_id == "connect_gateway":
        return quick_connect_gateway(cfg)
    if action_id == "connect_official":
        return quick_connect_official(cfg)
    if action_id == "manage_channels":
        return run_manage_channels(cfg)
    if action_id == "migrate_config":
        handle_config_migrate()
        return load_config() or cfg, True
    console.print("[yellow]已取消接入[/yellow]")
    return cfg, False


def manage_provider_target(
    cfg,
    provider_id,
    *,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    use_tui,
    select_channel_action_tui,
    ensure_rich,
    panel_cls,
    prompt_ask,
    display_runtime_usage,
    manage_provider_models,
    default_provider_id,
    save_config,
    load_config,
    normalize_provider_id_input,
    handle_provider_rename_config,
    handle_provider_credentials_config,
    provider_map,
    handle_provider_remove_config,
    console,
):
    provider = resolve_provider_context(cfg, provider_id)
    while True:
        default_tag = "是" if cfg.get("provider", {}).get("default", default_provider_id) == provider_id else "否"
        extra_count = len(provider.get("extra_models", []) or [])
        hidden_count = len(provider.get("hidden_models", []) or [])

        info_lines = [
            ("名称", provider.get("name", provider_id)),
            ("标识", provider_id),
            ("默认", default_tag),
            ("OpenAI", provider_openai_base_url(provider) or "(未设置)"),
            ("Anthropic", provider_anthropic_base_url(provider) or "(未设置)"),
            ("模型列表地址", provider.get("models_endpoint", "/models")),
            ("模型补丁", f"补充 {extra_count} / 隐藏 {hidden_count}"),
            ("协议", ", ".join(provider.get("protocols", []))),
            ("Proxy", provider.get("proxy", "") or "-"),
            ("Timezone", provider.get("timezone", "") or "-"),
        ]
        actions = [
            ("1", "查看本地统计"),
            ("2", "模型管理"),
            ("3", "设为默认网关"),
            ("4", "重命名"),
            ("5", "编辑地址和 Key"),
            ("6", "删除通道"),
            ("7", "返回"),
        ]

        choice = None
        if use_tui():
            try:
                choice = select_channel_action_tui(f"网关 · {provider.get('name', provider_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not use_tui():
            ensure_rich()
            console.print(panel_cls(
                "\n".join(f"[bold]{label}:[/bold]  {value}" for label, value in info_lines),
                title="通道详情", border_style="cyan",
            ))
            for action_id, action_label in actions:
                console.print(f"  {action_id}. {action_label}")
            choice = prompt_ask("选择操作", choices=[action[0] for action in actions], default="7")
        if choice is None:
            return cfg, False
        if choice == "1":
            display_runtime_usage("provider", provider_id, provider.get("name", provider_id))
            continue
        if choice == "2":
            return manage_provider_models(cfg, provider_id)
        if choice == "3":
            cfg.setdefault("provider", {})["default"] = provider_id
            save_config(cfg)
            console.print(f"[green]✓ 默认网关已切换为 {provider_id}[/green]")
            return load_config(), True
        if choice == "4":
            ensure_rich()
            new_id = normalize_provider_id_input(prompt_ask("新的内部标识", default=provider_id).strip())
            new_name = prompt_ask("新的显示名", default=provider.get("name", provider_id)).strip() or new_id
            if new_id == provider_id and new_name == provider.get("name", provider_id):
                console.print("[yellow]名称和标识都未变化，已取消重命名[/yellow]")
                return cfg, False
            handle_provider_rename_config(cfg, [provider_id, new_id, new_name])
            return load_config(), True
        if choice == "5":
            handle_provider_credentials_config(cfg, [provider_id])
            return load_config(), True
        if choice == "6":
            before = set(provider_map(cfg).keys())
            handle_provider_remove_config(cfg, [provider_id])
            after_cfg = load_config()
            return after_cfg, set(provider_map(after_cfg).keys()) != before
        return cfg, False


def prompt_account_rename(
    cfg,
    account_id,
    *,
    ensure_rich,
    prompt_ask,
    account_map,
    handle_account_rename_config,
    load_config,
    console,
):
    ensure_rich()
    console.print(f"[cyan]准备重命名官方通道: {account_id}[/cyan]")
    new_id = prompt_ask("新的文件夹名", default=account_id).strip()
    if not new_id or new_id == account_id:
        console.print("[yellow]文件夹名未变化，已取消重命名[/yellow]")
        return cfg, False
    before_ids = set(account_map(cfg).keys())
    handle_account_rename_config(cfg, [account_id, new_id])
    updated_cfg = load_config()
    after_ids = set(account_map(updated_cfg).keys())
    changed = new_id in after_ids and before_ids != after_ids
    return updated_cfg, changed


def manage_account_target(
    cfg,
    account_id,
    *,
    resolve_account_context,
    probe_account_status,
    use_tui,
    select_channel_action_tui,
    ensure_rich,
    panel_cls,
    prompt_ask,
    display_runtime_usage,
    run_account_login,
    save_config,
    load_config,
    prompt_account_rename,
    handle_account_edit_config,
    handle_account_remove_config,
    account_map,
    console,
):
    account = resolve_account_context(cfg, account_id=account_id)
    while True:
        login_state = probe_account_status(account)
        default_tag = "是" if cfg.get("account", {}).get("defaults", {}).get(account.get("cli")) == account_id else "否"

        info_lines = [
            ("名称", account.get("name", account_id)),
            ("文件夹", account_id),
            ("CLI", account.get("cli", "").upper()),
            ("默认", f"{default_tag}（{account.get('cli', '').upper()}）"),
            ("登录", login_state.get("summary") or login_state.get("state", "")),
            ("Proxy", account.get("proxy", "") or "-"),
            ("Timezone", account.get("timezone", "") or "-"),
        ]
        actions = [
            ("1", "查看本地统计"),
            ("2", "重新登录"),
            ("3", "设为默认官方通道"),
            ("4", "重命名"),
            ("5", "编辑通道"),
            ("6", "删除通道"),
            ("7", "返回"),
        ]

        choice = None
        if use_tui():
            try:
                choice = select_channel_action_tui(f"官方 · {account.get('name', account_id)}", info_lines, actions)
            except (ImportError, Exception):
                pass
        if choice is None and not use_tui():
            ensure_rich()
            console.print(panel_cls(
                "\n".join(f"[bold]{label}:[/bold]  {value}" for label, value in info_lines),
                title="通道详情", border_style="cyan",
            ))
            for action_id, action_label in actions:
                console.print(f"  {action_id}. {action_label}")
            choice = prompt_ask("选择操作", choices=[action[0] for action in actions], default="7")
        if choice is None:
            return cfg, False
        if choice == "1":
            display_runtime_usage("account", account_id, account.get("name", account_id))
            continue
        if choice == "2":
            run_account_login(account)
            return load_config(), True
        if choice == "3":
            cfg.setdefault("account", {}).setdefault("defaults", {})
            cfg["account"]["defaults"][account.get("cli")] = account_id
            save_config(cfg)
            console.print(f"[green]✓ {account.get('cli')} 默认官方通道已更新为 {account_id}[/green]")
            return load_config(), True
        if choice == "4":
            return prompt_account_rename(cfg, account_id)
        if choice == "5":
            handle_account_edit_config(cfg, [account_id])
            return load_config(), True
        if choice == "6":
            before = set(account_map(cfg).keys())
            handle_account_remove_config(cfg, [account_id])
            after_cfg = load_config()
            return after_cfg, set(account_map(after_cfg).keys()) != before
        return cfg, False


def run_account_mgmt_tui(
    cfg,
    *,
    use_tui,
    select_manage_target_tui,
    manage_account_target,
    usage_summary_for_runtime,
    console,
):
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]当前没有配置任何 OAuth 账号[/yellow]")
        return

    account_defaults = cfg.get("account", {}).get("defaults", {})
    targets = []
    for acct in accounts:
        acct_id = str(acct.get("id", "")).strip()
        if not acct_id:
            continue
        cli_name = str(acct.get("cli", "")).strip()
        is_default = account_defaults.get(cli_name) == acct_id
        launches, last_used_at = usage_summary_for_runtime("account", acct_id)
        targets.append({
            "kind": "account",
            "id": acct_id,
            "title": acct.get("name", acct_id),
            "summary": f"官方 · {cli_name.upper()}" + (" · 默认" if is_default else ""),
            "default_label": cli_name.upper() if is_default else "备选",
            "status": "",
            "launches": launches,
            "last_used_at": last_used_at,
        })

    if not targets:
        console.print("[yellow]当前没有可管理的账号[/yellow]")
        return

    if use_tui():
        try:
            target = select_manage_target_tui(targets)
            if target:
                manage_account_target(cfg, target["id"])
        except (ImportError, Exception):
            pass


def run_recommend_mgmt_tui(
    cfg,
    *,
    use_tui,
    load_select_channel_action_tui,
    ensure_rich,
    prompt_ask,
    save_config,
    console,
):
    current_list = list(cfg.get("recommend", {}).get("models", []))

    if use_tui():
        try:
            select_channel_action_tui = load_select_channel_action_tui()
        except ImportError:
            return cfg

        while True:
            info_lines = []
            for i, model_name in enumerate(current_list):
                info_lines.append((str(i + 1), model_name))
            if not info_lines:
                info_lines.append(("-", "(空)"))

            actions = [
                ("add", "添加模型"),
                ("remove", "移除模型"),
                ("clear", "清空列表"),
                ("back", "返回"),
            ]
            choice = select_channel_action_tui("推荐模型", info_lines, actions)

            if choice == "add":
                ensure_rich()
                raw = prompt_ask("输入模型名（逗号分隔）", default="")
                additions = [model.strip() for model in raw.split(",") if model.strip()]
                if additions:
                    for model_name in additions:
                        if model_name not in current_list:
                            current_list.append(model_name)
                    cfg.setdefault("recommend", {})["models"] = current_list
                    save_config(cfg)
                    console.print(f"[green]已添加: {', '.join(additions)}[/green]")
            elif choice == "remove":
                if not current_list:
                    continue
                ensure_rich()
                raw = prompt_ask("输入要移除的模型名（逗号分隔）", default="")
                removals = [model.strip() for model in raw.split(",") if model.strip()]
                if removals:
                    current_list = [model_name for model_name in current_list if model_name not in removals]
                    cfg.setdefault("recommend", {})["models"] = current_list
                    save_config(cfg)
                    console.print(f"[green]已移除: {', '.join(removals)}[/green]")
            elif choice == "clear":
                current_list = []
                cfg.setdefault("recommend", {})["models"] = []
                save_config(cfg)
                console.print("[green]已清空推荐列表[/green]")
            else:
                break

    return cfg


def format_rescue_hot_fallback_event(event):
    if not isinstance(event, dict) or not event:
        return "-"
    at = str(event.get("at") or "")[:19].replace("T", " ")
    model = str(event.get("model") or "").strip()
    note = str(event.get("note") or "").strip()
    parts = [item for item in (at, model, note) if item]
    return " · ".join(parts) if parts else "-"


def latest_rescue_hot_fallback_event(*, get_recent_events, limit=40):
    try:
        events = get_recent_events(limit=limit)
    except Exception:
        return None
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "fallback":
            continue
        if "rescue_hot_fallback" not in str(event.get("note") or ""):
            continue
        return event
    return None


def rescue_landing_tui_payload(default_label, rescue_events, latest_fallback_event=None, hot_fallback_enabled=False):
    events = list(rescue_events or [])
    latest = events[0] if events else {}
    if latest:
        latest_line = " ".join(
            item
            for item in (
                str(latest.get("created_at") or "")[:19].replace("T", " "),
                str(latest.get("failed_model") or ""),
                str(latest.get("status_code") or latest.get("failure_kind") or ""),
            )
            if item
        )
    else:
        latest_line = "-"
    packet_summary = f"{len(events)} 个 packet" if events else "没有 packet"
    has_default = bool(str(default_label or "").strip() and str(default_label or "").strip() != "未设置")
    info_lines = [
        ("全局默认", str(default_label or "未设置")),
        ("Hot fallback", "开启" if hot_fallback_enabled and has_default else "关闭"),
        ("生效范围", "MMS 全局默认；bridge 失败时读取"),
        ("触发时机", "429 / 503 / context / provider failure"),
        ("最近失败", f"{packet_summary} · {latest_line}" if latest else packet_summary),
        ("最近 fallback 尝试", format_rescue_hot_fallback_event(latest_fallback_event)),
        ("安全边界", "只走 routed provider；不使用 global OAuth"),
    ]
    actions = [
        ("choose_route_default", "设置全局默认 fallback（routed models）"),
        ("manual_default", "手动输入 fallback model"),
        ("clear_default", "清除全局默认 fallback"),
    ]
    if has_default:
        actions.append(
            (
                "disable_hot_fallback" if hot_fallback_enabled else "enable_hot_fallback",
                "关闭 hot fallback（只记录 handoff）" if hot_fallback_enabled else "开启 hot fallback（当前会话热切）",
            )
        )
    if events:
        actions.append(("view_packets", "查看最近失败 / rescue packet"))
    actions.extend(
        [
            ("create_demo", "生成测试 rescue packet"),
            ("back", "返回"),
        ]
    )
    return info_lines, actions


def registry_truth_tui_payload(status, *, localize):
    status = status if isinstance(status, dict) else {}
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    freshness = status.get("source_freshness") if isinstance(status.get("source_freshness"), dict) else {}
    info_lines = [
        ("DB", status.get("db_path") or "-"),
        (localize("来源快照", "source snapshots"), counts.get("source_snapshot", 0)),
        (localize("模型身份", "model identities"), counts.get("model_identity", 0)),
        (localize("模型事实", "model facts"), counts.get("model_fact", 0)),
        (localize("待刷新来源", "sources due"), freshness.get("due_count", 0)),
        (localize("最新来源", "latest source"), latest.get("source_path") or "none"),
    ]
    actions = [
        ("check_staleness", localize("检查 Source Staleness", "Check Source Staleness")),
        ("refresh_due_sources", localize("刷新到期 Sources", "Refresh Due Sources")),
        ("scheduled_dry_run", localize("定时刷新 Dry Run", "Scheduled Refresh Dry Run")),
        ("scheduled_no_network", localize("定时刷新 No Network", "Scheduled Refresh No Network")),
        ("refresh_sources", localize("刷新全部 Sources", "Refresh Sources")),
        ("fetch_openrouter", localize("拉取 OpenRouter Catalog", "Fetch OpenRouter Catalog")),
        ("diff_openrouter", localize("对比 OpenRouter Candidate", "OpenRouter Candidate Diff")),
        ("publish_approved", localize("发布 Approved Bundle", "Publish Approved Bundle")),
        ("verify_approved", localize("验证 Approved Bundle", "Verify Approved Bundle")),
        ("doctor", localize("Registry Doctor / 状态", "Registry Doctor / Status")),
        ("back", localize("返回", "Back")),
    ]
    return localize("模型真源 / Registry Truth", "Registry Truth"), info_lines, actions
