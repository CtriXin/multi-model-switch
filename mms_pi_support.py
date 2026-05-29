"""Pi runner support extracted from launcher glue."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from mms_capability_resolver import resolve_model_capabilities
from mms_core import _model_supports_vision, _probe_models
from mms_opencode_config import opencode_config_slug as _opencode_config_slug
from mms_provider_profiles import resolve_provider_profile
from mms_state_io import atomic_write_text

_ONE_M_CONTEXT_SUFFIX = "[1m]"
_ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS = {
    "mimo-v2.5-pro": 262_144,
    "mimo-v2.5": 262_144,
}


def _launchers_module():
    import mms_launchers
    return mms_launchers


def _openai_base_url(provider):
    return _launchers_module()._openai_base_url(provider)


def _anthropic_base_url(provider):
    return _launchers_module()._anthropic_base_url(provider)


def _resolve_model(model_info):
    return _launchers_module()._resolve_model(model_info)


def _cleanup_stale_sessions(sessions_dir, stale_callback=None, *, max_entries=None, max_seconds=None):
    return _launchers_module()._cleanup_stale_sessions(
        sessions_dir,
        stale_callback=stale_callback,
        max_entries=max_entries,
        max_seconds=max_seconds,
    )


def _scrub_inherited_runtime_env(env, *, strip_openai=False, strip_proxy=False):
    return _launchers_module()._scrub_inherited_runtime_env(
        env,
        strip_openai=strip_openai,
        strip_proxy=strip_proxy,
    )


def _inject_real_home_hints(env, *, include_xdg=False):
    return _launchers_module()._inject_real_home_hints(env, include_xdg=include_xdg)


def _inject_host_capability_hints(env):
    return _launchers_module()._inject_host_capability_hints(env)


def _inject_selected_model_name(env, *candidates, model_info=None):
    return _launchers_module()._inject_selected_model_name(env, *candidates, model_info=model_info)


def _set_session_home_hint(env, session_home):
    return _launchers_module()._set_session_home_hint(env, session_home)


def _real_user_path(*parts):
    return _launchers_module()._real_user_path(*parts)


def _apply_runtime_network_profile(env, runtime, *, validate_proxy=True):
    return _launchers_module()._apply_runtime_network_profile(env, runtime, validate_proxy=validate_proxy)


def _apply_runtime_locale_profile(env, runtime=None):
    return _launchers_module()._apply_runtime_locale_profile(env, runtime)


def _apply_runtime_ip_stack_profile(env, runtime):
    return _launchers_module()._apply_runtime_ip_stack_profile(env, runtime)


def _install_session_command_wrappers(session_home, env):
    return _launchers_module()._install_session_command_wrappers(session_home, env)


def _install_session_packet_env(env, cli, runtime, model_info, session_home, features):
    return _launchers_module()._install_session_packet_env(
        env,
        cli=cli,
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features=features,
    )


def _resolve_web_access_root():
    return _launchers_module()._resolve_web_access_root()


def _resolve_weber_root():
    return _launchers_module()._resolve_weber_root()


def _resolve_toon_root():
    return _launchers_module()._resolve_toon_root()


def _resolve_token_saver_root():
    return _launchers_module()._resolve_token_saver_root()


def _resolve_xmem_root():
    return _launchers_module()._resolve_xmem_root()


def _exec_or_run(cmd, env, once):
    return _launchers_module()._exec_or_run(cmd, env, once)

def _pi_wrapper_path():
    wrapper_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scripts",
        "pi-cli-wrapper.sh",
    )
    if os.path.isfile(wrapper_path) and os.access(wrapper_path, os.X_OK):
        return wrapper_path
    return ""


def _pi_retry_extension_path():
    extension_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "scripts",
        "pi-retry-extension.mjs",
    )
    if os.path.isfile(extension_path):
        return extension_path
    return ""


def _pi_npx_cache_dir():
    return str(Path(__file__).resolve().parent / ".ai" / "cache" / "pi-npx")


def _pi_settings_payload():
    payload = {
        "retry": {
            "enabled": True,
            "maxRetries": 8,
            "baseDelayMs": 1000,
        }
    }
    extension_path = _pi_retry_extension_path()
    if extension_path:
        payload["extensions"] = [extension_path]
    return payload


def _pi_provider_ref(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    return f"mms-{_opencode_config_slug(runtime.get('id') or runtime.get('name'), 'provider')}"


_PI_ADAPTIVE_CLAUDE_MODELS = {
    "claude-opus-4-6",
    "claude-opus-4.6",
    "claude-opus-4-7",
    "claude-opus-4.7",
    "claude-sonnet-4-6",
    "claude-sonnet-4.6",
}

_PI_OPENAI_PROFILE_COMPAT = {
    "dashscope-openai": {
        "thinkingFormat": "qwen",
    },
    "deepseek": {
        "requiresReasoningContentOnAssistantMessages": True,
        "thinkingFormat": "deepseek",
    },
    "glm": {
        "supportsDeveloperRole": False,
        "thinkingFormat": "zai",
    },
    "kimi-code": {
        "supportsStore": False,
        "supportsDeveloperRole": False,
        "supportsReasoningEffort": False,
        "maxTokensField": "max_tokens",
        "supportsStrictMode": False,
    },
    "mimo": {
        "requiresReasoningContentOnAssistantMessages": True,
        "supportsDeveloperRole": False,
        "thinkingFormat": "deepseek",
    },
    "mimo-openai": {
        "requiresReasoningContentOnAssistantMessages": True,
        "supportsDeveloperRole": False,
        "thinkingFormat": "deepseek",
    },
    "qwen-chat-template": {
        "thinkingFormat": "qwen-chat-template",
    },
}

_PI_CAPABILITY_REFERENCE_PATH = (
    Path(__file__).resolve().parent
    / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"
)

_PI_MODEL_MAX_TOKENS_HINTS = {
    "deepseek-v4-flash": 384000,
    "deepseek-v4-pro": 384000,
    "gpt-5.3-codex": 128000,
    "gpt-5.3-codex-spark": 32000,
    "k2.6": 32768,
    "k2.6-code-preview": 32768,
    "kimi-for-coding": 32768,
    "kimi-k2.6": 32768,
    "kimi-k2.6-code-preview": 32768,
    "mimo-v2-flash": 65536,
    "mimo-v2-pro": 131072,
    "mimo-v2.5": 131072,
    "mimo-v2.5-pro": 131072,
    "mimo-v2.5-pro[1m]": 131072,
    "mimo-v2.5[1m]": 131072,
    "qwen3.5-plus": 65536,
    "qwen3.6-flash": 65536,
    "qwen3.6-plus": 65536,
    "qwen3.7-max": 65536,
}

_PI_MODEL_CONTEXT_WINDOW_HINTS = {
    "gpt-5.3-codex": 400000,
    "gpt-5.3-codex-spark": 128000,
    "qwen3.6-flash": 1000000,
    "qwen3.7-max": 1000000,
}

_PI_MODEL_INPUT_HINTS = {
    "claude-opus-4-6-thinking": ["text", "image"],
    "claude-sonnet-4-6": ["text", "image"],
    "gpt-5.3-codex": ["text", "image"],
    "gpt-5.3-codex-spark": ["text", "image"],
    "kimi-for-coding": ["text", "image"],
    "minimax-m2.7": ["text"],
    "qwen3.6-flash": ["text", "image"],
    "qwen3.7-max": ["text"],
}

_PI_MODEL_UNSUPPORTED_HINTS = {
    "gemini-3.1-flash-image",
    "gpt-draw-1024x1024",
    "gpt-draw-1024x1536",
    "gpt-draw-1536x1024",
    "gpt-image-2",
}

# Fail closed for provider/model pairs that currently surface in probe results but
# are not actually usable through Pi in live smoke. Keep Pi's exposed model list
# aligned with what the runner can really launch today.
_PI_PROVIDER_MODEL_BLOCK_REASONS = {
    "newapi-personal-tokyo": {
        "anthropic/claude-opus-4.7": "2026-05-28 live Pi smoke returned key-limit 403 on this relay",
        "claude-opus-4-6": "2026-05-28 live Pi smoke returned model_not_found on this relay",
        "claude-opus-4-6-thinking": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
        "gemini-3-flash-agent(high)": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
        "gemini-3-flash-agent(low)": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
        "gemini-3-flash-agent(medium)": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
        "gemini-3.1-flash-lite": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
        "gemini-3.1-pro-low": "2026-05-28 live Pi smoke returned upstream 500 on this relay",
    },
    "openrouter": {
        "anthropic/claude-opus-4.7": "2026-05-28 live Pi smoke returned key-limit 403 on this relay",
    },
    "us-cpa-local-antigravity": {
        "gemini-3-pro-high": "Gemini 3 Pro is deprecated upstream; live Pi smoke now returns a switch-to-Gemini-3.1 notice",
        "gemini-3-pro-low": "Gemini 3 Pro is deprecated upstream; live Pi smoke now returns a switch-to-Gemini-3.1 notice",
    },
    "xin": {
        "anthropic/claude-opus-4.6": "2026-05-28 current-surface rerun returned region-blocked 403 on this relay",
        "anthropic/claude-opus-4.7": "2026-05-28 current-surface rerun returned region-blocked 403 on this relay",
        "claude-opus-4-6": "2026-05-28 current-surface rerun returned model_not_found / no available distributor on this relay",
        "claude-opus-4-6-thinking": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "claude-sonnet-4-6": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gemini-3-flash-agent(high)": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gemini-3-flash-agent(low)": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gemini-3-flash-agent(medium)": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gemini-3.1-flash-lite": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gemini-3.1-pro-low": "2026-05-28 current-surface rerun returned upstream 500 on this relay",
        "gpt-5.3-codex": "2026-05-28 blocked-only recheck stayed request_fail across 3 attempts; relay returned no available distributor for this model",
    },
}

_PI_PROVIDER_MODEL_REPLACEMENTS = {
    "us-cpa-local-antigravity": {
        # Upstream now responds with a deprecation notice that explicitly points
        # callers at Gemini 3.1 Pro, so MMS rewrites the old Pi selection to the
        # current live alias when that replacement is actually present.
        "gemini-3-pro-high": "gemini-3.1-pro-low",
        "gemini-3-pro-low": "gemini-3.1-pro-low",
    },
}

_PI_CAPABILITY_REFERENCE_CACHE = None
_PI_CAPABILITY_REFERENCE_INDEX = None


def _pi_normalize_model_key(value):
    model_key = str(value or "").strip().lower()
    if "/" in model_key:
        model_key = model_key.rsplit("/", 1)[-1]
    return model_key


def _pi_reference_payload():
    global _PI_CAPABILITY_REFERENCE_CACHE
    if _PI_CAPABILITY_REFERENCE_CACHE is not None:
        return _PI_CAPABILITY_REFERENCE_CACHE
    try:
        payload = json.loads(_PI_CAPABILITY_REFERENCE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        payload = {}
    _PI_CAPABILITY_REFERENCE_CACHE = payload if isinstance(payload, dict) else {}
    return _PI_CAPABILITY_REFERENCE_CACHE


def _pi_reference_model_row(model_name):
    global _PI_CAPABILITY_REFERENCE_INDEX
    if _PI_CAPABILITY_REFERENCE_INDEX is None:
        indexed = {}
        rows = _pi_reference_payload().get("models")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in (
                    "alias",
                    "model",
                    "model_name",
                    "model_id",
                    "routed_model_id",
                    "canonical_model_id",
                    "openrouter_model_id",
                ):
                    model_key = _pi_normalize_model_key(row.get(key))
                    if model_key and model_key not in indexed:
                        indexed[model_key] = row
        _PI_CAPABILITY_REFERENCE_INDEX = indexed
    return (_PI_CAPABILITY_REFERENCE_INDEX or {}).get(_pi_normalize_model_key(model_name), {})


def _pi_first_positive_int(payload, *keys):
    if not isinstance(payload, dict):
        return None
    for key in keys:
        try:
            value = int(payload.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _pi_hint_max_tokens(model_name):
    normalized = _pi_normalize_model_key(model_name)
    direct = _PI_MODEL_MAX_TOKENS_HINTS.get(normalized)
    if direct:
        return direct
    for key, value in _PI_MODEL_MAX_TOKENS_HINTS.items():
        if normalized.startswith(key):
            return value
    return None


def _pi_hint_context_window(model_name):
    normalized = _pi_normalize_model_key(model_name)
    direct = _PI_MODEL_CONTEXT_WINDOW_HINTS.get(normalized)
    if direct:
        return direct
    for key, value in _PI_MODEL_CONTEXT_WINDOW_HINTS.items():
        if normalized.startswith(key):
            return value
    return None


def _pi_reference_supports_vision(model_name):
    row = _pi_reference_model_row(model_name)
    value = row.get("supports_vision")
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text == "image_generation":
        return "image_generation"
    if text in {"true", "false"}:
        return text == "true"
    return None


def _pi_model_supported(model_name):
    normalized = _pi_normalize_model_key(model_name)
    if normalized in _PI_MODEL_UNSUPPORTED_HINTS:
        return False
    return _pi_reference_supports_vision(model_name) != "image_generation"


def _pi_model_replacement(runtime, model_name):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    provider_id = str(runtime.get("id") or runtime.get("provider_id") or "").strip().lower()
    if not provider_id:
        return ""
    candidates = _PI_PROVIDER_MODEL_REPLACEMENTS.get(provider_id) or {}
    normalized = _pi_normalize_model_key(model_name)
    replacement = ""
    for source_name, target_name in candidates.items():
        if _pi_normalize_model_key(source_name) == normalized:
            replacement = str(target_name or "").strip()
            break
    if not replacement:
        return ""

    available = {
        _pi_normalize_model_key(candidate): str(candidate or "").strip()
        for candidate in launchers._pi_runtime_model_names(runtime, selected_model=model_name)
        if str(candidate or "").strip()
    }
    return available.get(_pi_normalize_model_key(replacement), "")


def _pi_model_block_reason(runtime, model_name):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    provider_id = str(runtime.get("id") or runtime.get("provider_id") or "").strip().lower()
    if not provider_id:
        return ""
    if launchers._pi_model_replacement(runtime, model_name):
        return ""
    candidates = _PI_PROVIDER_MODEL_BLOCK_REASONS.get(provider_id) or {}
    normalized = _pi_normalize_model_key(model_name)
    for blocked_name, reason in candidates.items():
        if _pi_normalize_model_key(blocked_name) == normalized:
            return str(reason or "").strip()
    return ""


def _pi_model_available_for_runtime(runtime, model_name):
    if not _pi_model_supported(model_name):
        return False
    return not _pi_model_block_reason(runtime, model_name)


def _pi_exposed_model_names(runtime, selected_model=""):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    names = []
    seen = set()
    for model_name in launchers._pi_runtime_model_names(runtime, selected_model=selected_model):
        text = str(model_name or "").strip()
        if not text or text in seen:
            continue
        if not launchers._pi_model_available_for_runtime(runtime, text):
            continue
        seen.add(text)
        names.append(text)
    return names


def _pi_model_input_types(model_name):
    normalized = _pi_normalize_model_key(model_name)
    hint = _PI_MODEL_INPUT_HINTS.get(normalized)
    if isinstance(hint, list) and hint:
        return list(hint)
    if normalized.startswith(("claude-", "gpt-5", "gemini-")):
        return ["text", "image"]
    vision_state = _pi_reference_supports_vision(model_name)
    if vision_state is True:
        return ["text", "image"]
    if vision_state == "image_generation":
        return ["text"]
    if _model_supports_vision(model_name):
        return ["text", "image"]
    return ["text"]


def _pi_model_capabilities(runtime, model_name):
    runtime = runtime if isinstance(runtime, dict) else {}
    provider_id = str(runtime.get("id") or runtime.get("provider_id") or "").strip()
    base_url = str(_openai_base_url(runtime) or _anthropic_base_url(runtime) or "").strip()
    profile_id = _pi_profile_id(runtime, model_name, base_url=base_url)
    caps = resolve_model_capabilities(
        model_name,
        runtime=runtime,
        provider_id=provider_id,
        base_url=base_url,
        profile_id=profile_id,
    )

    needs_reference = any(
        caps.get("sources", {}).get(field) == "conservative_fallback"
        for field in ("context_window_tokens", "max_output_tokens", "supports_thinking")
    )
    if needs_reference:
        reference_caps = resolve_model_capabilities(
            model_name,
            runtime=runtime,
            provider_id=provider_id,
            base_url=base_url,
            profile_id=profile_id,
            approved_facts=_pi_reference_payload(),
        )
        for field in (
            "context_window_tokens",
            "max_output_tokens",
            "supports_thinking",
            "thinking_control",
            "expected_protocol",
            "protocol_hints",
        ):
            if caps.get("sources", {}).get(field) != "conservative_fallback":
                continue
            if reference_caps.get("sources", {}).get(field) != "approved_facts":
                continue
            caps[field] = copy.deepcopy(reference_caps.get(field))
            caps.setdefault("sources", {})[field] = "pi_reference_fallback"

    reference_row = _pi_reference_model_row(model_name)
    if caps.get("sources", {}).get("context_window_tokens") == "conservative_fallback":
        reference_context = _pi_first_positive_int(
            reference_row,
            "official_context_window_tokens",
            "provider_top_context_window_tokens",
            "provider_context_window_tokens",
            "current_mms_context_window_tokens",
        )
        if reference_context:
            caps["context_window_tokens"] = reference_context
            caps["sources"]["context_window_tokens"] = "pi_reference_fallback"

    if caps.get("sources", {}).get("context_window_tokens") == "conservative_fallback":
        hinted_context = _pi_hint_context_window(model_name)
        if hinted_context:
            caps["context_window_tokens"] = hinted_context
            caps["sources"]["context_window_tokens"] = "pi_builtin_hint"

    if caps.get("sources", {}).get("max_output_tokens") == "conservative_fallback":
        reference_max = _pi_first_positive_int(
            reference_row,
            "official_max_output_tokens",
            "provider_top_max_output_tokens",
        )
        if reference_max:
            caps["max_output_tokens"] = reference_max
            caps["sources"]["max_output_tokens"] = "pi_reference_fallback"

    if caps.get("sources", {}).get("max_output_tokens") == "conservative_fallback":
        hinted_max = _pi_hint_max_tokens(model_name)
        if hinted_max:
            caps["max_output_tokens"] = hinted_max
            caps["sources"]["max_output_tokens"] = "pi_builtin_hint"
    return caps


def _pi_anthropic_base_root(base_url):
    url = str(base_url or "").strip().rstrip("/")
    if url.endswith("/v1/messages"):
        return url[:-12]
    if url.endswith("/v1"):
        return url[:-3]
    return url


def _pi_openai_base_url(runtime):
    runtime = runtime if isinstance(runtime, dict) else {}
    base_url = str(_openai_base_url(runtime) or "").strip().rstrip("/")
    if not base_url:
        return ""
    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1].lower() if path else ""
    if last_segment == "v1":
        return base_url
    anthropic_root = _pi_anthropic_base_root(_anthropic_base_url(runtime))
    if anthropic_root and anthropic_root.rstrip("/") == base_url:
        return f"{base_url}/v1"
    if not path:
        return f"{base_url}/v1"
    return base_url


def _pi_protocol_variant(runtime, protocol):
    runtime = runtime if isinstance(runtime, dict) else {}
    protocol_name = str(protocol or "").strip()
    if protocol_name == "anthropic_messages":
        base_url = _pi_anthropic_base_root(_anthropic_base_url(runtime))
        if base_url:
            return {
                "protocol": "anthropic_messages",
                "api": "anthropic-messages",
                "base_url": base_url,
                "label": "Anthropic",
            }
        return None
    if protocol_name == "responses":
        base_url = _pi_openai_base_url(runtime)
        if base_url:
            return {
                "protocol": "responses",
                "api": "openai-responses",
                "base_url": base_url,
                "label": "OpenAI Responses",
            }
        return None
    if protocol_name == "openai_chat_completions":
        base_url = _pi_openai_base_url(runtime)
        if base_url:
            return {
                "protocol": "openai_chat_completions",
                "api": "openai-completions",
                "base_url": base_url,
                "label": "OpenAI",
            }
        return None
    return None


def _pi_protocol_variants(runtime):
    variants = []
    for protocol in ("anthropic_messages", "responses", "openai_chat_completions"):
        variant = _pi_protocol_variant(runtime, protocol)
        if variant:
            variants.append(variant)
    return variants


def _pi_runtime_model_names(runtime, selected_model=""):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    names = []
    seen = set()

    def _add(value):
        text = str(value or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        names.append(text)

    _add(selected_model)
    _add(runtime.get("model"))

    probe_result = runtime.get("_launch_prefetched_probe")
    if probe_result is None:
        try:
            probe_result = launchers._probe_models(runtime, emit_output=False)
        except Exception:
            probe_result = {}
        runtime["_launch_prefetched_probe"] = probe_result

    for item in (probe_result or {}).get("models") or []:
        _add(item)
    return names


def _pi_profile_id(runtime, model_name, base_url=""):
    runtime = runtime if isinstance(runtime, dict) else {}
    profile_id, _profile = resolve_provider_profile(
        runtime=runtime,
        provider_id=str(runtime.get("id") or runtime.get("provider_id") or "").strip(),
        base_url=str(base_url or _openai_base_url(runtime) or _anthropic_base_url(runtime) or "").strip(),
        model_name=model_name,
        profile_id=str(runtime.get("provider_profile") or runtime.get("profile") or "").strip(),
    )
    return str(profile_id or "").strip()


def _pi_pick_protocol(runtime, model_name):
    variants = _pi_protocol_variants(runtime)
    if not variants:
        raise RuntimeError("Pi runtime requires either an Anthropic or OpenAI base URL")
    available = {item["protocol"] for item in variants}
    variant_by_protocol = {item["protocol"]: item for item in variants}
    caps = _pi_model_capabilities(runtime, model_name)
    hints = caps.get("protocol_hints") if isinstance(caps.get("protocol_hints"), dict) else {}
    preferred = str(hints.get("preferred_protocol") or "").strip()
    if preferred == "responses":
        if "responses" in available:
            return variant_by_protocol["responses"], caps
        if "openai_chat_completions" in available:
            return variant_by_protocol["openai_chat_completions"], caps
    if preferred in available:
        return variant_by_protocol[preferred], caps
    for protocol_name in hints.get("protocols") or []:
        if protocol_name == "responses":
            if "responses" in available:
                return variant_by_protocol["responses"], caps
            if "openai_chat_completions" in available:
                return variant_by_protocol["openai_chat_completions"], caps
        if protocol_name in available:
            return variant_by_protocol[protocol_name], caps
    if "anthropic_messages" in available:
        return variant_by_protocol["anthropic_messages"], caps
    return variants[0], caps


def _pi_provider_compat(profile_id, protocol):
    if str(protocol or "").strip() not in {"openai_chat_completions", "responses"}:
        return {}
    compat = _PI_OPENAI_PROFILE_COMPAT.get(str(profile_id or "").strip(), {})
    return copy.deepcopy(compat) if compat else {}


def _pi_model_compat(model_name, protocol):
    normalized = str(model_name or "").strip().lower().rsplit("/", 1)[-1]
    compat = {}
    if str(protocol or "").strip() == "anthropic_messages" and normalized in _PI_ADAPTIVE_CLAUDE_MODELS:
        compat["forceAdaptiveThinking"] = True
    return compat


def _pi_model_thinking_level_map(profile_id, protocol, model_name, caps):
    if str(protocol or "").strip() != "openai_chat_completions":
        return {}
    if str(profile_id or "").strip() != "deepseek":
        return {}
    if not bool(caps.get("supports_thinking")):
        return {}
    normalized = str(model_name or "").strip().lower().rsplit("/", 1)[-1]
    if not normalized.startswith("deepseek"):
        return {}
    return {
        "minimal": None,
        "low": None,
        "medium": None,
        "high": "high",
        "xhigh": "max",
    }


def _pi_effective_selected_model(runtime, model_name):
    replacement = _pi_model_replacement(runtime, model_name)
    return replacement or str(model_name or "").strip()


def _pi_wire_model_name(runtime, model_name, protocol):
    protocol_name = str(protocol or "").strip()
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    original_model = str(model_name or "").strip()

    if original_model.lower().endswith(_ONE_M_CONTEXT_SUFFIX):
        base_model = original_model[: -len(_ONE_M_CONTEXT_SUFFIX)].strip()
        normalized_base = _pi_normalize_model_key(base_model)
        if normalized_base in _ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS:
            available = {}
            for candidate in launchers._pi_runtime_model_names(runtime, selected_model=model_name):
                normalized_candidate = _pi_normalize_model_key(candidate)
                if normalized_candidate and normalized_candidate not in available:
                    available[normalized_candidate] = str(candidate or "").strip()
            return available.get(normalized_base) or base_model, original_model

    runtime_id = str((runtime or {}).get("id") or (runtime or {}).get("provider_id") or "").strip().lower()
    reference_row = _pi_reference_model_row(model_name)
    routed_model = str(reference_row.get("routed_model_id") or "").strip()
    alias_status = str(reference_row.get("alias_status") or "").strip().lower()
    provider_hint = str(reference_row.get("provider_id") or "").strip().lower()
    normalized_original = _pi_normalize_model_key(model_name)
    normalized_routed = _pi_normalize_model_key(routed_model)
    if not normalized_routed or normalized_routed == normalized_original:
        return original_model, ""

    allow_reference_fallback = False
    if alias_status == "local_selector":
        # Local selectors like `[1m]` are MMS surface sugar and should not leak
        # through to Pi's upstream-facing wire model id.
        allow_reference_fallback = True
    elif (
        protocol_name == "anthropic_messages"
        and alias_status == "local_thinking_alias"
        and runtime_id
        and provider_hint == runtime_id
    ):
        pass
    else:
        return original_model, ""

    available = {}
    for candidate in launchers._pi_runtime_model_names(runtime, selected_model=model_name):
        normalized_candidate = _pi_normalize_model_key(candidate)
        if normalized_candidate and normalized_candidate not in available:
            available[normalized_candidate] = str(candidate or "").strip()
    wire_model = available.get(normalized_routed)
    if not wire_model and allow_reference_fallback:
        wire_model = routed_model
    if not wire_model:
        return original_model, ""
    return wire_model, original_model


def _pi_model_entry(runtime, model_name):
    variant, caps = _pi_pick_protocol(runtime, model_name)
    profile_id = _pi_profile_id(runtime, model_name, base_url=variant["base_url"])
    wire_model_name, display_name = _pi_wire_model_name(runtime, model_name, variant["protocol"])
    if not wire_model_name:
        wire_model_name = model_name
    entry = {
        "id": wire_model_name,
        "name": display_name or model_name,
        "input": _pi_model_input_types(model_name),
        "contextWindow": int(caps.get("context_window_tokens") or 128000),
        "maxTokens": int(caps.get("max_output_tokens") or 16384),
    }
    if bool(caps.get("supports_thinking")):
        entry["reasoning"] = True
    thinking_level_map = _pi_model_thinking_level_map(profile_id, variant["protocol"], model_name, caps)
    if thinking_level_map:
        entry["thinkingLevelMap"] = thinking_level_map
    model_compat = _pi_model_compat(model_name, variant["protocol"])
    if model_compat:
        entry["compat"] = model_compat
    return {
        "model": entry,
        "protocol": variant["protocol"],
        "api": variant["api"],
        "base_url": variant["base_url"],
        "provider_compat": _pi_provider_compat(profile_id, variant["protocol"]),
        "provider_label": variant["label"],
    }


def _pi_group_provider_ref(base_ref, providers_meta, group_index):
    if len(providers_meta) == 1:
        return base_ref
    meta = providers_meta[group_index]
    if meta["protocol"] == "anthropic_messages":
        protocol_slug = "anthropic"
    elif meta["protocol"] == "responses":
        protocol_slug = "responses"
    else:
        protocol_slug = "openai"
    compat_slug = _opencode_config_slug(meta["compat_slug"], "compat")
    if compat_slug == "default":
        return f"{base_ref}-{protocol_slug}"
    return f"{base_ref}-{protocol_slug}-{compat_slug}"


def _pi_build_models_payload(runtime, model_name):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    model = str(model_name or _resolve_model(runtime) or "").strip()
    if not model:
        raise RuntimeError("Pi runtime requires a selected model")
    if not _pi_model_supported(model):
        raise RuntimeError(f"Pi runner does not support image-generation-only model '{model}'")
    block_reason = launchers._pi_model_block_reason(runtime, model)
    if block_reason:
        raise RuntimeError(f"Pi runner currently blocks model '{model}': {block_reason}")
    model_names = launchers._pi_exposed_model_names(runtime, selected_model=model)
    if not model_names:
        raise RuntimeError("Pi runtime requires at least one available model")

    base_ref = _pi_provider_ref(runtime)
    base_name = str(runtime.get("name") or runtime.get("id") or base_ref).strip() or base_ref
    api_key = str(runtime.get("openai_api_key") or runtime.get("api_key") or "").strip()
    groups = []
    groups_by_key = {}
    selected_group_key = None

    for model_name_item in model_names:
        if not _pi_model_supported(model_name_item):
            continue
        resolved = _pi_model_entry(runtime, model_name_item)
        provider_compat = resolved["provider_compat"] if isinstance(resolved["provider_compat"], dict) else {}
        compat_key = json.dumps(provider_compat, sort_keys=True, ensure_ascii=True)
        group_key = (resolved["protocol"], compat_key)
        group = groups_by_key.get(group_key)
        if group is None:
            group = {
                "protocol": resolved["protocol"],
                "api": resolved["api"],
                "base_url": resolved["base_url"],
                "provider_compat": provider_compat,
                "compat_slug": "default" if not provider_compat else compat_key,
                "models": [],
                "_model_ids": set(),
            }
            groups_by_key[group_key] = group
            groups.append(group)
        model_id = str(resolved["model"].get("id") or "").strip()
        if model_id not in group["_model_ids"]:
            group["models"].append(resolved["model"])
            group["_model_ids"].add(model_id)
        if model_name_item == model:
            selected_group_key = group_key

    providers = {}
    selected_provider_ref = ""
    for index, group in enumerate(groups):
        provider_ref = _pi_group_provider_ref(base_ref, groups, index)
        if selected_group_key == (group["protocol"], json.dumps(group["provider_compat"], sort_keys=True, ensure_ascii=True)):
            selected_provider_ref = provider_ref
        provider_name = base_name if len(groups) == 1 else f"{base_name} · {group['api']}"
        payload = {
            "name": provider_name,
            "baseUrl": group["base_url"],
            "api": group["api"],
            "apiKey": api_key,
            "models": group["models"],
        }
        if group["provider_compat"]:
            payload["compat"] = group["provider_compat"]
        providers[provider_ref] = payload

    if not providers:
        raise RuntimeError("Pi runtime did not find any conversational models for the selected provider")
    if not selected_provider_ref:
        selected_provider_ref = next(iter(providers.keys()), base_ref)
    return {"providers": providers}, selected_provider_ref


def _write_pi_models_config(agent_dir, runtime, model_name):
    payload, provider_ref = _pi_build_models_payload(runtime, model_name)
    models_path = os.path.join(agent_dir, "models.json")
    os.makedirs(agent_dir, exist_ok=True)
    atomic_write_text(models_path, json.dumps(payload, indent=2) + "\n", mode=0o600)
    return models_path, provider_ref


def _write_pi_settings_config(agent_dir):
    settings_path = os.path.join(agent_dir, "settings.json")
    os.makedirs(agent_dir, exist_ok=True)
    atomic_write_text(settings_path, json.dumps(_pi_settings_payload(), indent=2) + "\n", mode=0o600)
    return settings_path


def _pi_gateway_env(runtime, model_info=None):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    requested_model = _resolve_model(model_info or runtime)
    model = _pi_effective_selected_model(runtime, requested_model)
    gateway_base = _real_user_path(".config", "mms", "pi-gateway")
    os.makedirs(gateway_base, exist_ok=True)
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(os.getpid()))
    os.makedirs(session_home, exist_ok=True)
    _cleanup_stale_sessions(sessions_dir)

    env = dict(os.environ)
    _scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    _inject_real_home_hints(env, include_xdg=True)
    _inject_host_capability_hints(env)
    _inject_selected_model_name(env, requested_model or model, model_info=model_info)
    _set_session_home_hint(env, session_home)
    env["HOME"] = _real_user_path()
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    env["MMS_PI_SOFT_HOME"] = "1"

    agent_dir = os.path.join(session_home, ".pi", "agent")
    session_dir = os.path.join(agent_dir, "sessions")
    models_path, provider_ref = _write_pi_models_config(agent_dir, runtime, model)
    settings_path = _write_pi_settings_config(agent_dir)
    os.makedirs(session_dir, exist_ok=True)
    env["PI_CODING_AGENT_DIR"] = agent_dir
    env["PI_CODING_AGENT_SESSION_DIR"] = session_dir
    env["PI_TELEMETRY"] = "0"
    env["MMS_PI_MODELS_JSON"] = models_path
    env["MMS_PI_SETTINGS_JSON"] = settings_path
    env["MMS_PI_PROVIDER"] = provider_ref
    env["MMS_PI_SELECTED_MODEL"] = model
    env["MMS_PI_NPX_CACHE"] = _pi_npx_cache_dir()
    wrapper_path = launchers._pi_wrapper_path()
    if wrapper_path:
        env["MMS_PI_BIN"] = wrapper_path

    _apply_runtime_network_profile(env, runtime, validate_proxy=False)
    _apply_runtime_locale_profile(env, runtime)
    _apply_runtime_ip_stack_profile(env, runtime)
    _install_session_command_wrappers(session_home, env)
    _install_session_packet_env(
        env,
        cli="pi",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features={
            "web_access": bool(_resolve_web_access_root()),
            "weber": bool(_resolve_weber_root()),
            "toon": bool(_resolve_toon_root()),
            "token_saver": bool(_resolve_token_saver_root()),
            "xmem": bool(_resolve_xmem_root()),
        },
    )
    return env


def _pi_provider_export_env(runtime, model):
    runtime = runtime if isinstance(runtime, dict) else {}
    launchers = _launchers_module()
    effective_model = _pi_effective_selected_model(runtime, model or runtime.get("model"))
    provider_ref = _opencode_config_slug(runtime.get("id") or runtime.get("name"), "provider")
    model_ref = _opencode_config_slug(effective_model or runtime.get("model"), "model")
    agent_dir = _real_user_path(".config", "mms", "pi-gateway", "exports", f"{provider_ref}-{model_ref}", "agent")
    session_dir = os.path.join(agent_dir, "sessions")
    models_path, selected_provider_ref = _write_pi_models_config(agent_dir, runtime, effective_model)
    settings_path = _write_pi_settings_config(agent_dir)
    os.makedirs(session_dir, exist_ok=True)
    exports = {
        "PI_CODING_AGENT_DIR": agent_dir,
        "PI_CODING_AGENT_SESSION_DIR": session_dir,
        "PI_TELEMETRY": "0",
        "MMS_PI_MODELS_JSON": models_path,
        "MMS_PI_SETTINGS_JSON": settings_path,
        "MMS_PI_PROVIDER": selected_provider_ref,
        "MMS_PI_SELECTED_MODEL": effective_model,
        "MMS_PI_NPX_CACHE": _pi_npx_cache_dir(),
    }
    wrapper_path = launchers._pi_wrapper_path()
    if wrapper_path:
        exports["MMS_PI_BIN"] = wrapper_path
    return exports


def launch_pi(model_info, runtime, once=False, extra_args=None):
    """启动 Pi runner，当前走 MMS provider -> session-local models.json 适配层。"""
    launchers = _launchers_module()
    auth_mode = str(runtime.get("auth_mode") or "api_key").strip() or "api_key"
    if auth_mode != "api_key":
        launchers.console.print("[red]Pi 当前只支持模型源/API key 模式；官方 /login 请直接在 Pi 内使用[/red]")
        raise SystemExit(1)

    requested_model = _resolve_model(model_info)
    model = _pi_effective_selected_model(runtime, requested_model)
    env = _pi_gateway_env(runtime, model_info=model_info)
    provider_ref = str(env.get("MMS_PI_PROVIDER") or _pi_provider_ref(runtime)).strip()
    cmd = ["pi", "--provider", provider_ref]
    if model:
        cmd += ["--model", model]

    thinking_mode = str(runtime.get("thinking_mode") or "").strip().lower()
    reasoning_effort = str(runtime.get("reasoning_effort") or "").strip().lower()
    if thinking_mode == "disable":
        cmd += ["--thinking", "off"]
    elif reasoning_effort in {"minimal", "low", "medium", "high", "xhigh"}:
        cmd += ["--thinking", reasoning_effort]

    if extra_args:
        cmd += list(extra_args)
    _exec_or_run(cmd, env, once)
