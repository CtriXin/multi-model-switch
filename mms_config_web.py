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
    if branch and commit:
        display = f"{branch}@{commit}"
    elif channel and release:
        display = f"{channel} {release}"
    else:
        display = release
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


def _settings_action_cards() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    try:
        from mms_display.settings_actions import list_tui_settings_actions

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
            "capability": "provider 新增/编辑/默认/role/priority/Base URL/API Key/protocol/CLI/timezone/note/Claude 1M",
            "webui": "native",
            "tui": "can_degrade_after_save_flow_verified",
        },
        {
            "area": "通道",
            "capability": "模型拉取、手动 extra_models、hidden_models、能力标签",
            "webui": "native",
            "tui": "can_degrade_after_route_guard_verified",
        },
        {
            "area": "通道",
            "capability": "本地使用统计 / 最近使用 / 健康覆盖层",
            "webui": "read_only_detail_report",
            "tui": "can_degrade_after_report_smoke",
        },
        {
            "area": "账号",
            "capability": "CLI account 默认值、启用状态、priority、metadata、timezone、note；OAuth 登录主流程下线",
            "webui": "draft_review_human_gate",
            "tui": "keep_emergency_only_for_remove_and_claude_human_gate",
        },
        {
            "area": "设置",
            "capability": "Registry 源状态、preview doctor、Bundle、就绪度和状态",
            "webui": "read_only_reports_plus_existing_apply",
            "tui": "can_degrade_report_display_after_webui_smoke",
        },
        {
            "area": "设置",
            "capability": "Snapshot Guard 接受基线 / 真实配置 drift 确认",
            "webui": "manual_cli_human_gate",
            "tui": "keep_until_webui_double_confirm_flow_exists",
        },
        {
            "area": "设置",
            "capability": "Rescue fallback 配置",
            "webui": "native",
            "tui": "can_degrade_config_display_after_save_flow_verified",
        },
        {
            "area": "设置",
            "capability": "Rescue packet 浏览 / fallback 交接",
            "webui": "read_only_report",
            "tui": "keep_emergency_only_until_handover_write_flow_exists",
        },
        {
            "area": "设置",
            "capability": "界面语言和关于/版本检查",
            "webui": "report_or_planned",
            "tui": "keep_small",
        },
        {
            "area": "主屏入口",
            "capability": "O 接入 / P 通道 / S 设置入口覆盖状态",
            "webui": "module_native_controls_plus_reports",
            "tui": "keep_as_keyboard_launcher_until_webui_launch_surface_exists",
        },
    ]


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
        click_targets = []
        if webui_section_id:
            click_targets.append("open_section")
        if api_action:
            click_targets.append("settings_report")
        if status in {"native", "draft_review"}:
            click_targets.append("save_preview")
        if status == "human_gate":
            click_targets.append("human_gate_card")
        if status == "missing":
            click_targets.append("missing_gap")
        click_text = " + ".join(dict.fromkeys(click_targets))
        if status == "human_gate":
            acceptance_check = "点人工确认查看风险/写入范围/命令；只复制命令，不在 WebUI 自动执行。"
        elif status == "report":
            acceptance_check = "点报告确认 API 返回 ok/只读 JSON。"
        elif status == "draft_review":
            acceptance_check = "编辑草稿后生成保存预览，确认审查摘要和 diff。"
        elif status == "native":
            acceptance_check = "点打开 WebUI 落点；如修改配置，继续生成保存预览确认。"
        else:
            acceptance_check = "必须补 WebUI 落点或显式 gate，不允许隐藏。"
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
            "clickable": "yes" if webui_section_id or api_action else "no",
            "click_targets": click_text,
            "acceptance_check": acceptance_check,
        }

    rows = [
        row(
            "connect.add_gateway",
            tui_area="Main / O 接入",
            tui_action_id="connect_gateway",
            tui_label="添加网关通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="添加通道按钮 + 通道编辑器 + 保存预览",
            api_action="connect_gateway_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_added + save review",
            manual_check="WebUI 新增 provider 后仍需保存预览，不直接写真实配置。",
        ),
        row(
            "connect.add_official",
            tui_area="Main / O 接入",
            tui_action_id="connect_official",
            tui_label="添加官方通道 / OAuth 登录",
            webui_section="Settings / 兼容说明",
            webui_section_id="settings",
            webui_control="OAuth/AGY 官方登录已从 WebUI 主流程下线；仅保留只读兼容说明",
            api_action="connect_official_gate",
            status="report",
            write_policy="deprecated_read_only_compat",
            verification="/api/settings/report?action=connect_official_gate",
            manual_check="新配置使用 API Key 通道；旧 OAuth/AGY 账号只做兼容查看，不再作为新增入口。",
        ),
        row(
            "connect.manage_channels",
            tui_area="Main / O 接入",
            tui_action_id="manage_channels",
            tui_label="管理现有通道",
            webui_section="通道配置 + Settings / 账号",
            webui_section_id="channel",
            webui_control="通道编辑器 + 账号表模块动作",
            api_action="tui_mapping",
            status="native",
            write_policy="mixed_draft_review_human_gate",
            verification="/api/settings/report?action=tui_mapping",
            manual_check="网关通道 native；官方账号危险动作 需要人工确认。",
        ),
        row(
            "connect.migrate_config",
            tui_area="Main / O 接入",
            tui_action_id="migrate_config",
            tui_label="迁移配置到 mms",
            webui_section="能力整合",
            webui_section_id="settings",
            webui_control="迁移人工确认报告",
            api_action="migrate_config_gate",
            status="human_gate",
            write_policy="manual_cli_human_gate",
            verification="/api/settings/report?action=migrate_config_gate",
            manual_check="迁移会读写真实配置树，必须人工执行/确认。",
        ),
        row(
            "channel.provider_browse",
            tui_area="Main / P 通道",
            tui_action_id="provider_browse",
            tui_label="浏览 / 选择通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道列表、使用统计标签、默认值和 priority 字段",
            api_action="provider_usage_summary",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=provider_usage_summary",
            manual_check="启动时选择仍属于 launcher；配置侧状态已在 WebUI 可见。",
        ),
        row(
            "channel.provider_switch",
            tui_area="Model / Channel column",
            tui_action_id="←/→ focus + Enter provider override",
            tui_label="模型页切换通道来源",
            webui_section="通道配置 + Runtime",
            webui_section_id="channel",
            webui_control="默认通道、priority 字段、runtime/opencode 模型选择器",
            api_action="provider_channel_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_default/priority/runtime diffs",
            manual_check="WebUI 做持久配置；TUI 的单次启动选择仍保留为 launcher 能力。",
        ),
        row(
            "channel.priority_adjust",
            tui_area="Model / Channel column",
            tui_action_id="+/- priority_changes",
            tui_label="调整通道权重",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道 priority + family_priority_overrides 字段 + 保存预览",
            api_action="provider_channel_status",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider priority/family override diff",
            manual_check="全局 priority 与 family_priority_overrides 都进入 WebUI 草稿和保存预览。",
        ),
        row(
            "channel.family_autosort",
            tui_area="Model / Channel column",
            tui_action_id="A auto rank",
            tui_label="按 speed stats 智能排序",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道报告与确认 tab 的自动排序用途说明",
            api_action="family_autosort_gate",
            status="human_gate",
            write_policy="speed_stats_write_human_gate",
            verification="/api/settings/report?action=family_autosort_gate",
            manual_check="自动排序会批量改 priority/family override；WebUI 当前只展示用途和人工确认说明，不静默改顺序。",
        ),
        row(
            "settings.provider_mgmt",
            tui_area="Settings",
            tui_action_id="provider_mgmt",
            tui_label="Provider 管理",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="左侧通道列表、通道配置 tab、模型配置 tab、保存审计",
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
            webui_section="Settings / 账号",
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
            tui_label="模型源状态",
            webui_section="配置源状态",
            webui_section_id="source",
            webui_control="配置源状态卡片 + 报告按钮 + 保存 / 应用流程",
            api_action="model_source_status",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=model_source_status",
            manual_check="写入类 registry 操作必须继续走 save/apply 人工确认。",
        ),
        row(
            "settings.guard",
            tui_area="Settings",
            tui_action_id="guard",
            tui_label="启动快照",
            webui_section="Settings / Snapshot Guard",
            webui_section_id="settings",
            webui_control="Snapshot 快照状态 / 人工确认报告",
            api_action="guard_accept_gate",
            status="human_gate",
            write_policy="manual_cli_human_gate",
            verification="/api/settings/report?action=guard_accept_gate",
            manual_check="accept 不自动执行；必须 human double-confirm。",
        ),
        row(
            "settings.rescue",
            tui_area="Settings",
            tui_action_id="rescue",
            tui_label="中断/救援",
            webui_section="Fallback",
            webui_section_id="fallback",
            webui_control="rescue fallback / hot fallback 表单 + rescue 事件报告",
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
            webui_section="Settings / 界面语言",
            webui_section_id="settings",
            webui_control="界面语言选择器 + 保存审计",
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
            webui_control="生成保存预览、stable 审计保存、preview DB 发布",
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
            webui_section="Settings / 关于",
            webui_section_id="settings",
            webui_control="关于状态",
            api_action="about",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=about",
            manual_check="upgrade 动作仍是 manual CLI/人工确认。",
        ),
        row(
            "provider.local_usage",
            tui_area="Channel / Provider",
            tui_action_id="provider:1",
            tui_label="查看本地统计",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道列表使用统计标签 + 使用统计报告",
            api_action="provider_usage_summary",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=provider_usage_summary",
            manual_check="WebUI report 返回 TUI 同等 CLI/启动次数/最近模型/最近使用明细。",
        ),
        row(
            "provider.models",
            tui_area="Channel / Provider",
            tui_action_id="provider:2",
            tui_label="模型管理",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="模型配置 tab、拉取模型、extra_models、hidden_models、能力开关",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/provider/models + /api/plan",
            manual_check="检查模型拉取、隐藏/补充、capability toggle、stale cleanup。",
        ),
        row(
            "provider.model_patch_reset",
            tui_area="Channel / Provider",
            tui_action_id="provider:2/model:6",
            tui_label="恢复默认模型补丁",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="模型配置 tab 恢复模型补丁按钮",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan extra_models/hidden_models diff",
            manual_check="一键清空当前通道 extra_models + hidden_models，然后保存预览。",
        ),
        row(
            "provider.default",
            tui_area="Channel / Provider",
            tui_action_id="provider:3",
            tui_label="设为默认网关",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="设为默认通道复选框",
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
            webui_control="内部 ID + 显示名字段",
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
            webui_control="OpenAI/Anthropic Base URL、models_endpoint、API Key 待保存",
            status="native",
            write_policy="audited_secret_write",
            verification="/api/plan redacts key; save writes audited secret backend",
            manual_check="API Key 只显示 pending，不回显明文。",
        ),
        row(
            "provider.advanced_metadata",
            tui_area="Channel / Provider",
            tui_action_id="provider.edit metadata",
            tui_label="编辑 Claude 1M / timezone / note",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道高级 metadata 字段",
            status="native",
            write_policy="draft_review_confirmed_save",
            verification="/api/plan provider_metadata review_summary",
            manual_check="TUI provider.edit 的非 secret 元数据进入 WebUI 草稿和保存预览。",
        ),
        row(
            "provider.network_policy",
            tui_area="Channel / Provider",
            tui_action_id="provider.edit proxy/no_proxy",
            tui_label="编辑 proxy / no_proxy",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="通道配置模块里的通道网络策略人工确认",
            api_action="provider_network_gate",
            status="human_gate",
            write_policy="network_policy_human_gate",
            verification="/api/settings/report?action=provider_network_gate",
            manual_check="proxy/no_proxy 可能包含凭据或影响 Claude network policy；WebUI 不回显明文，只给 gate。",
        ),
        row(
            "provider.remove",
            tui_area="Channel / Provider",
            tui_action_id="provider:6",
            tui_label="删除通道",
            webui_section="通道配置",
            webui_section_id="channel",
            webui_control="输入通道 ID 确认 + 保存预览摘要",
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
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表使用统计列 + 账号摘要报告",
            api_action="accounts",
            status="report",
            write_policy="read_only_report",
            verification="/api/settings/report?action=accounts",
            manual_check="WebUI accounts report 返回 TUI 同等 CLI/启动次数/最近模型/最近使用明细。",
        ),
        row(
            "account.login",
            tui_area="Channel / Account",
            tui_action_id="account:2",
            tui_label="重新登录",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的登录人工确认",
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
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="非 Claude 默认账号单选按钮",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks Claude default and accepts non-Claude default",
            manual_check="Claude default radio disabled；非 Claude 进入保存预览。",
        ),
        row(
            "account.rename",
            tui_area="Channel / Account",
            tui_action_id="account:4",
            tui_label="重命名",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的重命名人工确认",
            api_action="account_rename_gate",
            status="human_gate",
            write_policy="account_home_human_gate",
            verification="/api/settings/report?action=account_rename_gate",
            manual_check="账号重命名会改 home_dir/usage/defaults 并可能移动目录；WebUI 不自动执行。",
        ),
        row(
            "account.edit_metadata",
            tui_area="Channel / Account",
            tui_action_id="account:5",
            tui_label="编辑通道",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="非 Claude 名称/启用/priority/family/timezone/Claude 1M/note 草稿字段",
            api_action="accounts",
            status="draft_review",
            write_policy="draft_review_human_gate",
            verification="/api/plan blocks protected fields",
            manual_check="非 Claude metadata 进入 WebUI 保存预览；home_dir/proxy/no_proxy/Claude metadata 仍锁定。",
        ),
        row(
            "account.network_policy",
            tui_area="Channel / Account",
            tui_action_id="account.edit proxy/no_proxy",
            tui_label="编辑账号 proxy / no_proxy",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的网络策略人工确认",
            api_action="account_network_gate",
            status="human_gate",
            write_policy="account_network_human_gate",
            verification="/api/settings/report?action=account_network_gate",
            manual_check="账号 proxy/no_proxy/home_dir 可能涉及 OAuth/Claude protected state；WebUI 不回显明文。",
        ),
        row(
            "account.remove",
            tui_area="Channel / Account",
            tui_action_id="account:6",
            tui_label="删除通道",
            webui_section="Settings / 账号",
            webui_section_id="settings",
            webui_control="账号表动作按钮里的删除人工确认",
            api_action="account_remove_gate",
            status="human_gate",
            write_policy="manual_remove_only",
            verification="/api/settings/report?action=account_remove_gate",
            manual_check="删除账号目录/登录状态必须由 human 手动确认。",
        ),
    ]

    registry_rows = [
        ("registry.model_source_status", "model_source_status", "查看配置源状态", "model_source_status", "report", "read_only_report"),
        ("registry.consumer_bundle_status", "consumer_bundle_status", "查看消费端 Bundle", "consumer_bundle_status", "report", "read_only_report"),
        ("registry.v2_save_plan", "registry_v2_save_plan", "查看 v2 保存计划", "", "native", "save_preview"),
        ("registry.config_v2_promotion_plan", "config_v2_promotion_plan", "查看晋级计划", "config_v2_promotion_plan", "report", "read_only_report"),
        ("registry.config_v2_release_readiness", "config_v2_release_readiness", "查看 4.0 就绪度", "config_v2_release_readiness", "report", "read_only_report"),
        ("registry.preview_doctor", "preview_doctor", "运行预览诊断", "preview_doctor", "report", "read_only_report"),
        ("registry.check_staleness", "check_staleness", "检查 source 过期状态", "check_staleness", "report", "read_only_report"),
        ("registry.refresh_due_sources", "refresh_due_sources", "刷新到期 source", "refresh_due_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.scheduled_dry_run", "scheduled_dry_run", "定时刷新 dry run", "scheduled_refresh_gate", "human_gate", "network_human_gate"),
        ("registry.scheduled_no_network", "scheduled_no_network", "定时刷新 no-network", "scheduled_refresh_gate", "human_gate", "manual_cli_human_gate"),
        ("registry.refresh_sources", "refresh_sources", "刷新全部 source", "refresh_sources_gate", "human_gate", "network_write_human_gate"),
        ("registry.fetch_openrouter", "fetch_openrouter", "拉取 OpenRouter catalog", "fetch_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.diff_openrouter", "diff_openrouter", "对比 OpenRouter candidate", "diff_openrouter_gate", "human_gate", "network_human_gate"),
        ("registry.publish_approved", "publish_approved", "发布已批准 Bundle", "publish_approved_gate", "human_gate", "write_human_gate"),
        ("registry.verify_approved", "verify_approved", "验证已批准 Bundle", "verify_approved", "report", "read_only_report"),
        ("registry.doctor", "doctor", "Registry 诊断 / 状态", "registry_status", "report", "read_only_report"),
    ]
    for row_id, action_id, label, api_action, status, write_policy in registry_rows:
        manual_check = (
            "只读 manifest/hash 验证，可直接在 WebUI 执行；publish 仍 需要人工确认。"
            if action_id == "verify_approved"
            else "只读项可直接点；network/write 类先人工确认，不静默执行。"
        )
        rows.append(
            row(
                row_id,
                tui_area="Settings / Registry",
                tui_action_id=action_id,
                tui_label=label,
                webui_section="保存 / 审计" if action_id == "registry_v2_save_plan" else "配置源状态",
                webui_section_id="save" if action_id == "registry_v2_save_plan" else "source",
                webui_control="保存页生成保存预览" if action_id == "registry_v2_save_plan" else "配置源状态模块动作按钮",
                api_action=api_action,
                status=status,
                write_policy=write_policy,
                verification=f"/api/settings/report?action={api_action}" if api_action else "/api/plan",
                manual_check=manual_check,
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
        ("rescue.handover", "Settings / Rescue", "handover/manual_handover", "生成 fallback handover", "rescue_handover_gate", "human_gate", "local_artifact_human_gate"),
        ("rescue.view_md_paths", "Settings / Rescue", "view_md/show_paths", "查看 rescue.md / 显示文件路径", "rescue_events", "report", "read_only_report"),
        ("about.refresh", "Settings / 关于", "refresh_versions", "刷新版本检查", "about_refresh_gate", "human_gate", "network_human_gate"),
        ("about.upgrade", "Settings / 关于", "upgrade_mms/upgrade_codex_cli/upgrade_claude_cli", "升级 MMS / CLI", "about_upgrade_gate", "human_gate", "manual_cli_human_gate"),
    ]
    for row_id, area, action_id, label, api_action, status, write_policy in extra_rows:
        is_rescue = area.endswith("Rescue")
        is_guard = "Snapshot Guard" in area
        is_about = area.endswith("About")
        rows.append(
            row(
                row_id,
                tui_area=area,
                tui_action_id=action_id,
                tui_label=label,
                webui_section="Fallback" if is_rescue else "Settings / Snapshot Guard" if is_guard else "Settings / 关于" if is_about else "Settings",
                webui_section_id="fallback" if is_rescue else "settings",
                webui_control="Fallback 表单 / rescue 动作按钮" if is_rescue else "Snapshot Guard 独立卡片" if is_guard else "关于独立卡片",
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
    clickable = 0
    with_report = 0
    with_open = 0
    for item in rows:
        status = _safe_text(item.get("status"))
        if status in counts:
            counts[status] += 1
        if item.get("clickable") == "yes" or item.get("api_action") or item.get("webui_section_id"):
            clickable += 1
        if item.get("api_action"):
            with_report += 1
        if item.get("webui_section_id"):
            with_open += 1
    return {
        "schema": "mms.setup_web.tui_mapping_summary.v1",
        "total": len(rows),
        "counts": counts,
        "clickable_rows": clickable,
        "rows_with_report_or_gate": with_report,
        "rows_with_open_target": with_open,
        "user_check_policy": "每行都可在 WebUI 点击：打开跳到页面落点，报告/人工确认验证 API 或人工确认卡，原生/草稿行再用保存预览核对写入。",
        "source_files": [
            "mms_display/tui.py:_connect_actions",
            "mms_display/tui.py:select_submodel_tui",
            "mms_display/tui.py:_settings_menu",
            "mms_core.py settings/provider/account/rescue action handlers",
        ],
        "policy": "原生/报告行由对应 WebUI 模块承接；human_gate/missing 行保留 CLI 人工路径。load_balance 已明确不进入本轮迁移。",
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
            "summary": "设置 首选 CLI、coding preset 和 OpenCode Multi-Agent profile。",
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
            "summary": "哪些日常偏好适合 preferences.toml，哪些真实配置必须 人工确认。",
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
        if provider_id in before_ids and _mapping_digest(before_meta) != _mapping_digest(after_meta):
            add_item(
                "provider_metadata",
                f"通道元数据变化：{provider_id}",
                f"name/enabled/role/priority/claude_1m/timezone/note 将更新；priority `{before_meta['priority']}` -> `{after_meta['priority']}`。",
                provider_id=provider_id,
                level="warn",
                meta={"before": before_meta, "after": after_meta},
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
    from mms_registry.cli import registry_v2_route_publish_guard, registry_v2_save_plan

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
        from mms_registry.cli import restore_registry_db

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
        from mms_runtime.state_io import mms_config_root_status

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
        from mms_registry.cli import registry_v2_route_publish_guard

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
        from mms_registry.cli import apply_registry_v2_save_candidate, publish_preview_bundle, verify_approved_bundle, write_registry_v2_webui_secret_backend

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


def _about_upgrade_gate_commands() -> list[str]:
    try:
        mms_core = _load_mms_core()
        commands = [
            mms_core._mms_upgrade_shell_command(include_clis=False),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("codex"),  # noqa: SLF001 - display only
            mms_core._cli_upgrade_shell_command("claude"),  # noqa: SLF001 - display only
        ]
        return [item for item in commands if _safe_text(item)]
    except Exception:
        return [
            "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash -s -- --latest-tag",
            "npm install -g @openai/codex@latest",
            "npm install -g @anthropic-ai/claude-code@latest",
        ]


def _settings_gate_catalog(command_name: str = "mms") -> dict[str, dict[str, Any]]:
    command = _safe_text(command_name) or "mms"
    registry = f"{command} registry"
    webui = f"{command} config web"
    interactive = command
    account_writes = [
        "~/.config/mms/config.toml accounts/account.defaults",
        "~/.config/mms/accounts/** OAuth/account state",
        "可能涉及外部浏览器或 CLI login side effects",
    ]
    registry_writes = [
        "<MMS_CONFIG_ROOT>/registry/model-registry.sqlite",
        "<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json",
        "<MMS_CONFIG_ROOT>/generated/model-capabilities.approved.json",
    ]
    return {
        "guard_status": {
            "title": "Snapshot 快照状态 / accept",
            "risk_level": "medium",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status 查看 accepted/latest/pending snapshot 和 drift。",
                "只有确认当前 config drift 是你要保留的状态后，再手动运行 accept。",
                "WebUI 只展示 gate，不会替你接受 baseline。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "只点 guard_status 查看状态；不要运行 accept。",
        },
        "guard_accept_gate": {
            "title": "接受当前 Snapshot baseline",
            "risk_level": "high",
            "commands": [f"{command} guard status", f"{command} guard accept"],
            "manual_steps": [
                "先运行 status，确认 drift 来自你刚刚认可的配置变化。",
                "再运行 accept；这会把当前 snapshot 设为新的已确认 baseline。",
                "如果 drift 涉及 Claude account/proxy/home_dir，按 human-only 规则停下人工确认。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/snapshots/startup/latest.json", "<MMS_CONFIG_ROOT>/snapshots/startup/accepted.json", "<MMS_CONFIG_ROOT>/snapshots/startup/pending.json cleanup"],
            "safe_alternative": "保留 pending drift，只在 WebUI/CLI 里查看 status。",
        },
        "connect_official_gate": {
            "title": "OAuth / AGY 官方登录已下线",
            "risk_level": "low",
            "commands": [],
            "manual_steps": [
                "不再新增 WebUI OAuth / AGY 官方登录能力。",
                "已有 account 只保留默认值、priority、note 等兼容配置。",
                "新配置走 API Key provider，并通过保存预览写入。",
            ],
            "writes": [],
            "safe_alternative": "网关 API Key 通道使用 WebUI Add provider + 保存预览，不走 OAuth。",
        },
        "migrate_config_gate": {
            "title": "迁移旧配置 / v2 promotion 人工确认",
            "risk_level": "high",
            "commands": [f"{command} migrate config-v2 --json", f"{command} config migrate", f"{command} config root --json"],
            "manual_steps": [
                "先用只读 migration/promotion plan 看 preview root 与 stable root 的差异。",
                "确认 backup、目标 root、secret 处理和 human-only config 边界。",
                "只有人工确认后才运行实际迁移命令。",
            ],
            "writes": ["~/.config/mms/** stable config tree", "<MMS_CONFIG_ROOT>/registry/** preview DB/root artifacts", "config backups / audit logs"],
            "safe_alternative": "在 WebUI 保存页生成 preview plan，不直接迁移 stable。",
        },
        "family_autosort_gate": {
            "title": "按速度统计批量排序 family priority",
            "risk_level": "medium",
            "commands": [webui, interactive],
            "manual_steps": [
                "先在 WebUI 通道页查看/编辑 provider priority 与 family_priority_overrides。",
                "生成保存预览，确认每个 family 的排序变化。",
                "如要使用 TUI speed stats autosort，只能人工打开主 TUI 并逐项确认，不从 WebUI 自动批量改。",
            ],
            "writes": ["provider.priority", "provider.family_priority_overrides", "account.family_priority_overrides"],
            "safe_alternative": "WebUI 已提供手工 family priority 草稿 + diff review，替代自动批量排序。",
        },
        "account_login_gate": {
            "title": "账号登录",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.login <account-id>", f"{command} config account.status <account-id>"],
            "manual_steps": [
                "确认 account id 不是 Claude human-only account。",
                "手动执行 login，并完成外部 OAuth/CLI 交互。",
                "回到 WebUI 刷新 accounts report，检查默认账号和状态。",
            ],
            "writes": account_writes,
            "safe_alternative": "非 OAuth API Key 通道使用 WebUI provider credentials draft。",
        },
        "account_remove_gate": {
            "title": "删除账号",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.status <account-id>", f"{command} config account.remove <account-id>"],
            "manual_steps": [
                "确认该 account 没有作为默认账号或专属 key 绑定使用。",
                "Claude account/remove 必须停在 human-only gate。",
                "手动 remove 后回 WebUI accounts report 和保存预览核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<account-id>/**"],
            "safe_alternative": "先在 WebUI 将非 Claude account disabled/default 草稿调整并 review。",
        },
        "account_rename_gate": {
            "title": "重命名账号 / 移动账号 home",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.rename <old-account-id> <new-account-id>"],
            "manual_steps": [
                "先确认 old/new account id、默认账号引用和账号 home_dir。",
                "该动作可能移动 account home 目录并重写 usage/defaults；必须人工确认备份和目标目录不存在。",
                "完成后回 WebUI accounts report，核对 id/default/usage 是否一致。",
            ],
            "writes": ["~/.config/mms/config.toml accounts/account.defaults", "~/.config/mms/accounts/<old-id>/** -> <new-id>/**", "~/.config/mms/usage.json account usage keys"],
            "safe_alternative": "WebUI 已支持非 Claude account 显示名、启用状态、priority、family、timezone、note 的草稿/保存预览。",
        },
        "account_network_gate": {
            "title": "编辑账号 proxy / no_proxy / home_dir",
            "risk_level": "high",
            "commands": [f"{command} config account.list", f"{command} config account.edit <account-id>"],
            "manual_steps": [
                "不要在 WebUI 中回显或复制 proxy/no_proxy 明文；这些字段可能包含凭据或影响 OAuth/Claude 网络边界。",
                "Claude account config 是 human-only；任何 Claude proxy/home_dir/no_proxy 变化都必须停止并人工确认。",
                "非 Claude 账号如需改 proxy/no_proxy，请在终端人工运行 account.edit 并随后回 WebUI 做只读核对。",
            ],
            "writes": ["~/.config/mms/config.toml accounts[*].proxy/no_proxy/home_dir/timezone", "~/.config/mms/accounts/** account state can be affected by launch/login"],
            "safe_alternative": "WebUI 只显示 proxy/no_proxy 是否已配置；非敏感 timezone/note 可在账号表中走保存预览。",
        },
        "provider_network_gate": {
            "title": "编辑通道 proxy / no_proxy",
            "risk_level": "high",
            "commands": [f"{command} config provider.edit <provider-id>"],
            "manual_steps": [
                "proxy/no_proxy 可能包含凭据，也可能改变 Claude/provider 的网络隔离策略；WebUI 不回显明文。",
                "修改前先确认目标 provider、expected proxy、no_proxy 不会命中 Claude/OpenAI 域名造成直连泄漏。",
                "人工执行 provider.edit 后回到 WebUI 生成保存预览或 provider_usage_summary 核对非敏感字段。",
            ],
            "writes": ["~/.config/mms/config.toml providers[*].proxy/no_proxy", "provider network policy for future launches"],
            "safe_alternative": "WebUI 支持通道 URL/API Key/protocol/CLI/timezone/note/Claude 1M 的草稿/保存预览；只把 proxy/no_proxy 留给人工确认。",
        },
        "refresh_due_sources_gate": {
            "title": "刷新到期 registry source",
            "risk_level": "medium",
            "commands": [f"{registry} check-staleness", f"{registry} refresh-sources --if-due"],
            "manual_steps": [
                "先运行 check-staleness，只读确认哪些 source 到期。",
                "确认可写 preview registry root 后，再运行 --if-due refresh。",
                "刷新后运行 source-status/preview-doctor 核对。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "WebUI 点击过期检查报告只读查看。",
        },
        "scheduled_refresh_gate": {
            "title": "定时 registry 刷新",
            "risk_level": "medium",
            "commands": [f"{registry} scheduled-refresh --dry-run --no-network", f"{registry} scheduled-refresh --no-network", f"{registry} scheduled-refresh"],
            "manual_steps": [
                "先 dry-run/no-network，确认 due state 和不会访问外网。",
                "需要联网 OpenRouter refresh 时，由人工明确运行不带 --no-network 的命令。",
                "执行后查看 scheduled output、source-status 和 preview doctor。",
            ],
            "writes": registry_writes,
            "safe_alternative": "保留 WebUI 只读报告；不要执行联网/写入刷新。",
        },
        "refresh_sources_gate": {
            "title": "刷新全部 registry source",
            "risk_level": "high",
            "commands": [f"{registry} refresh-sources", f"{registry} source-status --json"],
            "manual_steps": [
                "确认当前 root 是预期 preview/stable root。",
                "运行 refresh-sources 前先确认 reference snapshots 和写入范围。",
                "完成后用 source-status/preview-doctor 验证。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "只运行 check-staleness 或 source-status。",
        },
        "fetch_openrouter_gate": {
            "title": "拉取 OpenRouter catalog",
            "risk_level": "medium",
            "commands": [f"{registry} fetch-openrouter-catalog", f"{registry} fetch-openrouter-catalog --from-file <models.json>"],
            "manual_steps": [
                "联网拉取前确认网络可用和 OpenRouter source 仍可信。",
                "如已有离线 catalog，优先使用 --from-file。",
                "完成后再运行 diff-openrouter-catalog 查看候选变化。",
            ],
            "writes": registry_writes[:1],
            "safe_alternative": "用 --from-file 导入人工下载的 catalog，避免 WebUI 自动联网。",
        },
        "diff_openrouter_gate": {
            "title": "对比 OpenRouter candidate 变化",
            "risk_level": "medium",
            "commands": [f"{registry} diff-openrouter-catalog --limit 50", f"{registry} diff-openrouter-catalog --no-store --limit 50"],
            "manual_steps": [
                "先用 --no-store 只读查看 diff。",
                "确认 candidate changes 合理后，再允许 store candidate_change rows。",
                "后续 publish 前必须走 approved bundle 验证。",
            ],
            "writes": ["<MMS_CONFIG_ROOT>/registry/model-registry.sqlite candidate_change rows"],
            "safe_alternative": "只运行 --no-store diff。",
        },
        "publish_approved_gate": {
            "title": "发布已批准 Bundle",
            "risk_level": "high",
            "commands": [f"{registry} publish-approved", f"{registry} verify --json"],
            "manual_steps": [
                "先确认 candidate/bundle revision 和 route shrink guard。",
                "人工运行 publish-approved 后立刻运行 verify。",
                "verify 未通过时不要继续把结果交给 launcher/runtime。",
            ],
            "writes": registry_writes[1:],
            "safe_alternative": "WebUI 保存页 preview apply 会在明确 confirm 后 publish/verify preview bundle。",
        },
        "verify_approved_gate": {
            "title": "验证已批准 Bundle",
            "risk_level": "low",
            "commands": [f"{registry} verify --json", f"{registry} consumer-bundle --json --no-strict-exit"],
            "manual_steps": [
                "运行 verify 检查 latest-approved manifest/hash。",
                "再运行 consumer-bundle 查看下游可读状态。",
                "此 gate 保留 CLI/manual path，WebUI 不替你执行外部命令。",
            ],
            "writes": [],
            "safe_alternative": "WebUI 点击消费端 Bundle 报告读取当前状态。",
        },
        "rescue_create_demo_gate": {
            "title": "生成 demo rescue packet",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> Rescue -> 生成测试 rescue packet。",
                "确认写入 repo-local .mms/rescue demo artifacts。",
                "完成后在 WebUI 点击 rescue_events 查看 artifact path。",
            ],
            "writes": ["<repo>/.mms/rescue/**", "~/.config/mms/rescue/index.jsonl metadata"],
            "safe_alternative": "WebUI 只读 rescue_events；不生成 demo artifact。",
        },
        "rescue_handover_gate": {
            "title": "生成 fallback 交接",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "先在 WebUI rescue_events 找到要处理的 rescue packet。",
                "打开主 TUI：Settings -> Rescue -> 选择 packet -> handover/manual_handover。",
                "确认 fallback model 和 artifact path 后再生成。",
            ],
            "writes": ["<repo>/.mms/rescue/latest-fallback-handover.json", "<repo>/.mms/rescue/latest-fallback-handover.md"],
            "safe_alternative": "WebUI 已支持 fallback/hot fallback 持久配置草稿，handover artifact 仍人工生成。",
        },
        "about_refresh_gate": {
            "title": "刷新版本检查",
            "risk_level": "medium",
            "commands": [interactive, webui],
            "manual_steps": [
                "打开主 TUI：Settings -> About -> 刷新版本检查。",
                "该动作可能访问 GitHub/npm 并更新本地 version cache。",
                "WebUI about report 默认只读 cached 状态，不自动联网刷新。",
            ],
            "writes": ["~/.config/mms/version.json update cache"],
            "safe_alternative": "WebUI 点击关于状态读取缓存版本状态。",
        },
        "about_upgrade_gate": {
            "title": "升级 MMS / Codex / Claude CLI",
            "risk_level": "critical",
            "commands": _about_upgrade_gate_commands(),
            "manual_steps": [
                "先看当前版本和 latest 版本，确认升级目标。",
                "手动复制并运行对应升级命令；这会联网并修改本机安装。",
                "升级后重新打开 WebUI，运行 summary/py_compile/smoke 确认入口可用。",
            ],
            "writes": ["MMS install location", "global npm packages for Codex/Claude CLI"],
            "safe_alternative": "只查看 about cached status，不执行升级。",
        },
        "provider_remove_gate": {
            "title": "删除通道 legacy 人工确认",
            "risk_level": "medium",
            "commands": [webui, f"{command} config provider.remove <provider-id>"],
            "manual_steps": [
                "WebUI 当前已提供 typed confirm 草稿删除；优先使用 WebUI 保存预览。",
                "CLI remove 属于 legacy mutating path，执行前先确认 provider 不再被默认/route/fallback 使用。",
            ],
            "writes": ["~/.config/mms/config.toml providers/provider.default", "credentials/model-policy related entries"],
            "safe_alternative": "WebUI typed confirm -> 生成保存预览 -> confirm save。",
        },
    }


def _settings_gate_report(action: str, *, write_policy: str = "human_gate", note: str = "", command_name: str = "mms") -> dict[str, Any]:
    mapping_rows = [item for item in _tui_webui_mapping() if item.get("api_action") == action]
    gate = _settings_gate_catalog(command_name).get(action, {})
    commands = [item for item in (gate.get("commands") or []) if _safe_text(item)]
    return {
        "ok": True,
        "schema": "mms.setup_web.settings_report.v1",
        "action": action,
        "title": gate.get("title") or action,
        "write_policy": write_policy,
        "status": "human_gate",
        "risk_level": gate.get("risk_level") or "high",
        "requires_human_confirmation": True,
        "blocked_auto_execute": True,
        "copyable": bool(commands),
        "commands": commands,
        "manual_steps": gate.get("manual_steps") or [],
        "writes": gate.get("writes") or [],
        "safe_alternative": gate.get("safe_alternative") or "",
        "note": note or "该 TUI 动作会触发 network/write/OAuth/global-config 风险；WebUI 当前只显示 gate，不会自动执行。",
        "mapping": mapping_rows,
    }


def _snapshot_guard_status_report(cfg: dict[str, Any], *, config_path: str = "", command_name: str = "mms") -> dict[str, Any]:
    mapping_rows = [item for item in _tui_webui_mapping() if item.get("api_action") == "guard_status"]
    try:
        mms_core = _load_mms_core()
        target_config_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001 - read-only status
        current_snapshot = mms_core._build_config_guard_snapshot(cfg if isinstance(cfg, dict) else {}, config_path=target_config_path)  # noqa: SLF001
        latest_path = mms_core._config_snapshot_path("startup", "latest.json", config_path=target_config_path)  # noqa: SLF001
        accepted_path = mms_core._config_snapshot_path("startup", "accepted.json", config_path=target_config_path)  # noqa: SLF001
        pending_path = mms_core._config_snapshot_path("startup", "pending.json", config_path=target_config_path)  # noqa: SLF001
        accepted_payload = mms_core._load_json_snapshot(accepted_path) or {}  # noqa: SLF001
        accepted_snapshot = accepted_payload.get("snapshot") if isinstance(accepted_payload, dict) else None
        diff_lines = mms_core._snapshot_diff_lines(accepted_snapshot, current_snapshot) if accepted_snapshot else []  # noqa: SLF001
        status_value = "missing" if not accepted_snapshot else ("drift" if diff_lines else "stable")
        report = {
            "status": status_value,
            "accepted_path": accepted_path,
            "latest_path": latest_path,
            "pending_path": pending_path if os.path.exists(pending_path) else "",
            "real_home": _safe_text(current_snapshot.get("real_home")),
            "config_path": _safe_text(current_snapshot.get("config_path")),
            "accounts": len(current_snapshot.get("accounts") or []),
            "providers": len(current_snapshot.get("providers") or []),
            "diff_count": len(diff_lines),
            "diff_preview": diff_lines[:20],
        }
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": "guard_status",
            "status": "report",
            "write_policy": "read_only_report",
            "commands": [f"{_safe_text(command_name) or 'mms'} guard status"],
            "report": _sanitize_for_output(report),
            "mapping": mapping_rows,
            "note": "只读 Snapshot 快照状态；accept baseline 仍在 guard_accept_gate 人工确认。",
        }
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.setup_web.settings_report.v1",
            "action": "guard_status",
            "status": "report",
            "write_policy": "read_only_report",
            "error": f"{type(exc).__name__}: {exc}",
            "mapping": mapping_rows,
            "note": "读取 Snapshot 快照状态 失败；未执行 accept 或任何写入。",
        }


def build_settings_report(
    cfg: dict[str, Any],
    payload: dict[str, Any] | None = None,
    *,
    config_path: str = "",
    preferences_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    """Return one bounded settings report for the WebUI; mutating TUI actions stay 需要人工确认."""
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
            "note": "WebUI 支持已有非 Claude account 的 name/enabled/priority/family/timezone/Claude 1M/note/default 草稿预览；OAuth / AGY 新登录主流程已下线，remove/rename/home_dir/proxy 与 Claude account 仍 需要人工确认。",
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
            from mms_registry.cli import source_freshness

            report = source_freshness()
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "report": _sanitize_for_output(report)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "preview_doctor":
        config_root = _config_root_for_snapshot(config_path)
        try:
            from mms_registry.cli import preview_doctor

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
    if action == "verify_approved":
        config_root = _config_root_for_snapshot(config_path)
        try:
            from mms_registry.cli import verify_approved_bundle

            report = verify_approved_bundle(config_dir=config_root or None)
            return {
                "ok": True,
                "schema": "mms.setup_web.settings_report.v1",
                "action": action,
                "write_policy": "read_only_report",
                "status": "report",
                "report": _sanitize_for_output(report),
                "note": "只读验证 latest-approved manifest/hash；不会 publish、写入 bundle 或修改真实 config。",
            }
        except Exception as exc:
            return {
                "ok": False,
                "schema": "mms.setup_web.settings_report.v1",
                "action": action,
                "write_policy": "read_only_report",
                "status": "report",
                "error": f"{type(exc).__name__}: {exc}",
                "note": "只读验证 latest-approved manifest/hash 失败；WebUI 没有执行 publish/write。",
            }
    if action == "provider_usage_summary":
        requested_provider_id = _safe_text(payload.get("provider_id"))
        provider_items = [item for item in (snapshot.get("providers") or []) if isinstance(item, dict)]
        if requested_provider_id:
            provider_items = [item for item in provider_items if _safe_text(item.get("id")) == requested_provider_id]
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "read_only",
            "provider_id": requested_provider_id,
            "scope": "provider" if requested_provider_id else "all_providers",
            "providers": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "usage": item.get("usage") or {},
                    "model_count": item.get("model_count"),
                    "enabled": item.get("enabled"),
                    "role": item.get("role"),
                    "priority": item.get("priority"),
                    "models": [
                        {
                            "id": row.get("id"),
                            "source": row.get("source"),
                            "visible": row.get("visible", True),
                            "favorite": row.get("favorite", False),
                        }
                        for row in (item.get("models") or [])
                        if isinstance(row, dict) and row.get("id")
                    ],
                    "usage_rows": item.get("usage_rows") or [],
                }
                for item in provider_items
            ],
        }
    if action == "connect_gateway_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "webui_section": "channel",
            "provider_count": len(snapshot.get("providers") or []),
            "note": "TUI O 接入 -> 添加网关通道 已迁到 WebUI 的 Add provider / provider editor；保存前必须生成 diff preview。",
        }
    if action == "provider_channel_status":
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "write_policy": "draft_review_confirmed_save",
            "status": "native",
            "provider_default": snapshot.get("provider_default"),
            "providers": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "enabled": item.get("enabled"),
                    "role": item.get("role"),
                    "priority": item.get("priority"),
                    "family_priority_overrides": item.get("family_priority_overrides") or {},
                    "model_count": item.get("model_count"),
                }
                for item in (snapshot.get("providers") or [])
                if isinstance(item, dict)
            ],
            "note": "WebUI 暴露持久 provider default/priority/role；TUI 单次启动 provider override 仍属于 launcher 选择面。",
        }
    if action == "guard_status":
        return _snapshot_guard_status_report(snapshot, config_path=config_path, command_name=command_name)
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
            from mms_runtime.rescue import list_rescue_events

            events = list_rescue_events(repo_root=os.getcwd(), limit=20)
            return {"ok": True, "schema": "mms.setup_web.settings_report.v1", "action": action, "write_policy": "read_only", "events": _sanitize_for_output(events)}
        except Exception as exc:
            return {"ok": False, "schema": "mms.setup_web.settings_report.v1", "action": action, "error": f"{type(exc).__name__}: {exc}"}
    if action == "connect_official_gate":
        mapping_rows = [item for item in mapping if item.get("api_action") == action]
        return {
            "ok": True,
            "schema": "mms.setup_web.settings_report.v1",
            "action": action,
            "title": "OAuth / AGY 官方登录已下线",
            "status": "deprecated",
            "risk_level": "low",
            "write_policy": "deprecated_read_only_compat",
            "blocked_auto_execute": True,
            "requires_human_confirmation": False,
            "copyable": False,
            "commands": [],
            "manual_steps": [
                "WebUI 不再提供新的 OAuth / AGY 官方登录入口。",
                "新通道请在「通道配置」里维护 Base URL、API Key、protocol 和模型清单。",
                "已存在的 account 只保留默认值、priority、note 等兼容配置；login/remove/Claude account 仍按人工边界处理。",
            ],
            "writes": [],
            "safe_alternative": "使用 API Key provider：通道配置 -> 新增通道 -> 生成保存预览 -> 写入。",
            "note": "OAuth/AGY 官方登录已从 WebUI 主流程下线；这里只解释兼容边界，不提供登录命令。",
            "mapping": mapping_rows,
        }
    gate_actions = {
        "guard_accept_gate": ("manual_cli_human_gate", "Snapshot Guard accept 会更新 guard baseline；WebUI 不自动执行。"),
        "provider_remove_gate": ("planned_human_confirm", "删除 provider 需要 typed confirm + diff review；本 slice 只标出缺口。"),
        "provider_network_gate": ("network_policy_human_gate", "proxy/no_proxy 可能包含凭据并影响网络隔离；WebUI 不回显或自动写入。"),
        "migrate_config_gate": ("manual_cli_human_gate", "配置迁移会读写真实配置树；必须人工确认迁移源、目标和备份。"),
        "family_autosort_gate": ("speed_stats_write_human_gate", "用于按测速 / 使用统计重排 priority 与 family_priority_overrides；会批量影响路由优先级，所以 WebUI 只显示人工确认说明。"),
        "account_login_gate": ("manual_login_only", "OAuth login 会写外部账号状态；WebUI 当前不触发。"),
        "account_remove_gate": ("manual_remove_only", "删除 account 可能删除账号目录/登录状态；WebUI 当前不触发。"),
        "account_rename_gate": ("account_home_human_gate", "账号重命名可能移动 home_dir 并改 usage/defaults；WebUI 当前不自动执行。"),
        "account_network_gate": ("account_network_human_gate", "账号 proxy/no_proxy/home_dir 可能涉及 OAuth/Claude protected state；WebUI 不回显或自动写入。"),
        "refresh_due_sources_gate": ("network_write_human_gate", "刷新 registry source 可能触发 network/write；当前保持 人工确认。"),
        "scheduled_refresh_gate": ("network_human_gate", "scheduled refresh 需要单独确认执行模式；当前保持 人工确认。"),
        "refresh_sources_gate": ("network_write_human_gate", "刷新全部 sources 是 network/write 动作；当前保持 人工确认。"),
        "fetch_openrouter_gate": ("network_human_gate", "Fetch OpenRouter Catalog 需要联网；当前保持 人工确认。"),
        "diff_openrouter_gate": ("network_human_gate", "OpenRouter diff 可能依赖外部 catalog；当前保持 人工确认。"),
        "publish_approved_gate": ("write_human_gate", "发布 approved bundle 是写入动作；WebUI 只允许通过保存/发布审计流执行。"),
        "rescue_create_demo_gate": ("local_artifact_human_gate", "生成 demo rescue packet 会写本地 artifact；当前不自动执行。"),
        "rescue_handover_gate": ("planned_human_confirm", "fallback handover 写 artifact；后续需要 WebUI confirm flow。"),
        "about_refresh_gate": ("network_human_gate", "刷新版本检查可能联网；当前不自动执行。"),
        "about_upgrade_gate": ("manual_cli_human_gate", "升级 MMS/Codex/Claude CLI 是外部写入/安装动作；必须 human 手动执行。"),
    }
    if action in gate_actions:
        write_policy, note = gate_actions[action]
        return _settings_gate_report(action, write_policy=write_policy, note=note, command_name=command_name)
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
            "verify_approved",
            "provider_usage_summary",
            "connect_gateway_status",
            "connect_official_gate",
            "provider_channel_status",
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
    .module-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 9px;
      margin: -6px 0 18px;
    }
    .module-report {
      margin-top: 14px;
    }
    .model-inventory-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .inventory-tile {
      border: 1.5px solid var(--border);
      background:
        radial-gradient(circle at 100% 0, color-mix(in oklch, var(--accent) 9%, transparent), transparent 42%),
        var(--bg);
      border-radius: var(--radius);
      padding: 12px;
      min-height: 82px;
    }
    .inventory-tile span {
      display: block;
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .inventory-tile strong {
      display: block;
      margin-top: 8px;
      font-family: var(--font-mono);
      font-size: 28px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
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
    .entry-audit {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      background: color-mix(in oklch, var(--fg) 22%, var(--border));
      border: 1px solid color-mix(in oklch, var(--fg) 22%, var(--border));
    }
    .entry-audit-item {
      background: var(--surface);
      padding: 12px;
      min-height: 98px;
    }
    .entry-audit-item b {
      display: block;
      font-family: var(--font-mono);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .entry-audit-item small {
      display: block;
      color: var(--muted);
      line-height: 1.45;
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
    .acceptance-panel {
      border: 1.5px solid color-mix(in oklch, var(--accent) 35%, var(--border));
      background:
        linear-gradient(135deg, color-mix(in oklch, var(--accent) 9%, transparent), transparent 38%),
        color-mix(in oklch, var(--surface) 92%, var(--accent-soft));
      border-radius: var(--radius);
      padding: 14px;
      margin-bottom: 14px;
    }
    .acceptance-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      margin-bottom: 10px;
    }
    .acceptance-head h4 {
      font-size: 18px;
      line-height: 1.05;
      letter-spacing: -.03em;
      text-transform: uppercase;
    }
    .acceptance-progress {
      font-family: var(--font-mono);
      font-size: 24px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      color: var(--accent);
      white-space: nowrap;
    }
    .mapping-check {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      white-space: nowrap;
    }
    .mapping-check input {
      width: auto;
      accent-color: var(--accent);
      cursor: pointer;
    }
    .check-evidence {
      font-family: var(--font-mono);
      font-size: 11px;
      color: color-mix(in oklch, var(--fg) 72%, var(--muted));
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
    .gate-report {
      white-space: normal;
      font-family: var(--font-body);
      display: grid;
      gap: 14px;
    }
    .gate-plate {
      border: 1.5px solid color-mix(in oklch, var(--danger) 38%, var(--border));
      background:
        radial-gradient(circle at 0 0, color-mix(in oklch, var(--danger) 14%, transparent), transparent 34%),
        color-mix(in oklch, var(--surface) 92%, var(--danger-soft));
      border-radius: var(--radius);
      padding: 14px;
    }
    .gate-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      border-bottom: 1px solid color-mix(in oklch, var(--danger) 28%, var(--border));
      padding-bottom: 10px;
      margin-bottom: 10px;
    }
    .gate-head h4 {
      font-size: clamp(18px, 3vw, 28px);
      line-height: 1;
      letter-spacing: -.04em;
      text-transform: uppercase;
    }
    .gate-head p {
      margin-top: 6px;
      max-width: 740px;
      color: var(--muted);
    }
    .gate-risk {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: var(--danger);
      border: 1px solid var(--danger);
      padding: 6px 8px;
      white-space: nowrap;
    }
    .gate-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .gate-box {
      border: 1px solid var(--border);
      background: color-mix(in oklch, var(--bg) 72%, var(--surface));
      border-radius: var(--radius);
      padding: 12px;
      min-width: 0;
    }
    .gate-box h5 {
      margin: 0 0 8px;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .gate-list {
      margin: 0;
      padding-left: 18px;
      color: color-mix(in oklch, var(--fg) 78%, var(--muted));
    }
    .gate-list li { margin: 5px 0; }
    .gate-command-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      margin: 7px 0;
      padding: 8px;
      border: 1px solid color-mix(in oklch, var(--fg) 16%, var(--border));
      background: var(--surface);
      border-radius: 8px;
    }
    .gate-command-row code {
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.45;
      word-break: break-word;
    }
    .copy-gate-command {
      border-radius: 0;
      padding: 6px 9px;
      font-family: var(--font-mono);
      font-size: 10px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .gate-raw summary {
      cursor: pointer;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      margin-top: 8px;
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
    .span3 { grid-column: span 3; }
    .span4 { grid-column: span 4; }
    .span5 { grid-column: span 5; }
    .span6 { grid-column: span 6; }
    .span7 { grid-column: span 7; }
    .span8 { grid-column: span 8; }
    .span9 { grid-column: span 9; }
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

    .provider-editor-shell {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .provider-form-tabs {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 5px;
      padding: 5px;
      border: 1.5px solid var(--border);
      border-radius: 18px;
      background:
        radial-gradient(circle at 8% 0%, color-mix(in oklch, var(--accent) 10%, transparent) 0, transparent 30%),
        color-mix(in oklch, var(--bg) 82%, var(--surface));
    }
    .provider-form-tab {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      min-height: 38px;
      background: transparent;
      color: var(--muted);
      border: 1px solid transparent;
      box-shadow: none;
      padding: 7px 10px;
      border-radius: 13px;
      font-size: 12.5px;
      font-weight: 700;
      line-height: 1.2;
    }
    .provider-form-tab .muted { display: none; }
    .provider-form-tab:hover {
      color: var(--fg);
      background: var(--surface);
      border-color: var(--border);
    }
    .provider-form-tab.active {
      color: var(--surface);
      background: var(--fg);
      border-color: var(--fg);
      box-shadow: 0 8px 20px rgba(15, 23, 42, .12);
    }
    .provider-form-tab.active .muted { color: rgba(255,255,255,.72); }
    .provider-form-panel { display: none; }
    .provider-form-panel.active {
      display: block;
      animation: fadeIn .18s ease both;
    }
    .provider-advanced {
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      background: var(--bg);
    }
    .provider-advanced summary {
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-weight: 700;
      color: var(--fg);
      list-style-position: outside;
    }
    .provider-advanced summary::marker { color: var(--muted); }
    .provider-advanced[open] { border-color: color-mix(in oklch, var(--accent) 35%, var(--border)); }
    .provider-action-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 10px;
    }
    .explain-card {
      display: flex;
      flex-direction: column;
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 13px;
      box-shadow: var(--shadow-sm);
      min-height: 170px;
    }
    .explain-card h4 {
      margin-bottom: 6px;
      font-size: 14px;
      line-height: 1.35;
    }
    .explain-card p {
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.55;
      white-space: normal;
      margin-bottom: 10px;
    }
    .explain-card button {
      align-self: flex-start;
      margin-top: auto;
      padding: 7px 12px;
      font-size: 12.5px;
      border-radius: 13px;
    }
    .provider-editor-actions {
      border-top: 1px solid var(--border);
      padding-top: 14px;
      margin-top: 0;
    }
    .result .usage-report,
    .result .account-report {
      font-family: var(--font-body);
      white-space: normal;
      font-size: 13px;
      line-height: 1.55;
    }
    .result .usage-report h4,
    .result .account-report h4 {
      font-size: 16px;
      margin-bottom: 6px;
    }
    .result .usage-report p,
    .result .account-report p { color: var(--muted); }
    .result .usage-report table,
    .result .account-report table {
      font-family: var(--font-body);
      min-width: 760px;
    }
    .result .usage-report .table-wrap,
    .result .account-report .table-wrap { margin-top: 10px; }
    .usage-report .chips {
      gap: 5px;
      margin: 8px 0 12px;
    }
    .usage-report .chip {
      padding: 4px 9px;
      font-size: 11.5px;
    }
    .result .usage-report table.usage-model-table {
      min-width: 0;
      table-layout: fixed;
      font-size: 12.5px;
    }
    .usage-model-table th,
    .usage-model-table td {
      padding: 8px 10px;
      vertical-align: middle;
    }
    .usage-model-table th:nth-child(1) { width: 36%; }
    .usage-model-table th:nth-child(2) { width: 16%; }
    .usage-model-table th:nth-child(3) { width: 12%; }
    .usage-model-table th:nth-child(4) { width: 11%; }
    .usage-model-table th:nth-child(5) { width: 11%; }
    .usage-model-table th:nth-child(6) { width: 14%; }
    .usage-model-table td:first-child {
      font-family: var(--font-mono);
      word-break: break-word;
    }
    .usage-detail {
      margin-top: 12px;
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      background: var(--bg);
      padding: 11px 12px;
    }
    .usage-detail summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--fg);
      user-select: none;
    }
    .usage-detail summary::marker { color: var(--muted); }
    .usage-detail .table-wrap { margin-top: 10px; }

    .settings-console {
      display: grid;
      gap: 14px;
    }
    .settings-hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      border: 1.5px solid color-mix(in oklch, var(--fg) 18%, var(--border));
      border-radius: var(--radius-xl);
      padding: 18px;
      background:
        radial-gradient(circle at 0 0, color-mix(in oklch, var(--accent) 14%, transparent), transparent 34%),
        linear-gradient(135deg, color-mix(in oklch, var(--surface) 84%, var(--bg)), var(--surface));
      box-shadow: var(--shadow-sm);
    }
    .settings-hero h3 {
      font-size: clamp(22px, 3.2vw, 36px);
      letter-spacing: -.035em;
      line-height: 1.05;
      margin-bottom: 8px;
    }
    .settings-hero p {
      color: color-mix(in oklch, var(--fg) 70%, var(--muted));
      max-width: 760px;
    }
    .settings-hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .settings-tabs {
      display: flex;
      gap: 6px;
      padding: 6px;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: color-mix(in oklch, var(--bg) 70%, var(--surface));
      overflow-x: auto;
      scrollbar-width: thin;
    }
    .settings-tab {
      flex: 1 0 150px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 1px solid transparent;
      border-radius: var(--radius);
      background: transparent;
      color: var(--muted);
      text-align: left;
      box-shadow: none;
      padding: 8px 10px;
      min-height: 42px;
      white-space: nowrap;
    }
    .settings-tab strong,
    .settings-tab span {
      display: inline;
      white-space: nowrap;
    }
    .settings-tab strong {
      color: inherit;
      font-size: 13px;
      line-height: 1;
    }
    .settings-tab span {
      color: color-mix(in oklch, var(--muted) 84%, var(--fg));
      font-size: 11px;
      line-height: 1;
    }
    .settings-tab:hover {
      background: var(--surface);
      border-color: var(--border);
      color: var(--fg);
    }
    .settings-tab.active {
      background: var(--fg);
      border-color: var(--fg);
      color: var(--surface);
    }
    .settings-tab.active span { color: rgba(255,255,255,.74); }
    .settings-tab-panel { display: none; }
    .settings-tab-panel.active {
      display: block;
      animation: fadeIn .18s ease both;
    }
    .settings-panel-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
    }
    .setting-edit-card {
      border: 1.5px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      padding: 15px;
      box-shadow: var(--shadow-sm);
    }
    .setting-edit-card h3 {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 7px;
    }
    .settings-next-step {
      border: 1.5px dashed color-mix(in oklch, var(--accent) 40%, var(--border));
      background: color-mix(in oklch, var(--accent) 8%, transparent);
      border-radius: var(--radius-lg);
      padding: 14px;
    }
    .account-config-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .account-config-card {
      border: 1.5px solid var(--border);
      border-radius: var(--radius-lg);
      background:
        linear-gradient(180deg, color-mix(in oklch, var(--surface) 92%, var(--bg)), var(--surface));
      padding: 14px;
      box-shadow: var(--shadow-sm);
    }
    .account-config-card.locked {
      border-style: dashed;
      background: color-mix(in oklch, var(--bg) 74%, var(--surface));
    }
    .account-card-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      margin-bottom: 12px;
    }
    .account-card-head h4 {
      font-size: 16px;
      margin-bottom: 4px;
    }
    .account-fields {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .account-fields label { margin-top: 0; }
    .account-advanced {
      margin-top: 12px;
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      background: color-mix(in oklch, var(--bg) 70%, transparent);
      padding: 10px 12px;
    }
    .account-advanced summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--fg);
    }
    .account-advanced summary::marker { color: var(--muted); }
    .settings-compat-note {
      border-left: 3px solid var(--warn);
      background: color-mix(in oklch, var(--warn) 10%, transparent);
      padding: 10px 12px;
      border-radius: var(--radius);
      color: color-mix(in oklch, var(--fg) 76%, var(--muted));
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
    .chip.off {
      color: var(--muted);
      background: color-mix(in oklch, var(--bg) 72%, var(--surface));
      border-color: color-mix(in oklch, var(--border) 82%, var(--muted));
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
      .span3, .span4, .span5, .span6, .span7, .span8, .span9, .span12 { grid-column: span 12; }
      .provider-form-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .provider-form-tab { justify-content: flex-start; }
      .oc-summary, .model-inventory-summary, .settings-tabs, .account-config-grid { grid-template-columns: 1fr 1fr; }
      .settings-hero, .settings-command-head, .settings-metrics, .settings-route, .entry-audit, .mapping-head, .gate-head, .gate-grid, .acceptance-head { grid-template-columns: 1fr; }
      .settings-hero-actions { justify-content: flex-start; }
      .filterbar.compact { justify-content: flex-start; }
      .settings-command h3 { font-size: clamp(26px, 11vw, 44px); }
      .settings-stamp { white-space: normal; }
      .panel { padding: 20px; }
    }
    @media (max-width: 680px) {
      .settings-tabs, .account-config-grid, .account-fields { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<header>
  <div>
    <h1>MMS 配置中心</h1>
    <p class="lead">这里按模块直接配置和测试：通道里改 provider 与模型清单，模型测试里跑 smoke，设置里管账号、语言和 Guard。保存前先预览；stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
  </div>
  <div class="statusbar" id="statusbar"><span class="pill warn">加载中</span></div>
</header>
<div class="shell">
  <aside class="side" id="nav"></aside>
  <main class="content">
    <section class="panel" data-section="source">
      <h2>配置源状态</h2>
      <p>这是只读体检区：先确认当前 WebUI 正在读写哪个 config root，再看 registry DB、legacy import 和 latest-approved bundle。想写预览 DB 时，这里必须显示 mms-next；如果显示 mms，就是 stable 配置。</p>
      <div class="module-actions">
        <button class="ghost" data-settings-action="model_source_status" data-report-target="sourceReport">配置源状态</button>
        <button class="ghost" data-settings-action="consumer_bundle_status" data-report-target="sourceReport">消费端 Bundle</button>
        <button class="ghost" data-settings-action="verify_approved" data-report-target="sourceReport">验证已批准 Bundle</button>
        <button class="ghost" data-settings-action="preview_doctor" data-report-target="sourceReport">预览诊断</button>
        <button class="ghost" data-settings-action="check_staleness" data-report-target="sourceReport">检查过期源</button>
        <button class="ghost" data-settings-action="refresh_due_sources_gate" data-report-target="sourceReport">刷新到期源确认</button>
        <button class="ghost" data-settings-action="publish_approved_gate" data-report-target="sourceReport">发布确认</button>
      </div>
      <div class="grid" id="sourceStatus"></div>
      <div class="result module-report" id="sourceReport">选择配置源动作查看只读报告或人工确认。</div>
    </section>


    <!-- 通道配置 -->
    <section class="panel" data-section="channel">
      <h2>通道配置</h2>
      <p>先建通道：基础信息、连接凭据、策略高级项和报告确认分在编辑器 Tab 中；Key 只会通过 POST 发送，不会回显。</p>
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
              <div class="model-inventory-summary" id="modelInventorySummary"></div>
              <div class="card">
                <div class="btns">
                  <button id="fetchModels">拉取当前通道模型</button>
                  <button id="testList" class="secondary">测试 /models</button>
                  <button id="openModelTest" class="ghost">打开模型测试</button>
                  <label class="check"><input id="autoStaleCleanupOnFetch" type="checkbox"><span>拉取后自动标记缺失旧 route 为待清理（本页临时）</span></label>
                  <input id="modelSearch" placeholder="搜索模型" style="max-width:260px">
                </div>
                <label style="margin-top:14px">手动补充当前通道模型（extra_models，逗号或换行分隔）</label>
                <textarea id="manualModels" placeholder="例如：gpt-5.5, qwen3.6-plus, K2.6"></textarea>
                <div class="btns">
                  <button id="addManualModels" class="secondary">添加到补充模型库</button>
                  <button id="clearHidden" class="ghost">取消当前通道全部隐藏</button>
                  <button id="restoreModelPatch" class="ghost">恢复默认模型补丁</button>
                  <button id="clearAllStaleHidden" class="ghost">移除全部通道未匹配隐藏规则</button>
                </div>
              </div>
              <div id="modelChips" class="card"></div>
              <div class="card" id="staleHiddenBox"></div>
              <div class="table-wrap"><table id="modelTable"></table></div>
              <div class="result module-report" id="modelConfigResult">模型配置动作结果会显示在这里。</div>
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
          <label>提示词 Prompt</label>
          <textarea id="testPrompt">只回复 pong</textarea>
          <div class="chips" id="testState"></div>
          <div class="btns">
            <button id="testListBtn" class="ghost">测试 /models</button>
            <button id="testModelBtn">Ping 模型</button>
            <button id="chatTestBtn" class="secondary">简单对话</button>
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
      <p>stable legacy 保存写入 config.toml 的 [rescue] / [vision_sidecar]；preview root 保存为 DB candidate 并随 latest-approved bundle 发布。已下线的负载均衡不在本轮 WebUI 迭代范围。</p>
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
          <div class="btns">
            <button class="ghost" data-settings-action="rescue_events" data-report-target="fallbackReport">查看 rescue 事件</button>
            <button class="ghost" data-settings-action="rescue_handover_gate" data-report-target="fallbackReport">交接确认</button>
            <button class="ghost" data-settings-action="rescue_create_demo_gate" data-report-target="fallbackReport">Demo packet 确认</button>
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
        <div class="card span12">
          <h3>Fallback 报告 / 人工确认</h3>
          <div class="result" id="fallbackReport">选择 fallback 动作查看结果。</div>
        </div>
      </div>
    </section>

    <!-- 运行默认值 -->
    <section class="panel" data-section="runtime">
      <h2>运行默认值</h2>
      <p>首选 CLI 会写入 presets.coding.cli；OpenCode profile 和 agent roster 会写入 [opencode]，launcher 会生成 session-local opencode.json；不会写全局 OpenCode 配置。</p>
      <div class="grid">
        <div class="card span5">
          <label>首选 CLI</label>
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
          <label>OpenCode 默认 profile</label>
          <select id="opencodeProfile">
            <option>agent</option>
            <option>omo</option>
            <option>raw</option>
          </select>
          <p class="muted">推荐：5.5 总控/终审，5.4 长跑 executor，国产模型用于 explore / bug-hunt / vision。逐 agent 固定模型放在 Advanced，不作为默认必填项。</p>
        </div>
        <div class="card span12">
          <h3>OpenCode Agent 名单</h3>
          <p class="muted">默认使用 Lite Pro 自动路线；这里管理哪些 agent 进入 session-local opencode.json。顺序表示 priority/fallback 顺序，不是 round-robin。</p>
          <div class="oc-summary" id="opencodeOverrideSummary"></div>
          <div class="oc-order-note">
            Lean 默认只开关键链路；Balanced 适合日常；Deep 再启用第二意见。国产模型适合 explore / bughunt / vision，不默认做最终裁决。
          </div>
          <details class="oc-advanced" id="opencodeAdvanced">
            <summary>高级：OpenCode 逐 Agent 名单</summary>
            <div class="filterbar" id="opencodeAgentFilters"></div>
            <div class="table-wrap"><table id="opencodeAgents"></table></div>
          </details>
        </div>
      </div>
    </section>

    <!-- Settings -->
    <section class="panel" data-section="settings">
      <h2>设置</h2>
      <p>这里是 WebUI 配置台：日常配置在当前页面改草稿，统一去保存页生成 diff / 审计摘要；TUI 后续只保留启动、应急和人工确认兜底。</p>
      <div class="settings-console">
        <div class="settings-hero">
          <div>
            <h3>把设置从 TUI 迁到可保存的 WebUI 表单</h3>
            <p>用户只需要记住启动命令；通道、模型、Fallback、Runtime 和账号默认值都在 WebUI 里完成配置，再通过保存预览写入。</p>
            <div id="settingsGapSummary" class="chips"></div>
          </div>
          <div class="settings-hero-actions">
            <button class="secondary" data-section-jump="save">生成保存预览</button>
            <button class="ghost" data-settings-action="accounts" data-report-target="settingsReport">刷新账号状态</button>
          </div>
        </div>

        <div class="settings-tabs" id="settingsTabs">
          <button class="settings-tab" data-settings-tab="basics"><strong>常用设置</strong><span>语言 / 保存入口</span></button>
          <button class="settings-tab" data-settings-tab="accounts"><strong>账号默认值</strong><span>default / priority / note</span></button>
          <button class="settings-tab" data-settings-tab="guard"><strong>安全确认</strong><span>Snapshot / 迁移</span></button>
          <button class="settings-tab" data-settings-tab="about"><strong>维护关于</strong><span>版本 / 升级 gate</span></button>
          <button class="settings-tab" data-settings-tab="audit"><strong>验收辅助</strong><span>折叠的 TUI 对照</span></button>
        </div>

        <div class="settings-tab-panel" data-settings-panel="basics">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span5">
              <h3>界面语言 <span class="tag">可配置</span></h3>
              <p class="muted">进入 WebUI 草稿，写入仍走保存 / 审计。</p>
              <label>ui.language</label>
              <select id="uiLanguage">
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
              <div class="btns">
                <button id="saveUiLanguage" class="ghost">暂存语言修改</button>
                <button class="ghost" data-settings-action="language_status" data-report-target="settingsReport">语言状态</button>
              </div>
            </div>
            <div class="setting-edit-card span4">
              <h3>配置入口 <span class="tag">主路径</span></h3>
              <p class="muted">通道 URL/API Key、模型补丁、Fallback、Runtime 默认值都在各自模块配置，不再回到 TUI 里点散落菜单。</p>
              <div class="btns">
                <button class="ghost" data-section-jump="channel">通道配置</button>
                <button class="ghost" data-section-jump="fallback">Fallback 设置</button>
                <button class="ghost" data-section-jump="runtime">运行默认值</button>
              </div>
            </div>
            <div class="settings-next-step span3">
              <h3>保存规则</h3>
              <p class="muted">修改后先生成保存预览；preview root 写 DB candidate + latest-approved bundle，stable root 走 backup + audit。</p>
              <button class="secondary" data-section-jump="save">去保存审计</button>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="accounts">
          <div class="setting-edit-card">
            <h3>CLI 账号默认值 <span class="tag">草稿预览</span></h3>
            <p class="muted">这里配置已有 account 的默认选择、启用状态、priority、timezone 和 note；Claude account 仍是 human-only。OAuth / AGY 官方登录不再作为 WebUI 主流程。</p>
            <div class="btns" id="accountModuleActions">
              <button class="ghost" data-settings-action="accounts" data-report-target="settingsReport">刷新账号状态</button>
              <button class="ghost" data-section-jump="save">保存账号草稿</button>
            </div>
            <div id="accountTable" class="account-config-grid"></div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="guard">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span6">
              <h3>启动快照守卫（Snapshot Guard）</h3>
              <p class="muted">状态是只读报告；接受 baseline 需要人工确认，不在 WebUI 自动执行。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="guard_status" data-report-target="settingsReport">快照状态</button>
                <button class="ghost" data-settings-action="guard_accept_gate" data-report-target="settingsReport">接受基线确认</button>
              </div>
            </div>
            <div class="setting-edit-card span6">
              <h3>迁移 / 网络边界</h3>
              <p class="muted">会触发真实配置、账号目录、proxy/no_proxy 或迁移写入的动作保持人工确认；WebUI 只显示影响面。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="migrate_config_gate" data-report-target="settingsReport">迁移确认</button>
                <button class="ghost" data-settings-action="account_network_gate" data-report-target="settingsReport">账号网络确认</button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="about">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span6">
              <h3>关于 / 版本</h3>
              <p class="muted">默认读取缓存状态；刷新版本检查和升级命令都需要人工确认。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="about" data-report-target="settingsReport">关于状态</button>
                <button class="ghost" data-settings-action="about_refresh_gate" data-report-target="settingsReport">刷新版本确认</button>
                <button class="ghost" data-settings-action="about_upgrade_gate" data-report-target="settingsReport">升级确认</button>
              </div>
            </div>
            <div class="settings-compat-note span6">
              <strong>OAuth 主流程已下线</strong>
              <p>AGY / OAuth 仅作为旧 account 兼容状态查看；新增可用通道请走 API Key provider。</p>
              <details class="account-advanced">
                <summary>查看已下线兼容说明</summary>
                <div class="btns">
                  <button class="ghost" data-settings-action="connect_official_gate" data-report-target="settingsReport">查看下线说明</button>
                </div>
              </details>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="audit">
          <details class="setting-edit-card" open>
            <summary>开发验收辅助，不作为用户设置入口</summary>
            <p class="muted">这些表只用于核对 TUI 功能迁移，不再占据设置主页面。</p>
            <div class="table-wrap"><table id="settingsCoverage"></table></div>
          </details>
          <details class="setting-edit-card mapping-card" id="mappingAuditDetails">
            <summary>验收辅助：TUI ↔ WebUI 对照表</summary>
            <div class="mapping-head">
              <div>
                <h3>TUI ↔ WebUI 对照表</h3>
                <p class="muted">功能入口应在通道、模型测试、配置源、Fallback、Runtime 或设置对应 tab 里；这里仅做验收证据。</p>
              </div>
              <div id="mappingFilters" class="filterbar compact"></div>
            </div>
            <div id="acceptancePanel" class="acceptance-panel"></div>
            <div class="table-wrap"><table id="tuiMappingTable"></table></div>
          </details>
        </div>

        <div class="setting-edit-card">
          <h3>报告 / 人工确认</h3>
          <div class="result" id="settingsReport">选择一个设置动作查看结果</div>
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
            <summary>高级 / 恢复：plan JSON 与 CLI fallback</summary>
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
          <h3 style="margin-bottom:8px">原始 diff / 审计详情</h3>
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
  ['source','配置源','root / DB / bundle'],
  ['channel','通道配置','URL / Key / 协议 / 模型'],
  ['test','模型测试','ping / chat smoke'],
  ['fallback','Fallback','rescue / vision'],
  ['runtime','运行默认值','首选 CLI / OpenCode'],
  ['settings','设置','配置台 / 账号 / 安全'],
  ['save','保存审计','diff / backup / audit'],
  ['refs','本地参考','配置契约 / 文档']
];
let state=null; let activeProvider=0; let activeProviderTab='config'; let activeProviderFormTab='basic'; let lastPlan=null; let opencodeAgentFilter="all"; let opencodeOnlyOverridden=false; let editingExtraModels=false; let settingsActiveTab='accounts'; let settingsMappingFilter='all'; let touchedProviders=new Set(); let staleCleanupProviders=new Set(); let lastGateCommands=[]; let checkedMappingRows=new Set();
const $=id=>document.getElementById(id);
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await res.json();if(!res.ok){data.ok=false;data.http_status=res.status;data.error=data.error||res.statusText}return data}
function current(){return state.providers[activeProvider]}
function touchProvider(id){if(id)touchedProviders.add(id)}
function setSection(id){document.querySelectorAll('[data-section]').forEach(el=>el.classList.toggle('hide',el.dataset.section!==id));document.querySelectorAll('.navbtn').forEach(el=>el.classList.toggle('active',el.dataset.id===id))}
function switchProviderTab(tab){activeProviderTab=tab;document.querySelectorAll('.provider-tabs .tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tabPanel===tab))}
function switchProviderFormTab(tab){activeProviderFormTab=tab||'basic';document.querySelectorAll('[data-provider-form-tab]').forEach(b=>b.classList.toggle('active',b.dataset.providerFormTab===activeProviderFormTab));document.querySelectorAll('[data-provider-form-panel]').forEach(p=>p.classList.toggle('active',p.dataset.providerFormPanel===activeProviderFormTab))}
function renderNav(){ $('nav').innerHTML=sections.map(([id,title,sub])=>`<button class="navbtn" data-id="${id}">${title}<small>${sub}</small></button>`).join(''); document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>setSection(b.dataset.id)); setSection('source') }
function versionBadge(){const v=state.version_info||{};return v.display||v.release||v.git_describe||v.git_commit||'dev'}
function rootAlias(root){return (root?.mode==='preview')?'mms-next':'mms'}
function renderStatus(){const providers=state.providers||[];const root=(state.model_source_status||{}).root||{};$('statusbar').innerHTML=`<span class="pill ok">版本：${escapeHtml(versionBadge())}</span><span class="pill">${state.mode}</span><span class="pill">root：${escapeHtml(rootAlias(root))} / ${escapeHtml(root.mode||'stable')}</span><span class="pill">通道 ${providers.length}</span><span class="pill">配置：${escapeHtml(state.paths.config||'-')}</span><span class="pill">策略模型：${state.policy_summary.model_count}</span>`}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function yn(value){return value?'是':'否'}
function enumLabel(value){const key=String(value??'');const map={ok:'正常',missing:'缺失',unknown:'未知',ready:'就绪','not ready':'未就绪',not_ready:'未就绪',auto:'自动',enable:'启用',disable:'禁用',enabled:'已启用',disabled:'已禁用',configured:'已配置',none:'未配置',imported:'已导入',not_imported:'未导入',blocked:'已拦截',high:'高风险',medium:'中风险',low:'低风险',critical:'严重',required:'必需',redacted:'已脱敏',included:'包含明文'};return map[key]||key||'-'}
function writePolicyLabel(policy){const key=String(policy||'');const map={native:'原生',report:'报告',draft_review:'草稿预览',human_gate:'人工确认',missing:'缺失',report_only:'只读报告',native_test_panel:'原生测试面板',planned:'待补齐',existing_save_flow:'现有保存流程',manual_cli_only:'仅人工 CLI',draft_review_confirmed_save:'草稿预览后确认保存',manual_login_only:'仅人工登录',mixed_draft_review_human_gate:'草稿预览 + 人工确认',manual_cli_human_gate:'人工 CLI 确认',read_only_report:'只读报告',draft_review_human_gate:'草稿预览 + 人工确认',save_flow_or_preview_publish:'保存流程 / preview 发布',audited_secret_write:'审计凭据写入',network_policy_human_gate:'网络策略人工确认',account_home_human_gate:'账号 home 人工确认',account_network_human_gate:'账号网络人工确认',manual_remove_only:'仅人工删除',read_only:'只读',mixed:'混合',save_preview:'保存预览',network_write_human_gate:'联网写入人工确认',network_human_gate:'联网人工确认',write_human_gate:'写入人工确认',local_artifact_human_gate:'本地产物人工确认',speed_stats_write_human_gate:'速度统计写入人工确认',deprecated_read_only_compat:'已下线，只读兼容',deprecated_no_webui_iteration:'已下线，不再迭代',claude_human_only_locked:'Claude 人工锁定',can_degrade_after_save_flow_verified:'保存链路验证后可弱化',can_degrade_after_route_guard_verified:'route guard 验证后可弱化',can_degrade_after_report_smoke:'报告 smoke 后可弱化',keep_emergency_only_for_login_remove_and_claude_human_gate:'仅保留登录/删除/Claude 人工确认应急',keep_emergency_only_for_remove_and_claude_human_gate:'仅保留删除/Claude 人工确认应急',read_only_reports_plus_existing_apply:'只读报告 + 现有 apply',can_degrade_report_display_after_webui_smoke:'WebUI smoke 后可弱化报告展示',keep_until_webui_double_confirm_flow_exists:'保留到 WebUI 双确认流程补齐',can_degrade_config_display_after_save_flow_verified:'保存链路验证后可弱化配置展示',keep_emergency_only_until_handover_write_flow_exists:'保留应急直到 handover 写入流程补齐',report_or_planned:'报告或待补齐',keep_small:'保留最小入口',module_native_controls_plus_reports:'模块原生控件 + 报告',keep_as_keyboard_launcher_until_webui_launch_surface_exists:'保留键盘 launcher，直到 WebUI 启动面补齐'};return map[key]||key||'-'}
function clickTargetsLabel(text){const map={open_section:'打开模块',settings_report:'查看报告',save_preview:'保存预览',human_gate_card:'人工确认卡片',missing_gap:'缺口'};return String(text||'-').split(' + ').map(x=>map[x]||x).join(' + ')}
function riskLabel(level){return enumLabel(level||'high')}
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
  const ready=bundle.runtime_ready===true?'就绪':bundle.runtime_ready===false?'未就绪':'未知';
  const bundleCommand=(root.command||state.command||'mms')==='mmf'?'mmf config bundle --json':'mms config bundle --json';
  const sourceRootAlias=rootAlias(root);
  const rootHint=root.mode==='preview'?'当前写入目标是 mms-next：保存页会走“写入预览 DB + 发布”。':'当前写入目标是 mms stable：不会写 mms-next；要试预览 DB 请用 mmf config web。';
  box.innerHTML=`<div class="card span6"><h3>当前配置 Root：${escapeHtml(sourceRootAlias)}</h3><p class="mono">${escapeHtml(root.config_root||status.config_root||consumer.config_root||'-')}</p><p class="muted">${escapeHtml(rootHint)}</p><p class="muted">${escapeHtml(status.headline||'-')}</p><span class="tag ${status.ready?'':'off'}">${enumLabel(status.status||'unknown')}</span><span class="tag">${escapeHtml(root.command||state.command||'-')}</span><span class="tag">${escapeHtml(root.mode||'-')}</span><span class="tag">${escapeHtml(root.root_source||'-')}</span></div><div class="card span6"><h3>Registry DB</h3><p class="mono">${escapeHtml(db.path||'-')}</p><span class="tag ${db.status==='ok'?'':'off'}">${escapeHtml(db.status||'missing')}</span><span class="tag">source ${counts.source_snapshot||0}</span><span class="tag">fact ${counts.model_fact||0}</span><span class="tag">routes ${counts.provider_route||0}</span></div><div class="card span6"><h3>Legacy 导入</h3><p class="muted">${escapeHtml(legacy.next_action||'-')}</p><span class="tag">通道 ${legacy.provider_count||0}</span><span class="tag ${legacy.conflict_count?'off':''}">冲突 ${legacy.conflict_count||0}</span><span class="tag ${candidates.status==='imported'?'':'off'}">候选 ${enumLabel(candidates.status||'not_imported')}</span><span class="tag">候选 route ${candidates.provider_route_count||0}</span></div><div class="card span6"><h3>已批准 Bundle</h3><p class="mono">${escapeHtml(bundle.manifest_path||'-')}</p><span class="tag ${okBundle==='ok'?'':'off'}">${enumLabel(bundle.status||'missing')}</span><span class="tag">已验证 ${yn(bundle.verified)}</span><span class="tag ${bundle.runtime_ready===true?'':'off'}">runtime ${ready}</span><span class="tag">缺 API Key ${bundle.router_missing_api_key_count||0}</span><span class="tag">文件 ${bundle.file_count||0}</span></div><div class="card span12"><h3>消费端 Bundle</h3><p class="mono">${escapeHtml(consumer.consumer_entrypoint||bundle.manifest_path||'-')}</p><p class="muted">${escapeHtml((rules.length?rules.join(' · '):'下游只读 latest-approved manifest；不读 SQLite；不混合不同 revision。'))}</p><span class="tag ${okConsumer==='ok'?'':'off'}">${enumLabel(consumer.status||'missing')}</span><span class="tag">已验证 ${yn(consumer.verified)}</span><span class="tag">bundle ${escapeHtml(revisions.bundle||'-')}</span><span class="tag">route ${escapeHtml(revisions.route||'-')}</span><span class="tag">policy ${escapeHtml(revisions.policy||'-')}</span><span class="tag">profile ${escapeHtml(revisions.profile||'-')}</span><span class="tag">文件 ${Object.keys(consumerFiles).length}</span><p class="muted">CLI: <span class="mono">${escapeHtml(bundleCommand)}</span></p></div><div class="card span12"><h3>晋级计划 / 人工确认</h3><p class="muted">stable backup + bundle comparison 是只读审查；apply 仍停在 人工确认。</p><span class="tag ${okPromotion==='ok'?'':'off'}">${escapeHtml(promotion.status||'not_ready')}</span><span class="tag">人工审查 ${promotion.ready_for_human_review?'就绪':'未就绪'}</span><span class="tag">apply ${promotion.apply_enabled?'已启用':'已禁用'}</span><span class="tag">stable ${escapeHtml(safety.stable_write_policy||'human_only')}</span><span class="tag">backup ${backup.requires_backup_before_apply?'必需':'未知'}</span><span class="tag">将创建 backup ${yn(backup.would_create_backup)}</span><span class="tag">Bundle 对比 ${escapeHtml(compare.comparison_status||'-')}</span><p class="muted">preview ${escapeHtml(comparePreview.bundle_revision||comparePreview.status||'-')} → stable ${escapeHtml(compareStable.bundle_revision||compareStable.status||'-')}</p></div><div class="card span12"><h3>4.0 发布就绪度</h3><p class="muted">只读 audit：证明自动检查已到 stable promotion 人工确认；release_complete 仍为 false。</p><span class="tag ${readinessOk==='ok'?'':'off'}">${escapeHtml(readiness.result||'NOT_READY')}</span><span class="tag">状态 ${enumLabel(readiness.status||'not_ready')}</span><span class="tag">发布完成 ${yn(readiness.release_complete)}</span><span class="tag">人工确认 ${readiness.ready_for_human_gate?'就绪':'未就绪'}</span><span class="tag">阻塞 ${readinessBlocked.length}</span><span class="tag">检查项 ${readinessReqs.filter(r=>r&&r.ok).length}/${readinessReqs.length}</span><span class="tag">阻塞原因 ${escapeHtml(readiness.completion_blocker||'-')}</span><p class="muted">阻塞检查项：${escapeHtml(readinessBlocked.length?readinessBlocked.join(', '):'-')}</p><p class="muted">下一步：<span class="mono">${escapeHtml(readinessNext.command||readinessNext.label||'-')}</span></p></div><div class="card span12"><details><summary>原始状态 JSON</summary><div class="result">${escapeHtml(JSON.stringify({model_source_status:status,consumer_bundle_status:consumer,config_v2_promotion_plan:promotion,config_v2_release_readiness:readiness},null,2))}</div></details></div>`
}
function providerEntries(){return (state.providers||[]).map((p,i)=>({p,i})).sort((a,b)=>{if(!!a.p.enabled!==!!b.p.enabled)return a.p.enabled?-1:1;return a.i-b.i})}
function renderProviderList(){const list=$('providerList');list.innerHTML=providerEntries().map(({p,i})=>{const keyTag=p.api_key?'<span class="tag">待保存 Key</span>':(p.has_api_key?'<span class="tag">已保存 Key</span>':'<span class="tag off">缺少 Key</span>');const usage=p.usage||{};return `<div class="provider-item ${i===activeProvider?'active':''}" data-i="${i}"><strong>${escapeHtml(p.name||p.id)}</strong><span class="muted mono">${escapeHtml(p.id)}</span><br>${p.enabled?'<span class="tag">已启用</span>':'<span class="tag off">已禁用</span>'}${keyTag}<span class="tag">模型 ${p.models?.length||0}</span><span class="tag">启动 ${usage.launches||0}</span></div>`}).join('');document.querySelectorAll('.provider-item').forEach(el=>el.onclick=()=>{activeProvider=Number(el.dataset.i);renderAll()})}
function renderProviders(){renderProviderList();renderProviderForm();renderTestSelectors();renderModelTable();}
function checks(name,values,allowed){values=values||[];return `<div class="checks">${allowed.map(v=>`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${values.includes(v)?'checked':''}><span>${v}</span></label>`).join('')}</div>`}
function checkedValues(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value)}

