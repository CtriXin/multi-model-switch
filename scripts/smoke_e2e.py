#!/usr/bin/env python3
"""MMS 端到端 smoke test — 测试完整 bridge 链路。

每个 provider 自动识别支持的模型类型（Claude/GPT/国产），
每种类型挑一个代表模型，走完整的 bridge 路径验证：
  - Claude 路径: gateway_claude_bridge → Anthropic Messages
  - GPT-on-Claude 路径: gateway_claude_bridge (openai_url) → Responses API → Anthropic SSE
  - Codex GPT 路径: codex_responses_bridge → Responses API
  - Codex 国产路径: codex_chatcompletions_bridge → Chat Completions
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import httpx

from mms_bridge import (
    codex_chatcompletions_bridge,
    codex_responses_bridge,
    gateway_claude_bridge,
)
from mms_core import (
    _probe_models,
    _provider_map,
    apply_local_overrides,
    load_config,
    resolve_provider_context,
)
from mms_launchers import _is_gpt_model, _openai_base_url, _resolve_anthropic_base_url

TIMEOUT = 30

# ── 模型分类 ──

_CLAUDE_KW = ("claude", "opus", "sonnet", "haiku")
_GPT_PREFIXES = ("gpt-", "o1-", "o3-", "o4-", "codex-")


def _classify(model: str) -> str:
    lower = model.lower()
    if any(k in lower for k in _CLAUDE_KW):
        return "claude"
    if lower.startswith(_GPT_PREFIXES):
        return "gpt"
    return "domestic"


def _pick_one(models: list[str], category: str) -> str | None:
    """每个类别挑一个代表模型。"""
    preferred = {
        "claude": ["claude-sonnet-4-6", "claude-opus-4-6"],
        "gpt": ["gpt-5.4", "gpt-5", "gpt-5-codex"],
        "domestic": [],  # 取第一个
    }
    candidates = [m for m in models if _classify(m) == category]
    if not candidates:
        return None
    for pref in preferred.get(category, []):
        if pref in candidates:
            return pref
    return candidates[0]


# ── Anthropic Messages 请求 ──

def _anthropic_request(base_url: str, api_key: str, model: str) -> tuple[bool, int, str]:
    """发 Anthropic Messages 请求，返回 (ok, status, detail)。"""
    headers = {
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "x-api-key": api_key,
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "max_tokens": 16,
        "messages": [{"role": "user", "content": "Reply OK only."}],
    }
    t0 = time.monotonic()
    resp = httpx.post(f"{base_url}/v1/messages", headers=headers, json=payload, timeout=TIMEOUT)
    dt = time.monotonic() - t0
    if resp.status_code == 200:
        try:
            body = resp.json()
            text = ""
            for c in body.get("content", []):
                if c.get("type") == "text":
                    text = c.get("text", "")[:60]
                    break
            return True, 200, f'{dt:.1f}s "{text}"'
        except Exception:
            return True, 200, f"{dt:.1f}s (parse error)"
    return False, resp.status_code, resp.text[:120]


# ── Codex Responses 请求 ──

def _responses_request(base_url: str, api_key: str, model: str) -> tuple[bool, int, str]:
    """发 OpenAI Responses 请求（流式），返回 (ok, status, detail)。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "codex_cli_rs/0.38.0",
        "originator": "codex_cli_rs",
        "openai-beta": "responses=v1",
    }
    payload = {
        "model": model,
        "instructions": "Reply OK only.",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
        "stream": True,
    }
    t0 = time.monotonic()
    try:
        with httpx.stream("POST", f"{base_url}/v1/responses", headers=headers, json=payload, timeout=TIMEOUT) as resp:
            ct = resp.headers.get("content-type", "")
            lines = []
            for line in resp.iter_lines():
                if line:
                    lines.append(line)
                if len(lines) >= 5:
                    break
            dt = time.monotonic() - t0
            ok = resp.status_code == 200 and "text/event-stream" in ct.lower()
            return ok, resp.status_code, f'{dt:.1f}s ct={ct[:30]} lines={len(lines)}'
    except Exception as e:
        return False, 0, str(e)[:120]


# ── 测试入口 ──

