"""OpenCode session-local provider/config helpers."""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from mms_opencode_agents import (
    opencode_apply_agent_bypass_permissions,
    opencode_committee_agent_configs,
    opencode_debate_agent_configs,
    opencode_lite_agent_configs,
    opencode_lite_pro_agent_configs,
    opencode_review_hub_agent_configs,
)

OPENCODE_PROVIDER_ID = "mms"
OPENCODE_API_KEY_ENV = "MMS_OPENCODE_API_KEY"
OPENCODE_DEFAULT_OUTPUT_LIMIT = 8192
OPENCODE_DEFAULT_CONTEXT_WINDOW = 200_000
OPENCODE_LITE_DEFAULT_AGENT = "mobius-builder"
OPENCODE_BYPASS_FLAG = "--dangerously-skip-permissions"
OPENCODE_BYPASS_PERMISSION_ENV = json.dumps(
    {
        "read": "allow",
        "edit": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "bash": "allow",
        "task": "allow",
        "external_directory": "allow",
        "todowrite": "allow",
        "question": "allow",
        "webfetch": "allow",
        "websearch": "allow",
        "repo_clone": "allow",
        "repo_overview": "allow",
        "lsp": "allow",
        "doom_loop": "allow",
        "skill": "allow",
    },
    separators=(",", ":"),
)
OPENCODE_LAUNCH_PREFLIGHT_TIMEOUT = 35
OPENCODE_LAUNCH_PREFLIGHT_PROMPT = "MMS OpenCode launch preflight. Reply exactly OK and nothing else."
OPENCODE_IMAGE_INPUT_MODELS = set()
OPENCODE_MODEL_LIMIT_OVERRIDES = {}


def opencode_model_names(runtime, selected_model=""):
    seen = set()
    models = []

    def add(value):
        model = str(value or "").strip()
        if model and model not in seen:
            seen.add(model)
            models.append(model)

    add(selected_model)
    if isinstance(runtime, dict):
        add(runtime.get("model"))
        add(runtime.get("default_model"))
        for key in ("models", "fallback_models"):
            values = runtime.get(key)
            if isinstance(values, str):
                add(values)
            elif isinstance(values, (list, tuple)):
                for value in values:
                    add(value)
    return models


def opencode_model_ref(model_name):
    return f"{OPENCODE_PROVIDER_ID}/{model_name}"


def opencode_config_slug(value, default="default"):
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "_"
        for ch in str(value or "").strip()
    ).strip("_")
    return cleaned or default


def opencode_route_provider_ref(route, index=0):
    route = route if isinstance(route, dict) else {}
    route_id = opencode_config_slug(route.get("id") or route.get("provider_id") or index, f"route_{index}")
    return f"{OPENCODE_PROVIDER_ID}-{route_id}"


def opencode_route_env_key(provider_ref):
    suffix = "".join(
        ch.upper() if ch.isalnum() else "_"
        for ch in str(provider_ref or "").strip()
    ).strip("_")
    return f"{OPENCODE_API_KEY_ENV}_{suffix or 'ROUTE'}"


def opencode_route_model_ref(route, index=0):
    route = route if isinstance(route, dict) else {}
    provider_ref = str(route.get("provider_ref") or opencode_route_provider_ref(route, index)).strip()
    model = str(route.get("model") or "").strip()
    if not provider_ref or not model:
        return ""
    return f"{provider_ref}/{model}"


