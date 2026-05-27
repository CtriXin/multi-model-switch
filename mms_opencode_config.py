"""OpenCode session-local provider/config helpers."""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from mms_opencode_agents import (
    opencode_apply_agent_bypass_permissions,
    opencode_lite_agent_configs,
    opencode_lite_pro_agent_configs,
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
OPENCODE_IMAGE_INPUT_MODELS = {
    "gpt-5.3-codex",
    "gpt-5.4",
    "gpt-5.5",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-pro-preview",
    "k2.6",
    "kimi-k2.5",
    "mimo-v2.5",
    "qwen3.6-flash",
    "qwen3.6-plus",
}
OPENCODE_MODEL_LIMIT_OVERRIDES = {
    # MiMo's OpenCode guide advertises 1M context and 131072 output for the
    # OpenAI-compatible provider config, independent of Claude Code's [1m]
    # Anthropic selector.
    "mimo-v2.5-pro": {"context": 1_048_576, "output": 131_072},
    "mimo-v2.5": {"context": 1_048_576, "output": 131_072},
}


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


def opencode_model_output_limit(runtime, model_name):
    explicit = opencode_explicit_output_limit(runtime)
    if explicit is not None:
        return explicit
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


def opencode_model_config(runtime, model_name, *, context_window_resolver=None):
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
            "output": opencode_model_output_limit(runtime, model),
        }
    if model.lower() in OPENCODE_IMAGE_INPUT_MODELS:
        config["attachment"] = True
        config["modalities"] = {
            "input": ["text", "image"],
            "output": ["text"],
        }
    if opencode_model_requires_reasoning_roundtrip_guard(model):
        config["reasoning"] = False
    return config


def opencode_build_config_payload(runtime, model_name="", *, context_window_resolver=None):
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
        provider_config["models"][route["model"]] = opencode_model_config(
            {**runtime, "id": route.get("provider_id") or runtime.get("id")},
            route["model"],
            context_window_resolver=context_window_resolver,
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
            if roster in {"lite_pro", "lite_pro_orchestrated"}:
                payload["agent"] = opencode_lite_pro_agent_configs(
                    opencode_agent_model_refs(runtime, routes),
                    orchestrated=roster == "lite_pro_orchestrated",
                    roster_config=runtime.get("opencode_agent_roster"),
                )
            else:
                payload["agent"] = opencode_lite_agent_configs(model_ref)
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


def opencode_build_config_content(runtime, model_name="", *, context_window_resolver=None):
    return json.dumps(
        opencode_build_config_payload(
            runtime,
            model_name,
            context_window_resolver=context_window_resolver,
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