def smoke_provider_claude(ctx: dict, models: list[str], pid: str) -> list[dict]:
    """测试一个 provider 在 Claude Code 路径下的所有模型类型。"""
    results = []
    anthropic_url = (ctx.get("anthropic_base_url") or "").rstrip("/")
    openai_url = _openai_base_url(ctx) or None
    api_key = ctx.get("api_key", "")

    for cat in ("claude", "gpt", "domestic"):
        model = _pick_one(models, cat)
        if not model:
            continue

        if cat == "claude":
            # Claude 模型：直连或 bridge 走 Anthropic Messages
            if anthropic_url:
                # 通过 bridge 测，模拟真实链路
                try:
                    with gateway_claude_bridge(
                        anthropic_url + "/v1" if not anthropic_url.endswith("/v1") else anthropic_url,
                        api_key, heavy_model=model, advertised_models=models
                    ) as bridge:
                        ok, status, detail = _anthropic_request(bridge["base_url"], bridge["api_key"], model)
                        results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
                except Exception as e:
                    results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})
            else:
                results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": "no anthropic_url"})

        elif cat == "gpt":
            # GPT 模型：必须走 bridge 的 _forward_as_responses
            if openai_url and anthropic_url:
                try:
                    gw_url = anthropic_url + "/v1" if not anthropic_url.endswith("/v1") else anthropic_url
                    with gateway_claude_bridge(
                        gw_url, api_key, heavy_model=model,
                        advertised_models=models, openai_url=openai_url
                    ) as bridge:
                        ok, status, detail = _anthropic_request(bridge["base_url"], bridge["api_key"], model)
                        results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
                except Exception as e:
                    results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})
            elif openai_url:
                # 只有 openai_url，尝试走 bridge
                try:
                    with gateway_claude_bridge(
                        openai_url, api_key, heavy_model=model,
                        advertised_models=models, openai_url=openai_url
                    ) as bridge:
                        ok, status, detail = _anthropic_request(bridge["base_url"], bridge["api_key"], model)
                        results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
                except Exception as e:
                    results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})
            else:
                results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": "no openai_url for GPT"})

        elif cat == "domestic":
            # 国产模型：走 bridge Anthropic Messages（gateway 转格式）
            if anthropic_url:
                try:
                    gw_url = anthropic_url + "/v1" if not anthropic_url.endswith("/v1") else anthropic_url
                    with gateway_claude_bridge(
                        gw_url, api_key, heavy_model=model, advertised_models=models
                    ) as bridge:
                        ok, status, detail = _anthropic_request(bridge["base_url"], bridge["api_key"], model)
                        results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
                except Exception as e:
                    results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})
            else:
                results.append({"pid": pid, "cli": "claude", "cat": cat, "model": model, "ok": False, "status": 0, "detail": "no anthropic_url"})

    return results


def smoke_provider_codex(ctx: dict, models: list[str], pid: str) -> list[dict]:
    """测试一个 provider 在 Codex 路径下的模型类型。"""
    results = []
    openai_url = _openai_base_url(ctx) or None
    api_key = ctx.get("openai_api_key") or ctx.get("api_key", "")

    if not openai_url:
        return results  # 没有 openai_url 就不测 codex

    for cat in ("gpt", "domestic"):
        model = _pick_one(models, cat)
        if not model:
            continue

        if cat == "gpt":
            # GPT: codex_responses_bridge
            try:
                with codex_responses_bridge(
                    openai_url, api_key, model_name=model,
                    advertised_models=models, provider_id=pid
                ) as bridge:
                    ok, status, detail = _responses_request(bridge["base_url"], bridge["api_key"], model)
                    results.append({"pid": pid, "cli": "codex", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
            except Exception as e:
                results.append({"pid": pid, "cli": "codex", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})

        elif cat == "domestic":
            # 国产: codex_chatcompletions_bridge
            try:
                with codex_chatcompletions_bridge(
                    openai_url, api_key, model_name=model, advertised_models=models
                ) as bridge:
                    ok, status, detail = _responses_request(bridge["base_url"], bridge["api_key"], model)
                    results.append({"pid": pid, "cli": "codex", "cat": cat, "model": model, "ok": ok, "status": status, "detail": detail})
            except Exception as e:
                results.append({"pid": pid, "cli": "codex", "cat": cat, "model": model, "ok": False, "status": 0, "detail": f"bridge error: {e}"})

    return results


def main():
    cfg = load_config()
    if cfg is None:
        print("❌ 未找到配置")
        return 1
    cfg = apply_local_overrides(cfg)
    provider_defs = _provider_map(cfg)

    all_results = []
    for pid, pdef in provider_defs.items():
        if not pdef.get("enabled", True):
            continue
        ctx = resolve_provider_context(cfg, pid)
        models = _probe_models(ctx, emit_output=False).get("models") or []
        if not models:
            continue

        # Claude Code 路径
        all_results.extend(smoke_provider_claude(ctx, models, pid))
        # Codex 路径
        all_results.extend(smoke_provider_codex(ctx, models, pid))

    # 输出
    passed = [r for r in all_results if r["ok"]]
    failed = [r for r in all_results if not r["ok"]]

    print(f"\n{'='*70}")
    print(f"  MMS E2E Smoke Test — {len(passed)} passed, {len(failed)} failed")
    print(f"{'='*70}\n")

    for r in all_results:
        icon = "✅" if r["ok"] else "❌"
        print(f"  {icon} {r['pid']:20s} {r['cli']:6s} {r['cat']:8s} {r['model']:28s} {r['detail']}")

    if failed:
        print(f"\n  ⚠️  {len(failed)} 项失败")
    else:
        print(f"\n  🎉 全部通过!")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
