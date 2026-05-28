"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


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


def handle_fake_upstream_command(
    argv,
    *,
    command_name,
    set_enabled,
    status_payload,
    tail_log,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} fake-upstream",
        description="开发期 fake upstream：不访问真实上游，并把请求写入日志",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看 fake upstream 状态")
    subparsers.add_parser("on", help="开启 fake upstream")
    subparsers.add_parser("off", help="关闭 fake upstream")
    log_parser = subparsers.add_parser("log", help="查看 fake upstream 日志")
    log_parser.add_argument("--tail", type=int, default=20, help="最后 N 条")

    args = parser.parse_args(argv)

    if args.subcommand == "on":
        set_enabled(True)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已开启[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        console.print(f"[dim]log:   {payload['log_path']}[/dim]")
        return
    if args.subcommand == "off":
        set_enabled(False)
        payload = status_payload()
        console.print("[green]✓ fake upstream 已关闭[/green]")
        console.print(f"[dim]state: {payload['state_path']}[/dim]")
        return
    if args.subcommand == "log":
        rows = tail_log(args.tail)
        if not rows:
            console.print("[yellow]暂无 fake upstream 日志[/yellow]")
            return
        table = table_cls(title="Fake Upstream Log")
        table.add_column("Time", style="cyan")
        table.add_column("Kind", style="green")
        table.add_column("Target", style="magenta")
        table.add_column("Detail", style="white")
        for row in rows:
            target = str(row.get("url") or row.get("host") or "-")
            if str(row.get("kind") or "") == "upstream":
                detail = row.get("request_body_preview") or row.get("path") or "-"
            else:
                detail = (
                    row.get("path")
                    or row.get("request_body_preview")
                    or row.get("body")
                    or row.get("proxy")
                    or row.get("listen")
                    or "-"
                )
            table.add_row(str(row.get("ts") or "-"), str(row.get("kind") or "-"), target, str(detail))
        console.print(table)
        return

    payload = status_payload()
    table = table_cls(title="Fake Upstream")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("enabled", "yes" if payload.get("enabled") else "no")
    table.add_row("state_path", str(payload.get("state_path") or "-"))
    table.add_row("log_path", str(payload.get("log_path") or "-"))
    table.add_row("proxy_url", str(payload.get("proxy_url") or "-"))
    table.add_row("ca_cert_path", str(payload.get("ca_cert_path") or "-"))
    table.add_row("proxy_pid", str(payload.get("proxy_pid") or "-"))
    table.add_row("proxy_started_at", str(payload.get("proxy_started_at") or "-"))
    table.add_row("updated_at", str(payload.get("updated_at") or "-"))
    console.print(table)


def handle_logs_command(
    argv,
    *,
    command_name,
    fake_upstream_status_payload,
    config_root,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} logs",
        description="显示 MMS 常用日志路径与可直接复制的查看命令",
    )
    parser.add_argument("--tail", type=int, default=20, help="默认 tail 行数")
    args = parser.parse_args(argv)

    fake_payload = fake_upstream_status_payload()
    fake_log_path = str(fake_payload.get("log_path") or "-")
    fake_status_cmd = f"{command_name} fake-upstream status"
    fake_log_cmd = f"{command_name} fake-upstream log --tail {args.tail}"
    raw_tail_cmd = f"tail -n {args.tail} {shlex.quote(fake_log_path)}" if fake_log_path not in {"", "-"} else "-"
    guard_status_cmd = f"{command_name} guard status"

    table = table_cls(title="MMS Logs")
    table.add_column("项", style="cyan", no_wrap=True)
    table.add_column("值", style="green")
    table.add_row("config_root", config_root)
    table.add_row("fake_upstream", "on" if fake_payload.get("enabled") else "off")
    table.add_row("fake_log_path", fake_log_path)
    table.add_row("cmd.status", fake_status_cmd)
    table.add_row("cmd.fake_log", fake_log_cmd)
    table.add_row("cmd.raw_tail", raw_tail_cmd)
    table.add_row("cmd.guard", guard_status_cmd)
    console.print(table)


