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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from mms_config.web_assets import _HTML_PAGE
from mms_session.inventory import build_session_assets_snapshot
from mms_config.web_settings import (
    _settings_action_cards,
    _webui_capability_coverage,
    _tui_webui_mapping,
    _tui_webui_mapping_summary,
    build_settings_report,
)
from mms_config.web_server import (
    ConfigWebApp,
    _SetupWebHandler,
    _html_page,
    run_config_web,
    serve_config_web,
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
        from mms_registry import router as mms_router

        return str(getattr(mms_router, "MODEL_POLICY_PATH", ""))
    except Exception:
        return ""


def _config_root_for_snapshot(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.dirname(config_path)
    try:
        from mms_runtime.state_io import resolve_mms_config_dir

        return resolve_mms_config_dir()
    except Exception:
        return ""


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry.cli import model_source_status

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
        from mms_registry.cli import consumer_bundle_status

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
        from mms_runtime.state_io import mms_config_root_status

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
    secret_ref = _safe_text(provider.get("secret_ref"))
    if provider_id and not secret_ref:
        secret_ref = _preview_secret_refs_by_provider(config_root).get(provider_id, "")
        if secret_ref:
            provider["secret_ref"] = secret_ref
    if secret_ref and not _safe_text(provider.get("api_key") or provider.get("openai_api_key") or provider.get("anthropic_api_key")):
        value = _preview_secret_values_by_ref(config_root).get(secret_ref, "")
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
    providers = cfg.get("providers") if isinstance(cfg.get("providers"), list) else []
    changed = False
    next_providers = []
    for provider in providers:
        if not isinstance(provider, dict):
            next_providers.append(provider)
            continue
        row = dict(provider)
        provider_id = _safe_text(row.get("id") or row.get("provider_id"))
        if provider_id and not _safe_text(row.get("secret_ref")) and refs.get(provider_id):
            row["secret_ref"] = refs[provider_id]
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
        secret_ref = _safe_text(route_info.get("secret_ref") or secret_refs.get(provider_id))
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
    return {"providers": providers, "provider": {"default": provider_default}}


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
        from mms_registry.cli import verify_approved_bundle

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
        return _attach_preview_secret_refs(result, config_path=config_path, command_name=command_name)
    result = copy.deepcopy(cfg)
    result["providers"] = hydrated["providers"]
    result["provider"] = hydrated["provider"]
    result["_preview_bundle_hydrated"] = True
    return _attach_preview_secret_refs(result, config_path=config_path, command_name=command_name)


def _config_v2_promotion_plan_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_registry.cli import config_v2_promotion_plan

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
        from mms_registry.cli import config_v2_release_readiness

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
        "vision": lower in _KNOWN_VISION_MODELS or lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-")),
        "tool_use": lower.startswith(("claude-", "gpt-", "o", "qwen", "kimi", "glm", "minimax", "mimo", "gemini-")),
        "reasoning": any(hint in lower for hint in _REASONING_HINTS),
        "thinking": lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-", "qwen3.5-plus", "qwen3.6-plus", "qwen3-max", "kimi", "k2.", "glm", "deepseek", "minimax")),
        "long_context": "1m" in lower or "long" in lower or lower.startswith(("qwen3", "kimi-k2", "gpt-5", "claude-", "mimo-v2.5", "minimax-m3")),
        "cache_sensitive": lower.startswith(_CACHE_SENSITIVE_PREFIXES),
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
    truth_payloads, refresh_reports, warnings = _load_capability_truth_payloads(
        config_path,
        refresh_sources=_truthy(payload.get("refresh_sources"), True),
    )
    # OpenRouter refresh should mean OpenRouter-only matching; the local snapshot button covers official/approved facts.
    if use_openrouter_catalog:
        truth_payloads = []
        refresh_reports = []
    catalog_sources: list[dict[str, Any]] = []
    if use_openrouter_catalog:
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
        "source_mode": "openrouter_catalog" if catalog_sources else "known_snapshots",
        "fields": [field for field in _CAPABILITY_TRUTH_REFRESH_FIELDS if field in fields],
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


def _opencode_agent_preset(agent_id: str, category: str = "") -> str:
    text = _safe_text(agent_id).lower()
    category = _safe_text(category).lower()
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


def _opencode_agent_catalog(profile_id: str = "agent") -> list[dict[str, Any]]:
    try:
        mms_core = _load_mms_core()
        specs = mms_core._opencode_lite_pro_specs(profile_id)  # noqa: SLF001 - setup UI mirrors launcher roster
    except Exception:
        specs = ()
    rows = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        agent = _safe_text(spec.get("agent"))
        if not agent:
            continue
        key = _safe_text(spec.get("key"))
        models = _normalize_model_list(spec.get("models"))
        category = "执行/协调"
        if "explore" in agent:
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
    opencode_profile = _safe_text(opencode_cfg.get("default_profile") or "agent")
    opencode_agent_catalog = _opencode_agent_catalog("agent")
    opencode = {
        "default_profile": opencode_profile,
        "recommended_profile": "agent",
        "profiles": ["agent", "omo", "raw"],
        "agent_models": opencode_agent_models,
        "agent_roster": _normalize_opencode_agent_roster(opencode_cfg.get("agent_roster"), profile_id="agent"),
        "agent_catalog": opencode_agent_catalog,
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


def _migration_config_from_snapshot(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_config_from_snapshot(*args, **kwargs)


def _migration_payload_config_from_cfg(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_payload_config_from_cfg(*args, **kwargs)


def _migration_preferences_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_preferences_payload(*args, **kwargs)


def _migration_collect_credentials(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_collect_credentials(*args, **kwargs)


def build_migration_export(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_export as build_migration_export_impl

    return build_migration_export_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def _parse_migration_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._parse_migration_bundle(*args, **kwargs)


def _migration_decrypted_credentials(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_decrypted_credentials(*args, **kwargs)


def _safe_local_command_name(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._safe_local_command_name(*args, **kwargs)


def _migration_start_status_from_snapshot(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_start_status_from_snapshot(*args, **kwargs)


def build_migration_start_status(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_start_status as build_migration_start_status_impl

    return build_migration_start_status_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def start_migration_work_session(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import start_migration_work_session as start_migration_work_session_impl

    return start_migration_work_session_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def _migration_provider_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_provider_payload(*args, **kwargs)


def _migration_preferences_apply_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_preferences_apply_payload(*args, **kwargs)


def _migration_draft_from_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._migration_draft_from_bundle(*args, **kwargs)


def _merge_model_policy_import(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._merge_model_policy_import(*args, **kwargs)


def _build_migration_import_plan(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_migration

    return web_migration._build_migration_import_plan(*args, **kwargs)


def build_migration_import_preview(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import build_migration_import_preview as build_migration_import_preview_impl

    return build_migration_import_preview_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


def apply_migration_import(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_migration import apply_migration_import as apply_migration_import_impl

    return apply_migration_import_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, command_name=command_name)


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
    from mms_config.web_plan import _build_model_policy_from_draft as build_model_policy_from_draft_impl

    return build_model_policy_from_draft_impl(policy_before, draft)


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
    from mms_config.web_review import build_review_summary

    return build_review_summary(
        current_cfg,
        next_cfg,
        policy_before,
        policy_after,
        credential_updates,
    )


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
    from mms_config.web_plan import _build_registry_v2_save_plan as build_registry_v2_save_plan_impl

    return build_registry_v2_save_plan_impl(
        config_path=config_path,
        plan_summary=plan_summary,
        credential_updates=credential_updates,
        config_payload=config_payload,
        policy_payload=policy_payload,
        expected_bundle_revision=expected_bundle_revision,
        route_scope_provider_ids=route_scope_provider_ids,
        route_refresh_provider_ids=route_refresh_provider_ids,
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
    from mms_config.web_plan import build_config_plan as build_config_plan_impl

    return build_config_plan_impl(
        current_cfg,
        payload,
        config_path=config_path,
        preferences_path=preferences_path,
        include_secrets=include_secrets,
        command_name=command_name,
    )


def _expected_bundle_revision_from_payload(payload: dict[str, Any] | None) -> str:
    from mms_config.web_plan import _expected_bundle_revision_from_payload as expected_bundle_revision_from_payload_impl

    return expected_bundle_revision_from_payload_impl(payload)


def _route_scope_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_scope_provider_ids_from_payload as route_scope_provider_ids_from_payload_impl

    return route_scope_provider_ids_from_payload_impl(payload)


def _route_refresh_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_refresh_provider_ids_from_payload as route_refresh_provider_ids_from_payload_impl

    return route_refresh_provider_ids_from_payload_impl(payload)


def _latest_audit_rows(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._latest_audit_rows(*args, **kwargs)


def _copy_backup_file(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._copy_backup_file(*args, **kwargs)


def _bak_path_for_backup(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._bak_path_for_backup(*args, **kwargs)


def _registry_v2_snapshot_generated_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_snapshot_generated_bundle(*args, **kwargs)


def _registry_v2_restore_generated_bundle(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_generated_bundle(*args, **kwargs)


def _registry_v2_restore_webui_credential_backend(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_webui_credential_backend(*args, **kwargs)


def _registry_v2_restore_db_candidate(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._registry_v2_restore_db_candidate(*args, **kwargs)


def _rollback_registry_v2_preview_apply(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._rollback_registry_v2_preview_apply(*args, **kwargs)


def _append_audit(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._append_audit(*args, **kwargs)


def _save_provider_credentials_audited(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._save_provider_credentials_audited(*args, **kwargs)


def _write_model_policy_audited(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._write_model_policy_audited(*args, **kwargs)


def _preferences_target_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._preferences_target_path(*args, **kwargs)


def _preferences_lock_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._preferences_lock_path(*args, **kwargs)


def _load_preferences_raw(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._load_preferences_raw(*args, **kwargs)


def _normalize_asset_preferences_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._normalize_asset_preferences_payload(*args, **kwargs)


def _merge_asset_preferences(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._merge_asset_preferences(*args, **kwargs)


def build_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import build_preferences_plan as build_preferences_plan_impl

    return build_preferences_plan_impl(payload, config_path=config_path, preferences_path=preferences_path)


def _copy_preferences_backup(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._copy_preferences_backup(*args, **kwargs)


def apply_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_preferences_plan as apply_preferences_plan_impl

    return apply_preferences_plan_impl(payload, config_path=config_path, preferences_path=preferences_path)


def _expand_reveal_path(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_apply

    return web_apply._expand_reveal_path(*args, **kwargs)


def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    from mms_config.web_apply import reveal_local_path as reveal_local_path_impl

    return reveal_local_path_impl(payload)


def apply_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_config_plan as apply_config_plan_impl

    return apply_config_plan_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def apply_registry_v2_preview_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    from mms_config.web_apply import apply_registry_v2_preview_plan as apply_registry_v2_preview_plan_impl

    return apply_registry_v2_preview_plan_impl(current_cfg, payload, config_path=config_path, preferences_path=preferences_path)


def _provider_from_payload(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._provider_from_payload(*args, **kwargs)


def probe_provider_models(provider: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
    from mms_config.web_probe import probe_provider_models as probe_provider_models_impl

    return probe_provider_models_impl(provider, force_refresh=force_refresh)


def test_provider_models(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_probe import test_provider_models as test_provider_models_impl

    return test_provider_models_impl(cfg, payload, config_path=config_path, command_name=command_name)


def _join_openai_chat_url(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._join_openai_chat_url(*args, **kwargs)


def _join_anthropic_messages_url(*args: Any, **kwargs: Any) -> Any:
    from mms_config import web_probe

    return web_probe._join_anthropic_messages_url(*args, **kwargs)


def run_model_smoke(
    cfg: dict[str, Any],
    payload: dict[str, Any],
    *,
    chat: bool = False,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    from mms_config.web_probe import run_model_smoke as run_model_smoke_impl

    return run_model_smoke_impl(cfg, payload, chat=chat, config_path=config_path, command_name=command_name)
