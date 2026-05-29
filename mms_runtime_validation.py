"""Runtime provider/account validation helpers."""

from __future__ import annotations

import sys


def _launchers():
    import mms_launchers as _module

    return _module


def provider_supports_cli(provider, cli):
    launchers = _launchers()
    cli = str(cli or "").strip().lower()
    supported_clis = provider.get("supported_clis", [])
    if isinstance(supported_clis, str):
        supported_clis = [supported_clis]
    protocols = launchers._provider_protocols(provider)
    normalized = set()
    for item in supported_clis:
        name = str(item or "").strip().lower()
        if name in {"qwen", "kimi"}:
            if "anthropic_messages" in protocols:
                normalized.add("claude")
            if "openai_chat_completions" in protocols:
                normalized.add("codex")
            continue
        normalized.add(name)
    supported_clis = normalized
    if cli == "pi" and "pi" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "opencode", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    if cli == "opencode" and "opencode" not in supported_clis:
        if "openai_chat_completions" in protocols and any(
            item in supported_clis for item in ("codex", "claude")
        ):
            return True
        if "anthropic_messages" in protocols and "claude" in supported_clis:
            return True
    return cli in supported_clis


def validate_provider_for_cli(cli, provider):
    """在真正启动前做 fail-fast 校验。"""
    launchers = _launchers()
    provider_name = provider.get("name", provider.get("id", "provider"))
    provider_id = provider.get("id", "provider")
    required_protocol = launchers.CLI_PROTOCOL_REQUIREMENTS.get(cli)
    protocols = launchers._provider_protocols(provider)

    if cli == "codex" and str(provider_id).strip().lower().startswith("kimi"):
        launchers.console.print(f"[red]provider '{provider_id}' 当前不支持直接驱动 codex；请改走 claude 路径[/red]")
        sys.exit(1)

    if not provider.get("enabled", True):
        launchers.console.print(f"[red]provider '{provider_id}' 已禁用，无法用于 {cli}[/red]")
        sys.exit(1)

    if not launchers._provider_supports_cli(provider, cli):
        # OpenAI-compatible providers can still drive Claude through the bridge path.
        if not (cli == "claude" and "openai_chat_completions" in protocols):
            launchers.console.print(f"[red]provider '{provider_id}' 不支持 CLI: {cli}[/red]")
            sys.exit(1)

    if required_protocol and required_protocol not in launchers._provider_protocols(provider):
        # OpenAI-only provider 可以通过 bridge 驱动 claude，不阻断
        if cli == "claude" and "openai_chat_completions" in protocols:
            pass
        else:
            launchers.console.print(
                f"[red]provider '{provider_id}' ({provider_name}) 缺少协议 {required_protocol}，无法驱动 {cli}[/red]"
            )
            sys.exit(1)

    if not provider.get("api_key"):
        launchers.console.print(f"[red]provider '{provider_id}' 未配置 api_key[/red]")
        sys.exit(1)
    if cli == "claude" and not launchers._anthropic_base_url(provider) and not launchers._openai_base_url(provider):
        launchers.console.print(f"[red]provider '{provider_id}' 未配置任何 API 地址[/red]")
        sys.exit(1)
    if cli in {"codex", "opencode"} and not launchers._openai_base_url(provider):
        launchers.console.print(f"[red]provider '{provider_id}' 未配置 OpenAI 地址[/red]")
        sys.exit(1)
    if cli == "pi" and not launchers._anthropic_base_url(provider) and not launchers._openai_base_url(provider):
        launchers.console.print(f"[red]provider '{provider_id}' 未配置任何可供 Pi 使用的 API 地址[/red]")
        sys.exit(1)


def validate_account_for_cli(cli, account):
    launchers = _launchers()
    account_id = account.get("id", "account")
    account_cli = account.get("cli")
    if cli not in launchers.OAUTH_CAPABLE_CLIS:
        launchers.console.print(f"[red]{cli} 当前不支持 OAuth 账号档案[/red]")
        sys.exit(1)
    if not account.get("enabled", True):
        launchers.console.print(f"[red]账号档案 '{account_id}' 已禁用[/red]")
        sys.exit(1)
    if account_cli and account_cli != cli:
        launchers.console.print(f"[red]账号档案 '{account_id}' 绑定的是 {account_cli}，不能用于 {cli}[/red]")
        sys.exit(1)
    if not str(account.get("home_dir", "")).strip():
        launchers.console.print(f"[red]账号档案 '{account_id}' 缺少 home_dir[/red]")
        sys.exit(1)
