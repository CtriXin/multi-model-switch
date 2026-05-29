# -*- coding: utf-8 -*-
"""Local interactive WebUI for MMS setup, model policy, and audited config saves."""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import shutil
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


_SECRET_KEYS = {"api_key", "openai_api_key", "anthropic_api_key", "gateway_key", "token", "secret", "authorization"}
_SENSITIVE_CONFIG_KEYS = {"home_dir", "proxy", "no_proxy"}
_ALLOWED_PROTOCOLS = ("anthropic_messages", "openai_chat_completions")
_ALLOWED_CLIS = ("claude", "codex", "opencode", "agy")
_ALLOWED_ROLES = ("primary", "auto", "fallback")
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
    "qwen3.5-plus",
    "qwen3.6-flash",
    "qwen3.6-plus",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
}
_CACHE_SENSITIVE_PREFIXES = ("qwen", "kimi", "k2.", "glm", "deepseek", "minimax", "mimo")
_REASONING_HINTS = ("gpt-5", "o1-", "o3-", "o4-", "qwen3", "kimi-k2", "glm-5", "deepseek", "claude-opus", "claude-sonnet")


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
            elif key_lower in _SECRET_KEYS or any(token in key_lower for token in ("token", "secret", "api_key")):
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
        return _attach_preview_secret_refs(result, config_path=config_path, command_name=command_name)
    result = copy.deepcopy(cfg)
    result["providers"] = hydrated["providers"]
    result["provider"] = hydrated["provider"]
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


def _toml_text(payload: dict[str, Any]) -> str:
    try:
        import tomli_w

        return tomli_w.dumps(payload)
    except Exception:
        try:
            mms_core = _load_mms_core()
            if getattr(mms_core, "tomli_w", None) is not None:
                return mms_core.tomli_w.dumps(payload)
        except Exception:
            pass
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


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


