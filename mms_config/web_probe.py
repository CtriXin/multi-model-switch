# -*- coding: utf-8 -*-
"""Provider probing and model smoke helpers for the MMS config WebUI."""

from __future__ import annotations

import time
import traceback
from typing import Any


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _backend_web_wrapper(name: str) -> bool:
    func = getattr(_backend(), name, None)
    return callable(func) and getattr(func, "__module__", "") == "mms_config.web" and getattr(func, "__name__", "") == name


def _call_backend_override(name: str, default: Any, *args: Any, **kwargs: Any) -> Any:
    func = getattr(_backend(), name, None)
    if callable(func) and not _backend_web_wrapper(name):
        return func(*args, **kwargs)
    return default(*args, **kwargs)


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _normalize_choice_list(value: Any, allowed: Any, default: Any) -> list[str]:
    return _call_backend("_normalize_choice_list", value, allowed, default)


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _hydrate_preview_config_from_latest_bundle(current_cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_hydrate_preview_config_from_latest_bundle", current_cfg, config_path=config_path, command_name=command_name)


def _resolve_preview_provider_secret(provider: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_resolve_preview_provider_secret", provider, config_path=config_path, command_name=command_name)


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend("_policy_path_for_config", config_path)


def _model_capability_defaults(model_id: str, policy: dict[str, Any] | None = None, *, provider_id: str = "") -> dict[str, Any]:
    return _call_backend("_model_capability_defaults", model_id, policy, provider_id=provider_id)


def _allowed_protocols() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_PROTOCOLS"))


def _provider_from_payload(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    provider_payload = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    provider_id = _safe_text(payload.get("provider_id") or provider_payload.get("id"))
    provider = dict(provider_payload)
    cfg = _hydrate_preview_config_from_latest_bundle(cfg, config_path=config_path, command_name=command_name)
    cfg_provider_ids = {
        _safe_text(item.get("id"))
        for item in (cfg.get("providers", []) if isinstance(cfg, dict) else [])
        if isinstance(item, dict)
    }
    if provider_id and provider_id in cfg_provider_ids:
        try:
            mms_core = _load_mms_core()
            resolved = mms_core.resolve_provider_context(cfg, provider_id)
            if isinstance(resolved, dict):
                merged = dict(resolved)
                merged.update({key: value for key, value in provider.items() if value not in (None, "")})
                provider = merged
        except BaseException:
            for item in cfg.get("providers", []) or []:
                if isinstance(item, dict) and item.get("id") == provider_id:
                    base = dict(item)
                    base.update({key: value for key, value in provider.items() if value not in (None, "")})
                    provider = base
                    break
    provider["id"] = _safe_text(provider.get("id") or provider_id or "web-test-provider")
    provider["protocols"] = _normalize_choice_list(provider.get("protocols"), _allowed_protocols(), _allowed_protocols())
    if provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("openai_base_url")).rstrip("/")
    if provider.get("anthropic_base_url"):
        provider["anthropic_base_url"] = _safe_text(provider.get("anthropic_base_url")).rstrip("/")
    if provider.get("base_url") and not provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("base_url")).rstrip("/")
    return _resolve_preview_provider_secret(provider, config_path=config_path, command_name=command_name)


def _probe_provider_models_impl(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    mms_core = _load_mms_core()
    return mms_core._probe_models(provider, emit_output=False, force_refresh=force_refresh)  # noqa: SLF001


def test_provider_models(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    provider = _provider_from_payload(cfg, payload, config_path=config_path, command_name=command_name)
    started = time.time()
    try:
        probe = _call_backend_override("probe_provider_models", _probe_provider_models_impl, provider, force_refresh=_truthy(payload.get("force_refresh"), True))
        latency_ms = int((time.time() - started) * 1000)
        models = _normalize_model_list(probe.get("models") or [])
        policy_payload = _load_json_file(_policy_path_for_config(config_path))
        policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
        model_capabilities = {
            model_id: _model_capability_defaults(
                model_id,
                policy_models.get(model_id) if isinstance(policy_models.get(model_id), dict) else {},
                provider_id=_safe_text(provider.get("id")),
            )
            for model_id in models
        }
        return {
            "ok": not bool(probe.get("error")),
            "provider_id": provider.get("id"),
            "models": models,
            "model_capabilities": model_capabilities,
            "raw_models": _normalize_model_list(probe.get("raw_models") or models),
            "model_count": len(models),
            "base_source": probe.get("base_source") or "remote",
            "working_url": probe.get("working_url") or "",
            "error": probe.get("error") or "",
            "error_kind": probe.get("error_kind") or "",
            "latency_ms": latency_ms,
            "details": probe.get("details") or [],
            "cache_transport_evidence": {
                "schema": "cache_transport_evidence.v1",
                "provider_id": provider.get("id"),
                "request_url": probe.get("working_url") or provider.get("openai_base_url") or provider.get("anthropic_base_url") or "",
                "request_path": provider.get("models_endpoint") or "/models",
                "protocol": "openai_chat_completions" if "openai_chat_completions" in provider.get("protocols", []) else "anthropic_messages",
            },
        }
    except Exception as exc:
        return {"ok": False, "provider_id": provider.get("id"), "models": [], "error": str(exc), "trace": traceback.format_exc(limit=3)}


def _join_openai_chat_url(base_url: str) -> str:
    base = _safe_text(base_url).rstrip("/")
    if not base:
        return ""
    return base + "/chat/completions"


def _join_anthropic_messages_url(base_url: str) -> str:
    base = _safe_text(base_url).rstrip("/")
    if not base:
        return ""
    return base + ("/messages" if base.endswith("/v1") else "/v1/messages")


def run_model_smoke(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    chat: bool = False,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    provider = _provider_from_payload(cfg, payload, config_path=config_path, command_name=command_name)
    model = _safe_text(payload.get("model") or payload.get("model_id"))
    if not model:
        return {"ok": False, "error": "请选择要测试的模型。"}
    protocol = _safe_text(payload.get("protocol") or "auto")
    if protocol == "auto":
        protocol = "anthropic_messages" if "anthropic_messages" in provider.get("protocols", []) and provider.get("anthropic_base_url") else "openai_chat_completions"
    prompt = _safe_text(payload.get("prompt")) or ("用中文简短回复 pong" if chat else "只回复 pong")
    started = time.time()
    try:
        mms_core = _load_mms_core()
        if protocol == "anthropic_messages":
            api_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key"))
            url = _join_anthropic_messages_url(provider.get("anthropic_base_url") or provider.get("base_url"))
            if not url or not api_key:
                return {"ok": False, "error": "Anthropic 测试缺少 anthropic_base_url 或 API Key。"}
            body = {
                "model": model,
                "max_tokens": 64 if chat else 8,
                "messages": [{"role": "user", "content": prompt}],
            }
            response = mms_core._runtime_httpx_request(  # noqa: SLF001
                "POST",
                url,
                runtime=provider,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            data = response.json()
            content = data.get("content") if isinstance(data, dict) else None
            preview = ""
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    preview = _safe_text(first.get("text"))
            preview = preview or _safe_text(data.get("text") if isinstance(data, dict) else "")
            request_path = "/v1/messages" if "/v1/messages" in url else "/messages"
        else:
            api_key = _safe_text(provider.get("openai_api_key") or provider.get("api_key"))
            url = _join_openai_chat_url(provider.get("openai_base_url") or provider.get("base_url"))
            if not url or not api_key:
                return {"ok": False, "error": "OpenAI 测试缺少 openai_base_url 或 API Key。"}
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64 if chat else 8,
                "temperature": 0,
            }
            response = mms_core._runtime_httpx_request(  # noqa: SLF001
                "POST",
                url,
                runtime=provider,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=30,
            )
            status_code = int(getattr(response, "status_code", 0) or 0)
            data = response.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            preview = ""
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else {}
                if isinstance(message, dict):
                    preview = _safe_text(message.get("content"))
            request_path = "/chat/completions"
        latency_ms = int((time.time() - started) * 1000)
        return {
            "ok": 200 <= status_code < 300,
            "status_code": status_code,
            "provider_id": provider.get("id"),
            "model": model,
            "protocol": protocol,
            "latency_ms": latency_ms,
            "response_preview": preview[:500],
            "cache_transport_evidence": {
                "schema": "cache_transport_evidence.v1",
                "provider_id": provider.get("id"),
                "model": model,
                "protocol": protocol,
                "request_url": url,
                "request_path": request_path,
                "latency_ms": latency_ms,
            },
        }
    except Exception as exc:
        return {"ok": False, "provider_id": provider.get("id"), "model": model, "protocol": protocol, "error": str(exc), "trace": traceback.format_exc(limit=3)}


def probe_provider_models(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    return _probe_provider_models_impl(provider, force_refresh=force_refresh)
