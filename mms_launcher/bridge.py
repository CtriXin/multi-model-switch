"""Launcher bridge compatibility helpers."""

from __future__ import annotations

import inspect


def load_bridge_helpers():
    from mms_bridge import (
        _build_gateway_url as _bgw,
        _write_route_status as _wrs,
        codex_chatcompletions_bridge as _cccb,
        codex_claude_bridge as _ccb,
        codex_responses_bridge as _crb,
        gateway_claude_bridge as _gwb,
        gemini_claude_bridge as _gcb,
    )

    return {
        "_build_gateway_url": _bgw,
        "codex_claude_bridge": _ccb,
        "gemini_claude_bridge": _gcb,
        "gateway_claude_bridge": _gwb,
        "codex_chatcompletions_bridge": _cccb,
        "codex_responses_bridge": _crb,
        "_write_route_status": _wrs,
    }


def load_speed_stats_helper():
    from mms_runtime.speed_stats import build_provider_speed_scope

    return build_provider_speed_scope


def gateway_claude_bridge_context(target, *args, console, signature_fn=inspect.signature, **kwargs):
    if target is None:
        raise RuntimeError("gateway_claude_bridge 未初始化")
    signature_target = getattr(target, "__wrapped__", target)
    try:
        signature = signature_fn(signature_target)
    except (TypeError, ValueError):
        signature = None
    if signature is None:
        return target(*args, **kwargs)
    allowed = set(signature.parameters.keys())
    filtered = dict(kwargs)
    dropped = [key for key in list(filtered.keys()) if key not in allowed]
    for key in dropped:
        filtered.pop(key, None)
    if dropped:
        console.print(
            "[yellow]检测到旧版 bridge 签名，已自动降级忽略参数: "
            + ", ".join(sorted(dropped))
            + "[/yellow]"
        )
    return target(*args, **filtered)


__all__ = ["gateway_claude_bridge_context", "load_bridge_helpers", "load_speed_stats_helper"]