def _model_capability_defaults(model_id: str, policy_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    model = _safe_text(model_id)
    lower = model.lower().rsplit("/", 1)[-1]
    caps = {
        "text": True,
        "vision": lower in _KNOWN_VISION_MODELS or lower.startswith(("claude-", "sonnet-", "opus-", "haiku-", "gemini-")),
        "tool_use": lower.startswith(("claude-", "gpt-", "o", "qwen", "kimi", "glm", "minimax", "gemini-")),
        "reasoning": any(hint in lower for hint in _REASONING_HINTS),
        "long_context": "1m" in lower or "long" in lower or lower.startswith(("qwen3", "kimi-k2", "gpt-5", "claude-")),
        "cache_sensitive": lower.startswith(_CACHE_SENSITIVE_PREFIXES),
    }
    if isinstance(policy_entry, dict):
        policy_caps = policy_entry.get("capabilities") if isinstance(policy_entry.get("capabilities"), dict) else {}
        for key in caps:
            if key in policy_caps and isinstance(policy_caps[key], bool):
                caps[key] = policy_caps[key]
            if key == "cache_sensitive" and isinstance(policy_caps.get("cache_sensitive_transport"), bool):
                caps[key] = policy_caps["cache_sensitive_transport"]
    return caps


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
                "capabilities": _model_capability_defaults(model_id, entry if isinstance(entry, dict) else {}),
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
        "auth_mode": auth_mode,
        "is_default": is_default,
        "default_label": cli_name.upper() if is_default else "备选",
        "home_dir_configured": bool(_safe_text(account.get("home_dir"))),
        "proxy_configured": bool(_safe_text(account.get("proxy"))),
        "timezone": _safe_text(account.get("timezone")),
        "status": "configured",
        "is_claude_human_only": is_claude,
        "webui_write_policy": "claude_human_only_locked" if is_claude else "draft_review_confirmed_save",
        "usage": _usage_summary("account", account_id),
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


def _settings_action_cards() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    try:
        from mms_tui_settings_actions import list_tui_settings_actions

        for descriptor in list_tui_settings_actions():
            item = descriptor.as_dict()
            item["webui_status"] = {
                "refresh-sources": "report_only",
                "probe-selected": "native_test_panel",
                "registry-doctor": "report_only",
                "recoverable-models": "planned",
                "interrupted-sessions": "report_only",
                "export-approved-bundle": "existing_save_flow",
                "legacy-tools-emergency-debug": "manual_cli_only",
                "usage-health-overlay": "report_only",
            }.get(str(item.get("action_id") or ""), "planned")
            actions.append(item)
    except Exception:
        actions = []
    return actions


def _webui_capability_coverage() -> list[dict[str, str]]:
    return [
        {
            "area": "通道",
            "capability": "provider add/edit/default/role/priority/base URL/key/protocol/CLI",
            "webui": "native",
            "tui": "can_degrade_after_save_flow_verified",
        },
        {
            "area": "通道",
            "capability": "模型拉取、manual extra_models、hidden_models、capability tags",
            "webui": "native",
            "tui": "can_degrade_after_route_guard_verified",
        },
        {
            "area": "通道",
            "capability": "本地 usage / last-used / health overlay",
            "webui": "read_only_summary",
            "tui": "keep_until_webui_report_actions_land",
        },
        {
            "area": "账号",
            "capability": "OAuth/account status/default/login/edit/remove",
            "webui": "draft_review_human_gate",
            "tui": "keep_emergency_only_for_login_remove_and_claude_human_gate",
        },
        {
            "area": "设置",
            "capability": "Registry truth / preview doctor / bundle/readiness/status",
            "webui": "read_only_reports_plus_existing_apply",
            "tui": "can_degrade_report_display_after_webui_smoke",
        },
        {
            "area": "设置",
            "capability": "Snapshot Guard accept / real config drift acceptance",
            "webui": "manual_cli_human_gate",
            "tui": "keep_until_webui_double_confirm_flow_exists",
        },
        {
            "area": "设置",
            "capability": "Rescue fallback config",
            "webui": "native",
            "tui": "can_degrade_config_display_after_save_flow_verified",
        },
        {
            "area": "设置",
            "capability": "Rescue packet browsing / fallback handover",
            "webui": "read_only_report",
            "tui": "keep_emergency_only_until_handover_write_flow_exists",
        },
        {
            "area": "设置",
            "capability": "UI language and About/version checks",
            "webui": "report_or_planned",
            "tui": "keep_small",
        },
    ]


def _tui_webui_mapping() -> list[dict[str, str]]:
    """Trace every Settings/Channel TUI action to its WebUI destination."""

    def row(
        row_id: str,
        *,
        tui_area: str,
        tui_action_id: str,
        tui_label: str,
        webui_section: str,
        webui_control: str,
        status: str,
        write_policy: str,
        verification: str,
        manual_check: str,
        webui_section_id: str = "",
        api_action: str = "",
    ) -> dict[str, str]:
        return {
            "id": row_id,
            "tui_area": tui_area,
            "tui_action_id": tui_action_id,
            "tui_label": tui_label,
            "webui_section": webui_section,
            "webui_section_id": webui_section_id,
            "webui_control": webui_control,
            "api_action": api_action,
            "status": status,
            "write_policy": write_policy,
            "verification": verification,
            "manual_check": manual_check,
        }

    rows = [
        row(
            "settings.provider_mgmt",
            tui_area="Settings",
            tui_action_id="provider_mgmt",
            tui_label="Provider 管理",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="左侧 provider list、通道配置 tab、模型配置 tab、保存审计",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan diff + /api/save or /api/registry-v2/apply",
            manual_check="检查 provider add/edit/default/model list 是否都能进入保存预览。",
        ),
        row(
            "settings.account_mgmt",
            tui_area="Settings",
            tui_action_id="account_mgmt",
            tui_label="账号管理",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="账号 / OAuth 通道表 + 非 Claude account 草稿",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/settings/report?action=accounts redacts home_dir/proxy",
            manual_check="非 Claude account 可改 name/enabled/priority/default；Claude/login/remove 保持锁定。",
        ),
        row(
            "settings.registry",
            tui_area="Settings",
            tui_action_id="registry",
            tui_label="模型真源",
            webui_section="真源状态 + 能力整合",
            webui_section_id="source",
            webui_control="真源状态 cards + report buttons + save/apply flow",
            api_action="model_source_status",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=model_source_status",
            manual_check="写入类 registry 操作必须继续走 save/apply human gate。",
        ),
        row(
            "settings.guard",
            tui_area="Settings",
            tui_action_id="guard",
            tui_label="启动快照",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="Snapshot Guard status/gate report",
            api_action="guard_status",
            status="human_gate",
            write_policy="manual_cli_human_gate",
            verification="/api/settings/report?action=guard_status",
            manual_check="accept 不自动执行；必须 human double-confirm。",
        ),
        row(
            "settings.rescue",
            tui_area="Settings",
            tui_action_id="rescue",
            tui_label="中断/救援",
            webui_section="Fallback",
            webui_section_id="fallback",
            webui_control="rescue fallback/hot fallback 表单 + rescue events report",
            api_action="rescue_events",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="fallback form feeds /api/plan; events use /api/settings/report?action=rescue_events",
            manual_check="fallback 写入前必须生成保存预览；packet handover 仍未自动写。",
        ),
        row(
            "settings.language",
            tui_area="Settings",
            tui_action_id="language",
            tui_label="界面语言",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="界面语言 selector + 保存审计",
            api_action="language_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/settings/report?action=language_status",
            manual_check="语言变化进入 /api/plan diff；不直接写真实 config。",
        ),
        row(
            "settings.routes_export",
            tui_area="Settings",
            tui_action_id="routes_export",
            tui_label="Legacy 路由导出",
            webui_section="保存 / 审计",
            webui_section_id="save",
            webui_control="生成保存预览、stable audited save、preview DB publish",
            api_action="routes_export",
            status="native",
            write_policy="save_flow_or_preview_publish",
            verification="/api/plan + /api/save or /api/registry-v2/apply",
            manual_check="直接导出按钮不单独暴露；保存/发布流负责 routes artifacts。",
        ),
        row(
            "settings.about",
            tui_area="Settings",
            tui_action_id="about",
            tui_label="关于",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="About report",
            api_action="about",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=about",
            manual_check="upgrade 动作仍是 manual CLI/human gate。",
        ),
        row(
            "provider.local_usage",
            tui_area="Channel / Provider",
            tui_action_id="provider:1",
            tui_label="查看本地统计",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="provider list usage chips + usage summary report",
            api_action="provider_usage_summary",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=provider_usage_summary",
            manual_check="完整 Rich usage table 尚未迁移；先提供 summary。",
        ),
        row(
            "provider.models",
            tui_area="Channel / Provider",
            tui_action_id="provider:2",
            tui_label="模型管理",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="模型配置 tab、fetch models、extra_models、hidden_models、capability toggles",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/provider/models + /api/plan",
            manual_check="检查模型拉取、隐藏/补充、capability toggle、stale cleanup。",
        ),
        row(
            "provider.default",
            tui_area="Channel / Provider",
            tui_action_id="provider:3",
            tui_label="设为默认网关",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="设为默认 provider checkbox",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan review_summary.default_provider",
            manual_check="默认 provider 变化必须出现在保存摘要。",
        ),
        row(
            "provider.rename",
            tui_area="Channel / Provider",
            tui_action_id="provider:4",
            tui_label="重命名",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="内部 ID + 显示名 fields",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider rename/remove/add diff",
            manual_check="ID 变化会影响 route scope，必须看 diff。",
        ),
        row(
            "provider.credentials",
            tui_area="Channel / Provider",
            tui_action_id="provider:5",
            tui_label="编辑地址和 Key",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="OpenAI/Anthropic base URL、models_endpoint、API Key pending save",
            status="native",
            write_policy="audited_secret_write",
            verification="/api/plan redacts key; save writes audited secret backend",
            manual_check="API Key 只显示 pending，不回显明文。",
        ),
        row(
            "provider.remove",
            tui_area="Channel / Provider",
            tui_action_id="provider:6",
            tui_label="删除通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="typed provider ID confirm + save review summary",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan review_summary.provider_removed",
            manual_check="删除只改 WebUI 草稿；真正写入仍需保存预览 + confirm。",
        ),
        row(
            "account.local_usage",
            tui_area="Channel / Account",
            tui_action_id="account:1",
            tui_label="查看本地统计",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="account table usage columns + account summary report",
            api_action="accounts",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=accounts",
            manual_check="完整 Rich usage table 尚未迁移；先提供 summary。",
        ),
        row(
            "account.login",
            tui_area="Channel / Account",
            tui_action_id="account:2",
            tui_label="重新登录",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="human gate report only",
            api_action="account_login_gate",
            status="human_gate",
            write_policy="manual_login_only",
            verification="/api/settings/report?action=account_login_gate",
            manual_check="登录会碰全局/OAuth 状态，WebUI 不自动执行。",
        ),
        row(
            "account.default",
            tui_area="Channel / Account",
            tui_action_id="account:3",
            tui_label="设为默认官方通道",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="non-Claude default radio buttons",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks Claude default and accepts non-Claude default",
            manual_check="Claude default radio disabled；非 Claude 进入保存预览。",
        ),
        row(
            "account.rename_edit",
            tui_area="Channel / Account",
            tui_action_id="account:4/5",
            tui_label="重命名 / 编辑通道",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="non-Claude name/enabled/priority draft fields",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks protected fields",
            manual_check="home_dir/proxy/no_proxy/Claude metadata 不进入 WebUI write。",
        ),
        row(
            "account.remove",
            tui_area="Channel / Account",
            tui_action_id="account:6",
            tui_label="删除通道",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="human gate report only",
            api_action="account_remove_gate",
            status="human_gate",
            write_policy="manual_remove_only",
            verification="/api/settings/report?action=account_remove_gate",
            manual_check="删除账号目录/登录状态必须由 human 手动确认。",
        ),
    ]

    registry_rows = [
        ("registry.model_source_status", "model_source_status", "查看 Model Source Status", "model_source_status", "report", "read_only_report"),
        ("registry.consumer_bundle_status", "consumer_bundle_status", "查看 Consumer Bundle", "consumer_bundle_status", "report", "read_only_report"),
        ("registry.v2_save_plan", "registry_v2_save_plan", "查看 v2 Save Plan", "", "native", "save_preview"),
        ("registry.config_v2_promotion_plan", "config_v2_promotion_plan", "查看 Promote Plan", "config_v2_promotion_plan", "report", "read_only_report"),
        ("registry.config_v2_release_readiness", "config_v2_release_readiness", "查看 4.0 Readiness", "config_v2_release_readiness", "report", "read_only_report"),
        ("registry.preview_doctor", "preview_doctor", "运行 Preview Doctor", "preview_doctor", "report", "read_only_report"),
        ("registry.check_staleness", "check_staleness", "检查 Source Staleness", "check_staleness", "report", "read_only_report"),
        ("registry.refresh_due_sources", "refresh_due_sources", "刷新到期 Sources", "refresh_due_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.scheduled_dry_run", "scheduled_dry_run", "定时刷新 Dry Run", "scheduled_refresh_gate", "human_gate", "network_human_gate"),
        ("registry.scheduled_no_network", "scheduled_no_network", "定时刷新 No Network", "scheduled_refresh_gate", "human_gate", "manual_cli_human_gate"),
        ("registry.refresh_sources", "refresh_sources", "刷新全部 Sources", "refresh_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.fetch_openrouter", "fetch_openrouter", "拉取 OpenRouter Catalog", "fetch_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.diff_openrouter", "diff_openrouter", "对比 OpenRouter Candidate", "diff_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.publish_approved", "publish_approved", "发布 Approved Bundle", "publish_approved_gate", "human_gate", "write_human_gate"),
        ("registry.verify_approved", "verify_approved", "验证 Approved Bundle", "verify_approved_gate", "human_gate", "manual_cli_human_gate"),
        ("registry.doctor", "doctor", "Registry Doctor / 状态", "registry_status", "report", "read_only_report"),
    ]
    for row_id, action_id, label, api_action, status, write_policy in registry_rows:
        rows.append(
            row(
                row_id,
                tui_area="Settings / Registry",
                tui_action_id=action_id,
                tui_label=label,
                webui_section="能力整合",
                webui_section_id="settings",
                webui_control="TUI ↔ WebUI 对照表 action button",
                api_action=api_action,
                status=status,
                write_policy=write_policy,
                verification=f"/api/settings/report?action={api_action}" if api_action else "/api/plan",
                manual_check="read-only 可直接点；network/write 类先 gate，不静默执行。",
            )
        )

    extra_rows = [
        ("guard.status", "Settings / Snapshot Guard", "status", "查看当前 Snapshot 状态", "guard_status", "report", "read_only_report"),
        ("guard.accept", "Settings / Snapshot Guard", "accept", "接受当前 Snapshot", "guard_accept_gate", "human_gate", "manual_cli_human_gate"),
        ("rescue.default", "Settings / Rescue", "choose_route_default/manual_default", "设置全局默认 fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.clear_default", "Settings / Rescue", "clear_default", "清除全局默认 fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.hot_fallback", "Settings / Rescue", "enable_hot_fallback/disable_hot_fallback", "开启/关闭 hot fallback", "", "native", "draft_review_confirmed_save"),
        ("rescue.view_packets", "Settings / Rescue", "view_packets", "查看最近失败 / rescue packet", "rescue_events", "report", "read_only_report"),
        ("rescue.create_demo", "Settings / Rescue", "create_demo", "生成测试 rescue packet", "rescue_create_demo_gate", "human_gate", "local_artifact_human_gate"),
        ("rescue.handover", "Settings / Rescue", "handover/manual_handover", "生成 fallback handover", "rescue_handover_gate", "missing", "planned_human_confirm"),
        ("rescue.view_md_paths", "Settings / Rescue", "view_md/show_paths", "查看 rescue.md / 显示文件路径", "rescue_events", "report", "read_only_report"),
        ("about.refresh", "Settings / About", "refresh_versions", "刷新版本检查", "about_refresh_gate", "human_gate", "network_human_gate"),
        ("about.upgrade", "Settings / About", "upgrade_mms/upgrade_codex_cli/upgrade_claude_cli", "升级 MMS / CLI", "about_upgrade_gate", "human_gate", "manual_cli_human_gate"),
    ]
    for row_id, area, action_id, label, api_action, status, write_policy in extra_rows:
        rows.append(
            row(
                row_id,
                tui_area=area,
                tui_action_id=action_id,
                tui_label=label,
                webui_section="Fallback" if area.endswith("Rescue") and status == "native" else "能力整合",
                webui_section_id="fallback" if area.endswith("Rescue") and status == "native" else "settings",
                webui_control="Fallback form" if area.endswith("Rescue") and status == "native" else "TUI ↔ WebUI 对照表 action button",
                api_action=api_action,
                status=status,
                write_policy=write_policy,
                verification=f"/api/settings/report?action={api_action}" if api_action else "/api/plan",
                manual_check="native 走保存预览；gate/missing 不会伪装成已迁移。",
            )
        )
    return rows


def _tui_webui_mapping_summary(rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = rows if isinstance(rows, list) else _tui_webui_mapping()
    counts = {"native": 0, "report": 0, "draft_review": 0, "human_gate": 0, "missing": 0}
    for item in rows:
        status = _safe_text(item.get("status"))
        if status in counts:
            counts[status] += 1
    return {
        "schema": "mms.setup_web.tui_mapping_summary.v1",
        "total": len(rows),
        "counts": counts,
        "source_files": ["mms_tui.py:_settings_menu", "mms_core.py settings/provider/account/rescue action handlers"],
        "policy": "native/report rows are WebUI-owned; human_gate/missing rows keep TUI/CLI as emergency or manual path.",
    }


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
        "setup_flow": build_setup_flow(),
        "test_contracts": build_test_contracts(),
        "paths": {
            "config": config_path,
            "preferences": preferences_path,
            "model_policy": policy_path,
        },
        "providers": provider_rows,
        "provider_default": provider_default or (provider_rows[0]["id"] if provider_rows else ""),
        "accounts": _account_summaries(cfg),
        "account_defaults": _account_defaults(cfg),
        "account_write_policy": {
            "status": "draft_review_confirmed_save",
            "claude": "human_only_locked",
            "allowed_fields": ["name", "enabled", "priority", "default_non_claude"],
            "blocked_fields": ["login", "remove", "home_dir", "proxy", "no_proxy", "claude_default", "claude_metadata"],
        },
        "settings_actions": _settings_action_cards(),
        "webui_capability_coverage": _webui_capability_coverage(),
        "tui_webui_mapping": tui_webui_mapping,
        "tui_webui_mapping_summary": _tui_webui_mapping_summary(tui_webui_mapping),
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
            "summary": "设置 preferred CLI、coding preset 和 OpenCode Multi-Agent profile。",
            "fields": ["preferred_cli", "opencode_profile", "executor", "reviewer", "explore", "vision_agents"],
            "actions": ["preview_launch", "save_audited"],
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
            "summary": "哪些日常偏好适合 preferences.toml，哪些真实配置必须 human gate。",
        },
        {
            "title": "OpenCode Lite Pro",
            "path": "docs/OPENCODE_LITE_LAUNCHER.md",
            "summary": "OpenSpec Multi、GPT executor、国产只读 explore/bug-hunt 的当前策略。",
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
    lines.extend(["", "## Preferred CLI", "", "```toml", snippets.get("preferred_cli", ""), "```"])
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
        if route_rows:
            provider["models"] = route_rows
        else:
            provider.pop("models", None)
    return provider


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
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        hidden = set(_normalize_model_list(provider.get("hidden_models")))
        caps_map = dict(provider.get("model_capabilities") if isinstance(provider.get("model_capabilities"), dict) else {})
        rows = provider.get("models") if isinstance(provider.get("models"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = _safe_text(row.get("id"))
            if not model_id:
                continue
            touched = row.get("policy_touched") is True or row.get("touched") is True
            if not touched:
                continue
            caps_map.setdefault(model_id, row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {})
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
            cap_payload = entry.setdefault("capabilities", {})
            if not isinstance(cap_payload, dict):
                cap_payload = {}
                entry["capabilities"] = cap_payload
            for key in ("text", "vision", "tool_use", "reasoning", "long_context"):
                if isinstance(caps.get(key), bool):
                    cap_payload[key] = bool(caps[key])
            if isinstance(caps.get("cache_sensitive"), bool):
                cap_payload["cache_sensitive_transport"] = bool(caps["cache_sensitive"])
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
            f"name/enabled/priority/note 将更新；CLI: `{cli_name or '-'}`。",
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

    policy_before_models = policy_before.get("models") if isinstance(policy_before.get("models"), dict) else {}
    policy_after_models = policy_after.get("models") if isinstance(policy_after.get("models"), dict) else {}
    if _mapping_digest({"models": policy_before_models}) != _mapping_digest({"models": policy_after_models}):
        changed_models = sorted(set(policy_before_models) ^ set(policy_after_models))
        common_changed = sorted(
            model for model in (set(policy_before_models) & set(policy_after_models))
            if _mapping_digest(policy_before_models.get(model)) != _mapping_digest(policy_after_models.get(model))
        )
        total = len(changed_models) + len(common_changed)
        add_item("model_policy", "模型能力/偏好策略变化", f"将更新 {total} 个 model-policy 条目。")

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
        },
        "items": items,
        "risks": risks,
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
    route_refresh_provider_ids = _route_refresh_provider_ids_from_payload(payload or {})
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
            credential_updates.append(
                {
                    "provider_id": provider["id"],
                    "base_url": (openai_base or anthropic_base).rstrip("/"),
                    "openai_base_url": openai_base.rstrip("/"),
                    "anthropic_base_url": anthropic_base.rstrip("/"),
                    "api_key": api_key if include_secrets else _redact(api_key),
                }
            )
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
            errors.append(f"preferred CLI 不支持: {preferred_cli}")
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
    default_profile = _safe_text(opencode_payload.get("default_profile"))
    agent_model_overrides = _normalize_agent_model_overrides(opencode_payload.get("agent_models") or opencode_payload.get("agent_model_overrides"))
    agent_roster = _normalize_opencode_agent_roster(opencode_payload.get("agent_roster"), profile_id="agent")
    if default_profile or "agent_models" in opencode_payload or "agent_model_overrides" in opencode_payload or "agent_roster" in opencode_payload:
        opencode_cfg = dict(next_cfg.get("opencode") if isinstance(next_cfg.get("opencode"), dict) else {})
        current_default_profile = _safe_text(opencode_cfg.get("default_profile"))
        if default_profile and (current_default_profile or default_profile != "agent"):
            opencode_cfg["default_profile"] = default_profile
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

    try:
        mms_core = _load_mms_core()
        if hasattr(mms_core, "_ensure_provider_config"):
            next_cfg, _ = mms_core._ensure_provider_config(next_cfg)  # noqa: SLF001 - reuse existing normalization
    except Exception:
        pass
    next_cfg = _strip_empty_provider_model_lists(next_cfg)

    before_config_text = _toml_text(_sanitize_for_output(current_cfg))
    after_config_text = _toml_text(_sanitize_for_output(next_cfg))
    before_policy_text = _pretty_json(_sanitize_for_output(policy_before))
    after_policy_text = _pretty_json(_sanitize_for_output(policy_after))
    diffs = {
        "config_toml": _diff_text(before_config_text, after_config_text, before_name="config.toml(before)", after_name="config.toml(after)"),
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
        "route_scope_provider_ids": _route_scope_provider_ids_from_payload(payload or {}),
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
            route_scope_provider_ids=_route_scope_provider_ids_from_payload(payload or {}),
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
        return {
            "ok": not bool(probe.get("error")),
            "provider_id": provider.get("id"),
            "models": models,
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


def _settings_gate_report(action: str, *, write_policy: str = "human_gate", note: str = "") -> dict[str, Any]:
    mapping_rows = [item for item in _tui_webui_mapping() if item.get("api_action") == action]
    return {
        "ok": True,
        "schema": "mms.setup_web.settings_report.v1",
        "action": action,
        "write_policy": write_policy,
        "status": "human_gate",
        "note": note or "该 TUI 动作会触发 network/write/OAuth/global-config 风险；WebUI 当前只显示 gate，不会自动执行。",
        "mapping": mapping_rows,
    }


def build_settings_report(
    cfg: dict[str, Any],
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return one bounded settings report for the WebUI; mutating TUI actions stay human-gated."""
    payload = payload if isinstance(payload, dict) else {}
    action = _safe_text(payload.get("action") or "coverage")
    snapshot = build_config_snapshot(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    mapping = snapshot.get("tui_webui_mapping") or []
    if action in {"tui_mapping", "tui_webui_mapping"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "mixed",
            "summary": snapshot.get("tui_webui_mapping_summary") or _tui_webui_mapping_summary(mapping),
            "mapping": mapping,
        }
    if action in {"coverage", "capability_coverage"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "coverage": snapshot.get("webui_capability_coverage") or [],
            "settings_actions": snapshot.get("settings_actions") or [],
            "tui_webui_mapping_summary": snapshot.get("tui_webui_mapping_summary") or {},
        }
    if action in {"accounts", "account_status"}:
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_human_gate",
            "accounts": snapshot.get("accounts") or [],
            "account_defaults": snapshot.get("account_defaults") or {},
            "account_write_policy": snapshot.get("account_write_policy") or {},
            "note": "WebUI 支持非 Claude account 的 name/enabled/priority/default 草稿预览；login/remove/home_dir/proxy 与 Claude account 仍 human-gated。",
        }
    if action in {"model_source_status", "source"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("model_source_status") or {}}
    if action in {"consumer_bundle_status", "bundle"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("consumer_bundle_status") or {}}
    if action in {"config_v2_promotion_plan", "promotion_plan"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("config_v2_promotion_plan") or {}}
    if action in {"config_v2_release_readiness", "release_readiness"}:
        return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": snapshot.get("config_v2_release_readiness") or {}}
    if action == "registry_v2_save_plan":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "save_preview",
            "note": "WebUI 的 v2 Save Plan 由“保存 / 审计”页的“生成保存预览”生成；不在 settings report 里构造假 plan。",
            "webui_section": "save",
        }
    if action == "check_staleness":
        try:
            from mms_registry_cli import source_freshness

            report = source_freshness()
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "preview_doctor":
        config_root = _config_root_for_snapshot(config_path)
        try:
            from mms_registry_cli import preview_doctor

            report = preview_doctor(config_dir=config_root or None, command_name=f"{command_name} config doctor")
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "registry_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "report": snapshot.get("model_source_status") or {},
            "note": "registry_status CLI can initialize SQLite; WebUI uses model_source_status instead to stay read-only.",
        }
    if action == "provider_usage_summary":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "providers": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "usage": item.get("usage") or {},
                    "model_count": item.get("model_count"),
                    "enabled": item.get("enabled"),
                    "role": item.get("role"),
                    "priority": item.get("priority"),
                }
                for item in (snapshot.get("providers") or [])
                if isinstance(item, dict)
            ],
        }
    if action == "guard_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "manual_cli_human_gate",
            "status": "human_gate",
            "commands": [f"{command_name} guard status", f"{command_name} guard accept"],
            "note": "WebUI 当前只显示 Snapshot Guard gate；accept 会改变 config guard baseline，必须 human double-confirm 后走 CLI。",
        }
    if action == "language_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "ui_language": _safe_text((cfg.get("ui") if isinstance(cfg.get("ui"), dict) else {}).get("language") or "zh"),
            "note": "WebUI Settings 页可暂存 ui.language，真正写入仍要经过保存预览与 confirm。",
        }
    if action == "routes_export":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "save_flow_or_preview_publish",
            "status": "native",
            "webui_section": "save",
            "note": "Legacy model-routes.json 不再单独做 settings 按钮；WebUI 保存/preview publish 会产出对应 routes artifacts。",
            "writes": (snapshot.get("save_contract") or {}).get("preview_v2_writes") or [],
        }
    if action == "about":
        try:
            mms_core = _load_mms_core()
            report = mms_core._about_status_snapshot(force_update=False)  # noqa: SLF001 - read-only cached about status
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "rescue_events":
        try:
            from mms_rescue import list_rescue_events

            events = list_rescue_events(repo_root=os.getcwd(), limit=20)
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "events": _sanitize_for_output(events)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    gate_actions = {
        "guard_accept_gate": ("manual_cli_human_gate", "Snapshot Guard accept 会更新 guard baseline；WebUI 不自动执行。"),
        "provider_remove_gate": ("planned_human_confirm", "删除 provider 需要 typed confirm + diff review；本 slice 只标出缺口。"),
        "account_login_gate": ("manual_login_only", "OAuth login 会写外部账号状态；WebUI 当前不触发。"),
        "account_remove_gate": ("manual_remove_only", "删除 account 可能删除账号目录/登录状态；WebUI 当前不触发。"),
        "refresh_due_sources_gate": ("network_write_human_gate", "刷新 registry source 可能触发 network/write；当前保持 human gate。"),
        "scheduled_refresh_gate": ("network_human_gate", "scheduled refresh 需要单独确认执行模式；当前保持 human gate。"),
        "refresh_sources_gate": ("network_write_human_gate", "刷新全部 sources 是 network/write 动作；当前保持 human gate。"),
        "fetch_openrouter_gate": ("network_human_gate", "Fetch OpenRouter Catalog 需要联网；当前保持 human gate。"),
        "diff_openrouter_gate": ("network_human_gate", "OpenRouter diff 可能依赖外部 catalog；当前保持 human gate。"),
        "publish_approved_gate": ("write_human_gate", "发布 approved bundle 是写入动作；WebUI 只允许通过保存/发布审计流执行。"),
        "verify_approved_gate": ("manual_cli_human_gate", "verify approved 当前保留 CLI/manual path。"),
        "rescue_create_demo_gate": ("local_artifact_human_gate", "生成 demo rescue packet 会写本地 artifact；当前不自动执行。"),
        "rescue_handover_gate": ("planned_human_confirm", "fallback handover 写 artifact；后续需要 WebUI confirm flow。"),
        "about_refresh_gate": ("network_human_gate", "刷新版本检查可能联网；当前不自动执行。"),
        "about_upgrade_gate": ("manual_cli_human_gate", "升级 MMS/Codex/Claude CLI 是外部写入/安装动作；必须 human 手动执行。"),
    }
    if action in gate_actions:
        write_policy, note = gate_actions[action]
        return _settings_gate_report(action, write_policy=write_policy, note=note)
    return {
        "ok": False,
        "schema": "mms.setup_web.settings_report.v1",
        "action": action,
        "error": "unknown settings report action",
        "available_actions": [
            "tui_mapping",
            "coverage",
            "accounts",
            "model_source_status",
            "consumer_bundle_status",
            "registry_v2_save_plan",
            "config_v2_promotion_plan",
            "config_v2_release_readiness",
            "preview_doctor",
            "check_staleness",
            "registry_status",
            "provider_usage_summary",
            "guard_status",
            "language_status",
            "routes_export",
            "about",
            "rescue_events",
            *sorted(gate_actions.keys()),
        ],
    }


_HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMS 配置中心</title>
  <style>
    :root {
      --bg:      oklch(97% 0.004 250);
      --surface: oklch(100% 0 0);
      --fg:      oklch(16% 0.015 250);
      --muted:   oklch(50% 0.015 250);
      --border:  oklch(88% 0.008 250);
      --accent:  oklch(54% 0.16 155);

      --ok:      oklch(55% 0.14 145);
      --warn:    oklch(68% 0.11 80);
      --danger:  oklch(55% 0.18 25);

      --accent-soft:  color-mix(in oklch, var(--accent) 10%, transparent);
      --accent-hover: color-mix(in oklch, var(--accent) 80%, black);
      --fg-soft:      color-mix(in oklch, var(--fg) 5%, transparent);
      --fg-ghost:     color-mix(in oklch, var(--fg) 8%, transparent);
      --ok-soft:      color-mix(in oklch, var(--ok) 12%, transparent);
      --warn-soft:    color-mix(in oklch, var(--warn) 12%, transparent);
      --danger-soft:  color-mix(in oklch, var(--danger) 12%, transparent);

      --shadow-sm: 0 1px 2px oklch(0% 0 0 / 0.04);
      --shadow:    0 1px 3px oklch(0% 0 0 / 0.06), 0 1px 2px oklch(0% 0 0 / 0.04);
      --shadow-md: 0 4px 6px -1px oklch(0% 0 0 / 0.05), 0 2px 4px -2px oklch(0% 0 0 / 0.04);
      --shadow-lg: 0 10px 15px -3px oklch(0% 0 0 / 0.05), 0 4px 6px -4px oklch(0% 0 0 / 0.03);

      --font-body: 'Geist', 'Satoshi', 'Avenir Next', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
      --font-mono: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace;

      --radius:    10px;
      --radius-lg: 14px;
      --radius-xl: 18px;

      --gap-xs: 6px;
      --gap-sm: 10px;
      --gap-md: 16px;
      --gap-lg: 24px;
      --gap-xl: 32px;
    }

    *, *::before, *::after { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: var(--font-body);
      font-size: 14px;
      line-height: 1.55;
      text-rendering: optimizeLegibility;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
    }
    img, svg { display: block; max-width: 100%; }
    a { color: inherit; text-decoration: none; }
    button { font: inherit; cursor: pointer; }
    p { text-wrap: pretty; margin: 0; }
    h1, h2, h3, h4 { text-wrap: balance; margin: 0; }
    pre { margin: 0; }

    /* ===== Header ===== */
    header {
      padding: 24px clamp(18px, 4vw, 56px) 16px;
      display: grid;
      grid-template-columns: 1.5fr .5fr;
      gap: 20px;
      align-items: end;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    h1 {
      font-size: clamp(26px, 3.5vw, 42px);
      line-height: 1.15;
      letter-spacing: -0.025em;
      font-weight: 700;
      color: var(--fg);
    }
    .lead {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
      max-width: 560px;
      margin-top: 6px;
    }
    .statusbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    /* ===== Shell layout ===== */
    .shell {
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 28px;
      padding: 24px clamp(18px, 4vw, 56px) 48px;
      max-width: 1440px;
      margin: 0 auto;
    }
    .side {
      position: sticky;
      top: 20px;
      align-self: start;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 10px;
      box-shadow: var(--shadow-sm);
    }
    .content {
      display: grid;
      gap: 24px;
    }

    /* ===== Sidebar nav ===== */
    .navbtn {
      width: 100%;
      border: 0;
      background: transparent;
      text-align: left;
      border-radius: var(--radius);
      padding: 10px 12px;
      margin: 3px 0;
      cursor: pointer;
      color: var(--fg);
      font-size: 14px;
      font-weight: 500;
      transition: all .15s ease;
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .navbtn:hover {
      background: var(--fg-soft);
    }
    .navbtn.active {
      background: var(--accent);
      color: #fff;
      box-shadow: var(--shadow-sm);
    }
    .navbtn small {
      display: block;
      font-size: 11.5px;
      font-weight: 400;
      color: var(--muted);
      margin-top: 1px;
    }
    .navbtn.active small { color: rgba(255,255,255,0.82); }

    /* ===== Panels ===== */
    .panel {
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      padding: 28px;
      box-shadow: var(--shadow-sm);
      transition: box-shadow .2s ease;
    }
    .panel:hover {
      box-shadow: var(--shadow);
    }
    .panel h2 {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel > p:first-of-type {
      color: var(--muted);
      font-size: 13.5px;
      line-height: 1.6;
      margin-bottom: 22px;
    }
    .panel h3 {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--fg);
    }

    /* ===== Cards ===== */
    .card {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--bg);
      padding: 18px;
      transition: border-color .15s ease, box-shadow .15s ease;
    }
    .card:hover {
      border-color: color-mix(in oklch, var(--accent) 20%, var(--border));
    }

    /* ===== Settings mission control ===== */
    .settings-command {
      border: 1.5px solid color-mix(in oklch, var(--fg) 22%, var(--border));
      background:
        linear-gradient(90deg, color-mix(in oklch, var(--fg) 4%, transparent) 1px, transparent 1px),
        linear-gradient(0deg, color-mix(in oklch, var(--fg) 4%, transparent) 1px, transparent 1px),
        color-mix(in oklch, var(--surface) 86%, var(--bg));
      background-size: 26px 26px;
      border-radius: 0;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 16px 36px color-mix(in oklch, var(--fg) 10%, transparent);
    }
    .settings-command-head {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: start;
      border-bottom: 1.5px solid var(--fg);
      padding-bottom: 14px;
      margin-bottom: 14px;
    }
    .settings-kicker {
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: var(--danger);
      margin-bottom: 6px;
    }
    .settings-command h3 {
      font-size: clamp(28px, 4.5vw, 56px);
      line-height: .92;
      letter-spacing: -.06em;
      text-transform: uppercase;
      max-width: 820px;
      margin: 0;
    }
    .settings-command p {
      max-width: 760px;
      color: color-mix(in oklch, var(--fg) 72%, var(--muted));
    }
    .settings-stamp {
      align-self: start;
      border: 1.5px solid var(--danger);
      color: var(--danger);
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .08em;
      padding: 8px 10px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .settings-metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      background: var(--fg);
      margin-bottom: 14px;
    }
    .settings-metric {
      background: var(--surface);
      padding: 14px;
      min-height: 92px;
    }
    .settings-metric span {
      display: block;
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--muted);
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .settings-metric strong {
      display: block;
      font-family: var(--font-mono);
      font-size: clamp(24px, 4vw, 44px);
      line-height: 1;
      margin: 10px 0 4px;
      font-variant-numeric: tabular-nums;
    }
    .settings-metric em {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-style: normal;
    }
    .settings-route {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .settings-route-card {
      border-left: 3px solid var(--fg);
      background: color-mix(in oklch, var(--fg) 5%, transparent);
      padding: 12px;
    }
    .settings-route-card.locked { border-left-color: var(--danger); }
    .settings-route-card.ready { border-left-color: var(--accent); }
    .settings-route-card.report { border-left-color: var(--warn); }
    .settings-route-card b {
      display: block;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .07em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .settings-route-card small {
      display: block;
      color: var(--muted);
      line-height: 1.45;
    }
    .settings-empty-note {
      border: 1px dashed color-mix(in oklch, var(--fg) 26%, var(--border));
      background: color-mix(in oklch, var(--warn) 9%, transparent);
      padding: 12px;
      margin: 12px 0 0;
      color: color-mix(in oklch, var(--fg) 76%, var(--muted));
    }
    .mapping-card {
      background:
        radial-gradient(circle at top right, color-mix(in oklch, var(--accent) 10%, transparent), transparent 32%),
        var(--bg);
    }
    .mapping-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: end;
      margin-bottom: 12px;
    }
    .filterbar.compact {
      margin: 0;
      justify-content: flex-end;
    }
    .mapping-action {
      border-radius: 0;
      padding: 6px 10px;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .04em;
      text-transform: uppercase;
    }
    .status-native { background: var(--ok-soft); color: var(--ok); }
    .status-report { background: var(--warn-soft); color: color-mix(in oklch, var(--warn) 72%, black); }
    .status-draft_review { background: var(--accent-soft); color: var(--accent); }
    .status-human_gate { background: var(--danger-soft); color: var(--danger); }
    .status-missing {
      background: var(--fg-soft);
      color: var(--muted);
      border: 1px dashed color-mix(in oklch, var(--fg) 18%, var(--border));
    }
    .delete-zone {
      border: 1.5px dashed color-mix(in oklch, var(--danger) 42%, var(--border));
      background: color-mix(in oklch, var(--danger) 7%, transparent);
      border-radius: var(--radius);
      padding: 12px;
    }

    /* ===== Grid system ===== */
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
    }
    .span4 { grid-column: span 4; }
    .span5 { grid-column: span 5; }
    .span6 { grid-column: span 6; }
    .span7 { grid-column: span 7; }
    .span8 { grid-column: span 8; }
    .span12 { grid-column: span 12; }

    /* ===== Forms ===== */
    label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      margin: 0 0 6px;
      letter-spacing: 0.01em;
    }
    input, select, textarea {
      width: 100%;
      border: 1.5px solid var(--border);
      background: var(--surface);
      border-radius: var(--radius);
      padding: 10px 12px;
      font: inherit;
      font-size: 14px;
      color: var(--fg);
      transition: border-color .15s ease, box-shadow .15s ease, outline .15s ease;
    }
    input:hover, select:hover, textarea:hover {
      border-color: color-mix(in oklch, var(--fg) 25%, var(--border));
    }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
    }
    textarea {
      min-height: 88px;
      resize: vertical;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.55;
    }
    select { cursor: pointer; }
    input[type="password"] { font-family: var(--font-mono); }

    /* ===== Checkbox groups ===== */
    .checks {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .check {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1.5px solid var(--border);
      border-radius: 999px;
      padding: 7px 13px;
      background: var(--surface);
      font-size: 13px;
      cursor: pointer;
      transition: border-color .15s ease, background .15s ease;
      user-select: none;
    }
    .check:hover {
      border-color: color-mix(in oklch, var(--accent) 30%, var(--border));
      background: var(--accent-soft);
    }
    .check input {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
      margin: 0;
    }

    /* ===== Buttons ===== */
    button, .button {
      border: 0;
      border-radius: 999px;
      padding: 9px 17px;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      transition: background .15s ease, transform .06s ease, box-shadow .15s ease;
      box-shadow: var(--shadow-sm);
    }
    button:hover, .button:hover {
      background: var(--accent-hover);
      box-shadow: var(--shadow);
    }
    button:active, .button:active { transform: translateY(1px); }
    button.secondary, .button.secondary {
      background: var(--fg-ghost);
      color: var(--fg);
      box-shadow: none;
    }
    button.secondary:hover, .button.secondary:hover {
      background: var(--fg-soft);
    }
    button.ghost, .button.ghost {
      background: transparent;
      color: var(--fg);
      border: 1.5px solid var(--border);
      box-shadow: none;
    }
    button.ghost:hover, .button.ghost:hover {
      border-color: var(--fg);
      background: var(--fg-soft);
    }
    button.danger, .button.danger { background: var(--danger); }
    button.danger:hover, .button.danger:hover {
      background: color-mix(in oklch, var(--danger) 82%, black);
    }
    button:disabled, .button:disabled { opacity: .45; cursor: not-allowed; }

    .btns {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
      align-items: center;
    }

    /* ===== Provider list ===== */
    .provider-list { display: grid; gap: 6px; }
    .provider-item {
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      padding: 12px 14px;
      background: var(--surface);
      cursor: pointer;
      font-size: 13px;
      transition: all .15s ease;
    }
    .provider-item:hover {
      border-color: color-mix(in oklch, var(--accent) 30%, var(--border));
      box-shadow: var(--shadow-sm);
    }
    .provider-item.active {
      outline: none;
      border-color: var(--accent);
      background: var(--accent-soft);
      box-shadow: 0 0 0 1px var(--accent);
    }
    .provider-item strong {
      display: block;
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 2px;
    }

    /* ===== Channel layout: sidebar + main ===== */
    .channel-layout {
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 20px;
      align-items: start;
    }
    .channel-sidebar {
      position: sticky;
      top: 20px;
      max-height: calc(100vh - 120px);
      overflow: auto;
      scrollbar-gutter: stable;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .channel-sidebar .btns {
      margin-top: 4px;
      flex-shrink: 0;
    }
    .channel-main {
      display: flex;
      flex-direction: column;
      gap: 24px;
      min-width: 0;
    }
    .channel-main .provider-editor {
      position: static;
      max-height: none;
      overflow: visible;
      align-self: stretch;
    }

    /* ===== Provider tabs ===== */
    .provider-tabs {
      display: flex;
      gap: 2px;
      border-bottom: 1.5px solid var(--border);
      margin-bottom: 4px;
      padding: 0 2px;
    }
    .tab-btn {
      background: transparent;
      border: 0;
      border-bottom: 2.5px solid transparent;
      padding: 10px 16px;
      font-size: 14px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      transition: all .15s ease;
      border-radius: var(--radius) var(--radius) 0 0;
      box-shadow: none;
      margin-bottom: -1.5px;
    }
    .tab-btn:hover {
      color: var(--fg);
      background: var(--fg-soft);
    }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
      background: var(--accent-soft);
    }
    .tab-panel {
      display: none;
      animation: fadeIn .2s ease both;
    }
    .tab-panel.active {
      display: block;
    }

    .model-section {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .model-section h3 {
      font-size: 18px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .model-section > p {
      color: var(--muted);
      font-size: 13.5px;
      line-height: 1.6;
    }

    /* ===== Pills ===== */
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 5px 11px;
      background: var(--surface);
      font-size: 12px;
      color: var(--muted);
      box-shadow: var(--shadow-sm);
    }
    .pill.ok {
      color: var(--ok);
      border-color: var(--ok-soft);
      background: var(--ok-soft);
    }
    .pill.warn {
      color: var(--warn);
      border-color: var(--warn-soft);
      background: var(--warn-soft);
    }

    /* ===== Tags ===== */
    .tag {
      display: inline-block;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 3px 9px;
      font-size: 11px;
      font-weight: 600;
      margin: 2px;
      letter-spacing: 0.01em;
    }
    .tag.off {
      background: var(--fg-soft);
      color: var(--muted);
      font-weight: 500;
    }

    /* ===== Tables ===== */
    .table-wrap {
      overflow: auto;
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
      font-size: 13px;
    }
    th, td {
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 1;
      font-weight: 600;
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    td input[type="checkbox"] {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
    }
    tbody tr {
      transition: background .1s ease;
    }
    tbody tr:hover {
      background: var(--fg-soft);
    }

    /* ===== Chips ===== */
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1.5px solid var(--border);
      border-radius: 999px;
      padding: 5px 11px;
      background: var(--surface);
      font-size: 12px;
      transition: border-color .15s ease;
    }
    .chip:hover {
      border-color: color-mix(in oklch, var(--accent) 25%, var(--border));
    }
    .chip button {
      padding: 0 4px;
      background: transparent;
      color: var(--muted);
      border: 0;
      cursor: pointer;
      font-size: 15px;
      line-height: 1;
      border-radius: 4px;
      box-shadow: none;
    }
    .chip button:hover { color: var(--danger); }

    /* ===== Result / Diff blocks ===== */
    .result, .diff {
      white-space: pre-wrap;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.6;
      background: var(--bg);
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      padding: 18px;
      max-height: 420px;
      overflow: auto;
      color: var(--fg);
      box-shadow: inset var(--shadow-sm);
    }
    .diff { max-height: 320px; }

    /* ===== OpenCode metrics ===== */
    .oc-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .oc-metric {
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 16px;
      text-align: center;
      transition: border-color .15s ease, box-shadow .15s ease;
    }
    .oc-metric:hover {
      border-color: color-mix(in oklch, var(--accent) 20%, var(--border));
      box-shadow: var(--shadow-sm);
    }
    .oc-metric strong {
      display: block;
      font-size: 22px;
      color: var(--fg);
      margin: 6px 0;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .oc-metric .muted { font-size: 11px; }
    .oc-metric .mono {
      font-size: 11px;
      color: var(--muted);
    }

    .oc-advanced {
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      padding: 18px;
      background: var(--bg);
      transition: border-color .15s ease;
    }
    .oc-advanced:hover {
      border-color: color-mix(in oklch, var(--accent) 25%, var(--border));
    }
    .oc-advanced summary {
      cursor: pointer;
      font-weight: 600;
      color: var(--fg);
      font-size: 14px;
      user-select: none;
    }
    .oc-advanced summary::marker { color: var(--muted); }

    .oc-order-note {
      border-left: 3px solid var(--accent);
      background: var(--accent-soft);
      border-radius: 0 var(--radius) var(--radius) 0;
      padding: 12px 16px;
      margin: 14px 0;
      color: var(--fg);
      font-size: 13px;
      line-height: 1.6;
    }
    .oc-enabled {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
    }

    /* ===== Filter bar ===== */
    .filterbar {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin: 14px 0;
    }
    .filterbar button {
      background: var(--fg-ghost);
      color: var(--fg);
      box-shadow: none;
      font-size: 13px;
      padding: 7px 13px;
    }
    .filterbar button.active {
      background: var(--accent);
      color: #fff;
      box-shadow: var(--shadow-sm);
    }

    /* ===== Empty / default helpers ===== */
    .empty-row {
      padding: 22px;
      color: var(--muted);
      text-align: center;
      font-size: 14px;
    }
    .default-route {
      max-width: 300px;
      white-space: normal;
      font-size: 12px;
      color: var(--muted);
    }

    /* ===== Toast ===== */
    .toast {
      position: fixed;
      bottom: 28px;
      right: 28px;
      padding: 14px 22px;
      background: var(--fg);
      color: var(--surface);
      border-radius: var(--radius-lg);
      opacity: 0;
      transform: translateY(16px) scale(0.96);
      transition: opacity .35s cubic-bezier(.4,0,.2,1), transform .35s cubic-bezier(.4,0,.2,1);
      pointer-events: none;
      z-index: 100;
      font-size: 14px;
      font-weight: 500;
      box-shadow: var(--shadow-lg);
      max-width: 400px;
      word-break: break-word;
    }
    .toast.show {
      opacity: 1;
      transform: translateY(0) scale(1);
    }

    /* ===== Utilities ===== */
    .muted {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .mono {
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }
    .hide { display: none !important; }

    /* ===== Section entrance animation ===== */
    [data-section] {
      animation: fadeIn .25s ease both;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    /* ===== Responsive ===== */
    @media (max-width: 980px) {
      header { grid-template-columns: 1fr; }
      .statusbar { justify-content: flex-start; }
      .shell { grid-template-columns: 1fr; padding: 16px; }
      .side, .provider-editor {
        position: relative;
        top: auto;
        max-height: none;
        overflow: visible;
      }
      .channel-layout { grid-template-columns: 1fr; }
      .channel-sidebar {
        position: relative;
        top: auto;
        max-height: none;
        overflow: visible;
      }
      .span4, .span5, .span6, .span7, .span8, .span12 { grid-column: span 12; }
      .oc-summary { grid-template-columns: 1fr 1fr; }
      .settings-command-head, .settings-metrics, .settings-route, .mapping-head { grid-template-columns: 1fr; }
      .filterbar.compact { justify-content: flex-start; }
      .settings-command h3 { font-size: clamp(26px, 11vw, 44px); }
      .settings-stamp { white-space: normal; }
      .panel { padding: 20px; }
    }
  </style>
</head>
<body>
<header>
  <div>
    <h1>MMS 配置中心</h1>
    <p class="lead">不是展示页：这里可以配置通道、拉取模型、隐藏/补充模型、标记能力、测试模型、设置 fallback。保存前先预览；stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
  </div>
  <div class="statusbar" id="statusbar"><span class="pill warn">加载中</span></div>
</header>
<div class="shell">
  <aside class="side" id="nav"></aside>
  <main class="content">
    <section class="panel" data-section="source">
      <h2>真源状态</h2>
      <p>只读汇总当前 config root、registry DB、legacy import 冲突和 latest-approved bundle 校验状态。</p>
      <div class="grid" id="sourceStatus"></div>
    </section>


    <!-- 通道配置 -->
    <section class="panel" data-section="channel">
      <h2>通道配置</h2>
      <p>先建通道：内部 ID、显示名、OpenAI/Anthropic URL、API Key、协议和模型列表接口。Key 只会通过 POST 发送，不会回显。</p>
      <div class="channel-layout">
        <div class="channel-sidebar">
          <div class="provider-list" id="providerList"></div>
          <div class="btns">
            <button id="addProvider" class="secondary">+ 添加通道</button>
            <button id="duplicateProvider" class="ghost">复制当前</button>
          </div>
        </div>
        <div class="channel-main">
          <div class="provider-tabs">
            <button class="tab-btn active" data-tab="config" onclick="switchProviderTab('config')">通道配置</button>
            <button class="tab-btn" data-tab="models" onclick="switchProviderTab('models')">模型配置</button>
          </div>
          <div class="tab-panel active" data-tab-panel="config">
            <div class="card provider-editor" id="providerForm"></div>
          </div>
          <div class="tab-panel" data-tab-panel="models">
            <div class="model-section">
              <p class="muted">这是当前通道的模型清单，不是全局模型池。手动补充会写入当前通道的 extra_models；取消勾选「显示」会写入当前通道的 hidden_models。</p>
              <div class="card">
                <div class="btns">
                  <button id="fetchModels">拉取当前通道模型</button>
                  <button id="testList" class="secondary">测试 /models</button>
                  <label class="check"><input id="autoStaleCleanupOnFetch" type="checkbox"><span>拉取后自动标记缺失旧 route 为待清理（本页临时）</span></label>
                  <input id="modelSearch" placeholder="搜索模型" style="max-width:260px">
                </div>
                <label style="margin-top:14px">手动补充当前通道模型（extra_models，逗号或换行分隔）</label>
                <textarea id="manualModels" placeholder="例如：gpt-5.5, qwen3.6-plus, K2.6"></textarea>
                <div class="btns">
                  <button id="addManualModels" class="secondary">添加到补充模型库</button>
                  <button id="clearHidden" class="ghost">取消当前通道全部隐藏</button>
                  <button id="clearAllStaleHidden" class="ghost">移除全部通道未匹配隐藏规则</button>
                </div>
              </div>
              <div id="modelChips" class="card"></div>
              <div class="card" id="staleHiddenBox"></div>
              <div class="table-wrap"><table id="modelTable"></table></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 模型测试 -->
    <section class="panel" data-section="test">
      <h2>模型测试</h2>
      <p>支持模型列表 smoke、指定模型 ping/pong 和简单 chat。结果会显示脱敏 request_url/request_path evidence。</p>
      <div class="grid">
        <div class="card span5">
          <label>测试通道</label><select id="testProvider"></select>
          <label>测试模型</label><select id="testModel"></select>
          <label>协议</label>
          <select id="testProtocol">
            <option value="auto">auto</option>
            <option value="anthropic_messages">anthropic_messages</option>
            <option value="openai_chat_completions">openai_chat_completions</option>
          </select>
          <label>Prompt</label>
          <textarea id="testPrompt">只回复 pong</textarea>
          <div class="btns">
            <button id="testModelBtn">Ping 模型</button>
            <button id="chatTestBtn" class="secondary">Simple chat</button>
          </div>
        </div>
        <div class="card span7">
          <div class="result" id="testResult">暂无测试结果</div>
        </div>
      </div>
    </section>

    <!-- Fallback -->
    <section class="panel" data-section="fallback">
      <h2>Fallback 设置</h2>
      <p>stable legacy 保存写入 config.toml 的 [rescue] / [vision_sidecar]；preview root 保存为 DB candidate 并随 latest-approved bundle 发布。</p>
      <div class="grid">
        <div class="card span6">
          <h3>Rescue fallback</h3>
          <label>fallback_model</label>
          <input id="rescueModel" placeholder="deepseek-v4-flash">
          <label>fallback_cli</label>
          <select id="rescueCli">
            <option value="">不指定</option>
            <option>codex</option>
            <option>claude</option>
            <option>opencode</option>
            <option>agy</option>
          </select>
          <div class="check" style="margin-top:10px">
            <input id="rescueHot" type="checkbox"><span>开启 hot_fallback_enabled</span>
          </div>
        </div>
        <div class="card span6">
          <h3>Vision sidecar</h3>
          <div class="check">
            <input id="visionEnabled" type="checkbox"><span>启用 vision sidecar</span>
          </div>
          <label>provider_id</label>
          <select id="visionProvider"></select>
          <label>model</label>
          <select id="visionModel"></select>
          <p class="muted">模型下拉优先显示当前通道中标记为 vision/multimodal 的模型；当前值不在列表时会保留为「当前配置值」。</p>
          <label>候选列表</label>
          <div id="visionCandidates" class="grid"></div>
          <div class="btns">
            <button id="addVisionCandidate" class="secondary">+ 添加 vision 候选</button>
          </div>
        </div>
      </div>
    </section>

    <!-- 运行默认值 -->
    <section class="panel" data-section="runtime">
      <h2>运行默认值</h2>
      <p>Preferred CLI 会写入 presets.coding.cli；OpenCode profile 和 agent roster 会写入 [opencode]，launcher 会生成 session-local opencode.json；不会写全局 OpenCode 配置。</p>
      <div class="grid">
        <div class="card span5">
          <label>preferred CLI</label>
          <select id="preferredCli">
            <option>opencode</option>
            <option>codex</option>
            <option>claude</option>
            <option>agy</option>
          </select>
          <label>coding preset model（可选）</label>
          <input id="codingModel" placeholder="gpt-5.5">
        </div>
        <div class="card span7">
          <label>OpenCode default profile</label>
          <select id="opencodeProfile">
            <option>agent</option>
            <option>omo</option>
            <option>raw</option>
          </select>
          <p class="muted">推荐：5.5 总控/终审，5.4 长跑 executor，国产模型用于 explore / bug-hunt / vision。逐 agent 固定模型放在 Advanced，不作为默认必填项。</p>
        </div>
        <div class="card span12">
          <h3>OpenCode Agent Roster</h3>
          <p class="muted">默认使用 Lite Pro 自动路线；这里管理哪些 agent 进入 session-local opencode.json。Order 是 priority/fallback order, not round-robin。</p>
          <div class="oc-summary" id="opencodeOverrideSummary"></div>
          <div class="oc-order-note">
            Lean 默认只开关键链路；Balanced 适合日常；Deep 再启用第二意见。国产模型适合 explore / bughunt / vision，不默认做最终裁决。
          </div>
          <details class="oc-advanced" id="opencodeAdvanced">
            <summary>Advanced: OpenCode per-agent roster</summary>
            <div class="filterbar" id="opencodeAgentFilters"></div>
            <div class="table-wrap"><table id="opencodeAgents"></table></div>
          </details>
        </div>
      </div>
    </section>

    <!-- Settings parity -->
    <section class="panel" data-section="settings">
      <h2>Settings / Channel 能力</h2>
      <p>这里把 TUI settings/channel 的剩余能力拉到 WebUI：安全项直接展示或调用 read-only report；会写真实账号、Snapshot Guard accept、login/delete 的动作先保持 human-gated，不在页面里静默执行。</p>
      <div id="settingsCommand" class="settings-command"></div>
      <div class="grid">
        <div class="card span4">
          <h3>界面语言</h3>
          <p class="muted">对应 TUI Settings → 界面语言。这里先进入 WebUI 草稿；真正写入仍走保存 / 审计。</p>
          <label>ui.language</label>
          <select id="uiLanguage">
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
          <div class="btns"><button id="saveUiLanguage" class="ghost">暂存语言修改</button></div>
        </div>
        <div class="card span8">
          <h3>剩余 TUI 降级边界</h3>
          <p class="muted">Provider 删除现在有 typed confirm 草稿；语言可在 WebUI 暂存。仍未 native 的是 rescue handover / demo packet 等本地 artifact 写入，保持 gate/missing。</p>
          <div id="settingsGapSummary" class="chips"></div>
        </div>
        <div class="card span12">
          <h3>账号 / OAuth 通道</h3>
          <p class="muted">支持非 Claude account 的 name/enabled/priority/default 草稿预览；Claude account、login/remove、home_dir/proxy/no_proxy 仍是 human-gated，不会静默写入。</p>
          <div class="table-wrap"><table id="accountTable"></table></div>
        </div>
        <div class="card span12">
          <h3>功能覆盖矩阵</h3>
          <div class="table-wrap"><table id="settingsCoverage"></table></div>
        </div>
        <div class="card span12 mapping-card">
          <div class="mapping-head">
            <div>
              <h3>TUI ↔ WebUI 对照表</h3>
              <p class="muted">逐项对应 TUI settings/channel action：native 直接在 WebUI 操作，report 可点击取 JSON，human gate/missing 明确保留，不伪装完成。</p>
            </div>
            <div id="mappingFilters" class="filterbar compact"></div>
          </div>
          <div class="table-wrap"><table id="tuiMappingTable"></table></div>
        </div>
        <div class="card span5">
          <h3>维护动作</h3>
          <p class="muted">按钮只返回 JSON report；真正写入仍走保存页的 diff + confirm，或后续单独 HumanGate flow。</p>
          <div id="maintenanceActions" class="btns"></div>
        </div>
        <div class="card span7">
          <h3>Report</h3>
          <div class="result" id="settingsReport">选择一个维护动作查看结果</div>
        </div>
      </div>
    </section>

    <!-- 保存 / 审计 -->
    <section class="panel" data-section="save">
      <h2>保存 / 审计</h2>
      <p id="saveModeLead">保存前先生成 diff。preview root 走 DB candidate + latest-approved publish；stable legacy 使用 audited writer：lock、backup、audit log。API Key 不会出现在 diff 或响应里。</p>
      <div class="grid">
        <div class="card span5">
          <p class="muted" id="saveModeHint"></p>
          <div class="btns">
            <button id="previewPlan">生成保存预览</button>
            <button id="applyV2Preview" class="secondary">写入预览 DB + 发布</button>
            <button id="saveBtn" class="danger legacy-save-action">确认保存</button>
          </div>
          <details class="oc-advanced" id="advancedPlanTools" style="margin-top:14px">
            <summary>Advanced / Recovery：plan JSON 与 CLI fallback</summary>
            <p class="muted">WebUI plan JSON = “生成保存预览”的 redacted review artifact；下载 JSON 不含明文 key。CLI apply 是无 WebUI 时的 fallback，不是日常主流程。</p>
            <div class="btns">
              <button id="downloadPlanJson" class="ghost">下载 plan JSON</button>
              <button id="copyApplyCommand" class="ghost">复制 CLI apply 命令</button>
            </div>
          </details>
          <div class="check" style="margin-top:12px">
            <input id="confirmSave" type="checkbox"><span>我已检查摘要、风险和 diff，同意执行所选写入</span>
          </div>
          <label id="confirmPhraseLabel" style="margin-top:12px">输入确认文字</label>
          <input id="confirmPhrase" placeholder="保存配置 或 写入预览DB">
          <label>保存原因 / audit reason</label>
          <input id="saveReason" value="setup-web-ui:interactive-save">
          <p class="muted" id="saveCompatibilityNote">stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
        </div>
        <div class="card span7">
          <div class="result" id="saveResult">尚未生成预览</div>
        </div>
        <div class="card span12">
          <h3>保存摘要</h3>
          <div id="reviewSummary">
            <p class="muted">点击“生成保存预览”后，这里会先用人话列出 URL、隐藏模型、fallback、OpenCode 和风险变化。</p>
          </div>
        </div>
        <div class="span12">
          <h3 style="margin-bottom:8px">Raw diff / 审计详情</h3>
          <div class="diff" id="diffBox">点击“生成保存预览”</div>
        </div>
      </div>
    </section>

    <!-- 本地参考 -->
    <section class="panel" data-section="refs">
      <h2>本地参考</h2>
      <p>这些是当前配置页面使用的本地参考入口；联网查最新厂商文档应作为后续显式动作，不在保存时自动外连。</p>
      <div class="grid" id="refsGrid"></div>
    </section>
  </main>
</div>
<div class="toast" id="toast"></div>
<script>
const sections=[
  ['source','真源状态','DB / legacy / bundle'],
  ['channel','通道配置','URL / Key / 协议 / 模型'],
  ['test','模型测试','ping / chat smoke'],
  ['fallback','Fallback','rescue / vision'],
  ['runtime','运行默认值','preferred CLI / OpenCode'],
  ['settings','能力整合','accounts / reports / parity'],
  ['save','保存审计','diff / backup / audit'],
  ['refs','本地参考','配置契约 / docs']
];
let state=null; let activeProvider=0; let activeProviderTab='config'; let lastPlan=null; let opencodeAgentFilter="all"; let opencodeOnlyOverridden=false; let editingExtraModels=false; let settingsMappingFilter='all'; let touchedProviders=new Set(); let staleCleanupProviders=new Set();
const $=id=>document.getElementById(id);
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await res.json();if(!res.ok){data.ok=false;data.http_status=res.status;data.error=data.error||res.statusText}return data}
function current(){return state.providers[activeProvider]}
function touchProvider(id){if(id)touchedProviders.add(id)}
function setSection(id){document.querySelectorAll('[data-section]').forEach(el=>el.classList.toggle('hide',el.dataset.section!==id));document.querySelectorAll('.navbtn').forEach(el=>el.classList.toggle('active',el.dataset.id===id))}
function switchProviderTab(tab){activeProviderTab=tab;document.querySelectorAll('.provider-tabs .tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tabPanel===tab))}
function renderNav(){ $('nav').innerHTML=sections.map(([id,title,sub])=>`<button class="navbtn" data-id="${id}">${title}<small>${sub}</small></button>`).join(''); document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>setSection(b.dataset.id)); setSection('source') }
function renderStatus(){const providers=state.providers||[];const root=(state.model_source_status||{}).root||{};$('statusbar').innerHTML=`<span class="pill ok">${state.mode}</span><span class="pill">${escapeHtml(root.mode||'stable')}</span><span class="pill">通道 ${providers.length}</span><span class="pill">config: ${escapeHtml(state.paths.config||'-')}</span><span class="pill">policy: ${state.policy_summary.model_count} models</span>`}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function renderSaveControls(){const root=(state.model_source_status||{}).root||{};const preview=root.mode==='preview';const hasPlan=!!lastPlan;const modeName=preview?'MMF preview / DB truth':'MMS stable / legacy compatibility';if($('saveModeHint')){$('saveModeHint').innerHTML=preview?'当前是 <strong>mmf + ~/.config/mms-next</strong>：日常只需要“生成保存预览” → “写入预览 DB + 发布”。':'当前是 <strong>mms stable</strong>：使用 legacy audited save，仍会 backup + audit。'}if($('saveModeLead')){$('saveModeLead').textContent=preview?'保存前先生成 diff。写入只落到当前 preview root 的 DB candidate，并发布 latest-approved bundle；API Key 不会出现在 diff 或响应里。':'保存前先生成 diff。stable legacy 使用 audited writer：lock、backup、audit log；API Key 不会出现在 diff 或响应里。'}if($('confirmPhraseLabel')){$('confirmPhraseLabel').textContent=preview?'输入确认文字：写入预览DB':'输入确认文字：保存配置'}if($('confirmPhrase')){$('confirmPhrase').placeholder=preview?'写入预览DB':'保存配置'}if($('saveCompatibilityNote')){$('saveCompatibilityNote').textContent=preview?'旧版“确认保存”在 mmf 中已隐藏；下载 JSON / CLI apply 只在 Advanced / Recovery 里作为 fallback。':'stable legacy 保存写入 config.toml / credentials.sh / model-policy，并保留 backup + audit；preview DB 发布请用 mmf。'}document.querySelectorAll('.legacy-save-action').forEach(el=>el.classList.toggle('hide',preview));if($('saveBtn')){$('saveBtn').disabled=preview;$('saveBtn').title=preview?'MMF preview 已隐藏 legacy save，请使用写入预览 DB + 发布':''}if($('applyV2Preview')){$('applyV2Preview').classList.toggle('hide',!preview);$('applyV2Preview').disabled=!preview;$('applyV2Preview').title=preview?modeName:'Stable root 不能写 preview DB，请用 mmf preview root'}if($('advancedPlanTools')){$('advancedPlanTools').open=false}if($('downloadPlanJson')){$('downloadPlanJson').disabled=!hasPlan;$('downloadPlanJson').title=hasPlan?'下载 redacted plan JSON；不含明文 API Key':'请先生成保存预览'}if($('copyApplyCommand')){$('copyApplyCommand').disabled=!hasPlan;$('copyApplyCommand').title=hasPlan?'复制 mmf config apply-plan 命令':'请先生成保存预览'}}
function renderSourceStatus(){
  const box=$('sourceStatus');if(!box)return;
  const status=state.model_source_status||{};
  const consumer=state.consumer_bundle_status||{};
  const promotion=state.config_v2_promotion_plan||{};
  const readiness=state.config_v2_release_readiness||{};
  const root=status.root||consumer.root||{};
  const db=status.registry_db||{};
  const legacy=status.legacy_import||{};
  const candidates=legacy.candidates||db.legacy_import_candidates||{};
  const bundle=status.generated_bundle||{};
  const revisions=consumer.component_revisions||{};
  const rules=consumer.consumer_rules||[];
  const consumerFiles=consumer.files||{};
  const counts=db.counts||{};
  const safety=promotion.promotion_safety||{};
  const backup=promotion.stable_backup_plan||{};
  const compare=promotion.bundle_comparison||{};
  const comparePreview=compare.preview||{};
  const compareStable=compare.stable||{};
  const readinessNext=readiness.next_action||{};
  const readinessBlocked=Array.isArray(readiness.blocked_requirements)?readiness.blocked_requirements:[];
  const readinessReqs=Array.isArray(readiness.requirements)?readiness.requirements:[];
  const readinessOk=readiness.ready_for_human_gate?'ok':'warn';
  const okBundle=bundle.verified?'ok':'warn';
  const okConsumer=consumer.verified?'ok':'warn';
  const okPromotion=promotion.ready_for_human_review?'ok':'warn';
  const ready=bundle.runtime_ready===true?'ready':bundle.runtime_ready===false?'not ready':'unknown';
  const bundleCommand=(root.command||state.command||'mms')==='mmf'?'mmf config bundle --json':'mms config bundle --json';
  box.innerHTML=`<div class="card span6"><h3>Root</h3><p class="mono">${escapeHtml(root.config_root||status.config_root||consumer.config_root||'-')}</p><p class="muted">${escapeHtml(status.headline||'-')}</p><span class="tag ${status.ready?'':'off'}">${escapeHtml(status.status||'unknown')}</span><span class="tag">${escapeHtml(root.command||state.command||'-')}</span><span class="tag">${escapeHtml(root.mode||'-')}</span><span class="tag">${escapeHtml(root.root_source||'-')}</span></div><div class="card span6"><h3>Registry DB</h3><p class="mono">${escapeHtml(db.path||'-')}</p><span class="tag ${db.status==='ok'?'':'off'}">${escapeHtml(db.status||'missing')}</span><span class="tag">sources ${counts.source_snapshot||0}</span><span class="tag">facts ${counts.model_fact||0}</span><span class="tag">routes ${counts.provider_route||0}</span></div><div class="card span6"><h3>Legacy Import</h3><p class="muted">${escapeHtml(legacy.next_action||'-')}</p><span class="tag">providers ${legacy.provider_count||0}</span><span class="tag ${legacy.conflict_count?'off':''}">conflicts ${legacy.conflict_count||0}</span><span class="tag ${candidates.status==='imported'?'':'off'}">candidates ${escapeHtml(candidates.status||'not_imported')}</span><span class="tag">candidate routes ${candidates.provider_route_count||0}</span></div><div class="card span6"><h3>Latest Approved Bundle</h3><p class="mono">${escapeHtml(bundle.manifest_path||'-')}</p><span class="tag ${okBundle==='ok'?'':'off'}">${escapeHtml(bundle.status||'missing')}</span><span class="tag">verified ${bundle.verified?'yes':'no'}</span><span class="tag ${bundle.runtime_ready===true?'':'off'}">runtime ${ready}</span><span class="tag">missing keys ${bundle.router_missing_api_key_count||0}</span><span class="tag">files ${bundle.file_count||0}</span></div><div class="card span12"><h3>Consumer Bundle</h3><p class="mono">${escapeHtml(consumer.consumer_entrypoint||bundle.manifest_path||'-')}</p><p class="muted">${escapeHtml((rules.length?rules.join(' · '):'下游只读 latest-approved manifest；不读 SQLite；不混合不同 revision。'))}</p><span class="tag ${okConsumer==='ok'?'':'off'}">${escapeHtml(consumer.status||'missing')}</span><span class="tag">verified ${consumer.verified?'yes':'no'}</span><span class="tag">bundle ${escapeHtml(revisions.bundle||'-')}</span><span class="tag">route ${escapeHtml(revisions.route||'-')}</span><span class="tag">policy ${escapeHtml(revisions.policy||'-')}</span><span class="tag">profile ${escapeHtml(revisions.profile||'-')}</span><span class="tag">files ${Object.keys(consumerFiles).length}</span><p class="muted">CLI: <span class="mono">${escapeHtml(bundleCommand)}</span></p></div><div class="card span12"><h3>Promotion Plan / Human Gate</h3><p class="muted">stable backup + bundle comparison 是只读审查；apply 仍停在 human gate。</p><span class="tag ${okPromotion==='ok'?'':'off'}">${escapeHtml(promotion.status||'not_ready')}</span><span class="tag">review ${promotion.ready_for_human_review?'ready':'not ready'}</span><span class="tag">apply ${promotion.apply_enabled?'enabled':'disabled'}</span><span class="tag">stable ${escapeHtml(safety.stable_write_policy||'human_only')}</span><span class="tag">backup ${backup.requires_backup_before_apply?'required':'unknown'}</span><span class="tag">would backup ${backup.would_create_backup?'yes':'no'}</span><span class="tag">bundle comparison ${escapeHtml(compare.comparison_status||'-')}</span><p class="muted">preview ${escapeHtml(comparePreview.bundle_revision||comparePreview.status||'-')} → stable ${escapeHtml(compareStable.bundle_revision||compareStable.status||'-')}</p></div><div class="card span12"><h3>4.0 Release Readiness</h3><p class="muted">只读 audit：证明自动检查已到 stable promotion human gate；release_complete 仍为 false。</p><span class="tag ${readinessOk==='ok'?'':'off'}">${escapeHtml(readiness.result||'NOT_READY')}</span><span class="tag">status ${escapeHtml(readiness.status||'not_ready')}</span><span class="tag">release complete ${readiness.release_complete?'yes':'no'}</span><span class="tag">human gate ${readiness.ready_for_human_gate?'ready':'not ready'}</span><span class="tag">blocked ${readinessBlocked.length}</span><span class="tag">requirements ${readinessReqs.filter(r=>r&&r.ok).length}/${readinessReqs.length}</span><span class="tag">blocker ${escapeHtml(readiness.completion_blocker||'-')}</span><p class="muted">blocked requirements: ${escapeHtml(readinessBlocked.length?readinessBlocked.join(', '):'-')}</p><p class="muted">next: <span class="mono">${escapeHtml(readinessNext.command||readinessNext.label||'-')}</span></p></div><div class="card span12"><h3>Raw Status</h3><div class="result">${escapeHtml(JSON.stringify({model_source_status:status,consumer_bundle_status:consumer,config_v2_promotion_plan:promotion,config_v2_release_readiness:readiness},null,2))}</div></div>`
}
function providerEntries(){return (state.providers||[]).map((p,i)=>({p,i})).sort((a,b)=>{if(!!a.p.enabled!==!!b.p.enabled)return a.p.enabled?-1:1;return a.i-b.i})}
function renderProviderList(){const list=$('providerList');list.innerHTML=providerEntries().map(({p,i})=>{const keyTag=p.api_key?'<span class="tag">pending key</span>':(p.has_api_key?'<span class="tag">key set</span>':'<span class="tag off">no key</span>');const usage=p.usage||{};return `<div class="provider-item ${i===activeProvider?'active':''}" data-i="${i}"><strong>${escapeHtml(p.name||p.id)}</strong><span class="muted mono">${escapeHtml(p.id)}</span><br>${p.enabled?'<span class="tag">enabled</span>':'<span class="tag off">disabled</span>'}${keyTag}<span class="tag">${p.models?.length||0} models</span><span class="tag">launches ${usage.launches||0}</span></div>`}).join('');document.querySelectorAll('.provider-item').forEach(el=>el.onclick=()=>{activeProvider=Number(el.dataset.i);renderAll()})}
function renderProviders(){renderProviderList();renderProviderForm();renderTestSelectors();renderModelTable();}
function checks(name,values,allowed){values=values||[];return `<div class="checks">${allowed.map(v=>`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${values.includes(v)?'checked':''}><span>${v}</span></label>`).join('')}</div>`}
function checkedValues(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value)}
function renderProviderForm(){const p=current(); if(!p){$('providerForm').innerHTML='<p>暂无通道</p>';return} const pendingKey=!!p.api_key;const keyPlaceholder=pendingKey?'已输入新 key，保存前会保留（不回显）':(p.has_api_key?'已保存；输入新 key 才会覆盖':'sk-...');$('providerForm').innerHTML=`<div class="grid"><div class="span6"><label>内部 ID</label><input id="pId" value="${escapeHtml(p.id)}"></div><div class="span6"><label>显示名</label><input id="pName" value="${escapeHtml(p.name)}"></div><div class="span4"><label>状态</label><select id="pEnabled"><option value="true" ${p.enabled?'selected':''}>启用</option><option value="false" ${!p.enabled?'selected':''}>禁用</option></select></div><div class="span4"><label>role</label><select id="pRole">${['primary','auto','fallback'].map(v=>`<option ${p.role===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="span4"><label>priority</label><input id="pPriority" type="number" value="${escapeHtml(p.priority||100)}"></div><div class="span6"><label>OpenAI base URL</label><input id="pOpenAI" value="${escapeHtml(p.openai_base_url||'')}" placeholder="https://.../v1"></div><div class="span6"><label>Anthropic base URL</label><input id="pAnthropic" value="${escapeHtml(p.anthropic_base_url||'')}" placeholder="https://.../v1 或 /anthropic"></div><div class="span6"><label>API Key（留空不更新）</label><input id="pKey" type="password" placeholder="${escapeHtml(keyPlaceholder)}"></div><div class="span6"><label>models_endpoint</label><input id="pModelsEndpoint" value="${escapeHtml(p.models_endpoint||'/models')}" placeholder="/models 或 manual"></div><div class="span12"><label>protocols</label>${checks('pProtocols',p.protocols,['anthropic_messages','openai_chat_completions'])}</div><div class="span12"><label>supported CLIs</label>${checks('pClis',p.supported_clis,['claude','codex','opencode','agy'])}</div><div class="span12 check"><input id="pUpdateCreds" type="checkbox" ${p.update_credentials?'checked':''}><span>保存时更新凭据（stable 写 credentials.sh；preview 写 secret backend；需要填写 API Key）</span></div><div class="span12 check"><input id="pDefault" type="checkbox" ${state.provider_default===p.id?'checked':''}><span>设为默认 provider</span></div><div class="span12 delete-zone"><label>删除通道 typed confirm</label><input id="pDeleteConfirm" placeholder="输入 ${escapeHtml(p.id)} 后从草稿移除"><p class="muted">只从 WebUI 草稿移除；真正写入仍需要保存预览和确认。</p><div class="btns"><button id="deleteProvider" class="danger">从草稿移除通道</button></div></div></div><div class="btns"><button id="saveProviderForm">保存通道修改</button></div>`;bindProviderForm()}
function bindProviderForm(){['pId','pName','pEnabled','pRole','pPriority','pOpenAI','pAnthropic','pModelsEndpoint'].forEach(id=>$(id).oninput=syncProvider);const keyEl=$('pKey');keyEl.oninput=()=>{keyEl.dataset.touched='1';syncProvider()};$('pUpdateCreds').onchange=syncProvider;$('pDefault').onchange=()=>{syncProvider(); if($('pDefault').checked) state.provider_default=current().id; renderProviders();};const del=$('deleteProvider');if(del)del.onclick=deleteCurrentProviderDraft;document.querySelectorAll('input[name="pProtocols"],input[name="pClis"]').forEach(x=>x.onchange=syncProvider);const save=$('saveProviderForm');if(save)save.onclick=()=>{syncProvider();setSection('save');toast('通道修改已暂存，生成保存预览后再写入')}}
function deleteCurrentProviderDraft(){const p=current();if(!p)return;const typed=($('pDeleteConfirm')?.value||'').trim();if(typed!==p.id){toast('输入当前 provider ID 后才能从草稿移除');return}if((state.providers||[]).length<=1){toast('至少保留一个 provider；删除最后一个通道请走 CLI/manual gate');return}const removed=p.id;state.providers.splice(activeProvider,1);touchedProviders.add(removed);if(state.provider_default===removed)state.provider_default=(state.providers[0]||{}).id||'';activeProvider=Math.max(0,Math.min(activeProvider,state.providers.length-1));lastPlan=null;renderAll();setSection('save');toast(`${removed} 已从 WebUI 草稿移除，生成保存预览后再写入`)}
function syncProvider(){const p=current(); if(!p)return; const old=p.id;touchProvider(old);const keyEl=$('pKey');const updateEl=$('pUpdateCreds');p.id=$('pId').value.trim()||p.id;if(p.id!==old){touchedProviders.delete(old);touchProvider(p.id)}p.name=$('pName').value.trim()||p.id;p.enabled=$('pEnabled').value==='true';p.role=$('pRole').value;p.priority=Number($('pPriority').value||100);p.openai_base_url=$('pOpenAI').value.trim();p.anthropic_base_url=$('pAnthropic').value.trim();p.models_endpoint=$('pModelsEndpoint').value.trim()||'/models';p.protocols=checkedValues('pProtocols');p.supported_clis=checkedValues('pClis');const keyText=keyEl?keyEl.value.trim():'';const keyTouched=keyEl?.dataset?.touched==='1';if(keyText){p.api_key=keyText;p.pending_api_key=true;p.has_api_key=true;if(updateEl)updateEl.checked=true}else if(keyTouched){p.api_key='';p.pending_api_key=false}p.update_credentials=!!(updateEl&&updateEl.checked);if(state.provider_default===old)state.provider_default=p.id;renderProviderList();renderTestSelectors();}
function derivedAliases(base,p){const ids=(base||[]).map(x=>String(x||''));const tails=ids.map(id=>id.toLowerCase().split('/').pop());const aliases=[];if(tails.some(id=>id.startsWith('claude-sonnet-4-')||id.startsWith('claude-sonnet-4.')))aliases.push('claude-sonnet-4-6');if(tails.some(id=>id.startsWith('claude-opus-4-')||id.startsWith('claude-opus-4.')))aliases.push('claude-opus-4-6');const ident=String([p?.id,p?.name,p?.label,p?.provider_profile].filter(Boolean).join(' ')).toLowerCase();const anthropic=String(p?.anthropic_base_url||p?.default_anthropic_base_url||'').toLowerCase();if((anthropic.includes('xiaomimimo.com')||ident.includes('mimo')||ident.includes('xiaomi'))&&!ident.includes('openrouter')){['mimo-v2.5-pro','mimo-v2.5'].forEach(id=>{if(ids.includes(id)&&!ids.includes(`${id}[1m]`))aliases.push(`${id}[1m]`)})}return aliases}
function providerModels(p){p=p||{};const map=new Map();const hiddenLower=new Set((p.hidden_models||[]).map(x=>String(x||'').toLowerCase()));const baseRows=(p.models||[]).filter(r=>r&&r.id&&r.source!=='hidden');baseRows.forEach(r=>map.set(r.id,{...r,visible:r.visible!==false&&!hiddenLower.has(String(r.id).toLowerCase()),capabilities:{...(r.capabilities||{})}}));if(!baseRows.length){(p.fallback_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'fallback',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})})}const baseIds=[...map.keys()];derivedAliases(baseIds.filter(id=>!hiddenLower.has(String(id).toLowerCase())),p).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'derived_alias',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.extra_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'extra',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.hidden_models||[]).forEach(id=>{[...map.keys()].forEach(key=>{if(String(key).toLowerCase()===String(id).toLowerCase())map.get(key).visible=false})});return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id))}
function defaultCaps(id){const l=String(id||'').toLowerCase();return {text:true,vision:['mimo-v2.5','mimo-v2-omni','k2.6','k2.6-code-preview','kimi-k2.5','qwen3.6-plus','qwen3.6-flash','qwen3.5-plus'].includes(l)||l.startsWith('claude-')||l.startsWith('gemini-'),tool_use:/^(claude|gpt|o|qwen|kimi|glm|minimax|gemini)/.test(l),reasoning:/gpt-5|qwen3|kimi-k2|glm-5|deepseek|claude/.test(l),long_context:/1m|long|qwen3|kimi-k2|gpt-5|claude/.test(l),cache_sensitive:/^(qwen|kimi|k2\.|glm|deepseek|minimax|mimo)/.test(l)}}
function providerCurrentIds(p){return new Set(providerModels(p).map(r=>r.id))}
function staleHiddenModels(p){const ids=providerCurrentIds(p);return [...new Set([...(p.stale_hidden_models||[]),...(p.hidden_models||[]).filter(id=>!ids.has(id))])]}
function cleanupStaleHidden(p){const stale=staleHiddenModels(p);const doomed=new Set(stale);p.hidden_models=(p.hidden_models||[]).filter(x=>!doomed.has(x));p.stale_hidden_models=[];return stale.length}
function cleanupAllStaleHidden(){let total=0;(state.providers||[]).forEach(p=>{total+=cleanupStaleHidden(p)});renderProviders();toast(total?`已移除 ${total} 条未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}
function staleRouteModels(p){const approved=(p.approved_route_models&&p.approved_route_models.length?p.approved_route_models:(p.fallback_models||[]));const remote=new Set((p.models||[]).filter(r=>r&&r.id).map(r=>String(r.id)));const extras=new Set((p.extra_models||[]).map(x=>String(x)));return [...new Set(approved.filter(id=>id&&!remote.has(String(id))&&!extras.has(String(id))))]}
function renderStaleRouteBox(p){const box=$('staleRouteBox');if(!box)return;const stale=staleRouteModels(p);if(!stale.length){box.innerHTML='<strong>缺失旧 route</strong><p class="muted">当前没有“本地已批准但本次拉取未返回”的旧 route。</p>';return}const armed=staleCleanupProviders.has(p.id);box.innerHTML=`<strong>缺失旧 route（默认保留）</strong><p class="muted">这些模型在本地已批准 routes 里，但不在当前拉取到的模型列表里。默认不会删除；如果勾选“拉取后自动标记”，本页后续拉取会自动标记清理。避免上游 /models 抖动或 New API 临时关闭导致下游模型被清空。</p><div class="chips">${stale.slice(0,24).map(m=>`<span class="chip">${escapeHtml(m)}</span>`).join('')}${stale.length>24?`<span class="chip">+${stale.length-24}</span>`:''}</div><div class="btns"><button id="armStaleRouteCleanup" class="ghost">${armed?'已标记：保存时清理这些旧 route':'显式标记保存时清理这些旧 route'}</button></div>`;$('armStaleRouteCleanup').onclick=()=>{staleCleanupProviders.add(p.id);touchProvider(p.id);renderStaleRouteBox(p);toast(`已标记 ${p.id}：下次写入预览 DB 会清理 ${stale.length} 条缺失旧 route`)}}
function visibleModelsForProvider(providerId,{visionFirst=false,includeHidden=false,enabledOnly=false}={}){let rows=[];(state.providers||[]).forEach(p=>{if(providerId&&p.id!==providerId)return;if(enabledOnly&&p.enabled===false)return;providerModels(p).forEach(r=>{if(!includeHidden&&r.visible===false)return;rows.push({...r,provider_id:p.id,provider_name:p.name||p.id,capabilities:{...(r.capabilities||defaultCaps(r.id))}})})});const seen=new Set();rows=rows.filter(r=>{const key=(providerId?'':r.provider_id+'::')+r.id;if(seen.has(key))return false;seen.add(key);return true});rows.sort((a,b)=>{const av=!!(a.capabilities||{}).vision,bv=!!(b.capabilities||{}).vision;if(visionFirst&&av!==bv)return av?-1:1;return (a.provider_id+' '+a.id).localeCompare(b.provider_id+' '+b.id)});return rows}
function providerOptions(selected,{blankLabel='请选择通道',auto=false,enabledOnly=false}={}){const opts=[];const providers=providerEntries().filter(({p})=>!enabledOnly||p.enabled||p.id===selected);if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动选择 provider</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>${escapeHtml(blankLabel)}</option>`);opts.push(...providers.map(({p})=>{const disabled=p.enabled?'':' [disabled 当前配置值]';return `<option value="${escapeHtml(p.id)}" ${p.id===selected?'selected':''}>${escapeHtml(p.name||p.id)} / ${escapeHtml(p.id)}${disabled}</option>`}));if(selected&&!state.providers.some(p=>p.id===selected))opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function modelOptionValue(providerId,row){return providerId?row.id:`${row.provider_id}::${row.id}`}
function decodeModelSelection(value,currentProvider){const text=String(value||'');if(!text)return{provider_id:currentProvider||'',model:''};const marker='::';if(text.includes(marker)){const [provider_id,...rest]=text.split(marker);return{provider_id,model:rest.join(marker)}}return{provider_id:currentProvider||'',model:text}}
function modelOptions(providerId,selected,{visionFirst=false,auto=false,defaultModels=[],enabledOnly=false,selectedProvider=''}={}){const rows=visibleModelsForProvider(providerId,{visionFirst,enabledOnly});let opts=[];if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动路线${defaultModels.length?'：'+escapeHtml(defaultModels.join(' / ')):''}</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>请选择模型</option>`);let matched=false;opts.push(...rows.map(r=>{const value=modelOptionValue(providerId,r);const label=providerId?r.id:`${r.provider_id} / ${r.id}`;const tag=(r.capabilities||{}).vision?' [vision]':'';const isSelected=providerId?r.id===selected:((selectedProvider&&r.provider_id===selectedProvider&&r.id===selected)||(!selectedProvider&&r.id===selected));if(isSelected)matched=true;return `<option value="${escapeHtml(value)}" ${isSelected?'selected':''}>${escapeHtml(label)}${tag}</option>`}));if(selected&&!matched)opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function renderStaleHiddenBox(p){const stale=staleHiddenModels(p);const box=$('staleHiddenBox');if(!box)return;if(!stale.length){box.innerHTML='<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">当前没有“暂时匹配不到模型行”的隐藏规则。</p>';return}box.innerHTML=`<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">这些只是当前通道 hidden_models 里的隐藏规则，暂时没有匹配到当前模型行；不等于远端不存在，也不等于 route 待删除。移除后如果模型仍在远端或 approved routes 里，会重新显示出来。</p><div class="chips">${stale.map(m=>`<span class="chip">${escapeHtml(m)} <button data-stale-rm="${escapeHtml(m)}">移除记录</button></span>`).join('')}</div><div class="btns"><button id="clearStaleHidden" class="ghost">移除当前通道未匹配隐藏规则</button></div>`;document.querySelectorAll('[data-stale-rm]').forEach(b=>b.onclick=()=>{p.hidden_models=(p.hidden_models||[]).filter(x=>x!==b.dataset.staleRm);p.stale_hidden_models=(p.stale_hidden_models||[]).filter(x=>x!==b.dataset.staleRm);renderModelTable()});$('clearStaleHidden').onclick=()=>{const count=cleanupStaleHidden(p);renderModelTable();toast(count?`已移除 ${count} 条当前通道未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}}
function renderModelTable(){const p=current(); if(!p)return;const q=($('modelSearch')?.value||'').toLowerCase();const rows=providerModels(p).filter(r=>r.id.toLowerCase().includes(q));const extras=p.extra_models||[];$('modelChips').innerHTML=`<strong>当前通道补充模型库（extra_models）</strong><p class="muted">这些模型是手动补充到当前 provider 的可用模型，会参与当前通道路由；不是待删除列表，也不是全局模型池。</p><div class="chips">${extras.length?extras.map(m=>`<span class="chip">${escapeHtml(m)}${editingExtraModels?` <button data-rm-extra="${escapeHtml(m)}">从补充库移除</button>`:''}</span>`).join(''):'<span class="muted">当前通道暂无手动补充模型。</span>'}</div><div class="btns"><button id="toggleExtraEdit" class="ghost">${editingExtraModels?'完成编辑':'编辑补充模型库'}</button></div><div id="staleRouteBox"></div>`;$('toggleExtraEdit').onclick=()=>{editingExtraModels=!editingExtraModels;renderModelTable()};document.querySelectorAll('[data-rm-extra]').forEach(b=>b.onclick=()=>{p.extra_models=extras.filter(x=>x!==b.dataset.rmExtra);toast(`已从当前通道补充模型库移除 ${b.dataset.rmExtra}`);renderModelTable()});renderStaleRouteBox(p);renderStaleHiddenBox(p);$('modelTable').innerHTML=`<thead><tr><th>显示</th><th>模型</th><th>来源</th><th>收藏</th><th>text</th><th>vision</th><th>tool</th><th>reason</th><th>long</th><th>cache</th></tr></thead><tbody>${rows.map(r=>{const c=r.capabilities||{};return `<tr><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="visible" ${r.visible?'checked':''}></td><td class="mono">${escapeHtml(r.id)}</td><td><span class="tag ${r.visible?'':'off'}">${escapeHtml(r.source||'manual')}</span></td><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="favorite" ${r.favorite?'checked':''}></td>${['text','vision','tool_use','reasoning','long_context','cache_sensitive'].map(k=>`<td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-cap="${k}" ${c[k]?'checked':''}></td>`).join('')}</tr>`}).join('')}</tbody>`;document.querySelectorAll('#modelTable input').forEach(x=>x.onchange=onModelToggle);renderTestSelectors();renderFallback();renderRuntime()}
function onModelToggle(e){const p=current();const model=e.target.dataset.model;let row=providerModels(p).find(r=>r.id===model)||{id:model,source:'hidden',visible:!(p.hidden_models||[]).includes(model),favorite:false,capabilities:defaultCaps(model)};row.policy_touched=true;if(e.target.dataset.field==='visible'){row.visible=e.target.checked;p.hidden_models=e.target.checked?(p.hidden_models||[]).filter(x=>x!==model):[...(p.hidden_models||[]).filter(x=>x!==model),model]}else if(e.target.dataset.field==='favorite'){row.favorite=e.target.checked}else if(e.target.dataset.cap){row.capabilities=row.capabilities||{};row.capabilities[e.target.dataset.cap]=e.target.checked}p.model_capabilities=p.model_capabilities||{};p.model_capabilities[model]=row.capabilities;p.models=(p.models||[]).filter(r=>r.id!==model).concat(row);renderTestSelectors();renderFallback();renderRuntime()}
function renderTestSelectors(){const tp=$('testProvider');if(!tp)return;tp.innerHTML=providerEntries().map(({p,i})=>`<option value="${i}">${escapeHtml(p.name||p.id)}${p.enabled?'':' [disabled]'}</option>`).join('');tp.value=String(activeProvider);tp.onchange=()=>{activeProvider=Number(tp.value);renderAll()};const models=providerModels(current()||{});$('testModel').innerHTML=models.map(r=>`<option>${escapeHtml(r.id)}</option>`).join('')}
function syncFallback(){state.rescue=state.rescue||{};state.rescue.fallback_model=$('rescueModel').value.trim();state.rescue.fallback_cli=$('rescueCli').value;state.rescue.hot_fallback_enabled=$('rescueHot').checked;state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.enabled=$('visionEnabled').checked;state.vision_sidecar.provider_id=$('visionProvider').value.trim();state.vision_sidecar.model=$('visionModel').value.trim();state.vision_sidecar.candidates=[...document.querySelectorAll('[data-vision-candidate]')].map(row=>({provider_id:row.querySelector('[data-vc-provider]').value.trim(),model:row.querySelector('[data-vc-model]').value.trim()})).filter(x=>x.provider_id&&x.model)}
function bindVisionCandidateRow(row){const provider=row.querySelector('[data-vc-provider]');const model=row.querySelector('[data-vc-model]');provider.onchange=()=>{model.innerHTML=modelOptions(provider.value,'',{visionFirst:true});syncFallback()};model.onchange=syncFallback;row.querySelector('[data-vc-remove]').onclick=()=>{row.remove();syncFallback()}}
function renderVisionCandidates(candidates){const wrap=$('visionCandidates');wrap.innerHTML=(candidates||[]).map((item,i)=>{const provider=item.provider_id||item.provider||'';const model=item.model||item.vision_model||'';return `<div class="grid span12" data-vision-candidate="1"><div class="span5"><label>候选 ${i+1} provider</label><select data-vc-provider>${providerOptions(provider,{blankLabel:'请选择通道'})}</select></div><div class="span5"><label>候选 ${i+1} model</label><select data-vc-model>${modelOptions(provider,model,{visionFirst:true})}</select></div><div class="span2"><label>&nbsp;</label><button class="ghost" data-vc-remove>移除</button></div></div>`}).join('');document.querySelectorAll('[data-vision-candidate]').forEach(bindVisionCandidateRow)}
function renderFallback(){const r=state.rescue||{},v=state.vision_sidecar||{};$('rescueModel').value=r.fallback_model||'';$('rescueCli').value=r.fallback_cli||'';$('rescueHot').checked=!!r.hot_fallback_enabled;$('visionEnabled').checked=v.enabled!==false;const provider=v.provider_id||v.provider||'';const model=v.model||v.vision_model||'';$('visionProvider').innerHTML=providerOptions(provider,{blankLabel:'请选择 vision 通道'});$('visionProvider').value=provider;$('visionModel').innerHTML=modelOptions(provider,model,{visionFirst:true});$('visionModel').value=model;renderVisionCandidates(v.candidates||[]);['rescueModel','rescueCli','rescueHot','visionEnabled','visionModel'].forEach(id=>$(id).oninput=syncFallback);$('visionProvider').onchange=()=>{$('visionModel').innerHTML=modelOptions($('visionProvider').value,'',{visionFirst:true});syncFallback()};$('rescueHot').onchange=syncFallback;$('visionEnabled').onchange=syncFallback;$('addVisionCandidate').onclick=()=>{const provider=(state.providers[0]||{}).id||'';const model=(visibleModelsForProvider(provider,{visionFirst:true})[0]||{}).id||'';const list=[...(state.vision_sidecar?.candidates||[]),{provider_id:provider,model:model}];state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.candidates=list;renderVisionCandidates(list);syncFallback()}}
function opencodeOverrides(){state.opencode=state.opencode||{};state.opencode.agent_models=state.opencode.agent_models||{};return state.opencode.agent_models}
function opencodeRoster(){state.opencode=state.opencode||{};state.opencode.agent_roster=state.opencode.agent_roster||{};return state.opencode.agent_roster}
function opencodeOverrideEntries(){const overrides=opencodeOverrides();return Object.entries(overrides).filter(([,v])=>v&&v.model)}
function opencodeDefaults(){const map={};(state.opencode.agent_catalog||[]).forEach((row,i)=>{map[row.agent]={enabled:true,preset:row.preset||categoryPreset(row.category),priority:row.priority||((i+1)*10),custom:false}});return map}
function categoryPreset(category){const c=String(category||'');if(c==='Vision')return 'vision';if(c==='探索')return 'explore';if(c==='找茬')return 'bughunt';if(c==='审查')return 'reviewer';if(c==='执行')return 'executor';return 'builder'}
function rosterEntry(agent,row={}){const defaults=opencodeDefaults();return {...(defaults[agent]||{enabled:true,preset:row.preset||categoryPreset(row.category),priority:999,custom:!!row.custom}),...(opencodeRoster()[agent]||{})}}
function setOpencodeOverride(agent,provider,model){const overrides=opencodeOverrides();if(model){overrides[agent]={model};if(provider)overrides[agent].provider_id=provider}else{delete overrides[agent]}}
function persistRosterEntry(agent,row,patch={}){const roster=opencodeRoster();const defaults=opencodeDefaults();const base=rosterEntry(agent,row);const next={...base,...patch};const def=defaults[agent]||{};const providerMeaningful=!!next.provider_id&&(!!next.model||!!next.custom);const keep=!!next.custom||next.enabled===false||next.preset!==def.preset||Number(next.priority||0)!==Number(def.priority||0)||providerMeaningful||!!next.model||!!next.description||!!next.prompt;if(!keep){delete roster[agent];return}const payload={preset:next.preset||row.preset||categoryPreset(row.category),enabled:next.enabled!==false,priority:Number(next.priority||def.priority||999)};if(next.custom)payload.custom=true;if(providerMeaningful)payload.provider_id=next.provider_id;if(next.model)payload.model=next.model;if(next.description)payload.description=next.description;if(next.prompt)payload.prompt=next.prompt;roster[agent]=payload}
function setRosterEnabled(agent,row,enabled){persistRosterEntry(agent,row,{enabled})}
function opencodeAllRows(){const base=(state.opencode.agent_catalog||[]).map(row=>({...row,custom:false}));const seen=new Set(base.map(row=>row.agent));Object.entries(opencodeRoster()).forEach(([agent,entry])=>{if(seen.has(agent))return;base.push({agent,route_key:agent,category:presetLabel(entry.preset),preset:entry.preset||'explore',priority:entry.priority||999,default_models:[],custom:true})});return base.sort((a,b)=>Number(rosterEntry(a.agent,a).priority||999)-Number(rosterEntry(b.agent,b).priority||999)||a.agent.localeCompare(b.agent))}
function presetLabel(preset){return {builder:'执行/协调',executor:'执行',explore:'探索',bughunt:'找茬',vision:'Vision',reviewer:'审查',spec:'Spec',fixer:'执行'}[preset]||preset||'custom'}
function customAgentId(preset){const existing=new Set(opencodeAllRows().map(row=>row.agent));let i=1;let id='';do{id=`mobius-${preset}-custom-${i++}`}while(existing.has(id));return id}
function addCustomAgent(preset){const agent=customAgentId(preset);opencodeRoster()[agent]={enabled:true,custom:true,preset,priority:900+Object.keys(opencodeRoster()).length};renderOpencodeAgents();toast(`已添加 ${agent}`)}
function syncRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};state.runtime.preferred_cli=$('preferredCli').value;state.runtime.coding_preset_model=$('codingModel').value.trim();state.opencode.default_profile=$('opencodeProfile').value;state.opencode.agent_models=Object.fromEntries(opencodeOverrideEntries());state.opencode.agent_roster={...opencodeRoster()}}
function renderOpencodeSummary(){const box=$('opencodeOverrideSummary');if(!box)return;const rows=opencodeAllRows();const enabled=rows.filter(row=>rosterEntry(row.agent,row).enabled!==false).length;const count=opencodeOverrideEntries().length;const custom=rows.filter(row=>rosterEntry(row.agent,row).custom).length;const profile=state.opencode.default_profile||'agent';box.innerHTML=`<div class="oc-metric"><span class="muted">Profile</span><strong>${escapeHtml(profile)}</strong><span class="mono">Lite Pro Roster</span></div><div class="oc-metric"><span class="muted">Enabled agents</span><strong>${enabled}/${rows.length}</strong><span class="mono">进入 session-local opencode.json</span></div><div class="oc-metric"><span class="muted">Agent overrides</span><strong>${count}/${rows.length}</strong><span class="mono">Auto 不写 agent_models</span></div><div class="oc-metric"><span class="muted">Custom agents</span><strong>${custom}</strong><span class="mono">按 preset 继承 prompt/permission</span></div>`}
function opencodeFilterMatches(row,overridden){const entry=rosterEntry(row.agent,row);if(opencodeOnlyOverridden&&!overridden&&entry.enabled!==false&&!entry.custom)return false;if(opencodeAgentFilter==='all')return true;if(opencodeAgentFilter==='enabled')return entry.enabled!==false;if(opencodeAgentFilter==='custom')return !!entry.custom;if(opencodeAgentFilter==='execute')return ['builder','executor','fixer','spec'].includes(entry.preset)||String(row.category||'').startsWith('执行');if(opencodeAgentFilter==='explore')return entry.preset==='explore'||row.category==='探索';if(opencodeAgentFilter==='bughunt')return entry.preset==='bughunt'||row.category==='找茬';if(opencodeAgentFilter==='vision')return entry.preset==='vision'||row.category==='Vision';if(opencodeAgentFilter==='review')return entry.preset==='reviewer'||row.category==='审查';return true}
function renderOpencodeFilters(){const wrap=$('opencodeAgentFilters');if(!wrap)return;const filters=[['all','全部'],['enabled','已启用'],['custom','自定义'],['execute','执行/协调'],['explore','探索'],['bughunt','找茬'],['vision','Vision'],['review','审查']];wrap.innerHTML=`${filters.map(([id,label])=>`<button class="ghost ${opencodeAgentFilter===id?'active':''}" data-oc-filter="${id}">${label}</button>`).join('')}<label class="check"><input id="ocOnlyOverridden" type="checkbox" ${opencodeOnlyOverridden?'checked':''}><span>只看改动项</span></label><button class="ghost" data-oc-add="vision">+ Add Vision Agent</button><button class="ghost" data-oc-add="executor">+ Add Executor Agent</button><button class="ghost" data-oc-add="explore">+ Add Explore Agent</button><button class="ghost" id="ocClearAll">全部自动</button>`;document.querySelectorAll('[data-oc-filter]').forEach(btn=>btn.onclick=()=>{opencodeAgentFilter=btn.dataset.ocFilter;renderOpencodeAgents()});document.querySelectorAll('[data-oc-add]').forEach(btn=>btn.onclick=()=>addCustomAgent(btn.dataset.ocAdd));$('ocOnlyOverridden').onchange=()=>{opencodeOnlyOverridden=$('ocOnlyOverridden').checked;renderOpencodeAgents()};$('ocClearAll').onclick=()=>{state.opencode.agent_models={};state.opencode.agent_roster={};syncRuntime();renderOpencodeAgents();toast('OpenCode roster 已恢复默认自动路线')}}
function renderOpencodeAgents(){const table=$('opencodeAgents');if(!table)return;const overrides=opencodeOverrides();renderOpencodeSummary();renderOpencodeFilters();const rows=opencodeAllRows();const visible=rows.filter(row=>{const entry=rosterEntry(row.agent,row);const overridden=!!(overrides[row.agent]&&overrides[row.agent].model)||entry.enabled===false||entry.custom;return opencodeFilterMatches(row,overridden)});const presetOptions=(selected)=>['builder','executor','explore','bughunt','vision','reviewer','spec','fixer'].map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p}</option>`).join('');const body=visible.length?visible.map(row=>{const entry=rosterEntry(row.agent,row);const ov=overrides[row.agent]||{};const provider=ov.provider_id||entry.provider_id||'';const model=ov.model||entry.model||'';const enabled=entry.enabled!==false;const changed=!!model||!enabled||!!entry.custom;return `<tr data-oc-agent="${escapeHtml(row.agent)}"><td><input class="oc-enabled" type="checkbox" data-oc-enabled ${enabled?'checked':''} ${row.agent==='mobius-builder-pro'?'disabled':''}></td><td class="mono">${escapeHtml(row.agent)}<br><span class="muted">${escapeHtml(row.route_key)}</span>${entry.custom?'<br><span class="tag">custom</span>':''}${changed?'<span class="tag">changed</span>':''}</td><td><select data-oc-preset ${entry.custom?'':'disabled'}>${presetOptions(entry.preset)}</select></td><td><input data-oc-priority type="number" value="${escapeHtml(entry.priority||999)}" style="max-width:86px"></td><td><select data-oc-provider>${providerOptions(provider,{auto:true,enabledOnly:true})}</select></td><td><select data-oc-model>${modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})}</select></td><td class="mono default-route">${escapeHtml((row.default_models||[]).join(' / ')||'preset auto')}</td><td><button class="ghost" data-oc-reset>自动</button></td></tr>`}).join(''):'<tr><td colspan="8" class="empty-row">没有匹配的 agent</td></tr>';table.innerHTML=`<thead><tr><th>启用</th><th>Agent</th><th>Preset</th><th>Priority</th><th>Provider</th><th>Model</th><th>Default</th><th></th></tr></thead><tbody>${body}</tbody>`;document.querySelectorAll('[data-oc-agent]').forEach(tr=>{const agent=tr.dataset.ocAgent;const row=visible.find(r=>r.agent===agent);const entry=rosterEntry(agent,row);tr.querySelector('[data-oc-enabled]').onchange=(e)=>{setRosterEnabled(agent,row,e.target.checked);renderOpencodeSummary()};tr.querySelector('[data-oc-preset]').onchange=(e)=>{persistRosterEntry(agent,row,{preset:e.target.value});renderOpencodeAgents()};tr.querySelector('[data-oc-priority]').oninput=(e)=>{persistRosterEntry(agent,row,{priority:Number(e.target.value)});renderOpencodeSummary()};tr.querySelector('[data-oc-provider]').onchange=(e)=>{const sel=e.target;const modelSel=tr.querySelector('[data-oc-model]');modelSel.innerHTML=modelOptions(sel.value,modelSel.value,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:sel.value});setOpencodeOverride(agent,sel.value,tr.querySelector('[data-oc-model]').value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-model]').onchange=(e)=>{setOpencodeOverride(agent,tr.querySelector('[data-oc-provider]').value,e.target.value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-reset]').onclick=()=>{const roster=opencodeRoster();delete roster[agent];const overrides=opencodeOverrides();delete overrides[agent];syncRuntime();renderOpencodeAgents();toast(`${agent} 已恢复默认`)}})}
function renderRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};$('preferredCli').value=state.runtime.preferred_cli||'opencode';$('codingModel').value=state.runtime.coding_preset_model||'';$('opencodeProfile').value=state.opencode.default_profile||'agent';$('preferredCli').oninput=syncRuntime;$('codingModel').oninput=syncRuntime;$('opencodeProfile').oninput=()=>{syncRuntime();renderOpencodeSummary()};renderOpencodeAgents()}
function accountLocked(a){return !!a.is_claude_human_only}
function syncAccounts(){if(!state.accounts)return;state.account_defaults=state.account_defaults||{};document.querySelectorAll('[data-account-id]').forEach(tr=>{const id=tr.dataset.accountId;const acc=(state.accounts||[]).find(a=>a.id===id);if(!acc||accountLocked(acc))return;const nameEl=tr.querySelector('[data-account-name]');const enabledEl=tr.querySelector('[data-account-enabled]');const priorityEl=tr.querySelector('[data-account-priority]');if(nameEl)acc.name=nameEl.value;if(enabledEl)acc.enabled=enabledEl.checked;if(priorityEl)acc.priority=Number(priorityEl.value||100)});document.querySelectorAll('[data-account-default]:checked').forEach(el=>{if(!el.disabled&&el.dataset.accountCli)state.account_defaults[el.dataset.accountCli]=el.value})}
function mappingStatusLabel(status){return {native:'Native',report:'Report',draft_review:'Draft review',human_gate:'Human gate',missing:'Missing'}[status]||status||'-'}
function mappingStatusClass(status){return 'status-'+String(status||'missing').replace(/[^a-z0-9_ -]/gi,'').replace(/\s+/g,'_')}
function mappingActionButton(row){const parts=[];if(row.webui_section_id){parts.push(`<button class="ghost mapping-action" data-section-jump="${escapeHtml(row.webui_section_id)}">打开</button>`)}if(row.api_action){const label=row.status==='human_gate'?'Gate':(row.status==='missing'?'Gap':'Report');parts.push(`<button class="ghost mapping-action" data-settings-action="${escapeHtml(row.api_action)}">${label}</button>`)}return parts.join(' ')}
function renderMappingFilters(mapping){const box=$('mappingFilters');if(!box)return;const count=s=>mapping.filter(row=>s==='all'||row.status===s).length;const filters=[['all','全部'],['native','Native'],['report','Report'],['draft_review','Draft'],['human_gate','Gate'],['missing','Missing']];box.innerHTML=filters.map(([id,label])=>`<button class="${settingsMappingFilter===id?'active':''}" data-map-filter="${id}">${label} ${count(id)}</button>`).join('');document.querySelectorAll('[data-map-filter]').forEach(btn=>{btn.onclick=()=>{settingsMappingFilter=btn.dataset.mapFilter;renderSettings()}})}
function renderTuiMapping(mapping){renderMappingFilters(mapping);const rows=(settingsMappingFilter==='all'?mapping:mapping.filter(row=>row.status===settingsMappingFilter));const body=rows.length?rows.map(row=>`<tr><td class="mono">${escapeHtml(row.tui_area)}<br><span class="muted">${escapeHtml(row.tui_action_id)}</span></td><td>${escapeHtml(row.tui_label)}</td><td>${escapeHtml(row.webui_section)}<br><span class="muted">${escapeHtml(row.webui_control)}</span></td><td><span class="tag ${mappingStatusClass(row.status)}">${mappingStatusLabel(row.status)}</span><br><span class="muted">${escapeHtml(row.write_policy)}</span></td><td class="default-route">${escapeHtml(row.verification||'-')}<br><span class="muted">${escapeHtml(row.manual_check||'')}</span></td><td>${mappingActionButton(row)}</td></tr>`).join(''):'<tr><td colspan="6" class="empty-row">当前筛选没有条目</td></tr>';$('tuiMappingTable').innerHTML=`<thead><tr><th>TUI area/action</th><th>TUI label</th><th>WebUI 落点</th><th>Status</th><th>验证 / check</th><th>操作</th></tr></thead><tbody>${body}</tbody>`}
function bindSettingsActionButtons(){document.querySelectorAll('[data-settings-action]').forEach(btn=>{btn.onclick=async()=>{const action=btn.dataset.settingsAction;$('settingsReport').textContent='读取中...';const data=await api('/api/settings/report',{action});$('settingsReport').textContent=JSON.stringify(data,null,2);toast(data.ok?`${btn.textContent} report 已刷新`:`${btn.textContent} report 失败`)}});document.querySelectorAll('[data-section-jump]').forEach(btn=>{btn.onclick=()=>{setSection(btn.dataset.sectionJump);toast(`已打开 ${btn.dataset.sectionJump} 对应 WebUI 区域`)}})}
function syncUiSettings(){state.ui=state.ui||{};state.ui.language=$('uiLanguage')?.value||'zh'}
function renderUiSettings(mapping){state.ui=state.ui||{language:'zh'};const lang=state.ui.language||'zh';if($('uiLanguage')){$('uiLanguage').value=['zh','en'].includes(lang)?lang:'zh';$('uiLanguage').onchange=()=>{syncUiSettings();toast('界面语言已暂存，生成保存预览后再写入')}}const save=$('saveUiLanguage');if(save)save.onclick=()=>{syncUiSettings();setSection('save');toast('界面语言修改已暂存，生成保存预览后再写入')};const counts=(state.tui_webui_mapping_summary||{}).counts||{};const missingRows=(mapping||[]).filter(row=>row.status==='missing').map(row=>row.tui_label);if($('settingsGapSummary')){$('settingsGapSummary').innerHTML=`<span class="chip">native ${counts.native||0}</span><span class="chip">report ${counts.report||0}</span><span class="chip">draft ${counts.draft_review||0}</span><span class="chip">gate ${counts.human_gate||0}</span><span class="chip">missing ${counts.missing||0}</span>${missingRows.length?`<span class="chip">仍缺：${escapeHtml(missingRows.join(' / '))}</span>`:'<span class="chip">无 missing 行</span>'}`}}
function renderSettingsCommand(accounts,coverage,mapping){const board=$('settingsCommand');if(!board)return;const policy=state.account_write_policy||{};const summary=state.tui_webui_mapping_summary||{};const counts=summary.counts||{};const editable=accounts.filter(a=>!accountLocked(a)).length;const locked=accounts.filter(a=>accountLocked(a)).length;const nativeCount=counts.native??mapping.filter(r=>r.status==='native').length;const reportCount=(counts.report??mapping.filter(r=>r.status==='report').length)+(counts.draft_review??mapping.filter(r=>r.status==='draft_review').length);const gateCount=(counts.human_gate??mapping.filter(r=>r.status==='human_gate').length)+(counts.missing??mapping.filter(r=>r.status==='missing').length);const empty=accounts.length?'':`<div class="settings-empty-note"><strong>当前配置没有 OAuth account。</strong> 这也是你刚才看不出变化的原因：account draft/default 编辑器只会在存在 account 时出现；本页现在先把能力边界、TUI 降级路径和 human gate 明确展示出来。</div>`;board.innerHTML=`<div class="settings-command-head"><div><div class="settings-kicker">MMX / WEBUI TAKEOVER MAP</div><h3>Settings moved out of TUI</h3><p>这块现在是 settings/channel 迁移指挥台：${mapping.length} 条 TUI action 已逐项映射；能在 WebUI 里安全操作的直接显形，涉及真实账号、Claude config、Snapshot Guard accept、network/write 的动作保留 human gate。</p></div><div class="settings-stamp">${escapeHtml(policy.claude||'human_only_locked')}</div></div><div class="settings-metrics"><div class="settings-metric"><span>accounts loaded</span><strong>${accounts.length}</strong><em>${editable} editable / ${locked} Claude locked</em></div><div class="settings-metric"><span>native webui</span><strong>${nativeCount}</strong><em>direct WebUI controls</em></div><div class="settings-metric"><span>report / draft</span><strong>${reportCount}</strong><em>clickable JSON or save preview</em></div><div class="settings-metric"><span>gates / gaps</span><strong>${gateCount}</strong><em>visible, not hidden in TUI</em></div></div><div class="settings-route"><div class="settings-route-card ready"><b>01 / native controls</b><small>provider 编辑、模型管理、fallback/runtime/save 已经走 WebUI draft + diff。</small></div><div class="settings-route-card report"><b>02 / clickable reports</b><small>registry、about、usage、guard、rescue rows 都能点出 bounded JSON report。</small></div><div class="settings-route-card locked"><b>03 / human gates</b><small>Claude account、OAuth login/remove、Snapshot accept、network/write 操作不自动执行。</small></div><div class="settings-route-card"><b>04 / audit table</b><small>TUI ↔ WebUI 对照表是逐项 check list，不再让迁移范围藏在代码里。</small></div></div>${empty}`}
function renderSettings(){state.account_defaults=state.account_defaults||{};const accounts=state.accounts||[];const coverage=state.webui_capability_coverage||[];const mapping=state.tui_webui_mapping||[];renderSettingsCommand(accounts,coverage,mapping);renderUiSettings(mapping);const accountRows=accounts.length?accounts.map(a=>{const locked=accountLocked(a);const cli=String(a.cli||'').toLowerCase();const isDefault=(state.account_defaults||{})[cli]===a.id;return `<tr data-account-id="${escapeHtml(a.id)}"><td>${locked?'<span class="tag off">Claude human-only</span>':`<input data-account-enabled type="checkbox" ${a.enabled?'checked':''}>`}</td><td class="mono">${escapeHtml(a.id)}</td><td>${locked?escapeHtml(a.name):`<input data-account-name value="${escapeHtml(a.name)}" style="min-width:150px">`}</td><td>${escapeHtml((a.cli||'-').toUpperCase())}</td><td><input data-account-default data-account-cli="${escapeHtml(cli)}" name="account-default-${escapeHtml(cli)}" type="radio" value="${escapeHtml(a.id)}" ${isDefault?'checked':''} ${locked?'disabled':''}></td><td><input data-account-priority type="number" value="${escapeHtml(a.priority||100)}" ${locked?'disabled':''} style="max-width:82px"></td><td>${escapeHtml(a.auth_mode||'-')}</td><td>${a.home_dir_configured?'yes':'no'}</td><td>${a.proxy_configured?'yes':'no'}</td><td>${escapeHtml(a.timezone||'-')}</td><td>${a.usage?.launches||0}</td><td>${escapeHtml(a.usage?.last_used_at||'-')}</td><td><span class="tag ${locked?'off':''}">${escapeHtml(a.webui_write_policy||'read_only')}</span></td></tr>`}).join(''):'<tr><td colspan="13" class="empty-row">没有配置 OAuth/account 通道</td></tr>';$('accountTable').innerHTML=`<thead><tr><th>状态</th><th>ID</th><th>名称</th><th>CLI</th><th>默认</th><th>Priority</th><th>auth</th><th>home</th><th>proxy</th><th>timezone</th><th>启动</th><th>最近</th><th>WebUI 写入</th></tr></thead><tbody>${accountRows}</tbody>`;document.querySelectorAll('[data-account-name],[data-account-enabled],[data-account-priority]').forEach(el=>{el.oninput=()=>{syncAccounts();toast('account 草稿已暂存，生成保存预览后再写入')}});document.querySelectorAll('[data-account-default]').forEach(el=>{el.onchange=()=>{syncAccounts();renderSettings();toast('account 默认已暂存，生成保存预览后再写入')}});$('settingsCoverage').innerHTML=`<thead><tr><th>Area</th><th>Capability</th><th>WebUI</th><th>TUI 后续</th></tr></thead><tbody>${coverage.map(row=>`<tr><td>${escapeHtml(row.area)}</td><td>${escapeHtml(row.capability)}</td><td><span class="tag ${String(row.webui||'').includes('planned')||String(row.webui||'').includes('human_gate')?'off':''}">${escapeHtml(row.webui)}</span></td><td>${escapeHtml(row.tui)}</td></tr>`).join('')}</tbody>`;renderTuiMapping(mapping);const actionLabels=new Map([['tui_mapping','TUI Mapping'],['coverage','覆盖矩阵']]);mapping.forEach(row=>{if(row.api_action&&!actionLabels.has(row.api_action))actionLabels.set(row.api_action,row.tui_label||row.api_action)});$('maintenanceActions').innerHTML=[...actionLabels.entries()].map(([id,label])=>`<button class="ghost" data-settings-action="${escapeHtml(id)}">${escapeHtml(label)}</button>`).join('');bindSettingsActionButtons()}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function planJsonHint(plan){const v2=plan?.registry_v2_save_plan||{};const planJson=v2.plan_json||{};const apply=v2.apply_plan||{};if(!planJson.name&&!apply.cli_apply_command)return '';return `<h4>Plan JSON / apply-plan</h4><p class="muted">${escapeHtml(planJson.note||'Plan JSON 是保存预览的 review artifact。')}</p><p><span class="tag">${escapeHtml(planJson.name||'webui-plan.json')}</span> <span class="tag ${planJson.redacted?'off':''}">secrets ${planJson.redacted?'redacted':'included'}</span></p><p class="mono">${escapeHtml(apply.cli_apply_command||'')}</p>`}
function renderApplyResult(data){const blockers=data.runtime_blockers||{};const next=data.next_action||{};const publish=data.publish||{};const verify=data.verify||{};const ready=data.runtime_ready===true;const notReady=data.runtime_ready===false;const errs=Array.isArray(data.errors)?data.errors:[data.error||'unknown error'];const title=!data.ok?'写入被阻止':(ready?'已发布，可直接给 mmf 使用':'已发布，但 runtime 未就绪');const detail=!data.ok?errs.join('；'):(ready?'latest-approved bundle 已验证，mmf 会读到这次保存后的最新 bundle。':'latest-approved bundle 已发布且已验证；mmf 会读到最新 bundle，但缺 key/base URL/模型 route 的条目不能正常启动。');$('saveResult').innerHTML=`<div><p><span class="tag ${data.ok&&!notReady?'':'off'}">${escapeHtml(title)}</span> <span class="tag">${escapeHtml(data.status||'-')}</span></p><p class="muted">${escapeHtml(detail)}</p><p><span class="tag">manifest ${verify.verified?'verified':'not verified'}</span><span class="tag ${ready?'':'off'}">runtime ${ready?'ready':notReady?'not ready':'unknown'}</span><span class="tag">missing keys ${blockers.missing_api_key_count||0}</span><span class="tag">missing base URL ${blockers.missing_base_url_count||0}</span><span class="tag">provider routes ${blockers.provider_route_count||publish.provider_route_count||0}</span></p>${next.label?`<p><strong>下一步</strong>：${escapeHtml(next.label)}</p>`:''}<details><summary>Raw JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`}
function renderReviewSummary(plan){const review=plan?.review_summary||{};const counts=review.counts||{};const risks=review.risks||[];const items=review.items||[];const riskHtml=risks.length?`<h4>风险提示</h4><div>${risks.map(r=>`<p><span class="tag ${r.level==='danger'?'off':''}">${escapeHtml(levelLabel(r.level))}</span> <strong>${escapeHtml(r.title)}</strong> ${escapeHtml(r.detail)}</p>`).join('')}</div>`:'<p><span class="tag">无高风险提示</span></p>';const itemHtml=items.length?items.map(item=>`<p><span class="tag ${item.level==='danger'?'off':''}">${escapeHtml(levelLabel(item.level))}</span> <strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.detail)}</p>`).join(''):'<p class="muted">没有检测到配置变化。</p>';$('reviewSummary').innerHTML=`<div class="chips"><span class="chip">变化 ${counts.items||0}</span><span class="chip">风险 ${counts.risks||0}</span><span class="chip">移除隐藏记录 ${counts.hidden_removed||0}</span><span class="chip">凭据更新 ${counts.credential_updates||0}</span></div>${riskHtml}<h4>将要写入的变化</h4>${itemHtml}${planJsonHint(plan)}`}
function currentBundleRevision(){return state?.consumer_bundle_status?.component_revisions?.bundle||state?.consumer_bundle_status?.manifest?.bundle_revision||state?.model_source_status?.generated_bundle?.component_revisions?.bundle||state?.model_source_status?.generated_bundle?.manifest?.bundle_revision||''}
function draft(){syncProvider();syncFallback();syncRuntime();syncAccounts();syncUiSettings();return JSON.parse(JSON.stringify({providers:state.providers,provider_default:state.provider_default,accounts:state.accounts,account_defaults:state.account_defaults,rescue:state.rescue,vision_sidecar:state.vision_sidecar,ui:state.ui,runtime:state.runtime,opencode:state.opencode,expected_bundle_revision:currentBundleRevision(),route_scope_provider_ids:[...touchedProviders],route_refresh_provider_ids:[...staleCleanupProviders]}))}
function renderAll(){renderStatus();renderSaveControls();renderSourceStatus();renderProviders();renderFallback();renderRuntime();renderSettings();renderRefs()}
async function load(){const res=await fetch('/api/state');state=await res.json();state.providers=state.providers||[];renderNav();renderAll();}
$('addProvider').onclick=()=>{state.providers.push({id:`provider-${state.providers.length+1}`,original_id:'',name:'新通道',enabled:true,role:'auto',priority:100,models_endpoint:'/models',protocols:['anthropic_messages','openai_chat_completions'],supported_clis:['claude','codex','opencode'],openai_base_url:'',anthropic_base_url:'',api_key:'',update_credentials:false,fallback_models:[],extra_models:[],hidden_models:[],models:[]});activeProvider=state.providers.length-1;renderAll()}
$('duplicateProvider').onclick=()=>{const p=JSON.parse(JSON.stringify(current()));p.id=p.id+'-copy';p.original_id='';p.name=p.name+' Copy';p.api_key='';p.pending_api_key=false;p.update_credentials=false;p.has_api_key=false;state.providers.push(p);activeProvider=state.providers.length-1;renderAll()}
$('modelSearch').oninput=renderModelTable;$('addManualModels').onclick=()=>{const p=current();const vals=$('manualModels').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);p.extra_models=[...new Set([...(p.extra_models||[]),...vals])];p.hidden_models=(p.hidden_models||[]).filter(x=>!vals.includes(x));$('manualModels').value='';renderModelTable();toast(`已添加 ${vals.length} 个模型`)};$('clearHidden').onclick=()=>{current().hidden_models=[];renderModelTable()};$('clearAllStaleHidden').onclick=cleanupAllStaleHidden
$('fetchModels').onclick=async()=>{syncProvider();const data=await api('/api/provider/models',{provider:current(),force_refresh:true});if(data.ok&&Array.isArray(data.models)){const p=current();if(!p.approved_route_models||!p.approved_route_models.length){p.approved_route_models=(p.models||[]).filter(r=>r&&r.id&&r.source!=='derived_alias').map(r=>r.id)}p.models=data.models.map(id=>({id,source:data.base_source||'remote',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)}));touchProvider(p.id);if($('autoStaleCleanupOnFetch')?.checked&&staleRouteModels(p).length){staleCleanupProviders.add(p.id)}renderModelTable();$('testResult').textContent=JSON.stringify(data,null,2);toast(staleCleanupProviders.has(p.id)?`拉取到 ${data.models.length} 个模型；已自动标记缺失旧 route 清理`:`拉取到 ${data.models.length} 个模型；不会自动写入 fallback_models；缺失旧 route 默认保留`)}else{$('testResult').textContent=JSON.stringify(data,null,2);toast(data.error||'模型拉取失败，请看测试结果')}}
$('testList').onclick=async()=>{$('testResult').textContent=JSON.stringify(await api('/api/provider/test',{provider:current(),force_refresh:true}),null,2);setSection('test')}
$('testModelBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/model/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('chatTestBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/chat/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('previewPlan').onclick=async()=>{const data=await api('/api/plan',{draft:draft()});lastPlan=data;renderSaveControls();renderReviewSummary(data);$('saveResult').textContent=JSON.stringify({ok:data.ok,summary:data.summary,registry_v2_save_plan:data.registry_v2_save_plan,warnings:data.warnings,errors:data.errors,risks:data.review_summary?.risks},null,2);$('diffBox').textContent=[data.diffs?.config_toml,data.diffs?.model_policy_json,data.diffs?.credentials].filter(Boolean).join('\n')||'没有配置变化';toast(data.ok?'预览已生成':'预览有错误')}
function currentApplyCommand(){return lastPlan?.registry_v2_save_plan?.apply_plan?.cli_apply_command||'./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json'}
$('downloadPlanJson').onclick=()=>{if(!lastPlan){toast('请先生成保存预览');return}const blob=new Blob([JSON.stringify(lastPlan,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=lastPlan?.registry_v2_save_plan?.plan_json?.name||'webui-plan.json';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast('已下载 redacted plan JSON')}
$('copyApplyCommand').onclick=async()=>{const cmd=currentApplyCommand();try{await navigator.clipboard.writeText(cmd);toast('已复制 CLI apply 命令')}catch(_err){$('saveResult').textContent=cmd;toast('无法访问剪贴板，命令已显示在结果框')}}
$('applyV2Preview').onclick=async()=>{const data=await api('/api/registry-v2/apply',{draft:draft(),confirm_v2_preview:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});renderApplyResult(data);toast(data.ok?(data.runtime_ready===false?'已发布但 runtime 未就绪：请看 missing key/base URL':'预览 DB 已写入并发布，mmf 会读最新 bundle'):'预览 DB 写入被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
$('saveBtn').onclick=async()=>{const data=await api('/api/save',{draft:draft(),confirm_save:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});$('saveResult').textContent=JSON.stringify(data,null,2);toast(data.ok?'保存完成，已写入 audit':'保存被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
load().catch(err=>{document.body.innerHTML='<pre style="padding:30px;color:var(--danger);font-family:var(--font-mono)">'+escapeHtml(err.stack||err.message)+'</pre>'})
</script>
</body>
</html>"""


def _html_page(_snapshot: dict[str, Any]) -> bytes:
    return _HTML_PAGE.encode("utf-8")


class ConfigWebApp:
    def __init__(self, cfg: dict[str, Any] | None, *, config_path: str = "", preferences_path: str = "", command_name: str = "mms") -> None:
        self.cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
        self.config_path = config_path
        self.preferences_path = preferences_path
        self.command_name = command_name
        self.lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return build_config_snapshot(self.cfg, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
            if result.get("ok"):
                plan = build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)
                self.cfg = plan.get("config") if isinstance(plan.get("config"), dict) else self.cfg
            return result

    def registry_v2_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            result = apply_registry_v2_preview_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path)
            if result.get("ok"):
                plan = build_config_plan(self.cfg, payload, config_path=self.config_path, preferences_path=self.preferences_path, command_name=self.command_name)
                self.cfg = plan.get("config") if isinstance(plan.get("config"), dict) else self.cfg
            return result

    def provider_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return test_provider_models(self.cfg, payload, config_path=self.config_path, command_name=self.command_name)

    def model_test(self, payload: dict[str, Any], *, chat: bool = False) -> dict[str, Any]:
        with self.lock:
            return run_model_smoke(self.cfg, payload, chat=chat, config_path=self.config_path, command_name=self.command_name)

    def settings_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            return build_settings_report(
                self.cfg,
                payload,
                config_path=self.config_path,
                preferences_path=self.preferences_path,
                command_name=self.command_name,
            )


class _SetupWebHandler(BaseHTTPRequestHandler):
    app: ConfigWebApp | None = None

    def log_message(self, *_args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid json: {exc}") from exc
        return payload if isinstance(payload, dict) else {}

    def do_GET(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        snapshot = app.snapshot()
        if path in {"/", "/index.html"}:
            self._send(200, _html_page(snapshot), "text/html; charset=utf-8")
            return
        if path in {"/api/state", "/api/snapshot"}:
            self._send(*_json_response(snapshot))
            return
        if path == "/api/references":
            self._send(*_json_response({"references": build_reference_cards()}))
            return
        if path == "/setup.md":
            self._send(200, build_setup_markdown(snapshot).encode("utf-8"), "text/markdown; charset=utf-8")
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        app = self.app
        if app is None:
            self._send(*_json_response({"error": "app not initialized"}, status=500))
            return
        path = self.path.split("?", 1)[0]
        try:
            payload = self._read_json()
            if path == "/api/provider/models" or path == "/api/provider/test":
                self._send(*_json_response(app.provider_test(payload)))
                return
            if path == "/api/model/test":
                self._send(*_json_response(app.model_test(payload, chat=False)))
                return
            if path == "/api/chat/test":
                self._send(*_json_response(app.model_test(payload, chat=True)))
                return
            if path == "/api/settings/report":
                self._send(*_json_response(app.settings_report(payload)))
                return
            if path == "/api/plan":
                self._send(*_json_response(app.plan(payload)))
                return
            if path == "/api/save":
                result = app.save(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            if path == "/api/registry-v2/apply":
                result = app.registry_v2_apply(payload)
                self._send(*_json_response(result, status=200 if result.get("ok") else 400))
                return
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
        except Exception as exc:
            self._send(*_json_response({"ok": False, "error": str(exc), "trace": traceback.format_exc(limit=5)}, status=500))


def serve_config_web(app_or_snapshot: ConfigWebApp | dict[str, Any], *, host: str, port: int, open_browser: bool = True) -> str:
    if isinstance(app_or_snapshot, ConfigWebApp):
        app = app_or_snapshot
    else:
        app = ConfigWebApp({}, command_name="mms")
    handler = type("MMSSetupWebHandler", (_SetupWebHandler,), {"app": app})
    server = ThreadingHTTPServer((host, int(port)), handler)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="mms-setup-web")
    thread.start()
    print(f"MMS 配置 WebUI: {url}")
    print("交互配置页面已启动；保存前会要求 diff + 明确确认。按 Ctrl-C 停止。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping MMS setup WebUI.")
    finally:
        server.shutdown()
        server.server_close()
    return url


def run_config_web(
    cfg: dict[str, Any] | None,
    argv: list[str] | None = None,
    *,
    command_name: str = "mms",
    config_path: str = "",
    preferences_path: str = "",
) -> int:
    parser = argparse.ArgumentParser(prog=f"{command_name} config web", description="Start the local interactive MMS configuration WebUI")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; default 127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="Bind port; default 0 chooses a free port")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--print-summary", action="store_true", help="Print redacted setup JSON and exit")
    parser.add_argument("--print-markdown", action="store_true", help="Print setup markdown and exit")
    args = parser.parse_args(argv or [])
    app = ConfigWebApp(cfg, config_path=config_path, preferences_path=preferences_path, command_name=command_name)
    snapshot = app.snapshot()
    if args.print_summary:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.print_markdown:
        print(build_setup_markdown(snapshot), end="")
        return 0
    serve_config_web(app, host=args.host, port=args.port, open_browser=not args.no_open)
    return 0
