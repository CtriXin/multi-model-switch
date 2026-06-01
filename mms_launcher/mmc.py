"""OAuth Claude manual-only launch guard helpers."""

from __future__ import annotations

import sys


def _launchers():
    import mms_launchers as _module

    return _module


def exit_oauth_claude_manual_only(runtime=None, model_info=None, *, caller="MMS"):
    launchers = _launchers()
    runtime = runtime if isinstance(runtime, dict) else {}
    runtime_label = (
        str(runtime.get("id") or runtime.get("name") or runtime.get("cli") or "claude-oauth").strip()
        or "claude-oauth"
    )
    model_name = launchers._resolve_model(model_info) if model_info else ""
    model_name = str(model_name or "").strip() or "claude-sonnet-4-6"
    launchers.console.print("[red]已阻止 OAuth Claude 自动进入。[/red]")
    launchers.console.print(
        "[yellow]OAuth Claude 现在是 manual-only 保护面：MMS / Hive / fallback / 子进程都不能自动启动它。[/yellow]"
    )
    launchers.console.print(f"[dim]入口: {caller} · runtime={runtime_label} · model={model_name}[/dim]")
    launchers.console.print("[dim]允许的唯一入口：你自己在 real/global shell 手动输入 `claude`，并先跑你的验证脚本。[/dim]")
    raise SystemExit(launchers._CLAUDE_OAUTH_MANUAL_ONLY_EXIT_CODE)
