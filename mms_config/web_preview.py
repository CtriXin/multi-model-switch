# -*- coding: utf-8 -*-
"""Preview bundle and config-root helpers for the MMS config WebUI."""

from __future__ import annotations

import copy
import os
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


def _normalize_model_list(value: Any) -> list[str]:
    return _call_backend("_normalize_model_list", value)


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _load_json_file(path: str) -> dict[str, Any]:
    return _call_backend("_load_json_file", path)


def _version_info_for_snapshot_impl(command_name: str = "mms") -> dict[str, Any]:
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


def _policy_path_for_config_impl(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.join(os.path.dirname(config_path), "model-policy.json")
    try:
        from mms_registry import router as mms_router

        return str(getattr(mms_router, "MODEL_POLICY_PATH", ""))
    except Exception:
        return ""


def _config_root_for_snapshot_impl(config_path: str = "") -> str:
    config_path = os.path.abspath(os.path.expanduser(str(config_path or ""))) if config_path else ""
    if config_path:
        return os.path.dirname(config_path)
    try:
        from mms_runtime.state_io import resolve_mms_config_dir

        return resolve_mms_config_dir()
    except Exception:
        return ""


def _model_source_status_for_snapshot_impl(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
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


def _consumer_bundle_status_for_snapshot_impl(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
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


def _is_preview_config_root_impl(config_path: str = "", *, command_name: str = "mms") -> bool:
    config_root = _config_root_for_snapshot(config_path)
    if not config_root:
        return False
    try:
        from mms_runtime.state_io import mms_config_root_status

        return mms_config_root_status(command=command_name, config_dir=config_root).get("mode") == "preview"
    except Exception:
        return False


def _is_placeholder_provider_config_impl(cfg: dict[str, Any]) -> bool:
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


def _read_json_from_verified_file_impl(verified_files: dict[str, Any], key: str) -> dict[str, Any]:
    row = verified_files.get(key) if isinstance(verified_files.get(key), dict) else {}
    path = _safe_text(row.get("path"))
    if not path:
        return {}
    return _load_json_file(path)


def _preview_secret_refs_by_provider_impl(config_root: str = "") -> dict[str, str]:
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


def _preview_secret_values_by_ref_impl(config_root: str = "") -> dict[str, str]:
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


def _preview_cached_provider_url_impl(provider_id: str) -> str:
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


def _resolve_preview_provider_secret_impl(
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


def _attach_preview_secret_refs_impl(
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


def _preview_bundle_config_from_verified_files_impl(verified_files: dict[str, Any], *, config_root: str = "") -> dict[str, Any]:
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


def _hydrate_preview_config_from_latest_bundle_impl(
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


def _config_v2_promotion_plan_for_snapshot_impl(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
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


def _config_v2_release_readiness_for_snapshot_impl(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
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


def _version_info_for_snapshot(command_name: str = "mms") -> dict[str, Any]:
    return _call_backend_override("_version_info_for_snapshot", _version_info_for_snapshot_impl, command_name)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend_override("_policy_path_for_config", _policy_path_for_config_impl, config_path)


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _call_backend_override("_config_root_for_snapshot", _config_root_for_snapshot_impl, config_path)


def _model_source_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend_override("_model_source_status_for_snapshot", _model_source_status_for_snapshot_impl, config_path, command_name=command_name)


def _consumer_bundle_status_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend_override("_consumer_bundle_status_for_snapshot", _consumer_bundle_status_for_snapshot_impl, config_path, command_name=command_name)


def _is_preview_config_root(config_path: str = "", *, command_name: str = "mms") -> bool:
    return _call_backend_override("_is_preview_config_root", _is_preview_config_root_impl, config_path, command_name=command_name)


def _is_placeholder_provider_config(cfg: dict[str, Any]) -> bool:
    return _call_backend_override("_is_placeholder_provider_config", _is_placeholder_provider_config_impl, cfg)


def _read_json_from_verified_file(verified_files: dict[str, Any], key: str) -> dict[str, Any]:
    return _call_backend_override("_read_json_from_verified_file", _read_json_from_verified_file_impl, verified_files, key)


def _preview_secret_refs_by_provider(config_root: str = "") -> dict[str, str]:
    return _call_backend_override("_preview_secret_refs_by_provider", _preview_secret_refs_by_provider_impl, config_root)


def _preview_secret_values_by_ref(config_root: str = "") -> dict[str, str]:
    return _call_backend_override("_preview_secret_values_by_ref", _preview_secret_values_by_ref_impl, config_root)


def _preview_cached_provider_url(provider_id: str) -> str:
    return _call_backend_override("_preview_cached_provider_url", _preview_cached_provider_url_impl, provider_id)


def _resolve_preview_provider_secret(
    provider: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    return _call_backend_override("_resolve_preview_provider_secret", _resolve_preview_provider_secret_impl, provider, config_path=config_path, command_name=command_name)


def _attach_preview_secret_refs(
    cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    return _call_backend_override("_attach_preview_secret_refs", _attach_preview_secret_refs_impl, cfg, config_path=config_path, command_name=command_name)


def _preview_bundle_config_from_verified_files(verified_files: dict[str, Any], *, config_root: str = "") -> dict[str, Any]:
    return _call_backend_override("_preview_bundle_config_from_verified_files", _preview_bundle_config_from_verified_files_impl, verified_files, config_root=config_root)


def _hydrate_preview_config_from_latest_bundle(
    current_cfg: dict[str, Any],
    *,
    config_path: str = "",
    command_name: str = "mms",
) -> dict[str, Any]:
    return _call_backend_override("_hydrate_preview_config_from_latest_bundle", _hydrate_preview_config_from_latest_bundle_impl, current_cfg, config_path=config_path, command_name=command_name)


def _config_v2_promotion_plan_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend_override("_config_v2_promotion_plan_for_snapshot", _config_v2_promotion_plan_for_snapshot_impl, config_path, command_name=command_name)


def _config_v2_release_readiness_for_snapshot(config_path: str = "", *, command_name: str = "mms") -> dict[str, Any]:
    return _call_backend_override("_config_v2_release_readiness_for_snapshot", _config_v2_release_readiness_for_snapshot_impl, config_path, command_name=command_name)

