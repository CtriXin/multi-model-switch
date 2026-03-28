#!/usr/bin/env python3
"""Minimal CLI-closed-loop smoke tests for MMS providers."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import httpx

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from mms_bridge import codex_chatcompletions_bridge, codex_responses_bridge, gateway_claude_bridge
from mms_core import _probe_models, _provider_map, apply_local_overrides, load_config, resolve_provider_context
from mms_launchers import _is_gpt_model, _openai_base_url, _resolve_anthropic_base_url


def _trim(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _pick_claude_model(models: list[str]) -> str:
    ordered = []
    seen = set()

    def _push(value: str) -> None:
        model = str(value or "").strip()
        if not model or model in seen:
            return
        seen.add(model)
        ordered.append(model)

    for preferred in ("claude-sonnet-4-6", "claude-opus-4-6"):
        _push(preferred)
    for model in models:
        if model.startswith("claude-sonnet-4-"):
            _push(model)
    for model in models:
        if model.startswith("claude-opus-4-"):
            _push(model)
    for model in models:
        if model.startswith("claude-haiku-4-5"):
            _push(model)
    for model in models:
        if "claude" in model.lower():
            _push(model)
    for model in models:
        _push(model)
    return ordered[0] if ordered else ""


def _pick_codex_model(models: list[str]) -> str:
    ordered = []
    seen = set()

    def _push(value: str) -> None:
        model = str(value or "").strip()
        if not model or model in seen:
            return
        seen.add(model)
        ordered.append(model)

    for preferred in ("gpt-5.4", "gpt-5", "gpt-5-chat-latest", "gpt-4.1", "o3", "o4-mini"):
        _push(preferred)
    for model in models:
        if _is_gpt_model(model):
            _push(model)
    for model in models:
        _push(model)
    return ordered[0] if ordered else ""


def _result(provider_id: str, cli: str, ok: bool, route: str, model: str, status: str, detail: str, preview: Any = None) -> dict[str, Any]:
    return {
        "provider": provider_id,
        "cli": cli,
        "ok": ok,
        "route": route,
        "model": model,
        "status": status,
        "detail": detail,
        "preview": preview,
    }


def _smoke_claude(runtime: dict[str, Any], *, model: str = "", timeout: int = 45) -> dict[str, Any]:
    provider_id = runtime.get("id", "?")
    advertised = list(_probe_models(runtime, emit_output=False).get("models") or [])
    selected_model = model or _pick_claude_model(advertised)
    if not selected_model:
        return _result(provider_id, "claude", False, "unavailable", "", "no_model", "未找到可用于 Claude smoke 的模型")

    anthropic_url, method = _resolve_anthropic_base_url(runtime, probe_model=selected_model)
    headers = {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "user-agent": "claude-cli/2.1.81 (external, sdk-cli)",
    }
    payload = {
        "model": selected_model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Reply with OK only."}],
    }

    if anthropic_url:
        direct_headers = dict(headers)
        direct_headers["x-api-key"] = runtime.get("api_key", "")
        direct_headers["Authorization"] = f"Bearer {runtime.get('api_key', '')}"
        resp = httpx.post(f"{anthropic_url.rstrip('/')}/v1/messages", headers=direct_headers, json=payload, timeout=timeout)
        ok = resp.status_code == 200
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text[:500]}
        preview = body.get("content") if isinstance(body, dict) else None
        return _result(provider_id, "claude", ok, "direct", selected_model, str(resp.status_code), f"resolved={anthropic_url} method={method}", preview=preview)

    openai_url = _openai_base_url(runtime)
    api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
    if not openai_url or not api_key:
        return _result(provider_id, "claude", False, "unavailable", selected_model, "no_route", "既没有可用 anthropic route，也没有可桥接的 openai route")

    with gateway_claude_bridge(openai_url, api_key, heavy_model=selected_model, advertised_models=advertised) as bridge:
        bridge_headers = dict(headers)
        bridge_headers["x-api-key"] = bridge["api_key"]
        bridge_headers["Authorization"] = f"Bearer {bridge['api_key']}"
        models_resp = httpx.get(f"{bridge['base_url']}/v1/models", headers=bridge_headers, timeout=20)
        msg_resp = httpx.post(f"{bridge['base_url']}/v1/messages", headers=bridge_headers, json=payload, timeout=timeout)
        ok = models_resp.status_code == 200 and msg_resp.status_code == 200
        try:
            body = msg_resp.json()
        except Exception:
            body = {"raw": msg_resp.text[:500]}
        detail = f"bridge_models={models_resp.status_code} bridge_messages={msg_resp.status_code}"
        preview = body.get("content") if isinstance(body, dict) else None
        return _result(provider_id, "claude", ok, "bridge", selected_model, str(msg_resp.status_code), detail, preview=preview)


def _smoke_codex(runtime: dict[str, Any], *, model: str = "", timeout: int = 90, max_preview_lines: int = 6) -> dict[str, Any]:
    provider_id = runtime.get("id", "?")
    advertised = list(_probe_models(runtime, emit_output=False).get("models") or [])
    selected_model = model or _pick_codex_model(advertised)
    if not selected_model:
        return _result(provider_id, "codex", False, "unavailable", "", "no_model", "未找到可用于 Codex smoke 的模型")

    gateway_url = _openai_base_url(runtime)
    api_key = runtime.get("openai_api_key") or runtime.get("api_key", "")
    if not gateway_url or not api_key:
        return _result(provider_id, "codex", False, "unavailable", selected_model, "no_route", "缺少 openai base_url 或 api_key")

    bridge_factory = codex_responses_bridge if _is_gpt_model(selected_model) else codex_chatcompletions_bridge
    route = "responses_bridge" if bridge_factory is codex_responses_bridge else "chatcompletions_bridge"

    if bridge_factory is codex_responses_bridge:
        bridge_ctx = bridge_factory(
            gateway_url,
            api_key,
            model_name=selected_model,
            advertised_models=advertised,
            provider_id=provider_id,
        )
    else:
        bridge_ctx = bridge_factory(
            gateway_url,
            api_key,
            model_name=selected_model,
            advertised_models=advertised,
        )

    with bridge_ctx as bridge:
        headers = {
            "Authorization": f"Bearer {bridge['api_key']}",
            "User-Agent": "codex_cli_rs/0.116.0",
            "originator": "codex_cli_rs",
            "openai-beta": "responses=v1",
            "x-session-id": f"smoke-{provider_id}-{int(time.time())}",
        }
        models_resp = httpx.get(f"{bridge['base_url']}/v1/models", headers=headers, timeout=20)
        preview = []
        with httpx.stream(
            "POST",
            f"{bridge['base_url']}/v1/responses",
            headers=headers,
            json={
                "model": selected_model,
                "instructions": "Reply with OK only.",
                "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
                "stream": True,
            },
            timeout=timeout,
        ) as resp:
            content_type = resp.headers.get("content-type", "")
            for line in resp.iter_lines():
                if line:
                    preview.append(line)
                if len(preview) >= max_preview_lines:
                    break
            ok = models_resp.status_code == 200 and resp.status_code == 200 and "text/event-stream" in content_type.lower()
            detail = f"bridge_models={models_resp.status_code} stream={resp.status_code} content_type={content_type}"
            return _result(provider_id, "codex", ok, route, selected_model, str(resp.status_code), detail, preview=preview)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog=os.environ.get("MMS_SUBCOMMAND_PROG") or None,
        description="Minimal CLI smoke for MMS providers.",
    )
    parser.add_argument("--provider", action="append", help="Provider id to test. Repeatable. Default: all enabled providers.")
    parser.add_argument("--cli", action="append", choices=["claude", "codex"], help="CLI to test. Repeatable. Default: claude + codex.")
    parser.add_argument("--model", help="Override model for all selected checks.")
    parser.add_argument("--timeout", type=int, default=90, help="HTTP timeout for the smoke request.")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    args = parser.parse_args()

    cfg = load_config()
    if cfg is None:
        print(json.dumps({"error": "未找到配置"}, ensure_ascii=False))
        return 1
    cfg = apply_local_overrides(cfg)

    provider_defs = _provider_map(cfg)
    provider_ids = args.provider or [pid for pid, item in provider_defs.items() if item.get("enabled", True)]
    clis = args.cli or ["claude", "codex"]

    results: list[dict[str, Any]] = []
    for provider_id in provider_ids:
        provider_def = provider_defs.get(provider_id)
        if not provider_def:
            results.append(_result(provider_id, "-", False, "missing", "", "missing_provider", "provider not found"))
            continue
        runtime = resolve_provider_context(cfg, provider_id)
        supported = set(runtime.get("supported_clis") or [])
        for cli in clis:
            if supported and cli not in supported:
                results.append(_result(provider_id, cli, True, "skip", "", "skipped", "provider 未声明支持该 CLI"))
                continue
            if cli == "claude":
                results.append(_smoke_claude(runtime, model=args.model or "", timeout=min(args.timeout, 60)))
            elif cli == "codex":
                results.append(_smoke_codex(runtime, model=args.model or "", timeout=args.timeout))

    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            prefix = "PASS" if item["ok"] else "FAIL"
            print(f"[{prefix}] {item['provider']} {item['cli']} route={item['route']} model={item['model']} status={item['status']}")
            print(f"       {item['detail']}")
            if item.get("preview"):
                preview = item["preview"]
                if not isinstance(preview, str):
                    preview = json.dumps(preview, ensure_ascii=False)
                print(f"       preview={_trim(preview)}")

    failing = [item for item in results if not item["ok"]]
    return 0 if not failing else 2


if __name__ == "__main__":
    sys.exit(main())
