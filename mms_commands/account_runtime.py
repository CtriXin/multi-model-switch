"""Account runtime env, status, and login helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys


def scrub_account_command_env(
    env,
    *,
    prefix_blocklist,
    proxy_env_keys,
    fake_env_keys,
    ca_env_keys,
):
    env = env if isinstance(env, dict) else {}
    for key in list(env.keys()):
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if any(normalized.startswith(prefix) for prefix in prefix_blocklist):
            env.pop(key, None)
            continue
        if normalized in proxy_env_keys or normalized in fake_env_keys or normalized in ca_env_keys:
            env.pop(key, None)
    return env


def account_env(
    account,
    *,
    scrub_account_command_env,
    seed_claude_state,
    seed_agy_state,
    seed_gemini_state,
    environ=os.environ,
    expanduser=os.path.expanduser,
    path_join=os.path.join,
):
    home_dir = expanduser(str(account.get("home_dir", "")).strip())
    cli_name = account.get("cli")
    if cli_name == "claude":
        seed_claude_state(home_dir)
    elif cli_name == "agy":
        seed_agy_state(home_dir)
    env = dict(environ)
    scrub_account_command_env(env)
    if cli_name == "gemini":
        seed_gemini_state(home_dir)
        env["GEMINI_CLI_HOME"] = home_dir
    else:
        xdg_config_home = path_join(home_dir, ".config")
        env["HOME"] = home_dir
        env["XDG_CONFIG_HOME"] = xdg_config_home
    proxy = str(account.get("proxy", "")).strip()
    no_proxy = str(account.get("no_proxy", "")).strip()
    timezone_name = str(account.get("timezone", "")).strip()
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            env[key] = proxy
        for key in ("NO_PROXY", "no_proxy"):
            env[key] = no_proxy
    if timezone_name:
        env["TZ"] = timezone_name
    env["MMS_ACCOUNT_ID"] = str(account.get("id", ""))
    return env


def account_status_command(cli_name):
    if cli_name == "claude":
        return ["claude", "auth", "status"]
    if cli_name == "codex":
        return ["codex", "login", "status"]
    if cli_name == "gemini":
        return None
    if cli_name == "agy":
        return None
    return None


def probe_account_status(
    account,
    *,
    account_env,
    account_status_command=account_status_command,
    expanduser=os.path.expanduser,
    path_exists=os.path.exists,
    path_isdir=os.path.isdir,
    run_command=subprocess.run,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        return {
            "state": "delegated",
            "summary": "Claude OAuth 独立入口已下线；MMS 不再探测或登录这个账号",
        }
    if cli_name == "gemini":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        gemini_dir = os.path.join(home_dir, ".gemini")
        oauth_path = os.path.join(gemini_dir, "oauth_creds.json")
        accounts_path = os.path.join(gemini_dir, "google_accounts.json")
        settings_path = os.path.join(gemini_dir, "settings.json")
        if path_exists(oauth_path) or path_exists(accounts_path):
            return {
                "state": "configured",
                "summary": "已配置 OAuth，建议直接启动 Gemini 验证",
            }
        has_state = path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，待登录" if has_state else "待登录",
        }
    if cli_name == "agy":
        home_dir = expanduser(str(account.get("home_dir", "")).strip())
        agy_dir = os.path.join(home_dir, ".gemini", "antigravity-cli")
        settings_path = os.path.join(agy_dir, "settings.json")
        has_state = path_isdir(agy_dir) or path_exists(settings_path)
        return {
            "state": "manual",
            "summary": "已初始化，登录状态需启动 agy 验证" if has_state else "待登录",
        }
    command = account_status_command(cli_name)
    if command is None:
        return {"state": "unsupported", "summary": "不支持状态探测"}
    try:
        result = run_command(
            command,
            env=account_env(account),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return {"state": "cli_missing", "summary": f"{cli_name} 未安装"}
    except subprocess.TimeoutExpired:
        return {"state": "timeout", "summary": "状态探测超时"}

    output_text = (result.stdout or result.stderr or "").strip()
    output = output_text.splitlines()
    summary = output[0].strip() if output else ""
    if cli_name == "claude" and output_text.startswith("{"):
        try:
            payload = json.loads(output_text)
            email = payload.get("email", "")
            sub = payload.get("subscriptionType", "")
            summary = " / ".join(part for part in [email, sub] if part) or summary
        except json.JSONDecodeError:
            pass
    if result.returncode == 0:
        return {"state": "logged_in", "summary": summary or "已登录"}
    return {"state": "logged_out", "summary": summary or "未登录"}


def run_account_login(
    account,
    *,
    account_env,
    account_label,
    makedirs=os.makedirs,
    run_command=subprocess.run,
    console,
):
    cli_name = account.get("cli")
    if cli_name == "claude":
        console.print("[yellow]Claude OAuth 独立入口已下线；请使用 provider/API route 启动 Claude。[/yellow]")
        return
    env = account_env(account)
    makedirs(account.get("home_dir", ""), exist_ok=True)
    if cli_name == "codex":
        command = ["codex", "login"]
    elif cli_name == "gemini":
        command = ["gemini"]
    elif cli_name == "agy":
        command = ["agy"]
    else:
        console.print(f"[red]不支持的官方账号类型: {cli_name}[/red]")
        sys.exit(1)
    env_hint = f"HOME={account.get('home_dir')}"
    if cli_name == "gemini":
        env_hint = f"GEMINI_CLI_HOME={account.get('home_dir')}"
    console.print(
        f"[cyan]正在为账号档案 {account_label(account)} 打开 {cli_name} 登录流程[/cyan]\n"
        f"[dim]{env_hint}[/dim]"
    )
    if cli_name == "gemini":
        console.print("[dim]Gemini 会在自己的 CLI 内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    if cli_name == "agy":
        console.print("[dim]Antigravity CLI 会在自己的流程内引导 Google 登录；登录完成后按提示重启即可。[/dim]")
    result = run_command(command, env=env)
    if result.returncode != 0:
        sys.exit(result.returncode)
