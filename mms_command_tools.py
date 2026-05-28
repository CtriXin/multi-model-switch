"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


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
