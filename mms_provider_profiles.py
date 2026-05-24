"""Declarative provider/model compatibility profiles for MMS.

Profiles keep vendor-specific request/header differences in data files instead of
scattering special cases through launcher, bridge, and single-dispatch code.
"""

from __future__ import annotations

import copy
import json
import os
from functools import lru_cache
from typing import Any

from mms_state_io import resolve_mms_config_dir

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
_BUILTIN_PROFILE_PATH = os.path.join(_REPO_ROOT, "config", "provider-profiles.json")
_USER_PROFILE_BASENAMES = (
    "provider-profiles.json",
    "model-profiles.json",
)
DEFAULT_HTTP_USER_AGENT = "MMS/1.0"


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    if override is None:
        return base
    return copy.deepcopy(override)


def _load_latest_approved_profiles(config_dir: str) -> dict[str, Any]:
    try:
        import mms_registry
    except Exception:
        return {}
    payload = mms_registry.try_load_latest_approved_payload("profile", config_dir=config_dir)
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def load_provider_profiles() -> dict[str, Any]:
    """Load built-in profiles plus verified latest-approved or legacy overlays."""
    loaded = _read_json(_BUILTIN_PROFILE_PATH)
    profiles = loaded if loaded else {"schema_version": 1, "profiles": {}}
    config_dir = resolve_mms_config_dir()
    approved_payload = _load_latest_approved_profiles(config_dir)
    if approved_payload:
        profiles = _deep_merge(profiles, approved_payload)
        if not isinstance(profiles.get("profiles"), dict):
            profiles["profiles"] = {}
        return profiles
    for basename in _USER_PROFILE_BASENAMES:
        user_payload = _read_json(os.path.join(config_dir, basename))
        if user_payload:
            profiles = _deep_merge(profiles, user_payload)
    if not isinstance(profiles.get("profiles"), dict):
        profiles["profiles"] = {}
    return profiles


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def default_http_user_agent() -> str:
    """Stable default for MMS-owned HTTP probes/relays.

    Some relay front doors challenge Python's default urllib/httpx user agents
    before the request reaches the provider. Keep this explicit and overridable.
    """
    return _clean(os.environ.get("MMS_HTTP_USER_AGENT")) or DEFAULT_HTTP_USER_AGENT


def ensure_default_user_agent(headers: dict[str, str]) -> dict[str, str]:
    """Set a safe MMS User-Agent unless the caller/client already supplied one."""
    if not isinstance(headers, dict):
        return headers
    if not any(_lower(key) == "user-agent" for key in headers):
        headers["User-Agent"] = default_http_user_agent()
    return headers


def _normalize_model(model_name: Any) -> str:
    model = _lower(model_name)
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    return model


def _profile_match_score(profile_id: str, profile: dict[str, Any], *, provider_id: str, base_url: str, model_name: str) -> int:
    match = profile.get("match") if isinstance(profile.get("match"), dict) else {}
    if match.get("profile_only"):
        return 0
    score = 0
    provider_l = _lower(provider_id)
    base_l = _lower(base_url)
    model_l = _normalize_model(model_name)

    for item in match.get("provider_id_contains") or []:
        token = _lower(item)
        if token and token in provider_l:
            score = max(score, 70)
    for item in match.get("base_url_contains") or []:
        token = _lower(item)
        if token and token in base_l:
            score = max(score, 90)
    for item in match.get("model_prefixes") or []:
        token = _lower(item)
        if token and model_l.startswith(token):
            score = max(score, 50)
    if profile_id and profile_id in {provider_l, model_l}:
        score = max(score, 80)
    return score


