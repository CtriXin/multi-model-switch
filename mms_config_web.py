# -*- coding: utf-8 -*-
"""Local interactive WebUI for MMS setup, model policy, and audited config saves."""

from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from mms_config_web_assets import _HTML_PAGE
from mms_session_assets import build_session_assets_snapshot
from mms_config_web_settings import (
    _settings_action_cards,
    _webui_capability_coverage,
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
    build_settings_report,
)
from mms_config_web_server import (
    ConfigWebApp,
    _SetupWebHandler,
    _html_page,
    run_config_web,
    serve_config_web,
)
from mms_opencode_profiles import (
    OPENCODE_COMMITTEE_TIERS,
    OPENCODE_COMMITTEE_TIER_DEFAULTS,
    OPENCODE_PROFILE_OPTIONS,
    OPENCODE_REVIEW_PROFILE_ID,
    normalize_opencode_profile_id,
    opencode_committee_preset_config,
    opencode_lite_pro_specs,
    opencode_profile_selection_ids,
    opencode_review_host_config,
    validate_opencode_committee_tier_preset,
)


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
    "k3",
    "k3[1m]",
    "kimi-k3",
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
    "k3",
    "kimi-k3",
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
    "thinking_control",
    "reasoning_effort",
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


def _redact_inline_secrets(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer ***", text)
    text = re.sub(r"\b(?:sk|sk-or-v1|sk-ant|ak)-[A-Za-z0-9._-]{12,}\b", "***", text)
    return text


def _is_redacted_secret_token(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text in {"<redacted>", "[redacted]", "***", "****"} or "***" in text or "****" in text


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


def _normalize_channel_map(value: Any, allowed_models: list[str] | None = None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    allowed = {str(model or "").strip().lower() for model in (allowed_models or []) if str(model or "").strip()}
    result: dict[str, str] = {}
    for key, channel in value.items():
        model = _safe_text(key)
        route = _safe_text(channel)
        if not model or not route:
            continue
        if allowed and model.lower() not in allowed:
            continue
        result[model] = route
    return result


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


def _known_model_families() -> list[str]:
    try:
        mms_core = _load_mms_core()
        families = []
        for entry in getattr(mms_core, "MODEL_FAMILIES", ()):
            if isinstance(entry, dict):
                family = _safe_text(entry.get("family"))
                if family and family not in families:
                    families.append(family)
        return families or list(_FALLBACK_MODEL_FAMILIES)
    except Exception:
        return list(_FALLBACK_MODEL_FAMILIES)


def _canonical_family_name(value: Any) -> str:
    raw = _safe_text(value)
    if not raw:
        return ""
    for family in _known_model_families():
        if family.lower() == raw.lower():
            return family
    return ""


def _normalize_family_priority_overrides(value: Any) -> dict[str, int]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, int] = {}
    for family, priority in raw.items():
        canonical = _canonical_family_name(family)
        if not canonical:
            continue
        result[canonical] = _normalize_priority(priority)
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
    return status, json.dumps(_sanitize_for_output(payload), ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8"), "application/json; charset=utf-8"


def _load_mms_core():
    import mms_core

    return mms_core


def _version_info_for_snapshot(command_name: str = "mms") -> dict[str, Any]:
    try:
        mms_core = _load_mms_core()
        raw = mms_core._release_version_info()  # noqa: SLF001 - read-only version metadata for WebUI chrome
        info = dict(raw) if isinstance(raw, dict) else {}
    except Exception as exc:
        info = {"release": "dev", "error": f"{type(exc).__name__}: {exc}"}
    release = _safe_text(info.get("release") or info.get("installed_version") or info.get("git_describe") or info.get("git_commit") or "dev")
    branch = _safe_text(info.get("git_branch"))
    commit = _safe_text(info.get("git_commit"))
    channel = _safe_text(info.get("install_channel"))
    track_label = _safe_text(info.get("release_track_label") or info.get("release_track_version"))
    if branch and commit:
        display = f"{branch}@{commit}"
    elif channel and release:
        display = f"{channel} {release}"
    else:
        display = release
    if track_label:
        display = f"{track_label} · {display}"
    info["command"] = command_name
    info["display"] = display
    return info


def _policy_path_for_config(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.join(os.path.dirname(config_path), "model-policy.json")
    try:
        import mms_router

        return str(getattr(mms_router, "MODEL_POLICY_PATH", ""))
    except Exception:
        return ""


def _config_root_for_snapshot(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.dirname(config_path)
    try:
        from mms_state_io import resolve_mms_config_dir

        return resolve_mms_config_dir()
    except Exception:
        return ""


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import model_source_status

        return model_source_status(
            config_dir=config_root or None,
            command_name=f"{command_name} config source",
        )
    except Exception as exc:
        return {
            "schema": "mms.model_source_status.v1",
            "read_only": True,
            "status": "error",
            "error": str(exc),
            "config_root": config_root,
        }


def _consumer_bundle_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import consumer_bundle_status

        return consumer_bundle_status(
            config_dir=config_root or None,
            command_name=f"{command_name} config bundle",
        )
    except Exception as exc:
        return {
            "schema": "mms.consumer_bundle_status.v1",
            "read_only": True,
            "status": "error",
            "verified": False,
            "error": str(exc),
            "config_root": config_root,
        }


def _is_preview_config_root(config_path: str = "", *, command_name: str = "mms") -> bool:
    config_root = _config_root_for_snapshot(config_path)
    if not config_root:
        return False
    try:
        from mms_state_io import mms_config_root_status

        return mms_config_root_status(command=command_name, config_dir=config_root).get("mode") == "preview"
    except Exception:
        return False


def _is_placeholder_provider_config(cfg: dict[str, Any]) -> bool:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    if not providers:
        return True
    if len(providers) != 1 or not isinstance(providers[0], dict):
        return False
    provider = providers[0]
    provider_id = _safe_text(provider.get("id"))
    name = _safe_text(provider.get("name"))
    if provider_id not in {"default", "local", ""}:
        return False
    if name and name not in {"Default Gateway", "Default", "Local"}:
        return False
    configured_models = (
        _normalize_model_list(provider.get("fallback_models"))
        or _normalize_model_list(provider.get("extra_models"))
        or _normalize_model_list(provider.get("models"))
    )
    configured_urls = _safe_text(
        provider.get("openai_base_url")
        or provider.get("anthropic_base_url")
        or provider.get("default_openai_base_url")
        or provider.get("default_anthropic_base_url")
        or provider.get("base_url")
    )
    configured_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key") or provider.get("anthropic_api_key"))
    return not configured_models and not configured_urls and not configured_key


def _read_json_from_verified_file(verified_files: dict[str, Any], key: str) -> dict[str, Any]:
    row = verified_files.get(key) if isinstance(verified_files.get(key), dict) else {}
    path = _safe_text(row.get("path"))
    if not path:
        return {}
    return _load_json_file(path)


def _preview_secret_refs_by_provider(config_root: str = "") -> dict[str, str]:
    root = os.path.abspath(os.path.expanduser(config_root)) if config_root else ""
    if not root:
        return {}
    ranked: dict[str, tuple[int, str]] = {}
    paths = [
        (os.path.join(root, "secrets", "legacy-secrets.json"), 10),
        (os.path.join(root, "secrets", "webui-secrets.json"), 20),
    ]
    field_rank = {"api_key": 3, "openai_api_key": 2, "anthropic_api_key": 1}
    for path, source_score in paths:
        payload = _load_json_file(path)
        entries = payload.get("secrets") if isinstance(payload.get("secrets"), list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            provider_id = _safe_text(entry.get("provider_id"))
            secret_ref = _safe_text(entry.get("secret_ref"))
            if not provider_id or not secret_ref:
                continue
            score = source_score + field_rank.get(_safe_text(entry.get("field")), 0)
            current = ranked.get(provider_id)
            if current is None or score > current[0]:
                ranked[provider_id] = (score, secret_ref)
    return {provider_id: secret_ref for provider_id, (_score, secret_ref) in ranked.items()}


def _preview_secret_values_by_ref(config_root: str = "") -> dict[str, str]:
    root = os.path.abspath(os.path.expanduser(config_root)) if config_root else ""
    if not root:
        return {}
    values: dict[str, str] = {}
    for filename in ("legacy-secrets.json", "webui-secrets.json"):
        payload = _load_json_file(os.path.join(root, "secrets", filename))
        entries = payload.get("secrets") if isinstance(payload.get("secrets"), list) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            secret_ref = _safe_text(entry.get("secret_ref"))
            value = _safe_text(entry.get("value"))
            if secret_ref and value:
                values[secret_ref] = value
    return values


def _preview_cached_provider_url(provider_id: str) -> str:
    provider_id = _safe_text(provider_id)
    if not provider_id:
        return ""
    try:
        mms_core = _load_mms_core()
        cached = mms_core._load_probe_file_cache(provider_id, allow_stale=True)  # noqa: SLF001 - UI recovery only
    except Exception:
        cached = {}
    if not isinstance(cached, dict):
        return ""
    return _safe_text(cached.get("working_url")).rstrip("/")


def _resolve_preview_provider_secret(
    provider: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    provider = dict(provider or {})
    if not _is_preview_config_root(config_path, command_name=command_name):
        return provider
    config_root = _config_root_for_snapshot(config_path)
    provider_id = _safe_text(provider.get("id") or provider.get("provider_id"))
    secret_refs = _preview_secret_refs_by_provider(config_root)
    secret_values = _preview_secret_values_by_ref(config_root)
    secret_ref = _safe_text(provider.get("secret_ref"))
    replacement_ref = secret_refs.get(provider_id, "") if provider_id else ""
    if provider_id and replacement_ref and (
        not secret_ref or _is_redacted_secret_token(secret_ref) or not _safe_text(secret_values.get(secret_ref))
    ):
        secret_ref = replacement_ref
    elif _is_redacted_secret_token(secret_ref):
        secret_ref = ""
    if secret_ref:
        provider["secret_ref"] = secret_ref
    else:
        provider.pop("secret_ref", None)
    if secret_ref and not _safe_text(provider.get("api_key") or provider.get("openai_api_key") or provider.get("anthropic_api_key")):
        value = secret_values.get(secret_ref, "")
        if value:
            provider["api_key"] = value
    return provider


def _attach_preview_secret_refs(
    cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    if not _is_preview_config_root(config_path, command_name=command_name):
        return cfg
    refs = _preview_secret_refs_by_provider(_config_root_for_snapshot(config_path))
    if not refs:
        return cfg
    values = _preview_secret_values_by_ref(_config_root_for_snapshot(config_path))
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    changed = False
    next_providers = []
    for provider in providers:
        if not isinstance(provider, dict):
            next_providers.append(provider)
            continue
        row = dict(provider)
        provider_id = _safe_text(row.get("id") or row.get("provider_id"))
        secret_ref = _safe_text(row.get("secret_ref"))
        replacement_ref = refs.get(provider_id, "") if provider_id else ""
        if provider_id and replacement_ref and (
            not secret_ref or _is_redacted_secret_token(secret_ref) or not _safe_text(values.get(secret_ref))
        ):
            row["secret_ref"] = replacement_ref
            changed = True
        elif _is_redacted_secret_token(secret_ref):
            row.pop("secret_ref", None)
            changed = True
        next_providers.append(row)
    if changed:
        cfg["providers"] = next_providers
    return cfg


def _preview_bundle_config_from_verified_files(verified_files: dict[str, Any], *, config_root: str = "") -> dict[str, Any]:
    profiles_payload = _read_json_from_verified_file(verified_files, "profile")
    router_payload = _read_json_from_verified_file(verified_files, "router")
    profiles = profiles_payload.get("profiles") if isinstance(profiles_payload.get("profiles"), dict) else {}
    routes = router_payload.get("routes") if isinstance(router_payload.get("routes"), dict) else {}
    secret_refs = _preview_secret_refs_by_provider(config_root)
    secret_values = _preview_secret_values_by_ref(config_root)
    provider_models: dict[str, set[str]] = {}
    provider_routes: dict[str, dict[str, Any]] = {}
    for route_model, route in routes.items():
        if not isinstance(route, dict):
            continue
        leaves = []
        primary = route.get("primary")
        if isinstance(primary, dict):
            leaves.append(primary)
        leaves.extend(item for item in (route.get("fallbacks") or []) if isinstance(item, dict))
        for leaf in leaves:
            provider_id = _safe_text(leaf.get("provider_id"))
            if not provider_id:
                continue
            model_id = _safe_text(leaf.get("model") or leaf.get("model_id") or route_model)
            if model_id:
                provider_models.setdefault(provider_id, set()).add(model_id)
            info = provider_routes.setdefault(provider_id, {"openai_base_url": "", "anthropic_base_url": "", "has_api_key": False})
            if not info["openai_base_url"]:
                info["openai_base_url"] = _safe_text(leaf.get("openai_base_url"))
            if not info["anthropic_base_url"]:
                info["anthropic_base_url"] = _safe_text(leaf.get("anthropic_base_url"))
            if _safe_text(leaf.get("api_key")):
                info["has_api_key"] = True
            if not info.get("secret_ref"):
                info["secret_ref"] = _safe_text(leaf.get("secret_ref"))

    provider_ids = set(profiles.keys()) | set(provider_models.keys())
    providers: list[dict[str, Any]] = []
    for provider_id in sorted(provider_ids):
        profile = profiles.get(provider_id) if isinstance(profiles.get(provider_id), dict) else {}
        route_info = provider_routes.get(provider_id, {})
        cached_url = _preview_cached_provider_url(provider_id)
        openai_base_url = _safe_text(route_info.get("openai_base_url"))
        anthropic_base_url = _safe_text(route_info.get("anthropic_base_url"))
        route_secret_ref = _safe_text(route_info.get("secret_ref"))
        backend_secret_ref = _safe_text(secret_refs.get(provider_id))
        secret_ref = route_secret_ref or backend_secret_ref
        if backend_secret_ref and (
            not secret_ref or _is_redacted_secret_token(secret_ref) or not _safe_text(secret_values.get(secret_ref))
        ):
            secret_ref = backend_secret_ref
        elif _is_redacted_secret_token(secret_ref):
            secret_ref = ""
        protocols = _normalize_model_list(profile.get("protocols"))
        if cached_url:
            if not openai_base_url and "openai_chat_completions" in protocols:
                openai_base_url = cached_url
            if not anthropic_base_url and "anthropic_messages" in protocols:
                anthropic_base_url = cached_url
        providers.append(
            {
                "id": provider_id,
                "name": _safe_text(profile.get("name") or provider_id),
                "enabled": profile.get("enabled", True) is not False,
                "role": _safe_text(profile.get("role") or "auto"),
                "priority": int(profile.get("priority") or 0),
                "models_endpoint": _safe_text(profile.get("models_endpoint") or "manual"),
                "protocols": protocols,
                "supported_clis": _normalize_model_list(profile.get("supported_clis")),
                "openai_base_url": openai_base_url,
                "anthropic_base_url": anthropic_base_url,
                "has_api_key": bool(route_info.get("has_api_key") or (secret_ref and secret_values.get(secret_ref))),
                "secret_ref": secret_ref,
                "fallback_models": sorted(provider_models.get(provider_id, set()), key=str.lower),
                "extra_models": [],
                "hidden_models": _normalize_model_list(profile.get("hidden_models")),
            }
        )
    role_rank = {"primary": 0, "auto": 1, "fallback": 2}
    providers.sort(key=lambda item: (role_rank.get(str(item.get("role") or "auto"), 1), -int(item.get("priority") or 0), str(item.get("id") or "")))
    provider_cfg = profiles_payload.get("provider") if isinstance(profiles_payload.get("provider"), dict) else {}
    explicit_default = _safe_text(provider_cfg.get("default") or profiles_payload.get("default_provider"))
    provider_ids = {_safe_text(item.get("id")) for item in providers}
    provider_default = explicit_default if explicit_default in provider_ids else (providers[0]["id"] if providers else "")
    result: dict[str, Any] = {"providers": providers, "provider": {"default": provider_default}}
    runtime_config = profiles_payload.get("runtime_config") if isinstance(profiles_payload.get("runtime_config"), dict) else {}
    runtime_opencode = runtime_config.get("opencode") if isinstance(runtime_config.get("opencode"), dict) else {}
    if runtime_opencode:
        result["opencode"] = copy.deepcopy(runtime_opencode)
    return result


def _hydrate_preview_config_from_latest_bundle(
    cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Preview roots may have no legacy config.toml; hydrate the editor from the verified bundle."""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    if not _is_preview_config_root(config_path, command_name=command_name):
        return cfg
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import verify_approved_bundle

        verified = verify_approved_bundle(config_dir=config_root or None)
    except Exception:
        return cfg
    if not verified.get("verified"):
        return cfg
    hydrated = _preview_bundle_config_from_verified_files(
        verified.get("verified_files") if isinstance(verified.get("verified_files"), dict) else {},
        config_root=config_root,
    )
    if not hydrated.get("providers"):
        return cfg
    if not _is_placeholder_provider_config(cfg):
        result = _attach_preview_secret_refs(cfg, config_path=config_path, command_name=command_name)
        existing_ids = {
            _safe_text(item.get("id"))
            for item in (result.get("providers") if isinstance(result.get("providers"), list) else [])
            if isinstance(item, dict)
        }
        missing = [
            dict(item)
            for item in hydrated.get("providers", [])
            if isinstance(item, dict) and _safe_text(item.get("id")) and _safe_text(item.get("id")) not in existing_ids
        ]
        if missing:
            result["providers"] = list(result.get("providers") or []) + missing
            result["_preview_bundle_profile_merged"] = True
        if isinstance(hydrated.get("opencode"), dict):
            result["opencode"] = copy.deepcopy(hydrated["opencode"])
        return _attach_preview_secret_refs(result, config_path=config_path, command_name=command_name)
    result = copy.deepcopy(cfg)
    result["providers"] = hydrated["providers"]
    result["provider"] = hydrated["provider"]
    if isinstance(hydrated.get("opencode"), dict):
        result["opencode"] = copy.deepcopy(hydrated["opencode"])
    result["_preview_bundle_hydrated"] = True
    return _attach_preview_secret_refs(result, config_path=config_path, command_name=command_name)


def _config_v2_promotion_plan_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import config_v2_promotion_plan

        return config_v2_promotion_plan(
            preview_config_dir=config_root or None,
            command_name=f"{command_name} config promote-plan",
        )
    except Exception as exc:
        return {
            "schema": "mms.config_v2_promotion_plan.v1",
            "read_only": True,
            "apply_enabled": False,
            "status": "error",
            "ready_for_human_review": False,
            "error": str(exc),
            "config_root": config_root,
        }


def _config_v2_release_readiness_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry_cli import config_v2_release_readiness

        return config_v2_release_readiness(
            preview_config_dir=config_root or None,
            command_name=f"{command_name} config release-readiness",
        )
    except Exception as exc:
        return {
            "schema": "mms.config_v2_release_readiness.v1",
            "read_only": True,
            "release_complete": False,
            "status": "error",
            "result": "NOT_READY",
            "ready_for_human_gate": False,
            "human_gate_required": True,
            "completion_blocker": "release_readiness_error",
            "blocked_requirements": ["release_readiness_error"],
            "error": str(exc),
            "config_root": config_root,
        }


def _load_json_file(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _pretty_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _toml_key(key: Any) -> str:
    text = str(key)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    if value is None:
        return '""'
    if isinstance(value, datetime):
        return json.dumps(value.isoformat(), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _fallback_toml_dumps(payload: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_table(mapping: dict[str, Any], prefix: list[str]) -> None:
        scalars: list[tuple[str, Any]] = []
        nested: list[tuple[str, dict[str, Any]]] = []
        for key, value in mapping.items():
            if isinstance(value, dict):
                nested.append((str(key), value))
            else:
                scalars.append((str(key), value))

        if prefix and scalars:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("[" + ".".join(_toml_key(part) for part in prefix) + "]")
        for key, value in scalars:
            lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")
        for key, value in nested:
            emit_table(value, [*prefix, key])

    emit_table(payload if isinstance(payload, dict) else {}, [])
    return "\n".join(lines).rstrip() + "\n"


def _toml_dumps(payload: dict[str, Any]) -> str:
    try:
        import tomli_w

        return tomli_w.dumps(payload)
    except Exception:
        pass
    try:
        mms_core = _load_mms_core()
        writer = getattr(mms_core, "tomli_w", None)
        if writer is not None:
            return writer.dumps(payload)
    except Exception:
        pass
    return _fallback_toml_dumps(payload)


def _toml_text(payload: dict[str, Any]) -> str:
    return _toml_dumps(payload)


def _atomic_write_preferences_toml(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_toml_dumps(payload))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _diff_text(before: str, after: str, *, before_name: str, after_name: str) -> str:
    if before == after:
        return ""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def _provider_credentials_status(provider_id: str) -> dict[str, Any]:
    try:
        mms_core = _load_mms_core()
        creds = mms_core.load_provider_credentials(provider_id)
    except Exception:
        creds = {}
    return {
        "has_api_key": bool(_safe_text((creds or {}).get("api_key") or (creds or {}).get("openai_api_key"))),
        "base_url": _safe_text((creds or {}).get("base_url")),
        "openai_base_url": _safe_text((creds or {}).get("openai_base_url")),
        "anthropic_base_url": _safe_text((creds or {}).get("anthropic_base_url")),
    }


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
        "vision": False,
        "tool_use": False,
        "reasoning": False,
        "thinking": False,
        "long_context": "1m" in lower or "long" in lower,
        "cache_sensitive": False,
    }
    try:
        from mms_capability_resolver import resolve_model_capabilities

        resolved = resolve_model_capabilities(model, provider_id=provider_id)
        if resolved.get("supports_thinking") is True:
            caps["thinking"] = True
            caps["reasoning"] = True
        if isinstance(resolved.get("thinking_control"), dict) and resolved.get("sources", {}).get("thinking_control") != "conservative_fallback":
            caps["thinking_control"] = _truth_thinking_control(resolved["thinking_control"])
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
        if isinstance(policy_caps.get("thinking_control"), dict):
            caps["thinking_control"] = _truth_thinking_control(policy_caps["thinking_control"])
        if _safe_text(policy_caps.get("reasoning_effort")):
            caps["reasoning_effort"] = _safe_text(policy_caps["reasoning_effort"])
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
        "thinking_control": ("Effort 控制", "结构化 thinking / effort 控制路径、默认值和可选档位"),
        "reasoning_effort": ("默认 Effort", "模型默认 reasoning effort 档位"),
        "one_m_context": ("1M", "one_million_context 或 context >= 1M"),
    }
    return [
        {"key": key, "label": labels[key][0], "description": labels[key][1]}
        for key in _CAPABILITY_TRUTH_REFRESH_FIELDS
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
    raw = _safe_text(value).lower()
    text = _truth_normalize_model_key(value)
    if not raw and not text:
        return []
    keys: list[str] = []
    for item in (raw, text):
        if not item:
            continue
        tail = item.rsplit("/", 1)[-1] if "/" in item else item
        keys.extend([item, tail])
    return list(dict.fromkeys(keys))


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


def _truth_field_source(
    field: str,
    row: dict[str, Any],
    source_path: str = "",
    *,
    source_layer_override: str = "",
) -> dict[str, Any]:
    confidence = _safe_text(row.get("confidence") or "structured")
    source_layer = _safe_text(row.get("source_layer")).lower()
    source_name = _safe_text(row.get("source_name"))
    checked_at = _safe_text(row.get("checked_at"))
    if not checked_at:
        ref = _truth_first_provider_ref(row)
        checked_at = _safe_text(ref.get("checked_at")) if isinstance(ref, dict) else ""
    layer = source_layer_override or source_layer or "official"
    if not source_layer_override and (field == "tool_use" or "provider_catalog" in confidence or "openrouter" in confidence):
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


def _truth_thinking_control(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key in (
        "supported",
        "control_type",
        "path",
        "default",
        "request_default",
        "official_default",
        "recommended_default",
        "numeric_budget_tokens",
        "mode",
        "disable_supported",
    ):
        if key in value:
            result[key] = copy.deepcopy(value[key])
    for key in ("allowed", "map"):
        if isinstance(value.get(key), (list, dict)):
            result[key] = copy.deepcopy(value[key])
    return result

def _truth_control_has_positive_signal(control: dict[str, Any]) -> bool:
    if not isinstance(control, dict):
        return False
    if control.get("supported") is True:
        return True
    path = _safe_text(control.get("path"))
    control_type = _safe_text(control.get("control_type")).lower()
    return bool(path) or bool(control_type and control_type != "none")


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
    thinking_control = _truth_thinking_control(row.get("thinking_control"))
    if thinking_control and "thinking_control" in fields:
        caps["thinking_control"] = thinking_control
        sources["thinking_control"] = _truth_field_source("thinking_control", row, source_path)
        if "thinking" in fields and "thinking" not in caps:
            caps["thinking"] = bool(thinking_control.get("supported", True))
            sources["thinking"] = _truth_field_source("thinking", row, source_path)
        if "reasoning" in fields and "reasoning" not in caps:
            caps["reasoning"] = bool(thinking_control.get("supported", True))
            sources["reasoning"] = _truth_field_source("reasoning", row, source_path)
    effort_default = _safe_text(row.get("reasoning_effort") or row.get("reasoning_effort_default"))
    if effort_default and "reasoning_effort" in fields:
        caps["reasoning_effort"] = effort_default
        sources["reasoning_effort"] = _truth_field_source("reasoning_effort", row, source_path)
    official_effort = _safe_text(row.get("official_reasoning_effort_default"))
    if official_effort and "reasoning_effort" in fields:
        caps["official_reasoning_effort"] = official_effort
        sources["official_reasoning_effort"] = _truth_field_source("official_reasoning_effort", row, source_path)
    recommended_effort = _safe_text(row.get("recommended_reasoning_effort_default") or row.get("reasoning_effort_default"))
    if recommended_effort and "reasoning_effort" in fields:
        caps["recommended_reasoning_effort"] = recommended_effort
        sources["recommended_reasoning_effort"] = _truth_field_source("recommended_reasoning_effort", row, source_path)

    official_capabilities = row.get("official_capabilities") if isinstance(row.get("official_capabilities"), dict) else {}
    if "tool_use" in fields and official_capabilities.get("function_calling") is True:
        caps["tool_use"] = True
        sources["tool_use"] = _truth_field_source(
            "tool_use",
            row,
            source_path,
            source_layer_override="official",
        )

    params = _truth_supported_parameters(row)
    if "tool_use" in fields and "tool_use" not in caps and {"tools", "tool_choice", "parallel_tool_calls"}.intersection(params):
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
    source_path: str = _OPENROUTER_MODELS_API_URL,
    checked_at: str = "",
) -> dict[str, Any]:
    """Convert OpenRouter /models records into the same structured snapshot shape."""
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


def _fetch_openrouter_catalog_payload(*, url: str = _OPENROUTER_MODELS_API_URL, timeout: float = 20.0) -> dict[str, Any]:
    request = Request(
        url or _OPENROUTER_MODELS_API_URL,
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
                from mms_registry_cli import refresh_source_snapshots

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
                        source_path=source_path or _OPENROUTER_MODELS_API_URL,
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


def _mmf_official_overrides_payload(
    provider: dict[str, Any],
    model_ids: list[str],
    *,
    source_path: str = "",
) -> dict[str, Any]:
    """Build a draft-only capability payload from MMS-maintained provider profiles."""
    checked = _now_iso()
    source = source_path or str(Path(__file__).resolve().parent / "config" / "provider-profiles.json")
    rows: list[dict[str, Any]] = []
    try:
        from mms_capability_resolver import resolve_model_capabilities
        from mms_provider_profiles import load_provider_profiles
        from mms_provider_profiles import profile_thinking_capabilities
    except Exception:
        return {
            "schema": "mms.model_capability.mmf_official_overrides.v1",
            "source": "mmf_official_overrides",
            "source_layer": "official",
            "source_path": source,
            "checked_at": checked,
            "models": rows,
        }

    cache_clear = getattr(load_provider_profiles, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    profiles = load_provider_profiles()
    runtime = provider if isinstance(provider, dict) else {}
    provider_id = _safe_text(runtime.get("id") or runtime.get("provider_id"))
    base_url = _safe_text(runtime.get("anthropic_base_url") or runtime.get("openai_base_url") or runtime.get("base_url"))
    for model_id in model_ids:
        model = _safe_text(model_id)
        if not model:
            continue
        try:
            resolved = resolve_model_capabilities(
                model,
                runtime=runtime,
                provider_id=provider_id,
                base_url=base_url,
                approved_facts={},
                model_policy={},
                provider_profiles=profiles,
            )
        except Exception:
            continue
        sources = resolved.get("sources") if isinstance(resolved.get("sources"), dict) else {}
        row: dict[str, Any] = {
            "alias": model,
            "model": model,
            "model_id": model,
            "confidence": "mmf_official_profile",
            "source_layer": "official",
            "source_name": "MMF 官方覆盖",
            "checked_at": checked,
            "evidence": [{"url": source, "source": "mms_provider_profiles"}],
        }
        has_profile_value = False
        if sources.get("context_window_tokens") == "provider_profile":
            row["official_context_window_tokens"] = resolved.get("context_window_tokens")
            has_profile_value = True
        if sources.get("max_output_tokens") == "provider_profile":
            row["official_max_output_tokens"] = resolved.get("max_output_tokens")
            has_profile_value = True
        # MMF official overlays are additive: never downgrade OpenRouter/user enabled booleans to false.
        if sources.get("supports_vision") == "provider_profile" and resolved.get("supports_vision") is True:
            row["supports_vision"] = resolved.get("supports_vision")
            has_profile_value = True
        if sources.get("supports_thinking") == "provider_profile" and resolved.get("supports_thinking") is True:
            row["supports_thinking"] = resolved.get("supports_thinking")
            has_profile_value = True
        if sources.get("thinking_control") == "provider_profile" and isinstance(resolved.get("thinking_control"), dict):
            thinking_control = _truth_thinking_control(resolved["thinking_control"])
            if _truth_control_has_positive_signal(thinking_control):
                row["thinking_control"] = thinking_control
            if "thinking_control" in row:
                control_path = _safe_text(row["thinking_control"].get("path")).lower()
                control_type = _safe_text(row["thinking_control"].get("control_type")).lower()
                default_effort = _safe_text(row["thinking_control"].get("default"))
                if default_effort and ("effort" in control_path or "effort" in control_type):
                    row["reasoning_effort_default"] = default_effort
                has_profile_value = True
        try:
            profile_caps = profile_thinking_capabilities(model, runtime=runtime, provider_id=provider_id, base_url=base_url)
        except Exception:
            profile_caps = {}
        effort_default = _safe_text(profile_caps.get("effort_default"))
        if effort_default:
            row["reasoning_effort_default"] = effort_default
            has_profile_value = True
        official_effort_default = _safe_text(profile_caps.get("effort_official_default"))
        if official_effort_default:
            row["official_reasoning_effort_default"] = official_effort_default
            has_profile_value = True
        recommended_effort_default = _safe_text(profile_caps.get("effort_recommended_default"))
        if recommended_effort_default:
            row["recommended_reasoning_effort_default"] = recommended_effort_default
            has_profile_value = True
        if has_profile_value:
            rows.append(row)
    return {
        "schema": "mms.model_capability.mmf_official_overrides.v1",
        "source": "mmf_official_overrides",
        "source_layer": "official",
        "source_path": source,
        "checked_at": checked,
        "models": rows,
    }


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
    fields = requested_fields.intersection(_CAPABILITY_TRUTH_REFRESH_FIELDS) or set(_CAPABILITY_TRUTH_REFRESH_FIELDS)
    model_ids = _normalize_model_list(payload.get("models")) or _truth_model_ids_from_provider(provider)
    use_openrouter_catalog = _truthy(payload.get("openrouter_catalog"), False)
    use_mmf_official = _truthy(payload.get("mmf_official_overrides"), False)
    truth_payloads, refresh_reports, warnings = _load_capability_truth_payloads(
        config_path,
        refresh_sources=_truthy(payload.get("refresh_sources"), True) and not use_mmf_official,
    )
    # OpenRouter refresh should mean OpenRouter-only matching; the local snapshot button covers official/approved facts.
    if use_openrouter_catalog or use_mmf_official:
        truth_payloads = []
        refresh_reports = []
    catalog_sources: list[dict[str, Any]] = []
    if use_mmf_official:
        official_truth = _mmf_official_overrides_payload(provider, model_ids)
        official_truth["_source_path"] = _safe_text(official_truth.get("source_path"))
        truth_payloads.insert(0, official_truth)
        catalog_sources.append(
            {
                "source": "mmf_official_overrides",
                "source_layer": "official",
                "transport": "local",
                "source_path": official_truth.get("source_path"),
                "model_count": len(official_truth.get("models") or []),
                "checked_at": official_truth.get("checked_at"),
                "confidence": "mmf_official_profile",
                "note": "MMF 官方覆盖来自仓库维护的 provider-profiles，用于覆盖 OpenRouter catalog 的 provider 参考值。",
            }
        )
    if use_openrouter_catalog and not use_mmf_official:
        source_url = _safe_text(payload.get("openrouter_url") or _OPENROUTER_MODELS_API_URL)
        try:
            timeout = float(payload.get("openrouter_timeout") or 20.0)
        except (TypeError, ValueError):
            timeout = 20.0
        timeout = max(1.0, min(timeout, 45.0))
        try:
            openrouter_payload = _fetch_openrouter_catalog_payload(url=source_url, timeout=timeout)
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
        "source_mode": "mmf_official_overrides" if use_mmf_official else "openrouter_catalog" if catalog_sources else "known_snapshots",
        "fields": [field for field in _CAPABILITY_TRUTH_REFRESH_FIELDS if field in fields],
        "field_config": capability_truth_refresh_fields(),
        "model_count": len(model_ids),
        "matched_model_count": len(model_capabilities),
        "changed_field_count": len(changes),
        "force_apply": bool(use_mmf_official),
        "model_capabilities": model_capabilities,
        "model_sources": model_sources,
        "changes": changes[:200],
        "unmatched_models": unmatched[:80],
        "warnings": warnings,
        "refresh_reports": refresh_reports,
        "catalog_sources": catalog_sources,
        "note": "只使用结构化 source snapshot、approved capabilities、MMF 官方覆盖或 provider catalog 字段；OpenRouter 是快速结构化参考源，不是厂商官方真值；结果只进入页面草稿，保存发布后才生效。",
    }


def _provider_derived_model_aliases(base_models: list[str], provider: dict[str, Any]) -> list[str]:
    try:
        mms_core = _load_mms_core()
        return list(mms_core._derived_model_aliases(base_models, provider))  # noqa: SLF001 - mirror runtime model patching
    except Exception:
        return []


def _provider_effective_model_rows(provider: dict[str, Any], policy_payload: dict[str, Any]) -> list[dict[str, Any]]:
    model_sources: dict[str, str] = {}
    provider_id = _safe_text(provider.get("id"))
    bundle_runtime = bool(provider.get("_mms_bundle_runtime"))
    cached_raw: list[str] = []
    cached_source = "fallback"
    if not bundle_runtime:
        try:
            mms_core = _load_mms_core()
            cached = mms_core._load_probe_file_cache(provider_id, allow_stale=True)  # noqa: SLF001 - UI snapshot only
            if cached:
                cached_raw = _normalize_model_list(cached.get("raw_models") or cached.get("models") or [])
                cached_source = _safe_text(cached.get("base_source") or "remote") or "remote"
        except Exception:
            cached_raw = []
    row_models: list[str] = []
    row_sources: dict[str, str] = {}
    for item in (provider.get("models") if isinstance(provider.get("models"), list) else []):
        model_id = _safe_text(item.get("id") or item.get("model")) if isinstance(item, dict) else _safe_text(item)
        if not model_id:
            continue
        row_models.append(model_id)
        if isinstance(item, dict):
            row_sources.setdefault(model_id, _safe_text(item.get("source") or "manual") or "manual")
    fallback_models = _normalize_model_list(provider.get("fallback_models"))
    base_models = cached_raw or fallback_models or row_models
    for model in base_models:
        source = "approved" if bundle_runtime else (cached_source if cached_raw else ("fallback" if fallback_models else row_sources.get(model, "manual")))
        model_sources.setdefault(model, source)
    for model in _normalize_model_list(provider.get("extra_models")):
        model_sources.setdefault(model, "extra")
    hidden = set(_normalize_model_list(provider.get("hidden_models")))
    hidden_lower = {model.lower() for model in hidden}
    alias_base_models = [model for model in base_models if model.lower() not in hidden_lower]
    for model in _provider_derived_model_aliases(alias_base_models, provider):
        model_sources.setdefault(model, "derived_alias")
    policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    rows: list[dict[str, Any]] = []
    for model_id in sorted(model_sources.keys(), key=lambda item: item.lower()):
        entry = policy_models.get(model_id) if isinstance(policy_models.get(model_id), dict) else {}
        visible = model_id.lower() not in hidden_lower
        if isinstance(entry, dict) and isinstance(entry.get("visible"), bool):
            visible = bool(entry.get("visible")) and visible
        rows.append(
            {
                "id": model_id,
                "source": model_sources.get(model_id) or "manual",
                "visible": visible,
                "favorite": bool(entry.get("favorite")) if isinstance(entry, dict) else False,
                "capabilities": _model_capability_defaults(
                    model_id,
                    entry if isinstance(entry, dict) else {},
                    provider_id=provider_id,
                ),
                "policy_touched": False,
            }
        )
    return rows


def _provider_stale_hidden_models(provider: dict[str, Any], model_rows: list[dict[str, Any]]) -> list[str]:
    current_ids = {str(row.get("id") or "").strip() for row in model_rows if isinstance(row, dict)}
    return [model for model in _normalize_model_list(provider.get("hidden_models")) if model not in current_ids]


def _usage_summary(runtime_kind: str, runtime_id: str) -> dict[str, Any]:
    """Best-effort local usage summary for WebUI display only."""
    runtime_id = _safe_text(runtime_id)
    if not runtime_id:
        return {"launches": 0, "last_used_at": ""}
    try:
        mms_core = _load_mms_core()
        launches, last_used_at = mms_core._usage_summary_for_runtime(runtime_kind, runtime_id)  # noqa: SLF001 - read-only UI summary
        return {"launches": int(launches or 0), "last_used_at": _safe_text(last_used_at)}
    except Exception:
        return {"launches": 0, "last_used_at": ""}


def _runtime_usage_rows(runtime_kind: str, runtime_id: str) -> list[dict[str, Any]]:
    """Mirror the TUI local usage table without exposing unrelated usage.json data."""
    runtime_id = _safe_text(runtime_id)
    if not runtime_id:
        return []

    def count_value(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    try:
        mms_core = _load_mms_core()
        rows = mms_core._usage_rows_for_runtime(runtime_kind, runtime_id)  # noqa: SLF001 - read-only UI report
    except Exception:
        return []
    result: list[dict[str, Any]] = []
    for item in rows if isinstance(rows, list) else []:
        if not isinstance(item, dict):
            continue
        models = item.get("models") if isinstance(item.get("models"), dict) else {}
        model_usage = [
            {"model": _safe_text(model), "launches": count_value(count)}
            for model, count in sorted(models.items(), key=lambda pair: count_value(pair[1]), reverse=True)
            if _safe_text(model)
        ]
        top_models = model_usage[:8]
        result.append(
            {
                "cli": _safe_text(item.get("cli")),
                "runtime_kind": _safe_text(item.get("runtime_kind") or runtime_kind),
                "id": _safe_text(item.get("id") or runtime_id),
                "name": _safe_text(item.get("name")),
                "launches": count_value(item.get("launches")),
                "last_model": _safe_text(item.get("last_model")),
                "last_used_at": _safe_text(item.get("last_used_at")),
                "top_models": top_models,
                "model_usage": model_usage,
            }
        )
    return result


def _provider_summary(provider: dict[str, Any], *, policy_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    provider = provider if isinstance(provider, dict) else {}
    provider_id = _safe_text(provider.get("id"))
    bundle_runtime = bool(provider.get("_mms_bundle_runtime"))
    protocols = provider.get("protocols") if isinstance(provider.get("protocols"), list) else []
    supported_clis = provider.get("supported_clis") if isinstance(provider.get("supported_clis"), list) else []
    models = []
    for key in ("models", "fallback_models", "extra_models"):
        values = provider.get(key)
        if isinstance(values, list):
            models.extend(str(item) for item in values if item)
        elif isinstance(values, dict):
            models.extend(str(item) for item in values.keys() if item)
    creds = _provider_credentials_status(provider_id) if provider_id else {}
    config_openai_base = _safe_text(provider.get("openai_base_url") or provider.get("default_openai_base_url") or provider.get("base_url"))
    config_anthropic_base = _safe_text(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
    credential_openai_base = _safe_text(creds.get("openai_base_url") or creds.get("base_url"))
    credential_anthropic_base = _safe_text(creds.get("anthropic_base_url"))
    openai_base = config_openai_base or credential_openai_base
    anthropic_base = config_anthropic_base or credential_anthropic_base
    api_key = _safe_text(provider.get("api_key") or provider.get("openai_api_key"))
    policy_payload = policy_payload if isinstance(policy_payload, dict) else {}
    model_rows = _provider_effective_model_rows(provider, policy_payload)
    if bundle_runtime:
        for row in model_rows:
            if row.get("source") in {"fallback", "manual"}:
                row["source"] = "approved"
    approved_route_models = _normalize_model_list(provider.get("fallback_models"))
    fallback_models = [] if bundle_runtime else approved_route_models
    extra_models = _normalize_model_list(provider.get("extra_models"))
    return {
        "id": provider_id,
        "original_id": provider_id,
        "name": _safe_text(provider.get("name") or provider_id),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": provider.get("priority", 100),
        "family_priority_overrides": _normalize_family_priority_overrides(provider.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(provider.get("claude_1m_mode") or "auto") or "auto",
        "proxy_configured": bool(_safe_text(provider.get("proxy"))),
        "no_proxy_configured": bool(_safe_text(provider.get("no_proxy"))),
        "timezone": _safe_text(provider.get("timezone")),
        "note": _safe_text(provider.get("note")),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "/models"),
        "protocols": [str(item) for item in protocols if item],
        "supported_clis": [str(item) for item in supported_clis if item],
        "openai_base_url": openai_base,
        "anthropic_base_url": anthropic_base,
        "effective_openai_base_url": openai_base,
        "effective_anthropic_base_url": anthropic_base,
        "config_openai_base_url": config_openai_base,
        "config_anthropic_base_url": config_anthropic_base,
        "openai_base_url_source": "config" if config_openai_base else ("credentials" if credential_openai_base else ""),
        "anthropic_base_url_source": "config" if config_anthropic_base else ("credentials" if credential_anthropic_base else ""),
        "api_key": "",
        "has_api_key": bool(api_key or creds.get("has_api_key") or provider.get("has_api_key")),
        "update_credentials": False,
        "fallback_models": fallback_models,
        "approved_route_models": approved_route_models,
        "extra_models": extra_models,
        "hidden_models": _normalize_model_list(provider.get("hidden_models")),
        "stale_hidden_models": _provider_stale_hidden_models(provider, model_rows),
        "model_count": len(dict.fromkeys(row["id"] for row in model_rows)),
        "models": model_rows,
        "usage": _usage_summary("provider", provider_id),
        "usage_rows": _runtime_usage_rows("provider", provider_id),
    }


def _sanitized_mapping(payload: Any) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        normalized = str(key or "").strip()
        if not normalized:
            continue
        if normalized.lower() in _SECRET_KEYS:
            result[normalized] = _redact(value)
        elif isinstance(value, dict):
            result[normalized] = _sanitized_mapping(value)
        elif isinstance(value, list):
            result[normalized] = [_sanitized_mapping(item) if isinstance(item, dict) else item for item in value]
        else:
            result[normalized] = value
    return result


def _account_summary(account: dict[str, Any], *, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    defaults = defaults if isinstance(defaults, dict) else {}
    account_id = _safe_text(account.get("id"))
    cli_name = _safe_text(account.get("cli"))
    is_default = bool(cli_name and defaults.get(cli_name) == account_id)
    auth_mode = _safe_text(account.get("auth_mode") or account.get("mode") or "oauth")
    is_claude = cli_name == "claude"
    return {
        "id": account_id,
        "name": _safe_text(account.get("name") or account_id),
        "cli": cli_name,
        "enabled": account.get("enabled", True) is not False,
        "priority": _normalize_priority(account.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(account.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(account.get("claude_1m_mode") or "auto") or "auto",
        "auth_mode": auth_mode,
        "is_default": is_default,
        "default_label": cli_name.upper() if is_default else "备选",
        "home_dir_configured": bool(_safe_text(account.get("home_dir"))),
        "proxy_configured": bool(_safe_text(account.get("proxy"))),
        "no_proxy_configured": bool(_safe_text(account.get("no_proxy"))),
        "timezone": _safe_text(account.get("timezone")),
        "note": _safe_text(account.get("note")),
        "status": "configured",
        "is_claude_human_only": is_claude,
        "webui_write_policy": "claude_human_only_locked" if is_claude else "draft_review_confirmed_save",
        "usage": _usage_summary("account", account_id),
        "usage_rows": _runtime_usage_rows("account", account_id),
    }


def _account_defaults(cfg: dict[str, Any]) -> dict[str, str]:
    account_cfg = cfg.get("account") if isinstance(cfg.get("account"), dict) else {}
    raw_defaults = account_cfg.get("defaults") if isinstance(account_cfg.get("defaults"), dict) else account_cfg
    result: dict[str, str] = {}
    if isinstance(raw_defaults, dict):
        for cli, account_id in raw_defaults.items():
            cli_name = _safe_text(cli).lower()
            value = _safe_text(account_id)
            if cli_name and value:
                result[cli_name] = value
    return result


def _account_summaries(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = _account_defaults(cfg)
    rows = []
    for account in cfg.get("accounts") if isinstance(cfg.get("accounts"), list) else []:
        if isinstance(account, dict):
            rows.append(_account_summary(account, defaults=defaults))
    return sorted(
        rows,
        key=lambda item: (
            0 if item.get("is_default") else 1,
            item.get("cli") or "",
            item.get("name") or item.get("id") or "",
        ),
    )


def _account_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    accounts = cfg.get("accounts") if isinstance(cfg.get("accounts"), list) else []
    return {
        _safe_text(account.get("id")): account
        for account in accounts
        if isinstance(account, dict) and _safe_text(account.get("id"))
    }


def _account_review_fields(account: dict[str, Any] | None) -> dict[str, Any]:
    account = account if isinstance(account, dict) else {}
    return {
        "name": _safe_text(account.get("name")),
        "enabled": account.get("enabled", True) is not False,
        "priority": _normalize_priority(account.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(account.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(account.get("claude_1m_mode") or "auto") or "auto",
        "timezone": _safe_text(account.get("timezone")),
        "note": _safe_text(account.get("note")),
    }


def _copy_existing_account(existing: dict[str, Any], account_payload: dict[str, Any]) -> dict[str, Any]:
    account = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    if "name" in account_payload:
        name = _safe_text(account_payload.get("name"))
        current_name = _safe_text(account.get("name") or account.get("id"))
        if name and name != current_name:
            account["name"] = name
    if "enabled" in account_payload:
        enabled = _truthy(account_payload.get("enabled"), True)
        if enabled != (account.get("enabled", True) is not False):
            account["enabled"] = enabled
    if "priority" in account_payload:
        priority = _normalize_priority(account_payload.get("priority"), _normalize_priority(account.get("priority", 100)))
        if priority != _normalize_priority(account.get("priority", 100)):
            account["priority"] = priority
    if "family_priority_overrides" in account_payload:
        overrides = _normalize_family_priority_overrides(account_payload.get("family_priority_overrides"))
        if overrides:
            account["family_priority_overrides"] = overrides
        else:
            account.pop("family_priority_overrides", None)
    if "claude_1m_mode" in account_payload:
        mode = _safe_text(account_payload.get("claude_1m_mode") or "auto")
        normalized = mode if mode in {"auto", "enable", "disable"} else "auto"
        if normalized != "auto" or "claude_1m_mode" in account:
            account["claude_1m_mode"] = normalized
        else:
            account.pop("claude_1m_mode", None)
    if "timezone" in account_payload:
        timezone_name = _safe_text(account_payload.get("timezone"))
        if timezone_name:
            account["timezone"] = timezone_name
        else:
            account.pop("timezone", None)
    if "note" in account_payload:
        note = _safe_text(account_payload.get("note"))
        if note:
            account["note"] = note
        else:
            account.pop("note", None)
    return account


def _apply_account_draft(
    *,
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    draft: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    has_accounts_payload = isinstance(draft.get("accounts"), list)
    has_defaults_payload = isinstance(draft.get("account_defaults"), dict)
    if not has_accounts_payload and not has_defaults_payload:
        return

    current_accounts = current_cfg.get("accounts") if isinstance(current_cfg.get("accounts"), list) else []
    existing_by_id = _account_by_id(current_cfg)
    next_accounts = copy.deepcopy(current_accounts)
    next_by_id = _account_by_id({"accounts": next_accounts})

    if has_accounts_payload:
        seen_payload_ids: set[str] = set()
        for item in draft.get("accounts") or []:
            if not isinstance(item, dict):
                continue
            account_id = _safe_text(item.get("original_id") or item.get("id"))
            if not account_id:
                continue
            if account_id in seen_payload_ids:
                errors.append(f"账号 ID 重复: {account_id}")
                continue
            seen_payload_ids.add(account_id)
            existing = existing_by_id.get(account_id)
            if not existing:
                errors.append(f"账号 {account_id} 不在当前配置中；WebUI 当前不创建新账号。")
                continue
            updated = _copy_existing_account(existing, item)
            if _safe_text(existing.get("cli")).lower() == "claude" and _mapping_digest(_account_review_fields(existing)) != _mapping_digest(_account_review_fields(updated)):
                errors.append(f"Claude account `{account_id}` 是 human-only；WebUI 当前只允许查看和生成 review，不会保存 Claude account 编辑。")
                continue
            next_by_id[account_id] = updated

        next_accounts = [next_by_id.get(_safe_text(account.get("id")), account) for account in next_accounts if isinstance(account, dict)]
        next_cfg["accounts"] = next_accounts

    if has_defaults_payload:
        defaults = _account_defaults(current_cfg)
        payload_defaults = draft.get("account_defaults") if isinstance(draft.get("account_defaults"), dict) else {}
        accounts_after = _account_by_id({"accounts": next_cfg.get("accounts") if isinstance(next_cfg.get("accounts"), list) else current_accounts})
        for cli, raw_account_id in payload_defaults.items():
            cli_name = _safe_text(cli).lower()
            if cli_name not in _ALLOWED_CLIS:
                warnings.append(f"账号默认 CLI 不支持: {cli_name}")
                continue
            account_id = _safe_text(raw_account_id)
            before_default = defaults.get(cli_name, "")
            if cli_name == "claude" and before_default != account_id:
                errors.append("Claude 默认账号是 human-only；WebUI 当前不会保存 Claude account default 变化。")
                continue
            if not account_id:
                defaults.pop(cli_name, None)
                continue
            account = accounts_after.get(account_id)
            if not account:
                errors.append(f"默认账号 {cli_name} -> {account_id} 不存在。")
                continue
            if _safe_text(account.get("cli")).lower() != cli_name:
                errors.append(f"默认账号 {cli_name} -> {account_id} 的 CLI 不匹配。")
                continue
            defaults[cli_name] = account_id
        if defaults:
            next_cfg["account"] = {"defaults": defaults}
        else:
            next_cfg.pop("account", None)


def _load_balance_summary(cfg: dict[str, Any] | None) -> dict[str, Any]:
    section = (cfg or {}).get("load_balance") if isinstance(cfg, dict) else {}
    section = section if isinstance(section, dict) else {}
    profiles = section.get("profiles") if isinstance(section.get("profiles"), dict) else {}
    rows: list[dict[str, Any]] = []
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        profile_name = _safe_text(name)
        slots: dict[str, dict[str, str]] = {}
        for slot_name in ("heavy", "medium", "light"):
            raw_slot = profile.get(slot_name)
            if isinstance(raw_slot, dict):
                slots[slot_name] = {
                    "model": _safe_text(raw_slot.get("model") or raw_slot.get("model_id")),
                    "provider_id": _safe_text(raw_slot.get("provider_id") or raw_slot.get("provider")),
                }
            else:
                slots[slot_name] = {"model": _safe_text(raw_slot), "provider_id": ""}
        rows.append(
            {
                "name": profile_name,
                "label": _safe_text(profile.get("label") or profile_name),
                "is_default": profile_name == _safe_text(section.get("default")),
                "slots": slots,
            }
        )
    rows.sort(key=lambda item: (not bool(item.get("is_default")), str(item.get("name") or "")))
    return {
        "schema": "mms.setup_web.load_balance_summary.v1",
        "default_profile": _safe_text(section.get("default")),
        "profile_count": len(rows),
        "profiles": rows,
        "write_policy": "deprecated_read_only_compat",
        "history_write_policy": "deprecated_no_webui_iteration",
        "note": "load_balance 已下线；WebUI 仅保留旧配置只读摘要，不再提供编辑入口。",
    }


def _normalize_load_balance_draft(value: Any, *, errors: list[str] | None = None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    raw_profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    profiles: dict[str, Any] = {}
    for item in raw_profiles:
        if not isinstance(item, dict):
            continue
        name = _slug(item.get("name") or item.get("label"), "")
        if not name:
            if errors is not None:
                errors.append("load_balance profile 缺少 name。")
            continue
        if name in profiles:
            if errors is not None:
                errors.append(f"load_balance profile 重复: {name}")
            continue
        profile: dict[str, Any] = {"label": _safe_text(item.get("label") or name), "slots": ["heavy", "medium", "light"]}
        slots = item.get("slots") if isinstance(item.get("slots"), dict) else {}
        for slot_name in ("heavy", "medium", "light"):
            slot = slots.get(slot_name) if isinstance(slots, dict) else {}
            if not isinstance(slot, dict):
                slot = {"model": slot}
            model = _safe_text(slot.get("model") or slot.get("model_id"))
            provider_id = _safe_text(slot.get("provider_id") or slot.get("provider"))
            if not model:
                continue
            slot_payload = {"model": model}
            if provider_id:
                slot_payload["provider"] = provider_id
            profile[slot_name] = slot_payload
        if "heavy" not in profile:
            if errors is not None:
                errors.append(f"load_balance profile `{name}` 缺少 heavy model。")
            continue
        profiles[name] = profile
    default_name = _slug(payload.get("default_profile") or payload.get("default"), "")
    if default_name and default_name not in profiles:
        if errors is not None:
            errors.append(f"load_balance.default `{default_name}` 不存在。")
        default_name = ""
    if not default_name and profiles:
        default_name = next(iter(profiles))
    return {"default": default_name, "profiles": profiles} if profiles else {}


def _normalize_agent_model_overrides(value: Any) -> dict[str, dict[str, str]]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, dict[str, str]] = {}
    for agent, entry in raw.items():
        agent_id = _safe_text(agent)
        if not agent_id:
            continue
        provider_id = ""
        model = ""
        if isinstance(entry, dict):
            provider_id = _safe_text(entry.get("provider_id") or entry.get("provider"))
            model = _safe_text(entry.get("model") or entry.get("model_id"))
        elif isinstance(entry, str):
            model = _safe_text(entry)
        if model:
            payload = {"model": model}
            if provider_id:
                payload["provider_id"] = provider_id
            result[agent_id] = payload
    return result


def _normalize_opencode_review_host(value: Any) -> dict[str, list[str]]:
    if isinstance(value, dict) and "opencode" in value:
        cfg = value
    elif isinstance(value, dict) and ("review" in value or "review_host" in value):
        cfg = {"opencode": value}
    elif isinstance(value, dict):
        cfg = {"opencode": {"review": {"host": value}}}
    else:
        cfg = {}
    normalized = opencode_review_host_config(cfg)
    return {
        "primary_models": list(normalized.get("primary_models") or []),
        "fallback_models": list(normalized.get("fallback_models") or []),
    }


def _opencode_review_host_defaults() -> dict[str, list[str]]:
    specs = {str(spec.get("key") or ""): spec for spec in opencode_lite_pro_specs(OPENCODE_REVIEW_PROFILE_ID)}
    return {
        "primary_models": list(specs.get("builder_primary", {}).get("models") or []),
        "fallback_models": list(specs.get("builder_fallback", {}).get("models") or []),
    }


def _normalize_opencode_committee_presets(opencode_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose the 5 committee tiers with resolved {host, members, channel} for the web UI.

    Each row merges user config `opencode.committee.presets.{tier}` over the
    built-in defaults. `is_default` marks tiers whose resolved value still equals
    the built-in default (no user override). Read-only display data; the frontend
    persists edits into `state.opencode.committee.presets[tier]`.
    """
    rows: list[dict[str, Any]] = []
    for tier in OPENCODE_COMMITTEE_TIERS:
        resolved = opencode_committee_preset_config({"opencode": opencode_cfg or {}}, tier)
        builtin = OPENCODE_COMMITTEE_TIER_DEFAULTS.get(tier, {})
        members = list(resolved.get("members") or [])
        default_members = list(builtin.get("members") or [])
        member_channels = _normalize_channel_map(resolved.get("member_channels"), members)
        default_member_channels = _normalize_channel_map(builtin.get("member_channels"), default_members)
        host_primary_channel = resolved.get("host_primary_channel") or resolved.get("channel") or "direct"
        host_fallback_channel = resolved.get("host_fallback_channel") or resolved.get("channel") or "direct"
        default_host_primary_channel = builtin.get("host_primary_channel") or builtin.get("channel") or "direct"
        default_host_fallback_channel = builtin.get("host_fallback_channel") or builtin.get("channel") or "direct"
        user_value = None
        if isinstance(opencode_cfg, dict):
            committee = opencode_cfg.get("committee") if isinstance(opencode_cfg.get("committee"), dict) else {}
            presets = committee.get("presets") if isinstance(committee.get("presets"), dict) else {}
            if isinstance(presets.get(tier), dict):
                user_value = presets.get(tier)
        is_default = (
            (resolved.get("host_primary") or "") == (builtin.get("host_primary") or "")
            and (resolved.get("host_fallback") or "") == (builtin.get("host_fallback") or "")
            and members == default_members
            and (resolved.get("channel") or "direct") == (builtin.get("channel") or "direct")
            and host_primary_channel == default_host_primary_channel
            and host_fallback_channel == default_host_fallback_channel
            and member_channels == default_member_channels
        )
        rows.append(
            {
                "tier": tier,
                "host_primary": resolved.get("host_primary") or "",
                "host_fallback": resolved.get("host_fallback") or "",
                "members": members,
                "channel": resolved.get("channel") or "direct",
                "host_primary_channel": host_primary_channel,
                "host_fallback_channel": host_fallback_channel,
                "member_channels": member_channels,
                "is_default": is_default,
                "user_value": user_value,
                "default_host_primary": builtin.get("host_primary") or "",
                "default_host_fallback": builtin.get("host_fallback") or "",
                "default_members": default_members,
                "default_channel": builtin.get("channel") or "direct",
                "default_host_primary_channel": default_host_primary_channel,
                "default_host_fallback_channel": default_host_fallback_channel,
                "default_member_channels": default_member_channels,
            }
        )
    return rows


def _normalize_opencode_committee_presets_input(payload: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    """Convert the frontend committee_presets list into a `{tier: {host, members, channel}}` config dict.

    Rows flagged `is_default` (or with no host/members) are dropped so the config
    only records explicit user overrides. Invalid rows append an error message.
    """
    result: dict[str, dict[str, Any]] = {}
    raw = payload.get("committee_presets")
    items = raw if isinstance(raw, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        tier = _safe_text(item.get("tier"))
        if tier not in OPENCODE_COMMITTEE_TIERS:
            continue
        if _truthy(item.get("is_default"), False):
            continue
        members = _normalize_model_list(item.get("members"))
        host_primary = _safe_text(item.get("host_primary"))
        host_fallback = _safe_text(item.get("host_fallback"))
        preset = {
            "host_primary": host_primary,
            "host_fallback": host_fallback,
            "members": members,
            "channel": _safe_text(item.get("channel")) or "direct",
            "host_primary_channel": _safe_text(item.get("host_primary_channel")) if host_primary else "",
            "host_fallback_channel": _safe_text(item.get("host_fallback_channel")) if host_fallback else "",
            "member_channels": _normalize_channel_map(item.get("member_channels"), members),
        }
        preset = {key: value for key, value in preset.items() if value}
        for message in validate_opencode_committee_tier_preset(tier, preset):
            errors.append(f"committee 档位 {tier}: {message}")
        if preset:
            result[tier] = preset
    return result


def _opencode_surface_profile_id(value: Any, *, default: str = "agent") -> str:
    raw = _safe_text(value)
    if not raw:
        return default
    canonical = normalize_opencode_profile_id(raw)
    for option in OPENCODE_PROFILE_OPTIONS:
        option_id = _safe_text(option.get("id"))
        option_profile = normalize_opencode_profile_id(option.get("profile_id") or option_id)
        if raw == option_id or canonical == option_profile:
            return option_id
    return default


def _opencode_agent_preset(agent_id: str, category: str = "") -> str:
    text = _safe_text(agent_id).lower()
    category = _safe_text(category).lower()
    if text == "committee-host":
        return "builder"
    if text.startswith("committee-") or "委员会" in category:
        return "reviewer"
    if "vision" in text or category == "vision":
        return "vision"
    if "bughunt" in text or "找茬" in category:
        return "bughunt"
    if "explore" in text or "探索" in category:
        return "explore"
    if "review" in text or "compliance" in text or "审查" in category:
        return "reviewer"
    if "spec" in text:
        return "spec"
    if "executor" in text:
        return "executor"
    if "fixer" in text:
        return "fixer"
    return "builder"


def _opencode_roster_defaults(profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(_opencode_agent_catalog(profile_id), 1):
        agent_id = _safe_text(row.get("agent"))
        if not agent_id:
            continue
        defaults[agent_id] = {
            "enabled": True,
            "preset": _opencode_agent_preset(agent_id, _safe_text(row.get("category"))),
            "priority": index * 10,
            "custom": False,
        }
    return defaults


def _normalize_opencode_agent_roster(value: Any, *, profile_id: str = "agent") -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    defaults = _opencode_roster_defaults(profile_id)
    result: dict[str, dict[str, Any]] = {}
    for agent, entry in raw.items():
        agent_id = _safe_text(agent)
        if not agent_id or not isinstance(entry, dict):
            continue
        is_required_builder = agent_id in _OPENCODE_REQUIRED_BUILDER_AGENTS
        default = defaults.get(agent_id, {"enabled": True, "preset": "builder", "custom": False} if is_required_builder else {})
        preset = _safe_text(entry.get("preset") or entry.get("category") or default.get("preset") or "explore").lower()
        if preset not in _OPENCODE_ROSTER_PRESETS:
            preset = "explore"
        payload: dict[str, Any] = {"preset": preset}
        custom = bool(entry.get("custom") is True or (agent_id not in defaults and not is_required_builder))
        if custom:
            payload["custom"] = True
        if "enabled" in entry:
            enabled = _truthy(entry.get("enabled"), True)
            payload["enabled"] = True if is_required_builder and not enabled else enabled
        elif custom:
            payload["enabled"] = True
        provider_id = _safe_text(entry.get("provider_id") or entry.get("provider"))
        model = _safe_text(entry.get("model") or entry.get("model_id"))
        if provider_id and (model or custom):
            payload["provider_id"] = provider_id
        if model:
            payload["model"] = model
        try:
            priority = int(entry.get("priority"))
        except (TypeError, ValueError):
            priority = 0
        if priority > 0:
            payload["priority"] = priority
        description = _safe_text(entry.get("description"))
        if description:
            payload["description"] = description[:240]
        prompt = _safe_text(entry.get("prompt"))
        if prompt:
            payload["prompt"] = prompt[:4000]

        comparable = dict(payload)
        if not custom:
            if comparable.get("enabled", True) is True:
                comparable.pop("enabled", None)
            if comparable.get("preset") == default.get("preset"):
                comparable.pop("preset", None)
            if comparable.get("priority") == default.get("priority"):
                comparable.pop("priority", None)
        if comparable or custom:
            result[agent_id] = payload
    return result


def _strip_empty_provider_model_lists(cfg: dict[str, Any]) -> dict[str, Any]:
    """Keep WebUI saves from materializing absent empty fallback model lists."""
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if "fallback_models" in provider and not _normalize_model_list(provider.get("fallback_models")):
            provider.pop("fallback_models", None)
    return cfg


def _opencode_committee_catalog_from_config(opencode_cfg: dict[str, Any], existing_agents: set[str]) -> list[dict[str, Any]]:
    """Expose configured committee members without baking model families into the profile."""
    if not isinstance(opencode_cfg, dict):
        return []
    committee = opencode_cfg.get("committee") if isinstance(opencode_cfg.get("committee"), dict) else {}
    roster = opencode_cfg.get("agent_roster") if isinstance(opencode_cfg.get("agent_roster"), dict) else {}
    selected_agents = [
        _safe_text(agent)
        for agent in (committee.get("selected_agents") if isinstance(committee.get("selected_agents"), list) else [])
    ]
    if not selected_agents:
        selected_agents = [
            _safe_text(agent)
            for agent in roster
            if _safe_text(agent).startswith("committee-") and _safe_text(agent) not in {"committee-host", "committee-host-pro"}
        ]
    if not selected_agents:
        for model in _normalize_model_list(committee.get("models")):
            slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
            if slug:
                selected_agents.append(f"committee-{slug}")

    rows: list[dict[str, Any]] = []
    for agent in selected_agents:
        if not agent or agent in existing_agents or agent in {"committee-host", "committee-host-pro"}:
            continue
        entry = roster.get(agent) if isinstance(roster.get(agent), dict) else {}
        model = _safe_text(entry.get("model"))
        if not model and agent.startswith("committee-"):
            model = agent.removeprefix("committee-")
        rows.append(
            {
                "agent": agent,
                "route_key": f"custom_{agent}",
                "category": "委员会",
                "preset": _opencode_agent_preset(agent, "委员会"),
                "priority": 1000 + len(rows) * 10,
                "default_models": [model] if model else [],
                "fallback_allowed": False,
                "custom": True,
            }
        )
        existing_agents.add(agent)
    return rows


def _opencode_agent_catalog(profile_id: str = "agent", opencode_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    surface_profile = _opencode_surface_profile_id(profile_id, default="agent")
    if surface_profile in {"raw", "omo"}:
        return []
    try:
        mms_core = _load_mms_core()
        specs = mms_core._opencode_lite_pro_specs(profile_id)  # noqa: SLF001 - setup UI mirrors launcher roster
    except Exception:
        specs = ()
    rows = []
    seen_agents = set()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        agent = _safe_text(spec.get("agent"))
        if not agent or agent in seen_agents:
            continue
        seen_agents.add(agent)
        key = _safe_text(spec.get("key"))
        models = _normalize_model_list(spec.get("models"))
        category = "执行/协调"
        if agent == "committee-host":
            category = "执行/协调"
        elif agent.startswith("committee-"):
            category = "委员会"
        elif "explore" in agent:
            category = "探索"
        elif "bughunt" in agent:
            category = "找茬"
        elif "vision" in agent:
            category = "Vision"
        elif "review" in agent or "compliance" in agent:
            category = "审查"
        elif "executor" in agent or "fixer" in agent:
            category = "执行"
        rows.append(
            {
                "agent": agent,
                "route_key": key,
                "category": category,
                "preset": _opencode_agent_preset(agent, category),
                "priority": len(rows) * 10 + 10,
                "default_models": models,
                "fallback_allowed": spec.get("gpt_fallback", True) is not False,
            }
        )
    if surface_profile == "committee":
        rows.extend(_opencode_committee_catalog_from_config(opencode_cfg or {}, seen_agents))
    return rows


def build_config_snapshot(
    cfg: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return a redacted, UI-friendly config snapshot; never mutates config."""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    cfg = _hydrate_preview_config_from_latest_bundle(cfg, config_path=config_path, command_name=command_name)
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    policy_path = _policy_path_for_config(config_path)
    policy_payload = _load_json_file(policy_path)
    provider_rows = [_provider_summary(item, policy_payload=policy_payload) for item in providers if isinstance(item, dict)]
    vision_sidecar = cfg.get("vision_sidecar") if isinstance(cfg.get("vision_sidecar"), dict) else {}
    rescue = cfg.get("rescue") if isinstance(cfg.get("rescue"), dict) else {}
    ui_cfg = cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}
    provider_default = _safe_text((cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}).get("default"))
    presets = cfg.get("presets") if isinstance(cfg.get("presets"), dict) else {}
    coding_preset = presets.get("coding") if isinstance(presets.get("coding"), dict) else {}
    opencode_cfg = cfg.get("opencode") if isinstance(cfg.get("opencode"), dict) else {}
    opencode_agent_models = _normalize_agent_model_overrides(opencode_cfg.get("agent_models") or opencode_cfg.get("agent_model_overrides"))
    opencode_profile = _opencode_surface_profile_id(opencode_cfg.get("default_profile") or "agent")
    opencode_profiles = opencode_profile_selection_ids()
    opencode_agent_catalogs = {
        profile: _opencode_agent_catalog(profile, opencode_cfg=opencode_cfg)
        for profile in opencode_profiles
    }
    opencode_agent_catalog = opencode_agent_catalogs.get(opencode_profile) or _opencode_agent_catalog(opencode_profile, opencode_cfg=opencode_cfg)
    opencode = {
        "default_profile": opencode_profile,
        "recommended_profile": "agent",
        "profiles": opencode_profiles,
        "review": {"host": _normalize_opencode_review_host(opencode_cfg)},
        "review_host_defaults": _opencode_review_host_defaults(),
        "committee_presets": _normalize_opencode_committee_presets(opencode_cfg),
        "agent_models": opencode_agent_models,
        "agent_roster": _normalize_opencode_agent_roster(opencode_cfg.get("agent_roster"), profile_id=opencode_profile),
        "agent_catalog": opencode_agent_catalog,
        "agent_catalogs": opencode_agent_catalogs,
        "roster_presets": list(_OPENCODE_ROSTER_PRESETS),
        "vision_agents": ["mobius-vision-mimo", "mobius-vision-kimi", "mobius-vision-qwen"],
        "executor": "mobius-executor-gpt54",
        "release_gate": "mobius-reviewer-gpt55",
    }
    recommendations = []
    if not provider_rows:
        recommendations.append("先添加至少一个通道，然后再配置模型列表和 fallback。")
    if not vision_sidecar:
        recommendations.append("如果常用模型不直接支持图片，建议配置 vision sidecar。")
    if not _safe_text(rescue.get("fallback_model")):
        recommendations.append("建议先设置 rescue fallback model，失败时可以稳定交接。")
    if not any(row.get("anthropic_base_url") for row in provider_rows):
        recommendations.append("CN / dual-protocol 模型建议保留 Anthropic /v1/messages 路径，避免 cache 退化。")
    tui_webui_mapping = _tui_webui_mapping()
    return {
        "schema": "mms.setup_web.snapshot.v2",
        "mode": "interactive_audited_save",
        "command": command_name,
        "version_info": _version_info_for_snapshot(command_name),
        "setup_flow": build_setup_flow(),
        "test_contracts": build_test_contracts(),
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "providers": provider_rows,
        "provider_default": provider_default or (provider_rows[0]["id"] if provider_rows else ""),
        "model_families": _known_model_families(),
        "accounts": _account_summaries(cfg),
        "account_defaults": _account_defaults(cfg),
        "account_write_policy": {
            "status": "draft_review_confirmed_save",
            "claude": "human_only_locked",
            "allowed_fields": ["name", "enabled", "priority", "family_priority_overrides", "timezone", "note", "claude_1m_mode", "default_non_claude"],
            "blocked_fields": ["login", "remove", "rename/home_dir", "proxy", "no_proxy", "claude_default", "claude_metadata"],
        },
        "settings_actions": _settings_action_cards(),
        "webui_capability_coverage": _webui_capability_coverage(),
        "tui_webui_mapping": tui_webui_mapping,
        "tui_webui_mapping_summary": _tui_webui_mapping_summary(tui_webui_mapping),
        "load_balance": _load_balance_summary(cfg),
        "vision_sidecar": _sanitized_mapping(vision_sidecar),
        "rescue": _sanitized_mapping(rescue),
        "ui": {"language": _safe_text(ui_cfg.get("language") or "zh") or "zh"},
        "runtime": {
            "preferred_cli": _safe_text(coding_preset.get("cli") or "opencode"),
            "coding_preset_model": _safe_text(coding_preset.get("model")),
        },
        "opencode": opencode,
        "policy_summary": {
            "path": policy_path,
            "model_count": len((policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}) or {}),
            "project_count": len((policy_payload.get("projects") if isinstance(policy_payload.get("projects"), dict) else {}) or {}),
        },
        "model_source_status": _model_source_status_for_snapshot(config_path, command_name=command_name),
        "consumer_bundle_status": _consumer_bundle_status_for_snapshot(config_path, command_name=command_name),
        "config_v2_promotion_plan": _config_v2_promotion_plan_for_snapshot(config_path, command_name=command_name),
        "config_v2_release_readiness": _config_v2_release_readiness_for_snapshot(config_path, command_name=command_name),
        "session_assets": build_session_assets_snapshot(
            cfg,
            config_path=config_path,
            preferences_path=preferences_path,
            command_name=command_name,
        ),
        "references": build_reference_cards(),
        "recommendations": recommendations,
        "snippets": build_config_snippets(),
        "save_contract": {
            "requires_diff_preview": True,
            "requires_confirm_save": True,
            "confirm_phrase": "保存配置",
            "preview_confirm_phrase": "写入预览DB",
            "writes": ["config.toml", "credentials.sh(仅当输入新 key 并勾选更新凭据)", "model-policy.json"],
            "stable_legacy_writes": ["config.toml", "credentials.sh(仅当输入新 key 并勾选更新凭据)", "model-policy.json"],
            "preview_v2_writes": [
                "registry/model-registry.sqlite(candidate revisions)",
                "secrets/webui-secrets.json(仅当输入新 key)",
                "generated/model-registry.latest-approved.json",
                "generated/model-routes.json",
                "generated/model-policy.effective.json",
                "generated/provider-profiles.generated.json",
            ],
            "safety": "stable legacy 保存走 lock + backup + audit；preview root 使用 DB candidate + generated bundle 发布并校验；页面不会回显真实 API Key。",
        },
    }


def build_config_snippets() -> dict[str, str]:
    """Manual snippets shown in WebUI; callers choose whether to apply."""
    vision = """# config.toml: vision sidecar
[vision_sidecar]
enabled = true
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "mimo-direct-anthropic"
model = "mimo-v2.5"

[[vision_sidecar.candidates]]
provider_id = "direct-kimi"
model = "K2.6"

[[vision_sidecar.candidates]]
provider_id = "direct-qwen"
model = "qwen3.6-plus"
""".strip()
    rescue = """# config.toml: rescue fallback
[rescue]
fallback_model = "deepseek-v4-flash"
fallback_cli = "codex"
hot_fallback_enabled = false
""".strip()
    opencode = """# OpenCode launch examples
mms opencode --profile agent
mms opencode --profile omo
mms opencode-smoke --profile agent --health-summary
""".strip()
    policy = """// model-policy.json: visibility and capability overrides
{
  "models": {
    "qwen3.6-plus": {
      "visible": true,
      "favorite": true,
      "capabilities": {
        "text": true,
        "vision": true,
        "tool_use": true,
        "reasoning": true,
        "thinking": true,
        "supports_thinking": true,
        "one_m_context": true,
        "context_window_tokens": 1000000,
        "cache_sensitive_transport": true
      }
    },
    "retired-or-noisy-model": {
      "visible": false,
      "hide_in": ["mms", "hive", "pilot", "ant", "mobius"]
    }
  },
  "projects": {
    "mms": {
      "default_visible": true,
      "hidden_models": ["retired-or-noisy-model"],
      "favorite_models": ["qwen3.6-plus"]
    }
  }
}
""".strip()
    preferred_cli = """# config.toml: practical WebUI target
[presets.coding]
cli = "opencode"
model = "gpt-5.5"

[opencode]
default_profile = "agent"

[opencode.agent_models.mobius-explore-glm]
provider_id = "domestic"
model = "glm-5-turbo"
""".strip()
    return {
        "vision_sidecar": vision,
        "rescue": rescue,
        "opencode": opencode,
        "model_policy": policy,
        "preferred_cli": preferred_cli,
    }


def build_setup_flow() -> list[dict[str, Any]]:
    """Product IA for the visual setup flow; kept in snapshot for WebUI/Markdown."""
    return [
        {
            "id": "channel",
            "title": "1. 通道配置",
            "summary": "配置通道名称、URL、Key、协议和模型列表接口，然后拉取模型。",
            "fields": ["provider_id", "display_name", "openai_base_url", "anthropic_base_url", "api_key", "models_endpoint", "protocols"],
            "actions": ["fetch_models", "test_models_endpoint", "save_credentials_with_audit"],
        },
        {
            "id": "model_inventory",
            "title": "2. 模型列表",
            "summary": "查看当前通道拉取结果，隐藏噪音模型，像 NewAPI 一样手动补充当前通道模型。",
            "fields": ["visible", "favorite", "hidden_models", "manual_models", "model_aliases"],
            "actions": ["hide_selected", "add_manual_model", "copy_selected"],
        },
        {
            "id": "capability",
            "title": "3. 能力标记",
            "summary": "手动标记 text、vision/multimodal、tool use、reasoning、long context 和 cache-sensitive。",
            "fields": ["text", "vision", "long_context", "tool_use", "reasoning", "cache_sensitive"],
            "actions": ["apply_known_defaults", "save_model_policy"],
        },
        {
            "id": "validation",
            "title": "4. 模型测试",
            "summary": "测试拉取、指定模型 ping/pong、可选 simple chat，并记录 request path evidence。",
            "fields": ["stream", "protocol", "request_url", "request_path", "latency", "error"],
            "actions": ["test_list", "test_selected_model", "test_chat"],
        },
        {
            "id": "fallbacks",
            "title": "5. Fallback 设置",
            "summary": "设置 rescue fallback、vision sidecar/fallback 模型和 hot fallback 开关。",
            "fields": ["fallback_model", "fallback_cli", "vision_model", "vision_candidates", "hot_fallback_enabled"],
            "actions": ["preview_config_diff", "run_non_live_smoke"],
        },
        {
            "id": "runtime",
            "title": "6. 运行默认值",
            "summary": "设置 首选 CLI、coding preset 和 OpenCode Multi-Agent profile。",
            "fields": ["preferred_cli", "opencode_profile", "executor", "reviewer", "explore", "vision_agents"],
            "actions": ["preview_launch", "save_audited"],
        },
        {
            "id": "session_assets",
            "title": "7. Session 能力面板",
            "summary": "区分 MMS dynamic 与 Global/inherited 的 skills、MCP、hooks，并可单独保存 preferences.toml 偏好。",
            "fields": ["cli", "kind", "origin", "path", "disable_key", "default_state"],
            "actions": ["filter_by_cli", "filter_by_origin", "save_preferences", "copy_preferences_snippet"],
        },
    ]


def build_test_contracts() -> list[dict[str, str]]:
    return [
        {
            "id": "models_endpoint",
            "title": "模型列表测试",
            "method": "GET /models 或配置的 models_endpoint",
            "result": "模型 ID、endpoint 状态、协议提示和脱敏 transport evidence",
        },
        {
            "id": "model_ping",
            "title": "指定模型 smoke",
            "method": "通过选定 protocol 发送最小非流式 prompt",
            "result": "ok/fail、latency、response shape、request_url/request_path",
        },
        {
            "id": "simple_chat",
            "title": "简单 chat 测试",
            "method": "一条 user message，限制短回答",
            "result": "回复预览 + cache_transport_evidence.v1",
        },
        {
            "id": "vision_probe",
            "title": "Vision probe",
            "method": "仅当模型标记 vision-capable 时发小图片/OCR 请求",
            "result": "确认直接 vision 支持，或建议启用 sidecar fallback",
        },
    ]


def build_reference_cards() -> list[dict[str, str]]:
    return [
        {
            "title": "模型配置契约",
            "path": "docs/MODEL_CONFIG_CONTRACT.md",
            "summary": "Router / Lineup / Profile / Policy 四份配置的职责边界。",
        },
        {
            "title": "用户偏好 allowlist",
            "path": "docs/MMS_USER_PREFERENCES.md",
            "summary": "哪些日常偏好适合 preferences.toml，哪些真实配置必须 人工确认。",
        },
        {
            "title": "OpenCode Lite Pro",
            "path": "docs/OPENCODE_LITE_LAUNCHER.md",
            "summary": "OpenSpec Multi、GPT executor、国产只读 explore/bug-hunt 的当前策略。",
        },
        {
            "title": "Session assets / preferences",
            "path": "docs/MMS_USER_PREFERENCES.md",
            "summary": "解释 MMS dynamic skills/MCP/hooks、global config 边界和 preferences.toml allowlist。",
        },
        {
            "title": "能力校准快照",
            "path": "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.md",
            "summary": "当前模型能力证据输入，WebUI 默认能力标记会参考这些本地事实。",
        },
    ]


def build_setup_markdown(snapshot: dict[str, Any]) -> str:
    providers = snapshot.get("providers") or []
    lines = [
        "# MMS Setup Configuration",
        "",
        f"- mode: `{snapshot.get('mode')}`",
        f"- config: `{snapshot.get('paths', {}).get('config') or '-'}`",
        f"- model_policy: `{snapshot.get('paths', {}).get('model_policy') or '-'}`",
        f"- preferences: `{snapshot.get('paths', {}).get('preferences') or '-'}`",
        "",
        "## Providers",
    ]
    if providers:
        for item in providers:
            lines.append(
                "- `{id}` enabled={enabled} protocols={protocols} clis={clis} models={models} key={key}".format(
                    id=item.get("id") or "-",
                    enabled=item.get("enabled"),
                    protocols=",".join(item.get("protocols") or []) or "-",
                    clis=",".join(item.get("supported_clis") or []) or "-",
                    models=item.get("model_count", 0),
                    key="set" if item.get("has_api_key") else "missing",
                )
            )
    else:
        lines.append("- No providers found.")
    flow = snapshot.get("setup_flow") or []
    if flow:
        lines.extend(["", "## Visual Setup Flow"])
        for item in flow:
            lines.append(f"- **{item.get('title')}**: {item.get('summary')}")
            actions = ", ".join(item.get("actions") or [])
            if actions:
                lines.append(f"  - actions: `{actions}`")
    tests = snapshot.get("test_contracts") or []
    if tests:
        lines.extend(["", "## Model Test Contracts"])
        for item in tests:
            lines.append(f"- **{item.get('title')}**: {item.get('method')} -> {item.get('result')}")
    snippets = snapshot.get("snippets") or {}
    lines.extend(["", "## Vision Sidecar", "", "```toml", snippets.get("vision_sidecar", ""), "```"])
    lines.extend(["", "## Rescue Fallback", "", "```toml", snippets.get("rescue", ""), "```"])
    lines.extend(["", "## Model Visibility And Capability Policy", "", "```json", snippets.get("model_policy", ""), "```"])
    lines.extend(["", "## 首选 CLI", "", "```toml", snippets.get("preferred_cli", ""), "```"])
    lines.extend(["", "## OpenCode", "", "```bash", snippets.get("opencode", ""), "```"])
    recommendations = snapshot.get("recommendations") or []
    if recommendations:
        lines.extend(["", "## Recommendations"])
        lines.extend(f"- {item}" for item in recommendations)
    lines.extend(
        [
            "",
            "## Safety",
            "- WebUI writes are interactive only: preview diff, check confirmation, then save.",
            "- Saves use MMS config lock, backup, and config audit log.",
            "- API keys are accepted only in POST bodies and are never echoed back.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _migration_cryptography_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401

        return True
    except Exception:
        return False


def _migration_openssl_available() -> bool:
    return bool(shutil.which("openssl"))


def _migration_secret_crypto_backend() -> str:
    if _migration_cryptography_available():
        return "cryptography"
    if _migration_openssl_available():
        return "openssl"
    return "none"


def _migration_crypto_available() -> bool:
    return _migration_secret_crypto_backend() != "none"


def _migration_derive_key(password: str, salt: bytes, *, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)


def _migration_encrypt_json_aesgcm(payload: dict[str, Any], password: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iterations = 220_000
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _migration_derive_key(password, salt, iterations=iterations)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, _MIGRATION_BUNDLE_SCHEMA.encode("utf-8"))
    return {
        "schema": _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA,
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": iterations,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_schema": "mms.config_migration_credentials_payload.v1",
    }


def _migration_decrypt_json_aesgcm(box: dict[str, Any], password: str) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    iterations = int(box.get("iterations") or 0)
    if iterations < 100_000:
        raise ValueError("迁移包凭据 KDF 强度过低，已拒绝导入。")
    salt = base64.b64decode(str(box.get("salt_b64") or ""))
    nonce = base64.b64decode(str(box.get("nonce_b64") or ""))
    ciphertext = base64.b64decode(str(box.get("ciphertext_b64") or ""))
    key = _migration_derive_key(password, salt, iterations=iterations)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, _MIGRATION_BUNDLE_SCHEMA.encode("utf-8"))
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("迁移包凭据解密后不是对象。")
    return payload


def _migration_openssl_passfile(password: str) -> str:
    fd, path = tempfile.mkstemp(prefix="mms-migration-pass-", text=False)
    try:
        os.chmod(path, 0o600)
        os.write(fd, password.encode("utf-8"))
        os.close(fd)
        fd = -1
        return path
    except Exception:
        try:
            if fd >= 0:
                os.close(fd)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise


def _migration_run_openssl_enc(data: bytes, password: str, *, decrypt: bool, iterations: int) -> bytes:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("当前 Python 环境缺少 cryptography，且找不到 openssl，不能处理加密 API Key。")
    passfile = _migration_openssl_passfile(password)
    try:
        cmd = [
            openssl,
            "enc",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            str(iterations),
            "-md",
            "sha256",
            "-salt",
            "-pass",
            f"file:{passfile}",
        ]
        if decrypt:
            cmd.insert(2, "-d")
        proc = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    finally:
        try:
            os.unlink(passfile)
        except OSError:
            pass
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip().splitlines()
        message = detail[-1] if detail else "openssl enc failed"
        raise ValueError(f"OpenSSL 加密后备失败：{message}")
    return proc.stdout


def _migration_openssl_mac_payload(box: dict[str, Any]) -> bytes:
    fields = {
        "schema": _safe_text(box.get("schema")),
        "algorithm": _safe_text(box.get("algorithm")),
        "kdf": _safe_text(box.get("kdf")),
        "iterations": int(box.get("iterations") or 0),
        "mac_salt_b64": _safe_text(box.get("mac_salt_b64")),
        "ciphertext_b64": _safe_text(box.get("ciphertext_b64")),
        "plaintext_schema": _safe_text(box.get("plaintext_schema")),
        "aad": _MIGRATION_BUNDLE_SCHEMA,
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _migration_encrypt_json_openssl(payload: dict[str, Any], password: str) -> dict[str, Any]:
    iterations = 220_000
    mac_salt = os.urandom(16)
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = _migration_run_openssl_enc(plaintext, password, decrypt=False, iterations=iterations)
    box = {
        "schema": _MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA,
        "algorithm": "AES-256-CBC+HMAC-SHA256",
        "kdf": "OpenSSL-PBKDF2-HMAC-SHA256 + PBKDF2-HMAC-SHA256-MAC",
        "iterations": iterations,
        "mac_salt_b64": base64.b64encode(mac_salt).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "plaintext_schema": "mms.config_migration_credentials_payload.v1",
    }
    mac_key = _migration_derive_key(password, mac_salt, iterations=iterations)
    box["hmac_b64"] = base64.b64encode(
        hmac.new(mac_key, _migration_openssl_mac_payload(box), hashlib.sha256).digest()
    ).decode("ascii")
    return box


def _migration_decrypt_json_openssl(box: dict[str, Any], password: str) -> dict[str, Any]:
    iterations = int(box.get("iterations") or 0)
    if iterations < 100_000:
        raise ValueError("迁移包凭据 KDF 强度过低，已拒绝导入。")
    mac_salt = base64.b64decode(str(box.get("mac_salt_b64") or ""))
    ciphertext = base64.b64decode(str(box.get("ciphertext_b64") or ""))
    expected = base64.b64decode(str(box.get("hmac_b64") or ""))
    mac_key = _migration_derive_key(password, mac_salt, iterations=iterations)
    actual = hmac.new(mac_key, _migration_openssl_mac_payload(box), hashlib.sha256).digest()
    if not expected or not hmac.compare_digest(actual, expected):
        raise ValueError("迁移密码错误或凭据已损坏。")
    plaintext = _migration_run_openssl_enc(ciphertext, password, decrypt=True, iterations=iterations)
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("迁移包凭据解密后不是对象。")
    return payload


def _migration_encrypt_json(payload: dict[str, Any], password: str) -> dict[str, Any]:
    backend = _migration_secret_crypto_backend()
    if backend == "cryptography":
        return _migration_encrypt_json_aesgcm(payload, password)
    if backend == "openssl":
        return _migration_encrypt_json_openssl(payload, password)
    raise ValueError("当前 Python 环境缺少 cryptography，且找不到 openssl，不能导出包含 API Key 的加密迁移包。")


def _migration_decrypt_json(box: dict[str, Any], password: str) -> dict[str, Any]:
    if not isinstance(box, dict):
        raise ValueError("迁移包凭据格式不受支持。")
    schema = box.get("schema")
    if schema == _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA:
        if not _migration_cryptography_available():
            raise ValueError("这个迁移包使用 AES-GCM，需要当前 Python 环境安装 cryptography 才能解密。")
        return _migration_decrypt_json_aesgcm(box, password)
    if schema == _MIGRATION_CREDENTIAL_BOX_OPENSSL_SCHEMA:
        if not _migration_openssl_available():
            raise ValueError("这个迁移包使用 OpenSSL 后备加密；当前环境找不到 openssl，不能解密。")
        return _migration_decrypt_json_openssl(box, password)
    raise ValueError("迁移包凭据格式不受支持。")


def _migration_config_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    provider_rows = snapshot.get("providers") if isinstance(snapshot.get("providers"), list) else []
    providers: list[dict[str, Any]] = []
    for row in provider_rows:
        if not isinstance(row, dict):
            continue
        provider_id = _safe_text(row.get("id"))
        if not provider_id:
            continue
        provider = {
            "id": provider_id,
            "name": _safe_text(row.get("name") or provider_id),
            "enabled": row.get("enabled", True) is not False,
            "role": _safe_text(row.get("role") or "auto"),
            "priority": _normalize_priority(row.get("priority", 100)),
            "family_priority_overrides": _normalize_family_priority_overrides(row.get("family_priority_overrides")),
            "claude_1m_mode": _safe_text(row.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(row.get("timezone")),
            "note": _safe_text(row.get("note")),
            "models_endpoint": _safe_text(row.get("models_endpoint") or "/models"),
            "protocols": [str(item) for item in (row.get("protocols") or []) if item],
            "supported_clis": [str(item) for item in (row.get("supported_clis") or []) if item],
            "openai_base_url": _safe_text(row.get("openai_base_url") or row.get("effective_openai_base_url")),
            "anthropic_base_url": _safe_text(row.get("anthropic_base_url") or row.get("effective_anthropic_base_url")),
            "fallback_models": _normalize_model_list(row.get("approved_route_models") or row.get("fallback_models")),
            "extra_models": _normalize_model_list(row.get("extra_models")),
            "hidden_models": _normalize_model_list(row.get("hidden_models")),
            "models": [],
        }
        model_rows = []
        for model_row in row.get("models") if isinstance(row.get("models"), list) else []:
            if not isinstance(model_row, dict):
                continue
            model_id = _safe_text(model_row.get("id") or model_row.get("model"))
            if not model_id or _safe_text(model_row.get("source")) == "derived_alias":
                continue
            model_rows.append(
                {
                    "id": model_id,
                    "source": _safe_text(model_row.get("source") or "migration"),
                    "visible": model_row.get("visible", True) is not False,
                    "favorite": model_row.get("favorite") is True,
                }
            )
        if model_rows:
            provider["models"] = model_rows
        else:
            provider.pop("models", None)
        providers.append({key: value for key, value in provider.items() if value not in ("", {}, [])})

    raw_config: dict[str, Any] = {}
    if providers:
        raw_config["providers"] = providers
    provider_default = _safe_text(snapshot.get("provider_default"))
    if provider_default:
        raw_config["provider"] = {"default": provider_default}
    for key in ("rescue", "vision_sidecar", "ui", "opencode"):
        value = snapshot.get(key)
        if isinstance(value, dict) and value:
            raw_config[key] = _sanitize_for_output(value)
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    if runtime:
        coding: dict[str, Any] = {}
        preferred_cli = _safe_text(runtime.get("preferred_cli"))
        coding_model = _safe_text(runtime.get("coding_preset_model"))
        if preferred_cli:
            coding["cli"] = preferred_cli
        if coding_model:
            coding["model"] = coding_model
        if coding:
            raw_config["presets"] = {"coding": coding}
    return raw_config


def _migration_payload_config_from_cfg(cfg: dict[str, Any], *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    snapshot = build_config_snapshot(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    exported = _migration_config_from_snapshot(snapshot)
    for key in ("load_balance",):
        value = cfg.get(key) if isinstance(cfg.get(key), dict) else {}
        if value:
            exported[key] = _sanitize_for_output(value)
    return exported


def _migration_preferences_payload(config_path: str = "", preferences_path: str = "") -> dict[str, Any]:
    target_path = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    prefs = _load_preferences_raw(target_path)
    payload: dict[str, Any] = {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    disabled_clis = _normalize_model_list(launch.get("disabled_clis"))
    if disabled_clis:
        payload.setdefault("launch", {})["disabled_clis"] = disabled_clis
    session_surfaces = prefs.get("session_surfaces") if isinstance(prefs.get("session_surfaces"), dict) else {}
    disabled = session_surfaces.get("disabled") if isinstance(session_surfaces.get("disabled"), dict) else {}
    normalized_disabled: dict[str, list[str]] = {}
    for key in ("skills", "mcp", "hooks"):
        values = _normalize_model_list(disabled.get(key))
        if values:
            normalized_disabled[key] = values
    if normalized_disabled:
        payload["session_surfaces"] = {"disabled": normalized_disabled}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    managed_root = _safe_text(assets.get("managed_root"))
    if managed_root:
        payload["assets"] = {"managed_root": managed_root}
    return payload


def _migration_collect_credentials(cfg: dict[str, Any]) -> list[dict[str, str]]:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    mms_core = _load_mms_core()
    credentials: list[dict[str, str]] = []
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        provider_id = _safe_text(provider.get("id"))
        if not provider_id:
            continue
        try:
            raw = mms_core.load_provider_credentials(provider_id)
        except Exception:
            raw = {}
        api_key = _safe_text(raw.get("api_key") or provider.get("api_key"))
        openai_api_key = _safe_text(raw.get("openai_api_key") or provider.get("openai_api_key"))
        if not api_key and not openai_api_key:
            continue
        openai_base = _safe_text(raw.get("openai_base_url") or raw.get("base_url") or provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url"))
        anthropic_base = _safe_text(raw.get("anthropic_base_url") or provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url"))
        credentials.append(
            {
                "provider_id": provider_id,
                "base_url": (openai_base or anthropic_base).rstrip("/"),
                "openai_base_url": openai_base.rstrip("/"),
                "anthropic_base_url": anthropic_base.rstrip("/"),
                "api_key": api_key or openai_api_key,
                "openai_api_key": openai_api_key,
            }
        )
    return credentials


def build_migration_export(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    cfg = _hydrate_preview_config_from_latest_bundle(cfg, config_path=config_path, command_name=command_name)
    include_credentials = _truthy(payload.get("include_credentials") or payload.get("include_secrets"), False)
    password = _safe_text(payload.get("password") or payload.get("passphrase"))
    warnings = [
        "OAuth / Claude / Codex 原生登录态不会进入迁移包；另一台机器仍需人工登录原生 CLI。",
        "Claude account、proxy/no_proxy、home_dir 等 human-only 配置不会被自动迁移。",
    ]
    policy_path = _policy_path_for_config(config_path)
    bundle: dict[str, Any] = {
        "schema": _MIGRATION_BUNDLE_SCHEMA,
        "created_at": _now_iso(),
        "source": {
            "command": command_name,
            "version": _version_info_for_snapshot(command_name),
            "config_root": _config_root_for_snapshot(config_path),
            "config_path": os.path.abspath(os.path.expanduser(config_path)) if config_path else "",
            "preferences_path": os.path.abspath(os.path.expanduser(preferences_path)) if preferences_path else "",
        },
        "security": {
            "contains_credentials": False,
            "credential_box": "none",
            "oauth_state": "excluded",
            "native_cli_auth": "excluded",
            "redaction": "api_key/password/token fields are never stored in payload",
        },
        "payload": {
            "config": _migration_payload_config_from_cfg(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name),
            "model_policy": _load_json_file(policy_path),
            "preferences": _migration_preferences_payload(config_path=config_path, preferences_path=preferences_path),
        },
        "warnings": warnings,
    }
    credential_count = 0
    if include_credentials:
        crypto_backend = _migration_secret_crypto_backend()
        if len(password) < 8:
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": ["包含 API Key 的迁移包必须输入至少 8 位迁移密码。"],
                "crypto_available": _migration_crypto_available(),
                "crypto_backend": crypto_backend,
            }
        if crypto_backend == "none":
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": ["当前 Python 环境缺少 cryptography，且找不到 openssl，不能导出包含 API Key 的加密迁移包。"],
                "crypto_available": False,
                "crypto_backend": crypto_backend,
            }
        credentials = _migration_collect_credentials(cfg)
        credential_count = len(credentials)
        credential_payload = {
            "schema": "mms.config_migration_credentials_payload.v1",
            "created_at": _now_iso(),
            "credentials": credentials,
        }
        try:
            encrypted_credentials = _migration_encrypt_json(credential_payload, password)
        except Exception as exc:
            return {
                "ok": False,
                "schema": "mms.config_migration_export_result.v1",
                "status": "blocked",
                "errors": [f"API Key 加密失败：{type(exc).__name__}: {exc}"],
                "crypto_available": _migration_crypto_available(),
                "crypto_backend": crypto_backend,
            }
        bundle["encrypted_credentials"] = encrypted_credentials
        bundle["security"]["contains_credentials"] = bool(credentials)
        bundle["security"]["credential_box"] = (
            "encrypted-aesgcm"
            if encrypted_credentials.get("schema") == _MIGRATION_CREDENTIAL_BOX_AESGCM_SCHEMA
            else "encrypted-openssl-cbc-hmac"
        )
        bundle["security"]["credential_crypto_backend"] = crypto_backend
    model_policy = (bundle.get("payload") or {}).get("model_policy") if isinstance(bundle.get("payload"), dict) else {}
    summary = {
        "providers": len((bundle.get("payload", {}).get("config", {}).get("providers") if isinstance(bundle.get("payload"), dict) else []) or []),
        "policy_models": len((model_policy.get("models") if isinstance(model_policy, dict) else {}) or {}),
        "preferences": bool((bundle.get("payload") or {}).get("preferences")),
        "credentials": credential_count,
        "encrypted_credentials": include_credentials,
    }
    bundle["summary"] = summary
    return {
        "ok": True,
        "schema": "mms.config_migration_export_result.v1",
        "status": "ready",
        "bundle": bundle,
        "summary": summary,
        "crypto_available": _migration_crypto_available(),
        "crypto_backend": _migration_secret_crypto_backend(),
        "filename": f"mms-config-migration-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    }


def _parse_migration_bundle(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    raw = payload.get("bundle") or payload.get("migration_bundle") or payload.get("text") or payload.get("raw")
    errors: list[str] = []
    bundle: Any = {}
    if isinstance(raw, dict):
        bundle = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            errors.append("请先粘贴或上传迁移包 JSON。")
        else:
            try:
                bundle = json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(f"迁移包 JSON 解析失败：{exc}")
    else:
        errors.append("请提供迁移包 JSON。")
    if not isinstance(bundle, dict):
        errors.append("迁移包必须是 JSON 对象。")
        bundle = {}
    if bundle and bundle.get("schema") != _MIGRATION_BUNDLE_SCHEMA:
        errors.append(f"迁移包 schema 不支持：{bundle.get('schema') or '-'}")
    return bundle, errors


def _migration_decrypted_credentials(bundle: dict[str, Any], password: str) -> tuple[list[dict[str, str]], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    box = bundle.get("encrypted_credentials") if isinstance(bundle.get("encrypted_credentials"), dict) else {}
    if not box:
        return [], warnings, errors
    if not password:
        errors.append("这个迁移包包含加密 API Key；请输入迁移密码后再预览或导入。")
        return [], warnings, errors
    try:
        payload = _migration_decrypt_json(box, password)
    except Exception as exc:
        errors.append(f"迁移密码错误或凭据已损坏：{type(exc).__name__}: {exc}")
        return [], warnings, errors
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), list) else []
    result: list[dict[str, str]] = []
    for item in credentials:
        if not isinstance(item, dict):
            continue
        provider_id = _safe_text(item.get("provider_id"))
        api_key = _safe_text(item.get("api_key"))
        openai_api_key = _safe_text(item.get("openai_api_key"))
        if not provider_id or (not api_key and not openai_api_key):
            continue
        result.append(
            {
                "provider_id": provider_id,
                "base_url": _safe_text(item.get("base_url")).rstrip("/"),
                "openai_base_url": _safe_text(item.get("openai_base_url")).rstrip("/"),
                "anthropic_base_url": _safe_text(item.get("anthropic_base_url")).rstrip("/"),
                "api_key": api_key or openai_api_key,
                "openai_api_key": openai_api_key,
            }
        )
    if not result:
        warnings.append("迁移包声明了加密凭据，但没有可导入的 provider API Key。")
    return result, warnings, errors


def _safe_local_command_name(command_name: str = "mms") -> str:
    command = _safe_text(command_name or "mms") or "mms"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", command):
        return "mms"
    return command


def _migration_start_status_from_snapshot(snapshot: dict[str, Any], *, command_name: str = "mms", disabled_clis_override: list[str] | None = None) -> dict[str, Any]:
    command = _safe_local_command_name(command_name)
    providers = [item for item in (snapshot.get("providers") if isinstance(snapshot.get("providers"), list) else []) if isinstance(item, dict)]
    enabled = [item for item in providers if item.get("enabled", True) is not False]
    missing_key = [_safe_text(item.get("id")) for item in enabled if not item.get("has_api_key")]
    missing_url = [
        _safe_text(item.get("id"))
        for item in enabled
        if not _safe_text(item.get("openai_base_url") or item.get("anthropic_base_url") or item.get("effective_openai_base_url") or item.get("effective_anthropic_base_url"))
    ]
    missing_models = [_safe_text(item.get("id")) for item in enabled if int(item.get("model_count") or 0) <= 0]
    ready_providers = [
        _safe_text(item.get("id"))
        for item in enabled
        if item.get("has_api_key")
        and int(item.get("model_count") or 0) > 0
        and _safe_text(item.get("openai_base_url") or item.get("anthropic_base_url") or item.get("effective_openai_base_url") or item.get("effective_anthropic_base_url"))
    ]
    source_status = snapshot.get("model_source_status") if isinstance(snapshot.get("model_source_status"), dict) else {}
    root = source_status.get("root") if isinstance(source_status.get("root"), dict) else {}
    bundle = source_status.get("generated_bundle") if isinstance(source_status.get("generated_bundle"), dict) else {}
    preview_root = root.get("mode") == "preview"
    bundle_verified = bool(bundle.get("verified"))
    bundle_runtime_ready = bundle.get("runtime_ready") is True
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    preferred_cli = _safe_text(runtime.get("preferred_cli") or "opencode")
    coding_model = _safe_text(runtime.get("coding_preset_model"))
    disabled_clis = list(disabled_clis_override or [])
    if not disabled_clis:
        session_assets = snapshot.get("session_assets") if isinstance(snapshot.get("session_assets"), dict) else {}
        cli_visibility = session_assets.get("cli_visibility") if isinstance(session_assets.get("cli_visibility"), dict) else {}
        disabled_clis = _normalize_model_list(cli_visibility.get("disabled"))
    blockers: list[dict[str, Any]] = []
    if not enabled:
        blockers.append({"id": "no_enabled_provider", "label": "没有启用通道", "detail": "请先导入或启用至少一个 provider。"})
    if missing_key:
        blockers.append({"id": "missing_api_key", "label": "缺少 API Key", "detail": "这些通道没有 Key，无法直接开始工作。", "providers": missing_key})
    if missing_url:
        blockers.append({"id": "missing_base_url", "label": "缺少 Base URL", "detail": "这些通道没有 OpenAI/Anthropic Base URL。", "providers": missing_url})
    if missing_models:
        blockers.append({"id": "missing_models", "label": "缺少模型", "detail": "这些通道没有可用模型，请拉取或手动添加模型。", "providers": missing_models})
    if preview_root and not bundle_verified:
        blockers.append({"id": "bundle_not_verified", "label": "预览 Bundle 未验证", "detail": "preview root 需要 latest-approved bundle 验证通过后更稳。"})
    if preferred_cli in disabled_clis:
        blockers.append({"id": "preferred_cli_disabled", "label": "首选 CLI 已默认关闭", "detail": f"{preferred_cli} 在 preferences 中被关闭；启动后请换 CLI 或先打开。"})
    provider_ready = bool(bundle_runtime_ready if preview_root else ready_providers)
    ready_to_work = provider_ready and preferred_cli not in disabled_clis
    start_command = command
    return {
        "schema": "mms.config_migration_start_status.v1",
        "ready_to_work": ready_to_work,
        "start_command": start_command,
        "copy_command": start_command,
        "preferred_cli": preferred_cli,
        "coding_model": coding_model,
        "command_name": command,
        "target_mode": _safe_text(root.get("mode") or ("preview" if preview_root else "stable")),
        "config_root": _safe_text(root.get("config_root") or source_status.get("config_root") or _config_root_for_snapshot(snapshot.get("paths", {}).get("config") if isinstance(snapshot.get("paths"), dict) else "")),
        "terminal_launch_available": sys.platform == "darwin",
        "provider_count": len(providers),
        "enabled_provider_count": len(enabled),
        "ready_provider_ids": ready_providers,
        "missing_api_key_provider_ids": missing_key,
        "missing_base_url_provider_ids": missing_url,
        "missing_model_provider_ids": missing_models,
        "preview_bundle": {
            "verified": bundle_verified,
            "runtime_ready": bundle_runtime_ready,
            "status": _safe_text(bundle.get("status")),
            "missing_api_key_count": int(bundle.get("router_missing_api_key_count") or 0),
            "missing_base_url_count": int(bundle.get("router_missing_base_url_count") or 0),
        },
        "blockers": blockers,
        "notes": [
            "按钮只启动当前 MMS 命令，不会迁移 OAuth / Claude / Codex 原生登录态。",
            "如果 API Key 已随加密迁移包导入，通常可以直接打开终端运行。",
        ],
    }


def build_migration_start_status(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    del payload
    snapshot = build_config_snapshot(current_cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    prefs = _load_preferences_raw(_preferences_target_path(config_path=config_path, preferences_path=preferences_path))
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    disabled_clis = _normalize_model_list(launch.get("disabled_clis"))
    return _migration_start_status_from_snapshot(snapshot, command_name=command_name, disabled_clis_override=disabled_clis)


def start_migration_work_session(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    status = build_migration_start_status(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    command = _safe_text(status.get("start_command") or _safe_local_command_name(command_name))
    cwd = os.getcwd()
    shell_command = f"cd {shlex.quote(cwd)} && {command}"
    if sys.platform != "darwin":
        return {
            "ok": False,
            "schema": "mms.config_migration_start_result.v1",
            "status": "unsupported_platform",
            "errors": ["当前系统不支持从 WebUI 自动打开终端；可以复制启动命令手动运行。"],
            "command": command,
            "shell_command": shell_command,
            "start_status": status,
        }
    script = f'tell application "Terminal" to activate\ntell application "Terminal" to do script {json.dumps(shell_command)}'
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.config_migration_start_result.v1",
            "status": "failed",
            "errors": [f"打开终端失败：{type(exc).__name__}: {exc}"],
            "command": command,
            "shell_command": shell_command,
            "start_status": status,
        }
    return {
        "ok": True,
        "schema": "mms.config_migration_start_result.v1",
        "status": "started",
        "command": command,
        "shell_command": shell_command,
        "cwd": cwd,
        "start_status": status,
    }


def _migration_provider_payload(provider: dict[str, Any]) -> dict[str, Any]:
    provider_id = _safe_text(provider.get("id"))
    result = {
        "id": provider_id,
        "original_id": provider_id,
        "name": _safe_text(provider.get("name") or provider_id),
        "enabled": provider.get("enabled", True) is not False,
        "role": _safe_text(provider.get("role") or "auto"),
        "priority": _normalize_priority(provider.get("priority", 100)),
        "family_priority_overrides": _normalize_family_priority_overrides(provider.get("family_priority_overrides")),
        "claude_1m_mode": _safe_text(provider.get("claude_1m_mode") or "auto") or "auto",
        "timezone": _safe_text(provider.get("timezone")),
        "note": _safe_text(provider.get("note")),
        "models_endpoint": _safe_text(provider.get("models_endpoint") or "/models"),
        "protocols": [str(item) for item in (provider.get("protocols") or []) if item],
        "supported_clis": [str(item) for item in (provider.get("supported_clis") or []) if item],
        "openai_base_url": _safe_text(provider.get("openai_base_url") or provider.get("default_openai_base_url") or provider.get("base_url")),
        "anthropic_base_url": _safe_text(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url")),
        "fallback_models": _normalize_model_list(provider.get("fallback_models") or provider.get("approved_route_models")),
        "extra_models": _normalize_model_list(provider.get("extra_models")),
        "hidden_models": _normalize_model_list(provider.get("hidden_models")),
    }
    models = []
    for row in provider.get("models") if isinstance(provider.get("models"), list) else []:
        if isinstance(row, dict):
            model_id = _safe_text(row.get("id") or row.get("model"))
            if model_id:
                models.append({"id": model_id, "visible": row.get("visible", True) is not False})
        else:
            model_id = _safe_text(row)
            if model_id:
                models.append({"id": model_id, "visible": True})
    if models:
        result["models"] = models
    return {key: value for key, value in result.items() if value not in ("", {}, [])}


def _migration_preferences_apply_payload(bundle: dict[str, Any]) -> dict[str, Any]:
    prefs = ((bundle.get("payload") or {}).get("preferences") if isinstance(bundle.get("payload"), dict) else {}) or {}
    prefs = prefs if isinstance(prefs, dict) else {}
    launch = prefs.get("launch") if isinstance(prefs.get("launch"), dict) else {}
    session_surfaces = prefs.get("session_surfaces") if isinstance(prefs.get("session_surfaces"), dict) else {}
    assets = prefs.get("assets") if isinstance(prefs.get("assets"), dict) else {}
    return {
        "disabled_clis": _normalize_model_list(launch.get("disabled_clis")),
        "disabled": (session_surfaces.get("disabled") if isinstance(session_surfaces.get("disabled"), dict) else {}) or {},
        "assets": {
            "managed_enabled": bool(_safe_text(assets.get("managed_root"))),
            "managed_root": _safe_text(assets.get("managed_root")),
        },
    }


def _migration_draft_from_bundle(current_cfg: dict[str, Any], bundle: dict[str, Any], credentials: list[dict[str, str]], *, config_path: str = "") -> dict[str, Any]:
    policy_payload = _load_json_file(_policy_path_for_config(config_path))
    current_providers = {
        _safe_text(row.get("id")): _migration_provider_payload(row)
        for row in [_provider_summary(item, policy_payload=policy_payload) for item in current_cfg.get("providers", []) if isinstance(item, dict)]
        if _safe_text(row.get("id"))
    }
    payload = bundle.get("payload") if isinstance(bundle.get("payload"), dict) else {}
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    incoming_providers = config.get("providers") if isinstance(config.get("providers"), list) else []
    for provider in incoming_providers:
        if not isinstance(provider, dict):
            continue
        normalized = _migration_provider_payload(provider)
        provider_id = _safe_text(normalized.get("id"))
        if provider_id:
            current_providers[provider_id] = normalized
    for update in credentials:
        provider_id = _safe_text(update.get("provider_id"))
        if not provider_id:
            continue
        provider = current_providers.setdefault(provider_id, {"id": provider_id, "name": provider_id, "enabled": True})
        provider["update_credentials"] = True
        provider["api_key"] = _safe_text(update.get("api_key"))
        provider["openai_api_key"] = _safe_text(update.get("openai_api_key"))
        if _safe_text(update.get("openai_base_url")):
            provider["openai_base_url"] = _safe_text(update.get("openai_base_url"))
        if _safe_text(update.get("anthropic_base_url")):
            provider["anthropic_base_url"] = _safe_text(update.get("anthropic_base_url"))
        if not _safe_text(provider.get("openai_base_url")) and not _safe_text(provider.get("anthropic_base_url")) and _safe_text(update.get("base_url")):
            provider["openai_base_url"] = _safe_text(update.get("base_url"))

    draft: dict[str, Any] = {"providers": list(current_providers.values())}
    provider_default = _safe_text((config.get("provider") if isinstance(config.get("provider"), dict) else {}).get("default"))
    if provider_default:
        draft["provider_default"] = provider_default
    for key in ("rescue", "vision_sidecar", "ui", "opencode", "load_balance"):
        value = config.get(key) if isinstance(config.get(key), dict) else {}
        if value:
            draft[key] = value
    presets = config.get("presets") if isinstance(config.get("presets"), dict) else {}
    coding = presets.get("coding") if isinstance(presets.get("coding"), dict) else {}
    runtime: dict[str, Any] = {}
    if _safe_text(coding.get("cli")):
        runtime["preferred_cli"] = _safe_text(coding.get("cli"))
    if _safe_text(coding.get("model")):
        runtime["coding_preset_model"] = _safe_text(coding.get("model"))
    if runtime:
        draft["runtime"] = runtime
    model_policy = payload.get("model_policy") if isinstance(payload.get("model_policy"), dict) else {}
    if model_policy:
        draft["model_policy_import"] = model_policy
    return draft


def _merge_model_policy_import(policy_before: dict[str, Any], incoming: Any) -> dict[str, Any]:
    if not isinstance(incoming, dict) or not incoming:
        return policy_before
    original = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy.setdefault("version", incoming.get("version") if isinstance(incoming.get("version"), int) else 1)
    policy.setdefault("description", "User-maintained model visibility and preference policy. MMS never stores provider secrets here.")
    for section in ("models", "projects"):
        src = incoming.get(section) if isinstance(incoming.get(section), dict) else {}
        if not src:
            continue
        dst = policy.setdefault(section, {})
        if not isinstance(dst, dict):
            dst = {}
            policy[section] = dst
        for key, value in src.items():
            key_text = _safe_text(key)
            if not key_text:
                continue
            dst[key_text] = _sanitize_for_output(value)
    if _mapping_digest(policy) != _mapping_digest(original):
        policy["updated_at"] = _now_iso()
    elif isinstance(original, dict) and "updated_at" in original:
        policy["updated_at"] = original["updated_at"]
    return policy


def _build_migration_import_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    current_cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    current_cfg = _hydrate_preview_config_from_latest_bundle(current_cfg, config_path=config_path, command_name=command_name)
    bundle, parse_errors = _parse_migration_bundle(payload)
    warnings = [
        "导入不会迁移 OAuth / Claude / Codex 原生登录态；只处理 WebUI 可审计配置、model-policy、preferences 和可选加密 API Key。",
        "导入采用 merge 策略：同 ID provider 覆盖，当前机器独有 provider 默认保留。",
    ]
    credentials: list[dict[str, str]] = []
    if not parse_errors:
        credentials, cred_warnings, cred_errors = _migration_decrypted_credentials(bundle, _safe_text(payload.get("password") or payload.get("passphrase")))
        warnings.extend(cred_warnings)
        parse_errors.extend(cred_errors)
    if parse_errors:
        return {
            "ok": False,
            "schema": "mms.config_migration_import_plan.v1",
            "status": "blocked",
            "errors": parse_errors,
            "warnings": warnings,
        }
    draft = _migration_draft_from_bundle(current_cfg, bundle, credentials, config_path=config_path)
    config_plan = build_config_plan(current_cfg, {"draft": draft}, config_path=config_path, preferences_path=preferences_path, include_secrets=True, command_name=command_name)
    pref_payload = _migration_preferences_apply_payload(bundle)
    pref_plan = build_preferences_plan(pref_payload, config_path=config_path, preferences_path=preferences_path)
    ok = bool(config_plan.get("ok") and pref_plan.get("ok"))
    errors = list(config_plan.get("errors") or [])
    summary = {
        "providers": (config_plan.get("summary") or {}).get("providers", 0),
        "credential_updates": len(credentials),
        "policy_models": (config_plan.get("summary") or {}).get("policy_models", 0),
        "preferences_will_write": bool(pref_plan.get("will_write")),
        "target_root": _config_root_for_snapshot(config_path),
        "target_mode": (_model_source_status_for_snapshot(config_path, command_name=command_name).get("root") or {}).get("mode", ""),
    }
    return {
        "ok": ok,
        "schema": "mms.config_migration_import_plan.v1",
        "status": "planned" if ok else "blocked",
        "errors": errors,
        "warnings": [*warnings, *(config_plan.get("warnings") or [])],
        "bundle_summary": bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {},
        "summary": summary,
        "draft": draft,
        "config_plan": config_plan,
        "preferences_payload": pref_payload,
        "preferences_plan": pref_plan,
        "diffs": {
            "config_toml": (config_plan.get("diffs") or {}).get("config_toml", ""),
            "model_policy_json": (config_plan.get("diffs") or {}).get("model_policy_json", ""),
            "credentials": (config_plan.get("diffs") or {}).get("credentials", ""),
            "preferences_toml": pref_plan.get("diff", ""),
        },
    }


def build_migration_import_preview(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    plan = _build_migration_import_plan(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    return _sanitize_for_output(plan)


def apply_migration_import(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_migration"), False):
        return {"ok": False, "schema": "mms.config_migration_import_result.v1", "status": "blocked", "errors": ["导入前必须勾选确认导入。"]}
    if _safe_text(payload.get("confirm_phrase")) != "导入配置":
        return {"ok": False, "schema": "mms.config_migration_import_result.v1", "status": "blocked", "errors": ["确认文字必须输入：导入配置"]}
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:migration-import"
    plan = _build_migration_import_plan(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    if not plan.get("ok"):
        return {
            "ok": False,
            "schema": "mms.config_migration_import_result.v1",
            "status": "blocked",
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "plan": _sanitize_for_output(plan),
        }
    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    if _is_preview_config_root(config_path, command_name=command_name):
        config_result = apply_registry_v2_preview_plan(
            current_cfg,
            {
                "draft": draft,
                "confirm_v2_preview": True,
                "confirm_phrase": "写入预览DB",
                "reason": reason,
            },
            config_path=config_path,
            preferences_path=preferences_path,
        )
    else:
        config_result = apply_config_plan(
            current_cfg,
            {
                "draft": draft,
                "confirm_save": True,
                "confirm_phrase": "保存配置",
                "reason": reason,
            },
            config_path=config_path,
            preferences_path=preferences_path,
        )
    preferences_result: dict[str, Any] = {"ok": True, "status": "no_change"}
    pref_plan = plan.get("preferences_plan") if isinstance(plan.get("preferences_plan"), dict) else {}
    if config_result.get("ok") and pref_plan.get("will_write"):
        pref_payload = dict(plan.get("preferences_payload") if isinstance(plan.get("preferences_payload"), dict) else {})
        pref_payload.update(
            {
                "confirm_preferences": True,
                "confirm_phrase": "保存偏好",
                "reason": f"{reason}:preferences",
            }
        )
        preferences_result = apply_preferences_plan(pref_payload, config_path=config_path, preferences_path=preferences_path)
    ok = bool(config_result.get("ok") and preferences_result.get("ok"))
    applied_cfg = ((plan.get("config_plan") or {}).get("config") if isinstance(plan.get("config_plan"), dict) else {}) or current_cfg
    start_status = build_migration_start_status(
        applied_cfg if isinstance(applied_cfg, dict) else current_cfg,
        {},
        config_path=config_path,
        preferences_path=preferences_path,
        command_name=command_name,
    )
    return _sanitize_for_output(
        {
            "ok": ok,
            "schema": "mms.config_migration_import_result.v1",
            "status": "imported" if ok else "failed",
            "summary": plan.get("summary") or {},
            "warnings": plan.get("warnings") or [],
            "config_result": config_result,
            "preferences_result": preferences_result,
            "start_status": start_status,
        }
    )


def _extract_draft(payload: dict[str, Any]) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else payload
    return draft if isinstance(draft, dict) else {}


def _route_model_rows_from_payload(provider_payload: dict[str, Any]) -> list[dict[str, Any]]:
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


def _copy_existing_provider(
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
    provider["role"] = role if role in _ALLOWED_ROLES else "auto"
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
    provider["protocols"] = _normalize_choice_list(provider_payload.get("protocols"), _ALLOWED_PROTOCOLS, _ALLOWED_PROTOCOLS)
    provider["supported_clis"] = _normalize_choice_list(provider_payload.get("supported_clis"), _ALLOWED_CLIS, ("claude", "codex", "opencode"))
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


def _strip_implicit_provider_timezone_defaults(
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


def _build_model_policy_from_draft(policy_before: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    original_policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy = copy.deepcopy(policy_before) if isinstance(policy_before, dict) else {}
    policy.setdefault("version", 1)
    policy.setdefault("description", "User-maintained model visibility and preference policy. MMS never stores provider secrets here.")
    models = policy.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        policy["models"] = models
    providers = draft.get("providers") if isinstance(draft.get("providers"), list) else []

    def sanitize_capability_source(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key in ("source_layer", "source_name", "confidence", "source_path", "checked_at"):
            text = _safe_text(value.get(key))
            if text:
                result[key] = text
        urls = value.get("evidence_urls") if isinstance(value.get("evidence_urls"), list) else []
        clean_urls = [_safe_text(item) for item in urls if _safe_text(item)]
        if clean_urls:
            result["evidence_urls"] = list(dict.fromkeys(clean_urls))[:6]
        return result

    def capability_value(entry: dict[str, Any], field: str) -> Any:
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        return caps.get(field)

    def capability_changed(before_entry: dict[str, Any], after_entry: dict[str, Any], field: str) -> bool:
        return _mapping_digest({"value": capability_value(before_entry, field)}) != _mapping_digest({"value": capability_value(after_entry, field)})

    def source_for_field(source_map: dict[str, Any], field: str) -> dict[str, Any]:
        if not isinstance(source_map, dict):
            return {}
        source = source_map.get(field)
        if source is None and field == "supports_thinking":
            source = source_map.get("thinking")
        if source is None and field == "cache_sensitive_transport":
            source = source_map.get("cache_sensitive")
        if source is None and field == "long_context":
            source = source_map.get("context_window_tokens") or source_map.get("one_m_context")
        if source is None and field == "thinking_control":
            source = source_map.get("reasoning_effort")
        return sanitize_capability_source(source)

    def positive_capability_overlays(value: Any) -> dict[str, Any]:
        """Keep positive catalog facts when a later partial overlay omits them."""
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        for key in (
            "vision",
            "tool_use",
            "reasoning",
            "thinking",
            "supports_thinking",
            "one_m_context",
            "long_context",
            "cache_sensitive",
            "cache_sensitive_transport",
        ):
            if value.get(key) is True:
                result[key] = True
        for key in ("context_window_tokens", "max_context_tokens", "max_output_tokens", "official_max_output_tokens"):
            tokens = _normalize_context_tokens(value.get(key))
            if tokens:
                result[key] = tokens
        for key in ("reasoning_effort", "official_reasoning_effort", "recommended_reasoning_effort"):
            text = _safe_text(value.get(key))
            if text:
                result[key] = text
        if isinstance(value.get("thinking_control"), dict):
            result["thinking_control"] = _truth_thinking_control(value["thinking_control"])
        return result

    for provider in providers:
        if not isinstance(provider, dict):
            continue
        hidden = set(_normalize_model_list(provider.get("hidden_models")))
        caps_map = dict(provider.get("model_capabilities") if isinstance(provider.get("model_capabilities"), dict) else {})
        source_map = dict(provider.get("model_capability_sources") if isinstance(provider.get("model_capability_sources"), dict) else {})
        rows = provider.get("models") if isinstance(provider.get("models"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _safe_text(row.get("id"))
            if not model_id:
                continue
            touched = row.get("policy_touched") is True or row.get("touched") is True
            capability_touched = row.get("capability_touched") is True or row.get("capabilities_touched") is True
            if not touched and not capability_touched:
                continue
            row_policy_caps = row.get("policy_capabilities") if isinstance(row.get("policy_capabilities"), dict) else None
            if row_policy_caps is not None:
                existing_caps = caps_map.get(model_id) if isinstance(caps_map.get(model_id), dict) else {}
                row_caps = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
                preserved_caps = positive_capability_overlays(row_caps) if existing_caps else {}
                caps_map[model_id] = {
                    **existing_caps,
                    **preserved_caps,
                    **row_policy_caps,
                }
            else:
                caps_map.setdefault(model_id, row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {})
            if capability_touched and not touched:
                if isinstance(row.get("capability_sources"), dict):
                    source_map[model_id] = row.get("capability_sources")
                continue
            if isinstance(row.get("capability_sources"), dict):
                source_map[model_id] = row.get("capability_sources")
            if model_id in hidden or row.get("visible") is False:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = False
            elif row.get("visible") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["visible"] = True
            if row.get("favorite") is True:
                entry = models.setdefault(model_id, {})
                if isinstance(entry, dict):
                    entry["favorite"] = True
            elif row.get("favorite") is False and isinstance(models.get(model_id), dict) and "favorite" in models[model_id]:
                models[model_id]["favorite"] = False
        for model_id, caps in caps_map.items():
            model_id = _safe_text(model_id)
            if not model_id or not isinstance(caps, dict):
                continue
            entry = models.setdefault(model_id, {})
            if not isinstance(entry, dict):
                entry = {}
                models[model_id] = entry
            before_entry_for_sources = copy.deepcopy(entry)
            cap_payload = entry.setdefault("capabilities", {})
            if not isinstance(cap_payload, dict):
                cap_payload = {}
                entry["capabilities"] = cap_payload
            for key in ("text", "vision", "tool_use", "reasoning", "thinking", "long_context"):
                if isinstance(caps.get(key), bool):
                    cap_payload[key] = bool(caps[key])
            if isinstance(caps.get("one_m_context"), bool):
                cap_payload["one_m_context"] = bool(caps["one_m_context"])
            if isinstance(caps.get("thinking"), bool):
                cap_payload["supports_thinking"] = bool(caps["thinking"])
            if caps.get("text") is False:
                entry["visible"] = False
            if isinstance(caps.get("cache_sensitive"), bool):
                cap_payload["cache_sensitive_transport"] = bool(caps["cache_sensitive"])
            if "context_window_tokens" in caps or "max_context_tokens" in caps or caps.get("one_m_context") is True:
                context_tokens = _normalize_context_tokens(
                    caps.get("context_window_tokens") or caps.get("max_context_tokens") or (1_000_000 if caps.get("one_m_context") is True else None)
                )
                if context_tokens:
                    cap_payload["context_window_tokens"] = context_tokens
                    cap_payload["long_context"] = context_tokens >= 200_000
            if "max_output_tokens" in caps or "official_max_output_tokens" in caps:
                max_output_tokens = _normalize_context_tokens(caps.get("max_output_tokens") or caps.get("official_max_output_tokens"))
                if max_output_tokens:
                    cap_payload["max_output_tokens"] = max_output_tokens
            if isinstance(caps.get("thinking_control"), dict):
                control = _truth_thinking_control(caps["thinking_control"])
                if control:
                    cap_payload["thinking_control"] = control
            if _safe_text(caps.get("reasoning_effort")):
                cap_payload["reasoning_effort"] = _safe_text(caps.get("reasoning_effort")).lower()
            if _safe_text(caps.get("official_reasoning_effort")):
                cap_payload["official_reasoning_effort"] = _safe_text(caps.get("official_reasoning_effort")).lower()
            if _safe_text(caps.get("recommended_reasoning_effort")):
                cap_payload["recommended_reasoning_effort"] = _safe_text(caps.get("recommended_reasoning_effort")).lower()
            per_model_sources = source_map.get(model_id) if isinstance(source_map.get(model_id), dict) else {}
            if per_model_sources:
                source_payload = entry.get("capability_sources") if isinstance(entry.get("capability_sources"), dict) else {}
                source_payload = dict(source_payload)
                for field in (
                    "text",
                    "vision",
                    "tool_use",
                    "reasoning",
                    "thinking",
                    "supports_thinking",
                    "one_m_context",
                    "long_context",
                    "context_window_tokens",
                    "max_output_tokens",
                    "thinking_control",
                    "reasoning_effort",
                    "official_reasoning_effort",
                    "recommended_reasoning_effort",
                    "cache_sensitive_transport",
                ):
                    source = source_for_field(per_model_sources, field)
                    if source and capability_changed(before_entry_for_sources, entry, field):
                        source_payload[field] = source
                if source_payload:
                    entry["capability_sources"] = source_payload
    def comparable(payload: dict[str, Any]) -> dict[str, Any]:
        copy_payload = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        copy_payload.pop("updated_at", None)
        return copy_payload

    if _mapping_digest(comparable(policy)) != _mapping_digest(comparable(original_policy)):
        policy["updated_at"] = _now_iso()
    elif isinstance(original_policy, dict) and "updated_at" in original_policy:
        policy["updated_at"] = original_policy["updated_at"]
    return policy


def _provider_urls(provider: dict[str, Any] | None) -> dict[str, str]:
    provider = provider if isinstance(provider, dict) else {}
    return {
        "openai": _safe_text(provider.get("default_openai_base_url") or provider.get("openai_base_url") or provider.get("base_url")),
        "anthropic": _safe_text(provider.get("default_anthropic_base_url") or provider.get("anthropic_base_url")),
    }


def _provider_by_id(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    return {
        _safe_text(provider.get("id")): provider
        for provider in providers
        if isinstance(provider, dict) and _safe_text(provider.get("id"))
    }


def _provider_default_id(cfg: dict[str, Any]) -> str:
    provider_cfg = cfg.get("provider") if isinstance(cfg.get("provider"), dict) else {}
    return _safe_text(provider_cfg.get("default"))


def _mapping_digest(payload: Any) -> str:
    return json.dumps(_sanitize_for_output(payload if isinstance(payload, dict) else {}), ensure_ascii=False, sort_keys=True)


def _build_review_summary(
    current_cfg: dict[str, Any],
    next_cfg: dict[str, Any],
    policy_before: dict[str, Any],
    policy_after: dict[str, Any],
    credential_updates: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a human-readable save review; raw diff remains the audit detail."""
    items: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    before_providers = _provider_by_id(current_cfg)
    after_providers = _provider_by_id(next_cfg)
    before_ids = set(before_providers)
    after_ids = set(after_providers)

    def add_item(kind: str, title: str, detail: str, *, provider_id: str = "", level: str = "info", meta: dict[str, Any] | None = None) -> None:
        items.append({
            "kind": kind,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
            "meta": meta or {},
        })

    def add_risk(risk_id: str, title: str, detail: str, *, level: str = "warn", provider_id: str = "") -> None:
        risks.append({
            "id": risk_id,
            "level": level,
            "title": title,
            "detail": detail,
            "provider_id": provider_id,
        })

    def field_changes(before: dict[str, Any], after: dict[str, Any], labels: dict[str, str]) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for key in labels:
            before_value = before.get(key)
            after_value = after.get(key)
            if _mapping_digest({key: before_value}) == _mapping_digest({key: after_value}):
                continue
            changes.append({"field": key, "label": labels[key], "before": before_value, "after": after_value})
        return changes

    def display_value(value: Any) -> str:
        if value in (None, ""):
            return "-"
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def change_detail(changes: list[dict[str, Any]]) -> str:
        return "；".join(
            f"{item['label']} `{display_value(item.get('before'))}` -> `{display_value(item.get('after'))}`"
            for item in changes
        )

    for provider_id in sorted(after_ids - before_ids):
        add_item("provider_added", "新增通道", f"`{provider_id}` 将被加入配置。", provider_id=provider_id)
    for provider_id in sorted(before_ids - after_ids):
        add_item("provider_removed", "删除通道", f"`{provider_id}` 将从配置里移除。", provider_id=provider_id, level="danger")
        add_risk("provider_removed", "删除通道", f"`{provider_id}` 删除后新 session 不会再使用该通道。", level="danger", provider_id=provider_id)

    before_default = _provider_default_id(current_cfg)
    after_default = _provider_default_id(next_cfg)
    if before_default != after_default:
        add_item("default_provider", "默认通道变化", f"`{before_default or '-'}` -> `{after_default or '-'}`", level="warn")
        add_risk("default_provider_changed", "默认通道变化", "默认 provider 改变会影响后续新 session 的默认路由。", provider_id=after_default)

    before_accounts = _account_by_id(current_cfg)
    after_accounts = _account_by_id(next_cfg)
    before_account_defaults = _account_defaults(current_cfg)
    after_account_defaults = _account_defaults(next_cfg)
    account_change_count = 0
    for cli_name in sorted(set(before_account_defaults) | set(after_account_defaults)):
        before_account = before_account_defaults.get(cli_name, "")
        after_account = after_account_defaults.get(cli_name, "")
        if before_account == after_account:
            continue
        account_change_count += 1
        level = "danger" if cli_name == "claude" else "warn"
        add_item(
            "account_default",
            f"默认账号变化：{cli_name}",
            f"`{before_account or '-'}` -> `{after_account or '-'}`",
            level=level,
            meta={"cli": cli_name, "before": before_account, "after": after_account},
        )
        add_risk(
            "claude_account_human_gate" if cli_name == "claude" else "account_default_changed",
            "默认账号变化",
            "Claude account default 属于 human-only，WebUI 当前不会保存。" if cli_name == "claude" else f"`{cli_name}` 后续新 session 会默认使用 `{after_account or '-'}`。",
            level=level,
        )
    for account_id in sorted(set(before_accounts) & set(after_accounts)):
        before_account = before_accounts.get(account_id, {})
        after_account = after_accounts.get(account_id, {})
        if _mapping_digest(_account_review_fields(before_account)) == _mapping_digest(_account_review_fields(after_account)):
            continue
        account_change_count += 1
        cli_name = _safe_text(after_account.get("cli") or before_account.get("cli")).lower()
        level = "danger" if cli_name == "claude" else "warn"
        add_item(
            "account_metadata",
            f"账号元数据变化：{account_id}",
            f"name/enabled/priority/family/timezone/claude_1m/note 将更新；CLI: `{cli_name or '-'}`。",
            level=level,
            meta={"account_id": account_id, "cli": cli_name},
        )
        if cli_name == "claude":
            add_risk(
                "claude_account_human_gate",
                "Claude account human-only",
                "Claude account metadata 属于 human-only，WebUI 当前不会保存。",
                level="danger",
            )

    hidden_removed_total = 0
    hidden_added_total = 0
    for provider_id in sorted(after_ids):
        before = before_providers.get(provider_id, {})
        after = after_providers[provider_id]
        before_meta = {
            "name": _safe_text(before.get("name") or provider_id),
            "enabled": before.get("enabled", True) is not False,
            "role": _safe_text(before.get("role") or "auto"),
            "priority": _normalize_priority(before.get("priority", 100)),
            "claude_1m_mode": _safe_text(before.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(before.get("timezone")),
            "note": _safe_text(before.get("note")),
        }
        after_meta = {
            "name": _safe_text(after.get("name") or provider_id),
            "enabled": after.get("enabled", True) is not False,
            "role": _safe_text(after.get("role") or "auto"),
            "priority": _normalize_priority(after.get("priority", 100)),
            "claude_1m_mode": _safe_text(after.get("claude_1m_mode") or "auto") or "auto",
            "timezone": _safe_text(after.get("timezone")),
            "note": _safe_text(after.get("note")),
        }
        meta_labels = {
            "name": "名称",
            "enabled": "启用",
            "role": "角色",
            "priority": "优先级",
            "claude_1m_mode": "Claude 1M",
            "timezone": "时区",
            "note": "备注",
        }
        meta_changes = field_changes(before_meta, after_meta, meta_labels)
        if provider_id in before_ids and meta_changes:
            important_fields = {item["field"] for item in meta_changes}.intersection({"enabled", "role", "priority", "claude_1m_mode"})
            add_item(
                "provider_metadata",
                f"通道元数据变化：{provider_id}",
                change_detail(meta_changes),
                provider_id=provider_id,
                level="warn" if important_fields else "info",
                meta={"before": before_meta, "after": after_meta, "changes": meta_changes},
            )
        before_family = _normalize_family_priority_overrides(before.get("family_priority_overrides"))
        after_family = _normalize_family_priority_overrides(after.get("family_priority_overrides"))
        if _mapping_digest(before_family) != _mapping_digest(after_family):
            changed = sorted(set(before_family) | set(after_family))
            detail = "；".join(f"{family}: `{before_family.get(family, '-')}` -> `{after_family.get(family, '-')}`" for family in changed)
            add_item(
                "provider_family_priority",
                f"Family 权重变化：{provider_id}",
                detail,
                provider_id=provider_id,
                level="warn",
                meta={"before": before_family, "after": after_family},
            )
        before_urls = _provider_urls(before)
        after_urls = _provider_urls(after)
        if provider_id in before_ids:
            for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
                if before_urls[field] == after_urls[field]:
                    continue
                add_item(
                    "provider_url",
                    f"通道 URL 变化：{provider_id}",
                    f"{label}: `{before_urls[field] or '-'}` -> `{after_urls[field] or '-'}`",
                    provider_id=provider_id,
                    level="warn",
                    meta={"field": field, "before": before_urls[field], "after": after_urls[field]},
                )
        elif after_urls["openai"] or after_urls["anthropic"]:
            url_parts = []
            if after_urls["openai"]:
                url_parts.append(f"OpenAI: `{after_urls['openai']}`")
            if after_urls["anthropic"]:
                url_parts.append(f"Anthropic: `{after_urls['anthropic']}`")
            add_item("provider_url", f"通道 URL：{provider_id}", "；".join(url_parts), provider_id=provider_id)
        url_changed_by_field: dict[str, bool] = {}
        for field, label in (("openai", "OpenAI base URL"), ("anthropic", "Anthropic base URL")):
            url_changed_by_field[field] = before_urls[field] != after_urls[field]
            url = after_urls[field]
            if url.lower().startswith("http://") and (provider_id not in before_ids or url_changed_by_field[field]):
                add_risk("http_base_url", "HTTP URL", f"`{provider_id}` 的 {label} 使用 `http://`，请确认这是内网/代理预期。", provider_id=provider_id)
        before_enabled = before.get("enabled", True) is not False
        after_enabled = after.get("enabled", True) is not False
        became_empty = bool(before_urls["openai"] or before_urls["anthropic"]) and not after_urls["openai"] and not after_urls["anthropic"]
        became_enabled = not before_enabled and after_enabled
        if after_enabled and not after_urls["openai"] and not after_urls["anthropic"] and (provider_id not in before_ids or became_empty or became_enabled):
            add_risk("empty_provider_url", "启用通道缺少 URL", f"`{provider_id}` 已启用但没有 OpenAI/Anthropic URL。", provider_id=provider_id)
        before_hidden = set(_normalize_model_list(before.get("hidden_models")))
        after_hidden = set(_normalize_model_list(after.get("hidden_models")))
        removed = sorted(before_hidden - after_hidden, key=str.lower)
        added = sorted(after_hidden - before_hidden, key=str.lower)
        hidden_removed_total += len(removed)
        hidden_added_total += len(added)
        if removed:
            preview = ", ".join(removed[:8])
            suffix = f" 等 {len(removed)} 个" if len(removed) > 8 else ""
            add_item("hidden_removed", f"移除隐藏记录：{provider_id}", f"将移除 `{preview}`{suffix}", provider_id=provider_id, meta={"models": removed})
        if added:
            preview = ", ".join(added[:8])
            suffix = f" 等 {len(added)} 个" if len(added) > 8 else ""
            add_item("hidden_added", f"新增隐藏模型：{provider_id}", f"将隐藏 `{preview}`{suffix}", provider_id=provider_id, meta={"models": added})
        before_extra = set(_normalize_model_list(before.get("extra_models")))
        after_extra = set(_normalize_model_list(after.get("extra_models")))
        if before_extra != after_extra:
            add_item(
                "extra_models",
                f"手动模型变化：{provider_id}",
                f"新增 {len(after_extra - before_extra)} 个，移除 {len(before_extra - after_extra)} 个。",
                provider_id=provider_id,
            )

    ui_before = current_cfg.get("ui") if isinstance(current_cfg.get("ui"), dict) else {}
    ui_after = next_cfg.get("ui") if isinstance(next_cfg.get("ui"), dict) else {}
    if _safe_text(ui_before.get("language") or "zh") != _safe_text(ui_after.get("language") or "zh"):
        add_item(
            "ui_language",
            "界面语言变化",
            f"`{_safe_text(ui_before.get('language') or 'zh')}` -> `{_safe_text(ui_after.get('language') or 'zh')}`",
        )

    rescue_before = current_cfg.get("rescue") if isinstance(current_cfg.get("rescue"), dict) else {}
    rescue_after = next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {}
    if _mapping_digest(rescue_before) != _mapping_digest(rescue_after):
        add_item("rescue", "Rescue fallback 变化", f"`{_safe_text(rescue_before.get('fallback_model')) or '-'}` -> `{_safe_text(rescue_after.get('fallback_model')) or '-'}`")

    lb_before = current_cfg.get("load_balance") if isinstance(current_cfg.get("load_balance"), dict) else {}
    lb_after = next_cfg.get("load_balance") if isinstance(next_cfg.get("load_balance"), dict) else {}
    if _mapping_digest(lb_before) != _mapping_digest(lb_after):
        before_profiles = (lb_before.get("profiles") if isinstance(lb_before.get("profiles"), dict) else {}) or {}
        after_profiles = (lb_after.get("profiles") if isinstance(lb_after.get("profiles"), dict) else {}) or {}
        add_item(
            "load_balance",
            "Load balance profile 变化",
            f"default `{_safe_text(lb_before.get('default')) or '-'}` -> `{_safe_text(lb_after.get('default')) or '-'}`；profiles {len(before_profiles)} -> {len(after_profiles)}。",
            level="warn",
        )

    vision_before = current_cfg.get("vision_sidecar") if isinstance(current_cfg.get("vision_sidecar"), dict) else {}
    vision_after = next_cfg.get("vision_sidecar") if isinstance(next_cfg.get("vision_sidecar"), dict) else {}
    if _mapping_digest(vision_before) != _mapping_digest(vision_after):
        before_ref = f"{_safe_text(vision_before.get('provider_id') or vision_before.get('provider')) or '-'}/{_safe_text(vision_before.get('model') or vision_before.get('vision_model')) or '-'}"
        after_ref = f"{_safe_text(vision_after.get('provider_id') or vision_after.get('provider')) or '-'}/{_safe_text(vision_after.get('model') or vision_after.get('vision_model')) or '-'}"
        add_item("vision_sidecar", "Vision sidecar 变化", f"`{before_ref}` -> `{after_ref}`")

    opencode_before = current_cfg.get("opencode") if isinstance(current_cfg.get("opencode"), dict) else {}
    opencode_after = next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {}
    if _safe_text(opencode_before.get("default_profile")) != _safe_text(opencode_after.get("default_profile")):
        add_item("opencode_profile", "OpenCode profile 变化", f"`{_safe_text(opencode_before.get('default_profile')) or '-'}` -> `{_safe_text(opencode_after.get('default_profile')) or '-'}`")
    before_review_host = _normalize_opencode_review_host(opencode_before)
    after_review_host = _normalize_opencode_review_host(opencode_after)
    if _mapping_digest(before_review_host) != _mapping_digest(after_review_host):
        primary = after_review_host.get("primary_models") or []
        fallback = after_review_host.get("fallback_models") or []
        add_item(
            "opencode_review_host",
            "OpenCode Review host 变化",
            f"primary `{', '.join(primary) or '-'}`；fallback `{', '.join(fallback) or '-'}`",
            meta={
                "primary_models": primary,
                "fallback_models": fallback,
            },
        )
    before_agents = _normalize_agent_model_overrides(opencode_before.get("agent_models") or opencode_before.get("agent_model_overrides"))
    after_agents = _normalize_agent_model_overrides(opencode_after.get("agent_models") or opencode_after.get("agent_model_overrides"))
    if _mapping_digest(before_agents) != _mapping_digest(after_agents):
        added_agents = sorted(set(after_agents) - set(before_agents))
        removed_agents = sorted(set(before_agents) - set(after_agents))
        updated_agents = sorted(
            agent for agent in (set(before_agents) & set(after_agents))
            if _mapping_digest(before_agents.get(agent)) != _mapping_digest(after_agents.get(agent))
        )
        changed_agents = sorted(
            set(added_agents) | set(removed_agents) | set(updated_agents)
        )
        preview = ", ".join(changed_agents[:8])
        suffix = f" 等 {len(changed_agents)} 个" if len(changed_agents) > 8 else ""
        buckets = []
        if added_agents:
            buckets.append(f"新增 {len(added_agents)}")
        if removed_agents:
            buckets.append(f"移除 {len(removed_agents)}")
        if updated_agents:
            buckets.append(f"修改 {len(updated_agents)}")
        add_item(
            "opencode_agent_models",
            "OpenCode agent 模型覆盖变化",
            f"{'，'.join(buckets)}；agent：{preview}{suffix}",
            meta={
                "agents": changed_agents,
                "added_agents": added_agents,
                "removed_agents": removed_agents,
                "updated_agents": updated_agents,
            },
        )
    before_roster = _normalize_opencode_agent_roster(opencode_before.get("agent_roster"), profile_id="agent")
    after_roster = _normalize_opencode_agent_roster(opencode_after.get("agent_roster"), profile_id="agent")
    if _mapping_digest(before_roster) != _mapping_digest(after_roster):
        changed_roster = sorted(
            agent for agent in (set(before_roster) | set(after_roster))
            if _mapping_digest(before_roster.get(agent)) != _mapping_digest(after_roster.get(agent))
        )
        disabled = sorted(agent for agent, entry in after_roster.items() if entry.get("enabled") is False)
        custom = sorted(agent for agent, entry in after_roster.items() if entry.get("custom") is True)
        parts = []
        if disabled:
            parts.append(f"禁用 {len(disabled)}")
        if custom:
            parts.append(f"自定义 {len(custom)}")
        if not parts:
            parts.append(f"更新 {len(changed_roster)}")
        preview = ", ".join(changed_roster[:8])
        suffix = f" 等 {len(changed_roster)} 个" if len(changed_roster) > 8 else ""
        add_item(
            "opencode_agent_roster",
            "OpenCode roster 变化",
            f"{'，'.join(parts)}；agent：{preview}{suffix}",
            meta={"agents": changed_roster, "disabled_agents": disabled, "custom_agents": custom},
        )

    if credential_updates:
        provider_ids = ", ".join(item["provider_id"] for item in credential_updates)
        add_item(
            "credentials",
            "凭据写入",
            f"stable legacy 写 credentials.sh；preview 写 secret backend：{provider_ids}",
            level="warn",
        )
        add_risk(
            "credential_update",
            "凭据写入",
            "只有输入了新 API Key 且勾选更新凭据的通道才会写入；stable legacy 目标是 credentials.sh，preview 目标是 secret backend。",
            level="warn",
        )

    policy_field_labels = {
        "visible": "显示",
        "favorite": "置顶",
        "capabilities.text": "文本",
        "capabilities.vision": "看图",
        "capabilities.tool_use": "工具",
        "capabilities.reasoning": "推理",
        "capabilities.thinking": "Think",
        "capabilities.one_m_context": "1M",
        "capabilities.long_context": "长上下文",
        "capabilities.context_window_tokens": "上下文",
        "capabilities.max_output_tokens": "输出上限",
        "capabilities.thinking_control": "Effort 控制",
        "capabilities.reasoning_effort": "默认 Effort",
        "capabilities.cache_sensitive": "缓存",
        "capabilities.cache_sensitive_transport": "缓存传输",
        "capabilities.supports_thinking": "支持 Think",
    }

    def policy_value_display(value: Any) -> str:
        if value is None:
            return "未写入配置"
        if isinstance(value, int) and value >= 1000:
            if value >= 1_000_000 and value % 1_000_000 == 0:
                return f"{value // 1_000_000}M"
            if value >= 100_000 and value % 1000 == 0:
                return f"{value // 1000}K"
        return display_value(value)

    def policy_flat(entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        flat: dict[str, Any] = {}
        for key in ("visible", "favorite"):
            if key in entry:
                flat[key] = entry.get(key)
        caps = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        for key in sorted(caps):
            flat[f"capabilities.{key}"] = caps.get(key)
        for key in sorted(entry):
            if key in {"visible", "favorite", "capabilities", "capability_sources"}:
                continue
            flat[key] = entry.get(key)
        return flat

    def policy_source_label(source: Any) -> str:
        if not isinstance(source, dict):
            return ""
        name = _safe_text(source.get("source_name"))
        layer = _safe_text(source.get("source_layer")).lower()
        confidence = _safe_text(source.get("confidence")).lower()
        if name:
            return name
        if "openrouter" in confidence:
            return "OpenRouter catalog"
        if layer == "provider_catalog":
            return "Provider catalog"
        if layer == "official":
            return "官方 / 已确认"
        if layer == "manual":
            return "手动调整"
        return layer or ""

    def policy_source_for_field(entry: Any, field: str) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        sources = entry.get("capability_sources") if isinstance(entry.get("capability_sources"), dict) else {}
        key = field.replace("capabilities.", "", 1)
        source = sources.get(key)
        if source is None and key == "supports_thinking":
            source = sources.get("thinking")
        if source is None and key == "long_context":
            source = sources.get("context_window_tokens") or sources.get("one_m_context")
        if source is None and key == "cache_sensitive_transport":
            source = sources.get("cache_sensitive")
        source = source if isinstance(source, dict) else {}
        label = policy_source_label(source)
        result = _sanitize_for_output(source) if source else {}
        if label:
            result["label"] = label
        return result

    def policy_change_rows(before_entry: Any, after_entry: Any) -> list[dict[str, Any]]:
        before_flat = policy_flat(before_entry)
        after_flat = policy_flat(after_entry)
        rows: list[dict[str, Any]] = []
        for field in sorted(set(before_flat) | set(after_flat)):
            before_value = before_flat.get(field)
            after_value = after_flat.get(field)
            if _mapping_digest({field: before_value}) == _mapping_digest({field: after_value}):
                continue
            source = policy_source_for_field(after_entry, field)
            rows.append(
                {
                    "field": field,
                    "label": policy_field_labels.get(field, field),
                    "before": before_value,
                    "after": after_value,
                    "before_label": policy_value_display(before_value),
                    "after_label": policy_value_display(after_value),
                    "source": source,
                    "source_label": source.get("label", ""),
                }
            )
        return rows

    def build_policy_changes() -> dict[str, Any]:
        policy_before_models = policy_before.get("models") if isinstance(policy_before.get("models"), dict) else {}
        policy_after_models = policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}
        rows: list[dict[str, Any]] = []
        added = sorted(set(policy_after_models) - set(policy_before_models), key=str.lower)
        removed = sorted(set(policy_before_models) - set(policy_after_models), key=str.lower)
        common = sorted(set(policy_before_models) & set(policy_after_models), key=str.lower)
        for model in added:
            changes = policy_change_rows({}, policy_after_models.get(model))
            rows.append(
                {
                    "model": model,
                    "action": "added",
                    "action_label": "新增",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "；".join(f"{item['label']} `{item['after_label']}`" for item in changes[:8]) or "新增条目",
                    "before": {},
                    "after": _sanitize_for_output(policy_after_models.get(model)),
                }
            )
        for model in removed:
            changes = policy_change_rows(policy_before_models.get(model), {})
            rows.append(
                {
                    "model": model,
                    "action": "removed",
                    "action_label": "移除",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "将移除该 model-policy 条目",
                    "before": _sanitize_for_output(policy_before_models.get(model)),
                    "after": {},
                }
            )
        for model in common:
            changes = policy_change_rows(policy_before_models.get(model), policy_after_models.get(model))
            if not changes:
                continue
            rows.append(
                {
                    "model": model,
                    "action": "updated",
                    "action_label": "修改",
                    "changed_fields": [item["field"] for item in changes],
                    "changes": changes,
                    "summary": "；".join(f"{item['label']} `{item['before_label']}` -> `{item['after_label']}`" for item in changes[:8]),
                    "before": _sanitize_for_output(policy_before_models.get(model)),
                    "after": _sanitize_for_output(policy_after_models.get(model)),
                }
            )
        rows.sort(key=lambda item: ({"updated": 0, "added": 1, "removed": 2}.get(str(item.get("action")), 9), str(item.get("model") or "").lower()))
        return {
            "schema": "mms.setup_web.model_policy_changes.v1",
            "total": len(rows),
            "added": len(added),
            "removed": len(removed),
            "updated": len([item for item in rows if item.get("action") == "updated"]),
            "items": rows,
        }

    model_policy_changes = build_policy_changes()
    if model_policy_changes["total"]:
        add_item(
            "model_policy",
            "模型能力/偏好策略变化",
            f"将更新 {model_policy_changes['total']} 个 model-policy 条目：修改 {model_policy_changes['updated']}，新增 {model_policy_changes['added']}，移除 {model_policy_changes['removed']}。",
            meta={
                "total": model_policy_changes["total"],
                "updated": model_policy_changes["updated"],
                "added": model_policy_changes["added"],
                "removed": model_policy_changes["removed"],
                "models": [item["model"] for item in model_policy_changes["items"][:80]],
            },
        )

    if not items:
        add_item("no_change", "没有配置变化", "当前草稿与已加载配置一致。")
    return {
        "schema": "mms.setup_web.review_summary.v1",
        "counts": {
            "items": len(items),
            "risks": len(risks),
            "providers_before": len(before_ids),
            "providers_after": len(after_ids),
            "hidden_removed": hidden_removed_total,
            "hidden_added": hidden_added_total,
            "credential_updates": len(credential_updates),
            "account_changes": account_change_count,
            "model_policy_changes": model_policy_changes["total"],
        },
        "items": items,
        "risks": risks,
        "model_policy_changes": model_policy_changes,
    }


def _build_registry_v2_save_plan(
    *,
    config_path: str,
    plan_summary: dict[str, Any],
    credential_updates: list[dict[str, str]],
    config_payload: dict[str, Any] | None = None,
    policy_payload: dict[str, Any] | None = None,
    expected_bundle_revision: str = "",
    route_scope_provider_ids: list[str] | None = None,
    route_refresh_provider_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Describe the future DB-truth save path without writing anything."""
    from mms_registry_cli import registry_v2_route_publish_guard, registry_v2_save_plan

    route_publish_guard: dict[str, Any] = {}
    try:
        config_root = _config_root_for_snapshot(config_path)
        route_publish_guard = registry_v2_route_publish_guard(
            config_dir=config_root or None,
            config_payload=config_payload if isinstance(config_payload, dict) else {},
            policy_payload=policy_payload if isinstance(policy_payload, dict) else {},
            credential_updates=credential_updates,
            expected_bundle_revision=expected_bundle_revision,
            route_scope_provider_ids=route_scope_provider_ids,
            route_refresh_provider_ids=route_refresh_provider_ids,
        )
    except Exception as exc:
        route_publish_guard = {
            "ok": False,
            "reason": "route_publish_guard_error",
            "message": f"{type(exc).__name__}: {exc}",
        }

    return registry_v2_save_plan(
        config_path=config_path,
        command_name="mms-config-web",
        plan_summary=plan_summary,
        credential_updates=credential_updates,
        route_publish_guard=route_publish_guard,
    )


def build_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    include_secrets: bool = False,
    command_name: str = "mms",
) -> dict[str, Any]:
    current_cfg = copy.deepcopy(current_cfg) if isinstance(current_cfg, dict) else {}
    current_cfg = _hydrate_preview_config_from_latest_bundle(current_cfg, config_path=config_path, command_name=command_name)
    draft = _extract_draft(payload or {})
    providers_payload = draft.get("providers") if isinstance(draft.get("providers"), list) else []
    existing_by_id = {str(item.get("id") or ""): item for item in current_cfg.get("providers", []) if isinstance(item, dict)}
    preserve_model_rows = _is_preview_config_root(config_path, command_name=command_name)
    route_scope_provider_ids = _route_scope_provider_ids_from_payload(payload or {})
    route_refresh_provider_ids = _route_refresh_provider_ids_from_payload(payload or {})
    touched_route_provider_ids = set(route_scope_provider_ids) | set(route_refresh_provider_ids)
    refreshed_provider_ids = set(route_refresh_provider_ids)
    next_providers: list[dict[str, Any]] = []
    credential_updates: list[dict[str, str]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for provider_payload in providers_payload:
        if not isinstance(provider_payload, dict):
            continue
        original_id = _safe_text(provider_payload.get("original_id") or provider_payload.get("id"))
        provider_id = _safe_text(provider_payload.get("id") or original_id)
        provider = _copy_existing_provider(
            existing_by_id.get(original_id),
            provider_payload,
            preserve_model_rows=preserve_model_rows,
            force_model_rows=original_id in touched_route_provider_ids or provider_id in touched_route_provider_ids,
            clear_fallback_models=preserve_model_rows and (original_id in refreshed_provider_ids or provider_id in refreshed_provider_ids),
        )
        next_providers.append(provider)
        if _truthy(provider_payload.get("update_credentials"), False):
            api_key = _safe_text(provider_payload.get("api_key"))
            openai_base = _safe_text(provider_payload.get("openai_base_url") or provider_payload.get("base_url") or provider.get("default_openai_base_url"))
            anthropic_base = _safe_text(provider_payload.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
            if not api_key:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 API Key 为空。")
            if not openai_base and not anthropic_base:
                errors.append(f"通道 {provider['id']} 勾选了更新凭据，但 URL 为空。")
            credential_update = {
                "provider_id": provider["id"],
                "base_url": (openai_base or anthropic_base).rstrip("/"),
                "openai_base_url": openai_base.rstrip("/"),
                "anthropic_base_url": anthropic_base.rstrip("/"),
                "api_key": api_key if include_secrets else _redact(api_key),
            }
            openai_api_key = _safe_text(provider_payload.get("openai_api_key"))
            if openai_api_key:
                credential_update["openai_api_key"] = openai_api_key if include_secrets else _redact(openai_api_key)
            credential_updates.append(credential_update)
        if provider.get("anthropic_base_url") and "anthropic_messages" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 Anthropic URL，但 protocols 未包含 anthropic_messages。")
        if provider.get("openai_base_url") and "openai_chat_completions" not in provider.get("protocols", []):
            warnings.append(f"通道 {provider['id']} 填了 OpenAI URL，但 protocols 未包含 openai_chat_completions。")

    if providers_payload:
        seen: set[str] = set()
        deduped = []
        for provider in next_providers:
            provider_id = provider.get("id")
            if provider_id in seen:
                errors.append(f"通道 ID 重复: {provider_id}")
                continue
            seen.add(provider_id)
            deduped.append(provider)
        next_providers = deduped
    else:
        next_providers = list(current_cfg.get("providers") or [])

    next_cfg = copy.deepcopy(current_cfg)
    if next_providers:
        next_cfg["providers"] = next_providers
    provider_default = _safe_text(draft.get("provider_default") or (next_cfg.get("provider") if isinstance(next_cfg.get("provider"), dict) else {}).get("default"))
    provider_ids = {provider.get("id") for provider in next_providers if isinstance(provider, dict)}
    if provider_default and provider_default not in provider_ids:
        warnings.append(f"默认通道 {provider_default} 不在通道列表中，保存时会使用第一个通道。")
        provider_default = ""
    if next_providers:
        next_cfg["provider"] = {"default": provider_default or str(next_providers[0].get("id"))}

    _apply_account_draft(
        current_cfg=current_cfg,
        next_cfg=next_cfg,
        draft=draft,
        errors=errors,
        warnings=warnings,
    )

    ui_payload = draft.get("ui") if isinstance(draft.get("ui"), dict) else {}
    if "language" in ui_payload:
        language = _safe_text(ui_payload.get("language") or "zh").lower()
        if language not in {"zh", "en"}:
            errors.append("ui.language 只支持 zh 或 en。")
        else:
            ui_cfg = dict(next_cfg.get("ui") if isinstance(next_cfg.get("ui"), dict) else {})
            ui_cfg["language"] = language
            next_cfg["ui"] = ui_cfg

    rescue_payload = draft.get("rescue") if isinstance(draft.get("rescue"), dict) else {}
    if rescue_payload:
        rescue = dict(next_cfg.get("rescue") if isinstance(next_cfg.get("rescue"), dict) else {})
        fallback_model = _safe_text(rescue_payload.get("fallback_model"))
        fallback_cli = _safe_text(rescue_payload.get("fallback_cli"))
        if fallback_model:
            rescue["fallback_model"] = fallback_model
            if fallback_cli:
                rescue["fallback_cli"] = fallback_cli
            else:
                rescue.pop("fallback_cli", None)
            rescue["hot_fallback_enabled"] = _truthy(rescue_payload.get("hot_fallback_enabled"), False)
        else:
            rescue.pop("fallback_model", None)
            rescue.pop("fallback_cli", None)
            rescue.pop("hot_fallback_enabled", None)
        if rescue:
            next_cfg["rescue"] = rescue
        else:
            next_cfg.pop("rescue", None)

    if isinstance(draft.get("load_balance"), dict):
        load_balance = _normalize_load_balance_draft(draft.get("load_balance"), errors=errors)
        if load_balance:
            next_cfg["load_balance"] = load_balance
        else:
            next_cfg.pop("load_balance", None)

    vision_payload = draft.get("vision_sidecar") if isinstance(draft.get("vision_sidecar"), dict) else {}
    if vision_payload:
        vision = {
            "enabled": _truthy(vision_payload.get("enabled"), True),
            "provider_id": _safe_text(vision_payload.get("provider_id") or vision_payload.get("provider")),
            "model": _safe_text(vision_payload.get("model") or vision_payload.get("vision_model")),
        }
        candidates = []
        for item in vision_payload.get("candidates") or []:
            if not isinstance(item, dict):
                continue
            provider_id = _safe_text(item.get("provider_id") or item.get("provider"))
            model = _safe_text(item.get("model") or item.get("vision_model"))
            if provider_id and model:
                candidates.append({"provider_id": provider_id, "model": model})
        if candidates:
            vision["candidates"] = candidates
        if vision["provider_id"] or vision["model"] or candidates or vision["enabled"] is False:
            next_cfg["vision_sidecar"] = vision

    runtime_payload = draft.get("runtime") if isinstance(draft.get("runtime"), dict) else {}
    preferred_cli = _safe_text(runtime_payload.get("preferred_cli"))
    if preferred_cli:
        if preferred_cli not in _ALLOWED_CLIS:
            errors.append(f"首选 CLI 不支持: {preferred_cli}")
        else:
            presets = dict(next_cfg.get("presets") if isinstance(next_cfg.get("presets"), dict) else {})
            coding = dict(presets.get("coding") if isinstance(presets.get("coding"), dict) else {})
            coding_model = _safe_text(runtime_payload.get("coding_preset_model"))
            if coding or preferred_cli != "opencode" or coding_model:
                coding["cli"] = preferred_cli
            if coding_model:
                coding["model"] = coding_model
            if coding:
                presets["coding"] = coding
                next_cfg["presets"] = presets

    opencode_payload = draft.get("opencode") if isinstance(draft.get("opencode"), dict) else {}
    raw_default_profile = _safe_text(opencode_payload.get("default_profile"))
    default_profile = _opencode_surface_profile_id(raw_default_profile, default="") if raw_default_profile else ""
    review_host = _normalize_opencode_review_host(opencode_payload)
    agent_model_overrides = _normalize_agent_model_overrides(opencode_payload.get("agent_models") or opencode_payload.get("agent_model_overrides"))
    agent_roster_profile = default_profile or _opencode_surface_profile_id(
        (next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {}).get("default_profile") or "agent"
    )
    agent_roster = _normalize_opencode_agent_roster(opencode_payload.get("agent_roster"), profile_id=agent_roster_profile)
    opencode_payload_touched = (
        default_profile
        or "agent_models" in opencode_payload
        or "agent_model_overrides" in opencode_payload
        or "agent_roster" in opencode_payload
        or "review" in opencode_payload
        or "review_host" in opencode_payload
        or "committee_presets" in opencode_payload
    )
    if opencode_payload_touched:
        opencode_cfg = dict(next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {})
        current_default_profile = _safe_text(opencode_cfg.get("default_profile"))
        if default_profile and (current_default_profile or default_profile != "agent"):
            opencode_cfg["default_profile"] = default_profile
        if review_host["primary_models"] or review_host["fallback_models"]:
            review_cfg = dict(opencode_cfg.get("review") if isinstance(opencode_cfg.get("review"), dict) else {})
            review_cfg["host"] = {key: models for key, models in review_host.items() if models}
            opencode_cfg["review"] = review_cfg
            opencode_cfg.pop("review_host", None)
        elif "review" in opencode_payload or "review_host" in opencode_payload:
            review_cfg = dict(opencode_cfg.get("review") if isinstance(opencode_cfg.get("review"), dict) else {})
            review_cfg.pop("host", None)
            if review_cfg:
                opencode_cfg["review"] = review_cfg
            else:
                opencode_cfg.pop("review", None)
            opencode_cfg.pop("review_host", None)
        if "committee_presets" in opencode_payload:
            committee_presets = _normalize_opencode_committee_presets_input(opencode_payload, errors)
            committee_cfg = dict(opencode_cfg.get("committee") if isinstance(opencode_cfg.get("committee"), dict) else {})
            if committee_presets:
                committee_cfg["presets"] = committee_presets
                opencode_cfg["committee"] = committee_cfg
            else:
                committee_cfg.pop("presets", None)
                if committee_cfg:
                    opencode_cfg["committee"] = committee_cfg
                else:
                    opencode_cfg.pop("committee", None)
        if agent_model_overrides:
            opencode_cfg["agent_models"] = agent_model_overrides
            opencode_cfg.pop("agent_model_overrides", None)
        else:
            opencode_cfg.pop("agent_models", None)
            opencode_cfg.pop("agent_model_overrides", None)
        if agent_roster:
            opencode_cfg["agent_roster"] = agent_roster
        else:
            opencode_cfg.pop("agent_roster", None)
        if opencode_cfg:
            next_cfg["opencode"] = opencode_cfg
        else:
            next_cfg.pop("opencode", None)

    policy_path = _policy_path_for_config(config_path)
    policy_before = _load_json_file(policy_path)
    if not policy_before:
        policy_before = {
            "version": 1,
            "updated_at": _now_iso(),
            "description": "User-maintained model visibility and preference policy. MMS never stores provider secrets here.",
            "models": {},
            "projects": {},
        }
    policy_after = _build_model_policy_from_draft(policy_before, draft)
    policy_after = _merge_model_policy_import(policy_after, draft.get("model_policy_import"))

    try:
        mms_core = _load_mms_core()
        if hasattr(mms_core, "_ensure_provider_config"):
            next_cfg, _ = mms_core._ensure_provider_config(next_cfg)  # noqa: SLF001 - reuse existing normalization
    except Exception:
        pass
    next_cfg = _strip_implicit_provider_timezone_defaults(next_cfg, providers_payload)
    next_cfg = _strip_empty_provider_model_lists(next_cfg)

    before_config_text = _toml_text(_sanitize_for_output(current_cfg))
    after_config_text = _toml_text(_sanitize_for_output(next_cfg))
    before_policy_text = _pretty_json(_sanitize_for_output(policy_before))
    after_policy_text = _pretty_json(_sanitize_for_output(policy_after))
    config_changed = _mapping_digest(current_cfg) != _mapping_digest(next_cfg)
    diffs = {
        "config_toml": _diff_text(before_config_text, after_config_text, before_name="config.toml(before)", after_name="config.toml(after)") if config_changed else "",
        "model_policy_json": _diff_text(before_policy_text, after_policy_text, before_name="model-policy.json(before)", after_name="model-policy.json(after)"),
        "credentials": "\n".join(
            f"credential update: provider {item['provider_id']} (secret hidden; stable credentials.sh / preview secret backend)"
            for item in credential_updates
        ),
    }
    review_summary = _build_review_summary(current_cfg, next_cfg, policy_before, policy_after, credential_updates)
    summary = {
        "providers": len(next_cfg.get("providers") or []),
        "credential_updates": len(credential_updates),
        "policy_models": len((policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}) or {}),
        "will_write_config": bool(diffs["config_toml"]),
        "will_write_policy": bool(diffs["model_policy_json"]),
        "will_write_credentials": bool(credential_updates),
    }
    return {
        "schema": "mms.setup_web.plan.v1",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "expected_bundle_revision": _expected_bundle_revision_from_payload(payload or {}),
        "route_scope_provider_ids": route_scope_provider_ids,
        "route_refresh_provider_ids": route_refresh_provider_ids,
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "config": next_cfg,
        "model_policy": policy_after,
        "credential_updates": credential_updates,
        "diffs": diffs,
        "review_summary": review_summary,
        "registry_v2_save_plan": _build_registry_v2_save_plan(
            config_path=config_path,
            plan_summary=summary,
            credential_updates=credential_updates,
            config_payload=next_cfg,
            policy_payload=policy_after,
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload or {}),
            route_scope_provider_ids=route_scope_provider_ids,
            route_refresh_provider_ids=route_refresh_provider_ids,
        ),
        "summary": summary,
    }


def _expected_bundle_revision_from_payload(payload: dict[str, Any] | None) -> str:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        for key in ("expected_bundle_revision", "bundle_revision", "source_bundle_revision"):
            value = _safe_text(source.get(key))
            if value:
                return value
    return ""


def _route_scope_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        values = source.get("route_scope_provider_ids") or source.get("touched_provider_ids")
        if isinstance(values, list):
            result = []
            seen = set()
            for item in values:
                provider_id = _safe_text(item)
                if provider_id and provider_id not in seen:
                    seen.add(provider_id)
                    result.append(provider_id)
            if result:
                return result
    return []


def _route_refresh_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    payload = payload if isinstance(payload, dict) else {}
    draft = _extract_draft(payload)
    for source in (payload, draft):
        values = source.get("route_refresh_provider_ids") or source.get("refreshed_provider_ids")
        if isinstance(values, list):
            result = []
            seen = set()
            for item in values:
                provider_id = _safe_text(item)
                if provider_id and provider_id not in seen:
                    seen.add(provider_id)
                    result.append(provider_id)
            if result:
                return result
    return []


def _latest_audit_rows(config_path: str, limit: int = 8) -> list[dict[str, Any]]:
    try:
        mms_core = _load_mms_core()
        audit_path = mms_core._config_audit_path(config_path)  # noqa: SLF001
        if not os.path.exists(audit_path):
            return []
        rows = []
        with open(audit_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]
    except Exception:
        return []


def _copy_backup_file(target_path: str, *, config_path: str, label: str) -> str:
    if not target_path or not os.path.exists(target_path):
        return ""
    mms_core = _load_mms_core()
    backup_root = mms_core._config_backup_root(config_path)  # noqa: SLF001
    backup_dir = os.path.join(backup_root, f"{label}-{mms_core._local_now_slug()}")  # noqa: SLF001
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(target_path))
    shutil.copy2(target_path, backup_path)
    shutil.copy2(target_path, f"{backup_path}.bak")
    return backup_path


def _bak_path_for_backup(backup_path: str) -> str:
    bak_path = f"{backup_path}.bak" if backup_path else ""
    return bak_path if bak_path and os.path.exists(bak_path) else ""


def _registry_v2_snapshot_generated_bundle(config_root: str) -> dict[str, Any]:
    generated_dir = os.path.join(config_root, "generated")
    summary: dict[str, Any] = {
        "schema": "mms.setup_web.registry_v2_generated_snapshot.v1",
        "generated_dir": generated_dir,
        "file_names": list(_REGISTRY_V2_GENERATED_FILES),
    }
    if not os.path.isdir(generated_dir):
        summary.update({"skipped": True, "reason": "missing_generated_dir", "files": []})
        return summary
    existing = [name for name in _REGISTRY_V2_GENERATED_FILES if os.path.isfile(os.path.join(generated_dir, name))]
    if not existing:
        summary.update({"skipped": True, "reason": "no_existing_bundle_files", "files": []})
        return summary
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(config_root, "backups", "generated", f"webui-apply-{slug}")
    os.makedirs(backup_dir, exist_ok=True)
    for name in existing:
        target = os.path.join(backup_dir, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(generated_dir, name), target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    manifest_path = os.path.join(backup_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema": "mms.setup_web.registry_v2_generated_snapshot_manifest.v1",
                "created_at": _now_iso(),
                "generated_dir": generated_dir,
                "files": existing,
            },
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    try:
        os.chmod(manifest_path, 0o600)
    except OSError:
        pass
    summary.update({"skipped": False, "backup_dir": backup_dir, "manifest_path": manifest_path, "files": existing})
    return summary


def _registry_v2_restore_generated_bundle(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"attempted": False, "reason": "missing_snapshot"}
    generated_dir = str(snapshot.get("generated_dir") or "")
    if not generated_dir:
        return {"attempted": False, "reason": "missing_generated_dir"}
    file_names = [str(name) for name in (snapshot.get("file_names") or _REGISTRY_V2_GENERATED_FILES)]
    removed: list[str] = []
    restored: list[str] = []
    backup_dir = str(snapshot.get("backup_dir") or "")
    if not os.path.isdir(generated_dir) and not backup_dir:
        return {
            "attempted": True,
            "snapshot_skipped": bool(snapshot.get("skipped")),
            "removed": removed,
            "restored": restored,
            "backup_dir": backup_dir,
        }
    os.makedirs(generated_dir, exist_ok=True)
    for name in file_names:
        target = os.path.join(generated_dir, name)
        if os.path.exists(target):
            os.remove(target)
            removed.append(name)
    for name in [str(item) for item in (snapshot.get("files") or [])]:
        source = os.path.join(backup_dir, name)
        target = os.path.join(generated_dir, name)
        if backup_dir and os.path.isfile(source):
            shutil.copy2(source, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            restored.append(name)
    try:
        if not os.listdir(generated_dir):
            os.rmdir(generated_dir)
    except OSError:
        pass
    return {
        "attempted": True,
        "snapshot_skipped": bool(snapshot.get("skipped")),
        "removed": removed,
        "restored": restored,
        "backup_dir": backup_dir,
    }


def _registry_v2_restore_webui_credential_backend(secret_backend: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(secret_backend, dict) or bool(secret_backend.get("skipped")):
        return {"attempted": False, "reason": "not_written"}
    path = str(secret_backend.get("path") or "")
    if not path:
        return {"attempted": False, "reason": "missing_path"}
    backup_path = str(secret_backend.get("backup_path") or "")
    if backup_path and os.path.isfile(backup_path):
        shutil.copy2(backup_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return {"attempted": True, "restored": True, "removed_new_file": False, "backup_path": backup_path}
    if os.path.exists(path):
        os.remove(path)
        return {"attempted": True, "restored": False, "removed_new_file": True, "path": path}
    return {"attempted": True, "restored": False, "removed_new_file": False, "path": path}


def _registry_v2_restore_db_candidate(candidate: dict[str, Any] | None, *, config_root: str) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {"attempted": False, "reason": "missing_candidate"}
    backup = candidate.get("backup") if isinstance(candidate.get("backup"), dict) else {}
    backup_path = str(backup.get("backup_path") or "")
    db_path = str(candidate.get("db_path") or backup.get("source_db_path") or "")
    if backup_path:
        from mms_registry_cli import restore_registry_db

        restore = restore_registry_db(
            backup_path,
            config_dir=config_root,
            db_path=db_path or None,
            apply=True,
            reason="webui-registry-v2-preview-apply-rollback",
        )
        return {"attempted": True, "restored": True, "removed_new_db": False, "restore": restore}
    if backup.get("reason") == "new_db" and db_path:
        removed: list[str] = []
        for suffix in ("", "-wal", "-shm"):
            target = f"{db_path}{suffix}"
            if os.path.exists(target):
                os.remove(target)
                removed.append(target)
        return {"attempted": True, "restored": False, "removed_new_db": bool(removed), "removed": removed}
    return {"attempted": False, "reason": "no_candidate_backup", "db_path": db_path}


def _rollback_registry_v2_preview_apply(
    *,
    config_root: str,
    candidate: dict[str, Any] | None,
    secret_backend: dict[str, Any] | None,
    generated_snapshot: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "attempted": True,
        "reason": reason,
        "generated": _registry_v2_restore_generated_bundle(generated_snapshot),
        "credential_backend": _registry_v2_restore_webui_credential_backend(secret_backend),
        "db": _registry_v2_restore_db_candidate(candidate, config_root=config_root),
    }


def _append_audit(*, config_path: str, target_path: str, backup_path: str, reason: str, before_sha1: str, after_sha1: str, function: str) -> None:
    mms_core = _load_mms_core()
    mms_core._append_config_audit_entry(  # noqa: SLF001
        {
            "timestamp": mms_core._iso_now(),  # noqa: SLF001
            "reason": reason,
            "target_path": os.path.abspath(target_path),
            "backup_path": backup_path,
            "caller_path": os.path.abspath(__file__),
            "caller_line": 0,
            "caller_function": function,
            "pid": os.getpid(),
            "before_sha1": before_sha1,
            "after_sha1": after_sha1,
        },
        config_path=config_path,
    )


def _save_provider_credentials_audited(update: dict[str, str], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    target_path = getattr(mms_core, "CREDENTIALS_PATH")
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        backup_path = _copy_backup_file(target_path, config_path=lock_path, label="credentials-write")
        mms_core.save_provider_credentials(
            update["provider_id"],
            update.get("base_url", ""),
            update.get("api_key", ""),
            openai_base_url=update.get("openai_base_url", ""),
            anthropic_base_url=update.get("anthropic_base_url", ""),
            openai_api_key=update.get("openai_api_key") if "openai_api_key" in update else None,
        )
        after_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=target_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_credentials",
        )
    return {"provider_id": update["provider_id"], "target_path": os.path.abspath(target_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def _write_model_policy_audited(policy_path: str, payload: dict[str, Any], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        backup_path = _copy_backup_file(policy_path, config_path=lock_path, label="model-policy-write")
        os.makedirs(os.path.dirname(policy_path), exist_ok=True)
        tmp_path = f"{policy_path}.tmp-{os.getpid()}-{time.time_ns()}"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(_pretty_json(payload))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, policy_path)
        os.chmod(policy_path, 0o600)
        after_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=policy_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_model_policy",
        )
    return {"target_path": os.path.abspath(policy_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def _preferences_target_path(*, config_path: str = "", preferences_path: str = "") -> str:
    preferences_path = _safe_text(preferences_path)
    if preferences_path:
        return os.path.abspath(os.path.expanduser(preferences_path))
    if config_path:
        return os.path.join(os.path.dirname(os.path.abspath(config_path)), "preferences.toml")
    mms_core = _load_mms_core()
    paths = getattr(mms_core, "PREFERENCES_PATHS", None)
    if isinstance(paths, list) and paths:
        return os.path.abspath(os.path.expanduser(str(paths[0])))
    return os.path.abspath(os.path.expanduser("~/.config/mms/preferences.toml"))


def _preferences_lock_path(*, config_path: str = "", preferences_path: str = "") -> str:
    if config_path:
        return os.path.abspath(config_path)
    target = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    return os.path.join(os.path.dirname(target), "config.toml")


def _load_preferences_raw(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    mms_core = _load_mms_core()
    try:
        loaded = mms_core._load_toml_file(path)  # noqa: SLF001
    except Exception:
        loaded = {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_asset_preferences_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    disabled = payload.get("disabled")
    if not isinstance(disabled, dict):
        disabled = ((payload.get("session_surfaces") or {}).get("disabled") if isinstance(payload.get("session_surfaces"), dict) else {})
    launch_payload = payload.get("launch") if isinstance(payload.get("launch"), dict) else {}
    disabled_clis_raw = payload.get("disabled_clis")
    if disabled_clis_raw is None:
        disabled_clis_raw = launch_payload.get("disabled_clis")
    assets = payload.get("assets") if isinstance(payload.get("assets"), dict) else {}
    mms_core = _load_mms_core()
    sanitize_disabled = getattr(mms_core, "_sanitize_disabled_session_surfaces", None)
    if callable(sanitize_disabled):
        disabled_clean = sanitize_disabled(disabled)
    else:
        disabled_clean = {}
    sanitize_disabled_clis = getattr(mms_core, "_sanitize_disabled_clis", None)
    if callable(sanitize_disabled_clis):
        disabled_clis = sanitize_disabled_clis(disabled_clis_raw)
    else:
        disabled_clis = []
    normalized: dict[str, Any] = {"session_surfaces": {"disabled": disabled_clean}, "assets": {}, "launch": {}}
    if disabled_clis_raw is not None:
        normalized["launch"]["disabled_clis"] = disabled_clis
    if "managed_enabled" in assets:
        normalized["assets"]["managed_enabled"] = _truthy(assets.get("managed_enabled"), default=True)
    managed_root = _safe_text(assets.get("managed_root"))
    if managed_root:
        normalized["assets"]["managed_root"] = os.path.abspath(os.path.expanduser(managed_root))
    return normalized


def _merge_asset_preferences(current: dict[str, Any], asset_preferences: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(current) if isinstance(current, dict) else {}
    incoming_launch = asset_preferences.get("launch") if isinstance(asset_preferences.get("launch"), dict) else {}
    if "disabled_clis" in incoming_launch:
        launch = result.get("launch") if isinstance(result.get("launch"), dict) else {}
        launch["disabled_clis"] = copy.deepcopy(incoming_launch.get("disabled_clis") or [])
        result["launch"] = launch

    session_surfaces = result.get("session_surfaces") if isinstance(result.get("session_surfaces"), dict) else {}
    disabled = ((asset_preferences.get("session_surfaces") or {}).get("disabled") if isinstance(asset_preferences.get("session_surfaces"), dict) else {})
    session_surfaces["disabled"] = copy.deepcopy(disabled) if isinstance(disabled, dict) else {}
    result["session_surfaces"] = session_surfaces

    assets = result.get("assets") if isinstance(result.get("assets"), dict) else {}
    incoming_assets = asset_preferences.get("assets") if isinstance(asset_preferences.get("assets"), dict) else {}
    for key in ("managed_enabled", "managed_root"):
        if key in incoming_assets:
            assets[key] = incoming_assets[key]
    result["assets"] = assets
    return result


def build_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    target_path = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    current = _load_preferences_raw(target_path)
    asset_preferences = _normalize_asset_preferences_payload(payload)
    next_prefs = _merge_asset_preferences(current, asset_preferences)
    before_text = _toml_text(current)
    after_text = _toml_text(next_prefs)
    diff_text = _diff_text(before_text, after_text, before_name="preferences.toml(before)", after_name="preferences.toml(after)")
    disabled = ((asset_preferences.get("session_surfaces") or {}).get("disabled") or {}) if isinstance(asset_preferences.get("session_surfaces"), dict) else {}
    disabled_clis = ((asset_preferences.get("launch") or {}).get("disabled_clis") or []) if isinstance(asset_preferences.get("launch"), dict) else []
    return {
        "ok": True,
        "schema": "mms.setup_web.preferences_plan.v1",
        "status": "planned",
        "target_path": target_path,
        "exists": os.path.exists(target_path),
        "will_write": bool(diff_text),
        "diff": diff_text,
        "preferences": next_prefs,
        "summary": {
            "disabled_clis": len(disabled_clis),
            "skills": len(disabled.get("skills") or []),
            "mcp": len(disabled.get("mcp") or []),
            "hooks": len(disabled.get("hooks") or []),
            "managed_root": ((asset_preferences.get("assets") or {}).get("managed_root") if isinstance(asset_preferences.get("assets"), dict) else ""),
        },
    }


def _copy_preferences_backup(target_path: str, *, lock_path: str) -> str:
    mms_core = _load_mms_core()
    backup_root = mms_core._config_backup_root(lock_path)  # noqa: SLF001
    backup_dir = os.path.join(backup_root, f"preferences-write-{mms_core._local_now_slug()}")  # noqa: SLF001
    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(target_path):
        backup_path = os.path.join(backup_dir, os.path.basename(target_path))
        shutil.copy2(target_path, backup_path)
        shutil.copy2(target_path, f"{backup_path}.bak")
        return backup_path
    marker_path = os.path.join(backup_dir, f"{os.path.basename(target_path) or 'preferences.toml'}.missing")
    with open(marker_path, "w", encoding="utf-8") as handle:
        handle.write(f"missing before preferences write: {target_path}\n")
    os.chmod(marker_path, 0o600)
    return marker_path


def apply_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_preferences"), False):
        return {"ok": False, "schema": "mms.setup_web.preferences_save_result.v1", "status": "blocked", "errors": ["保存 Skill/MCP 偏好前必须勾选确认。"]}
    if _safe_text(payload.get("confirm_phrase")) != "保存偏好":
        return {"ok": False, "schema": "mms.setup_web.preferences_save_result.v1", "status": "blocked", "errors": ["确认文字必须输入：保存偏好"]}
    plan = build_preferences_plan(payload, config_path=config_path, preferences_path=preferences_path)
    if not plan.get("will_write"):
        return {
            "ok": True,
            "schema": "mms.setup_web.preferences_save_result.v1",
            "status": "no_change",
            "target_path": plan.get("target_path"),
            "summary": plan.get("summary") or {},
            "message": "preferences.toml 已是当前 Skill/MCP 偏好。",
        }

    mms_core = _load_mms_core()
    target_path = str(plan.get("target_path") or "")
    lock_path = _preferences_lock_path(config_path=config_path, preferences_path=preferences_path)
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:asset-preferences"
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        backup_path = _copy_preferences_backup(target_path, lock_path=lock_path)
        _atomic_write_preferences_toml(target_path, plan["preferences"])
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass
        after_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=target_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_preferences",
        )
    return {
        "ok": True,
        "schema": "mms.setup_web.preferences_save_result.v1",
        "status": "saved",
        "target_path": target_path,
        "backup_path": backup_path,
        "bak_path": _bak_path_for_backup(backup_path),
        "summary": plan.get("summary") or {},
        "diff": plan.get("diff") or "",
        "audit_tail": _latest_audit_rows(lock_path),
    }


def _expand_reveal_path(raw_path: Any) -> str:
    path = _safe_text(raw_path)
    if not path or "\x00" in path or "\n" in path or "\r" in path or "://" in path:
        return ""
    if path.startswith("~"):
        try:
            mms_core = _load_mms_core()
            real_home = mms_core.resolve_real_user_home()
        except Exception:
            real_home = os.path.expanduser("~")
        if path == "~":
            path = real_home
        elif path.startswith("~/"):
            path = os.path.join(real_home, path[2:])
        else:
            path = os.path.expanduser(path)
    else:
        path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return path


def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Reveal a local file/folder from the local WebUI without shell execution."""
    payload = payload if isinstance(payload, dict) else {}
    target_path = _expand_reveal_path(payload.get("path"))
    if not target_path:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "blocked",
            "errors": ["只能打开本地文件或目录路径。"],
        }

    exists = os.path.exists(target_path)
    reveal_path = target_path if exists else os.path.dirname(target_path)
    if not reveal_path or not os.path.exists(reveal_path):
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "missing",
            "path": target_path,
            "errors": ["路径和父目录都不存在，无法打开。"],
        }

    if sys.platform == "darwin":
        command = ["open", reveal_path] if os.path.isdir(target_path) else ["open", "-R", reveal_path]
    elif sys.platform.startswith("win"):
        command = ["explorer", reveal_path if os.path.isdir(target_path) else f"/select,{reveal_path}"]
    else:
        folder = reveal_path if os.path.isdir(reveal_path) else os.path.dirname(reveal_path)
        opener = shutil.which("xdg-open")
        if not opener:
            return {
                "ok": False,
                "schema": "mms.setup_web.reveal_path_result.v1",
                "status": "blocked",
                "path": target_path,
                "errors": ["当前系统未找到 xdg-open，无法自动打开文件夹。"],
            }
        command = [opener, folder]

    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "error",
            "path": target_path,
            "errors": [str(exc)],
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "error",
            "path": target_path,
            "errors": [f"打开路径失败，退出码 {result.returncode}。"],
        }
    return {
        "ok": True,
        "schema": "mms.setup_web.reveal_path_result.v1",
        "status": "opened",
        "path": target_path,
        "opened_path": reveal_path,
        "exists": exists,
        "kind": "directory" if os.path.isdir(target_path) else ("file" if exists else "parent"),
    }


def apply_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_save"), False):
        return {"ok": False, "errors": ["保存前必须勾选确认保存。"], "status": "blocked"}
    if _safe_text(payload.get("confirm_phrase")) != "保存配置":
        return {"ok": False, "errors": ["确认文字必须输入：保存配置"], "status": "blocked"}
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_state_io import mms_config_root_status

        root_status = mms_config_root_status(command="mms-config-web", config_dir=config_root or None)
    except Exception:
        root_status = {}
    if root_status.get("mode") == "preview":
        return {
            "ok": False,
            "schema": "mms.setup_web.save_result.v1",
            "status": "blocked",
            "errors": ["preview root 已禁用 legacy /api/save；请使用“写入预览 DB + 发布”。"],
            "root": root_status,
        }
    plan = build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, include_secrets=True)
    if not plan.get("ok"):
        return {
            "ok": False,
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "status": "blocked",
            "plan": _sanitize_for_output(plan),
        }

    mms_core = _load_mms_core()
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:interactive-save"
    target_config_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    save_report: dict[str, Any] = {"config": {}, "credentials": [], "model_policy": {}, "routes_export": False}
    webui_config_backup_path = _copy_backup_file(target_config_path, config_path=target_config_path, label="setup-web-config-write")
    mms_core.save_config(plan["config"], reason=reason)
    save_report["config"] = {
        "target_path": os.path.abspath(target_config_path),
        "backup_path": webui_config_backup_path,
        "bak_path": _bak_path_for_backup(webui_config_backup_path),
    }

    for update in plan.get("credential_updates") or []:
        save_report["credentials"].append(_save_provider_credentials_audited(update, config_path=target_config_path, reason=f"{reason}:credentials"))

    policy_path = plan.get("paths", {}).get("model_policy") or _policy_path_for_config(target_config_path)
    if policy_path:
        save_report["model_policy"] = _write_model_policy_audited(policy_path, plan["model_policy"], config_path=target_config_path, reason=f"{reason}:model-policy")

    try:
        save_report["routes_export"] = bool(mms_core._refresh_routes_export_for_hive(plan["config"], force=True, quiet=True, startup_safe=True))  # noqa: SLF001
    except Exception:
        save_report["routes_export"] = False

    return {
        "ok": True,
        "schema": "mms.setup_web.save_result.v1",
        "status": "saved",
        "summary": plan.get("summary") or {},
        "warnings": plan.get("warnings") or [],
        "paths": plan.get("paths") or {},
        "save_report": save_report,
        "audit_tail": _latest_audit_rows(target_config_path),
    }


def apply_registry_v2_preview_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_v2_preview"), False):
        return {"ok": False, "errors": ["写入预览 DB 前必须勾选确认。"], "status": "blocked"}
    if _safe_text(payload.get("confirm_phrase")) != "写入预览DB":
        return {"ok": False, "errors": ["确认文字必须输入：写入预览DB"], "status": "blocked"}
    plan = build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, include_secrets=True, command_name="mmf")
    if not plan.get("ok"):
        return {
            "ok": False,
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "status": "blocked",
            "plan": _sanitize_for_output(plan),
        }
    v2_plan = plan.get("registry_v2_save_plan") if isinstance(plan.get("registry_v2_save_plan"), dict) else {}
    blocked_reasons = [str(item) for item in (v2_plan.get("blocked_reasons") or []) if str(item or "").strip()]
    if blocked_reasons:
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "blocked",
            "errors": blocked_reasons,
            "registry_v2_save_plan": v2_plan,
            "route_publish_guard": _sanitize_for_output(v2_plan.get("route_publish_guard") if isinstance(v2_plan.get("route_publish_guard"), dict) else {}),
        }

    config_root = _config_root_for_snapshot(config_path)
    route_publish_guard: dict[str, Any] = {}
    try:
        from mms_registry_cli import registry_v2_route_publish_guard

        route_publish_guard = registry_v2_route_publish_guard(
            config_dir=config_root or None,
            config_payload=plan.get("config") if isinstance(plan.get("config"), dict) else {},
            policy_payload=plan.get("model_policy") if isinstance(plan.get("model_policy"), dict) else {},
            credential_updates=[item for item in (plan.get("credential_updates") or []) if isinstance(item, dict)],
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload),
            route_scope_provider_ids=_route_scope_provider_ids_from_payload(payload),
            route_refresh_provider_ids=_route_refresh_provider_ids_from_payload(payload),
        )
    except Exception as exc:
        route_publish_guard = {
            "ok": False,
            "reason": "route_publish_guard_error",
            "message": f"{type(exc).__name__}: {exc}",
        }
    if not route_publish_guard.get("ok"):
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "blocked",
            "errors": [str(route_publish_guard.get("message") or route_publish_guard.get("reason") or "route publish guard blocked")],
            "registry_v2_save_plan": v2_plan,
            "route_publish_guard": _sanitize_for_output(route_publish_guard),
        }
    candidate: dict[str, Any] | None = None
    secret_backend: dict[str, Any] | None = None
    generated_snapshot: dict[str, Any] | None = None
    try:
        from mms_registry_cli import apply_registry_v2_save_candidate, publish_preview_bundle, verify_approved_bundle, write_registry_v2_webui_secret_backend

        credential_updates = [item for item in (plan.get("credential_updates") or []) if isinstance(item, dict)]
        generated_snapshot = _registry_v2_snapshot_generated_bundle(config_root)
        candidate = apply_registry_v2_save_candidate(
            config_dir=config_root or None,
            config_payload=plan.get("config") if isinstance(plan.get("config"), dict) else {},
            policy_payload=plan.get("model_policy") if isinstance(plan.get("model_policy"), dict) else {},
            credential_updates=credential_updates,
            apply=True,
            command_name="mms-config-web",
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload),
            route_scope_provider_ids=_route_scope_provider_ids_from_payload(payload),
            route_refresh_provider_ids=_route_refresh_provider_ids_from_payload(payload),
        )
        secret_backend = write_registry_v2_webui_secret_backend(
            config_dir=config_root or None,
            credential_updates=credential_updates,
            command_name="mms-config-web",
        )
        publish = publish_preview_bundle(config_dir=config_root or None)
        verify = verify_approved_bundle(config_dir=config_root or None)
    except Exception as exc:
        rollback = _rollback_registry_v2_preview_apply(
            config_root=config_root,
            candidate=candidate,
            secret_backend=secret_backend,
            generated_snapshot=generated_snapshot,
            reason=f"{type(exc).__name__}: {exc}",
        )
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "registry_v2_save_plan": v2_plan,
            "rollback": rollback,
        }

    verified = bool(verify.get("verified"))
    runtime_ready = publish.get("runtime_ready") is True
    missing_api_keys = int(publish.get("missing_api_key_count") or 0)
    missing_base_urls = int(publish.get("missing_base_url_count") or 0)
    provider_route_count = int(publish.get("provider_route_count") or 0)
    route_count = int(publish.get("route_count") or 0)
    runtime_next_action = {}
    if verified and not runtime_ready:
        if missing_api_keys:
            runtime_next_action = {
                "label": "填写 API Key 并勾选更新凭据后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里输入 API Key，勾选更新凭据，再点写入预览 DB + 发布",
            }
        elif missing_base_urls:
            runtime_next_action = {
                "label": "补齐 OpenAI/Anthropic base URL 后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里补齐 base URL，再点写入预览 DB + 发布",
            }
        elif provider_route_count <= 0:
            runtime_next_action = {
                "label": "给通道添加至少一个可见模型后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里添加 fallback/extra/可见模型，再点写入预览 DB + 发布",
            }
    credential_backend = {
        "schema": secret_backend.get("schema"),
        "skipped": bool(secret_backend.get("skipped")),
        "path": secret_backend.get("path"),
        "count": secret_backend.get("updated_secret_count", secret_backend.get("secret_count", 0)),
        "secret_count": secret_backend.get("secret_count", 0),
        "preserved_count": secret_backend.get("preserved_secret_count", 0),
        "backup_path": secret_backend.get("backup_path", ""),
        "plaintext_store": bool(secret_backend.get("plaintext_secret_store")),
    }
    rollback: dict[str, Any] = {}
    if not verified:
        rollback = _rollback_registry_v2_preview_apply(
            config_root=config_root,
            candidate=candidate,
            secret_backend=secret_backend,
            generated_snapshot=generated_snapshot,
            reason="verify_failed",
        )
    return {
        "ok": verified,
        "schema": "mms.setup_web.registry_v2_apply_result.v1",
        "status": "verified" if verified and runtime_ready else "verified_not_runtime_ready" if verified else "failed_verify",
        "runtime_ready": runtime_ready,
        "runtime_ready_reason": publish.get("runtime_ready_reason") or "",
        "runtime_blockers": {
            "missing_api_key_count": missing_api_keys,
            "missing_base_url_count": missing_base_urls,
            "provider_route_count": provider_route_count,
            "route_count": route_count,
        },
        "next_action": runtime_next_action,
        "summary": plan.get("summary") or {},
        "warnings": plan.get("warnings") or [],
        "paths": plan.get("paths") or {},
        "registry_v2_save_plan": v2_plan,
        "route_publish_guard": _sanitize_for_output(route_publish_guard),
        "candidate": _sanitize_for_output(candidate),
        "credential_backend": credential_backend,
        "publish": _sanitize_for_output(publish),
        "verify": _sanitize_for_output(verify),
        "rollback": rollback,
    }


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
    provider["protocols"] = _normalize_choice_list(provider.get("protocols"), _ALLOWED_PROTOCOLS, _ALLOWED_PROTOCOLS)
    if provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("openai_base_url")).rstrip("/")
    if provider.get("anthropic_base_url"):
        provider["anthropic_base_url"] = _safe_text(provider.get("anthropic_base_url")).rstrip("/")
    if provider.get("base_url") and not provider.get("openai_base_url"):
        provider["openai_base_url"] = _safe_text(provider.get("base_url")).rstrip("/")
    return _resolve_preview_provider_secret(provider, config_path=config_path, command_name=command_name)


def probe_provider_models(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
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
        probe = probe_provider_models(provider, force_refresh=_truthy(payload.get("force_refresh"), True))
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
