"""Runtime context-window helpers."""

from __future__ import annotations

import json
import os

MODEL_CONTEXT_WINDOWS = {
    # Claude standard context windows; long-context variants are handled by Claude Code.
    "claude-opus-4-6": 1_000_000,
    "claude-sonnet-4-6": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
    # Kimi / K2 series.
    "kimi-for-coding": 262_144,
    "kimi-k2.5": 262_144,
    "kimi-k2.6": 262_144,
    "kimi-k2.6-code-preview": 262_144,
    "K2.6": 262_144,
    "K2.6-code-preview": 262_144,
    # Qwen hosted long-context models.
    "qwen3.5-plus": 1_000_000,
    "qwen3.6-plus": 1_000_000,
    "qwen3-coder-plus": 1_000_000,
    "qwen3-max": 262_144,
    # GLM family.
    "glm-5": 200_000,
    "glm-5-turbo": 200_000,
    "glm-5.1": 200_000,
    "glm-4.7": 200_000,
    # MiniMax / MiMo defaults.
    "mimo-v2-pro": 262_144,
    "MiniMax-M2.5": 196_608,
    "MiniMax-M2.7": 200_000,
    # GPT-5 family.
    "gpt-5": 1_000_000,
    "gpt-5-mini": 1_000_000,
    "gpt-5-nano": 256_000,
    "gpt-5-codex": 1_000_000,
    "gpt-5.1-codex": 1_000_000,
    "gpt-5.1-codex-max": 1_000_000,
    "gpt-5.1-codex-mini": 1_000_000,
    "gpt-5.2": 1_000_000,
    "gpt-5.2-codex": 1_000_000,
    "gpt-5.3-codex": 1_000_000,
    "gpt-5.3-codex-spark": 1_000_000,
    "gpt-5.4": 1_000_000,
    "gpt-5.4-pro": 1_000_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000
ONE_M_CONTEXT_SUFFIX = "[1m]"
ONE_M_SUFFIX_CONTEXT_WINDOWS = {
    "mimo-v2.5-pro": 1_000_000,
    "mimo-v2.5": 1_000_000,
}
ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS = {
    "mimo-v2.5-pro": 262_144,
    "mimo-v2.5": 262_144,
}
MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS = {
    "mimo-v2.5-pro": 1_048_576,
    "mimo-v2.5": 1_048_576,
}
MIMO_PLAIN_ONE_M_PROVIDER_HINTS = (
    "openrouter",
    "mimo-openai",
    "mimo-direct-openai",
    "xiaomi-openai",
    "openai-mimo",
)


def coerce_context_window(value):
    try:
        window = int(value)
    except Exception:
        return None
    return window if window > 0 else None


def provider_advertises_plain_mimo_1m(provider_id):
    provider = str(provider_id or "").strip().lower()
    return bool(provider and any(token in provider for token in MIMO_PLAIN_ONE_M_PROVIDER_HINTS))


def empty_context_overrides():
    return {"models": {}, "provider_overrides": {}}


def load_model_context_overrides(path, cache):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        cache["mtime"] = None
        cache["data"] = empty_context_overrides()
        return cache["data"]

    if cache["mtime"] == mtime:
        return cache["data"]

    models = {}
    provider_overrides = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        payload = {}

    if isinstance(payload, dict):
        raw_models = payload.get("models", payload)
        if isinstance(raw_models, dict):
            for key, value in raw_models.items():
                if key in {"models", "provider_overrides"}:
                    continue
                window = coerce_context_window(value)
                if window:
                    models[str(key).strip()] = window

        raw_provider_overrides = payload.get("provider_overrides", {})
        if isinstance(raw_provider_overrides, dict):
            for key, value in raw_provider_overrides.items():
                if isinstance(value, dict):
                    provider_id = str(key or "").strip()
                    if not provider_id:
                        continue
                    for model_id, window_value in value.items():
                        window = coerce_context_window(window_value)
                        if window:
                            provider_overrides[f"{provider_id}:{str(model_id).strip()}"] = window
                else:
                    window = coerce_context_window(value)
                    if window:
                        provider_overrides[str(key).strip()] = window

    cache["mtime"] = mtime
    cache["data"] = {
        "models": models,
        "provider_overrides": provider_overrides,
    }
    return cache["data"]


def lookup_context_window(
    model_name,
    provider_id=None,
    *,
    context_overrides_loader=None,
    model_context_windows=None,
    profile_context_window_fn=None,
    capability_resolver=None,
):
    raw_model = str(model_name or "").strip()
    if not raw_model:
        return None

    provider_key = str(provider_id or "").strip()
    raw_lower = raw_model.lower()
    has_1m_suffix = ONE_M_CONTEXT_SUFFIX in raw_lower
    clean = raw_model.replace(ONE_M_CONTEXT_SUFFIX, "").replace(ONE_M_CONTEXT_SUFFIX.upper(), "").strip()
    lower = clean.lower()
    overrides = context_overrides_loader() if callable(context_overrides_loader) else empty_context_overrides()

    def _provider_override_lookup(candidate, candidate_lower):
        if not provider_key:
            return None
        provider_overrides = overrides.get("provider_overrides", {})
        direct = provider_overrides.get(f"{provider_key}:{candidate}")
        if direct is not None:
            return direct
        for key, value in provider_overrides.items():
            try:
                override_provider, override_model = key.split(":", 1)
            except ValueError:
                continue
            if override_provider == provider_key and override_model.lower() == candidate_lower:
                return value
        return None

    def _model_override_lookup(candidate, candidate_lower):
        models = overrides.get("models", {})
        direct = models.get(candidate)
        if direct is not None:
            return direct
        for key, value in models.items():
            if key.lower() == candidate_lower:
                return value
        return None

    provider_exact = _provider_override_lookup(raw_model, raw_lower)
    if provider_exact is not None:
        return provider_exact
    model_exact = _model_override_lookup(raw_model, raw_lower)
    if model_exact is not None:
        return model_exact

    if has_1m_suffix:
        suffixed_window = ONE_M_SUFFIX_CONTEXT_WINDOWS.get(lower)
        if suffixed_window is not None:
            return suffixed_window
    else:
        if provider_advertises_plain_mimo_1m(provider_key):
            plain_one_m_window = MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS.get(lower)
            if plain_one_m_window is not None:
                return plain_one_m_window
        else:
            safe_base_window = ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS.get(lower)
            if safe_base_window is not None:
                return safe_base_window

    if provider_key:
        provider_clean = _provider_override_lookup(clean, lower)
        if provider_clean is not None:
            return provider_clean

    model_clean = _model_override_lookup(clean, lower)
    if model_clean is not None:
        return model_clean

    try:
        if capability_resolver is None:
            from mms_capability_resolver import resolve_model_capabilities as capability_resolver

        caps = capability_resolver(clean, provider_id=provider_id or "")
        if caps.get("sources", {}).get("context_window_tokens") == "approved_facts":
            approved_window = coerce_context_window(caps.get("context_window_tokens"))
            if approved_window is not None:
                return approved_window
    except Exception:
        pass

    if profile_context_window_fn is None:
        from mms_provider_profiles import profile_context_window as profile_context_window_fn

    profiled = profile_context_window_fn(clean, provider_id=provider_id or "")
    if profiled is not None:
        return profiled

    windows = model_context_windows if isinstance(model_context_windows, dict) else MODEL_CONTEXT_WINDOWS
    direct = windows.get(clean)
    if direct is not None:
        return direct
    for key, value in windows.items():
        if key.lower() == lower:
            return value
    return None
