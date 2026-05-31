"""Session guard marker and reservation helpers."""

from __future__ import annotations

import os
import subprocess


def session_guard_marker_path(session_home, marker_name):
    return os.path.join(str(session_home or "").strip(), marker_name)


def session_guard_lock_path(sessions_dir, lock_name):
    return os.path.join(str(sessions_dir or "").strip(), lock_name)


def session_guard_process_identity(pid, *, subprocess_run=subprocess.run):
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return ""
    if normalized_pid <= 0:
        return ""
    try:
        result = subprocess_run(
            ["ps", "-p", str(normalized_pid), "-o", "comm=,lstart="],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return str(result.stdout or "").strip()


def session_guard_pid_alive(pid, *, identity="", os_kill=os.kill, process_identity_fn=session_guard_process_identity):
    try:
        normalized_pid = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized_pid <= 0:
        return False
    try:
        os_kill(normalized_pid, 0)
    except (ProcessLookupError, FileNotFoundError):
        return False
    except PermissionError:
        return True
    if identity:
        return process_identity_fn(normalized_pid) == str(identity or "").strip()
    return True


def read_session_guard_marker(session_home, *, marker_path_fn, load_json_dict_unlocked_fn):
    marker_path = marker_path_fn(session_home)
    if not marker_path:
        return {}
    return load_json_dict_unlocked_fn(marker_path)


def write_session_guard_marker(
    session_home,
    *,
    account_id="",
    runtime_kind="",
    child_pid=None,
    marker_path_fn,
    locked_state_file_fn,
    load_json_dict_unlocked_fn,
    atomic_write_json_fn,
    guard_utc_now_fn,
    process_identity_fn,
    getpid_fn=os.getpid,
    makedirs_fn=os.makedirs,
):
    marker_path = marker_path_fn(session_home)
    if not marker_path:
        return
    makedirs_fn(os.path.dirname(marker_path), exist_ok=True)
    with locked_state_file_fn(marker_path):
        marker = load_json_dict_unlocked_fn(marker_path)
        launcher_pid = int(marker.get("launcher_pid") or getpid_fn())
        marker.update(
            {
                "account_id": str(account_id or marker.get("account_id") or "").strip(),
                "runtime_kind": str(runtime_kind or marker.get("runtime_kind") or "").strip(),
                "session_home": str(session_home or ""),
                "launcher_pid": launcher_pid,
                "launcher_identity": str(
                    marker.get("launcher_identity")
                    or process_identity_fn(launcher_pid)
                    or ""
                ).strip(),
                "updated_at": guard_utc_now_fn(),
            }
        )
        if "created_at" not in marker:
            marker["created_at"] = marker["updated_at"]
        if child_pid is not None:
            try:
                normalized_child_pid = int(child_pid)
            except (TypeError, ValueError):
                normalized_child_pid = 0
            if normalized_child_pid > 0:
                marker["child_pid"] = normalized_child_pid
                marker["child_identity"] = process_identity_fn(normalized_child_pid)
        atomic_write_json_fn(marker_path, marker, mode=0o600)


def session_home_is_active(
    session_home,
    *,
    read_marker_fn,
    pid_alive_fn,
):
    session_home = str(session_home or "").strip()
    if not session_home or not os.path.isdir(session_home):
        return False
    marker = read_marker_fn(session_home)
    if marker:
        if pid_alive_fn(
            marker.get("child_pid"),
            identity=marker.get("child_identity"),
        ):
            return True
        if pid_alive_fn(
            marker.get("launcher_pid"),
            identity=marker.get("launcher_identity"),
        ):
            return True
        return False
    try:
        pid = int(os.path.basename(session_home))
    except (TypeError, ValueError):
        return False
    return pid_alive_fn(pid)


def bounded_env_float(name, default, *, environ=os.environ):
    raw = str(environ.get(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(default)


def reserve_session_home(
    sessions_dir,
    *,
    account_id="",
    runtime_kind="",
    stale_callback=None,
    max_live_sessions=None,
    timings=None,
    getpid_fn=os.getpid,
    makedirs_fn=os.makedirs,
    timed_launch_step_fn,
    locked_state_file_fn,
    session_guard_lock_path_fn,
    cleanup_stale_sessions_fn,
    session_cleanup_launch_max_entries_fn,
    session_cleanup_launch_max_seconds_fn,
    count_live_session_dirs_fn,
    session_home_is_active_fn,
    write_session_guard_marker_fn,
):
    sessions_dir = str(sessions_dir or "").strip()
    if not sessions_dir:
        return "", 0, 0
    makedirs_fn(sessions_dir, exist_ok=True)
    session_home = os.path.join(sessions_dir, str(getpid_fn()))
    with timed_launch_step_fn(timings, "reserve session lock+cleanup"):
        with locked_state_file_fn(session_guard_lock_path_fn(sessions_dir)):
            with timed_launch_step_fn(timings, "stale session cleanup"):
                cleanup_stale_sessions_fn(
                    sessions_dir,
                    stale_callback=stale_callback,
                    max_entries=session_cleanup_launch_max_entries_fn(),
                    max_seconds=session_cleanup_launch_max_seconds_fn(),
                )
            active_before = count_live_session_dirs_fn(sessions_dir)
            if session_home_is_active_fn(session_home):
                active_before = max(0, active_before - 1)
            active_after = active_before + 1
            if max_live_sessions is not None and active_after > int(max_live_sessions):
                return "", active_before, active_after
            makedirs_fn(session_home, exist_ok=True)
            write_session_guard_marker_fn(
                session_home,
                account_id=account_id,
                runtime_kind=runtime_kind,
            )
            return session_home, active_before, active_after
