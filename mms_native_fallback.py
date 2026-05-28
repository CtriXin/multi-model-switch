"""Same-vendor native fallback discovery for MMS bridge runtimes."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from mms_provider_profiles import resolve_provider_profile

_DIRECT_ID_TOKENS = ("direct", "native", "official")
_DEFAULT_TRY_NEXT_ON = (
    401,
    403,
    408,
    409,
    425,
    429,
    500,
    502,
    503,
    504,
    520,
    521,
    522,
    523,
    524,
    "connect_error",
    "timeout",
    "invalid_json",
    "invalid_text",
)


def _clean(value):
    return str(value or "").strip()


def _normalize_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raw = _clean(value).lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return default


def _normalize_model(value):
    model = _clean(value).lower()
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    return model.replace("[1m]", "").strip()


def _normalize_url(value):
    raw = _clean(value).rstrip("/")
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except Exception:
        return raw.lower()
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").rstrip("/").lower()
    return f"{host}{path}"


def _base_url(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    return (
        _clean(runtime.get("anthropic_base_url"))
        or _clean(runtime.get("default_anthropic_base_url"))
        or _clean(runtime.get("openai_base_url"))
        or _clean(runtime.get("default_openai_base_url"))
        or _clean(runtime.get("base_url"))
    )


def _protocols(provider):
    raw = provider.get("protocols") if isinstance(provider, dict) else []
    if isinstance(raw, str):
        raw = [raw]
    return {_clean(item) for item in (raw or []) if _clean(item)}


def _profile_for(runtime, model_name):
    return resolve_provider_profile(
        runtime=runtime if isinstance(runtime, dict) else {},
        provider_id=_clean((runtime or {}).get("id") or (runtime or {}).get("provider_id")),
        base_url=_base_url(runtime),
        model_name=model_name,
        profile_id=_clean((runtime or {}).get("profile") or (runtime or {}).get("provider_profile")),
    )


def _profile_endpoint_urls(profile):
    endpoints = profile.get("endpoints") if isinstance(profile, dict) else {}
    if not isinstance(endpoints, dict):
        return []
    return [
        _clean(endpoints.get("anthropic_base_url")),
        _clean(endpoints.get("openai_base_url")),
    ]


def _url_matches_profile_endpoint(base_url, profile):
    normalized = _normalize_url(base_url)
    if not normalized:
        return False
    for endpoint in _profile_endpoint_urls(profile):
        endpoint_norm = _normalize_url(endpoint)
        if endpoint_norm and normalized.startswith(endpoint_norm):
            return True
    return False


def _provider_looks_native_direct(provider, profile):
    provider_id = _clean(provider.get("id") or provider.get("provider_id")).lower()
    if any(token in provider_id for token in _DIRECT_ID_TOKENS):
        return True
    return _url_matches_profile_endpoint(_base_url(provider), profile)


def _provider_context(cfg, provider_def):
    provider_id = _clean(provider_def.get("id"))
    ctx = dict(provider_def)
    if provider_id:
        try:
            from mms_core import resolve_provider_context

            resolved = resolve_provider_context(cfg, provider_id)
            if isinstance(resolved, dict):
                for key, value in resolved.items():
                    if value not in (None, "") or key not in ctx:
                        ctx[key] = value
        except Exception:
            pass
    return ctx


def _known_models(provider, cfg):
    models = []

    def add_many(values):
        if isinstance(values, str):
            values = [values]
        for item in values or []:
            text = _clean(item)
            if text and text not in models:
                models.append(text)

    add_many(provider.get("models"))
    add_many(provider.get("fallback_models"))
    add_many(provider.get("extra_models"))
    try:
        from mms_core import _load_probe_file_cache, _provider_effective_models

        cached = _load_probe_file_cache(_clean(provider.get("id")), allow_stale=True)
        cached_models = None
        if cached is not None and not cached.get("is_stale"):
            cached_models = list((cached or {}).get("raw_models") or [])
        add_many(_provider_effective_models(provider, cached_models, cfg))
    except Exception:
        pass
    return models


def _provider_has_model(provider, cfg, model_name):
    wanted = _normalize_model(model_name)
    if not wanted:
        return False
    return any(_normalize_model(item) == wanted for item in _known_models(provider, cfg))


def _load_runtime_config():
    try:
        from mms_state_io import mms_config_root_mode

        if mms_config_root_mode() == "preview":
            return {}
    except Exception:
        pass
    try:
        from mms_core import apply_local_overrides, load_config

        cfg = load_config()
        return apply_local_overrides(cfg) if cfg else {}
    except Exception:
        return {}


def _enabled_for_runtime(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    env_flag = os.environ.get("MMS_NATIVE_FALLBACK")
    if env_flag is not None and not _normalize_bool(env_flag, default=True):
        return False
    return _normalize_bool(runtime.get("native_fallback"), default=True)


def _fallback_gateway_url(provider):
    anthropic_url = _clean(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url"))
    if not anthropic_url:
        return ""
    gateway_url = anthropic_url.rstrip("/")
    if not gateway_url.endswith("/v1"):
        gateway_url += "/v1"
    return gateway_url


def _fallback_openai_url(provider):
    openai_url = _clean(provider.get("openai_base_url") or provider.get("default_openai_base_url"))
    if openai_url:
        return openai_url.rstrip("/")
    openai_url = _clean(provider.get("base_url"))
    if not openai_url:
        return ""
    gateway_url = openai_url.rstrip("/")
    if not gateway_url.endswith("/v1"):
        gateway_url += "/v1"
    return gateway_url


def _supports_cli(provider, cli_name):
    supported = provider.get("supported_clis") if isinstance(provider, dict) else []
    if isinstance(supported, str):
        supported = [supported]
    supported = {_clean(item).lower() for item in (supported or []) if _clean(item)}
    return not supported or cli_name in supported


def resolve_native_fallback_routes(runtime, model_name, *, cfg=None, max_routes=None):
    """Return explicit same-vendor native Anthropic routes for a selected runtime.

    The result is in-memory bridge metadata only; this function does not write
    MMS config and does not probe remote providers synchronously.
    """
    runtime = runtime if isinstance(runtime, dict) else {}
    model_name = _clean(model_name)
    if not model_name or not _enabled_for_runtime(runtime):
        return []
    if runtime.get("auth_mode") not in {None, "", "api_key"}:
        return []

    current_profile_id, current_profile = _profile_for(runtime, model_name)
    if not current_profile_id or not current_profile:
        return []

    cfg = cfg if isinstance(cfg, dict) else _load_runtime_config()
    providers = cfg.get("providers") if isinstance(cfg, dict) else []
    if not isinstance(providers, list):
        return []

    current_id = _clean(runtime.get("id") or runtime.get("provider_id"))
    current_urls = {
        _normalize_url(_clean(runtime.get("anthropic_base_url") or runtime.get("default_anthropic_base_url"))),
        _normalize_url(_clean(runtime.get("openai_base_url") or runtime.get("default_openai_base_url"))),
    }
    current_urls.discard("")
    try:
        limit = int(max_routes if max_routes is not None else runtime.get("native_fallback_max") or 1)
    except Exception:
        limit = 1
    limit = max(0, limit)
    if limit <= 0:
        return []

    candidates = []
    for provider_def in providers:
        if not isinstance(provider_def, dict) or not provider_def.get("enabled", True):
            continue
        provider_id = _clean(provider_def.get("id"))
        if not provider_id or provider_id == current_id:
            continue
        provider = _provider_context(cfg, provider_def)
        if "anthropic_messages" not in _protocols(provider):
            continue
        gateway_url = _fallback_gateway_url(provider)
        if not gateway_url or not provider.get("api_key"):
            continue
        provider_profile_id, provider_profile = _profile_for(provider, model_name)
        if provider_profile_id != current_profile_id:
            continue
        if not _provider_looks_native_direct(provider, provider_profile):
            continue
        route_urls = {
            _normalize_url(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url")),
            _normalize_url(provider.get("openai_base_url") or provider.get("default_openai_base_url")),
        }
        route_urls.discard("")
        if route_urls and route_urls == current_urls:
            continue
        if not _provider_has_model(provider, cfg, model_name):
            continue
        try:
            from mms_core import _normalize_priority, _normalize_role, _runtime_priority_for_model, ROLE_WEIGHTS

            role_weight = ROLE_WEIGHTS.get(_normalize_role(provider.get("role", "fallback")), 1)
            priority = _runtime_priority_for_model(provider, model_name)
            sort_key = (role_weight, -_normalize_priority(priority), provider_id)
        except Exception:
            sort_key = (1, 0, provider_id)
        candidates.append((sort_key, {
            "provider_id": provider_id,
            "provider_profile": _clean(provider.get("profile") or provider.get("provider_profile") or provider_profile_id),
            "gateway_url": gateway_url,
            "gateway_key": str(provider.get("api_key") or ""),
            "openai_url": _clean(provider.get("openai_base_url") or provider.get("default_openai_base_url")),
            "proxy_url": _clean(provider.get("proxy")),
            "no_proxy": _clean(provider.get("no_proxy")),
            "model": model_name,
            "protocol": "anthropic_messages",
            "fallback_reason": "same_vendor_native_direct",
            "try_next_on": list(_DEFAULT_TRY_NEXT_ON),
        }))

    candidates.sort(key=lambda item: item[0])
    return [route for _sort_key, route in candidates[:limit]]


def resolve_codex_responses_fallback_routes(runtime, model_name, *, cfg=None, max_routes=None):
    """Return configured Codex OpenAI-compatible fallback routes for Responses bridge.

    This is an in-memory launch-time fallback list only. It does not probe or
    write MMS config, and it stays within configured api_key runtimes.
    """
    runtime = runtime if isinstance(runtime, dict) else {}
    model_name = _clean(model_name)
    if not model_name or not _enabled_for_runtime(runtime):
        return []
    if runtime.get("auth_mode") not in {None, "", "api_key"}:
        return []

    current_profile_id, current_profile = _profile_for(runtime, model_name)
    if not current_profile_id or not current_profile:
        return []

    cfg = cfg if isinstance(cfg, dict) else _load_runtime_config()
    providers = cfg.get("providers") if isinstance(cfg, dict) else []
    if not isinstance(providers, list):
        return []

    current_id = _clean(runtime.get("id") or runtime.get("provider_id"))
    current_urls = {
        _normalize_url(_clean(runtime.get("openai_base_url") or runtime.get("default_openai_base_url"))),
        _normalize_url(_clean(runtime.get("base_url"))),
    }
    current_urls.discard("")
    try:
        limit = int(max_routes if max_routes is not None else runtime.get("native_fallback_max") or 2)
    except Exception:
        limit = 2
    limit = max(0, limit)
    if limit <= 0:
        return []

    candidates = []
    for provider_def in providers:
        if not isinstance(provider_def, dict) or not provider_def.get("enabled", True):
            continue
        provider_id = _clean(provider_def.get("id"))
        if not provider_id or provider_id == current_id:
            continue
        provider = _provider_context(cfg, provider_def)
        if not _supports_cli(provider, "codex"):
            continue
        if "openai_chat_completions" not in _protocols(provider):
            continue
        gateway_url = _fallback_openai_url(provider)
        if not gateway_url or not provider.get("api_key"):
            continue
        provider_profile_id, _provider_profile = _profile_for(provider, model_name)
        if provider_profile_id != current_profile_id:
            continue
        route_urls = {
            _normalize_url(provider.get("openai_base_url") or provider.get("default_openai_base_url")),
            _normalize_url(provider.get("base_url")),
        }
        route_urls.discard("")
        if route_urls and route_urls == current_urls:
            continue
        if not _provider_has_model(provider, cfg, model_name):
            continue
        try:
            from mms_core import _normalize_priority, _normalize_role, _runtime_priority_for_model, ROLE_WEIGHTS

            role_weight = ROLE_WEIGHTS.get(_normalize_role(provider.get("role", "fallback")), 1)
            priority = _runtime_priority_for_model(provider, model_name)
            sort_key = (role_weight, -_normalize_priority(priority), provider_id)
        except Exception:
            sort_key = (1, 0, provider_id)
        candidates.append((sort_key, {
            "provider_id": provider_id,
            "provider_profile": _clean(provider.get("profile") or provider.get("provider_profile") or provider_profile_id),
            "gateway_url": gateway_url,
            "gateway_key": str(provider.get("api_key") or ""),
            "openai_url": gateway_url,
            "proxy_url": _clean(provider.get("proxy")),
            "no_proxy": _clean(provider.get("no_proxy")),
            "model": model_name,
            "protocol": "responses",
            "fallback_reason": "codex_responses_fallback",
            "try_next_on": list(_DEFAULT_TRY_NEXT_ON),
        }))

    candidates.sort(key=lambda item: item[0])
    return [route for _sort_key, route in candidates[:limit]]
