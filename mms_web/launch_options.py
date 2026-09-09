"""Public model facts and validated thinking levels for the selected Pi route."""
from .errors import WebError

LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


def supported_levels(model):
    # Pi getSupportedThinkingLevels: null disables a level; xhigh/max opt in.
    if not model.get("reasoning"):
        return ["off"]
    mapping = model.get("thinkingLevelMap") or {}
    return [level for level in LEVELS if mapping.get(level, True) is not None
            and (level not in {"xhigh", "max"} or level in mapping)]


def public_options(runtime, model):
    import mms_core
    import mms_pi_support as pi
    selected = pi._pi_effective_selected_model(runtime, model)
    entry = pi._pi_model_entry(runtime, selected)
    info = entry["model"]
    levels = supported_levels(info)
    configured = str(runtime.get("reasoning_effort") or mms_core._default_reasoning_effort_for_model_info({"model": model})).lower()
    if runtime.get("thinking_mode") == "disable":
        configured = "off"
    # Pi clamps model-incompatible inherited preferences. Expose both, do not
    # pretend a disabled level was applied. Explicit user choices never clamp.
    effective = configured if configured in levels else next((v for v in levels if LEVELS.index(v) >= LEVELS.index(configured if configured in LEVELS else "high")), levels[-1])
    # Where each capability came from, so the page can say whether a value is
    # the user's own setting or something MMF supplied.
    try:
        sources = pi._pi_model_capabilities(runtime, selected).get("sources") or {}
    except Exception:
        sources = {}
    # What MMF knows before any user override. Passing an empty policy stops
    # the resolver reading the policy file, leaving catalogue facts only, which
    # is what a "put it back" control has to restore.
    catalog = {}
    try:
        from mms_capability_resolver import resolve_model_capabilities

        resolved = resolve_model_capabilities(
            selected,
            runtime=runtime,
            provider_id=str(runtime.get("id") or runtime.get("provider_id") or ""),
            base_url=str(runtime.get("anthropic_base_url") or runtime.get("openai_base_url") or ""),
            profile_id=str(runtime.get("profile") or runtime.get("provider_profile") or ""),
            model_policy={},
        )
        catalog = {
            "vision": "image" in pi._pi_model_input_types(selected, caps=resolved),
            "contextWindow": int(resolved.get("context_window_tokens") or 0) or None,
        }
    except Exception:
        catalog = {}
    return {"model": {k: info[k] for k in ("id", "name", "input", "contextWindow", "maxTokens", "reasoning") if k in info},
            "protocol": entry["protocol"], "supportedThinkingLevels": levels,
            "configuredThinkingLevel": configured, "defaultThinkingLevel": effective,
            "capabilitySources": {k: str(sources.get(k) or "") for k in ("supports_vision", "context_window_tokens")},
            "catalog": catalog,
            "thinkingLevelMap": info.get("thinkingLevelMap", {})}


def set_thinking(service, session, level):
    state = service._rpc(session, {"type": "get_state"})
    if level not in supported_levels(state.get("model") or {}):
        raise WebError("EFFORT_UNSUPPORTED", "这条模型通道不支持所选 effort，请重新选择。", 409)
    service._rpc(session, {"type": "set_thinking_level", "level": level})
    actual = service._rpc(session, {"type": "get_state"})
    if actual.get("thinkingLevel") != level:
        raise WebError("EFFORT_NOT_APPLIED", "执行进程没有采用所选 effort，尚未发送任务。", 409)
    session.meta.setdefault("controlSettings", {})["thinking"] = level
    session.meta["runtimeView"] = {"thinkingLevel": level, "supportedThinkingLevels": supported_levels(actual.get("model") or {})}
