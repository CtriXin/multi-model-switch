"""Small command handlers that are not part of the launcher runtime path."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys


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
