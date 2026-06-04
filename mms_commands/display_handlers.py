"""Display-oriented command helpers with dependencies injected by core."""

from __future__ import annotations

import os


def display_config_help(*, command_name, console):
    console.print(f"[bold]{command_name} config[/bold] — 配置查看与管理")
    console.print(f"[dim]用法: {command_name} config [子命令] [参数][/dim]")
    console.print("\n[bold]常用子命令:[/bold]")
    console.print(f"  {command_name} config")
    console.print(f"  {command_name} config file")
    console.print(f"  {command_name} config validate")
    console.print(f"  {command_name} config get <dot.path>")
    console.print(f"  {command_name} config set <dot.path> <value>")
    console.print(f"  {command_name} config unset <dot.path>")
    console.print(f"  {command_name} config connect")
    console.print(f"  {command_name} config web [--no-open]")
    console.print(f"  {command_name} config preferences.help")
    console.print(f"  {command_name} config human-gate")
    console.print(f"  [dim]可调参数示例: cache.probe_async_refresh_after_sec / cache.probe_async_min_interval_sec[/dim]")
    console.print("\n[bold]Provider:[/bold]")
    console.print(f"  {command_name} config provider.list")
    console.print(f"  {command_name} config provider.default [id]")
    console.print(f"  {command_name} config provider.add [id]")
    console.print(f"  {command_name} config provider.edit <id>")
    console.print(f"  {command_name} config provider.remove <id>")
    console.print(f"  {command_name} config provider.credentials [id]")
    console.print(f"  {command_name} config extension.openrouter [add|status|models]")
    console.print("\n[bold]Account:[/bold]")
    console.print(f"  {command_name} config account.list")
    console.print(f"  {command_name} config account.add \\[codex|agy]")
    console.print(f"  {command_name} config account.edit <id>")
    console.print(f"  {command_name} config account.remove <id>")
    console.print(f"  {command_name} config account.status [id]")
    console.print(f"  {command_name} config account.login <id>")
    console.print(f"  {command_name} config account.default <cli> <id>")
    console.print("  [dim]Claude OAuth 独立入口已下线；MMS 不再新增/登录/设默认 Claude 官方账号。[/dim]")
    console.print("\n[bold]其他:[/bold]")
    console.print(f"  {command_name} config stats")
    console.print(f"  {command_name} config api.edit")


