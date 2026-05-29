"""Launch-time display helpers for MMS CLI launchers."""

from __future__ import annotations

import json
import os


def _launchers():
    import mms_launchers as _module

    return _module


def show_launch_info(cli, runtime, auth_mode):
    """启动前轻量展示：gateway 可用模型 + 本地用量统计（失败不阻塞）。"""
    launchers = _launchers()
    runtime_kind = runtime.get("runtime_kind", "provider")
    runtime_id = runtime.get("id", "default")

    # ── gateway 可用模型列表 ──
    if auth_mode == "api_key":
        try:
            probe_result = runtime.get("_launch_prefetched_probe")
            if probe_result is None:
                probe_result = launchers._probe_models(runtime, emit_output=False)
            models = list(probe_result.get("models") or [])
            if models:
                launchers.console.print(
                    f"[dim]可用模型 ({len(models)}): {', '.join(models[:8])}"
                    f"{'…' if len(models) > 8 else ''}[/dim]"
                )
        except Exception:
            pass

    # ── 本地用量统计 ──
    try:
        usage_path = launchers._real_user_path(".config", "mms", "usage.json")
        if os.path.exists(usage_path):
            with open(usage_path, "r", encoding="utf-8") as f:
                stats = json.load(f)
            key = f"{runtime_kind}:{cli}:{runtime_id}"
            entry = stats.get("sources", {}).get(key)
            if entry:
                launches = entry.get("launches", 0)
                last_model = entry.get("last_model", "")
                last_at = entry.get("last_used_at", "")[:10]
                parts = [f"历史启动 {launches} 次"]
                if last_model:
                    parts.append(f"上次模型 {last_model}")
                if last_at:
                    parts.append(f"最近 {last_at}")
                launchers.console.print(f"[dim]{' | '.join(parts)}[/dim]")
    except Exception:
        pass

    if cli == "opencode":
        profile_label = str(runtime.get("opencode_profile_label") or runtime.get("opencode_profile") or "lite").strip()
        if profile_label:
            launchers.console.print(f"[dim]OpenCode profile: {profile_label}[/dim]")

    if cli == "claude":
        try:
            one_m = "开启" if launchers._runtime_supports_claude_1m(runtime) else "关闭"
            mode = launchers._normalize_claude_1m_mode((runtime or {}).get("claude_1m_mode", "auto"))
            launchers.console.print(f"[dim]Claude 1M: {one_m} ({mode})[/dim]")
        except Exception:
            pass
        try:
            report = runtime.get("_account_guard_report")
            if report:
                style = {
                    "stable": "green",
                    "watch": "yellow",
                    "risky": "yellow",
                    "blocked": "red",
                }.get(report.get("status"), "dim")
                launchers.console.print(f"[{style}]{launchers._format_account_guard_summary(report)}[/{style}]")
        except Exception:
            pass
    try:
        launchers.console.print(f"[dim]网络: {launchers._runtime_network_summary(runtime)}[/dim]")
    except Exception:
        pass
    try:
        launchers._emit_dns_guard_hint(runtime, cli_name=cli, auth_mode=auth_mode)
    except Exception:
        pass
