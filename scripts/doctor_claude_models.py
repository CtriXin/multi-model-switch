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
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from mms_bridge import gateway_claude_bridge
from mms_core import (
    _account_map,
    _probe_account_status,
    _probe_models,
    _provider_map,
    apply_local_overrides,
    detect_working_base_url,
    load_config,
    resolve_provider_context,
)
from mms_launchers import _anthropic_base_url, _claude_gateway_env, _openai_base_url

console = Console()
PROMPT = "Reply with OK only."
HTTP_TIMEOUT = 20
CLI_TIMEOUT = 90
ROUTE_PROBE_TIMEOUT = 3
DEFAULT_PARALLELISM = 4


@dataclass
class CheckResult:
    category: str
    target: str
    route: str
    status: str
    detail: str
    ok: bool
    created: str = ""
    created_ts: int | None = None


@dataclass
class ClaudeRoute:
    mode: str
    anthropic_url: str = ""
    openai_url: str = ""
    api_key: str = ""
    resolved_by: str = ""


@dataclass
class ProviderSummary:
    provider_id: str
    model_count: int
    chat_direct: str
    claude_protocol: str
    claude_cli: str
    recommendation: str


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
        if "only available for coding agents" in body or "access_terminated_error" in body:
            return "agent_only", False
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


def _extract_created_fields(model_entry: dict[str, Any]) -> tuple[str, int | None]:
    created_at = str(model_entry.get("created_at", "")).strip()
    if created_at:
        return created_at, None
    raw_created = model_entry.get("created")
    if isinstance(raw_created, (int, float)):
        ts = int(raw_created)
        display = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return display, ts
    return "", None


def _attach_created(result: CheckResult, model_entry: dict[str, Any]) -> CheckResult:
    created, created_ts = _extract_created_fields(model_entry)
    result.created = created
    result.created_ts = created_ts
    return result


def _attach_created_from_response(result: CheckResult, response_text: str) -> CheckResult:
    if result.created or not response_text:
        return result
    try:
        payload = json.loads(response_text)
    except Exception:
        return result
    if not isinstance(payload, dict):
        return result
    created, created_ts = _extract_created_fields(payload)
    if created:
        result.created = created
        result.created_ts = created_ts
    return result


