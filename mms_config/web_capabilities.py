# -*- coding: utf-8 -*-
"""Capability truth and OpenRouter catalog helpers for the MMS config WebUI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


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


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _normalize_context_tokens(value: Any) -> int | None:
    return _call_backend("_normalize_context_tokens", value)


def _canonical_family_name(model_id: str) -> str:
    return _call_backend("_canonical_family_name", model_id)


def _now_iso() -> str:
    return _call_backend("_now_iso")


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _call_backend("_config_root_for_snapshot", config_path)


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _provider_from_payload(cfg: dict[str, Any], payload: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    return _call_backend("_provider_from_payload", cfg, payload, config_path=config_path, command_name=command_name)


def _known_vision_models() -> set[str]:
    return set(getattr(_backend(), "_KNOWN_VISION_MODELS"))


def _cache_sensitive_prefixes() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_CACHE_SENSITIVE_PREFIXES"))


def _reasoning_hints() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_REASONING_HINTS"))


def _capability_truth_refresh_fields_const() -> tuple[str, ...]:
    return tuple(getattr(_backend(), "_CAPABILITY_TRUTH_REFRESH_FIELDS"))


def _openrouter_models_api_url() -> str:
    return str(getattr(_backend(), "_OPENROUTER_MODELS_API_URL"))


def _model_capability_defaults(
    model_id: str,
    policy_entry: dict[str, Any] | None = None,
    *,
    provider_id: str = "",
) -> dict[str, Any]:
    model = _safe_text(model_id)
    lower = model.lower().rsplit("/", 1)[-1]
    caps = {
        "text": True,
        "vision": lower in _known_vision_models() or lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-")),
        "tool_use": lower.startswith(("claude-", "gpt-", "o", "qwen", "kimi", "glm", "minimax", "mimo", "gemini-")),
        "reasoning": any(hint in lower for hint in _reasoning_hints()),
        "thinking": lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max", "kimi", "k2.", "glm", "deepseek", "minimax")),
        "long_context": "1m" in lower or "long" in lower or lower.startswith(("qwen3", "kimi-k2", "gpt-5", "claude-", "mimo-v2.5", "minimax-m3")),
        "cache_sensitive": lower.startswith(_cache_sensitive_prefixes()),
    }
    try:
        from mms_registry.capability_resolver import resolve_model_capabilities

        resolved = resolve_model_capabilities(model, provider_id=provider_id)
        if resolved.get("supports_thinking") is True:
            caps["thinking"] = True
            caps["reasoning"] = True
        context_window = int(resolved.get("context_window_tokens") or 0)
        if context_window > 0 and resolved.get("sources", {}).get("context_window_tokens") != "conservative_fallback":
            caps["context_window_tokens"] = context_window
        max_output = int(resolved.get("max_output_tokens") or 0)
        if max_output > 0 and resolved.get("sources", {}).get("max_output_tokens") != "conservative_fallback":
            caps["max_output_tokens"] = max_output
        if context_window >= 200_000:
            caps["long_context"] = True
        protocol_hints = resolved.get("protocol_hints") if isinstance(resolved.get("protocol_hints"), dict) else {}
        if protocol_hints.get("cache_sensitive_transport") is True:
            caps["cache_sensitive"] = True
    except Exception:
        pass
    if isinstance(policy_entry, dict):
        policy_caps = policy_entry.get("capabilities") if isinstance(policy_entry.get("capabilities"), dict) else {}
        for key in caps:
            if key in policy_caps and isinstance(policy_caps[key], bool):
                caps[key] = policy_caps[key]
            if key == "thinking" and isinstance(policy_caps.get("supports_thinking"), bool):
                caps[key] = policy_caps["supports_thinking"]
            if key == "cache_sensitive" and isinstance(policy_caps.get("cache_sensitive_transport"), bool):
                caps[key] = policy_caps["cache_sensitive_transport"]
        policy_context = _normalize_context_tokens(
            policy_caps.get("context_window_tokens")
            or policy_caps.get("max_context_tokens")
            or policy_entry.get("context_window_tokens")
            or policy_entry.get("max_context_tokens")
        )
        if not policy_context and policy_caps.get("one_m_context") is True:
            policy_context = 1_000_000
        if policy_context:
            caps["context_window_tokens"] = policy_context
            caps["long_context"] = policy_context >= 200_000
        policy_max_output = _normalize_context_tokens(
            policy_caps.get("max_output_tokens")
            or policy_caps.get("official_max_output_tokens")
            or policy_entry.get("max_output_tokens")
            or policy_entry.get("official_max_output_tokens")
        )
        if policy_max_output:
            caps["max_output_tokens"] = policy_max_output
    return caps


def capability_truth_refresh_fields() -> list[dict[str, str]]:
    """Fields that can be refreshed from structured capability snapshots without LLM prose parsing."""
    labels = {
        "context_window_tokens": ("上下文", "结构化 context window token 数"),
        "max_output_tokens": ("输出上限", "结构化 max output token 数"),
        "vision": ("看图", "supports_vision / input modality"),
        "tool_use": ("工具", "结构化 supported_parameters 包含 tools/tool_choice"),
        "reasoning": ("推理", "supports_thinking 或结构化 reasoning 参数"),
        "thinking": ("Think", "supports_thinking / thinking_control"),
        "one_m_context": ("1M", "one_million_context 或 context >= 1M"),
    }
    return [
        {"key": key, "label": labels[key][0], "description": labels[key][1]}
        for key in _capability_truth_refresh_fields_const()
    ]


def _truth_normalize_model_key(value: Any) -> str:
    text = _safe_text(value).lower()
    if not text:
        return ""
    # MMS used to encode long context in suffixes like [1m]; capability lookup
    # should match the real model id now that context is configured explicitly.
    text = re.sub(r"\[[^\]]+\]$", "", text).strip()
    return text


def _truth_model_index_key(value: Any) -> str:
    text = _truth_normalize_model_key(value)
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text


def _truth_model_index_keys(value: Any) -> list[str]:
    text = _truth_normalize_model_key(value)
    if not text:
        return []
    tail = text.rsplit("/", 1)[-1] if "/" in text else text
    return list(dict.fromkeys([text, tail]))


def _truth_model_ids_from_provider(provider: dict[str, Any]) -> list[str]:
    provider = provider if isinstance(provider, dict) else {}
    result: list[str] = []
    for item in provider.get("models") if isinstance(provider.get("models"), list) else []:
        model_id = _safe_text(item.get("id") or item.get("model")) if isinstance(item, dict) else _safe_text(item)
        if model_id:
            result.append(model_id)
    for key in ("fallback_models", "approved_route_models", "extra_models"):
        result.extend(_normalize_model_list(provider.get(key)))
    seen: set[str] = set()
    deduped: list[str] = []
    for model_id in result:
        key = model_id.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(model_id)
    return deduped


def _truth_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _truth_supported_parameters(row: dict[str, Any]) -> set[str]:
    params: set[str] = set()
    for value in (row.get("provider_supported_parameters"), row.get("supported_parameters")):
        if isinstance(value, list):
            params.update(_safe_text(item).lower() for item in value if _safe_text(item))
    for ref in row.get("provider_catalog_references") if isinstance(row.get("provider_catalog_references"), list) else []:
        if isinstance(ref, dict):
            params.update(_safe_text(item).lower() for item in ref.get("supported_parameters") or [] if _safe_text(item))
    return params


def _truth_first_provider_ref(row: dict[str, Any]) -> dict[str, Any]:
    refs = row.get("provider_catalog_references") if isinstance(row.get("provider_catalog_references"), list) else []
    for ref in refs:
        if isinstance(ref, dict):
            return ref
    return {}


def _truth_evidence_urls(row: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for item in row.get("evidence") if isinstance(row.get("evidence"), list) else []:
        if isinstance(item, dict) and _safe_text(item.get("url")):
            urls.append(_safe_text(item.get("url")))
    for ref in row.get("provider_catalog_references") if isinstance(row.get("provider_catalog_references"), list) else []:
        if isinstance(ref, dict):
            for key in ("source_url", "catalog_url"):
                if _safe_text(ref.get(key)):
                    urls.append(_safe_text(ref.get(key)))
    return list(dict.fromkeys(urls))[:6]


def _truth_field_source(field: str, row: dict[str, Any], source_path: str = "") -> dict[str, Any]:
    confidence = _safe_text(row.get("confidence") or "structured")
    source_layer = _safe_text(row.get("source_layer")).lower()
    source_name = _safe_text(row.get("source_name"))
    checked_at = _safe_text(row.get("checked_at"))
    if not checked_at:
        ref = _truth_first_provider_ref(row)
        checked_at = _safe_text(ref.get("checked_at")) if isinstance(ref, dict) else ""
    layer = source_layer or "official"
    if field == "tool_use" or "provider_catalog" in confidence or "openrouter" in confidence:
        layer = "provider_catalog"
    result = {
        "source_layer": layer,
        "source_name": source_name,
        "confidence": confidence,
        "source_path": source_path,
        "evidence_urls": _truth_evidence_urls(row),
    }
    if checked_at:
        result["checked_at"] = checked_at
    return result


def _truth_caps_from_row(row: dict[str, Any], *, fields: set[str], source_path: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    caps: dict[str, Any] = {}
    sources: dict[str, Any] = {}

    context = _truth_int(row.get("official_context_window_tokens") or row.get("context_window_tokens") or row.get("max_context_tokens"))
    if context is None:
        context = _truth_int(row.get("provider_context_window_tokens") or row.get("provider_top_context_window_tokens"))
    if context is None:
        ref = _truth_first_provider_ref(row)
        top_provider = ref.get("top_provider") if isinstance(ref.get("top_provider"), dict) else {}
        context = _truth_int(ref.get("context_length") or top_provider.get("context_length"))
    if context and "context_window_tokens" in fields:
        caps["context_window_tokens"] = context
        caps["long_context"] = context >= 200_000
        sources["context_window_tokens"] = _truth_field_source("context_window_tokens", row, source_path)
    if context and "one_m_context" in fields:
        caps["one_m_context"] = context >= 1_000_000
        sources["one_m_context"] = _truth_field_source("one_m_context", row, source_path)

    max_output = _truth_int(row.get("official_max_output_tokens") or row.get("max_output_tokens"))
    if max_output is None:
        max_output = _truth_int(row.get("provider_top_max_output_tokens"))
    if max_output is None:
        ref = _truth_first_provider_ref(row)
        top_provider = ref.get("top_provider") if isinstance(ref.get("top_provider"), dict) else {}
        max_output = _truth_int(ref.get("max_completion_tokens") or top_provider.get("max_completion_tokens"))
    if max_output and "max_output_tokens" in fields:
        caps["max_output_tokens"] = max_output
        sources["max_output_tokens"] = _truth_field_source("max_output_tokens", row, source_path)

    if isinstance(row.get("supports_vision"), bool) and "vision" in fields:
        caps["vision"] = bool(row["supports_vision"])
        sources["vision"] = _truth_field_source("vision", row, source_path)
    elif "vision" in fields:
        modalities = row.get("input_modalities") or row.get("modalities") or row.get("official_capabilities")
        if isinstance(modalities, list) and any(_safe_text(item).lower() in {"image", "vision", "multimodal"} for item in modalities):
            caps["vision"] = True
            sources["vision"] = _truth_field_source("vision", row, source_path)

    if isinstance(row.get("supports_thinking"), bool):
        if "thinking" in fields:
            caps["thinking"] = bool(row["supports_thinking"])
            sources["thinking"] = _truth_field_source("thinking", row, source_path)
        if "reasoning" in fields:
            caps["reasoning"] = bool(row["supports_thinking"])
            sources["reasoning"] = _truth_field_source("reasoning", row, source_path)

    params = _truth_supported_parameters(row)
    if "tool_use" in fields and {"tools", "tool_choice", "parallel_tool_calls"}.intersection(params):
        caps["tool_use"] = True
        sources["tool_use"] = _truth_field_source("tool_use", row, source_path)
    if "reasoning" in fields and {"reasoning", "reasoning_effort", "include_reasoning"}.intersection(params):
        caps["reasoning"] = True
        sources["reasoning"] = _truth_field_source("reasoning", row, source_path)

    if isinstance(row.get("one_million_context"), bool) and "one_m_context" in fields:
        caps["one_m_context"] = bool(row["one_million_context"])
        if row["one_million_context"] is True and "context_window_tokens" in fields and not caps.get("context_window_tokens"):
            caps["context_window_tokens"] = 1_000_000
            caps["long_context"] = True
            sources["context_window_tokens"] = _truth_field_source("context_window_tokens", row, source_path)
        sources["one_m_context"] = _truth_field_source("one_m_context", row, source_path)

    return caps, sources


def _openrouter_model_page_url(model_id: str) -> str:
    model = _safe_text(model_id).strip("/")
    return f"https://openrouter.ai/{model}" if model else "https://openrouter.ai/models"


def _openrouter_catalog_to_truth_payload(
    payload: dict[str, Any],
    *,
    source_path: str = "",
    checked_at: str = "",
) -> dict[str, Any]:
    """Convert OpenRouter /models records into the same structured snapshot shape."""
    source_path = source_path or _openrouter_models_api_url()
    checked = checked_at or _now_iso()
    rows: list[dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = _safe_text(item.get("id"))
        if not model_id:
            continue
        architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
        top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
        pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        params = [_safe_text(value) for value in item.get("supported_parameters") or [] if _safe_text(value)] if isinstance(item.get("supported_parameters"), list) else []
        input_modalities = [_safe_text(value) for value in architecture.get("input_modalities") or [] if _safe_text(value)] if isinstance(architecture.get("input_modalities"), list) else []
        output_modalities = [_safe_text(value) for value in architecture.get("output_modalities") or [] if _safe_text(value)] if isinstance(architecture.get("output_modalities"), list) else []
        catalog_ref = {
            "source": "openrouter",
            "model_id": model_id,
            "source_url": source_path,
            "catalog_url": _openrouter_model_page_url(model_id),
            "context_length": item.get("context_length"),
            "max_completion_tokens": top_provider.get("max_completion_tokens"),
            "top_provider": top_provider,
            "architecture": architecture,
            "input_modalities": input_modalities,
            "output_modalities": output_modalities,
            "supported_parameters": params,
            "pricing": pricing,
            "checked_at": checked,
        }
        rows.append(
            {
                "alias": model_id.rsplit("/", 1)[-1],
                "model": model_id,
                "model_id": model_id,
                "model_name": _safe_text(item.get("name")),
                "canonical_model_id": _safe_text(item.get("canonical_slug") or model_id),
                "confidence": "provider_catalog_openrouter",
                "source_layer": "provider_catalog",
                "source_name": "OpenRouter catalog",
                "provider_context_window_tokens": item.get("context_length"),
                "provider_top_context_window_tokens": top_provider.get("context_length"),
                "provider_top_max_output_tokens": top_provider.get("max_completion_tokens"),
                "provider_supported_parameters": params,
                "input_modalities": input_modalities,
                "output_modalities": output_modalities,
                "provider_catalog_references": [catalog_ref],
                "evidence": [
                    {"url": source_path, "source": "openrouter_models_api"},
                    {"url": _openrouter_model_page_url(model_id), "source": "openrouter_model_page"},
                ],
            }
        )
    return {
        "schema": "mms.model_capability.provider_catalog.openrouter.v1",
        "source": "openrouter",
        "source_layer": "provider_catalog",
        "source_path": source_path,
        "checked_at": checked,
        "models": rows,
    }


def _fetch_openrouter_catalog_payload(*, url: str = "", timeout: float = 20.0) -> dict[str, Any]:
    request = Request(
        url or _openrouter_models_api_url(),
        headers={
            "Accept": "application/json",
            "User-Agent": "MMS-Config-Web/1.0 (+https://github.com/CtriXin/multi-model-switch)",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("OpenRouter catalog payload must be a JSON object")
    return payload


def _latest_openrouter_catalog_payload(db: Any) -> tuple[dict[str, Any], str, str] | None:
    try:
        import mms_registry

        row = db.execute(
            """
            SELECT source_path, captured_at, payload_json
            FROM source_snapshot
            WHERE source_kind = ?
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (mms_registry.OPENROUTER_MODELS_SOURCE_KIND,),
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    try:
        payload = json.loads(str(row["payload_json"] or "{}"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload, _safe_text(row["source_path"]), _safe_text(row["captured_at"])


def _index_truth_payload(payload: dict[str, Any], *, source_path: str = "") -> dict[str, tuple[dict[str, Any], str]]:
    indexed: dict[str, tuple[dict[str, Any], str]] = {}

    def add_row(row: dict[str, Any], fallback_key: str = "") -> None:
        keys = [
            row.get("alias"),
            row.get("model"),
            row.get("model_name"),
            row.get("model_id"),
            row.get("routed_model_id"),
            row.get("canonical_model_id"),
            fallback_key,
        ]
        for value in keys:
            for key in _truth_model_index_keys(value):
                if key and key not in indexed:
                    indexed[key] = (row, source_path)

    for row in payload.get("models") if isinstance(payload.get("models"), list) else []:
        if isinstance(row, dict):
            add_row(row)
    for section_name in ("capabilities", "model_capabilities", "facts", "routes"):
        section = payload.get(section_name)
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if not isinstance(value, dict):
                continue
            row = dict(value)
            if section_name == "routes" and isinstance(row.get("primary"), dict):
                row = dict(row["primary"])
            add_row(row, str(key))
    return indexed


def _load_capability_truth_payloads(config_path: str = "", *, refresh_sources: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    payloads: list[dict[str, Any]] = []
    refresh_reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    config_root = _config_root_for_snapshot(config_path)
    try:
        import mms_registry

        db_path = mms_registry.default_registry_db_path(config_dir=config_root or None)
        if refresh_sources:
            try:
                from mms_registry.cli import refresh_source_snapshots

                refresh_reports.append(refresh_source_snapshots(db_path=db_path, if_due=False))
            except Exception as exc:
                warnings.append(f"刷新本地结构化 source snapshot 失败: {type(exc).__name__}: {exc}")
        try:
            db = mms_registry.open_registry(db_path)
            try:
                built = mms_registry.build_approved_capabilities_payload(db)
                if built.get("models"):
                    built["_source_path"] = str(db_path)
                    payloads.append(built)
                openrouter_snapshot = _latest_openrouter_catalog_payload(db)
                if openrouter_snapshot:
                    openrouter_payload, source_path, captured_at = openrouter_snapshot
                    built_openrouter = _openrouter_catalog_to_truth_payload(
                        openrouter_payload,
                        source_path=source_path or _openrouter_models_api_url(),
                        checked_at=captured_at,
                    )
                    if built_openrouter.get("models"):
                        built_openrouter["_source_path"] = source_path or str(db_path)
                        payloads.append(built_openrouter)
            finally:
                db.close()
        except Exception:
            pass
    except Exception:
        pass

    for path in (
        Path(config_root) / "generated" / "model-capabilities.approved.json" if config_root else None,
        Path(config_root) / "model-capabilities.approved.json" if config_root else None,
    ):
        if not path or not path.exists():
            continue
        payload = _load_json_file(str(path))
        if payload:
            payload["_source_path"] = str(path)
            payloads.append(payload)

    reference_dir = Path(__file__).resolve().parent / "docs" / "reference" / "model-capability-calibration"
    for path in sorted(reference_dir.glob("*.json")):
        payload = _load_json_file(str(path))
        if payload:
            payload["_source_path"] = str(path)
            payloads.append(payload)
    return payloads, refresh_reports, warnings


def refresh_model_capability_truth(
    cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Build draft capability updates from structured capability snapshots only.

    This is intentionally a draft helper: it never writes model-policy or the
    runtime bundle. Existing save/preview flow remains the only persistence path.
    """
    payload = payload if isinstance(payload, dict) else {}
    provider = _provider_from_payload(cfg or {}, payload, config_path=config_path, command_name=command_name)
    provider_payload = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    provider.update({key: value for key, value in provider_payload.items() if key in {"models", "fallback_models", "approved_route_models", "extra_models"}})
    requested_fields = {_safe_text(item) for item in payload.get("fields") or [] if _safe_text(item)}
    fields = requested_fields.intersection(_capability_truth_refresh_fields_const()) or set(_capability_truth_refresh_fields_const())
    model_ids = _normalize_model_list(payload.get("models")) or _truth_model_ids_from_provider(provider)
    use_openrouter_catalog = _truthy(payload.get("openrouter_catalog"), False)
    truth_payloads, refresh_reports, warnings = _call_backend_override(
        "_load_capability_truth_payloads",
        _load_capability_truth_payloads,
        config_path,
        refresh_sources=_truthy(payload.get("refresh_sources"), True),
    )
    # OpenRouter refresh should mean OpenRouter-only matching; the local snapshot button covers official/approved facts.
    if use_openrouter_catalog:
        truth_payloads = []
        refresh_reports = []
    catalog_sources: list[dict[str, Any]] = []
    if use_openrouter_catalog:
        source_url = _safe_text(payload.get("openrouter_url") or _openrouter_models_api_url())
        try:
            timeout = float(payload.get("openrouter_timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(1.0, min(timeout, 45.0))
        try:
            openrouter_payload = _call_backend_override("_fetch_openrouter_catalog_payload", _fetch_openrouter_catalog_payload, url=source_url, timeout=timeout)
            openrouter_truth = _openrouter_catalog_to_truth_payload(
                openrouter_payload,
                source_path=source_url,
                checked_at=_now_iso(),
            )
            openrouter_truth["_source_path"] = source_url
            truth_payloads.insert(0, openrouter_truth)
            catalog_sources.append(
                {
                    "source": "openrouter",
                    "source_layer": "provider_catalog",
                    "transport": "network",
                    "source_path": source_url,
                    "model_count": len(openrouter_truth.get("models") or []),
                    "checked_at": openrouter_truth.get("checked_at"),
                    "confidence": "provider_catalog_openrouter",
                    "note": "OpenRouter 是 provider catalog reference，不等于模型厂商官方真值。",
                }
            )
        except Exception as exc:
            warnings.append(f"读取 OpenRouter catalog 失败: {type(exc).__name__}: {exc}")
    truth_index: dict[str, tuple[dict[str, Any], str]] = {}
    for truth_payload in truth_payloads:
        source_path = _safe_text(truth_payload.get("_source_path"))
        for key, item in _index_truth_payload(truth_payload, source_path=source_path).items():
            truth_index.setdefault(key, item)

    model_capabilities: dict[str, dict[str, Any]] = {}
    model_sources: dict[str, dict[str, Any]] = {}
    changes: list[dict[str, Any]] = []
    unmatched: list[str] = []
    current_rows = {
        _truth_model_index_key(row.get("id") or row.get("model")): row
        for row in (provider_payload.get("models") if isinstance(provider_payload.get("models"), list) else [])
        if isinstance(row, dict)
    }

    for model_id in model_ids:
        keys = _truth_model_index_keys(model_id)
        truth = next((truth_index.get(key) for key in keys if truth_index.get(key)), None)
        if not truth:
            unmatched.append(model_id)
            continue
        row, source_path = truth
        caps, sources = _truth_caps_from_row(row, fields=fields, source_path=source_path)
        if not caps:
            unmatched.append(model_id)
            continue
        model_capabilities[model_id] = caps
        model_sources[model_id] = sources
        current_key = next((item_key for item_key in keys if item_key in current_rows), keys[-1] if keys else "")
        current_caps = current_rows.get(current_key, {}).get("capabilities")
        current_caps = current_caps if isinstance(current_caps, dict) else {}
        for field, value in caps.items():
            if field == "long_context":
                continue
            before = current_caps.get(field)
            if before != value:
                changes.append({"model": model_id, "field": field, "before": before, "after": value, "source": sources.get(field, {})})

    return {
        "ok": True,
        "schema": "mms.config_web.model_capability_snapshot_refresh.v1",
        "provider_id": provider.get("id"),
        "mode": "draft_only",
        "source_mode": "openrouter_catalog" if catalog_sources else "known_snapshots",
        "fields": [field for field in _capability_truth_refresh_fields_const() if field in fields],
        "field_config": capability_truth_refresh_fields(),
        "model_count": len(model_ids),
        "matched_model_count": len(model_capabilities),
        "changed_field_count": len(changes),
        "model_capabilities": model_capabilities,
        "model_sources": model_sources,
        "changes": changes[:200],
        "unmatched_models": unmatched[:80],
        "warnings": warnings,
        "refresh_reports": refresh_reports,
        "catalog_sources": catalog_sources,
        "note": "只使用结构化 source snapshot、approved capabilities 或 provider catalog 字段；OpenRouter 是快速结构化参考源，不是厂商官方真值；结果只进入页面草稿，保存发布后才生效。",
    }
