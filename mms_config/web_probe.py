# -*- coding: utf-8 -*-
"""Provider probing and model smoke helpers for the MMS config WebUI."""

from __future__ import annotations

import json
import re
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


def _sanitize_for_output(value: Any) -> Any:
    return _call_backend("_sanitize_for_output", value)


def _redact_inline_secrets(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer ***", text)
    text = re.sub(r"\b(?:sk|sk-or-v1|sk-ant|ak)-[A-Za-z0-9._-]{12,}\b", "***", text)
    return text


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


def _response_json_and_text(response: Any) -> tuple[Any, str]:
    try:
        data = response.json()
    except Exception:
        data = None
    text = _safe_text(getattr(response, "text", ""))
    if not text and data is not None:
        try:
            text = json.dumps(_sanitize_for_output(data), ensure_ascii=False)
        except Exception:
            text = str(data)
    return data, _redact_inline_secrets(text)


def _model_smoke_error_preview(data: Any, text: str) -> str:
    candidates: list[str] = []
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            for key in ("message", "detail", "code", "type"):
                value = _safe_text(error.get(key))
                if value:
                    candidates.append(value)
        elif error:
            candidates.append(_safe_text(error))
        for key in ("message", "detail", "error_description"):
            value = _safe_text(data.get(key))
            if value:
                candidates.append(value)
        if not candidates:
            try:
                candidates.append(json.dumps(_sanitize_for_output(data), ensure_ascii=False))
            except Exception:
                candidates.append(str(data))
    if not candidates and text:
        candidates.append(text)
    return _redact_inline_secrets(" · ".join(item for item in candidates if item))[:500]


def _model_smoke_diagnosis(provider: dict[str, Any], model: str, protocol: str, status_code: int) -> str:
    provider_id = _safe_text(provider.get("id")).lower()
    model_lower = model.lower()
    if (
        status_code == 403
        and provider_id == "openrouter"
        and protocol == "openai_chat_completions"
        and (model_lower.startswith("anthropic/") or "claude" in model_lower)
    ):
        return "OpenRouter 返回 403：模型存在，但当前 key/account 可能没有该 Anthropic/Claude 模型权限，或 OpenRouter route/provider 被限制；当前通道未配置 anthropic_base_url，所以 auto 走的是 /chat/completions。"
    if status_code == 404:
        return "上游返回 404：优先检查 model id 是否是该 provider 当前可用的精确 ID。"
    if status_code == 401:
        return "上游返回 401：优先检查 API Key 是否正确、是否已保存到当前预览配置。"
    return ""


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
            data, response_text = _response_json_and_text(response)
            content = data.get("content") if isinstance(data, dict) else None
            preview = ""
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict):
                    preview = _safe_text(first.get("text"))
            preview = preview or _safe_text(data.get("text") if isinstance(data, dict) else "")
            error_preview = "" if 200 <= status_code < 300 else _model_smoke_error_preview(data, response_text)
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
            data, response_text = _response_json_and_text(response)
            choices = data.get("choices") if isinstance(data, dict) else None
            preview = ""
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else {}
                if isinstance(message, dict):
                    preview = _safe_text(message.get("content"))
            error_preview = "" if 200 <= status_code < 300 else _model_smoke_error_preview(data, response_text)
            request_path = "/chat/completions"
        latency_ms = int((time.time() - started) * 1000)
        ok = 200 <= status_code < 300
        diagnosis = "" if ok else _model_smoke_diagnosis(provider, model, protocol, status_code)
        return {
            "ok": ok,
            "status_code": status_code,
            "provider_id": provider.get("id"),
            "model": model,
            "protocol": protocol,
            "latency_ms": latency_ms,
            "response_preview": (preview or error_preview)[:500],
            "error": "" if ok else error_preview,
            "diagnosis": diagnosis,
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
