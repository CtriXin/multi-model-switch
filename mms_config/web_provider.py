# -*- coding: utf-8 -*-
"""Provider draft and review helpers for the MMS config WebUI."""

from __future__ import annotations

import json
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


def _slug(value: Any, default: str = "provider") -> str:
    return _call_backend("_slug", value, default)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _normalize_choice_list(value: Any, allowed: tuple[str, ...], default: tuple[str, ...]) -> list[str]:
    return _call_backend("_normalize_choice_list", value, allowed, default)


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _normalize_priority(value: Any, default: int = 100) -> int:
    return _call_backend("_normalize_priority", value, default)


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    return _call_backend("_normalize_family_priority_overrides", value)


def _sanitize_for_output(value: Any) -> Any:
    return _call_backend("_sanitize_for_output", value)


def _allowed_protocols() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_PROTOCOLS"))


def _allowed_clis() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_CLIS"))


def _allowed_roles() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_ALLOWED_ROLES"))


def _extract_draft_impl(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
    return draft if isinstance(draft, dict) else {}


def _route_model_rows_from_payload_impl(provider_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in provider_payload.get("models") if isinstance(provider_payload.get("models"), list) else []:
        if isinstance(item, dict):
            model_id = _safe_text(item.get("id") or item.get("model"))
            visible = item.get("visible") is not False
        else:
            model_id = _safe_text(item)
            visible = True
        if not model_id or model_id in seen or not visible:
            continue
        seen.add(model_id)
        rows.append({"id": model_id, "visible": True})
    return rows


def _copy_existing_provider_impl(
    existing: dict[str, Any] | None,
    provider_payload: dict[str, Any],
    *,
    preserve_model_rows: bool = False,
    force_model_rows: bool = False,
    clear_fallback_models: bool = False,
) -> dict[str, Any]:
    provider = dict(existing or {})
    provider_id = _slug(provider_payload.get("id") or provider_payload.get("original_id") or provider.get("id"), "provider")
    provider["id"] = provider_id
    provider["name"] = _safe_text(provider_payload.get("name") or provider_id)
    provider["enabled"] = _truthy(provider_payload.get("enabled"), True)
    role = _safe_text(provider_payload.get("role") or provider.get("role") or "auto").lower()
    provider["role"] = role if role in _allowed_roles() else "auto"
    provider["priority"] = _normalize_priority(provider_payload.get("priority", provider.get("priority", 100)))
    if "family_priority_overrides" in provider_payload:
        overrides = _normalize_family_priority_overrides(provider_payload.get("family_priority_overrides"))
        if overrides:
            provider["family_priority_overrides"] = overrides
        else:
            provider.pop("family_priority_overrides", None)
    if "claude_1m_mode" in provider_payload:
        mode = _safe_text(provider_payload.get("claude_1m_mode") or "auto")
        normalized = mode if mode in {"auto", "enable", "disable"} else "auto"
        if normalized != "auto" or "claude_1m_mode" in provider:
            provider["claude_1m_mode"] = normalized
        else:
            provider.pop("claude_1m_mode", None)
    if "timezone" in provider_payload:
        timezone_name = _safe_text(provider_payload.get("timezone"))
        if timezone_name:
            provider["timezone"] = timezone_name
        else:
            provider.pop("timezone", None)
    if "note" in provider_payload:
        note = _safe_text(provider_payload.get("note"))
        if note:
            provider["note"] = note
        elif "note" in provider:
            provider["note"] = ""
        else:
            provider.pop("note", None)
    provider["protocols"] = _normalize_choice_list(provider_payload.get("protocols"), _allowed_protocols(), _allowed_protocols())
    provider["supported_clis"] = _normalize_choice_list(provider_payload.get("supported_clis"), _allowed_clis(), ("claude", "codex", "opencode"))
    endpoint = _safe_text(provider_payload.get("models_endpoint") or provider.get("models_endpoint") or "/models")
    if endpoint.lower() in {"manual", "none", "off"}:
        endpoint = "manual"
    elif endpoint and not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    provider["models_endpoint"] = endpoint or "/models"
    if "openai_base_url" in provider_payload or "base_url" in provider_payload:
        openai_base = _safe_text(provider_payload.get("openai_base_url") or provider_payload.get("base_url"))
        if (
            _safe_text(provider_payload.get("openai_base_url_source")) == "credentials"
            and not _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url"))
            and openai_base == _safe_text(provider_payload.get("effective_openai_base_url"))
        ):
            openai_base = ""
    else:
        openai_base = _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url"))
    if "anthropic_base_url" in provider_payload:
        anthropic_base = _safe_text(provider_payload.get("anthropic_base_url"))
        if (
            _safe_text(provider_payload.get("anthropic_base_url_source")) == "credentials"
            and not _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
            and anthropic_base == _safe_text(provider_payload.get("effective_anthropic_base_url"))
        ):
            anthropic_base = ""
    else:
        anthropic_base = _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
    if openai_base:
        provider["default_openai_base_url"] = openai_base.rstrip("/")
    elif "default_openai_base_url" in provider:
        provider["default_openai_base_url"] = ""
    else:
        provider.pop("default_openai_base_url", None)
    if anthropic_base:
        provider["default_anthropic_base_url"] = anthropic_base.rstrip("/")
    elif "default_anthropic_base_url" in provider:
        provider["default_anthropic_base_url"] = ""
    else:
        provider.pop("default_anthropic_base_url", None)
    provider["fallback_models"] = [] if clear_fallback_models else _normalize_model_list(provider_payload.get("fallback_models"))
    provider["extra_models"] = _normalize_model_list(provider_payload.get("extra_models"))
    provider["hidden_models"] = _normalize_model_list(provider_payload.get("hidden_models"))
    if preserve_model_rows:
        route_rows = _route_model_rows_from_payload(provider_payload)
        configured_model_ids = set(provider["fallback_models"]) | set(provider["extra_models"])
        has_route_only_rows = any(row["id"] not in configured_model_ids for row in route_rows)
        existing_has_models = isinstance(provider.get("models"), list)
        if route_rows and (force_model_rows or has_route_only_rows or existing_has_models):
            provider["models"] = route_rows
        elif force_model_rows or existing_has_models:
            provider.pop("models", None)
    return provider


def _strip_implicit_provider_timezone_defaults_impl(
    next_cfg: dict[str, Any],
    providers_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    payload_by_id: dict[str, dict[str, Any]] = {}
    for payload in providers_payload:
        if not isinstance(payload, dict):
            continue
        for key in (_safe_text(payload.get("id")), _safe_text(payload.get("original_id"))):
            if key:
                payload_by_id[key] = payload
    for provider in next_cfg.get("providers") if isinstance(next_cfg.get("providers"), list) else []:
        if not isinstance(provider, dict):
            continue
        payload = payload_by_id.get(_safe_text(provider.get("id")))
        if not payload or "timezone" not in payload:
            continue
        # mms_core normalization materializes Asia/Singapore as the implicit
        # default. Keep it out of persisted WebUI drafts unless the user typed it.
        if not _safe_text(payload.get("timezone")):
            provider.pop("timezone", None)
    return next_cfg


def _provider_urls_impl(provider: dict[str, Any] | None) -> dict[str, str]:
    provider = provider if isinstance(provider, dict) else {}
    return {
        "openai": _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url")),
        "anthropic": _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url")),
    }


def _provider_by_id_impl(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    return {
        _safe_text(provider.get("id")): provider
        for provider in providers
        if isinstance(provider, dict) and _safe_text(provider.get("id"))
    }


def _provider_default_id_impl(cfg: dict[str, Any]) -> str:
    provider_cfg = cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}
    return _safe_text(provider_cfg.get("default"))


def _mapping_digest_impl(payload: Any) -> str:
    return json.dumps(_sanitize_for_output(payload if isinstance(payload, dict) else {}), ensure_ascii=False, sort_keys=True)


def _extract_draft(payload: dict[str, Any]) -> dict[str, Any]:
    return _call_backend_override("_extract_draft", _extract_draft_impl, payload)


def _route_model_rows_from_payload(provider_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return _call_backend_override("_route_model_rows_from_payload", _route_model_rows_from_payload_impl, provider_payload)


def _copy_existing_provider(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend_override("_copy_existing_provider", _copy_existing_provider_impl, *args, **kwargs)


def _strip_implicit_provider_timezone_defaults(
    next_cfg: dict[str, Any],
    providers_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    return _call_backend_override("_strip_implicit_provider_timezone_defaults", _strip_implicit_provider_timezone_defaults_impl, next_cfg, providers_payload)


def _provider_urls(provider: dict[str, Any] | None) -> dict[str, str]:
    return _call_backend_override("_provider_urls", _provider_urls_impl, provider)


def _provider_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return _call_backend_override("_provider_by_id", _provider_by_id_impl, cfg)


def _provider_default_id(cfg: dict[str, Any]) -> str:
    return _call_backend_override("_provider_default_id", _provider_default_id_impl, cfg)


def _mapping_digest(payload: Any) -> str:
    return _call_backend_override("_mapping_digest", _mapping_digest_impl, payload)

