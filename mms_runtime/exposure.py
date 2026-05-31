"""Runtime exposure audit helpers for MMS launchers."""

from __future__ import annotations

import os


def _launchers():
    import mms_launchers as _module

    return _module


def masked_exposure_env_value(key, value):
    key = str(key or "").strip()
    value = str(value or "").strip()
    if not value:
        return ""
    lower_key = key.lower()
    if "proxy" in lower_key and "://" in value:
        return _launchers()._mask_proxy_url(value)
    return value


def inspect_runtime_exposure(cli, runtime):
    launchers = _launchers()
    cli = str(cli or "").strip()
    runtime = dict(runtime or {})
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    runtime_id = str(runtime.get("id") or runtime.get("name") or "").strip()
    real_home = launchers._real_user_home()
    account_home = launchers._normalize_path(runtime.get("home_dir") or "")
    fake_payload = launchers._fake_upstream_status_payload() if launchers._fake_upstream_enabled() else {}
    locale_env = launchers._runtime_locale_env(runtime)
    timezone_name = launchers._validate_timezone_or_exit(
        runtime.get("timezone") or launchers.DEFAULT_ACCOUNT_TIMEZONE,
        label=runtime_id or cli or "runtime",
    )
    process_env = {
        "MMS_REAL_HOME": real_home,
        "REAL_HOME": real_home,
        "ORIGINAL_HOME": real_home,
        "TZ": timezone_name,
    }
    process_env.update(locale_env)
    home_info = {
        "real_home": real_home,
        "account_home": account_home,
        "session_home": "",
        "settings_path": "",
    }
    settings_info = {
        "path": "",
        "statusline": False,
        "hook_events": [],
        "env_keys": [],
    }
    notes = [
        "CLI 进程可直接读取这些环境变量；上游通常看不到本地 proxy URL，但能观察到出口 IP / DNS 行为 / 时间与语言表现。",
    ]

    if cli == "claude" and auth_mode == "oauth":
        session_home = os.path.join(account_home, "s", str(os.getpid())) if account_home else ""
        account_claude_dir = os.path.join(account_home, ".claude") if account_home else ""
        session_claude_dir = os.path.join(session_home, ".claude") if session_home else ""
        process_env["HOME"] = session_home
        process_env["MMS_SESSION_HOME"] = session_home
        home_info["session_home"] = session_home
        home_info["settings_path"] = os.path.join(session_claude_dir, "settings.json") if session_claude_dir else ""
        account_settings = launchers._load_claude_settings_from_dir(account_claude_dir)
        projected_env = dict(process_env)
        launchers._apply_runtime_network_profile(projected_env, runtime, validate_proxy=False)
        required_env = launchers._session_required_env_from_runtime_env(projected_env)
        session_settings = launchers._build_claude_session_settings(
            base_settings=account_settings,
            required_env=required_env,
            default_env={
                "CLAUDE_CODE_ATTRIBUTION_HEADER": "0",
                "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
            },
            allow_execution_surfaces=False,
        )
        settings_info = {
            "path": home_info["settings_path"],
            "statusline": isinstance(session_settings.get("statusLine"), dict),
            "hook_events": sorted((session_settings.get("hooks") or {}).keys()),
            "env_keys": sorted((session_settings.get("env") or {}).keys()),
        }
        notes.append("Claude OAuth session 采用 fail-closed 隔离策略：不注入 MMS 管理的 hooks / statusLine / MCP / wrapper。")
    elif cli == "claude":
        gateway_home = launchers._claude_gateway_home()
        home_info["session_home"] = gateway_home
        home_info["settings_path"] = os.path.join(gateway_home, ".claude", "settings.json")
        process_env["HOME"] = gateway_home
        process_env["MMS_SESSION_HOME"] = gateway_home
        projected_settings = launchers._build_claude_session_settings(
            base_settings=launchers._load_real_claude_settings(),
            default_env={"CLAUDE_CODE_ATTRIBUTION_HEADER": "0"},
        )
        settings_info = {
            "path": home_info["settings_path"],
            "statusline": isinstance(projected_settings.get("statusLine"), dict),
            "hook_events": sorted((projected_settings.get("hooks") or {}).keys()),
            "env_keys": sorted((projected_settings.get("env") or {}).keys()),
        }
        notes.append("Claude provider/gateway 模式也会在 session settings.json 中暴露 statusLine / hooks / env。")
    elif cli == "codex" and auth_mode == "oauth":
        session_home = os.path.join(account_home, "s", str(os.getpid())) if account_home else ""
        process_env["HOME"] = launchers._real_user_path()
        process_env["MMS_SESSION_HOME"] = session_home
        process_env["CODEX_HOME"] = os.path.join(session_home, ".codex") if session_home else ""
        process_env["XDG_CONFIG_HOME"] = launchers._real_user_path(".config")
        process_env["MMS_HOME_ISOLATION_MODE"] = "soft"
        process_env["MMS_SOFT_HOME"] = "1"
        home_info["session_home"] = session_home
        notes.append("Codex 使用 soft-home：真实 HOME + 隔离 CODEX_HOME。")
    elif cli == "gemini" and auth_mode == "oauth":
        process_env["GEMINI_CLI_HOME"] = account_home
        home_info["session_home"] = account_home
        notes.append("Gemini OAuth 当前通过 GEMINI_CLI_HOME 指向账号目录，不走 Claude 那套 session settings。")
    elif cli == "agy" and auth_mode == "oauth":
        session_home = os.path.join(account_home, "s", str(os.getpid())) if account_home else ""
        process_env["HOME"] = session_home
        process_env["MMS_SESSION_HOME"] = session_home
        process_env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config") if session_home else ""
        home_info["session_home"] = session_home
        home_info["settings_path"] = os.path.join(
            account_home,
            ".gemini",
            "antigravity-cli",
            "settings.json",
        ) if account_home else ""
        notes.append("Antigravity CLI 使用隔离 HOME；账号状态位于 account_home/.gemini/antigravity-cli。")

    if launchers._runtime_force_ipv4(runtime):
        process_env["MMS_FORCE_IPV4"] = "1"
    proxy_url = str(runtime.get("proxy") or "").strip()
    no_proxy = str(runtime.get("no_proxy") or "").strip()
    if launchers._fake_upstream_enabled():
        fake_proxy_url = str(fake_payload.get("proxy_url") or "").strip()
        if fake_proxy_url:
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
                process_env[key] = fake_proxy_url
        for key in ("NO_PROXY", "no_proxy"):
            process_env[key] = "127.0.0.1,localhost,::1"
        process_env["MMS_FAKE_UPSTREAM_MODE"] = "upstream-proxy"
        if proxy_url:
            process_env["MMS_FAKE_UPSTREAM_ORIGINAL_PROXY"] = launchers._proxy_fingerprint(proxy_url)
        if no_proxy:
            process_env["MMS_FAKE_UPSTREAM_ORIGINAL_NO_PROXY"] = no_proxy
        if fake_payload.get("ca_cert_path"):
            process_env["NODE_EXTRA_CA_CERTS"] = str(fake_payload.get("ca_cert_path") or "")
            process_env["SSL_CERT_FILE"] = str(fake_payload.get("ca_cert_path") or "")
    elif proxy_url:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            process_env[key] = proxy_url
        for key in ("NO_PROXY", "no_proxy"):
            process_env[key] = no_proxy

    process_env_rows = [
        {"key": key, "value": launchers._masked_exposure_env_value(key, value)}
        for key, value in sorted(process_env.items())
        if str(value or "").strip()
    ]
    return {
        "cli": cli,
        "runtime_id": runtime_id,
        "runtime_name": str(runtime.get("name") or runtime_id or "").strip(),
        "auth_mode": auth_mode,
        "network": {
            "proxy_mode": launchers._runtime_net_mode(runtime),
            "proxy_fingerprint": launchers._proxy_fingerprint(proxy_url),
            "dns_mode": launchers._runtime_dns_mode(runtime),
            "timezone": timezone_name,
            "locale": locale_env.get("LANG", ""),
            "force_ipv4": bool(launchers._runtime_force_ipv4(runtime)),
            "fake_upstream": bool(launchers._fake_upstream_enabled()),
        },
        "home": home_info,
        "process_env": process_env_rows,
        "settings": settings_info,
        "notes": notes,
    }