def handle_exposure_command(
    argv,
    *,
    command_name,
    cli_names,
    load_command_config,
    ensure_provider_credentials,
    ensure_models_ready,
    choose_runtime_source,
    inspect_runtime_exposure,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} exposure",
        description="审计当前 runtime 会向 CLI 暴露哪些 env / settings / HOME 信息",
    )
    parser.add_argument("cli", nargs="?", default="claude", choices=cli_names, help="目标 CLI")
    parser.add_argument("--account", help="指定账号 id")
    parser.add_argument("--provider", help="指定 provider id")
    args = parser.parse_args(argv)

    cfg = load_command_config()
    default_provider = ensure_provider_credentials(cfg)
    default_provider, models_cache = ensure_models_ready(cfg, default_provider)
    runtime, _models, launch_cli = choose_runtime_source(
        cfg,
        args.cli,
        default_provider,
        models_cache,
        account_id=args.account,
        provider_id=args.provider,
    )
    if runtime is None:
        console.print(f"[red]{args.cli} 当前没有可用运行来源[/red]")
        return

    payload = inspect_runtime_exposure(launch_cli, runtime)

    summary = table_cls(title="MMS Exposure Audit")
    summary.add_column("字段", style="cyan")
    summary.add_column("值", style="green")
    summary.add_row("cli", str(payload.get("cli") or "-"))
    summary.add_row("runtime", str(payload.get("runtime_name") or payload.get("runtime_id") or "-"))
    summary.add_row("auth_mode", str(payload.get("auth_mode") or "-"))
    network = payload.get("network") or {}
    summary.add_row("net", str(network.get("proxy_mode") or "-"))
    summary.add_row("dns", str(network.get("dns_mode") or "-"))
    summary.add_row("proxy", str(network.get("proxy_fingerprint") or "-"))
    summary.add_row("timezone", str(network.get("timezone") or "-"))
    summary.add_row("locale", str(network.get("locale") or "-"))
    summary.add_row("fake_upstream", "on" if network.get("fake_upstream") else "off")
    summary.add_row("ipv4", "on" if network.get("force_ipv4") else "off")
    console.print(summary)

    home = payload.get("home") or {}
    home_table = table_cls(title="Session Home / Settings")
    home_table.add_column("字段", style="cyan")
    home_table.add_column("值", style="green")
    home_table.add_row("real_home", str(home.get("real_home") or "-"))
    home_table.add_row("account_home", str(home.get("account_home") or "-"))
    home_table.add_row("session_home", str(home.get("session_home") or "-"))
    home_table.add_row("settings_path", str(home.get("settings_path") or "-"))
    console.print(home_table)

    env_table = table_cls(title="Process Env Exposed To CLI")
    env_table.add_column("Key", style="cyan")
    env_table.add_column("Value", style="green")
    for item in payload.get("process_env") or []:
        env_table.add_row(str(item.get("key") or "-"), str(item.get("value") or "-"))
    console.print(env_table)

    settings = payload.get("settings") or {}
    settings_table = table_cls(title="Session Settings Exposure")
    settings_table.add_column("字段", style="cyan")
    settings_table.add_column("值", style="green")
    settings_table.add_row("statusLine", "on" if settings.get("statusline") else "off")
    settings_table.add_row("hook_events", ", ".join(settings.get("hook_events") or []) or "-")
    settings_table.add_row("env_keys", ", ".join(settings.get("env_keys") or []) or "-")
    console.print(settings_table)

    notes = payload.get("notes") or []
    if notes:
        console.print("[yellow]可观察性说明：[/yellow]")
        for note in notes:
            console.print(f"  - {note}")


def _save_cache_config_value(
    cfg,
    key,
    value,
    *,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
):
    updated_cfg = dict(cfg)
    cache_cfg = dict(updated_cfg.get("cache", {}) if isinstance(updated_cfg.get("cache"), dict) else {})
    cache_cfg[key] = normalize_positive_seconds(value, 1)
    updated_cfg["cache"] = cache_cfg
    updated_cfg, _ = ensure_provider_config(updated_cfg)
    updated_cfg, _ = ensure_account_config(updated_cfg)
    updated_cfg, _ = normalize_user_config(updated_cfg)
    updated_cfg, _ = normalize_cache_config(updated_cfg)
    save_config(updated_cfg)
    return updated_cfg