def display_preferences_path(*, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS preferences.toml[/bold]")
    for path in preference_paths:
        marker = "active" if os.path.exists(path) else "create-if-needed"
        console.print(f"  {path}  [dim]({marker})[/dim]")
    console.print(f"[dim]文档: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents may inspect/propose, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_preferences_example(*, preferences_example_toml, console):
    console.print(preferences_example_toml.rstrip(), markup=False)


def display_human_gate_help(*, command_name, preferences_doc_path, console):
    console.print("[bold]MMS Human Gate[/bold]")
    console.print("- real config tree `~/.config/mms/**` is human-only for agents.")
    console.print("- allowed for agents: inspect, explain, generate manual diff, print examples.")
    console.print("- blocked without human confirmation: writing config.toml, preferences.toml, override.toml, credentials.sh, accounts/**, env/**, usage/account state, or Claude config.")
    console.print("- required write flow: plan -> backup -> human double check -> audited write -> post-write human double check.")
    console.print("- `preferences.toml` is safer than `override.toml`, but it is still real user config and stays behind the same human gate.")
    console.print(f"[dim]LLM entry: run `{command_name} config preferences.help` and read {preferences_doc_path} before advising config edits.[/dim]")


def display_preferences_help(*, command_name, preference_paths, preferences_doc_path, console):
    console.print("[bold]MMS User Preferences[/bold]")
    console.print(f"Path: {preference_paths[0]}")
    console.print("Purpose: user-owned, install-safe, allowlisted launch preference overlay.")
    console.print("\n[bold]Commands:[/bold]")
    console.print(f"  {command_name} config preferences.path")
    console.print(f"  {command_name} config preferences.example")
    console.print(f"  {command_name} config preferences.doc")
    console.print(f"  {command_name} config human-gate")
    console.print("\n[bold]Allowed keys:[/bold]")
    console.print("  launch.disabled_clis: hide/disable MMS launch targets such as pi or agy")
    console.print("  launch.defaults: thinking_mode, reasoning_effort, caveman_mode, caveman_level, nsr_mode, agent_pack, bypass")
    console.print("  launch.cli.<claude|codex|opencode|pi|agy>: same launch keys")
    console.print("  session_surfaces.disabled: skills, mcp, hooks")
    console.print("  assets.managed_enabled / assets.managed_root: user-managed MMS session assets")
    console.print("  assets.roots: web_access, weber, agent_browser, codegraph, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor")
    console.print("\n[bold]Denied / ignored:[/bold]")
    console.print("  api_key, base_url, proxy, account identity, provider routes, OAuth tokens, credentials, Claude config, real HOME/XDG/auth state")
    console.print("\n[bold]Overlay order:[/bold]")
    console.print("  config.toml -> override.toml -> preferences.toml launch allowlist -> confirm screen changes -> launcher")
    console.print(f"[dim]Full doc: {preferences_doc_path}[/dim]")
    console.print("[yellow]Human gate:[/yellow] agents can propose edits, but must not auto-write real ~/.config/mms/** without human confirmation.")


def display_usage_stats(*, load_usage_stats, usage_path, table_cls, console):
    stats = load_usage_stats()
    sources = stats.get("sources", {})
    if not sources:
        console.print("[yellow]还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件会写入 {usage_path}[/dim]")
        return

    table = table_cls(title="本地启动统计", show_lines=True)
    table.add_column("来源", style="cyan")
    table.add_column("CLI", style="green")
    table.add_column("启动次数", style="yellow")
    table.add_column("最近模型", style="magenta")
    table.add_column("最近使用", style="white")

    rows = sorted(
        sources.values(),
        key=lambda item: (item.get("last_used_at", ""), item.get("launches", 0)),
        reverse=True,
    )
    for item in rows:
        table.add_row(
            f"{item.get('runtime_kind', 'source')} / {item.get('name', item.get('id', 'default'))}",
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这是本地软统计，用于排序/推荐参考；不等于真实计费数据。[/dim]")


def display_adapter_registry(*, top_source_companies, default_adapter_policy, command_name, table_cls, console):
    table = table_cls(title="来源公司 / Adapter Registry (Top 10)", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("公司/品牌", style="green")
    table.add_column("模型族", style="yellow")
    table.add_column("推荐 Adapter", style="magenta")
    table.add_column("当前状态", style="white")
    table.add_column("OAuth", style="white")
    table.add_column("默认 Claude Bridge", style="white")

    for idx, item in enumerate(top_source_companies, 1):
        table.add_row(
            str(idx),
            f"{item.get('company', '')} / {item.get('brand', '')}",
            ", ".join(item.get("families", [])),
            str(item.get("default_adapter", "")),
            str(item.get("current_support", "")),
            "yes" if item.get("oauth_native") else "no",
            "yes" if item.get("claude_bridge_default") else "no",
        )
    console.print(table)
    console.print("[bold]默认策略:[/bold]")
    for key, text in default_adapter_policy.items():
        console.print(f"  [cyan]{key}[/cyan]: {text}")
    console.print(
        f"[dim]详情文档: docs/ADAPTER_REGISTRY.md；命令: {command_name} config adapter.registry[/dim]"
    )


def display_providers(
    cfg,
    *,
    default_provider_id,
    default_priority,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    command_name,
    table_cls,
    console,
):
    providers = cfg.get("providers", [])
    if not providers:
        console.print("[yellow]未配置模型源[/yellow]")
        return

    table = table_cls(title="模型源列表", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("名称", style="green")
    table.add_column("协议", style="yellow")
    table.add_column("CLI", style="magenta")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="white")
    table.add_column("地址", style="blue")

    default_id = cfg.get("provider", {}).get("default", default_provider_id)
    for provider in providers:
        provider_ctx = resolve_provider_context(cfg, provider.get("id"))
        status = "默认" if provider.get("id") == default_id else ""
        status = f"{status} 启用" if provider.get("enabled", True) else f"{status} 禁用".strip()
        table.add_row(
            str(provider.get("id", "")),
            str(provider.get("name", "")),
            ", ".join(provider.get("protocols", [])),
            ", ".join(provider.get("supported_clis", [])),
            str(provider.get("priority", default_priority)),
            status.strip(),
            provider_openai_base_url(provider_ctx) or provider_anthropic_base_url(provider_ctx) or "(未设置)",
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config provider.default <id> 切换默认模型源。[/dim]"
    )


def display_accounts(
    cfg,
    *,
    default_priority,
    probe_account_status,
    command_name,
    table_cls,
    console,
):
    accounts = cfg.get("accounts", [])
    if not accounts:
        console.print("[yellow]未配置账号档案[/yellow]")
        return

    defaults = cfg.get("account", {}).get("defaults", {})
    table = table_cls(title="账号档案列表", show_lines=True)
    table.add_column("文件夹名", style="cyan")
    table.add_column("显示名", style="green")
    table.add_column("CLI", style="yellow")
    table.add_column("优先级", style="white")
    table.add_column("状态", style="magenta")
    table.add_column("登录态", style="white")
    table.add_column("文件夹目录", style="blue")

    for account in accounts:
        login_state = probe_account_status(account)
        status = []
        if defaults.get(account.get("cli")) == account.get("id"):
            status.append("默认")
        status.append("启用" if account.get("enabled", True) else "禁用")
        table.add_row(
            str(account.get("id", "")),
            str(account.get("name", "")),
            str(account.get("cli", "")),
            str(account.get("priority", default_priority)),
            " ".join(status).strip(),
            login_state.get("summary") or login_state.get("state", ""),
            str(account.get("home_dir", "")),
        )
    console.print(table)
    console.print(
        f"[dim]提示: 可用 {command_name} config account.default <cli> <id> 设置默认账号，"
        f"{command_name} config account.login <id> 进入官方登录。[/dim]"
    )
    console.print("[dim]注: Claude OAuth 独立入口已下线，这里仅保留旧配置只读兼容。[/dim]")


def recent_models_for_provider(provider_id, *, usage_rows_for_runtime):
    recent = []
    seen = set()
    for item in usage_rows_for_runtime("provider", provider_id):
        last_model = str(item.get("last_model", "")).strip()
        if last_model and last_model not in seen:
            seen.add(last_model)
            recent.append(last_model)
        for model_name, _count in sorted((item.get("models") or {}).items(), key=lambda pair: pair[1], reverse=True):
            model_name = str(model_name or "").strip()
            if model_name and model_name not in seen:
                seen.add(model_name)
                recent.append(model_name)
    return recent


def display_runtime_usage(
    runtime_kind,
    runtime_id,
    title,
    *,
    use_tui,
    clear_console,
    usage_rows_for_runtime,
    active_usage_path,
    pause_after_tui_report,
    table_cls,
    console,
):
    if use_tui():
        try:
            clear_console()
        except Exception:
            pass
    rows = usage_rows_for_runtime(runtime_kind, runtime_id)
    if not rows:
        console.print(f"[yellow]{title} 还没有本地启动统计[/yellow]")
        console.print(f"[dim]统计文件: {active_usage_path()}[/dim]")
        if use_tui():
            pause_after_tui_report("按 Enter 返回通道详情")
        return

    table = table_cls(title=f"{title} · 本地统计", show_lines=True)
    table.add_column("CLI", style="cyan")
    table.add_column("启动次数", style="green")
    table.add_column("最近模型", style="yellow")
    table.add_column("最近使用", style="magenta")
    for item in rows:
        table.add_row(
            str(item.get("cli", "")),
            str(item.get("launches", 0)),
            str(item.get("last_model", "")),
            str(item.get("last_used_at", "")),
        )
    console.print(table)
    console.print("[dim]这里只是本地启动统计，不代表官方真实余额或剩余额度。[/dim]")
    if use_tui():
        pause_after_tui_report("按 Enter 返回通道详情")


def display_provider_model_table(
    provider,
    probe,
    *,
    get_speed_entry,
    infer_model_family,
    model_capability_summary,
    model_cli_summary,
    model_source_label,
    ttfb_label,
    tps_label,
    table_cls,
    console,
):
    table = table_cls(title=f"{provider.get('name', provider.get('id'))} · 模型列表", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("家族", style="yellow")
    table.add_column("能力", style="magenta")
    table.add_column("CLI", style="dim")
    table.add_column("来源", style="green")
    table.add_column("首字节延迟", style="yellow")
    table.add_column("生成速度", style="magenta")
    table.add_column("样本", style="white")
    table.add_column("最近更新", style="blue")

    for model_id in probe.get("models") or []:
        speed = get_speed_entry(model_id, provider=provider)
        ttfb = "暂无数据"
        tps = "暂无数据"
        samples = "-"
        updated = "-"
        if speed:
            ttfb_value = speed.get("ttfb_avg_ms")
            ttfb = f"{ttfb_value:.0f}ms / {ttfb_label(ttfb_value)}" if isinstance(ttfb_value, (int, float)) else "暂无数据"
            tps_value = speed.get("tps_avg")
            tps = f"{tps_value:.1f} / {tps_label(tps_value)}" if isinstance(tps_value, (int, float)) else "暂无数据"
            samples = str(speed.get("samples", 0))
            if speed.get("warming_up"):
                samples = f"{samples}（预热中）"
            updated = str(speed.get("last_updated") or "-")
            if speed.get("is_stale"):
                updated = f"{updated} (stale)"
        table.add_row(
            model_id,
            infer_model_family(model_id)[0],
            model_capability_summary(model_id),
            model_cli_summary(model_id),
            model_source_label((probe.get("model_sources") or {}).get(model_id, probe.get("base_source", "remote"))),
            ttfb,
            tps,
            samples,
            updated,
        )
    console.print(table)
    hidden_models = probe.get("hidden_models") or []
    extra_models = probe.get("extra_models") or []
    if extra_models:
        console.print(f"[dim]手工补充模型: {', '.join(extra_models)}[/dim]")
    if hidden_models:
        console.print(f"[dim]已隐藏模型: {', '.join(hidden_models)}[/dim]")
    raw_models = probe.get("raw_models") or []
    if raw_models and raw_models != (probe.get("models") or []):
        console.print(f"[dim]原始模型数: {len(raw_models)} | 最终展示模型数: {len(probe.get('models') or [])}[/dim]")


def display_openrouter_extension_help(command_name, *, console):
    console.print(f"[bold]{command_name} config extension.openrouter[/bold] — OpenRouter 可选扩展")
    console.print(f"  {command_name} config extension.openrouter add")
    console.print(f"  {command_name} config extension.openrouter status [provider_id] [--limit N] [--json]")
    console.print(f"  {command_name} config extension.openrouter models [provider_id] [--limit N] [--json]")
    console.print("[dim]status/models 默认不写真实 MMS 配置；add 会进入交互式 provider 接入。[/dim]")


def display_openrouter_model_rows(title, rows, *, limit, table_cls, console):
    table = table_cls(title=title, show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("免费", style="yellow", width=6)
    table.add_column("输入", style="magenta")
    table.add_column("输出", style="magenta")
    table.add_column("Context", justify="right")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            "yes" if item.get("is_free") else "no",
            ",".join(item.get("input_modalities") or []),
            ",".join(item.get("output_modalities") or []),
            str(item.get("context_length") or ""),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_video_rows(rows, *, limit, table_cls, console):
    table = table_cls(title="OpenRouter Video 模型", show_lines=False)
    table.add_column("模型", style="cyan")
    table.add_column("原始来源", style="green")
    table.add_column("分辨率", style="yellow")
    table.add_column("时长", style="magenta")
    shown = list(rows or [])[: int(limit)]
    for item in shown:
        table.add_row(
            str(item.get("id") or ""),
            str(item.get("origin") or ""),
            ",".join(str(value) for value in item.get("supported_resolutions") or []),
            ",".join(str(value) for value in item.get("supported_durations") or []),
        )
    console.print(table)
    if len(rows or []) > len(shown):
        console.print(f"[dim]仅展示前 {len(shown)} / {len(rows)} 个；可加 --limit 调整。[/dim]")


def display_openrouter_extension_summary(
    summary,
    *,
    provider_label="",
    limit=12,
    show_models=False,
    table_cls,
    console,
):
    account = summary.get("account") or {}
    counts = summary.get("counts") or {}
    requests = summary.get("requests") or {}
    table = table_cls(title="OpenRouter Extension", show_lines=True)
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    table.add_row("provider/key", provider_label or "env/public")
    table.add_row("account tier", f"{account.get('tier')} ({account.get('reason')})")
    table.add_row("model source", str(summary.get("model_source") or "-"))
    table.add_row("visible text", str(counts.get("visible_text", 0)))
    table.add_row("image/video", f"{'on' if summary.get('image_enabled') else 'off'} / {'on' if summary.get('video_enabled') else 'off'}")
    table.add_row("requests", ", ".join(f"{key}:{value.get('status')}" for key, value in requests.items()))
    console.print(table)
    if summary.get("free_only"):
        console.print("[yellow]当前按 free-only 策略展示：只列免费文本模型，隐藏 OpenRouter Image / Video。[/yellow]")
    if not show_models:
        return
    display_openrouter_model_rows("OpenRouter Text 模型", summary.get("text_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("image_enabled"):
        display_openrouter_model_rows("OpenRouter Image 模型", summary.get("image_models") or [], limit=limit, table_cls=table_cls, console=console)
    if summary.get("video_enabled"):
        display_openrouter_video_rows(summary.get("video_models") or [], limit=limit, table_cls=table_cls, console=console)


def display_config(
    cfg,
    *,
    prefix="",
    depth=0,
    resolve_provider_context,
    provider_openai_base_url,
    provider_anthropic_base_url,
    mask_key,
    active_credentials_path,
    active_usage_path,
    display_providers,
    display_accounts,
    probe_async_refresh_after,
    probe_async_min_interval,
    existing_override_paths,
    override_paths,
    existing_preferences_paths,
    preference_paths,
    command_name,
    console,
):
    if depth == 0:
        provider = resolve_provider_context(cfg)
        console.print("[bold]模型源:[/bold]")
        console.print(f"  [cyan]default[/cyan] = {cfg.get('provider', {}).get('default', 'default')}")
        console.print(f"  [cyan]openai_base_url[/cyan] = {provider_openai_base_url(provider) or '(未设置)'}")
        console.print(f"  [cyan]anthropic_base_url[/cyan] = {provider_anthropic_base_url(provider) or '(未设置)'}")
        key_display = mask_key(provider.get("api_key", "")) if provider.get("api_key") else "(未设置)"
        console.print(f"  [cyan]api_key[/cyan] = {key_display}")
        console.print(f"  [cyan]credentials_file[/cyan] = {active_credentials_path()}")
        console.print("  [dim]api_key 为掩码显示；真实值请查看 credentials_file。[/dim]")
        display_providers(cfg)
        display_accounts(cfg)
        console.print(f"  [cyan]usage_file[/cyan] = {active_usage_path()}")
        console.print("  [dim]usage 只记录本地启动统计，不代表真实余额或官方剩余额度。[/dim]")
        cache_cfg = cfg.get("cache", {})
        if isinstance(cache_cfg, dict):
            console.print(f"  [cyan]probe_async_refresh_after_sec[/cyan] = {cache_cfg.get('probe_async_refresh_after_sec', probe_async_refresh_after)}")
            console.print(f"  [cyan]probe_async_min_interval_sec[/cyan] = {cache_cfg.get('probe_async_min_interval_sec', probe_async_min_interval)}")
            console.print("  [dim]以上窗口控制模型列表异步刷新：首屏先读 cache，后台再 refresh。[/dim]")
        active_overrides = existing_override_paths()
        if active_overrides:
            console.print(f"  [cyan]override_files[/cyan] = {active_overrides}")
            console.print("  [dim]override 仅在运行时叠加，不会直接写回 config.toml。[/dim]")
        else:
            console.print(f"  [cyan]override_files[/cyan] = {override_paths}")
            console.print("  [dim]如需团队共享默认值，可在以上路径创建 override.toml。[/dim]")
        active_preferences = existing_preferences_paths()
        console.print(f"  [cyan]preferences_files[/cyan] = {active_preferences or preference_paths}")
        console.print(f"  [dim]用户偏好 allowlist: {command_name} config preferences.help；真实配置仍受 human-gate 保护。[/dim]")

    for key, value in cfg.items():
        if depth == 0 and key in {"providers", "provider", "accounts", "account", "_mms_preferences"}:
            continue
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            console.print(f"{'  ' * depth}[bold]{key}:[/bold]")
            display_config(
                value,
                prefix=full_key,
                depth=depth + 1,
                resolve_provider_context=resolve_provider_context,
                provider_openai_base_url=provider_openai_base_url,
                provider_anthropic_base_url=provider_anthropic_base_url,
                mask_key=mask_key,
                active_credentials_path=active_credentials_path,
                active_usage_path=active_usage_path,
                display_providers=display_providers,
                display_accounts=display_accounts,
                probe_async_refresh_after=probe_async_refresh_after,
                probe_async_min_interval=probe_async_min_interval,
                existing_override_paths=existing_override_paths,
                override_paths=override_paths,
                existing_preferences_paths=existing_preferences_paths,
                preference_paths=preference_paths,
                command_name=command_name,
                console=console,
            )
        elif isinstance(value, list):
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {value}")
        else:
            display = mask_key(str(value)) if "key" in key.lower() else str(value)
            console.print(f"{'  ' * depth}[cyan]{key}[/cyan] = {display}")

