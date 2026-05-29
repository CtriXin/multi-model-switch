"""Retired MMC/OAuth Claude launch guard helpers."""

from __future__ import annotations

import os
import sys


def _launchers():
    import mms_launchers as _module

    return _module


def mmc_entry_path():
    return os.path.join(os.path.dirname(os.path.abspath(_launchers().__file__)), "mmc")


def assert_safe_mmc_delegate_binary(path_value, *, label):
    launchers = _launchers()
    normalized = os.path.realpath(str(path_value or "").strip())
    if not normalized:
        launchers.console.print(f"[red]缺少 {label} binary[/red]")
        sys.exit(1)
    forbidden_parts = ("/.mms/", "/.config/mms/", "/ccswitch", "/hive")
    lowered = normalized.lower()
    for token in forbidden_parts:
        if token.lower() in lowered:
            launchers.console.print(f"[red]{label} binary 命中禁止路径: {normalized}[/red]")
            sys.exit(1)
    if not os.path.isabs(normalized) or not os.path.exists(normalized):
        launchers.console.print(f"[red]{label} binary 非法: {normalized}[/red]")
        sys.exit(1)
    return normalized


def build_mmc_delegate_env():
    env = {}
    for key in ("TERM", "COLORTERM"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            env[key] = value
    env["PATH"] = os.pathsep.join(
        (
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            "/opt/homebrew/bin",
            "/usr/local/bin",
        )
    )
    env["MMC_REAL_HOME"] = _launchers()._real_user_home()
    return env


def mmc_launch_env_overrides(model_info, runtime, *, enable_claude_1m=True):
    launchers = _launchers()
    if isinstance(model_info, dict):
        if model_info.get("lb_light") or model_info.get("lb_medium"):
            launchers.console.print("[red]OAuth Claude 独立入口已下线，不再支持 load-balance / bridge 路线[/red]")
            sys.exit(1)
        resolved_model = launchers._resolve_model(model_info)
    else:
        resolved_model = launchers._resolve_model(model_info)

    resolved_model = str(resolved_model or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
    resolved_lower = resolved_model.lower()
    if not any(token in resolved_lower for token in ("claude", "opus", "sonnet", "haiku")):
        launchers.console.print(f"[red]OAuth Claude 仅支持 Claude family 模型，当前选择不允许: {resolved_model}[/red]")
        sys.exit(1)

    env = {
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "API_TIMEOUT_MS": "3000000",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
    }
    launchers._inject_selected_model_name(env, resolved_model)
    launchers._apply_claude_model_overrides(env, model_info or resolved_model, enable_1m=enable_claude_1m)
    if isinstance(model_info, dict):
        env["CLAUDE_CODE_ENABLE_SUBAGENT_PARALLELISM"] = "1"
        env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] = "5"

    ctx_window = launchers._effective_context_window(
        resolved_model,
        enable_claude_1m=enable_claude_1m,
        provider_id=(runtime or {}).get("id"),
    )
    env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(ctx_window)
    env["CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE"] = str(max(ctx_window - 3000, 10000))
    return env


def exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    launchers = _launchers()
    runtime = runtime if isinstance(runtime, dict) else {}
    runtime_label = (
        str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "claude-oauth").strip()
        or "claude-oauth"
    )
    model_name = launchers._resolve_model(model_info) if model_info else ""
    model_name = str(model_name or "").strip() or "claude-sonnet-4-6"
    launchers.console.print("[red]已阻止 OAuth Claude 自动进入。[/red]")
    launchers.console.print(
        "[yellow]OAuth Claude 现在是 manual-only 保护面：MMS / Hive / fallback / 子进程都不能自动启动它。[/yellow]"
    )
    launchers.console.print(f"[dim]入口: {caller} · runtime={runtime_label} · model={model_name}[/dim]")
    launchers.console.print("[dim]允许的唯一入口：你自己在 real/global shell 手动输入 `claude`，并先跑你的验证脚本。[/dim]")
    raise SystemExit(launchers._CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE)


def launch_claude_oauth_via_mmc(model_info, runtime, once=False, *, enable_claude_1m=True):
    launchers = _launchers()
    launchers._exit_oauth_claude_manual_only(runtime, model_info, caller="MMS")
    mmc_entry = launchers._mmc_entry_path()
    if not os.path.exists(mmc_entry):
        launchers.console.print(f"[red]未找到 MMC 入口: {mmc_entry}[/red]")
        sys.exit(1)

    workspace = os.path.realpath(launchers._safe_getcwd())
    locale_env = launchers._runtime_locale_env(runtime)
    timezone_name = launchers._validate_timezone_or_exit(
        runtime.get("timezone") or launchers.DEFAULT_ACCOUNT_TIMEZONE,
        label=str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "claude-oauth"),
    )
    launch_env = launchers._mmc_launch_env_overrides(
        model_info,
        runtime,
        enable_claude_1m=enable_claude_1m,
    )
    if launchers._runtime_force_ipv4(runtime):
        launchers.console.print("[red]OAuth Claude 路线已禁用 force_ipv4 注入；请改系统网络层，不再透传 NODE_OPTIONS[/red]")
        sys.exit(1)
    claude_bin = launchers._assert_safe_mmc_delegate_binary(
        launchers._resolve_real_home_command_path("claude"),
        label="claude",
    )
    node_bin = launchers._assert_safe_mmc_delegate_binary(
        launchers._resolve_real_home_command_path("node"),
        label="node",
    )

    cmd = [sys.executable, mmc_entry, "run", "--workspace", workspace]
    cmd.extend(["--claude-bin", claude_bin, "--node-bin", node_bin])
    proxy_url = str(runtime.get("proxy") or "").strip()
    if proxy_url:
        cmd.extend(["--proxy", proxy_url])
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if no_proxy:
        cmd.extend(["--no-proxy", no_proxy])
    for flag, value in (
        ("--lang", locale_env.get("LANG")),
        ("--lc-all", locale_env.get("LC_ALL")),
        ("--lc-ctype", locale_env.get("LC_CTYPE")),
        ("--lc-messages", locale_env.get("LC_MESSAGES")),
        ("--tz", timezone_name),
    ):
        if str(value or "").strip():
            cmd.extend([flag, str(value).strip()])
    if runtime.get("bypass"):
        cmd.extend(["--allow-dir", workspace, "--bypass"])
    for key, value in launch_env.items():
        if str(value or "").strip():
            cmd.extend(["--set-env", f"{key}={value}"])

    env = launchers._build_mmc_delegate_env()

    launchers.console.print("[dim]⏳ OAuth Claude 独立入口已下线；不应到达委托启动路径。[/dim]")
    launchers._exec_or_run(cmd, env, once)