def _display_cache_settings(
    cfg,
    *,
    probe_async_refresh_after,
    probe_async_min_interval,
    command_name,
    table_cls,
    console,
):
    cache_cfg = cfg.get("cache", {}) if isinstance(cfg.get("cache"), dict) else {}
    refresh_after = cache_cfg.get("probe_async_refresh_after_sec", probe_async_refresh_after)
    min_interval = cache_cfg.get("probe_async_min_interval_sec", probe_async_min_interval)
    table = table_cls(title="MMS Cache Settings")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Meaning", style="white")
    table.add_row("probe_async_refresh_after_sec", str(refresh_after), "cache 超过多久后，启动时后台刷新")
    table.add_row("probe_async_min_interval_sec", str(min_interval), "同一 provider 两次异步刷新最小间隔")
    console.print(table)
    console.print(f"[dim]命令示例: {command_name} cache refresh-after 1800[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache min-interval 300[/dim]")
    console.print(f"[dim]命令示例: {command_name} cache reset[/dim]")


def handle_cache_command(
    argv,
    *,
    command_name,
    load_command_config,
    normalize_positive_seconds,
    ensure_provider_config,
    ensure_account_config,
    normalize_user_config,
    normalize_cache_config,
    save_config,
    probe_async_refresh_after,
    probe_async_min_interval,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} cache",
        description="查看或调整启动期 provider model cache 的异步刷新窗口",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("show", help="显示当前 cache 异步刷新参数")

    refresh_parser = subparsers.add_parser("refresh-after", help="设置 cache 多久后触发后台刷新")
    refresh_parser.add_argument("seconds", type=int, help="正整数秒数")

    interval_parser = subparsers.add_parser("min-interval", help="设置同一 provider 最小异步刷新间隔")
    interval_parser.add_argument("seconds", type=int, help="正整数秒数")

    subparsers.add_parser("reset", help="恢复默认异步刷新参数")

    args = parser.parse_args(argv)
    cfg = load_command_config()

    display_kwargs = {
        "probe_async_refresh_after": probe_async_refresh_after,
        "probe_async_min_interval": probe_async_min_interval,
        "command_name": command_name,
        "table_cls": table_cls,
        "console": console,
    }

    if args.subcommand in {None, "show"}:
        _display_cache_settings(cfg, **display_kwargs)
        return
    if args.subcommand == "refresh-after":
        _save_cache_config_value(
            cfg,
            "probe_async_refresh_after_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_refresh_after_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "min-interval":
        _save_cache_config_value(
            cfg,
            "probe_async_min_interval_sec",
            args.seconds,
            normalize_positive_seconds=normalize_positive_seconds,
            ensure_provider_config=ensure_provider_config,
            ensure_account_config=ensure_account_config,
            normalize_user_config=normalize_user_config,
            normalize_cache_config=normalize_cache_config,
            save_config=save_config,
        )
        console.print(f"[green]✓ cache.probe_async_min_interval_sec = {int(args.seconds)}[/green]")
        return
    if args.subcommand == "reset":
        updated_cfg = dict(cfg)
        updated_cfg["cache"] = {
            "probe_async_refresh_after_sec": probe_async_refresh_after,
            "probe_async_min_interval_sec": probe_async_min_interval,
        }
        updated_cfg, _ = normalize_cache_config(updated_cfg)
        save_config(updated_cfg)
        console.print("[green]✓ 已恢复默认 cache 异步刷新参数[/green]")
        _display_cache_settings(updated_cfg, **display_kwargs)
        return

    parser.print_help()


def handle_guard_command(
    argv,
    *,
    command_name,
    bootstrap_cfg,
    load_config,
    default_config,
    config_write_target_path,
    build_config_guard_snapshot,
    config_snapshot_path,
    load_json_snapshot,
    snapshot_diff_lines,
    iso_now,
    snapshot_digest,
    write_json_snapshot,
    table_cls,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} guard",
        description="查看或接受 MMS 配置/关键文件快照",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("status", help="查看当前快照状态")
    subparsers.add_parser("accept", help="把当前状态设为新的已确认快照")

    args = parser.parse_args(argv)
    config_path = config_write_target_path()
    cfg = bootstrap_cfg if isinstance(bootstrap_cfg, dict) else (load_config() or default_config())
    current_snapshot = build_config_guard_snapshot(cfg, config_path=config_path)
    latest_path = config_snapshot_path("startup", "latest.json", config_path=config_path)
    accepted_path = config_snapshot_path("startup", "accepted.json", config_path=config_path)
    pending_path = config_snapshot_path("startup", "pending.json", config_path=config_path)
    accepted_payload = load_json_snapshot(accepted_path) or {}
    accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
    diff_lines = snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []

    if args.subcommand == "accept":
        payload = {
            "kind": "startup",
            "captured_at": iso_now(),
            "digest": snapshot_digest(current_snapshot),
            "snapshot": current_snapshot,
        }
        write_json_snapshot(latest_path, payload)
        write_json_snapshot(accepted_path, payload)
        if os.path.exists(pending_path):
            try:
                os.remove(pending_path)
            except OSError:
                pass
        console.print(f"[green]✓ 已接受当前快照[/green]\n[dim]{accepted_path}[/dim]")
        return

    status = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
    table = table_cls(title="MMS Snapshot Guard")
    table.add_column("字段", style="cyan")
    table.add_column("值", style="green")
    table.add_row("status", status)
    table.add_row("accepted", accepted_path)
    table.add_row("latest", latest_path)
    table.add_row("pending", pending_path if os.path.exists(pending_path) else "-")
    table.add_row("real_home", current_snapshot.get("real_home", "-"))
    table.add_row("config_path", current_snapshot.get("config_path", "-"))
    table.add_row("accounts", str(len(current_snapshot.get("accounts", []))))
    table.add_row("providers", str(len(current_snapshot.get("providers", []))))
    console.print(table)
    if diff_lines:
        console.print("[red]检测到漂移：[/red]")
        for item in diff_lines[:20]:
            console.print(f"  - {item}")
        if len(diff_lines) > 20:
            console.print(f"[dim]... 还有 {len(diff_lines) - 20} 项[/dim]")


def handle_session_command(
    argv,
    *,
    command_name,
    handle_session_ls,
    handle_session_info,
    handle_session_prune,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} session",
        description="查看 MMS 托管 CLI session",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    ls_parser = subparsers.add_parser("ls", help="列出已索引 session")
    ls_parser.add_argument("--cli", default="claude", choices=["claude"])

    info_parser = subparsers.add_parser("info", help="查看单个 session 详情")
    info_parser.add_argument("session_id", help="session_id 或 pid-<pid>")
    info_parser.add_argument("--cli", default="claude", choices=["claude"])

    prune_parser = subparsers.add_parser("prune", help="列出或删除 stale MMS gateway session")
    prune_parser.add_argument("--cli", default="all", choices=["claude", "codex", "opencode", "all"])
    prune_parser.add_argument("--dry-run", action="store_true", help="只列出候选项；默认行为")
    prune_parser.add_argument("--apply", action="store_true", help="实际删除 stale session；默认只 dry-run")
    prune_parser.add_argument("--yes", action="store_true", help="配合 --apply，确认删除")

    args = parser.parse_args(argv)
    if args.subcommand == "ls":
        handle_session_ls(args.cli)
        return
    if args.subcommand == "info":
        handle_session_info(args.session_id, args.cli)
        return
    if args.subcommand == "prune":
        handle_session_prune(args.cli, apply=bool(args.apply), yes=bool(args.yes))
        return
    parser.print_help()


def handle_env_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
    env_dir,
    preset_env_file_path,
    display_title,
    console,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} env",
        description="输出预设对应的 export 环境变量",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--apply", action="store_true", help="写入 ~/.config/mms/env/<preset>.sh")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name)
    if preset is None:
        return

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider)
    if result is None:
        return

    cli, exports, _runtime = result
    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{args.preset_name} ({cli}) 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if args.apply:
        os.makedirs(env_dir, exist_ok=True)
        env_path = preset_env_file_path(args.preset_name)
        with open(env_path, "w") as handle:
            handle.write(f"# Generated by {display_title()} — preset: {args.preset_name}\n")
            handle.write(export_block + "\n")
        console.print(f"\n[green]✓ 已写入 {env_path}[/green]")
        console.print(f"[dim]需要时手动执行: source {env_path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {command_name} env {args.preset_name} --apply 生成独立 env 文件[/dim]"
        )