function modelFamilies(){return (state.model_families&&state.model_families.length?state.model_families:['Claude','GPT','Gemini','DeepSeek','Qwen','Kimi','Mimo','MiniMax','GLM'])}
function familyPriorityInputs(values={},name='familyPriority'){return `<div class="grid">${modelFamilies().map(f=>`<div class="span4"><label>${escapeHtml(f)}</label><input data-family-priority="${escapeHtml(name)}" data-family="${escapeHtml(f)}" type="number" min="1" value="${escapeHtml(values[f]||'')}" placeholder="继承"></div>`).join('')}</div>`}
function readFamilyPriorityInputs(name='familyPriority'){const result={};document.querySelectorAll(`[data-family-priority="${name}"]`).forEach(input=>{const family=input.dataset.family;const raw=String(input.value||'').trim();if(family&&raw){result[family]=Math.max(1,Number(raw)||100)}});return result}
function formatFamilyOverrides(values={}){return Object.entries(values||{}).map(([k,v])=>`${k}=${v}`).join(', ')}
function parseFamilyOverrides(text){const allowed=new Set(modelFamilies());const result={};String(text||'').split(/[\n,]/).map(x=>x.trim()).filter(Boolean).forEach(part=>{const [rawFamily,rawValue]=part.split(/[=:]/);const family=modelFamilies().find(f=>f.toLowerCase()===String(rawFamily||'').trim().toLowerCase());const value=Math.max(1,Number(String(rawValue||'').trim())||0);if(family&&allowed.has(family)&&value>0)result[family]=value});return result}
function modelSourceLabel(source){return {remote:'远端',fallback:'fallback',extra:'手动补充',hidden:'隐藏',derived_alias:'派生 alias',manual:'手动'}[source]||escapeHtml(source||'-')}
function renderProviderForm(){
  const p=current();
  if(!p){$('providerForm').innerHTML='<p>暂无通道</p>';return}
  const pendingKey=!!p.api_key;
  const keyPlaceholder=pendingKey?'已输入新 key，保存前会保留（不回显）':(p.has_api_key?'已保存；输入新 key 才会覆盖':'sk-...');
  const activeTabs=new Set(['basic','connect','advanced','reports']);
  if(!activeTabs.has(activeProviderFormTab))activeProviderFormTab='basic';
  const familyOverrides=p.family_priority_overrides||{};
  const familyOverrideCount=Object.keys(familyOverrides).filter(k=>familyOverrides[k]).length;
  const familySummary=familyOverrideCount?`已配置 ${familyOverrideCount} 个 family`:'默认继承 priority';
  const tabButton=(id,label,desc)=>`<button type="button" class="provider-form-tab ${activeProviderFormTab===id?'active':''}" data-provider-form-tab="${id}">${label}<span class="muted"> · ${desc}</span></button>`;
  const panelClass=id=>`provider-form-panel ${activeProviderFormTab===id?'active':''}`;
  $('providerForm').innerHTML=`<div class="provider-editor-shell">
    <div class="provider-form-tabs" role="tablist" aria-label="通道配置分组">
      ${tabButton('basic','基础信息','ID / 默认 / priority')}
      ${tabButton('connect','连接与协议','Base URL / Key')}
      ${tabButton('advanced','策略与高级','Claude / Family / 删除')}
      ${tabButton('reports','报告与确认','统计 / 人工确认')}
    </div>
    <div class="${panelClass('basic')}" data-provider-form-panel="basic">
      <div class="grid">
        <div class="span6"><label>内部 ID</label><input id="pId" value="${escapeHtml(p.id)}"></div>
        <div class="span6"><label>显示名</label><input id="pName" value="${escapeHtml(p.name)}"></div>
        <div class="span4"><label>状态</label><select id="pEnabled"><option value="true" ${p.enabled?'selected':''}>启用</option><option value="false" ${!p.enabled?'selected':''}>禁用</option></select></div>
        <div class="span4"><label>role（角色）</label><select id="pRole">${['primary','auto','fallback'].map(v=>`<option ${p.role===v?'selected':''}>${v}</option>`).join('')}</select></div>
        <div class="span4"><label>priority（优先级）</label><input id="pPriority" type="number" value="${escapeHtml(p.priority||100)}"></div>
        <div class="span12 check"><input id="pDefault" type="checkbox" ${state.provider_default===p.id?'checked':''}><span>设为默认通道</span></div>
        <div class="span12"><p class="muted">role 决定 primary / auto / fallback 层级；同一层级里 priority 数值越大越优先。这里只暂存草稿，真正写入仍走保存预览。</p></div>
      </div>
    </div>
    <div class="${panelClass('connect')}" data-provider-form-panel="connect">
      <div class="grid">
        <div class="span6"><label>OpenAI Base URL</label><input id="pOpenAI" value="${escapeHtml(p.openai_base_url||'')}" placeholder="https://.../v1"></div>
        <div class="span6"><label>Anthropic Base URL</label><input id="pAnthropic" value="${escapeHtml(p.anthropic_base_url||'')}" placeholder="https://.../v1 或 /anthropic"></div>
        <div class="span6"><label>API Key（留空不更新）</label><input id="pKey" type="password" placeholder="${escapeHtml(keyPlaceholder)}"></div>
        <div class="span6"><label>models_endpoint</label><input id="pModelsEndpoint" value="${escapeHtml(p.models_endpoint||'/models')}" placeholder="/models 或 manual"></div>
        <div class="span12"><label>protocols（协议）</label>${checks('pProtocols',p.protocols,['anthropic_messages','openai_chat_completions'])}</div>
        <div class="span12"><label>supported CLIs（支持的 CLI）</label>${checks('pClis',p.supported_clis,['claude','codex','opencode','pi','agy'])}</div>
        <div class="span12 check"><input id="pUpdateCreds" type="checkbox" ${p.update_credentials?'checked':''}><span>保存时更新凭据（stable 写 credentials.sh；preview 写 secret backend；需要填写 API Key）</span></div>
      </div>
    </div>
    <div class="${panelClass('advanced')}" data-provider-form-panel="advanced">
      <div class="grid">
        <div class="span4"><label>Claude 1M 策略</label><select id="pClaude1m">${['auto','enable','disable'].map(v=>`<option value="${v}" ${(p.claude_1m_mode||'auto')===v?'selected':''}>${enumLabel(v)}</option>`).join('')}</select></div>
        <div class="span4"><label>timezone（时区）</label><input id="pTimezone" value="${escapeHtml(p.timezone||'')}" placeholder="Asia/Singapore"></div>
        <div class="span4"><label>网络策略</label><p class="muted">proxy ${p.proxy_configured?'已配置':'未配置'} · no_proxy ${p.no_proxy_configured?'已配置':'未配置'} · 明文走人工确认</p><button type="button" class="ghost" data-settings-action="provider_network_gate" data-report-target="channelReport">查看网络配置人工确认</button></div>
        <div class="span12"><label>备注 note</label><input id="pNote" value="${escapeHtml(p.note||'')}" placeholder="用途、限制或路由说明"></div>
        <div class="span12">
          <details class="provider-advanced">
            <summary><span>Family 权重覆盖（不常用）</span><span class="tag off">${escapeHtml(familySummary)}</span></summary>
            <p class="muted">对应 TUI 模型页 +/- 对单个 family 写入的权重覆盖；平时保持折叠，留空表示继承全局 priority。</p>
            ${familyPriorityInputs(familyOverrides,'providerFamilyPriority')}
          </details>
        </div>
        <div class="span12 delete-zone"><label>删除通道确认</label><input id="pDeleteConfirm" placeholder="输入 ${escapeHtml(p.id)} 后从草稿移除"><p class="muted">只从 WebUI 草稿移除；真正写入仍需要保存预览和确认。</p><div class="btns"><button type="button" id="deleteProvider" class="danger">从草稿移除通道</button></div></div>
      </div>
    </div>
    <div class="${panelClass('reports')}" data-provider-form-panel="reports">
      <div class="provider-action-grid">
        <div class="explain-card span4"><h4>使用统计</h4><p>读取当前通道的 usage 明细，并按这个通道内的模型展开启动次数；不会把其他通道混进来。</p><button type="button" class="ghost" data-settings-action="provider_usage_summary" data-report-target="channelReport">查看当前通道使用统计</button></div>
        <div class="explain-card span4"><h4>保存审计入口</h4><p>这里改的是持久通道配置。填完 Base URL、API Key、protocol、模型补丁后，统一到保存页生成 diff 和审计摘要。</p><button type="button" class="ghost" data-section-jump="save">去生成保存预览</button></div>
        <div class="explain-card span4"><h4>高级人工确认</h4><p>网络策略、自动排序这类会影响路由或本机边界的动作，不再放主路径；需要时只看说明，不自动执行。</p><button type="button" class="ghost" data-settings-action="provider_network_gate" data-report-target="channelReport">查看网络配置人工确认</button></div>
        <div class="span12"><div class="result module-report" id="channelReport">选择上方动作查看表格报告或人工确认说明。</div></div>
      </div>
    </div>
    <div class="btns provider-editor-actions"><button type="button" id="saveProviderForm">保存通道修改</button></div>
  </div>`;
  bindProviderForm();
  bindSettingsActionButtons();
}
function bindProviderForm(){
  document.querySelectorAll('[data-provider-form-tab]').forEach(btn=>{btn.onclick=()=>switchProviderFormTab(btn.dataset.providerFormTab)});
  ['pId','pName','pEnabled','pRole','pPriority','pClaude1m','pTimezone','pNote','pOpenAI','pAnthropic','pModelsEndpoint'].forEach(id=>{const el=$(id);if(!el)return;el.oninput=syncProvider;el.onchange=syncProvider});
  const keyEl=$('pKey');
  if(keyEl)keyEl.oninput=()=>{keyEl.dataset.touched='1';syncProvider()};
  const updateCreds=$('pUpdateCreds');if(updateCreds)updateCreds.onchange=syncProvider;
  const defaultEl=$('pDefault');if(defaultEl)defaultEl.onchange=()=>{syncProvider(); if($('pDefault').checked) state.provider_default=current().id; renderProviders();};
  const del=$('deleteProvider');if(del)del.onclick=deleteCurrentProviderDraft;
  document.querySelectorAll('input[name="pProtocols"],input[name="pClis"],[data-family-priority="providerFamilyPriority"]').forEach(x=>x.onchange=syncProvider);
  const save=$('saveProviderForm');if(save)save.onclick=()=>{syncProvider();setSection('save');toast('通道修改已暂存，生成保存预览后再写入')}
}
function deleteCurrentProviderDraft(){const p=current();if(!p)return;const typed=($('pDeleteConfirm')?.value||'').trim();if(typed!==p.id){toast('输入当前通道 ID 后才能从草稿移除');return}if((state.providers||[]).length<=1){toast('至少保留一个通道；删除最后一个通道请走 CLI/人工确认');return}const removed=p.id;state.providers.splice(activeProvider,1);touchedProviders.add(removed);if(state.provider_default===removed)state.provider_default=(state.providers[0]||{}).id||'';activeProvider=Math.max(0,Math.min(activeProvider,state.providers.length-1));lastPlan=null;renderAll();setSection('save');toast(`${removed} 已从 WebUI 草稿移除，生成保存预览后再写入`)}
function syncProvider(){const p=current(); if(!p)return; const old=p.id;touchProvider(old);const keyEl=$('pKey');const updateEl=$('pUpdateCreds');p.id=$('pId').value.trim()||p.id;if(p.id!==old){touchedProviders.delete(old);touchProvider(p.id)}p.name=$('pName').value.trim()||p.id;p.enabled=$('pEnabled').value==='true';p.role=$('pRole').value;p.priority=Number($('pPriority').value||100);p.family_priority_overrides=readFamilyPriorityInputs('providerFamilyPriority');p.claude_1m_mode=$('pClaude1m').value;p.timezone=$('pTimezone').value.trim();p.note=$('pNote').value.trim();p.openai_base_url=$('pOpenAI').value.trim();p.anthropic_base_url=$('pAnthropic').value.trim();p.models_endpoint=$('pModelsEndpoint').value.trim()||'/models';p.protocols=checkedValues('pProtocols');p.supported_clis=checkedValues('pClis');const keyText=keyEl?keyEl.value.trim():'';const keyTouched=keyEl?.dataset?.touched==='1';if(keyText){p.api_key=keyText;p.pending_api_key=true;p.has_api_key=true;if(updateEl)updateEl.checked=true}else if(keyTouched){p.api_key='';p.pending_api_key=false}p.update_credentials=!!(updateEl&&updateEl.checked);if(state.provider_default===old)state.provider_default=p.id;renderProviderList();renderTestSelectors();}