def opencode_provider_base_url(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    explicit = str(runtime.get("opencode_base_url") or "").strip().rstrip("/")
    if explicit:
        return explicit
    base_url = str(runtime.get("openai_base_url") or "").strip().rstrip("/")
    if not base_url:
        base_url = str(runtime.get("base_url") or "").strip().rstrip("/")
        if base_url and not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
    if not base_url:
        return ""
    path = urlsplit(base_url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    if last_segment != "v1":
        return f"{base_url}/v1"
    return base_url


def opencode_runtime_routes(runtime, selected_model=""):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw_routes = runtime.get("opencode_routes")
    if isinstance(raw_routes, list) and raw_routes:
        routes = []
        for index, raw in enumerate(raw_routes):
            if not isinstance(raw, dict):
                continue
            model = str(raw.get("model") or "").strip()
            base_url = str(raw.get("openai_base_url") or raw.get("base_url") or "").strip().rstrip("/")
            anthropic_base_url = str(raw.get("anthropic_base_url") or "").strip().rstrip("/")
            protocol = str(raw.get("protocol") or "").strip()
            if not protocol:
                protocol = "anthropic_messages" if anthropic_base_url and not base_url else "openai_chat_completions"
            api_key = str(raw.get("api_key") or raw.get("openai_api_key") or "").strip()
            provider_base_url = anthropic_base_url if protocol == "anthropic_messages" else base_url
            if not model or not provider_base_url:
                continue
            route = dict(raw)
            route["model"] = model
            route["protocol"] = protocol
            route["openai_base_url"] = base_url
            route["anthropic_base_url"] = anthropic_base_url
            route["api_key"] = api_key
            route["provider_ref"] = str(route.get("provider_ref") or opencode_route_provider_ref(route, index)).strip()
            routes.append(route)
        if routes:
            return routes

    return [
        {
            "id": "default",
            "model": model_name,
            "provider_id": runtime.get("id") or OPENCODE_PROVIDER_ID,
            "provider_name": runtime.get("name") or runtime.get("id") or "MMS",
            "protocol": "openai_chat_completions",
            "openai_base_url": opencode_provider_base_url(runtime),
            "anthropic_base_url": "",
            "api_key": str(runtime.get("openai_api_key") or runtime.get("api_key") or ""),
            "provider_ref": OPENCODE_PROVIDER_ID,
        }
        for model_name in opencode_model_names(runtime, selected_model)
    ]


def opencode_agent_model_refs(runtime, routes):
    runtime = runtime if isinstance(runtime, dict) else {}
    by_key = {
        str(route.get("id") or "").strip(): opencode_route_model_ref(route, index)
        for index, route in enumerate(routes or [])
    }
    refs = {}
    raw = runtime.get("opencode_agent_model_keys")
    if isinstance(raw, dict):
        for agent, key in raw.items():
            ref = by_key.get(str(key or "").strip())
            if ref:
                refs[str(agent)] = ref
    for index, route in enumerate(routes or []):
        key = str(route.get("id") or "").strip()
        ref = opencode_route_model_ref(route, index)
        if key and ref:
            refs.setdefault(key, ref)
    return refs


def opencode_agent_opencode_policies(runtime, routes):
    runtime = runtime if isinstance(runtime, dict) else {}
    policies_by_ref = {}
    for index, route in enumerate(routes or []):
        if not isinstance(route, dict):
            continue
        model_ref = opencode_route_model_ref(route, index)
        model_name = str(route.get("model") or "").strip()
        if not model_ref or not model_name:
            continue
        protocol = str(route.get("protocol") or "").strip()
        base_url = str(route.get("anthropic_base_url") or route.get("openai_base_url") or "").strip()
        # OpenCode agent policy is per route. Do not let a top-level runtime
        # profile force unrelated fallback routes into the same policy bucket.
        route_runtime = {
            key: value
            for key, value in runtime.items()
            if key not in {"profile", "provider_profile"}
        }
        route_runtime["id"] = route.get("provider_id") or runtime.get("id")
        if route.get("provider_profile"):
            route_runtime["provider_profile"] = route.get("provider_profile")
        try:
            from mms_provider_profiles import profile_opencode_policy

            policy = profile_opencode_policy(
                model_name,
                runtime=route_runtime,
                provider_id=str(route.get("provider_id") or runtime.get("id") or ""),
                base_url=base_url,
                profile_id=str(route.get("provider_profile") or ""),
                protocol=_opencode_profile_protocol(protocol),
            )
        except (ImportError, KeyError, TypeError, ValueError):
            policy = {}
        if policy:
            policies_by_ref[model_ref] = policy

    refs = opencode_agent_model_refs(runtime, routes)
    return {
        agent: policies_by_ref[model_ref]
        for agent, model_ref in refs.items()
        if model_ref in policies_by_ref
    }


def opencode_env_bool(name, default=False):
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return bool(default)


def opencode_runtime_bool(runtime, key, default=False):
    runtime = runtime if isinstance(runtime, dict) else {}
    if key not in runtime:
        return bool(default)
    value = runtime.get(key)
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return bool(default)


def opencode_entrypoint(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    raw = str(runtime.get("opencode_entrypoint") or "tui").strip().lower().replace("-", "_")
    if raw in {"backend", "backend_agent", "headless", "server", "serve"}:
        return "serve"
    if raw in {"acp", "editor", "agent_client_protocol"}:
        return "acp"
    return "tui"


def opencode_launch_preflight_enabled(runtime):
    default = opencode_runtime_bool(runtime, "opencode_launch_preflight", False)
    return opencode_env_bool("MMS_OPENCODE_LAUNCH_PREFLIGHT", default)


def opencode_preflight_timeout():
    raw = str(os.environ.get("MMS_OPENCODE_PREFLIGHT_TIMEOUT") or "").strip()
    if not raw:
        return OPENCODE_LAUNCH_PREFLIGHT_TIMEOUT
    try:
        return max(0, int(raw)) or OPENCODE_LAUNCH_PREFLIGHT_TIMEOUT
    except ValueError:
        return OPENCODE_LAUNCH_PREFLIGHT_TIMEOUT


def opencode_route_by_id(routes):
    indexed = {}
    for index, route in enumerate(routes or []):
        key = str((route or {}).get("id") or "").strip()
        if key and key not in indexed:
            indexed[key] = (index, route)
    return indexed


def opencode_launch_candidates(runtime, routes, selected_model=""):
    """Build deterministic launch failover candidates without random routing."""
    runtime = runtime if isinstance(runtime, dict) else {}
    routes = routes or []
    candidates = []
    seen = set()
    default_route_key = str(runtime.get("opencode_default_route_key") or "").strip()
    route_keys = []
    if default_route_key:
        route_keys.append(default_route_key)
    configured = runtime.get("opencode_launch_fallback_route_keys")
    if isinstance(configured, str):
        configured = [configured]
    if isinstance(configured, (list, tuple)):
        route_keys.extend(str(item or "").strip() for item in configured)
    if not route_keys and routes:
        route_keys.append(str(routes[0].get("id") or "").strip())

    fallback_agents = runtime.get("opencode_launch_fallback_agents")
    fallback_agents = fallback_agents if isinstance(fallback_agents, dict) else {}
    default_agent = str(runtime.get("opencode_agent", OPENCODE_LITE_DEFAULT_AGENT) or "").strip()
    route_index = opencode_route_by_id(routes)
    for key in route_keys:
        if not key or key in seen:
            continue
        item = route_index.get(key)
        if not item:
            continue
        index, route = item
        model_ref = opencode_route_model_ref(route, index)
        if not model_ref:
            continue
        seen.add(key)
        candidates.append(
            {
                "route_key": key,
                "route": route,
                "model_ref": model_ref,
                "agent": str(fallback_agents.get(key) or default_agent or "").strip(),
            }
        )

    if not candidates and selected_model:
        candidates.append(
            {
                "route_key": "selected_model",
                "route": {},
                "model_ref": opencode_model_ref(selected_model),
                "agent": default_agent,
            }
        )
    return candidates


def opencode_explicit_output_limit(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    for key in ("opencode_output_limit", "output_limit", "max_output_tokens"):
        try:
            value = int(runtime.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def opencode_output_limit(runtime):
    explicit = opencode_explicit_output_limit(runtime)
    if explicit is not None:
        return explicit
    return OPENCODE_DEFAULT_OUTPUT_LIMIT


def opencode_model_limit_override(model_name):
    model = str(model_name or "").strip().lower()
    if "/" in model:
        model = model.rsplit("/", 1)[-1]
    return OPENCODE_MODEL_LIMIT_OVERRIDES.get(model)


def _opencode_model_key(model_name):
    normalized = str(model_name or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    if normalized.endswith("[1m]"):
        normalized = normalized[:-4]
    return normalized


def opencode_model_capabilities(runtime, model_name):
    runtime = runtime if isinstance(runtime, dict) else {}
    caps_map = runtime.get("model_capabilities")
    target = _opencode_model_key(model_name)
    if isinstance(caps_map, dict) and target:
        for key, value in caps_map.items():
            if _opencode_model_key(key) == target and isinstance(value, dict):
                return value
    try:
        from mms_capability_resolver import resolve_model_capabilities

        return resolve_model_capabilities(
            model_name,
            runtime=runtime,
            provider_id=str(runtime.get("id") or runtime.get("provider_id") or ""),
            base_url=str(
                runtime.get("anthropic_base_url")
                or runtime.get("openai_base_url")
                or runtime.get("base_url")
                or ""
            ),
            profile_id=str(runtime.get("profile") or runtime.get("provider_profile") or ""),
        )
    except (ImportError, KeyError, TypeError, ValueError):
        return {}


def _opencode_capability_source(caps, key):
    sources = caps.get("sources") if isinstance(caps, dict) else {}
    if not isinstance(sources, dict):
        return ""
    return str(sources.get(key) or "").strip()


def _opencode_capability_source_allowed(caps, key):
    source = _opencode_capability_source(caps, key)
    return source != "conservative_fallback"


def opencode_capability_int(runtime, model_name, *keys):
    caps = opencode_model_capabilities(runtime, model_name)
    for key in keys:
        if not _opencode_capability_source_allowed(caps, key):
            continue
        try:
            value = int(caps.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def opencode_capability_bool(runtime, model_name, *keys):
    caps = opencode_model_capabilities(runtime, model_name)
    for key in keys:
        if not _opencode_capability_source_allowed(caps, key):
            continue
        if isinstance(caps.get(key), bool):
            return bool(caps[key])
    return None


def _opencode_profile_protocol(protocol):
    raw = str(protocol or "").strip()
    if raw == "openai_responses":
        return "responses"
    if raw == "anthropic_messages":
        return "anthropic_messages"
    return "openai_chat"


def _opencode_runtime_thinking_enabled(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "thinking_mode" not in runtime:
        return None
    raw = str(runtime.get("thinking_mode") or "").strip().lower()
    if raw in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    if raw in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    return None


def _opencode_runtime_effort(runtime, model_name, caps=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    caps = caps if isinstance(caps, dict) else opencode_model_capabilities(runtime, model_name)
    for source in (runtime, caps):
        raw = str(source.get("opencode_reasoning_effort") or source.get("reasoning_effort") or "").strip().lower()
        if raw and raw != "auto":
            return raw
    if not _opencode_capability_source_allowed(caps, "thinking_control"):
        return ""
    control = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    raw = str(control.get("default") or "").strip().lower()
    return raw if raw and raw != "auto" else ""


def _opencode_option_path(path):
    normalized = str(path or "").strip().replace("[", ".").replace("]", "")
    normalized_l = normalized.lower().replace("_", ".")
    if normalized_l in {"reasoning.effort", "reasoningeffort", "reasoning.effort"}:
        return ["reasoningEffort"]
    if normalized_l in {"thinking.budget.tokens", "thinking.budgettokens", "thinking.budget.tokens"}:
        return ["thinking", "budgetTokens"]
    parts = [part for part in normalized.split(".") if part]
    converted = []
    for part in parts:
        if part == "budget_tokens":
            converted.append("budgetTokens")
        elif part == "reasoning_effort":
            converted.append("reasoningEffort")
        else:
            converted.append(part)
    return converted


def _opencode_set_option_path(target, path, value):
    parts = _opencode_option_path(path)
    if not parts:
        return
    cursor = target
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = value


def _opencode_options_from_payload(payload):
    options = {}

    def walk(value, prefix=""):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{prefix}.{key}" if prefix else str(key))
            return
        _opencode_set_option_path(options, prefix, value)

    if isinstance(payload, dict):
        walk(payload)
    return options


def _opencode_deep_merge(base, override):
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _opencode_deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _opencode_options_have_effort_signal(options):
    if not isinstance(options, dict):
        return False

    def walk(value, path=""):
        if isinstance(value, dict):
            return any(walk(child, f"{path}.{key}" if path else str(key)) for key, child in value.items())
        normalized = path.lower()
        return any(token in normalized for token in ("effort", "thinkingbudget", "thinkinglevel", "budgettokens"))

    return walk(options)


def _opencode_normalize_control_value(control, effort, thinking_enabled):
    control = control if isinstance(control, dict) else {}
    path = str(control.get("path") or "").strip()
    path_l = path.lower()
    mapping = control.get("map") if isinstance(control.get("map"), dict) else {}
    value = str(effort or control.get("default") or "").strip().lower()
    if value in mapping:
        value = str(mapping[value] or "").strip().lower()
    if "budget" in path_l:
        raw = mapping.get(value, value) if value else control.get("numeric_budget_tokens") or control.get("default")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if "effort" in path_l or "thinkinglevel" in path_l:
        return value or str(control.get("default") or "").strip().lower() or None
    if path_l.endswith("thinking.type") or path_l == "thinking.type":
        return "disabled" if thinking_enabled is False else "enabled"
    return value or None


def _opencode_control_path_is_request_option(path):
    raw = str(path or "").strip()
    if not raw:
        return False
    normalized = raw.lower().replace("[", ".").replace("]", "").replace("_", ".")
    compact = "".join(ch for ch in normalized if ch.isalnum())
    return compact in {
        "reasoningeffort",
        "outputconfigeffort",
        "thinkingtype",
        "thinkingconfigthinkinglevel",
        "thinkingconfigthinkingbudget",
        "thinkingbudget",
        "thinkingbudgettokens",
        "budgettokens",
    }


def _opencode_options_from_capabilities(runtime, model_name, *, thinking_enabled=None, effort=""):
    caps = opencode_model_capabilities(runtime, model_name)
    if not _opencode_capability_source_allowed(caps, "thinking_control"):
        return {}
    control = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    if not control or control.get("supported") is False:
        return {}
    path = str(control.get("path") or "").strip()
    if not _opencode_control_path_is_request_option(path):
        return {}
    value = _opencode_normalize_control_value(control, effort, thinking_enabled)
    if value is None or value == "":
        return {}
    options = {}
    _opencode_set_option_path(options, path, value)
    return options


def opencode_model_request_options(
    runtime,
    model_name,
    *,
    protocol="",
    provider_id="",
    base_url="",
    reasoning_effort="",
    thinking_enabled=None,
):
    """Build OpenCode model options from MMS capability/provider-profile data."""
    runtime = runtime if isinstance(runtime, dict) else {}
    caps = opencode_model_capabilities(runtime, model_name)
    if thinking_enabled is None:
        thinking_enabled = _opencode_runtime_thinking_enabled(runtime)
    effort = str(reasoning_effort or _opencode_runtime_effort(runtime, model_name, caps)).strip().lower()

    payload = {}
    try:
        from mms_provider_profiles import apply_profile_body_patches

        apply_profile_body_patches(
            payload,
            protocol=_opencode_profile_protocol(protocol),
            runtime=runtime,
            provider_id=provider_id or runtime.get("id") or runtime.get("provider_id") or "",
            base_url=base_url
            or runtime.get("anthropic_base_url")
            or runtime.get("openai_base_url")
            or runtime.get("base_url")
            or "",
            model_name=model_name,
            thinking_enabled=thinking_enabled,
            reasoning_effort=effort or None,
        )
    except (ImportError, KeyError, TypeError, ValueError):
        payload = {}

    profile_options = _opencode_options_from_payload(payload)
    capability_options = _opencode_options_from_capabilities(
        runtime,
        model_name,
        thinking_enabled=thinking_enabled,
        effort=effort,
    )
    return _opencode_deep_merge(capability_options, profile_options)


def _opencode_effort_variant_values(runtime, model_name, *, provider_id="", base_url="", protocol=""):
    values = []

    def add(value):
        raw = str(value or "").strip().lower()
        if raw and raw != "auto" and raw not in values:
            values.append(raw)

    caps = opencode_model_capabilities(runtime, model_name)
    control = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    path = str(control.get("path") or "").strip()
    if _opencode_capability_source_allowed(caps, "thinking_control") and _opencode_control_path_is_request_option(path):
        for item in control.get("allowed") or []:
            add(item)
        if isinstance(control.get("map"), dict):
            for key, value in control["map"].items():
                add(key)
                add(value)
        add(control.get("default"))
    if _opencode_capability_source_allowed(caps, "reasoning_effort"):
        add(caps.get("reasoning_effort"))

    try:
        from mms_provider_profiles import profile_thinking_capabilities

        profile_caps = profile_thinking_capabilities(
            model_name,
            runtime=runtime if isinstance(runtime, dict) else None,
            provider_id=provider_id or runtime.get("id") or runtime.get("provider_id") or "",
            base_url=base_url
            or runtime.get("anthropic_base_url")
            or runtime.get("openai_base_url")
            or runtime.get("base_url")
            or "",
            protocol=_opencode_profile_protocol(protocol),
        )
        for item in profile_caps.get("effort_allowed") or []:
            add(item)
        if isinstance(profile_caps.get("effort_map"), dict):
            for key, value in profile_caps["effort_map"].items():
                add(key)
                add(value)
        add(profile_caps.get("effort_default"))
    except (ImportError, KeyError, TypeError, ValueError):
        pass
    return values


def opencode_model_variants(runtime, model_name, *, protocol="", provider_id="", base_url=""):
    variants = {}
    for effort in _opencode_effort_variant_values(
        runtime,
        model_name,
        provider_id=provider_id,
        base_url=base_url,
        protocol=protocol,
    ):
        options = opencode_model_request_options(
            runtime,
            model_name,
            protocol=protocol,
            provider_id=provider_id,
            base_url=base_url,
            reasoning_effort=effort,
            thinking_enabled=True,
        )
        if options and _opencode_options_have_effort_signal(options):
            variants[effort] = options
    return variants


def _opencode_agent_variant(runtime, route, existing_variant="", variants=None):
    variants = variants if isinstance(variants, dict) else {}
    if not variants:
        return ""
    caps = opencode_model_capabilities(runtime, route.get("model"))
    for value in (runtime.get("opencode_reasoning_effort"), runtime.get("reasoning_effort")):
        raw = str(value or "").strip().lower()
        if raw and raw in variants:
            return raw
    raw_existing = str(existing_variant or "").strip().lower()
    if raw_existing and raw_existing in variants:
        return raw_existing
    raw_cap = str(caps.get("reasoning_effort") or "").strip().lower()
    if raw_cap and raw_cap in variants:
        return raw_cap
    return ""


def opencode_apply_agent_model_variants(agents, runtime, routes):
    if not isinstance(agents, dict):
        return agents
    runtime = runtime if isinstance(runtime, dict) else {}
    route_by_ref = {
        opencode_route_model_ref(route, index): route
        for index, route in enumerate(routes or [])
    }
    updated = {}
    for name, agent in agents.items():
        if not isinstance(agent, dict):
            updated[name] = agent
            continue
        next_agent = dict(agent)
        route = route_by_ref.get(str(next_agent.get("model") or "").strip())
        if route:
            route_runtime = {**runtime, "id": route.get("provider_id") or runtime.get("id")}
            if isinstance(route.get("model_capabilities"), dict):
                route_runtime["model_capabilities"] = route["model_capabilities"]
            if route.get("provider_profile"):
                route_runtime["provider_profile"] = route.get("provider_profile")
            variants = opencode_model_variants(
                route_runtime,
                route.get("model"),
                protocol=route.get("protocol") or "",
                provider_id=route.get("provider_id") or "",
                base_url=route.get("anthropic_base_url") or route.get("openai_base_url") or "",
            )
            variant = _opencode_agent_variant(route_runtime, route, next_agent.get("variant"), variants)
            if variant:
                next_agent["variant"] = variant
            else:
                next_agent.pop("variant", None)
        updated[name] = next_agent
    return updated


def opencode_model_output_limit(runtime, model_name, *, output_limit_resolver=None):
    explicit = opencode_explicit_output_limit(runtime)
    if explicit is not None:
        return explicit
    capability_output = opencode_capability_int(runtime, model_name, "max_output_tokens", "official_max_output_tokens")
    if capability_output is not None:
        return capability_output
    if callable(output_limit_resolver):
        try:
            resolved = int(output_limit_resolver(model_name, provider_id=(runtime or {}).get("id")))
        except (TypeError, ValueError):
            resolved = 0
        if resolved > 0:
            return resolved
    override = opencode_model_limit_override(model_name)
    if isinstance(override, dict):
        try:
            output = int(override.get("output"))
        except (TypeError, ValueError):
            output = 0
        if output > 0:
            return output
    return OPENCODE_DEFAULT_OUTPUT_LIMIT


def opencode_model_requires_reasoning_roundtrip_guard(model_name):
    normalized = str(model_name or "").strip().lower()
    return normalized.startswith("mimo-")


def opencode_model_config(
    runtime,
    model_name,
    *,
    context_window_resolver=None,
    output_limit_resolver=None,
    protocol="",
    provider_id="",
    base_url="",
):
    runtime = runtime if isinstance(runtime, dict) else {}
    model = str(model_name or "").strip()
    config = {"name": model}
    limit_override = opencode_model_limit_override(model)
    context_window = None
    if isinstance(limit_override, dict):
        try:
            context_window = int(limit_override.get("context"))
        except (TypeError, ValueError):
            context_window = None
    if not context_window:
        context_window = opencode_capability_int(runtime, model, "context_window_tokens", "max_context_tokens")
    if not context_window and callable(context_window_resolver):
        context_window = context_window_resolver(
            model,
            enable_claude_1m=False,
            provider_id=runtime.get("id"),
        )
    if not context_window:
        context_window = OPENCODE_DEFAULT_CONTEXT_WINDOW
    if context_window:
        config["limit"] = {
            "context": context_window,
            "output": opencode_model_output_limit(
                runtime,
                model,
                output_limit_resolver=output_limit_resolver,
            ),
        }
    supports_vision = opencode_capability_bool(runtime, model, "vision", "supports_vision")
    if supports_vision is True or (supports_vision is None and model.lower() in OPENCODE_IMAGE_INPUT_MODELS):
        config["attachment"] = True
        config["modalities"] = {
            "input": ["text", "image"],
            "output": ["text"],
        }
    options = opencode_model_request_options(
        runtime,
        model,
        protocol=protocol,
        provider_id=provider_id,
        base_url=base_url,
    )
    if options:
        config["options"] = options
    variants = opencode_model_variants(
        runtime,
        model,
        protocol=protocol,
        provider_id=provider_id,
        base_url=base_url,
    )
    if variants:
        config["variants"] = variants
    if opencode_model_requires_reasoning_roundtrip_guard(model):
        config["reasoning"] = False
    return config


def opencode_build_config_payload(runtime, model_name="", *, context_window_resolver=None, output_limit_resolver=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    routes = opencode_runtime_routes(runtime, model_name)
    providers = {}
    for index, route in enumerate(routes):
        provider_ref = str(route.get("provider_ref") or opencode_route_provider_ref(route, index)).strip()
        if not provider_ref:
            continue
        env_key = opencode_route_env_key(provider_ref) if provider_ref != OPENCODE_PROVIDER_ID else OPENCODE_API_KEY_ENV
        protocol = str(route.get("protocol") or "openai_chat_completions").strip()
        if protocol == "anthropic_messages":
            provider_npm = "@ai-sdk/anthropic"
            base_url = str(route.get("anthropic_base_url") or "").strip().rstrip("/")
        elif protocol == "openai_responses":
            provider_npm = "@ai-sdk/openai"
            base_url = str(route.get("openai_base_url") or "").strip().rstrip("/")
        else:
            provider_npm = "@ai-sdk/openai-compatible"
            base_url = str(route.get("openai_base_url") or "").strip().rstrip("/")
        provider_name = str(
            route.get("provider_name")
            or route.get("provider_id")
            or runtime.get("name")
            or runtime.get("id")
            or "MMS"
        ).strip() or "MMS"
        provider_config = providers.setdefault(
            provider_ref,
            {
                "npm": provider_npm,
                "name": provider_name,
                "env": [env_key],
                "options": {
                    "baseURL": base_url,
                    "apiKey": f"{{env:{env_key}}}",
                },
                "models": {},
            },
        )
        route_runtime = {**runtime, "id": route.get("provider_id") or runtime.get("id")}
        if isinstance(route.get("model_capabilities"), dict):
            route_runtime["model_capabilities"] = route["model_capabilities"]
        if route.get("provider_profile"):
            route_runtime["provider_profile"] = route.get("provider_profile")
        provider_config["models"][route["model"]] = opencode_model_config(
            route_runtime,
            route["model"],
            context_window_resolver=context_window_resolver,
            output_limit_resolver=output_limit_resolver,
            protocol=protocol,
            provider_id=route.get("provider_id") or runtime.get("id") or "",
            base_url=base_url,
        )
    payload = {
        "$schema": "https://opencode.ai/config.json",
        "autoupdate": False,
        "share": "disabled",
        "provider": providers,
    }
    if routes:
        model_ref = opencode_route_model_ref(routes[0], 0)
        default_route_key = str(runtime.get("opencode_default_route_key") or "").strip()
        if default_route_key:
            for index, route in enumerate(routes):
                if str(route.get("id") or "").strip() == default_route_key:
                    model_ref = opencode_route_model_ref(route, index)
                    break
        payload["model"] = model_ref
        payload["small_model"] = model_ref
        if runtime.get("opencode_lite_agents", True) is not False:
            payload["default_agent"] = str(
                runtime.get("opencode_default_agent") or OPENCODE_LITE_DEFAULT_AGENT
            ).strip() or OPENCODE_LITE_DEFAULT_AGENT
            roster = str(runtime.get("opencode_roster") or "").strip()
            if roster == "review_hub":
                payload["agent"] = opencode_review_hub_agent_configs(
                    opencode_agent_model_refs(runtime, routes),
                    roster_config=runtime.get("opencode_agent_roster"),
                )
            elif roster == "committee":
                payload["agent"] = opencode_committee_agent_configs(
                    opencode_agent_model_refs(runtime, routes),
                    roster_config=runtime.get("opencode_agent_roster"),
                    agent_policies=opencode_agent_opencode_policies(runtime, routes),
                )
            elif roster == "debate":
                payload["agent"] = opencode_debate_agent_configs(
                    opencode_agent_model_refs(runtime, routes),
                    roster_config=runtime.get("opencode_agent_roster"),
                    agent_policies=opencode_agent_opencode_policies(runtime, routes),
                )
            elif roster in {"lite_pro", "lite_pro_orchestrated"}:
                payload["agent"] = opencode_lite_pro_agent_configs(
                    opencode_agent_model_refs(runtime, routes),
                    orchestrated=roster == "lite_pro_orchestrated",
                    roster_config=runtime.get("opencode_agent_roster"),
                )
            else:
                payload["agent"] = opencode_lite_agent_configs(model_ref)
            payload["agent"] = opencode_apply_agent_model_variants(payload.get("agent"), runtime, routes)
            if roster == "committee" and payload.get("default_agent") not in payload.get("agent", {}):
                payload["default_agent"] = "committee-host"
            if roster == "debate" and payload.get("default_agent") not in payload.get("agent", {}):
                payload["default_agent"] = "debate-host"
    if opencode_bypass_enabled(runtime):
        payload["permission"] = "allow"
        if "agent" in payload:
            payload["agent"] = opencode_apply_agent_bypass_permissions(payload.get("agent"))
    else:
        payload["permission"] = {
            "edit": "ask",
            "bash": "ask",
        }
    return payload


def opencode_bypass_enabled(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    value = runtime.get("bypass")
    if value is None:
        return True
    return bool(value)


def opencode_apply_bypass_env(env, runtime):
    if opencode_bypass_enabled(runtime):
        env["OPENCODE_PERMISSION"] = OPENCODE_BYPASS_PERMISSION_ENV
        env["MMS_OPENCODE_BYPASS"] = "1"
    else:
        env.pop("OPENCODE_PERMISSION", None)
        env["MMS_OPENCODE_BYPASS"] = "0"
    return env


def opencode_build_config_content(runtime, model_name="", *, context_window_resolver=None, output_limit_resolver=None):
    return json.dumps(
        opencode_build_config_payload(
            runtime,
            model_name,
            context_window_resolver=context_window_resolver,
            output_limit_resolver=output_limit_resolver,
        ),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def opencode_apply_route_env(env, runtime, selected_model=""):
    routes = opencode_runtime_routes(runtime, selected_model)
    default_key = ""
    default_base = ""
    default_anthropic_base = ""
    for index, route in enumerate(routes):
        provider_ref = str(route.get("provider_ref") or opencode_route_provider_ref(route, index)).strip()
        env_key = opencode_route_env_key(provider_ref) if provider_ref != OPENCODE_PROVIDER_ID else OPENCODE_API_KEY_ENV
        api_key = str(route.get("api_key") or runtime.get("openai_api_key") or runtime.get("api_key") or "")
        env[env_key] = api_key
        if not default_key:
            default_key = api_key
            default_base = str(route.get("openai_base_url") or "").strip().rstrip("/")
            default_anthropic_base = str(route.get("anthropic_base_url") or "").strip().rstrip("/")
    env[OPENCODE_API_KEY_ENV] = default_key or str(runtime.get("openai_api_key") or runtime.get("api_key") or "")
    env["OPENAI_API_KEY"] = env[OPENCODE_API_KEY_ENV]
    env["OPENAI_BASE_URL"] = default_base or opencode_provider_base_url(runtime)
    if default_anthropic_base:
        env["ANTHROPIC_API_KEY"] = env[OPENCODE_API_KEY_ENV]
        env["ANTHROPIC_BASE_URL"] = default_anthropic_base
    return routes
