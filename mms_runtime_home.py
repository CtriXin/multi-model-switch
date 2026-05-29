"""Runtime HOME isolation context helpers."""

from __future__ import annotations

import os
import sys


def normalize_path(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return os.path.abspath(os.path.expanduser(text))


def path_is_within(path, root):
    path = normalize_path(path)
    root = normalize_path(root)
    if not path or not root:
        return False
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def runtime_net_mode(runtime, *, fake_upstream_enabled_fn):
    if fake_upstream_enabled_fn():
        return "fake"
    return "proxy" if str((runtime or {}).get("proxy") or "").strip() else "direct"


def runtime_dns_mode(runtime, *, fake_upstream_enabled_fn, proxy_dns_mode_fn):
    if fake_upstream_enabled_fn():
        return "fake-local"
    return proxy_dns_mode_fn((runtime or {}).get("proxy") or "")


def build_home_context(
    env,
    runtime,
    cli_name,
    *,
    real_user_home_fn,
    real_user_path_fn,
    selected_mms_config_root_fn=None,
    config_root_is_explicit_fn=None,
    runtime_locale_env_fn,
    runtime_net_mode_fn,
    runtime_dns_mode_fn,
):
    env = env or {}
    runtime = dict(runtime or {})
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    real_home_values = {}
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME"):
        value = normalize_path(env.get(key) or os.environ.get(key) or "")
        if value:
            real_home_values[key] = value
    if not real_home_values:
        real_home_values["derived"] = real_user_home_fn()
    unique_real_homes = sorted(set(real_home_values.values()))
    real_home = unique_real_homes[0] if unique_real_homes else ""
    effective_home = normalize_path(env.get("HOME") or "")
    session_home = normalize_path(env.get("MMS_SESSION_HOME") or "")
    account_home = normalize_path(runtime.get("home_dir") or "")
    xdg_config_home = normalize_path(env.get("XDG_CONFIG_HOME") or "")
    gemini_cli_home = normalize_path(env.get("GEMINI_CLI_HOME") or "")
    if selected_mms_config_root_fn is not None:
        config_root = normalize_path(selected_mms_config_root_fn(env))
    else:
        config_root = os.path.join(real_home, ".config", "mms") if real_home else real_user_path_fn(".config", "mms")
    config_root_explicit = bool(config_root_is_explicit_fn(env)) if config_root_is_explicit_fn is not None else False
    expected_session_home = auth_mode == "oauth" and (
        cli_name == "claude"
        or (cli_name in {"codex", "agy"} and effective_home and effective_home != real_home)
    )
    locale_value = str(env.get("LC_ALL") or env.get("LANG") or runtime_locale_env_fn(runtime).get("LANG") or "").strip()
    return {
        "cli": str(cli_name or "").strip(),
        "auth_mode": auth_mode,
        "real_home": real_home,
        "real_home_values": real_home_values,
        "real_home_conflict": len(unique_real_homes) > 1,
        "effective_home": effective_home,
        "session_home": session_home,
        "account_home": account_home,
        "gemini_cli_home": gemini_cli_home,
        "xdg_config_home": xdg_config_home,
        "config_root": config_root,
        "config_root_explicit": config_root_explicit,
        "net_mode": runtime_net_mode_fn(runtime),
        "dns_mode": runtime_dns_mode_fn(runtime),
        "locale": locale_value,
        "expected_session_home": expected_session_home,
    }


def validate_home_context_or_exit(context, *, console, path_is_within_fn=path_is_within, exit_fn=sys.exit):
    context = dict(context or {})
    cli_name = context.get("cli") or "cli"
    auth_mode = context.get("auth_mode") or "api_key"
    real_home = context.get("real_home") or ""
    effective_home = context.get("effective_home") or ""
    session_home = context.get("session_home") or ""
    account_home = context.get("account_home") or ""
    xdg_config_home = context.get("xdg_config_home") or ""
    config_root = context.get("config_root") or ""
    gemini_cli_home = context.get("gemini_cli_home") or ""

    def _block(reason):
        console.print(f"[red]{cli_name} HOME 保护阻止启动[/red]\n[dim]{reason}[/dim]")
        exit_fn(1)

    if context.get("real_home_conflict"):
        detail = " | ".join(
            f"{key}={value}" for key, value in sorted((context.get("real_home_values") or {}).items())
        )
        _block(f"REAL_HOME hints 不一致：{detail}")
    if not real_home:
        _block("无法解析真实 HOME")

    if auth_mode != "oauth":
        if (
            effective_home
            and real_home
            and not context.get("config_root_explicit")
            and not path_is_within_fn(config_root, real_home)
        ):
            _block(f"config_root 异常：{config_root}")
        return context

    if context.get("expected_session_home"):
        if not effective_home:
            _block("缺少 HOME")
        if not session_home:
            _block("缺少 MMS_SESSION_HOME")
        if effective_home != session_home:
            _block(f"HOME 与 MMS_SESSION_HOME 不一致：HOME={effective_home} | SESSION={session_home}")
        if effective_home == real_home:
            _block(f"隔离账号 HOME 落回真实 HOME：{effective_home}")
        if account_home:
            sessions_root = os.path.join(account_home, "s")
            if not path_is_within_fn(session_home, sessions_root):
                _block(f"session HOME 不在账号隔离目录内：{session_home}")
        if cli_name in {"codex", "agy"}:
            expected_xdg = os.path.join(session_home, ".config")
            if xdg_config_home and xdg_config_home != expected_xdg:
                _block(f"XDG_CONFIG_HOME 未跟随 session HOME：{xdg_config_home}")
    elif cli_name == "gemini":
        if not gemini_cli_home:
            _block("缺少 GEMINI_CLI_HOME")
        if gemini_cli_home == real_home:
            _block(f"GEMINI_CLI_HOME 落回真实 HOME：{gemini_cli_home}")
        if account_home and gemini_cli_home != account_home:
            _block(f"GEMINI_CLI_HOME 与账号目录不一致：{gemini_cli_home}")

    if session_home and path_is_within_fn(config_root, session_home):
        _block(f"config_root 不应落在 session HOME 内：{config_root}")
    if gemini_cli_home and path_is_within_fn(config_root, gemini_cli_home):
        _block(f"config_root 不应落在账号 HOME 内：{config_root}")
    return context


def home_context_lines(context):
    context = dict(context or {})
    lines = []
    real_home = context.get("real_home") or ""
    if real_home:
        lines.append(f"HOME real={real_home}")
    session_home = context.get("session_home") or ""
    if session_home:
        lines.append(f"HOME session={session_home}")
    account_home = context.get("account_home") or ""
    if account_home:
        lines.append(f"HOME account={account_home}")
    gemini_cli_home = context.get("gemini_cli_home") or ""
    if gemini_cli_home:
        lines.append(f"GEMINI_CLI_HOME={gemini_cli_home}")
    extras = []
    xdg_config_home = context.get("xdg_config_home") or ""
    if xdg_config_home:
        extras.append(f"xdg={xdg_config_home}")
    config_root = context.get("config_root") or ""
    if config_root:
        extras.append(f"config_root={config_root}")
    net_mode = context.get("net_mode") or ""
    if net_mode:
        extras.append(f"net={net_mode}")
    dns_mode = context.get("dns_mode") or ""
    if dns_mode:
        extras.append(f"dns={dns_mode}")
    locale_value = context.get("locale") or ""
    if locale_value:
        extras.append(f"lang={locale_value}")
    if extras:
        lines.append(" | ".join(extras))
    return lines


def prepare_oauth_home_context(
    runtime,
    env,
    cli_name,
    *,
    build_home_context_fn,
    validate_home_context_fn,
    home_context_lines_fn,
    console,
):
    context = build_home_context_fn(env, runtime, cli_name)
    validate_home_context_fn(context)
    runtime["_home_context"] = dict(context)
    for line in home_context_lines_fn(context):
        console.print(f"[dim]{line}[/dim]")
    return context
