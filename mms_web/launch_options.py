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
    return {"model": {k: info[k] for k in ("id", "name", "input", "contextWindow", "maxTokens", "reasoning") if k in info},
            "protocol": entry["protocol"], "supportedThinkingLevels": levels,
            "configuredThinkingLevel": configured, "defaultThinkingLevel": effective,
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