def handle_activate_command(
    cfg,
    argv,
    *,
    command_name,
    resolve_named_preset,
    resolve_preset_export_runtime,
):
    parser = argparse.ArgumentParser(
        prog=f"{command_name} activate",
        description="输出可 eval 的 export 语句",
    )
    parser.add_argument("preset_name", help="预设名称")
    parser.add_argument("--provider", help="临时覆盖预设中的 provider")
    args = parser.parse_args(argv)

    preset = resolve_named_preset(cfg, args.preset_name, stderr_only=True)
    if preset is None:
        sys.exit(1)

    result = resolve_preset_export_runtime(cfg, preset, provider_override=args.provider, stderr_only=True)
    if result is None:
        sys.exit(1)

    _cli, exports, _runtime = result
    for key, value in exports.items():
        print(f"export {key}={shlex.quote(str(value))}")

    if sys.stderr.isatty():
        print(f"# ✓ preset '{args.preset_name}' activated", file=sys.stderr)


def handle_models_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_models,
    manage_provider_models,
    text_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} ls [provider_id]"))
        console.print("[dim]不带参数时先选通道，再进入模型列表与测速页。[/dim]")
        return
    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_models(cfg)
        if not provider_id:
            return

    manage_provider_models(cfg, provider_id)


def handle_warm_command(
    cfg,
    argv,
    *,
    command_name,
    provider_map,
    select_provider_for_warm,
    resolve_provider_context,
    probe_models,
    recent_models_for_provider,
    pick_manual_models,
    warm_model_request,
    text_cls,
    panel_cls,
    prompt_cls,
    confirm_cls,
    table_cls,
    console,
):
    if argv and argv[0] in {"-h", "--help"}:
        console.print("[cyan]用法:[/cyan]", text_cls(f"{command_name} warm [provider_id]"))
        console.print("[dim]不带参数时先选通道，再选择最近使用 / 手动选择 / 全部模型。[/dim]")
        return

    provider_id = str(argv[0]).strip() if argv else ""
    providers = provider_map(cfg)
    if provider_id:
        if provider_id not in providers:
            console.print(f"[red]未找到模型源: {provider_id}[/red]")
            console.print(f"[dim]可用模型源: {', '.join(sorted(providers.keys()))}[/dim]")
            sys.exit(1)
    else:
        provider_id = select_provider_for_warm(cfg)
        if not provider_id:
            return

    provider = resolve_provider_context(cfg, provider_id)
    probe = probe_models(provider, emit_output=False)
    models = list(probe.get("models") or [])
    if not models:
        console.print("[yellow]当前通道没有可预热的模型[/yellow]")
        return

    recent_models = [item for item in recent_models_for_provider(provider_id) if item in models]

    console.print(panel_cls(
        f"[bold]通道:[/bold] {provider.get('name', provider_id)}\n"
        f"[bold]可用模型数:[/bold] {len(models)}\n"
        f"[dim]预热会真实发请求，建议优先预热最近常用模型，不建议默认全量预热。[/dim]",
        title="模型预热",
        border_style="cyan",
    ))
    console.print("  1. 预热最近使用模型（推荐）")
    console.print("  2. 手动选择模型")
    console.print("  3. 预热全部模型（不推荐）")
    console.print("  4. 返回")
    choice = prompt_cls.ask("选择操作", choices=["1", "2", "3", "4"], default="1")

    selected_models = []
    if choice == "1":
        selected_models = recent_models
        if not selected_models:
            console.print("[yellow]当前没有最近使用模型，已改为手动选择[/yellow]")
            selected_models = pick_manual_models(models)
    elif choice == "2":
        selected_models = pick_manual_models(models)
    elif choice == "3":
        if not confirm_cls.ask("确认预热当前通道全部模型？这会产生真实请求成本。", default=False):
            console.print("[yellow]已取消全量预热[/yellow]")
            return
        selected_models = models
    else:
        return

    if not selected_models:
        console.print("[yellow]没有选择任何模型，已取消预热[/yellow]")
        return

    results = []
    for model_name in selected_models:
        console.print(f"[dim]正在预热 {model_name} ...[/dim]")
        ok, detail = warm_model_request(provider, model_name)
        results.append((model_name, ok, detail))

    table = table_cls(title=f"{provider.get('name', provider_id)} · 预热结果", show_lines=True)
    table.add_column("模型", style="cyan")
    table.add_column("结果", style="green")
    table.add_column("详情", style="yellow")
    success_count = 0
    for model_name, ok, detail in results:
        if ok:
            success_count += 1
        table.add_row(model_name, "成功" if ok else "失败", detail)
    console.print(table)
    console.print(f"[green]✓ 已完成预热：成功 {success_count} / {len(results)}[/green]")