def _fetch_openai_model_catalog(provider: dict[str, Any]) -> list[dict[str, Any]]:
    probe = _probe_models(provider, emit_output=False)
    if probe.get("models") is None:
        return []
    url = probe.get("working_url") or _openai_base_url(provider)
    headers = {"Authorization": f"Bearer {provider.get('openai_api_key') or provider.get('api_key', '')}"}
    try:
        resp = httpx.get(f"{url}/models", headers=headers, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        return [item for item in items if isinstance(item, dict) and item.get("id")]
    except Exception:
        return [{"id": model_id} for model_id in (probe.get("models") or [])]


def _dedupe_model_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for item in entries:
        model_id = str(item.get("id", "")).strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        ordered.append(item)
    return ordered


def _augment_catalog_for_checks(provider: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [dict(entry) for entry in catalog if isinstance(entry, dict)]
    model_ids = [str(entry.get("id", "")).strip() for entry in items]

    def _best_source(prefix: str) -> dict[str, Any] | None:
        matches = [entry for entry in items if str(entry.get("id", "")).strip().startswith(prefix)]
        if not matches:
            return None
        return sorted(
            matches,
            key=lambda item: (
                _extract_created_fields(item)[1] is None,
                -(_extract_created_fields(item)[1] or 0),
                str(item.get("id", "")),
            ),
        )[0]

    def _append_alias(alias: str, prefix: str) -> None:
        if alias in model_ids:
            return
        entry = {"id": alias}
        source = _best_source(prefix)
        if source is not None:
            created, created_ts = _extract_created_fields(source)
            if created:
                entry["created_at"] = created
            if created_ts is not None:
                entry["created"] = created_ts
        items.append(entry)
        model_ids.append(alias)

    if "anthropic_messages" in provider.get("protocols", []):
        _append_alias("claude-sonnet-4-6", "claude-sonnet-4-")
        _append_alias("claude-opus-4-6", "claude-opus-4-")

    def _priority(model_id: str) -> tuple[int, int, str]:
        lower = model_id.lower()
        created_ts = 0
        for item in items:
            if str(item.get("id", "")).strip() == model_id:
                created_ts = _extract_created_fields(item)[1] or 0
                break

        rank = 100
        if "anthropic_messages" in provider.get("protocols", []):
            if lower == "claude-sonnet-4-6":
                rank = 0
            elif lower == "claude-opus-4-6":
                rank = 1
            elif lower.startswith("claude-sonnet-4-"):
                rank = 2
            elif lower.startswith("claude-opus-4-"):
                rank = 3
            elif lower.startswith("claude-haiku-4-5"):
                rank = 4
            elif lower.startswith("claude-"):
                rank = 10
            elif "claude" in lower:
                rank = 11
        if rank == 100 and "openai_chat_completions" in provider.get("protocols", []):
            if lower == "gpt-5.4":
                rank = 20
            elif lower.startswith("gpt-5"):
                rank = 21
            elif lower.startswith("gpt-4.1"):
                rank = 22
            elif lower.startswith(("o1", "o3", "o4")):
                rank = 23
            elif lower.startswith("gpt-"):
                rank = 24
        return rank, -created_ts, model_id

    return sorted(_dedupe_model_entries(items), key=lambda item: _priority(str(item.get("id", "")).strip()))


def _ordered_claude_probe_models(sample_models: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    def _push(model_id: str) -> None:
        value = str(model_id or "").strip()
        if not value or value in seen:
            return
        seen.add(value)
        ordered.append(value)

    for preferred in (
        "claude-sonnet-4-6",
        "claude-opus-4-6",
    ):
        _push(preferred)

    for model_id in sample_models:
        if str(model_id).startswith("claude-sonnet-4-"):
            _push(model_id)
    for model_id in sample_models:
        if str(model_id).startswith("claude-opus-4-"):
            _push(model_id)
    for model_id in sample_models:
        if str(model_id).startswith("claude-haiku-4-5"):
            _push(model_id)
    for model_id in sample_models:
        if "claude" in str(model_id).lower():
            _push(model_id)
    for model_id in sample_models:
        _push(model_id)
    return ordered


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
        result = CheckResult("chat", f"{provider['id']}::{model}", "openai", status, _trim(resp.text), ok)
        return _attach_created_from_response(result, resp.text)
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
        result = CheckResult("chat", f"{provider['id']}::{model}", "anthropic", status, _trim(resp.text), ok)
        return _attach_created_from_response(result, resp.text)
    except Exception as exc:
        status, detail = _classify_exception(exc)
        return CheckResult("chat", f"{provider['id']}::{model}", "anthropic", status, detail, False)


def _resolve_anthropic_route(provider: dict[str, Any], probe_model: str, timeout: int) -> tuple[str | None, str]:
    configured = _anthropic_base_url(provider)
    api_key = provider.get("api_key", "")
    if not configured or not api_key:
        return None, "no_config"

    body = json.dumps({
        "model": probe_model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    headers = {
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    url = detect_working_base_url(configured.rstrip("/"), "/v1/messages", headers, body=body, timeout=timeout)
    if url:
        return url, "probed"
    return None, "failed"


def _resolve_claude_route(provider: dict[str, Any], sample_models: list[str], timeout: int) -> ClaudeRoute:
    ordered_models = _ordered_claude_probe_models(sample_models)
    for model in ordered_models:
        anthropic_url, _ = _resolve_anthropic_route(provider, model, timeout)
        if anthropic_url:
            return ClaudeRoute(mode="direct", anthropic_url=anthropic_url, resolved_by=model)

    openai_url = _openai_base_url(provider)
    api_key = provider.get("openai_api_key") or provider.get("api_key", "")
    if openai_url and api_key:
        resolved_by = ordered_models[0] if ordered_models else ""
        return ClaudeRoute(mode="bridge", openai_url=openai_url, api_key=api_key, resolved_by=resolved_by)
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
    table.add_column("Created", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Detail")
    ordered = sorted(
        results,
        key=lambda item: (
            item.target.split("::", 1)[0],
            0 if item.created_ts is not None or item.created else 1,
            -(item.created_ts or 0),
            item.created,
            item.target,
        ),
    )
    for item in ordered:
        status = f"[green]{item.status}[/green]" if item.ok else f"[red]{item.status}[/red]"
        table.add_row(item.category, item.target, item.route, item.created, status, item.detail)
    console.print(table)


def _collapse_status(results: list[CheckResult]) -> str:
    if not results:
        return "not_tested"
    statuses = [item.status for item in results]
    if any(item.ok for item in results):
        if any(status == "agent_only" for status in statuses):
            return "partial_ok"
        return "ok"
    priority = [
        "agent_only",
        "rate_limited",
        "auth_failed",
        "no_access",
        "endpoint_missing",
        "model_missing",
        "probe_failed",
        "timeout",
        "request_failed",
        "failed",
    ]
    for key in priority:
        if key in statuses:
            return key
    return statuses[0]


def _build_provider_summaries(model_results: list[CheckResult], claude_results: list[CheckResult], include_cli: bool) -> list[ProviderSummary]:
    grouped: dict[str, dict[str, list[CheckResult]]] = {}
    for item in model_results + claude_results:
        provider_id = item.target.split("::", 1)[0]
        grouped.setdefault(provider_id, {}).setdefault(item.category, []).append(item)

    summaries: list[ProviderSummary] = []
    for provider_id in sorted(grouped):
        chat_items = grouped[provider_id].get("chat", [])
        claude_protocol_items = grouped[provider_id].get("claude-protocol", [])
        claude_cli_items = grouped[provider_id].get("claude-cli", [])

        chat_status = _collapse_status(chat_items)
        claude_protocol_status = _collapse_status(claude_protocol_items)
        claude_cli_status = _collapse_status(claude_cli_items) if include_cli else "skipped"

        if claude_protocol_status == "ok" and chat_status == "agent_only":
            recommendation = "chat_direct=no, claude=yes"
        elif claude_protocol_status == "ok" and chat_status == "rate_limited":
            recommendation = "chat_blocked_by_quota, claude=yes"
        elif claude_protocol_status == "ok" and chat_status != "ok":
            recommendation = "chat_partial_or_blocked, claude=yes"
        elif claude_protocol_status != "ok" and chat_status == "ok":
            recommendation = "chat=yes, claude=no"
        elif claude_protocol_status == "ok" and chat_status == "ok":
            recommendation = "chat=yes, claude=yes"
        else:
            recommendation = "needs_manual_check"

        summaries.append(
            ProviderSummary(
                provider_id=provider_id,
                model_count=len(chat_items),
                chat_direct=chat_status,
                claude_protocol=claude_protocol_status,
                claude_cli=claude_cli_status,
                recommendation=recommendation,
            )
        )
    return summaries


def _render_summary_table(summaries: list[ProviderSummary]) -> None:
    table = Table(title="Provider Health Summary", show_lines=False)
    table.add_column("Provider", style="green")
    table.add_column("Models", style="cyan")
    table.add_column("Chat Direct", style="yellow")
    table.add_column("Claude Proto", style="magenta")
    table.add_column("Claude CLI", style="blue")
    table.add_column("Recommendation")
    for item in summaries:
        table.add_row(
            item.provider_id,
            str(item.model_count),
            item.chat_direct,
            item.claude_protocol,
            item.claude_cli,
            item.recommendation,
        )
    console.print(table)


def _run_provider_checks(cfg: dict[str, Any], provider_id: str, max_models: int, skip_claude_cli: bool, route_probe_timeout: int) -> tuple[list[CheckResult], list[CheckResult], list[CheckResult]]:
    provider = resolve_provider_context(cfg, provider_id)
    provider_results: list[CheckResult] = []
    model_results: list[CheckResult] = []
    claude_results: list[CheckResult] = []

    if "openai_chat_completions" in provider.get("protocols", []):
        provider_results.append(_check_openai_models(provider))

    catalog = _augment_catalog_for_checks(provider, _fetch_openai_model_catalog(provider))
    if max_models and max_models > 0:
        catalog = catalog[:max_models]
    probe_candidates = []
    for item in catalog:
        model_id = str(item.get("id", "")).strip()
        if model_id and model_id not in probe_candidates:
            probe_candidates.append(model_id)
    for model_id in provider.get("fallback_models") or []:
        mid = str(model_id).strip()
        if mid and mid not in probe_candidates:
            probe_candidates.append(mid)
    if not probe_candidates:
        probe_candidates = ["claude-sonnet-4-6"]
    route_info = _resolve_claude_route(provider, probe_candidates, route_probe_timeout)

    if "anthropic_messages" in provider.get("protocols", []):
        if route_info.mode == "direct":
            detail = f"resolved={route_info.anthropic_url} via={route_info.resolved_by or '(none)'}"
            provider_results.append(CheckResult("provider", provider["id"], "anthropic:/v1/messages", "ok", detail, True))
        else:
            provider_results.append(CheckResult("provider", provider["id"], "anthropic:/v1/messages", "probe_failed", f"configured={_anthropic_base_url(provider) or '(none)'}", False))

    for entry in catalog:
        model = str(entry.get("id", "")).strip()
        if not model:
            continue
        if "openai_chat_completions" in provider.get("protocols", []):
            model_results.append(_attach_created(_openai_chat_check(provider, model), entry))
        elif "anthropic_messages" in provider.get("protocols", []):
            model_results.append(_attach_created(_anthropic_chat_check(provider, model), entry))
        else:
            model_results.append(_attach_created(CheckResult("chat", f"{provider_id}::{model}", "none", "protocol_unsupported", "provider has no chat protocol", False), entry))

        claude_results.append(_attach_created(_claude_protocol_check(provider, model, route_info), entry))
        if not skip_claude_cli:
            claude_results.append(_attach_created(_claude_cli_check(provider, model, route_info), entry))

    return provider_results, model_results, claude_results


def main() -> int:
    parser = argparse.ArgumentParser(
        prog=os.environ.get("MMS_SUBCOMMAND_PROG") or None,
        description="Diagnose provider/account/model/Claude compatibility.",
        epilog=(
            "Modes:\n"
            "  default(report)  只输出兼容性结果，不改本地配置\n"
            "  --apply-hide     预留安全开关，计划把不兼容模型写入 hidden_models\n"
            "                   当前未实现，因为现有 hidden_models 是 provider 级，不是 per-CLI 级\n"
            "\n"
            "Examples:\n"
            "  mms doctor --provider private --skip-claude-cli --max-models 5\n"
            "  mms doctor --include-oauth --skip-claude-cli\n"
            "  mms doctor --apply-hide   # 当前会明确提示未实现原因"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--provider", action="append", help="Only check specific provider id (repeatable).")
    parser.add_argument("--account", action="append", help="Only check specific account id (repeatable).")
    parser.add_argument("--skip-claude-cli", action="store_true", help="Skip real Claude CLI smoke tests.")
    parser.add_argument("--include-oauth", action="store_true", help="Also probe OAuth account status.")
    parser.add_argument("--max-models", type=int, default=0, help="Limit models checked per provider (0 = all).")
    parser.add_argument("--parallelism", type=int, default=DEFAULT_PARALLELISM, help="How many providers to probe in parallel.")
    parser.add_argument("--route-probe-timeout", type=int, default=ROUTE_PROBE_TIMEOUT, help="Seconds per provider route probe.")
    parser.add_argument(
        "--apply-hide",
        action="store_true",
        help="Reserved safety valve. Planned to write incompatible models into hidden_models after review; currently blocked because hidden_models is provider-wide, not per-CLI.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of rich tables.")
    args = parser.parse_args()

    if args.apply_hide:
        console.print(
            "[yellow]--apply-hide 当前未实现。原因：现有 hidden_models 是 provider 级，会影响所有 CLI，不适合直接按本次诊断结果自动落配置。[/yellow]"
        )
        console.print(
            "[dim]现阶段建议：先用 mms doctor 看清单，再通过 provider 模型管理或 config 手动维护 hidden_models。[/dim]"
        )
        return 3

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

    with ThreadPoolExecutor(max_workers=max(1, args.parallelism)) as executor:
        future_map = {
            executor.submit(
                _run_provider_checks,
                cfg,
                provider_id,
                args.max_models,
                args.skip_claude_cli,
                args.route_probe_timeout,
            ): provider_id
            for provider_id in provider_ids
        }
        for future in as_completed(future_map):
            provider_id = future_map[future]
            try:
                p_results, m_results, c_results = future.result()
            except Exception as exc:
                provider_results.append(CheckResult("provider", provider_id, "diagnostic", "failed", _trim(str(exc)), False))
                continue
            provider_results.extend(p_results)
            model_results.extend(m_results)
            claude_results.extend(c_results)

    all_results = provider_results + account_results + model_results + claude_results
    if args.json:
        payload = {
            "summary": [item.__dict__ for item in _build_provider_summaries(model_results, claude_results, include_cli=not args.skip_claude_cli)],
            "results": [item.__dict__ for item in all_results],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _render_summary_table(_build_provider_summaries(model_results, claude_results, include_cli=not args.skip_claude_cli))
        _render_table("Provider / OAuth Connectivity", provider_results + account_results)
        _render_table("Model Chat Availability", model_results)
        _render_table("Claude Compatibility", claude_results)

    return 0 if all(item.ok for item in all_results) else 2


if __name__ == "__main__":
    sys.exit(main())
