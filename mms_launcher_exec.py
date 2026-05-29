"""Shared launcher process execution helper."""

from __future__ import annotations

import os
import subprocess
import sys


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
