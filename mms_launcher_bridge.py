"""Launcher bridge compatibility helpers."""

from __future__ import annotations

import inspect


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


__all__ = ["gateway_claude_bridge_context"]
