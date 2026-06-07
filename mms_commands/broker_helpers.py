"""Broker profile helpers for launcher command flows."""

from __future__ import annotations


def available_broker_profiles_for_cli(_cfg, _cli_name):
    return []


def broker_enabled_by_cli(cfg, cli_names, *, available_broker_profiles_for_cli=available_broker_profiles_for_cli):
    return {
        cli_name: bool(available_broker_profiles_for_cli(cfg, cli_name))
        for cli_name in (cli_names or [])
    }


def select_broker_profile_interactive(
    cfg,
    cli_name,
    *,
    available_broker_profiles_for_cli,
    ensure_rich,
    table_cls,
    prompt_ask,
    console,
):
    profiles = available_broker_profiles_for_cli(cfg, cli_name)
    if not profiles:
        return None
    if len(profiles) == 1:
        return profiles[0]

    ensure_rich()
    table = table_cls(title="Broker Experiment", show_lines=True)
    table.add_column("#", style="cyan", width=4)
    table.add_column("ID", style="green")
    table.add_column("设备/工作区", style="yellow")
    table.add_column("Broker", style="blue")
    table.add_column("Remote", style="magenta")
    for idx, profile in enumerate(profiles, 1):
        table.add_row(
            str(idx),
            str(profile.get("id", "")),
            f"{profile.get('device_id', '-')}/{profile.get('workspace_id', '-')}",
            str(profile.get("broker_base_url") or "-"),
            str(profile.get("remote_service_label") or profile.get("remote_service_base_url") or "-"),
        )
    console.print(table)

    while True:
        raw = prompt_ask("选择 broker profile，直接回车取消", default="").strip()
        if not raw:
            return None
        if raw.isdigit():
            picked = int(raw)
            if 1 <= picked <= len(profiles):
                return profiles[picked - 1]
        console.print("[yellow]请输入有效编号[/yellow]")


def launch_broker_experiment_interactive(
    cfg,
    cli_name,
    *,
    select_broker_profile_interactive,
    run_broker_profile_interactive,
    console,
):
    profile = select_broker_profile_interactive(cfg, cli_name)
    if profile is None:
        return False

    console.print(
        f"[cyan]Broker experiment[/cyan] -> {profile['name']} "
        f"[dim]({profile['device_id']}/{profile['workspace_id']})[/dim]"
    )
    console.print("[dim]支持续最近 / 新开 / 切换旧会话；默认直接回车续最近。[/dim]")
    exit_code = run_broker_profile_interactive(cfg, profile["id"])
    if exit_code != 0:
        console.print(f"[red]broker experiment 启动失败，退出码 {exit_code}[/red]")
    return True