def handle_export(
    cli_name,
    provider,
    *,
    apply=False,
    cli_names,
    get_export_env,
    env_dir,
    env_file_path,
    display_title,
    export_command_hint,
    console,
):
    if cli_name not in cli_names:
        console.print(f"[red]不支持的 CLI: {cli_name}[/red]")
        console.print(f"支持: {', '.join(cli_names)}")
        return

    exports = get_export_env(cli_name, provider)
    if not exports:
        console.print(f"[yellow]{cli_name} 无需 export；启动时会按 CLI 自己的参数或登录方式处理[/yellow]")
        return

    lines = [f"export {key}={shlex.quote(str(value))}" for key, value in exports.items()]
    export_block = "\n".join(lines)

    console.print(f"\n[bold cyan]{cli_name} 环境变量:[/bold cyan]\n")
    console.print(export_block)

    if apply:
        os.makedirs(env_dir, exist_ok=True)
        path = env_file_path(cli_name)
        with open(path, "w") as handle:
            handle.write(f"# Generated by {display_title()}\n")
            handle.write(export_block + "\n")

        console.print(f"\n[green]✓ 已写入 {path}[/green]")
        console.print("[dim]这是独立 env 文件，不会自动修改 ~/.zshrc 或 ~/.bashrc[/dim]")
        console.print(f"[dim]需要时手动执行: source {path}[/dim]")
    else:
        console.print(
            f"\n[dim]复制上面的命令临时使用，或执行 {export_command_hint(cli_name)} 生成独立 env 文件[/dim]"
        )


