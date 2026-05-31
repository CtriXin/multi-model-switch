"""Shared launcher process execution helper."""

from __future__ import annotations

import os
import subprocess
import sys


def print_session_summary(bridge_info, *, print_fn=print):
    """Print a compact session summary when a local bridge exits."""
    if not bridge_info or not isinstance(bridge_info, dict):
        return
    server = bridge_info.get("_server")
    if not server or not hasattr(server, "session_request_count"):
        return
    reqs = getattr(server, "session_request_count", 0)
    if reqs == 0:
        return
    inp = getattr(server, "session_input_tokens", 0)
    out = getattr(server, "session_output_tokens", 0)
    start = getattr(server, "session_start_time", 0)
    if start:
        import time

        elapsed = time.time() - start
    else:
        elapsed = 0
    if elapsed >= 3600:
        dur = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m"
    elif elapsed >= 60:
        dur = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
    else:
        dur = f"{int(elapsed)}s"

    def _fmt_tokens(n):
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    model = getattr(server, "heavy_model", None) or getattr(server, "model_name", "?")
    parts = [dur, model, f"{reqs} reqs"]
    if inp or out:
        parts.append(f"{_fmt_tokens(inp)} in + {_fmt_tokens(out)} out")
    try:
        print_fn(f"\n\033[2m[MMS] {' · '.join(parts)}\033[0m")
    except Exception:
        pass


def exec_or_run(
    cmd,
    env,
    once,
    *,
    cleanup_path=None,
    state_home=None,
    cleanup_context=None,
    exit_callback=None,
    force_subprocess=False,
    bridge_info=None,
    prepare_cli_command_fn,
    console,
    activated_state,
    record_session_child_pid,
    print_session_summary,
):
    """Exec the CLI unless cleanup/callback needs a subprocess."""
    cmd, env, exe = prepare_cli_command_fn(cmd, env)
    if not exe:
        console.print(f"[red]{cmd[0]} 未找到，请先安装[/red]")
        sys.exit(1)
    session_home = str((env or {}).get("MMS_SESSION_HOME") or "").strip()

    if once or cleanup_path or state_home or cleanup_context or exit_callback or force_subprocess:
        exit_code = None
        child = None
        try:
            if state_home:
                with activated_state(state_home):
                    child = subprocess.Popen(cmd, env=env)
                    if session_home:
                        record_session_child_pid(session_home, child.pid)
                    exit_code = child.wait()
            else:
                child = subprocess.Popen(cmd, env=env)
                if session_home:
                    record_session_child_pid(session_home, child.pid)
                exit_code = child.wait()
        except KeyboardInterrupt:
            if child is not None:
                try:
                    exit_code = child.wait(timeout=5)
                except Exception:
                    exit_code = 130
            if exit_code is None:
                exit_code = 130
        finally:
            if exit_callback is not None:
                try:
                    exit_callback(exit_code)
                except Exception:
                    pass
            if cleanup_path and os.path.exists(cleanup_path):
                try:
                    os.remove(cleanup_path)
                except OSError:
                    pass
            if cleanup_context is not None:
                try:
                    cleanup_context.__exit__(None, None, None)
                except (KeyboardInterrupt, Exception):
                    pass
            print_session_summary(bridge_info)
        sys.exit(exit_code or 0)
    else:
        os.execvpe(exe, cmd, env)