def resolve_provider_profile(
    *,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    model_name: str = "",
    profile_id: str = "",
) -> tuple[str, dict[str, Any]]:
    """Resolve the best declarative profile for a runtime/model.

    Explicit runtime/profile beats auto-detection. Return (id, profile); both are
    empty when nothing matches.
    """
    runtime = runtime or {}
    profiles = load_provider_profiles().get("profiles") or {}
    explicit = _clean(profile_id or runtime.get("profile") or runtime.get("provider_profile"))
    if explicit and isinstance(profiles.get(explicit), dict):
        return explicit, copy.deepcopy(profiles[explicit])

    provider = _clean(provider_id or runtime.get("id") or runtime.get("provider_id"))
    base = _clean(
        base_url
        or runtime.get("openai_base_url")
        or runtime.get("anthropic_base_url")
        or runtime.get("base_url")
    )
    model = _clean(model_name or runtime.get("model"))
    best_id = ""
    best_profile: dict[str, Any] = {}
    best_score = 0
    for candidate_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        score = _profile_match_score(candidate_id, profile, provider_id=provider, base_url=base, model_name=model)
        if score > best_score:
            best_id = str(candidate_id)
            best_profile = profile
            best_score = score
    if not best_id:
        hinted_id = _relay_model_profile_hint(provider_id=provider, base_url=base, model_name=model)
        hinted_profile = profiles.get(hinted_id)
        if isinstance(hinted_profile, dict):
            return hinted_id, copy.deepcopy(hinted_profile)
        return "", {}
    return best_id, copy.deepcopy(best_profile)


def _lookup_model_override(profile: dict[str, Any], model_name: str) -> dict[str, Any]:
    overrides = profile.get("model_overrides") if isinstance(profile.get("model_overrides"), dict) else {}
    model = _normalize_model(model_name)
    best_key = ""
    best_value: dict[str, Any] = {}
    for key, value in overrides.items():
        key_l = _lower(key)
        if not key_l or not model.startswith(key_l):
            continue
        if len(key_l) > len(best_key) and isinstance(value, dict):
            best_key = key_l
            best_value = value
    return best_value


def _effective_section(profile: dict[str, Any], section: str, model_name: str) -> dict[str, Any]:
    base = profile.get(section) if isinstance(profile.get(section), dict) else {}
    override = _lookup_model_override(profile, model_name).get(section)
    if isinstance(override, dict):
        return _deep_merge(base, override)
    return copy.deepcopy(base)


def profile_thinking_capabilities(
    model_name: str,
    *,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    profile_id: str = "",
) -> dict[str, Any]:
    profile_id, profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        model_name=model_name,
        profile_id=profile_id,
    )
    if not profile:
        return {"profile": "", "thinking_supported": False, "effort_supported": False}
    thinking = _effective_section(profile, "thinking", model_name)
    effort = _effective_section(profile, "effort", model_name)
    effort_allowed: set[str] = set()
    effort_map: dict[str, str] = {}
    effort_default = ""
    for config in effort.values():
        if not isinstance(config, dict) or not config.get("path"):
            continue
        effort_allowed.update(_lower(item) for item in (config.get("allowed") or []) if _lower(item))
        if isinstance(config.get("map"), dict):
            effort_map.update({_lower(key): _lower(value) for key, value in config["map"].items() if _lower(key)})
        if not effort_default:
            effort_default = _lower(config.get("default"))
    return {
        "profile": profile_id,
        "thinking_supported": bool(thinking.get("supported")),
        "effort_supported": any(isinstance(v, dict) and v.get("path") for v in effort.values()),
        "effort_allowed": sorted(effort_allowed),
        "effort_map": effort_map,
        "effort_default": effort_default,
        "ui": thinking.get("ui") or "",
        "default_enabled": thinking.get("default_enabled"),
    }


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in str(path or "").split(".") if part]
    if not parts:
        return
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    if value is _DELETE:
        cursor.pop(parts[-1], None)
    else:
        cursor[parts[-1]] = copy.deepcopy(value)


def _delete_path(payload: dict[str, Any], path: str) -> None:
    parts = [part for part in str(path or "").split(".") if part]
    if not parts:
        return
    stack: list[tuple[dict[str, Any], str]] = []
    cursor: dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            return
        stack.append((cursor, part))
        cursor = child
    cursor.pop(parts[-1], None)
    for parent, key in reversed(stack):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
        else:
            break


def _has_path(payload: dict[str, Any], path: str) -> bool:
    parts = [part for part in str(path or "").split(".") if part]
    if not parts:
        return False
    cursor: Any = payload
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return False
        cursor = cursor[part]
    return True


def _get_path(payload: dict[str, Any], path: str) -> Any:
    parts = [part for part in str(path or "").split(".") if part]
    cursor: Any = payload
    for part in parts:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


class _DeleteSentinel:
    pass


_DELETE = _DeleteSentinel()