def emit_preset_error(message, *, stderr_only=False, console):
    if stderr_only:
        print(message, file=sys.stderr)
    else:
        console.print(message)


def preset_env_file_path(preset_name, *, env_dir):
    safe_name = "".join(
        ch if ch.isalnum() or ch in {"-", "_"} else "-"
        for ch in str(preset_name or "").strip().lower()
    ).strip("-_")
    safe_name = safe_name or "preset"
    return os.path.join(env_dir, f"{safe_name}.sh")


def resolve_named_preset(
    cfg,
    preset_name,
    *,
    normalize_preset_entry,
    emit_preset_error,
    stderr_only=False,
):
    presets = cfg.get("presets", {})
    if preset_name not in presets:
        emit_preset_error(f"预设 '{preset_name}' 不存在", stderr_only=stderr_only)
        if presets:
            emit_preset_error(f"可用预设: {', '.join(presets.keys())}", stderr_only=stderr_only)
        return None
    return normalize_preset_entry(preset_name, presets[preset_name])


def infer_preset_auth_mode(preset):
    if not isinstance(preset, dict):
        return None
    if preset.get("bridge"):
        return "oauth_bridge"
    if preset.get("account"):
        return "oauth"
    if preset.get("provider"):
        return "api_key"
    return None


def resolve_preset_export_runtime(
    cfg,
    preset,
    provider_override=None,
    *,
    stderr_only=False,
    infer_preset_auth_mode,
    emit_preset_error,
    ensure_provider_credentials,
    validate_provider_for_cli,
    get_export_env,
):
    cli = preset.get("cli", "claude")
    auth_mode = infer_preset_auth_mode(preset)

    if auth_mode in ("oauth", "oauth_bridge"):
        emit_preset_error(f"此预设使用 {auth_mode} 模式，不支持 env export", stderr_only=stderr_only)
        return None

    provider_id = provider_override or preset.get("provider") or None

    runtime = ensure_provider_credentials(cfg, provider_id)
    if runtime is None:
        emit_preset_error(f"无法解析 provider: {provider_id or 'default'}", stderr_only=stderr_only)
        return None

    if not provider_id and sys.stderr.isatty():
        default_name = runtime.get("id", "default") if isinstance(runtime, dict) else "default"
        print(f"预设未指定 provider，使用默认: {default_name}", file=sys.stderr)

    try:
        validate_provider_for_cli(cli, runtime)
    except Exception as exc:
        emit_preset_error(str(exc), stderr_only=stderr_only)
        return None

    exports = get_export_env(cli, runtime)
    if not exports:
        emit_preset_error(f"{cli} 无需 export；启动时会按 CLI 自己的参数或登录方式处理", stderr_only=stderr_only)
        return None

    return cli, exports, runtime


