"""Launch-time display helpers for MMS CLI launchers."""

from __future__ import annotations

import json
import os
import shlex
import sys
from contextlib import contextmanager
from time import perf_counter


def _launchers():
    import mms_launchers as _module

    return _module


@contextmanager
def launch_status(message, *, spinner="dots", console):
    """Show a best-effort Rich status while preserving non-Rich fallback text."""
    status_cm = None
    try:
        status_cm = console.status(f"[cyan]{message}[/cyan]", spinner=spinner)
        status_cm.__enter__()
    except Exception:
        console.print(f"[dim]⏳ {message}[/dim]")
    start = perf_counter()
    try:
        yield start
    finally:
        if status_cm is not None:
            exc_type, exc, tb = sys.exc_info()
            status_cm.__exit__(exc_type, exc, tb)


def print_launch_step_done(label, started_at, detail=None, *, style="dim", console, perf_counter_fn=perf_counter):
    elapsed = perf_counter_fn() - started_at
    suffix = f" · {detail}" if detail else ""
    console.print(f"[{style}]· {label} 完成 ({elapsed:.1f}s){suffix}[/{style}]")


def launch_timing_threshold_sec(*, environ=os.environ):
    raw = str(environ.get("MMS_LAUNCH_TIMING_THRESHOLD_SEC") or "").strip()
    if not raw:
        return 5.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 5.0


def launch_timing_enabled(*, environ=os.environ):
    return str(environ.get("MMS_LAUNCH_TIMING") or "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def timed_launch_step(timings, label, *, perf_counter_fn=perf_counter):
    start = perf_counter_fn()
    try:
        yield
    finally:
        if isinstance(timings, list):
            timings.append((str(label), perf_counter_fn() - start))


def print_launch_timing_breakdown(
    timings,
    *,
    total_elapsed,
    console,
    launch_timing_enabled_fn,
    launch_timing_threshold_sec_fn,
):
    if not isinstance(timings, list) or not timings:
        return
    if not launch_timing_enabled_fn() and total_elapsed < launch_timing_threshold_sec_fn():
        return
    top = sorted(
        ((label, elapsed) for label, elapsed in timings if elapsed >= 0.05),
        key=lambda item: item[1],
        reverse=True,
    )[:8]
    if not top:
        return
    detail = "；".join(f"{label} {elapsed:.1f}s" for label, elapsed in top)
    console.print(f"[dim]  慢步骤拆分: {detail}[/dim]")


def prepare_claude_env_with_status(
    runtime,
    *,
    claude_gateway_env_fn,
    launch_status_fn,
    print_launch_step_done_fn,
    print_launch_timing_breakdown_fn,
    perf_counter_fn=perf_counter,
    **kwargs,
):
    timings = []
    with launch_status_fn("准备 Claude 会话环境中...", spinner="dots") as step_start:
        env = claude_gateway_env_fn(runtime, _timings=timings, **kwargs)
    selected = kwargs.get("selected_model") or kwargs.get("heavy_model")
    detail = selected if selected else runtime.get("id", "provider")
    total_elapsed = perf_counter_fn() - step_start
    print_launch_step_done_fn("Claude 会话环境准备", step_start, detail)
    print_launch_timing_breakdown_fn(timings, total_elapsed=total_elapsed)
    return env


def print_mms_resume_hint(cli_name, session_id, *, resume_command_name_fn, console, quote_fn=shlex.quote):
    cli_name = str(cli_name or "").strip().lower()
    session_id = str(session_id or "").strip()
    if (
        cli_name not in {"codex", "claude"}
        or not session_id
        or session_id == "None"
        or session_id.startswith("pid-")
    ):
        return
    resume_ref = f"{cli_name}:{session_id}"
    command = f"{resume_command_name_fn()} resume {quote_fn(resume_ref)}"
    console.print(f"[dim][MMS] resume:[/dim] [green]{command}[/green]")


def emit_dns_guard_hint(runtime, *, cli_name, auth_mode, runtime_dns_mode_fn, console):
    if auth_mode != "oauth":
        return
    if cli_name not in {"claude", "codex", "gemini", "agy"}:
        return
    dns_mode = runtime_dns_mode_fn(runtime)
    if dns_mode == "local-risk":
        console.print(
            "[yellow]DNS 风险: 当前 proxy 为 socks5，hostname 可能仍在本地解析；"
            "更稳的是 socks5h 或由上游 relay 负责 remote DNS[/yellow]"
        )
    elif dns_mode == "direct":
        console.print("[yellow]DNS: 当前为 direct，未经过代理 DNS 路径[/yellow]")


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