def _apply_patch_map(payload: dict[str, Any], patch: dict[str, Any]) -> None:
    for path, value in (patch or {}).items():
        if value == "__delete__":
            _delete_path(payload, path)
        else:
            _set_path(payload, path, value)


def _apply_parameter_aliases(payload: dict[str, Any], profile: dict[str, Any], protocol: str) -> None:
    aliases = profile.get("parameter_aliases") if isinstance(profile.get("parameter_aliases"), dict) else {}
    protocol_aliases = aliases.get(protocol) if isinstance(aliases.get(protocol), dict) else {}
    for source, target in protocol_aliases.items():
        source_path = str(source or "").strip()
        target_path = str(target or "").strip()
        if not source_path or not target_path or not _has_path(payload, source_path):
            continue
        value = _get_path(payload, source_path)
        if not _has_path(payload, target_path):
            _set_path(payload, target_path, value)
        _delete_path(payload, source_path)


def _normalize_effort(value: Any, config: dict[str, Any]) -> str:
    raw = _lower(value or config.get("default") or "")
    mapping = config.get("map") if isinstance(config.get("map"), dict) else {}
    if raw in mapping:
        raw = _lower(mapping[raw])
    allowed = [_lower(item) for item in (config.get("allowed") or []) if _lower(item)]
    if allowed and raw not in allowed:
        default = _lower(config.get("default"))
        return default if default in allowed else allowed[0]
    return raw or _lower(config.get("default"))


def _normalize_budget(value: Any, config: dict[str, Any]) -> int | None:
    raw = value if value not in (None, "") else config.get("default")
    mapping = config.get("map") if isinstance(config.get("map"), dict) else {}
    raw_key = _lower(raw)
    if raw_key in mapping:
        raw = mapping[raw_key]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _relay_model_profile_hint(*, provider_id: str, base_url: str, model_name: str) -> str:
    provider_l = _lower(provider_id)
    base_l = _lower(base_url)
    model_l = _normalize_model(model_name)
    is_newapi_relay = "newapi" in provider_l or "newapi" in base_l
    if is_newapi_relay and (model_l.startswith("qwen") or model_l.startswith("qwq")):
        return "dashscope-openai"
    return ""


def apply_profile_body_patches(
    payload: dict[str, Any],
    *,
    protocol: str,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    model_name: str = "",
    profile_id: str = "",
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    purpose: str = "default",
) -> str:
    """Apply declarative request-body patches in place. Return profile id."""
    if not isinstance(payload, dict):
        return ""
    profile_id, profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        model_name=model_name or payload.get("model", ""),
        profile_id=profile_id,
    )
    if not profile:
        return ""

    protocol_patches = (profile.get("body_patches") or {}).get(protocol)
    if isinstance(protocol_patches, dict):
        if purpose and purpose != "default" and isinstance(protocol_patches.get(purpose), dict):
            _apply_patch_map(payload, protocol_patches[purpose])
        else:
            thinking = _effective_section(profile, "thinking", model_name or payload.get("model", ""))
            effective_enabled = thinking_enabled
            if effective_enabled is None:
                default_enabled = thinking.get("default_enabled")
                effective_enabled = default_enabled if isinstance(default_enabled, bool) else None
            patch_key = "thinking_on" if effective_enabled is True else "thinking_off" if effective_enabled is False else ""
            if patch_key and isinstance(protocol_patches.get(patch_key), dict):
                _apply_patch_map(payload, protocol_patches[patch_key])

    effort_by_protocol = _effective_section(profile, "effort", model_name or payload.get("model", ""))
    effort_config = effort_by_protocol.get(protocol) if isinstance(effort_by_protocol.get(protocol), dict) else {}
    if effort_config.get("path"):
        thinking = _effective_section(profile, "thinking", model_name or payload.get("model", ""))
        effective_enabled = thinking_enabled
        if effective_enabled is None:
            default_enabled = thinking.get("default_enabled")
            effective_enabled = default_enabled if isinstance(default_enabled, bool) else None
        if effective_enabled is False:
            _delete_path(payload, str(effort_config["path"]))
        else:
            effort_value = _normalize_effort(reasoning_effort, effort_config)
            if effort_value:
                _set_path(payload, str(effort_config["path"]), effort_value)

    budget_by_protocol = _effective_section(profile, "budget", model_name or payload.get("model", ""))
    budget_config = budget_by_protocol.get(protocol) if isinstance(budget_by_protocol.get(protocol), dict) else {}
    if budget_config.get("path"):
        thinking = _effective_section(profile, "thinking", model_name or payload.get("model", ""))
        effective_enabled = thinking_enabled
        if effective_enabled is None:
            default_enabled = thinking.get("default_enabled")
            effective_enabled = default_enabled if isinstance(default_enabled, bool) else None
        if effective_enabled is False:
            _delete_path(payload, str(budget_config["path"]))
        else:
            budget_value = _normalize_budget(reasoning_effort, budget_config)
            if budget_value is not None:
                _set_path(payload, str(budget_config["path"]), budget_value)
    _apply_parameter_aliases(payload, profile, protocol)
    return profile_id


