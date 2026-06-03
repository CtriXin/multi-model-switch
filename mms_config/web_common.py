# -*- coding: utf-8 -*-
"""Shared constants and pure helpers for the MMS config WebUI."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable


_SECRET_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "gateway_key", "token", "secret", "authorization", "password", "passphrase"}
_SENSITIVE_CONFIG_KEYS = {"home_dir", "proxy", "no_proxy"}
_SAFE_TOKEN_COUNT_KEYS = {
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "completion_tokens",
    "context_tokens",
    "context_window_tokens",
    "input_tokens",
    "max_completion_tokens",
    "max_context_tokens",
    "max_output_tokens",
    "official_context_window_tokens",
    "official_max_output_tokens",
    "output_tokens",
    "output_window_tokens",
    "prompt_tokens",
    "total_tokens",
    "tokens",
}
_ALLOWED_PROTOCOLS = ("anthropic_messages", "openai_chat_completions")
_ALLOWED_CLIS = ("claude", "codex", "opencode", "pi", "agy")
_ALLOWED_ROLES = ("primary", "auto", "fallback")
_FALLBACK_MODEL_FAMILIES = ("Claude", "GPT", "Gemini", "DeepSeek", "Qwen", "Kimi", "Mimo", "MiniMax", "GLM")
_OPENCODE_ROSTER_PRESETS = ("builder", "executor", "explore", "bughunt", "vision", "reviewer", "spec", "fixer")
_OPENCODE_REQUIRED_BUILDER_AGENTS = {"mobius-builder-pro", "builder_primary"}
_REGISTRY_V2_GENERATED_FILES = (
    "model-routes.json",
    "model-routes.lineup.json",
    "provider-profiles.generated.json",
    "model-policy.effective.json",
    "model-capabilities.approved.json",
    "model-registry.latest-approved.json",
)
_MIGRATION_BUNDLE_SCHEMA = "mms.config_migration_bundle.v1"
_MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA = "mms.config_migration_credentials.aesgcm.v1"
_MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA = "mms.config_migration_credentials.openssl-cbc-hmac.v1"
_MIGRATION_CREDENTIAL_BOX_SCHEMA = _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA

_KNOWN_VISION_MODELS = {
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.5",
    "k2.6",
    "k2.6-code-preview",
    "kimi-k2.5",
    "kimi-k2.6",
    "mimo-v2.5",
    "mimo-v2-omni",
    "minimax-m2.7",
    "minimax-m3",
    "qwen3.5-plus",
    "qwen3.6-flash",
    "qwen3.6-plus",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
}
_CACHE_SENSITIVE_PREFIXES = ("qwen", "kimi", "k2.", "glm", "deepseek", "minimax", "mimo")
_REASONING_HINTS = (
    "gpt-5",
    "o1-",
    "o3-",
    "o4-",
    "qwen3",
    "kimi-k2",
    "glm-5",
    "deepseek",
    "claude-opus",
    "claude-sonnet",
    "mimo-v2.5",
    "minimax-m2",
    "minimax-m3",
)
_CAPABILITY_TRUTH_REFRESH_FIELDS = (
    "context_window_tokens",
    "max_output_tokens",
    "vision",
    "tool_use",
    "reasoning",
    "thinking",
    "one_m_context",
)
_OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models"


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enable", "enabled", "是", "开启"}


def _redact(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:3]}***{text[-3:]}"


def _is_secret_like_key(key_lower: str) -> bool:
    if key_lower in _SAFE_TOKEN_COUNT_KEYS or key_lower.endswith("_tokens"):
        return False
    if key_lower.startswith(("has_api_key", "missing_api_key")):
        return False
    return key_lower in _SECRET_KEYS or any(token in key_lower for token in ("token", "secret", "api_key"))


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _slug(value: Any, default: str = "provider") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = text.strip("-_")
    return text or default


def _split_values(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    elif isinstance(value, str):
        raw = re.split(r"[,\n]", value)
    else:
        raw = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_model_list(value: Any) -> list[str]:
    return _split_values(value)


def _normalize_choice_list(value: Any, allowed: tuple[str, ...], default: tuple[str, ...]) -> list[str]:
    values = []
    seen = set()
    for item in _split_values(value):
        normalized = item.strip().lower()
        if normalized in allowed and normalized not in seen:
            seen.add(normalized)
            values.append(normalized)
    return values or list(default)


def _normalize_priority(value: Any, default: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _normalize_context_tokens(value: Any) -> int | None:
    try:
        parsed = int(str(value).replace("_", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _known_model_families(load_mms_core_fn: Callable[[], Any] | None = None) -> list[str]:
    try:
        if load_mms_core_fn is None:
            import mms_core

            mms_core_obj = mms_core
        else:
            mms_core_obj = load_mms_core_fn()
        families = []
        for entry in getattr(mms_core_obj, "MODEL_FAMILIES", ()):
            if isinstance(entry, dict):
                family = _safe_text(entry.get("family"))
                if family and family not in families:
                    families.append(family)
        return families or list(_FALLBACK_MODEL_FAMILIES)
    except Exception:
        return list(_FALLBACK_MODEL_FAMILIES)


def _canonical_family_name(value: Any, *, known_model_families_fn: Callable[[], list[str]] | None = None) -> str:
    raw = _safe_text(value)
    if not raw:
        return ""
    families = known_model_families_fn() if known_model_families_fn is not None else _known_model_families()
    for family in families:
        if family.lower() == raw.lower():
            return family
    return ""


def _normalize_family_priority_overrides(
    value: Any,
    *,
    canonical_family_name_fn: Callable[[Any], str] | None = None,
    normalize_priority_fn: Callable[[Any], int] | None = None,
) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, int] = {}
    canonicalize = canonical_family_name_fn or _canonical_family_name
    normalize_priority = normalize_priority_fn or _normalize_priority
    for family, priority in raw.items():
        canonical = canonicalize(family)
        if not canonical:
            continue
        result[canonical] = normalize_priority(priority)
    return result


def _sanitize_for_output(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key or "")
            key_lower = key_text.lower()
            if key_lower.startswith("has_") or key_lower.endswith(("_count", "_counts")):
                result[key_text] = child
            elif key_lower in _SENSITIVE_CONFIG_KEYS:
                result[key_text] = bool(_safe_text(child))
            elif _is_secret_like_key(key_lower):
                result[key_text] = _redact(child)
            else:
                result[key_text] = _sanitize_for_output(child)
        return result
    if isinstance(value, list):
        return [_sanitize_for_output(item) for item in value]
    return value


def _json_response(payload: Any, *, status: int = 200) -> tuple[int, bytes, str]:
    return (
        status,
        json.dumps(_sanitize_for_output(payload), ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8"),
        "application/json; charset=utf-8",
    )
