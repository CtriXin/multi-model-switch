#!/usr/bin/env python3
"""Independent diagnostics for provider/account/model/Claude compatibility.

This script intentionally stays outside the normal launch path so it can be
used as a regression tool without changing runtime selection logic.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ccs_bridge import gateway_claude_bridge
from ccs_core import (
    _account_map,
    _probe_account_status,
    _probe_models,
    _provider_map,
    apply_local_overrides,
    load_config,
    resolve_provider_context,
)
from ccs_launchers import (
    _anthropic_base_url,
    _claude_gateway_env,
    _openai_base_url,
    _resolve_anthropic_base_url,
)

console = Console()
PROMPT = "Reply with OK only."
HTTP_TIMEOUT = 20
CLI_TIMEOUT = 90


@dataclass
class CheckResult:
    category: str
    target: str
    route: str
    status: str
    detail: str
    ok: bool


@dataclass
class ClaudeRoute:
    mode: str
    anthropic_url: str = ""
    openai_url: str = ""
    api_key: str = ""


def _classify_http(status_code: int, body_text: str) -> tuple[str, bool]:
    body = (body_text or "").lower()
    if 200 <= status_code < 300:
        return "ok", True
    if status_code == 400:
        if "model" in body and ("not" in body or "invalid" in body or "exist" in body):
            return "model_invalid", False
        return "bad_request", False
    if status_code == 401:
        return "auth_failed", False
    if status_code == 403:
        return "no_access", False
    if status_code == 404:
        if "model" in body:
            return "model_missing", False
        return "endpoint_missing", False
    if status_code == 408:
        return "timeout", False
    if status_code == 429:
        return "rate_limited", False
    if status_code >= 500:
        return "upstream_unstable", False
    return f"http_{status_code}", False


def _classify_exception(exc: Exception) -> tuple[str, str]:
    text = str(exc).strip() or exc.__class__.__name__
    lower = text.lower()
    if "timed out" in lower:
        return "timeout", text
    if "name or service not known" in lower or "nodename nor servname" in lower:
        return "dns_failed", text
    if "connection refused" in lower:
        return "connection_refused", text
    return "request_failed", text


def _classify_cli_failure(output: str) -> tuple[str, bool]:
    lower = output.lower()
    if "selected model" in lower and "may not exist" in lower:
        return "model_missing_or_no_access", False
    if "401" in lower or "authentication" in lower:
        return "auth_failed", False
    if "403" in lower or "permission" in lower or "access" in lower:
        return "no_access", False
    if "404" in lower or "not found" in lower:
        return "endpoint_or_model_missing", False
    if "rate limit" in lower or "429" in lower:
        return "rate_limited", False
    return "cli_error", False


def _trim(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _check_openai_models(provider: dict[str, Any]) -> CheckResult:
    probe = _probe_models(provider, emit_output=False)
    if probe.get("models") is not None:
        detail = f"models={len(probe.get('models') or [])} url={probe.get('working_url') or _openai_base_url(provider)}"
        return CheckResult("provider", provider["id"], "openai:/models", "ok", detail, True)
    return CheckResult(
        "provider",
        provider["id"],
        "openai:/models",
        probe.get("error_kind") or "probe_failed",
        probe.get("error") or "failed",
        False,
    )


def _check_anthropic_probe(provider: dict[str, Any], probe_model: str) -> CheckResult:
    url, method = _resolve_anthropic_base_url(provider, probe_model=probe_model)
    if url:
        return CheckResult(
            "provider",
            provider["id"],
            "anthropic:/v1/messages",
            "ok",
            f"resolved={url} method={method}",
            True,
        )
    return CheckResult(
        "provider",
        provider["id"],
        "anthropic:/v1/messages",
        "probe_failed",
        f"configured={_anthropic_base_url(provider) or '(none)'}",
        False,
    )


def _openai_chat_check(provider: dict[str, Any], model: str) -> CheckResult:
    url = _openai_base_url(provider)
    headers = {"Authorization": f"Bearer {provider.get('openai_api_key') or provider.get('api_key', '')}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        resp = httpx.post(f"{url}/chat/completions", headers=headers, json=payload, timeout=HTTP_TIMEOUT)
        status, ok = _classify_http(resp.status_code, resp.text)
        return CheckResult("chat", f"{provider['id']}::{model}", "openai", status, _trim(resp.text), ok)
    except Exception as exc:
        status, detail = _classify_exception(exc)
        return CheckResult("chat", f"{provider['id']}::{model}", "openai", status, detail, False)


def _anthropic_chat_check(provider: dict[str, Any], model: str, base_url: str | None = None) -> CheckResult:
    url = (base_url or _anthropic_base_url(provider)).rstrip("/")
    headers = {
        "x-api-key": provider.get("api_key", ""),
        "Authorization": f"Bearer {provider.get('api_key', '')}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    try:
        resp = httpx.post(f"{url}/v1/messages", headers=headers, json=payload, timeout=HTTP_TIMEOUT)
        status, ok = _classify_http(resp.status_code, resp.text)
        return CheckResult("chat", f"{provider['id']}::{model}", "anthropic", status, _trim(resp.text), ok)
    except Exception as exc:
        status, detail = _classify_exception(exc)
        return CheckResult("chat", f"{provider['id']}::{model}", "anthropic", status, detail, False)


def _resolve_claude_route(provider: dict[str, Any], sample_model: str) -> ClaudeRoute:
    anthropic_url, _ = _resolve_anthropic_base_url(provider, probe_model=sample_model)
    if anthropic_url:
        return ClaudeRoute(mode="direct", anthropic_url=anthropic_url)

    openai_url = _openai_base_url(provider)
    api_key = provider.get("openai_api_key") or provider.get("api_key", "")
    if openai_url and api_key:
        return ClaudeRoute(mode="bridge", openai_url=openai_url, api_key=api_key)
    return ClaudeRoute(mode="unavailable")


def _claude_protocol_check(provider: dict[str, Any], model: str, route: ClaudeRoute) -> CheckResult:
    if route.mode == "direct":
        result = _anthropic_chat_check(provider, model, base_url=route.anthropic_url)
        result.category = "claude-protocol"
        result.route = "direct"
        return result

    if route.mode != "bridge":
        return CheckResult("claude-protocol", f"{provider['id']}::{model}", "unavailable", "route_unavailable", "no anthropic/openai route", False)

    try:
        with gateway_claude_bridge(route.openai_url, route.api_key, heavy_model=model) as bridge_cfg:
            headers = {
                "x-api-key": bridge_cfg["api_key"],
                "Authorization": f"Bearer {bridge_cfg['api_key']}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": PROMPT}],
            }
            resp = httpx.post(f"{bridge_cfg['base_url']}/v1/messages", headers=headers, json=payload, timeout=HTTP_TIMEOUT)
            status, ok = _classify_http(resp.status_code, resp.text)
            return CheckResult("claude-protocol", f"{provider['id']}::{model}", "bridge", status, _trim(resp.text), ok)
    except Exception as exc:
        status, detail = _classify_exception(exc)
        return CheckResult("claude-protocol", f"{provider['id']}::{model}", "bridge", status, detail, False)


def _claude_cli_check(provider: dict[str, Any], model: str, route: ClaudeRoute) -> CheckResult:
    bridge_ctx: Any = None
    env: dict[str, str]

    if route.mode == "direct":
        env = _claude_gateway_env(provider, base_url=route.anthropic_url)
        route = "direct"
    else:
        if route.mode != "bridge":
            return CheckResult("claude-cli", f"{provider['id']}::{model}", "unavailable", "route_unavailable", "no route for Claude CLI", False)
        bridge_ctx = gateway_claude_bridge(route.openai_url, route.api_key, heavy_model=model)
        bridge_cfg = bridge_ctx.__enter__()
        env = _claude_gateway_env(provider, base_url=bridge_cfg["base_url"], auth_token=bridge_cfg["api_key"])
        route = "bridge"

    cmd = [
        "claude",
        "-p",
        PROMPT,
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        "",
        "--no-session-persistence",
    ]
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=CLI_TIMEOUT)
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode == 0:
            return CheckResult("claude-cli", f"{provider['id']}::{model}", route, "ok", _trim(output), True)
        status, ok = _classify_cli_failure(output)
        return CheckResult("claude-cli", f"{provider['id']}::{model}", route, status, _trim(output), ok)
    except FileNotFoundError:
        return CheckResult("claude-cli", f"{provider['id']}::{model}", route, "cli_missing", "claude CLI not installed", False)
    except subprocess.TimeoutExpired:
        return CheckResult("claude-cli", f"{provider['id']}::{model}", route, "timeout", "claude CLI timed out", False)
    finally:
        if bridge_ctx is not None:
            bridge_ctx.__exit__(None, None, None)


def _render_table(title: str, results: list[CheckResult]) -> None:
    table = Table(title=title, show_lines=False)
    table.add_column("Category", style="cyan")
    table.add_column("Target", style="green")
    table.add_column("Route", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Detail")
    for item in results:
        status = f"[green]{item.status}[/green]" if item.ok else f"[red]{item.status}[/red]"
        table.add_row(item.category, item.target, item.route, status, item.detail)
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose provider/account/model/Claude compatibility.")
    parser.add_argument("--provider", action="append", help="Only check specific provider id (repeatable).")
    parser.add_argument("--account", action="append", help="Only check specific account id (repeatable).")
    parser.add_argument("--skip-claude-cli", action="store_true", help="Skip real Claude CLI smoke tests.")
    parser.add_argument("--include-oauth", action="store_true", help="Also probe OAuth account status.")
    parser.add_argument("--max-models", type=int, default=0, help="Limit models checked per provider (0 = all).")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of rich tables.")
    args = parser.parse_args()

    cfg = load_config()
    if cfg is None:
        console.print("[red]未找到配置，无法运行诊断[/red]")
        return 1
    cfg = apply_local_overrides(cfg)

    provider_defs = _provider_map(cfg)
    account_defs = _account_map(cfg)
    provider_ids = args.provider or [pid for pid, item in provider_defs.items() if item.get("enabled", True)]
    if args.account:
        account_ids = list(args.account)
    elif args.include_oauth:
        account_ids = [aid for aid, item in account_defs.items() if item.get("enabled", True)]
    else:
        account_ids = []

    provider_results: list[CheckResult] = []
    account_results: list[CheckResult] = []
    model_results: list[CheckResult] = []
    claude_results: list[CheckResult] = []

    for account_id in account_ids:
        account = account_defs.get(account_id)
        if not account:
            account_results.append(CheckResult("oauth", account_id, "status", "missing", "account not found", False))
            continue
        try:
            status = _probe_account_status(account)
            ok = status.get("state") in {"logged_in", "configured"}
            account_results.append(CheckResult("oauth", account_id, "status", status.get("state", "unknown"), status.get("summary", ""), ok))
        except Exception as exc:
            account_results.append(CheckResult("oauth", account_id, "status", "probe_failed", _trim(str(exc)), False))

    for provider_id in provider_ids:
        provider = resolve_provider_context(cfg, provider_id)
        if "openai_chat_completions" in provider.get("protocols", []):
            provider_results.append(_check_openai_models(provider))
        if "anthropic_messages" in provider.get("protocols", []):
            probe_model = (provider.get("fallback_models") or ["claude-sonnet-4-6"])[0]
            provider_results.append(_check_anthropic_probe(provider, probe_model))

        models = _probe_models(provider, emit_output=False).get("models") or []
        if args.max_models and args.max_models > 0:
            models = models[: args.max_models]
        route_info = _resolve_claude_route(provider, models[0] if models else "claude-sonnet-4-6")
        for model in models:
            if "openai_chat_completions" in provider.get("protocols", []):
                model_results.append(_openai_chat_check(provider, model))
            elif "anthropic_messages" in provider.get("protocols", []):
                model_results.append(_anthropic_chat_check(provider, model))
            else:
                model_results.append(CheckResult("chat", f"{provider_id}::{model}", "none", "protocol_unsupported", "provider has no chat protocol", False))

            claude_results.append(_claude_protocol_check(provider, model, route_info))
            if not args.skip_claude_cli:
                claude_results.append(_claude_cli_check(provider, model, route_info))

    all_results = provider_results + account_results + model_results + claude_results
    if args.json:
        print(json.dumps([item.__dict__ for item in all_results], ensure_ascii=False, indent=2))
    else:
        _render_table("Provider / OAuth Connectivity", provider_results + account_results)
        _render_table("Model Chat Availability", model_results)
        _render_table("Claude Compatibility", claude_results)

    return 0 if all(item.ok for item in all_results) else 2


if __name__ == "__main__":
    sys.exit(main())