def apply_profile_auth_headers(
    headers: dict[str, str],
    *,
    protocol: str,
    api_key: str,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    model_name: str = "",
    profile_id: str = "",
) -> str:
    """Apply profile-defined auth headers in place. Return profile id."""
    if not isinstance(headers, dict):
        return ""
    ensure_default_user_agent(headers)
    profile_id, profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        model_name=model_name,
        profile_id=profile_id,
    )
    if not profile or not api_key:
        return profile_id
    auth = profile.get("auth_headers") if isinstance(profile.get("auth_headers"), dict) else {}
    for spec in auth.get(protocol) or []:
        normalized = _lower(spec)
        if normalized == "authorization_bearer":
            headers.setdefault("Authorization", f"Bearer {api_key}")
        elif normalized == "x-api-key":
            headers.setdefault("x-api-key", api_key)
        elif normalized == "api-key":
            headers.setdefault("api-key", api_key)
    return profile_id


def profile_context_window(
    model_name: str,
    *,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    profile_id: str = "",
) -> int | None:
    profile_id, profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        model_name=model_name,
        profile_id=profile_id,
    )
    if not profile_id:
        return None
    windows = profile.get("context_windows") if isinstance(profile.get("context_windows"), dict) else {}
    model = _normalize_model(model_name)
    best_len = 0
    best_value = None
    for key, value in windows.items():
        key_l = _lower(key)
        if key_l and model.startswith(key_l) and len(key_l) > best_len:
            try:
                best_value = int(value)
            except (TypeError, ValueError):
                best_value = None
            best_len = len(key_l)
    return best_value


def profile_model_alias(
    model_name: str,
    *,
    protocol: str,
    runtime: dict[str, Any] | None = None,
    provider_id: str = "",
    base_url: str = "",
    profile_id: str = "",
) -> str:
    """Return provider wire-model override for a protocol, if configured."""
    profile_id, profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        model_name=model_name,
        profile_id=profile_id,
    )
    if not profile_id:
        return ""
    aliases = profile.get("model_aliases") if isinstance(profile.get("model_aliases"), dict) else {}
    protocol_aliases = aliases.get(protocol) if isinstance(aliases.get(protocol), dict) else {}
    if not protocol_aliases:
        protocol_aliases = {key: value for key, value in aliases.items() if not isinstance(value, dict)}
    model = _normalize_model(model_name)
    for key, value in protocol_aliases.items():
        conditions = value if isinstance(value, dict) else {}
        alias = _clean(conditions.get("target") if isinstance(conditions, dict) else value)
        if not alias:
            continue
        provider_l = _lower(provider_id)
        base_l = _lower(base_url)
        provider_tokens = [_lower(item) for item in (conditions.get("provider_id_contains") or []) if _lower(item)]
        base_tokens = [_lower(item) for item in (conditions.get("base_url_contains") or []) if _lower(item)]
        if provider_tokens and not any(token in provider_l for token in provider_tokens):
            continue
        if base_tokens and not any(token in base_l for token in base_tokens):
            continue
        match_target = conditions.get("match_target", True) is not False
        if model == _lower(key) or (match_target and model == _normalize_model(alias)):
            return alias
    return ""


def provider_profile_references() -> dict[str, list[str]]:
    profiles = load_provider_profiles().get("profiles") or {}
    refs: dict[str, list[str]] = {}
    for profile_id, profile in profiles.items():
        if isinstance(profile, dict):
            refs[str(profile_id)] = [str(item) for item in (profile.get("references") or [])]
    return refs
