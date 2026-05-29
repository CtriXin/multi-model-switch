"""Launcher dispatch entrypoint helpers."""

from __future__ import annotations

import sys


def launch_cli(
    cli,
    model_info,
    runtime,
    *,
    once=False,
    extra_args=None,
    launchers,
    console,
    validate_account_for_cli_fn,
    validate_provider_for_cli_fn,
    is_opencode_global_profile_runtime_fn,
    enforce_claude_network_guard_or_exit_fn,
    claude_bypass_requires_proxy_fn,
    resolve_model_fn,
    exit_oauth_claude_manual_only_fn,
    probe_models_fn,
    launch_status_fn,
    print_launch_step_done_fn,
    show_launch_info_fn,
    exit_fn=sys.exit,
):
    """Dispatch a selected runtime to its CLI launcher."""
    runtime = dict(runtime)
    launcher = launchers.get(cli)
    if not launcher:
        console.print(f"[red]不支持的 CLI: {cli}[/red]")
        exit_fn(1)
    auth_mode = runtime.get("auth_mode", "api_key")
    if auth_mode == "oauth_bridge":
        source_label = runtime.get("name", runtime.get("id", "account"))
        source_kind = "官方桥接"
    elif auth_mode == "oauth":
        validate_account_for_cli_fn(runtime.get("cli", cli), runtime)
        source_label = runtime.get("name", runtime.get("id", "account"))
        source_kind = "账号档案"
    elif is_opencode_global_profile_runtime_fn(cli, runtime):
        source_label = runtime.get("name", runtime.get("id", "global-opencode-omo"))
        source_kind = "OpenCode 全局配置"
    else:
        validate_provider_for_cli_fn(cli, runtime)
        source_label = runtime.get("name", runtime.get("id", "provider"))
        source_kind = "模型源"

    if cli == "claude" and auth_mode == "oauth":
        # OAuth Claude remains a manual standalone path; MMS no longer reads its concurrent state.
        runtime.pop("_account_guard_report", None)
    if cli == "claude" and auth_mode in {"oauth", "api_key"} and runtime.get("bypass"):
        enforce_claude_network_guard_or_exit_fn(
            runtime,
            require_proxy=claude_bypass_requires_proxy_fn(runtime),
        )

    model_display = (
        resolve_model_fn(model_info)
        if not isinstance(model_info, dict)
        else model_info.get("model", model_info.get("sonnet", "多模型配置"))
    )

    if cli == "claude" and auth_mode == "oauth":
        exit_oauth_claude_manual_only_fn(runtime, model_info, caller="launch_cli")
    if cli == "claude" and auth_mode == "api_key":
        prefetched_probe = None
        try:
            with launch_status_fn("预读取模型列表中...", spinner="dots") as step_start:
                prefetched_probe = probe_models_fn(runtime, emit_output=False)
            models = list((prefetched_probe or {}).get("models") or [])
            detail = f"{len(models)} 个模型"
            base_source = (prefetched_probe or {}).get("base_source")
            if base_source:
                detail += f" · {base_source}"
            print_launch_step_done_fn("启动前模型预读取", step_start, detail)
        except Exception:
            console.print("[yellow]· 启动前模型预读取失败，后续继续按默认流程处理[/yellow]")
        runtime["_launch_prefetched_probe"] = prefetched_probe

    console.print(f"\n[bold green]🚀 启动 {cli}[/bold green] — {model_display}")
    console.print(f"[dim]{source_kind}: {source_label} ({runtime.get('id', 'default')})[/dim]")
    console.print(f"[dim]认证方式: {auth_mode}[/dim]")
    show_launch_info_fn(cli, runtime, auth_mode)
    console.print("[dim]─" * 40 + "[/dim]\n")

    if extra_args:
        launcher(model_info, runtime, once=once, extra_args=list(extra_args))
    else:
        launcher(model_info, runtime, once=once)
