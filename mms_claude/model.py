"""Claude model slot and context helpers for MMS launchers."""

from __future__ import annotations


def runtime_supports_claude_1m(runtime):
    import mms_launchers as _launchers

    explicit = _launchers._normalize_claude_1m_mode((runtime or {}).get("claude_1m_mode", "auto"))
    if explicit == "enable":
        return True
    if explicit == "disable":
        return False
    provider_id = str((runtime or {}).get("id", "")).strip().lower()
    disabled_ids = _launchers._provider_id_set_from_env("MMS_CLAUDE_DISABLE_1M_PROVIDER_IDS")
    if provider_id and provider_id in disabled_ids:
        return False
    return not _launchers._runtime_declares_sensitive_claude(runtime)


def effective_context_window(*models, enable_claude_1m=True, provider_id=None):
    """Return the smallest context window among active Claude-routed models."""
    import mms_launchers as _launchers

    windows = []
    for model in models:
        if not model:
            continue
        raw_model = str(model).strip()
        clean = raw_model.replace("[1m]", "").strip()
        window = _launchers._lookup_context_window(raw_model, provider_id=provider_id)
        if not enable_claude_1m:
            lower = clean.lower()
            if lower.startswith("claude-") and "haiku" not in lower:
                window = 200_000
        windows.append(window or _launchers._DEFAULT_CONTEXT_WINDOW)
    return min(windows) if windows else _launchers._DEFAULT_CONTEXT_WINDOW


def strip_one_m_context_suffix(model_name):
    import mms_launchers as _launchers

    normalized = _launchers._normalized_model_name(model_name)
    if not normalized:
        return ""
    suffix = _launchers._ONE_M_CONTEXT_SUFFIX
    return (
        normalized.replace(suffix, "")
        .replace(suffix.upper(), "")
        .strip()
    )


def is_claude_family_model_name(model_name):
    lower = strip_one_m_context_suffix(model_name).lower()
    return any(token in lower for token in ("claude", "opus", "sonnet", "haiku"))


def is_mimo_one_m_context_selector(model_name):
    import mms_launchers as _launchers

    normalized = _launchers._normalized_model_name(model_name).lower()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    suffix = _launchers._ONE_M_CONTEXT_SUFFIX
    return normalized in {
        f"mimo-v2.5-pro{suffix}",
        f"mimo-v2.5{suffix}",
    }


def claude_visible_model_name(model_name, *, fallback_model=""):
    """Return a model name safe for Claude Code's selected-model validation."""
    import mms_launchers as _launchers

    normalized = _launchers._normalized_model_name(model_name)
    if not normalized:
        return _launchers._normalized_model_name(fallback_model)
    fallback = _launchers._normalized_model_name(fallback_model) or "claude-sonnet-4-6"
    if not is_claude_family_model_name(normalized):
        return fallback
    if (
        _launchers._ONE_M_CONTEXT_SUFFIX in normalized.lower()
        and not is_claude_family_model_name(normalized)
        and is_mimo_one_m_context_selector(normalized)
    ):
        return strip_one_m_context_suffix(normalized)
    return normalized


def apply_claude_visible_model_overrides(target, model_name, *, fallback_model=""):
    visible_model = claude_visible_model_name(model_name, fallback_model=fallback_model)
    if not visible_model:
        return ""
    for key in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        target[key] = visible_model
    return visible_model


def claude_resume_model_name(*candidates):
    import mms_launchers as _launchers

    for candidate in candidates:
        normalized = _launchers._normalized_model_name(candidate)
        if normalized:
            return normalized
    return ""


def primary_claude_model(model_info):
    import mms_launchers as _launchers

    if isinstance(model_info, dict):
        for key in ("model", "sonnet", "opus", "haiku"):
            value = _launchers._normalized_model_name(model_info.get(key))
            if value:
                return value
        return ""
    return _launchers._normalized_model_name(model_info)


def with_1m_suffix(model_name, *, enable_1m=True):
    """Append Claude Code's 1M selector only for Claude opus/sonnet slots."""
    import mms_launchers as _launchers

    normalized = _launchers._normalized_model_name(model_name)
    if not normalized:
        return normalized
    lower = normalized.lower()
    suffix = _launchers._ONE_M_CONTEXT_SUFFIX
    if suffix in lower:
        if (
            not is_claude_family_model_name(normalized)
            and is_mimo_one_m_context_selector(normalized)
        ):
            return strip_one_m_context_suffix(normalized)
        return normalized
    if not enable_1m:
        return normalized
    if any(key in lower for key in ("opus", "sonnet")) and "haiku" not in lower:
        return normalized + suffix
    return normalized


def apply_claude_model_overrides(target, model_info, *, enable_1m=True):
    import mms_launchers as _launchers

    primary_model = primary_claude_model(model_info)
    if not primary_model:
        return ""

    if isinstance(model_info, dict):
        opus_model = _launchers._normalized_model_name(model_info.get("opus")) or primary_model
        sonnet_model = _launchers._normalized_model_name(model_info.get("sonnet")) or primary_model
        haiku_model = _launchers._normalized_model_name(model_info.get("haiku")) or primary_model
        target["ANTHROPIC_DEFAULT_OPUS_MODEL"] = with_1m_suffix(opus_model, enable_1m=enable_1m)
        target["ANTHROPIC_DEFAULT_SONNET_MODEL"] = with_1m_suffix(sonnet_model, enable_1m=enable_1m)
        target["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = haiku_model
        target["ANTHROPIC_MODEL"] = with_1m_suffix(primary_model, enable_1m=enable_1m)
        target["ANTHROPIC_REASONING_MODEL"] = with_1m_suffix(
            sonnet_model or primary_model,
            enable_1m=enable_1m,
        )
        subagent_model = _launchers._normalized_model_name(model_info.get("subagent")) or sonnet_model or primary_model
        target["CLAUDE_CODE_SUBAGENT_MODEL"] = with_1m_suffix(
            subagent_model,
            enable_1m=enable_1m,
        )
        return primary_model

    primary_1m = with_1m_suffix(primary_model, enable_1m=enable_1m)
    for key in (
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_REASONING_MODEL",
        "CLAUDE_CODE_SUBAGENT_MODEL",
    ):
        target[key] = primary_1m
    target["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = primary_model
    return primary_model