def handle_presets_command(
    cfg,
    *,
    preset_has_visible_model_options,
    infer_preset_auth_mode,
    default_provider_id,
    table_cls,
    console,
):
    presets = cfg.get("presets", {})
    visible_presets = {
        name: preset for name, preset in presets.items()
        if preset_has_visible_model_options(preset)
    }
    if visible_presets:
        table = table_cls(title="已保存预设")
        table.add_column("名称", style="cyan")
        table.add_column("CLI", style="green")
        table.add_column("Provider", style="magenta")
        table.add_column("模型", style="yellow")
        table.add_column("描述", style="dim")
        table.add_column("模式", style="blue")
        for name, preset in visible_presets.items():
            model_str = preset.get("model", f"opus={preset.get('opus','')}, sonnet={preset.get('sonnet','')}")
            desc = preset.get("description", "")
            auth = infer_preset_auth_mode(preset) or "—"
            table.add_row(
                name,
                preset.get("cli", "?"),
                preset.get("provider", default_provider_id),
                str(model_str),
                desc,
                auth,
            )
        console.print(table)


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
    console.print("  launch.defaults: thinking_mode, reasoning_effort, caveman_mode, nsr_mode, agent_pack, bypass")
    console.print("  launch.cli.<claude|codex|opencode|agy>: same launch keys")
    console.print("  session_surfaces.disabled: skills, mcp, hooks")
    console.print("  assets.roots: web_access, weber, agent_browser, token_saver, toon, xmem, caveman, nsr, ecc, omc, auto_github_contributor")
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


def run_script_subcommand(script_name, argv, subcommand_name, *, script_dir, command_name, console):
    script_path = os.path.join(script_dir, script_name)
    if not os.path.exists(script_path):
        console.print(f"[red]找不到脚本: {script_path}[/red]")
        return 1
    env = os.environ.copy()
    env["MMS_SUBCOMMAND_PROG"] = f"{command_name} {subcommand_name}"
    try:
        completed = subprocess.run([sys.executable, script_path, *argv], env=env)
        return int(completed.returncode or 0)
    except KeyboardInterrupt:
        return 130


def handle_doctor_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "doctor_claude_models.py",
        argv,
        "doctor",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_test_command(argv, *, subcommand_name, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_cli_channels.py",
        argv,
        subcommand_name,
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )


def handle_opencode_smoke_command(argv, *, script_dir, command_name, console):
    return run_script_subcommand(
        "smoke_opencode_profile.py",
        argv,
        "opencode-smoke",
        script_dir=script_dir,
        command_name=command_name,
        console=console,
    )