function derivedAliases(base,p){const ids=(base||[]).map(x=>String(x||''));const tails=ids.map(id=>id.toLowerCase().split('/').pop());const aliases=[];if(tails.some(id=>id.startsWith('claude-sonnet-4-')||id.startsWith('claude-sonnet-4.')))aliases.push('claude-sonnet-4-6');if(tails.some(id=>id.startsWith('claude-opus-4-')||id.startsWith('claude-opus-4.')))aliases.push('claude-opus-4-6');const ident=String([p?.id,p?.name,p?.label,p?.provider_profile].filter(Boolean).join(' ')).toLowerCase();const anthropic=String(p?.anthropic_base_url||p?.default_anthropic_base_url||'').toLowerCase();if((anthropic.includes('xiaomimimo.com')||ident.includes('mimo')||ident.includes('xiaomi'))&&!ident.includes('openrouter')){['mimo-v2.5-pro','mimo-v2.5'].forEach(id=>{if(ids.includes(id)&&!ids.includes(`${id}[1m]`))aliases.push(`${id}[1m]`)})}return aliases}
function providerModels(p){p=p||{};const map=new Map();const hiddenLower=new Set((p.hidden_models||[]).map(x=>String(x||'').toLowerCase()));const baseRows=(p.models||[]).filter(r=>r&&r.id&&r.source!=='hidden');baseRows.forEach(r=>map.set(r.id,{...r,visible:r.visible!==false&&!hiddenLower.has(String(r.id).toLowerCase()),capabilities:{...(r.capabilities||{})}}));if(!baseRows.length){(p.fallback_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'fallback',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})})}const baseIds=[...map.keys()];derivedAliases(baseIds.filter(id=>!hiddenLower.has(String(id).toLowerCase())),p).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'derived_alias',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.extra_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'extra',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.hidden_models||[]).forEach(id=>{[...map.keys()].forEach(key=>{if(String(key).toLowerCase()===String(id).toLowerCase())map.get(key).visible=false})});return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id))}
function defaultCaps(id){const l=String(id||'').toLowerCase();return {text:true,vision:['mimo-v2.5','mimo-v2-omni','k2.6','k2.6-code-preview','kimi-k2.5','qwen3.6-plus','qwen3.6-flash','qwen3.5-plus'].includes(l)||l.startsWith('claude-')||l.startsWith('gemini-'),tool_use:/^(claude|gpt|o|qwen|kimi|glm|minimax|gemini)/.test(l),reasoning:/gpt-5|qwen3|kimi-k2|glm-5|deepseek|claude/.test(l),long_context:/1m|long|qwen3|kimi-k2|gpt-5|claude/.test(l),cache_sensitive:/^(qwen|kimi|k2\.|glm|deepseek|minimax|mimo)/.test(l)}}
function providerCurrentIds(p){return new Set(providerModels(p).map(r=>r.id))}
function staleHiddenModels(p){const ids=providerCurrentIds(p);return [...new Set([...(p.stale_hidden_models||[]),...(p.hidden_models||[]).filter(id=>!ids.has(id))])]}
function cleanupStaleHidden(p){const stale=staleHiddenModels(p);const doomed=new Set(stale);p.hidden_models=(p.hidden_models||[]).filter(x=>!doomed.has(x));p.stale_hidden_models=[];return stale.length}
function cleanupAllStaleHidden(){let total=0;(state.providers||[]).forEach(p=>{const count=cleanupStaleHidden(p);if(count)touchProvider(p.id);total+=count});renderProviders();toast(total?`已移除 ${total} 条未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}
function staleRouteModels(p){const approved=(p.approved_route_models&&p.approved_route_models.length?p.approved_route_models:(p.fallback_models||[]));const remote=new Set((p.models||[]).filter(r=>r&&r.id).map(r=>String(r.id)));const extras=new Set((p.extra_models||[]).map(x=>String(x)));return [...new Set(approved.filter(id=>id&&!remote.has(String(id))&&!extras.has(String(id))))]}
function renderStaleRouteBox(p){const box=$('staleRouteBox');if(!box)return;const stale=staleRouteModels(p);if(!stale.length){box.innerHTML='<strong>缺失旧 route</strong><p class="muted">当前没有“本地已批准但本次拉取未返回”的旧 route。</p>';return}const armed=staleCleanupProviders.has(p.id);box.innerHTML=`<strong>缺失旧 route（默认保留）</strong><p class="muted">这些模型在本地已批准 routes 里，但不在当前拉取到的模型列表里。默认不会删除；如果勾选“拉取后自动标记”，本页后续拉取会自动标记清理。避免上游 /models 抖动或 New API 临时关闭导致下游模型被清空。</p><div class="chips">${stale.slice(0,24).map(m=>`<span class="chip">${escapeHtml(m)}</span>`).join('')}${stale.length>24?`<span class="chip">+${stale.length-24}</span>`:''}</div><div class="btns"><button id="armStaleRouteCleanup" class="ghost">${armed?'已标记：保存时清理这些旧 route':'显式标记保存时清理这些旧 route'}</button></div>`;$('armStaleRouteCleanup').onclick=()=>{staleCleanupProviders.add(p.id);touchProvider(p.id);renderStaleRouteBox(p);toast(`已标记 ${p.id}：下次写入预览 DB 会清理 ${stale.length} 条缺失旧 route`)}}
function visibleModelsForProvider(providerId,{visionFirst=false,includeHidden=false,enabledOnly=false}={}){let rows=[];(state.providers||[]).forEach(p=>{if(providerId&&p.id!==providerId)return;if(enabledOnly&&p.enabled===false)return;providerModels(p).forEach(r=>{if(!includeHidden&&r.visible===false)return;rows.push({...r,provider_id:p.id,provider_name:p.name||p.id,capabilities:{...(r.capabilities||defaultCaps(r.id))}})})});const seen=new Set();rows=rows.filter(r=>{const key=(providerId?'':r.provider_id+'::')+r.id;if(seen.has(key))return false;seen.add(key);return true});rows.sort((a,b)=>{const av=!!(a.capabilities||{}).vision,bv=!!(b.capabilities||{}).vision;if(visionFirst&&av!==bv)return av?-1:1;return (a.provider_id+' '+a.id).localeCompare(b.provider_id+' '+b.id)});return rows}
function providerOptions(selected,{blankLabel='请选择通道',auto=false,enabledOnly=false}={}){const opts=[];const providers=providerEntries().filter(({p})=>!enabledOnly||p.enabled||p.id===selected);if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动选择通道</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>${escapeHtml(blankLabel)}</option>`);opts.push(...providers.map(({p})=>{const disabled=p.enabled?'':' [已禁用，当前配置值]';return `<option value="${escapeHtml(p.id)}" ${p.id===selected?'selected':''}>${escapeHtml(p.name||p.id)} / ${escapeHtml(p.id)}${disabled}</option>`}));if(selected&&!state.providers.some(p=>p.id===selected))opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function modelOptionValue(providerId,row){return providerId?row.id:`${row.provider_id}::${row.id}`}
function decodeModelSelection(value,currentProvider){const text=String(value||'');if(!text)return{provider_id:currentProvider||'',model:''};const marker='::';if(text.includes(marker)){const [provider_id,...rest]=text.split(marker);return{provider_id,model:rest.join(marker)}}return{provider_id:currentProvider||'',model:text}}
function modelOptions(providerId,selected,{visionFirst=false,auto=false,defaultModels=[],enabledOnly=false,selectedProvider=''}={}){const rows=visibleModelsForProvider(providerId,{visionFirst,enabledOnly});let opts=[];if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动路线${defaultModels.length?'：'+escapeHtml(defaultModels.join(' / ')):''}</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>请选择模型</option>`);let matched=false;opts.push(...rows.map(r=>{const value=modelOptionValue(providerId,r);const label=providerId?r.id:`${r.provider_id} / ${r.id}`;const tag=(r.capabilities||{}).vision?' [vision]':'';const isSelected=providerId?r.id===selected:((selectedProvider&&r.provider_id===selectedProvider&&r.id===selected)||(!selectedProvider&&r.id===selected));if(isSelected)matched=true;return `<option value="${escapeHtml(value)}" ${isSelected?'selected':''}>${escapeHtml(label)}${tag}</option>`}));if(selected&&!matched)opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function renderStaleHiddenBox(p){const stale=staleHiddenModels(p);const box=$('staleHiddenBox');if(!box)return;if(!stale.length){box.innerHTML='<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">当前没有“暂时匹配不到模型行”的隐藏规则。</p>';return}box.innerHTML=`<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">这些只是当前通道 hidden_models 里的隐藏规则，暂时没有匹配到当前模型行；不等于远端不存在，也不等于 route 待删除。移除后如果模型仍在远端或 approved routes 里，会重新显示出来。</p><div class="chips">${stale.map(m=>`<span class="chip">${escapeHtml(m)} <button data-stale-rm="${escapeHtml(m)}">移除记录</button></span>`).join('')}</div><div class="btns"><button id="clearStaleHidden" class="ghost">移除当前通道未匹配隐藏规则</button></div>`;document.querySelectorAll('[data-stale-rm]').forEach(b=>b.onclick=()=>{p.hidden_models=(p.hidden_models||[]).filter(x=>x!==b.dataset.staleRm);p.stale_hidden_models=(p.stale_hidden_models||[]).filter(x=>x!==b.dataset.staleRm);touchProvider(p.id);renderModelTable()});$('clearStaleHidden').onclick=()=>{const count=cleanupStaleHidden(p);if(count)touchProvider(p.id);renderModelTable();toast(count?`已移除 ${count} 条当前通道未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}}
function renderModelInventorySummary(p){const box=$('modelInventorySummary');if(!box||!p)return;const rows=providerModels(p);const visible=rows.filter(r=>r.visible!==false).length;const hidden=(p.hidden_models||[]).length;const extra=(p.extra_models||[]).length;const stale=staleRouteModels(p).length+(p.stale_hidden_models||[]).length;box.innerHTML=[['显示',visible,'当前显示模型'],['补充',extra,'extra_models 补充'],['隐藏',hidden,'hidden_models 隐藏'],['待清理',stale,'待清理 route/hidden']].map(([label,count,desc])=>`<div class="inventory-tile"><span>${escapeHtml(label)}</span><strong>${count}</strong><p class="muted">${escapeHtml(desc)}</p></div>`).join('')}
function renderModelTable(){const p=current(); if(!p)return;renderModelInventorySummary(p);const q=($('modelSearch')?.value||'').toLowerCase();const rows=providerModels(p).filter(r=>r.id.toLowerCase().includes(q));const extras=p.extra_models||[];$('modelChips').innerHTML=`<strong>当前通道补充模型库（extra_models）</strong><p class="muted">这些模型是手动补充到当前 provider 的可用模型，会参与当前通道路由；不是待删除列表，也不是全局模型池。</p><div class="chips">${extras.length?extras.map(m=>`<span class="chip">${escapeHtml(m)}${editingExtraModels?` <button data-rm-extra="${escapeHtml(m)}">从补充库移除</button>`:''}</span>`).join(''):'<span class="muted">当前通道暂无手动补充模型。</span>'}</div><div class="btns"><button id="toggleExtraEdit" class="ghost">${editingExtraModels?'完成编辑':'编辑补充模型库'}</button></div><div id="staleRouteBox"></div>`;$('toggleExtraEdit').onclick=()=>{editingExtraModels=!editingExtraModels;renderModelTable()};document.querySelectorAll('[data-rm-extra]').forEach(b=>b.onclick=()=>{p.extra_models=extras.filter(x=>x!==b.dataset.rmExtra);touchProvider(p.id);toast(`已从当前通道补充模型库移除 ${b.dataset.rmExtra}`);renderModelTable()});renderStaleRouteBox(p);renderStaleHiddenBox(p);$('modelTable').innerHTML=`<thead><tr><th>显示</th><th>模型</th><th>来源</th><th>收藏</th><th>text</th><th>vision</th><th>tool</th><th>reason</th><th>long</th><th>cache</th></tr></thead><tbody>${rows.map(r=>{const c=r.capabilities||{};return `<tr><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="visible" ${r.visible?'checked':''}></td><td class="mono">${escapeHtml(r.id)}</td><td><span class="tag ${r.visible?'':'off'}">${modelSourceLabel(r.source||'manual')}</span></td><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="favorite" ${r.favorite?'checked':''}></td>${['text','vision','tool_use','reasoning','long_context','cache_sensitive'].map(k=>`<td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-cap="${k}" ${c[k]?'checked':''}></td>`).join('')}</tr>`}).join('')}</tbody>`;document.querySelectorAll('#modelTable input').forEach(x=>x.onchange=onModelToggle);renderTestSelectors();renderFallback();renderRuntime()}
function onModelToggle(e){const p=current();const model=e.target.dataset.model;let row=providerModels(p).find(r=>r.id===model)||{id:model,source:'hidden',visible:!(p.hidden_models||[]).includes(model),favorite:false,capabilities:defaultCaps(model)};row.policy_touched=true;if(e.target.dataset.field==='visible'){row.visible=e.target.checked;p.hidden_models=e.target.checked?(p.hidden_models||[]).filter(x=>x!==model):[...(p.hidden_models||[]).filter(x=>x!==model),model]}else if(e.target.dataset.field==='favorite'){row.favorite=e.target.checked}else if(e.target.dataset.cap){row.capabilities=row.capabilities||{};row.capabilities[e.target.dataset.cap]=e.target.checked}p.model_capabilities=p.model_capabilities||{};p.model_capabilities[model]=row.capabilities;p.models=(p.models||[]).filter(r=>r.id!==model).concat(row);touchProvider(p.id);renderTestSelectors();renderFallback();renderRuntime()}
function renderTestSelectors(){const tp=$('testProvider');if(!tp)return;tp.innerHTML=providerEntries().map(({p,i})=>`<option value="${i}">${escapeHtml(p.name||p.id)}${p.enabled?'':' [已禁用]'}</option>`).join('');tp.value=String(activeProvider);tp.onchange=()=>{activeProvider=Number(tp.value);renderAll()};const models=providerModels(current()||{});$('testModel').innerHTML=models.map(r=>`<option>${escapeHtml(r.id)}</option>`).join('')}
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
function presetLabel(preset){return {builder:'执行/协调',executor:'执行',explore:'探索',bughunt:'找茬',vision:'Vision',reviewer:'审查',spec:'Spec',fixer:'执行'}[preset]||preset||'自定义'}
function customAgentId(preset){const existing=new Set(opencodeAllRows().map(row=>row.agent));let i=1;let id='';do{id=`mobius-${preset}-custom-${i++}`}while(existing.has(id));return id}
function addCustomAgent(preset){const agent=customAgentId(preset);opencodeRoster()[agent]={enabled:true,custom:true,preset,priority:900+Object.keys(opencodeRoster()).length};renderOpencodeAgents();toast(`已添加 ${agent}`)}
function syncRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};state.runtime.preferred_cli=$('preferredCli').value;state.runtime.coding_preset_model=$('codingModel').value.trim();state.opencode.default_profile=$('opencodeProfile').value;state.opencode.agent_models=Object.fromEntries(opencodeOverrideEntries());state.opencode.agent_roster={...opencodeRoster()}}
function renderOpencodeSummary(){const box=$('opencodeOverrideSummary');if(!box)return;const rows=opencodeAllRows();const enabled=rows.filter(row=>rosterEntry(row.agent,row).enabled!==false).length;const count=opencodeOverrideEntries().length;const custom=rows.filter(row=>rosterEntry(row.agent,row).custom).length;const profile=state.opencode.default_profile||'agent';box.innerHTML=`<div class="oc-metric"><span class="muted">Profile</span><strong>${escapeHtml(profile)}</strong><span class="mono">Lite Pro Roster</span></div><div class="oc-metric"><span class="muted">已启用 Agent</span><strong>${enabled}/${rows.length}</strong><span class="mono">进入 session-local opencode.json</span></div><div class="oc-metric"><span class="muted">Agent 覆盖</span><strong>${count}/${rows.length}</strong><span class="mono">自动模式不写 agent_models</span></div><div class="oc-metric"><span class="muted">自定义 Agent</span><strong>${custom}</strong><span class="mono">按 preset 继承 prompt/permission</span></div>`}
function opencodeFilterMatches(row,overridden){const entry=rosterEntry(row.agent,row);if(opencodeOnlyOverridden&&!overridden&&entry.enabled!==false&&!entry.custom)return false;if(opencodeAgentFilter==='all')return true;if(opencodeAgentFilter==='enabled')return entry.enabled!==false;if(opencodeAgentFilter==='custom')return !!entry.custom;if(opencodeAgentFilter==='execute')return ['builder','executor','fixer','spec'].includes(entry.preset)||String(row.category||'').startsWith('执行');if(opencodeAgentFilter==='explore')return entry.preset==='explore'||row.category==='探索';if(opencodeAgentFilter==='bughunt')return entry.preset==='bughunt'||row.category==='找茬';if(opencodeAgentFilter==='vision')return entry.preset==='vision'||row.category==='Vision';if(opencodeAgentFilter==='review')return entry.preset==='reviewer'||row.category==='审查';return true}
function renderOpencodeFilters(){const wrap=$('opencodeAgentFilters');if(!wrap)return;const filters=[['all','全部'],['enabled','已启用'],['custom','自定义'],['execute','执行/协调'],['explore','探索'],['bughunt','找茬'],['vision','Vision'],['review','审查']];wrap.innerHTML=`${filters.map(([id,label])=>`<button class="ghost ${opencodeAgentFilter===id?'active':''}" data-oc-filter="${id}">${label}</button>`).join('')}<label class="check"><input id="ocOnlyOverridden" type="checkbox" ${opencodeOnlyOverridden?'checked':''}><span>只看改动项</span></label><button class="ghost" data-oc-add="vision">+ 添加 Vision Agent</button><button class="ghost" data-oc-add="executor">+ 添加执行 Agent</button><button class="ghost" data-oc-add="explore">+ 添加探索 Agent</button><button class="ghost" id="ocClearAll">全部自动</button>`;document.querySelectorAll('[data-oc-filter]').forEach(btn=>btn.onclick=()=>{opencodeAgentFilter=btn.dataset.ocFilter;renderOpencodeAgents()});document.querySelectorAll('[data-oc-add]').forEach(btn=>btn.onclick=()=>addCustomAgent(btn.dataset.ocAdd));$('ocOnlyOverridden').onchange=()=>{opencodeOnlyOverridden=$('ocOnlyOverridden').checked;renderOpencodeAgents()};$('ocClearAll').onclick=()=>{state.opencode.agent_models={};state.opencode.agent_roster={};syncRuntime();renderOpencodeAgents();toast('OpenCode roster 已恢复默认自动路线')}}
function renderOpencodeAgents(){const table=$('opencodeAgents');if(!table)return;const overrides=opencodeOverrides();renderOpencodeSummary();renderOpencodeFilters();const rows=opencodeAllRows();const visible=rows.filter(row=>{const entry=rosterEntry(row.agent,row);const overridden=!!(overrides[row.agent]&&overrides[row.agent].model)||entry.enabled===false||entry.custom;return opencodeFilterMatches(row,overridden)});const presetOptions=(selected)=>['builder','executor','explore','bughunt','vision','reviewer','spec','fixer'].map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p}</option>`).join('');const body=visible.length?visible.map(row=>{const entry=rosterEntry(row.agent,row);const ov=overrides[row.agent]||{};const provider=ov.provider_id||entry.provider_id||'';const model=ov.model||entry.model||'';const enabled=entry.enabled!==false;const changed=!!model||!enabled||!!entry.custom;return `<tr data-oc-agent="${escapeHtml(row.agent)}"><td><input class="oc-enabled" type="checkbox" data-oc-enabled ${enabled?'checked':''} ${row.agent==='mobius-builder-pro'?'disabled':''}></td><td class="mono">${escapeHtml(row.agent)}<br><span class="muted">${escapeHtml(row.route_key)}</span>${entry.custom?'<br><span class="tag">自定义</span>':''}${changed?'<span class="tag">已改动</span>':''}</td><td><select data-oc-preset ${entry.custom?'':'disabled'}>${presetOptions(entry.preset)}</select></td><td><input data-oc-priority type="number" value="${escapeHtml(entry.priority||999)}" style="max-width:86px"></td><td><select data-oc-provider>${providerOptions(provider,{auto:true,enabledOnly:true})}</select></td><td><select data-oc-model>${modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})}</select></td><td class="mono default-route">${escapeHtml((row.default_models||[]).join(' / ')||'preset auto')}</td><td><button class="ghost" data-oc-reset>自动</button></td></tr>`}).join(''):'<tr><td colspan="8" class="empty-row">没有匹配的 agent</td></tr>';table.innerHTML=`<thead><tr><th>启用</th><th>Agent</th><th>Preset</th><th>优先级</th><th>Provider</th><th>Model</th><th>默认模型</th><th></th></tr></thead><tbody>${body}</tbody>`;document.querySelectorAll('[data-oc-agent]').forEach(tr=>{const agent=tr.dataset.ocAgent;const row=visible.find(r=>r.agent===agent);const entry=rosterEntry(agent,row);tr.querySelector('[data-oc-enabled]').onchange=(e)=>{setRosterEnabled(agent,row,e.target.checked);renderOpencodeSummary()};tr.querySelector('[data-oc-preset]').onchange=(e)=>{persistRosterEntry(agent,row,{preset:e.target.value});renderOpencodeAgents()};tr.querySelector('[data-oc-priority]').oninput=(e)=>{persistRosterEntry(agent,row,{priority:Number(e.target.value)});renderOpencodeSummary()};tr.querySelector('[data-oc-provider]').onchange=(e)=>{const sel=e.target;const modelSel=tr.querySelector('[data-oc-model]');modelSel.innerHTML=modelOptions(sel.value,modelSel.value,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:sel.value});setOpencodeOverride(agent,sel.value,tr.querySelector('[data-oc-model]').value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-model]').onchange=(e)=>{setOpencodeOverride(agent,tr.querySelector('[data-oc-provider]').value,e.target.value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-reset]').onclick=()=>{const roster=opencodeRoster();delete roster[agent];const overrides=opencodeOverrides();delete overrides[agent];syncRuntime();renderOpencodeAgents();toast(`${agent} 已恢复默认`)}})}
function renderRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};$('preferredCli').value=state.runtime.preferred_cli||'opencode';$('codingModel').value=state.runtime.coding_preset_model||'';$('opencodeProfile').value=state.opencode.default_profile||'agent';$('preferredCli').oninput=syncRuntime;$('codingModel').oninput=syncRuntime;$('opencodeProfile').oninput=()=>{syncRuntime();renderOpencodeSummary()};renderOpencodeAgents()}
function accountLocked(a){return !!a.is_claude_human_only}
function syncAccounts(){if(!state.accounts)return;state.account_defaults=state.account_defaults||{};document.querySelectorAll('[data-account-id]').forEach(tr=>{const id=tr.dataset.accountId;const acc=(state.accounts||[]).find(a=>a.id===id);if(!acc||accountLocked(acc))return;const nameEl=tr.querySelector('[data-account-name]');const enabledEl=tr.querySelector('[data-account-enabled]');const priorityEl=tr.querySelector('[data-account-priority]');const familyEl=tr.querySelector('[data-account-family]');const claude1mEl=tr.querySelector('[data-account-claude-1m]');const timezoneEl=tr.querySelector('[data-account-timezone]');const noteEl=tr.querySelector('[data-account-note]');if(nameEl)acc.name=nameEl.value;if(enabledEl)acc.enabled=enabledEl.checked;if(priorityEl)acc.priority=Number(priorityEl.value||100);if(familyEl)acc.family_priority_overrides=parseFamilyOverrides(familyEl.value);if(claude1mEl)acc.claude_1m_mode=claude1mEl.value;if(timezoneEl)acc.timezone=timezoneEl.value.trim();if(noteEl)acc.note=noteEl.value.trim()});document.querySelectorAll('[data-account-default]:checked').forEach(el=>{if(!el.disabled&&el.dataset.accountCli)state.account_defaults[el.dataset.accountCli]=el.value})}
function mappingStatusLabel(status){return {native:'原生',report:'报告',draft_review:'草稿预览',human_gate:'人工确认',missing:'缺失'}[status]||status||'-'}
function mappingStatusClass(status){return 'status-'+String(status||'missing').replace(/[^a-z0-9_ -]/gi,'').replace(/\s+/g,'_')}
function mappingActionButton(row){const parts=[];if(row.webui_section_id){parts.push(`<button class="ghost mapping-action" data-section-jump="${escapeHtml(row.webui_section_id)}">打开</button>`)}if(row.api_action){const label=row.status==='human_gate'?'人工确认':(row.status==='missing'?'缺口':'报告');parts.push(`<button class="ghost mapping-action" data-settings-action="${escapeHtml(row.api_action)}">${label}</button>`)}return parts.join(' ')}
function renderMappingFilters(mapping){const box=$('mappingFilters');if(!box)return;const count=s=>mapping.filter(row=>s==='all'||row.status===s).length;const filters=[['all','全部'],['native','原生'],['report','报告'],['draft_review','草稿'],['human_gate','人工确认'],['missing','缺失']];box.innerHTML=filters.map(([id,label])=>`<button class="${settingsMappingFilter===id?'active':''}" data-map-filter="${id}">${label} ${count(id)}</button>`).join('');document.querySelectorAll('[data-map-filter]').forEach(btn=>{btn.onclick=()=>{settingsMappingFilter=btn.dataset.mapFilter;renderSettings()}})}
function acceptanceStorageKey(){return `mms-webui-tui-acceptance:${state?.command||'mms'}:${state?.schema||'snapshot'}`}
function loadAcceptanceState(mapping){try{const allowed=new Set((mapping||[]).map(row=>row.id));const raw=JSON.parse(localStorage.getItem(acceptanceStorageKey())||'[]');checkedMappingRows=new Set((Array.isArray(raw)?raw:[]).filter(id=>allowed.has(id)))}catch(_err){checkedMappingRows=new Set()}}
function saveAcceptanceState(){try{localStorage.setItem(acceptanceStorageKey(),JSON.stringify([...checkedMappingRows].sort()))}catch(_err){}}
function currentMappingRows(mapping){return settingsMappingFilter==='all'?mapping:mapping.filter(row=>row.status===settingsMappingFilter)}
function acceptanceReportText(mapping){const rows=mapping||[];const unchecked=rows.filter(row=>!checkedMappingRows.has(row.id));const counts=(state.tui_webui_mapping_summary||{}).counts||{};return [`MMS WebUI 设置/通道验收`,`命令: ${state.command||'mms'}`,`总数: ${rows.length}`,`已检查: ${rows.length-unchecked.length}`,`未检查: ${unchecked.length}`,`状态: 原生 ${counts.native||0} / 报告 ${counts.report||0} / 草稿 ${counts.draft_review||0} / 人工确认 ${counts.human_gate||0} / 缺失 ${counts.missing||0}`,`可点击: ${(state.tui_webui_mapping_summary||{}).clickable_rows||0}/${rows.length}`,`未检查行: ${unchecked.map(row=>row.id).join(', ')||'-'}`].join('\\n')}
async function copyAcceptanceReport(mapping){const text=acceptanceReportText(mapping);try{await navigator.clipboard.writeText(text);toast('已复制验收摘要')}catch(_err){$('settingsReport').textContent=text;toast('无法访问剪贴板，验收摘要已显示在报告区')}}
function renderAcceptancePanel(mapping){const box=$('acceptancePanel');if(!box)return;const rows=mapping||[];const visible=currentMappingRows(rows);const checked=rows.filter(row=>checkedMappingRows.has(row.id)).length;const clickable=(state.tui_webui_mapping_summary||{}).clickable_rows??rows.filter(row=>row.clickable==='yes').length;const missing=(state.tui_webui_mapping_summary||{}).counts?.missing||0;box.innerHTML=`<div class="acceptance-head"><div><h4>逐项验收清单</h4><p class="muted">你可以按行点击打开 / 报告 / 人工确认 / 保存预览验证，再勾选左侧已检查；状态保存在本浏览器 localStorage，不写真实 MMS config。</p></div><div class="acceptance-progress" id="mapCheckProgress">${checked}/${rows.length}</div></div><div class="chips"><span class="chip">可点击 ${clickable}/${rows.length}</span><span class="chip">当前可见 ${visible.length}</span><span class="chip">缺失 ${missing}</span><span class="chip">${checked===rows.length?'全部已检查':'未检查 '+(rows.length-checked)}</span></div><div class="btns"><button class="ghost" id="markVisibleChecked">标记当前筛选已检查</button><button class="ghost" id="copyAcceptanceReport">复制验收摘要</button><button class="ghost" id="clearAcceptanceChecks">清空本地勾选</button></div>`;$('markVisibleChecked').onclick=()=>{visible.forEach(row=>checkedMappingRows.add(row.id));saveAcceptanceState();renderTuiMapping(rows);toast(`已标记 ${visible.length} 行为已检查`)};$('clearAcceptanceChecks').onclick=()=>{checkedMappingRows.clear();saveAcceptanceState();renderTuiMapping(rows);toast('已清空本地验收勾选')};$('copyAcceptanceReport').onclick=()=>copyAcceptanceReport(rows)}
function bindMappingChecks(mapping){document.querySelectorAll('[data-map-check]').forEach(input=>{input.onchange=()=>{const id=input.dataset.mapCheck;if(input.checked)checkedMappingRows.add(id);else checkedMappingRows.delete(id);saveAcceptanceState();renderAcceptancePanel(mapping)}})}
function renderTuiMapping(mapping){renderMappingFilters(mapping);renderAcceptancePanel(mapping);const rows=currentMappingRows(mapping);const body=rows.length?rows.map(row=>`<tr><td><label class="mapping-check"><input data-map-check="${escapeHtml(row.id)}" type="checkbox" ${checkedMappingRows.has(row.id)?'checked':''}>已检查</label></td><td class="mono">${escapeHtml(row.tui_area)}<br><span class="muted">${escapeHtml(row.tui_action_id)}</span></td><td>${escapeHtml(row.tui_label)}</td><td>${escapeHtml(row.webui_section)}<br><span class="muted">${escapeHtml(row.webui_control)}</span></td><td><span class="tag ${mappingStatusClass(row.status)}">${mappingStatusLabel(row.status)}</span><br><span class="muted">${writePolicyLabel(row.write_policy)}</span></td><td class="default-route">${escapeHtml(row.verification||'-')}<br><span class="check-evidence">${clickTargetsLabel(row.click_targets||'-')}</span><br><span class="muted">${escapeHtml(row.acceptance_check||row.manual_check||'')}</span></td><td>${mappingActionButton(row)}</td></tr>`).join(''):'<tr><td colspan="7" class="empty-row">当前筛选没有条目</td></tr>';$('tuiMappingTable').innerHTML=`<thead><tr><th>检查</th><th>TUI 区域/动作</th><th>TUI 文案</th><th>WebUI 落点</th><th>状态</th><th>验证 / 点击证据</th><th>操作</th></tr></thead><tbody>${body}</tbody>`;bindMappingChecks(mapping)}
function gateArray(items){return Array.isArray(items)?items.filter(x=>String(x??'').trim()).map(x=>String(x)) : []}
function gateList(items,empty='-'){const rows=gateArray(items);return rows.length?`<ol class="gate-list">${rows.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ol>`:`<p class="muted">${escapeHtml(empty)}</p>`}
function gateCommands(commands){lastGateCommands=gateArray(commands);if(!lastGateCommands.length)return '<p class="muted">没有安全 one-shot CLI；按人工步骤处理。</p>';return lastGateCommands.map((cmd,i)=>`<div class="gate-command-row"><code>${escapeHtml(cmd)}</code><button class="ghost copy-gate-command" data-copy-gate-command="${i}">复制</button></div>`).join('')}
async function copyGateCommand(i){const cmd=lastGateCommands[Number(i)]||'';if(!cmd){toast('没有可复制命令');return}try{await navigator.clipboard.writeText(cmd);toast('已复制 人工确认 命令')}catch(_err){$('settingsReport').insertAdjacentHTML('afterbegin',`<div class="gate-box"><h5>剪贴板备用显示</h5><p class="mono">${escapeHtml(cmd)}</p></div>`);toast('无法访问剪贴板，命令已显示')}}
function bindGateCopyButtons(){document.querySelectorAll('[data-copy-gate-command]').forEach(btn=>{btn.onclick=()=>copyGateCommand(btn.dataset.copyGateCommand)})}
function renderGateReport(data,targetId='settingsReport'){const mapping=data.mapping||[];const mappingHtml=mapping.length?mapping.map(row=>`<span class="chip">${escapeHtml(row.tui_area||'-')} / ${escapeHtml(row.tui_label||row.tui_action_id||'-')}</span>`).join(''):'<span class="chip">无 mapping 行</span>';const writes=gateArray(data.writes);const writeText=writes.length?writes:['无直接写入；仍保留人工确认。'];const target=$(targetId)||$('settingsReport');if(!target)return;target.innerHTML=`<div class="gate-report"><div class="gate-plate"><div class="gate-head"><div><h4>${escapeHtml(data.title||data.action||'人工确认')}</h4><p>${escapeHtml(data.note||'该动作需要人工确认，WebUI 不自动执行。')}</p></div><div class="gate-risk">${riskLabel(data.risk_level||'high')} / 已拦截</div></div><div class="chips"><span class="chip">${writePolicyLabel(data.write_policy||'human_gate')}</span><span class="chip">${data.requires_human_confirmation?'需要人工确认':'只读'}</span><span class="chip">${data.blocked_auto_execute?'禁止自动执行':'允许自动执行'}</span><span class="chip">${data.copyable?'可复制命令':'仅人工'}</span></div></div><div class="gate-grid"><div class="gate-box"><h5>可复制命令</h5>${gateCommands(data.commands)}</div><div class="gate-box"><h5>人工步骤</h5>${gateList(data.manual_steps,'按项目 人工确认 规则人工处理。')}</div><div class="gate-box"><h5>写入范围</h5>${gateList(writeText)}</div><div class="gate-box"><h5>更安全的 WebUI 路径</h5><p>${escapeHtml(data.safe_alternative||'使用只读报告或保存页 diff 预览。')}</p><div class="chips">${mappingHtml}</div></div></div><details class="gate-raw"><summary>原始 JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`;bindGateCopyButtons()}
function reportTopModels(rows=[]){const top=[];(rows||[]).forEach(row=>{(row.top_models||[]).forEach(item=>{if(item&&item.model)top.push(`${item.model} × ${item.launches||0}`)})});return top.slice(0,6).join(' / ')||'-'}
function usageDetailRows(ownerId,rows=[]){const safeRows=Array.isArray(rows)?rows:[];if(!safeRows.length)return '';return safeRows.map(row=>`<tr><td class="mono">${escapeHtml(ownerId)}</td><td>${escapeHtml(row.cli||'-')}</td><td>${escapeHtml(row.name||row.id||'-')}</td><td>${Number(row.launches||0)}</td><td class="mono">${escapeHtml(row.last_model||'-')}</td><td>${escapeHtml(row.last_used_at||'-')}</td><td>${escapeHtml(reportTopModels([row]))}</td></tr>`).join('')}
function modelUsageKey(id){return String(id||'').trim().toLowerCase()}
function providerModelUsageRows(p){
  const counts=new Map();const lastUsed=new Map();const lastCli=new Map();
  (p.usage_rows||[]).forEach(row=>{
    (row.model_usage||row.top_models||[]).forEach(item=>{const key=modelUsageKey(item.model);if(!key)return;counts.set(key,(counts.get(key)||0)+Number(item.launches||0))});
    const lastKey=modelUsageKey(row.last_model);if(lastKey){lastUsed.set(lastKey,row.last_used_at||'');lastCli.set(lastKey,row.cli||'')}
  });
  const modelRows=Array.isArray(p.models)?p.models:[];const seen=new Set();
  const rows=modelRows.map(row=>{const id=String(row.id||'').trim();const key=modelUsageKey(id);seen.add(key);return {id,source:row.source||'manual',visible:row.visible!==false,favorite:!!row.favorite,launches:counts.get(key)||0,last_used_at:lastUsed.get(key)||'',last_cli:lastCli.get(key)||''}}).filter(row=>row.id);
  counts.forEach((launches,key)=>{if(seen.has(key))return;const display=(p.usage_rows||[]).flatMap(row=>row.model_usage||row.top_models||[]).find(item=>modelUsageKey(item.model)===key)?.model||key;rows.push({id:display,source:'usage-only',visible:true,favorite:false,launches,last_used_at:lastUsed.get(key)||'',last_cli:lastCli.get(key)||''})});
  return rows.sort((a,b)=>Number(b.launches||0)-Number(a.launches||0)||a.id.localeCompare(b.id));
}
function renderProviderUsageReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  let providers=Array.isArray(data.providers)?data.providers:[];
  if(targetId==='channelReport'&&current()){const activeId=current().id;providers=providers.filter(p=>p.id===activeId);if(providers.length===1){providers=[{...providers[0],models:providerModels(current())}]}}
  const channelScoped=targetId==='channelReport';
  const totalLaunches=providers.reduce((sum,p)=>sum+Number((p.usage||{}).launches||0),0);
  if(channelScoped&&!providers.length){target.innerHTML='<div class="usage-report"><h4>当前通道使用统计</h4><p class="muted">当前通道没有可读取的 usage 记录。</p></div>';return}
  const providerRows=!channelScoped&&providers.length?`<div class="table-wrap"><table><thead><tr><th>通道 ID</th><th>名称</th><th>状态</th><th>role</th><th>priority</th><th>模型数</th><th>启动</th><th>最近使用</th><th>常用模型</th></tr></thead><tbody>${providers.map(p=>`<tr><td class="mono">${escapeHtml(p.id||'-')}</td><td>${escapeHtml(p.name||'-')}</td><td>${p.enabled?'<span class="tag">启用</span>':'<span class="tag off">禁用</span>'}</td><td>${escapeHtml(p.role||'-')}</td><td>${Number(p.priority||0)}</td><td>${Number(p.model_count||0)}</td><td>${Number((p.usage||{}).launches||0)}</td><td>${escapeHtml((p.usage||{}).last_used_at||'-')}</td><td>${escapeHtml(reportTopModels(p.usage_rows||[]))}</td></tr>`).join('')}</tbody></table></div>`:'';
  const modelSections=providers.map(p=>{const modelRows=providerModelUsageRows(p);const usedCount=modelRows.filter(row=>Number(row.launches||0)>0).length;const rows=modelRows.length?modelRows.map(row=>`<tr><td>${escapeHtml(row.id)}</td><td><span class="tag ${row.visible?'':'off'}">${modelSourceLabel(row.source)}</span>${row.favorite?'<span class="tag">收藏</span>':''}</td><td>${row.visible?'显示':'隐藏'}</td><td>${Number(row.launches||0)}</td><td>${escapeHtml(row.last_cli||'-')}</td><td>${escapeHtml(row.last_used_at||'-')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty-row">当前通道没有模型清单</td></tr>';return `<div class="chips usage-summary"><span class="chip">当前通道 ${escapeHtml(p.name||p.id||'-')}</span><span class="chip mono">${escapeHtml(p.id||'-')}</span><span class="chip">模型 ${modelRows.length}</span><span class="chip">有使用 ${usedCount}</span><span class="chip">总启动 ${Number((p.usage||{}).launches||0)}</span><span class="chip">最近 ${escapeHtml((p.usage||{}).last_used_at||'-')}</span></div><div class="table-wrap usage-table-wrap"><table class="usage-model-table"><thead><tr><th>模型</th><th>来源</th><th>显示状态</th><th>启动次数</th><th>最近 CLI</th><th>最近使用</th></tr></thead><tbody>${rows}</tbody></table></div>`}).join('')||'<p class="muted">暂无通道使用统计</p>';
  const detailRows=providers.map(p=>usageDetailRows(p.id||p.name||'-',p.usage_rows||[])).join('')||'<tr><td colspan="7" class="empty-row">暂无 CLI 维度使用明细</td></tr>';
  const title=channelScoped?'当前通道使用统计':'通道使用统计汇总';
  const note=channelScoped?'只读报告：只展示当前选中通道，并按这个通道内的模型展开启动次数；不会把其他通道混进来。':'只读报告：展示全部 provider usage 汇总；通道页按钮会自动限定到当前通道。';
  target.innerHTML=`<div class="usage-report"><h4>${title}</h4><p>${note}</p><div class="chips"><span class="chip">统计范围 ${channelScoped?'当前通道':'全部通道'}</span><span class="chip">总启动 ${totalLaunches}</span><span class="chip">写入策略 ${writePolicyLabel(data.write_policy||'read_only')}</span></div>${providerRows}${modelSections}<details class="usage-detail"><summary>CLI 明细（按需展开）</summary><div class="table-wrap"><table><thead><tr><th>通道 ID</th><th>CLI</th><th>明细名</th><th>启动</th><th>最近模型</th><th>最近使用</th><th>Top models</th></tr></thead><tbody>${detailRows}</tbody></table></div></details></div>`;
}
function renderAccountStatusReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  const accounts=Array.isArray(data.accounts)?data.accounts:[];
  const defaults=data.account_defaults||{};
  const rows=accounts.length?accounts.map(a=>{const cli=String(a.cli||'').toLowerCase();const isDefault=defaults[cli]===a.id;return `<tr><td class="mono">${escapeHtml(a.id||'-')}</td><td>${escapeHtml(a.name||'-')}</td><td>${escapeHtml((a.cli||'-').toUpperCase())}</td><td>${isDefault?'是':'否'}</td><td>${a.enabled?'<span class="tag">启用</span>':'<span class="tag off">禁用</span>'}</td><td>${Number(a.priority||0)}</td><td>${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{})||'-')}</td><td>${escapeHtml(a.auth_mode||'-')}</td><td>${Number((a.usage||{}).launches||0)}</td><td>${escapeHtml((a.usage||{}).last_used_at||'-')}</td><td>${escapeHtml(reportTopModels(a.usage_rows||[]))}</td><td>${a.is_claude_human_only?'<span class="tag off">Claude 人工锁定</span>':`<span class="tag">${writePolicyLabel(a.webui_write_policy||'draft_review')}</span>`}</td></tr>`}).join(''):'<tr><td colspan="12" class="empty-row">暂无账号状态</td></tr>';
  target.innerHTML=`<div class="account-report"><h4>账号状态</h4><p>${escapeHtml(data.note||'只读表格展示；OAuth / AGY 新登录主流程已下线，删除、重命名和 Claude account 仍保持人工确认。')}</p><div class="table-wrap"><table><thead><tr><th>ID</th><th>名称</th><th>CLI</th><th>默认</th><th>状态</th><th>priority</th><th>Family</th><th>auth</th><th>启动</th><th>最近</th><th>常用模型</th><th>写入边界</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function renderSettingsReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  if(data&&data.action==='provider_usage_summary'){renderProviderUsageReport(data,targetId);return}
  if(data&&(data.action==='accounts'||data.action==='account_status')){renderAccountStatusReport(data,targetId);return}
  if(data&&(data.blocked_auto_execute||data.requires_human_confirmation||data.status==='human_gate')){renderGateReport(data,targetId);return}
  target.textContent=JSON.stringify(data,null,2)
}
function bindSettingsActionButtons(){document.querySelectorAll('[data-settings-action]').forEach(btn=>{btn.onclick=async()=>{const action=btn.dataset.settingsAction;const targetId=btn.dataset.reportTarget||'settingsReport';const target=$(targetId)||$('settingsReport');if(target)target.textContent='读取中...';const payload={action};if(btn.dataset.accountId)payload.account_id=btn.dataset.accountId;if(btn.dataset.providerId)payload.provider_id=btn.dataset.providerId;if(action==='provider_usage_summary'&&targetId==='channelReport'&&current()?.id)payload.provider_id=current().id;const data=await api('/api/settings/report',payload);renderSettingsReport(data,targetId);if(targetId==='channelReport')switchProviderFormTab('reports');toast(data.ok?`${btn.textContent} 已刷新`:`${btn.textContent} 失败`)}});document.querySelectorAll('[data-section-jump]').forEach(btn=>{btn.onclick=()=>{setSection(btn.dataset.sectionJump);toast(`已打开 ${btn.dataset.sectionJump} 对应 WebUI 区域`)}})}
function syncUiSettings(){state.ui=state.ui||{};state.ui.language=$('uiLanguage')?.value||'zh'}
function renderUiSettings(mapping){state.ui=state.ui||{language:'zh'};const lang=state.ui.language||'zh';if($('uiLanguage')){$('uiLanguage').value=['zh','en'].includes(lang)?lang:'zh';$('uiLanguage').onchange=()=>{syncUiSettings();toast('界面语言已暂存，生成保存预览后再写入')}}const save=$('saveUiLanguage');if(save)save.onclick=()=>{syncUiSettings();setSection('save');toast('界面语言修改已暂存，生成保存预览后再写入')};const counts=(state.tui_webui_mapping_summary||{}).counts||{};const missingRows=(mapping||[]).filter(row=>row.status==='missing').map(row=>row.tui_label);if($('settingsGapSummary')){$('settingsGapSummary').innerHTML=`<span class="chip">原生 ${counts.native||0}</span><span class="chip">报告 ${counts.report||0}</span><span class="chip">草稿 ${counts.draft_review||0}</span><span class="chip">人工确认 ${counts.human_gate||0}</span><span class="chip">缺失 ${counts.missing||0}</span>${missingRows.length?`<span class="chip">仍缺：${escapeHtml(missingRows.join(' / '))}</span>`:'<span class="chip">无缺失行</span>'}`}}
function switchSettingsTab(tab){
  settingsActiveTab=tab||'accounts';
  const panels=[...document.querySelectorAll('[data-settings-panel]')];
  if(!panels.some(p=>p.dataset.settingsPanel===settingsActiveTab))settingsActiveTab='accounts';
  document.querySelectorAll('[data-settings-tab]').forEach(btn=>btn.classList.toggle('active',btn.dataset.settingsTab===settingsActiveTab));
  panels.forEach(panel=>panel.classList.toggle('active',panel.dataset.settingsPanel===settingsActiveTab));
}
function bindSettingsTabs(){document.querySelectorAll('[data-settings-tab]').forEach(btn=>{btn.onclick=()=>switchSettingsTab(btn.dataset.settingsTab)})}
function accountActionButtons(a){const id=escapeHtml(a.id||'');return `<details class="account-advanced"><summary>兼容 / 危险动作（已降级）</summary><p class="muted">登录、重命名、网络和删除会碰外部账号状态或本机目录，不作为 WebUI 日常配置主流程。</p><div class="btns"><button class="ghost mapping-action" data-settings-action="account_login_gate" data-report-target="settingsReport" data-account-id="${id}">登录兼容说明</button><button class="ghost mapping-action" data-settings-action="account_rename_gate" data-report-target="settingsReport" data-account-id="${id}">重命名确认</button><button class="ghost mapping-action" data-settings-action="account_network_gate" data-report-target="settingsReport" data-account-id="${id}">网络确认</button><button class="ghost mapping-action" data-settings-action="account_remove_gate" data-report-target="settingsReport" data-account-id="${id}">删除确认</button></div></details>`}
function accountConfigCard(a){
  const locked=accountLocked(a);const cli=String(a.cli||'').toLowerCase();const isDefault=(state.account_defaults||{})[cli]===a.id;const name=escapeHtml(a.name||a.id||'-');const id=escapeHtml(a.id||'');const defaultInput=`<label class="check"><input data-account-default data-account-cli="${escapeHtml(cli)}" name="account-default-${escapeHtml(cli)}" type="radio" value="${id}" ${isDefault?'checked':''} ${locked?'disabled':''}><span>设为 ${escapeHtml((a.cli||'-').toUpperCase())} 默认账号</span></label>`;
  const fieldHtml=locked?`<div class="account-fields"><div class="span6"><label>名称</label><p class="mono">${name}</p></div><div class="span3"><label>priority</label><p class="mono">${Number(a.priority||100)}</p></div><div class="span3"><label>Claude 1M</label><p class="mono">${escapeHtml(a.claude_1m_mode||'auto')}</p></div><div class="span3"><label>timezone</label><p class="mono">${escapeHtml(a.timezone||'-')}</p></div><div class="span3"><label>note</label><p>${escapeHtml(a.note||'-')}</p></div></div>`:`<div class="account-fields"><div class="span6"><label>名称</label><input data-account-name value="${name}"></div><div class="span3"><label>priority</label><input data-account-priority type="number" value="${escapeHtml(a.priority||100)}"></div><div class="span3"><label>Claude 1M</label><select data-account-claude-1m><option value="auto" ${(a.claude_1m_mode||'auto')==='auto'?'selected':''}>自动</option><option value="enable" ${a.claude_1m_mode==='enable'?'selected':''}>启用</option><option value="disable" ${a.claude_1m_mode==='disable'?'selected':''}>禁用</option></select></div><div class="span3"><label>timezone</label><input data-account-timezone value="${escapeHtml(a.timezone||'')}" placeholder="Asia/Singapore"></div><div class="span9"><label>note</label><input data-account-note value="${escapeHtml(a.note||'')}" placeholder="备注会进入保存预览"></div></div>`;
  const family=locked?`<p class="mono">${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{})||'继承')}</p>`:`<input data-account-family value="${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{}))}" placeholder="GPT=120, Qwen=90">`;
  return `<div class="account-config-card ${locked?'locked':''}" data-account-id="${id}"><div class="account-card-head"><div><h4>${name}</h4><p class="mono">${id}</p></div><div class="chips"><span class="chip">${escapeHtml((a.cli||'-').toUpperCase())}</span><span class="chip ${a.enabled?'':'off'}">${a.enabled?'启用':'禁用'}</span>${isDefault?'<span class="chip">默认</span>':''}${locked?'<span class="chip off">Claude 人工锁定</span>':''}</div></div>${locked?'<p class="muted">Claude account 只读展示，不允许 WebUI 自动写入。</p>':`<label class="check"><input data-account-enabled type="checkbox" ${a.enabled?'checked':''}><span>启用这个账号</span></label>`}${defaultInput}${fieldHtml}<details class="account-advanced"><summary>Family 权重覆盖（不常用）</summary><p class="muted">平时留空继承账号 priority；只在某个 family 需要单独排序时填写。</p>${family}</details><div class="chips"><span class="chip">auth ${escapeHtml(a.auth_mode||'-')}</span><span class="chip">home ${yn(a.home_dir_configured)}</span><span class="chip">proxy ${yn(a.proxy_configured)}</span><span class="chip">启动 ${Number((a.usage||{}).launches||0)}</span><span class="chip">最近 ${escapeHtml((a.usage||{}).last_used_at||'-')}</span><span class="chip ${locked?'off':''}">${writePolicyLabel(a.webui_write_policy||'read_only')}</span></div>${accountActionButtons(a)}</div>`
}
function renderSettings(){
  state.account_defaults=state.account_defaults||{};
  const accounts=state.accounts||[];const coverage=state.webui_capability_coverage||[];const mapping=state.tui_webui_mapping||[];
  renderUiSettings(mapping);
  const accountEmpty='<div class="settings-compat-note"><strong>暂无 CLI account</strong><p>API Key provider 请在「通道配置」维护。OAuth / AGY 官方登录已不再作为新增主流程。</p></div>';
  if($('accountTable')){$('accountTable').innerHTML=accounts.length?accounts.map(accountConfigCard).join(''):accountEmpty}
  document.querySelectorAll('[data-account-name],[data-account-enabled],[data-account-priority],[data-account-family],[data-account-claude-1m],[data-account-timezone],[data-account-note]').forEach(el=>{const handler=()=>{syncAccounts();toast('账号草稿已暂存，生成保存预览后再写入')};el.oninput=handler;el.onchange=handler});
  document.querySelectorAll('[data-account-default]').forEach(el=>{el.onchange=()=>{syncAccounts();renderSettings();toast('账号默认值已暂存，生成保存预览后再写入')}});
  if($('settingsCoverage')){$('settingsCoverage').innerHTML=`<thead><tr><th>区域</th><th>能力</th><th>WebUI</th><th>TUI 后续</th></tr></thead><tbody>${coverage.map(row=>`<tr><td>${escapeHtml(row.area)}</td><td>${escapeHtml(row.capability)}</td><td><span class="tag ${String(row.webui||'').includes('planned')||String(row.webui||'').includes('human_gate')||String(row.webui||'').includes('待补齐')||String(row.webui||'').includes('人工确认')?'off':''}">${writePolicyLabel(row.webui)}</span></td><td>${writePolicyLabel(row.tui)}</td></tr>`).join('')}</tbody>`}
  renderTuiMapping(mapping);
  bindSettingsTabs();
  bindSettingsActionButtons();
  switchSettingsTab(settingsActiveTab);
}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function planJsonHint(plan){const v2=plan?.registry_v2_save_plan||{};const planJson=v2.plan_json||{};const apply=v2.apply_plan||{};if(!planJson.name&&!apply.cli_apply_command)return '';return `<h4>Plan JSON / apply-plan</h4><p class="muted">${escapeHtml(planJson.note||'Plan JSON 是保存预览的审查产物。')}</p><p><span class="tag">${escapeHtml(planJson.name||'webui-plan.json')}</span> <span class="tag ${planJson.redacted?'off':''}">secrets ${planJson.redacted?'已脱敏':'含明文'}</span></p><p class="mono">${escapeHtml(apply.cli_apply_command||'')}</p>`}
function renderApplyResult(data){const blockers=data.runtime_blockers||{};const next=data.next_action||{};const publish=data.publish||{};const verify=data.verify||{};const ready=data.runtime_ready===true;const notReady=data.runtime_ready===false;const errs=Array.isArray(data.errors)?data.errors:[data.error||'unknown error'];const title=!data.ok?'写入被阻止':(ready?'已发布，可直接给 mmf 使用':'已发布，但 runtime 未就绪');const detail=!data.ok?errs.join('；'):(ready?'latest-approved bundle 已验证，mmf 会读到这次保存后的最新 bundle。':'latest-approved bundle 已发布且已验证；mmf 会读到最新 bundle，但缺 key/base URL/模型 route 的条目不能正常启动。');$('saveResult').innerHTML=`<div><p><span class="tag ${data.ok&&!notReady?'':'off'}">${escapeHtml(title)}</span> <span class="tag">${escapeHtml(data.status||'-')}</span></p><p class="muted">${escapeHtml(detail)}</p><p><span class="tag">manifest ${verify.verified?'已验证':'未验证'}</span><span class="tag ${ready?'':'off'}">runtime ${ready?'就绪':notReady?'未就绪':'未知'}</span><span class="tag">缺 API Key ${blockers.missing_api_key_count||0}</span><span class="tag">缺 Base URL ${blockers.missing_base_url_count||0}</span><span class="tag">通道 route ${blockers.provider_route_count||publish.provider_route_count||0}</span></p>${next.label?`<p><strong>下一步</strong>：${escapeHtml(next.label)}</p>`:''}<details><summary>原始 JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`}
function renderReviewSummary(plan){const review=plan?.review_summary||{};const counts=review.counts||{};const risks=review.risks||[];const items=review.items||[];const riskHtml=risks.length?`<h4>风险提示</h4><div>${risks.map(r=>`<p><span class="tag ${r.level==='danger'?'off':''}">${escapeHtml(levelLabel(r.level))}</span> <strong>${escapeHtml(r.title)}</strong> ${escapeHtml(r.detail)}</p>`).join('')}</div>`:'<p><span class="tag">无高风险提示</span></p>';const itemHtml=items.length?items.map(item=>`<p><span class="tag ${item.level==='danger'?'off':''}">${escapeHtml(levelLabel(item.level))}</span> <strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.detail)}</p>`).join(''):'<p class="muted">没有检测到配置变化。</p>';$('reviewSummary').innerHTML=`<div class="chips"><span class="chip">变化 ${counts.items||0}</span><span class="chip">风险 ${counts.risks||0}</span><span class="chip">移除隐藏记录 ${counts.hidden_removed||0}</span><span class="chip">凭据更新 ${counts.credential_updates||0}</span></div>${riskHtml}<h4>将要写入的变化</h4>${itemHtml}${planJsonHint(plan)}`}
function currentBundleRevision(){return state?.consumer_bundle_status?.component_revisions?.bundle||state?.consumer_bundle_status?.manifest?.bundle_revision||state?.model_source_status?.generated_bundle?.component_revisions?.bundle||state?.model_source_status?.generated_bundle?.manifest?.bundle_revision||''}
function draft(){syncProvider();syncFallback();syncRuntime();syncAccounts();syncUiSettings();return JSON.parse(JSON.stringify({providers:state.providers,provider_default:state.provider_default,accounts:state.accounts,account_defaults:state.account_defaults,rescue:state.rescue,vision_sidecar:state.vision_sidecar,ui:state.ui,runtime:state.runtime,opencode:state.opencode,expected_bundle_revision:currentBundleRevision(),route_scope_provider_ids:[...touchedProviders],route_refresh_provider_ids:[...staleCleanupProviders]}))}
function renderAll(){renderStatus();renderSaveControls();renderSourceStatus();renderProviders();renderFallback();renderRuntime();renderSettings();renderRefs()}
async function load(){const res=await fetch('/api/state');state=await res.json();state.providers=state.providers||[];loadAcceptanceState(state.tui_webui_mapping||[]);renderNav();renderAll();}
$('addProvider').onclick=()=>{state.providers.push({id:`provider-${state.providers.length+1}`,original_id:'',name:'新通道',enabled:true,role:'auto',priority:100,family_priority_overrides:{},claude_1m_mode:'auto',timezone:'Asia/Singapore',note:'',models_endpoint:'/models',protocols:['anthropic_messages','openai_chat_completions'],supported_clis:['claude','codex','opencode'],openai_base_url:'',anthropic_base_url:'',api_key:'',update_credentials:false,fallback_models:[],extra_models:[],hidden_models:[],models:[]});activeProvider=state.providers.length-1;renderAll()}
$('duplicateProvider').onclick=()=>{const p=JSON.parse(JSON.stringify(current()));p.id=p.id+'-copy';p.original_id='';p.name=p.name+' Copy';p.api_key='';p.pending_api_key=false;p.update_credentials=false;p.has_api_key=false;state.providers.push(p);activeProvider=state.providers.length-1;renderAll()}
$('modelSearch').oninput=renderModelTable
$('addManualModels').onclick=()=>{const p=current();const vals=$('manualModels').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);p.extra_models=[...new Set([...(p.extra_models||[]),...vals])];p.hidden_models=(p.hidden_models||[]).filter(x=>!vals.includes(x));$('manualModels').value='';if(vals.length)touchProvider(p.id);renderModelTable();toast(`已添加 ${vals.length} 个模型`)}
$('clearHidden').onclick=()=>{const p=current();const count=(p.hidden_models||[]).length;p.hidden_models=[];p.stale_hidden_models=[];if(count)touchProvider(p.id);renderModelTable();toast(count?`已取消隐藏 ${count} 个模型`:'当前通道没有隐藏模型')}
$('restoreModelPatch').onclick=()=>{const p=current();const extra=(p.extra_models||[]).length;const hidden=(p.hidden_models||[]).length;p.extra_models=[];p.hidden_models=[];p.stale_hidden_models=[];touchProvider(p.id);renderModelTable();toast(extra||hidden?`已恢复默认模型补丁：清空 ${extra} 个补充 / ${hidden} 个隐藏`:'当前已是默认模型补丁')}
$('clearAllStaleHidden').onclick=cleanupAllStaleHidden
function setTestState(label,ok=null){const box=$('testState');if(!box)return;const cls=ok===false?'off':'';box.innerHTML=`<span class="chip ${cls}">${escapeHtml(label)}</span>`}
function showJson(targetId,data){const target=$(targetId);if(target)target.textContent=JSON.stringify(data,null,2)}
async function runProviderModelsTest({targetId='testResult',switchToTest=false,applyToCurrent=false}={}){syncProvider();const target=$(targetId);if(target)target.textContent='测试 /models 中...';setTestState('models endpoint 测试中');const data=await api('/api/provider/test',{provider:current(),force_refresh:true});showJson(targetId,data);setTestState(data.ok?'models endpoint 正常':'models endpoint 失败',data.ok);if(switchToTest)setSection('test');if(applyToCurrent&&data.ok&&Array.isArray(data.models)){const p=current();if(!p.approved_route_models||!p.approved_route_models.length){p.approved_route_models=(p.models||[]).filter(r=>r&&r.id&&r.source!=='derived_alias').map(r=>r.id)}p.models=data.models.map(id=>({id,source:data.base_source||'remote',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)}));touchProvider(p.id);if($('autoStaleCleanupOnFetch')?.checked&&staleRouteModels(p).length){staleCleanupProviders.add(p.id)}renderModelTable()}return data}
$('fetchModels').onclick=async()=>{const data=await runProviderModelsTest({targetId:'modelConfigResult',applyToCurrent:true});if(data.ok&&Array.isArray(data.models)){toast(staleCleanupProviders.has(current()?.id)?`拉取到 ${data.models.length} 个模型；已自动标记缺失旧 route 清理`:`拉取到 ${data.models.length} 个模型；不会自动写入 fallback_models；缺失旧 route 默认保留`)}else{toast(data.error||'模型拉取失败，请看模型配置结果')}}
$('testList').onclick=async()=>{await runProviderModelsTest({targetId:'modelConfigResult',switchToTest:true})}
$('openModelTest').onclick=()=>{renderTestSelectors();setSection('test')}
$('testListBtn').onclick=async()=>{await runProviderModelsTest({targetId:'testResult'})}
async function runSelectedModelTest(path,label){$('testResult').textContent=`${label} 测试中...`;setTestState(`${label} 测试中`);const data=await api(path,{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2);setTestState(data.ok?`${label} 成功`:`${label} 失败`,data.ok)}
$('testModelBtn').onclick=async()=>runSelectedModelTest('/api/model/test','ping')
$('chatTestBtn').onclick=async()=>runSelectedModelTest('/api/chat/test','chat')
$('previewPlan').onclick=async()=>{const data=await api('/api/plan',{draft:draft()});lastPlan=data;renderSaveControls();renderReviewSummary(data);$('saveResult').textContent=JSON.stringify({ok:data.ok,summary:data.summary,registry_v2_save_plan:data.registry_v2_save_plan,warnings:data.warnings,errors:data.errors,risks:data.review_summary?.risks},null,2);$('diffBox').textContent=[data.diffs?.config_toml,data.diffs?.model_policy_json,data.diffs?.credentials].filter(Boolean).join('\n')||'没有配置变化';toast(data.ok?'预览已生成':'预览有错误')}
function currentApplyCommand(){return lastPlan?.registry_v2_save_plan?.apply_plan?.cli_apply_command||'./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json'}
$('downloadPlanJson').onclick=()=>{if(!lastPlan){toast('请先生成保存预览');return}const blob=new Blob([JSON.stringify(lastPlan,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=lastPlan?.registry_v2_save_plan?.plan_json?.name||'webui-plan.json';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast('已下载脱敏 plan JSON')}
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
