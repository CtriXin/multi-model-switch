"""Grok Build TUI launcher: isolated GROK_HOME + current-provider catalog."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

try:
    import tomli_w
except ImportError:  # pragma: no cover - install extra, same as config writer
    tomli_w = None

import mms_pi_support as _pi_support
from mms_grok_compat import origin_of, rewrite_config_base_urls, start_compat_proxy
from mms_opencode_config import opencode_config_slug as _opencode_config_slug
from mms_state_io import atomic_write_text


_GROK_API_KEY_ENV = "MMS_GROK_API_KEY"
_GROK_AUTHORIZATION_ENV = "MMS_GROK_AUTHORIZATION"
_GROK_BACKENDS = {
    "openai_chat_completions": "chat_completions",
    "responses": "responses",
    "anthropic_messages": "messages",
}
_GROK_INHERITED_ENV_BLOCKLIST = (
    "XAI_API_KEY",
    "GROK_CODE_XAI_API_KEY",
    "GROK_HOME",
    "GROK_CONFIG",
    "GROK_CONFIG_PATH",
    "GROK_MODELS_BASE_URL",
    "GROK_MODELS_LIST_URL",
    "GROK_CLI_CHAT_PROXY_BASE_URL",
)
_ANTHROPIC_VERSION = "2023-06-01"


def _launchers_module():
    import mms_launchers
    return mms_launchers


def _resolve_model(model_info):
    return _launchers_module()._resolve_model(model_info)


def _grok_gateway_root():
    launchers = _launchers_module()
    config_root = launchers._selected_mms_config_root(
        {"MMS_REAL_HOME": launchers._real_user_path()}
    )
    return os.path.join(config_root, "grok-gateway")


def _grok_catalog_key(model_name):
    return str(model_name or "").strip()


def _grok_messages_base_url(base_url):
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        return ""
    path = urlsplit(url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    if last_segment == "v1":
        return url
    return f"{url}/v1"


def _grok_messages_backend_safe(model_name):
    """Grok's Messages client requires Anthropic thinking.signature.

    NewAPI MiniMax/Gemini/Kimi adapters often emit thinking blocks without
    that field, which Grok fails closed on. Only native Claude ids stay on
    messages for the TUI launcher.
    """
    return _pi_support._pi_normalize_model_key(model_name).startswith("claude-")


def _grok_resolved_entry(runtime, model_name):
    resolved = _pi_support._pi_model_entry(runtime, model_name)
    protocol = str(resolved.get("protocol") or "").strip()
    if protocol != "anthropic_messages" or _grok_messages_backend_safe(model_name):
        return resolved
    openai_variant = _pi_support._pi_protocol_variant(runtime, "openai_chat_completions")
    if not openai_variant:
        return resolved
    rewritten = dict(resolved)
    rewritten["protocol"] = openai_variant["protocol"]
    rewritten["api"] = openai_variant["api"]
    rewritten["base_url"] = openai_variant["base_url"]
    rewritten["provider_label"] = openai_variant["label"]
    return rewritten


def _grok_model_table(runtime, model_name):
    resolved = _grok_resolved_entry(runtime, model_name)
    protocol = str(resolved.get("protocol") or "").strip()
    backend = _GROK_BACKENDS.get(protocol)
    if not backend:
        raise RuntimeError(f"Grok launcher has no API backend for protocol '{protocol}'")
    wire_model = str((resolved.get("model") or {}).get("id") or model_name).strip()
    display_name = str((resolved.get("model") or {}).get("name") or model_name).strip()
    base_url = str(resolved.get("base_url") or "").strip().rstrip("/")
    if protocol == "anthropic_messages":
        base_url = _grok_messages_base_url(base_url)
    if not wire_model or not base_url:
        raise RuntimeError(f"Grok launcher could not resolve endpoint for '{model_name}'")
    caps_window = int((resolved.get("model") or {}).get("contextWindow") or 0)
    caps_max = int((resolved.get("model") or {}).get("maxTokens") or 0)
    table = {
        "model": wire_model,
        "name": display_name,
        "base_url": base_url,
        "api_backend": backend,
        "env_key": _GROK_API_KEY_ENV,
        "supports_backend_search": False,
        "stream_tool_calls": False,
    }
    if caps_window > 0:
        table["context_window"] = caps_window
    if caps_max > 0:
        table["max_completion_tokens"] = caps_max
    if protocol == "anthropic_messages":
        table["extra_headers"] = {"anthropic-version": _ANTHROPIC_VERSION}
        table["env_http_headers"] = {
            "x-api-key": _GROK_API_KEY_ENV,
            "authorization": _GROK_AUTHORIZATION_ENV,
        }
    if protocol == "responses":
        table["reasoning_summary"] = "none"
    return table


def _grok_build_config_payload(runtime, selected_model):
    launchers = _launchers_module()
    model = _pi_support._pi_effective_selected_model(runtime, selected_model)
    if not model:
        raise RuntimeError("Grok runtime requires a selected model")
    if not _pi_support._pi_model_supported(model):
        raise RuntimeError(f"Grok launcher does not support image-generation-only model '{model}'")
    block_reason = launchers._pi_model_block_reason(runtime, model)
    if block_reason:
        raise RuntimeError(f"Grok launcher currently blocks model '{model}': {block_reason}")
    model_names = launchers._pi_exposed_model_names(runtime, selected_model=model)
    if not model_names:
        raise RuntimeError("Grok runtime requires at least one available model")

    models = {}
    for model_name_item in model_names:
        catalog_key = _grok_catalog_key(model_name_item)
        if not catalog_key or catalog_key in models:
            continue
        if not _pi_support._pi_model_supported(model_name_item):
            continue
        models[catalog_key] = _grok_model_table(runtime, model_name_item)
    selected_key = _grok_catalog_key(model)
    if selected_key not in models:
        raise RuntimeError(f"Grok launcher could not expose selected model '{model}'")
    return {
        "cli": {
            "auto_update": False,
            "use_leader": False,
        },
        "features": {
            "telemetry": False,
            "remote_fetch": False,
            "feedback": False,
        },
        "models": {
            "default": selected_key,
            "allowed_models": list(models.keys()),
            "web_search": selected_key,
            "stream_tool_calls": False,
        },
        "model": models,
    }, selected_key


def _install_grok_compat_proxy(payload, grok_home):
    models = payload.get("model") if isinstance(payload, dict) else {}
    if not isinstance(models, dict):
        return payload
    origins = []
    for table in models.values():
        origin = origin_of((table or {}).get("base_url"))
        if origin and origin not in origins:
            origins.append(origin)
    if not origins:
        return payload
    listen = start_compat_proxy(
        origins[0],
        parent_pid=os.getpid(),
        log_path=os.path.join(grok_home, "logs", "compat-proxy.log"),
    )
    return rewrite_config_base_urls(payload, listen, origins[0])


def _write_grok_config(grok_home, runtime, selected_model):
    if tomli_w is None:
        raise RuntimeError("Grok launcher requires tomli-w to write isolated config.toml")
    payload, selected_key = _grok_build_config_payload(runtime, selected_model)
    os.makedirs(grok_home, exist_ok=True)
    payload = _install_grok_compat_proxy(payload, grok_home)
    config_path = os.path.join(grok_home, "config.toml")
    atomic_write_text(config_path, tomli_w.dumps(payload), mode=0o600)
    auth_path = os.path.join(grok_home, "auth.json")
    if os.path.exists(auth_path):
        os.remove(auth_path)
    return config_path, selected_key


def _grok_scrub_inherited_env(env):
    env = env if isinstance(env, dict) else {}
    for key in _GROK_INHERITED_ENV_BLOCKLIST:
        env.pop(key, None)
    return env


def _apply_common_runtime_env(env, runtime, model_info, session_home, selected_model):
    launchers = _launchers_module()
    launchers._scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _grok_scrub_inherited_env(env)
    launchers._inject_real_home_hints(env, include_xdg=True)
    launchers._inject_host_capability_hints(env)
    launchers._inject_selected_model_name(env, selected_model, model_info=model_info)
    launchers._set_session_home_hint(env, session_home)
    launchers._apply_runtime_network_profile(env, runtime, validate_proxy=False)
    launchers._apply_runtime_locale_profile(env, runtime)
    launchers._apply_runtime_ip_stack_profile(env, runtime)
    launchers._install_session_command_wrappers(session_home, env)
    launchers._install_session_packet_env(
        env,
        cli="grok",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features={
            "web_access": bool(launchers._resolve_web_access_root()),
            "weber": bool(launchers._resolve_weber_root()),
            "toon": bool(launchers._resolve_toon_root()),
            "token_saver": bool(launchers._resolve_token_saver_root()),
        },
    )
    return env


def _grok_api_key(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    return str(runtime.get("openai_api_key") or runtime.get("api_key") or "").strip()


def _grok_credential_env(runtime):
    api_key = _grok_api_key(runtime)
    if not api_key:
        raise RuntimeError("Grok runtime requires an API key")
    return {
        _GROK_API_KEY_ENV: api_key,
        _GROK_AUTHORIZATION_ENV: f"Bearer {api_key}",
        "GROK_DISABLE_AUTOUPDATER": "1",
        "GROK_TELEMETRY_ENABLED": "0",
    }


def _grok_gateway_env(runtime, model_info=None):
    launchers = _launchers_module()
    runtime = runtime if isinstance(runtime, dict) else {}
    requested_model = _resolve_model(model_info)
    model = _pi_support._pi_effective_selected_model(runtime, requested_model)
    gateway_base = _grok_gateway_root()
    os.makedirs(gateway_base, exist_ok=True)
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    os.makedirs(session_home, exist_ok=True)
    launchers._cleanup_stale_sessions(sessions_dir)

    grok_home = os.path.join(session_home, "home")
    config_path, selected_key = _write_grok_config(grok_home, runtime, model)
    persistent_sessions = os.path.join(gateway_base, "sessions")
    os.makedirs(persistent_sessions, exist_ok=True)
    session_link = os.path.join(grok_home, "sessions")
    if not os.path.exists(session_link):
        try:
            os.symlink(persistent_sessions, session_link)
        except OSError:
            os.makedirs(session_link, exist_ok=True)

    env = dict(os.environ)
    _apply_common_runtime_env(env, runtime, model_info, session_home, model)
    env.update(_grok_credential_env(runtime))
    env["GROK_HOME"] = grok_home
    env["MMS_GROK_HOME"] = grok_home
    env["MMS_GROK_CONFIG"] = config_path
    env["MMS_GROK_SELECTED_MODEL"] = selected_key
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    return env


def _grok_provider_export_env(runtime, model):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    effective_model = _pi_support._pi_effective_selected_model(
        runtime, model or runtime.get("model")
    )
    provider_ref = _opencode_config_slug(
        runtime.get("id") or runtime.get("name"), "provider"
    )
    model_ref = _opencode_config_slug(effective_model, "model")
    grok_home = os.path.join(_grok_gateway_root(), "exports", f"{provider_ref}-{model_ref}", "home")
    config_path, selected_key = _write_grok_config(grok_home, runtime, effective_model)
    exports = {
        "GROK_HOME": grok_home,
        "MMS_GROK_HOME": grok_home,
        "MMS_GROK_CONFIG": config_path,
        "MMS_GROK_SELECTED_MODEL": selected_key,
        "GROK_DISABLE_AUTOUPDATER": "1",
        "GROK_TELEMETRY_ENABLED": "0",
    }
    exports.update(_grok_credential_env(runtime))
    return launchers._inject_selected_model_name(exports, effective_model, model_info=runtime)


def launch_grok(model_info, runtime, once=False, extra_args=None):
    """Start Grok Build with an isolated GROK_HOME and the current provider catalog."""
    launchers = _launchers_module()
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    if auth_mode != "api_key":
        launchers.console.print("[red]Grok 当前只支持模型源/API key 模式；官方 grok login 请直接在 Grok 内使用[/red]")
        raise SystemExit(1)

    requested_model = _resolve_model(model_info)
    model = _pi_support._pi_effective_selected_model(runtime, requested_model)
    env = _grok_gateway_env(runtime, model_info=model_info)
    selected_key = str(env.get("MMS_GROK_SELECTED_MODEL") or model).strip()
    cmd = ["grok", "-m", selected_key]
    if runtime.get("bypass"):
        cmd.append("--always-approve")
    thinking_mode = str(runtime.get("thinking_mode") or "").strip().lower()
    reasoning_effort = str(runtime.get("reasoning_effort") or "").strip().lower()
    if thinking_mode == "disable":
        cmd += ["--effort", "none"]
    elif reasoning_effort in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
        cmd += ["--effort", reasoning_effort]
    if extra_args:
        cmd += list(extra_args)
    launchers._exec_or_run(cmd, env, once)
