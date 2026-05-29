"""Claude session tree and state helpers for MMS launchers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from time import perf_counter


def cleanup_stale_sessions(sessions_dir, stale_callback=None, *, max_entries=None, max_seconds=None):
    """Clean up dead Claude session homes."""
    import mms_launchers as _launchers

    if not os.path.isdir(sessions_dir):
        return
    start = perf_counter()
    removed = 0
    for name in os.listdir(sessions_dir):
        if max_entries is not None and removed >= int(max_entries):
            break
        if max_seconds is not None and (perf_counter() - start) >= float(max_seconds):
            break
        stale = os.path.join(sessions_dir, name)
        if not os.path.isdir(stale):
            continue
        if _launchers._session_home_is_active(stale):
            continue
        if stale_callback is not None:
            try:
                stale_callback(stale, stale_cleanup=True)
            except Exception:
                pass
        shutil.rmtree(stale, ignore_errors=True)
        removed += 1


def copy_tree_files_if_missing(src, dst):
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel_root = os.path.relpath(root, src)
        target_root = dst if rel_root == "." else os.path.join(dst, rel_root)
        os.makedirs(target_root, exist_ok=True)
        for dirname in dirs:
            os.makedirs(os.path.join(target_root, dirname), exist_ok=True)
        for filename in files:
            source_file = os.path.join(root, filename)
            target_file = os.path.join(target_root, filename)
            if os.path.exists(target_file) or os.path.islink(target_file):
                continue
            try:
                shutil.copy2(source_file, target_file)
            except OSError:
                pass


def normalized_claude_slot_account(value):
    return str(value or "").strip().lower()


def claude_project_resume_dir_names(project_path):
    paths = {
        os.path.abspath(os.path.expanduser(str(project_path or ""))),
        os.path.realpath(os.path.expanduser(str(project_path or ""))),
    }
    names = set()
    for path in paths:
        if not path:
            continue
        names.add(path.replace(os.sep, "-"))
    return sorted(name for name in names if name)


def claude_slot_roots_for_resume_backfill(account_id):
    import mms_launchers as _launchers

    roots = [
        _launchers._real_user_path(".config", "mms", "claude-gateway", "s"),
    ]
    normalized_account_id = normalized_claude_slot_account(account_id)
    if normalized_account_id:
        roots.append(_launchers._real_user_path(".config", "mms", "accounts", normalized_account_id, "s"))
    return roots


def backfill_real_claude_project_resume_files(target_projects_dir, current_cwd):
    import mms_launchers as _launchers

    source_projects_root = _launchers._real_user_path(".claude", "projects")
    if not os.path.isdir(source_projects_root):
        return
    if os.path.realpath(source_projects_root) == os.path.realpath(target_projects_dir):
        return
    for dirname in claude_project_resume_dir_names(current_cwd):
        source_project_dir = os.path.join(source_projects_root, dirname)
        target_project_dir = os.path.join(target_projects_dir, dirname)
        if os.path.realpath(source_project_dir) == os.path.realpath(target_project_dir):
            continue
        _launchers._copy_tree_files_if_missing(source_project_dir, target_project_dir)


def backfill_claude_project_resume_files(target_projects_dir, current_cwd, account_id, current_session_home=""):
    """Recover Claude Code /resume files from older MMS isolated slots."""
    import mms_launchers as _launchers

    target_projects_dir = os.path.abspath(os.path.expanduser(str(target_projects_dir or "")))
    if not target_projects_dir:
        return
    os.makedirs(target_projects_dir, exist_ok=True)
    current_cwd = os.path.realpath(current_cwd or _launchers._safe_getcwd())
    current_session_home = os.path.realpath(current_session_home) if current_session_home else ""
    expected_account = normalized_claude_slot_account(account_id)

    _launchers._backfill_real_claude_project_resume_files(target_projects_dir, current_cwd)

    for slots_root in _launchers._claude_slot_roots_for_resume_backfill(expected_account):
        if not os.path.isdir(slots_root):
            continue
        for name in os.listdir(slots_root):
            slot_home = os.path.join(slots_root, name)
            if not os.path.isdir(slot_home):
                continue
            if current_session_home and os.path.realpath(slot_home) == current_session_home:
                continue
            marker = _launchers.read_slot_marker(slot_home)
            if not isinstance(marker, dict):
                continue
            if os.path.realpath(str(marker.get("cwd") or "")) != current_cwd:
                continue
            marker_account = normalized_claude_slot_account(marker.get("account_id"))
            if expected_account and marker_account != expected_account:
                continue
            source_projects_dir = os.path.join(slot_home, ".claude", "projects")
            if os.path.realpath(source_projects_dir) == os.path.realpath(target_projects_dir):
                continue
            _launchers._copy_tree_files_if_missing(source_projects_dir, target_projects_dir)


def load_project_scoped_claude_resume_session_id(
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    import mms_launchers as _launchers

    normalized_project = os.path.realpath(str(project_path or "").strip())
    normalized_account_id = str(account_id or "").strip()
    normalized_runtime_kind = str(runtime_kind or "").strip()
    normalized_resume_model = _launchers._claude_resume_model_name(resume_model)
    if not normalized_project or not normalized_account_id:
        return None
    try:
        sessions = _launchers.list_indexed_sessions("claude")
    except Exception:
        return None

    candidates: list[tuple[str, str]] = []
    for session in sessions:
        if str(session.get("account_id") or "").strip() != normalized_account_id:
            continue
        session_project = os.path.realpath(
            str(session.get("project_path") or session.get("cwd") or "").strip()
        )
        if session_project != normalized_project:
            continue
        session_runtime_kind = str(session.get("runtime_kind") or "").strip()
        if normalized_runtime_kind and session_runtime_kind and session_runtime_kind != normalized_runtime_kind:
            continue
        if normalized_resume_model:
            session_resume_model = _launchers._claude_resume_model_name(
                session.get("resume_model"),
                session.get("display_model"),
                session.get("selected_model"),
            )
            if session_resume_model != normalized_resume_model:
                continue
        session_id = str(session.get("session_id") or "").strip()
        if not session_id or session_id.startswith("pid-"):
            continue
        sort_key = str(session.get("last_active_at") or session.get("started_at") or "").strip()
        candidates.append((sort_key, session_id))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def overlay_project_scoped_claude_resume_state(
    data,
    project_path,
    *,
    account_id="",
    runtime_kind="",
    resume_model="",
):
    import mms_launchers as _launchers

    payload = dict(data) if isinstance(data, dict) else {}
    normalized_project = os.path.realpath(str(project_path or "").strip())
    if not normalized_project:
        return payload
    session_id = _launchers._load_project_scoped_claude_resume_session_id(
        normalized_project,
        account_id=account_id,
        runtime_kind=runtime_kind,
        resume_model=resume_model,
    )
    if not session_id:
        return payload

    projects = payload.get("projects")
    if not isinstance(projects, dict):
        projects = {}
    entry = projects.get(normalized_project)
    next_entry = dict(entry) if isinstance(entry, dict) else {}
    next_entry["lastSessionId"] = session_id
    projects[normalized_project] = next_entry
    payload["projects"] = projects
    return payload


def link_claude_library_entries(session_home, entries=None):
    import mms_launchers as _launchers

    entries = _launchers._CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST if entries is None else entries
    real_library = _launchers._real_user_path("Library")
    if not os.path.isdir(real_library):
        return

    session_library = os.path.join(session_home, "Library")
    if os.path.islink(session_library):
        try:
            os.unlink(session_library)
        except OSError:
            return
    os.makedirs(session_library, exist_ok=True)

    for entry in entries:
        normalized = str(entry or "").strip()
        if not normalized:
            continue
        src = os.path.join(real_library, normalized)
        dst = os.path.join(session_library, normalized)
        if (not os.path.exists(src) and not os.path.islink(src)) or os.path.exists(dst) or os.path.islink(dst):
            continue
        os.symlink(src, dst)


def link_real_local_bin(session_home):
    import mms_launchers as _launchers

    real_bin = _launchers._real_user_path(".local", "bin")
    if not os.path.isdir(real_bin):
        return
    session_local = os.path.join(session_home, ".local")
    if os.path.islink(session_local):
        try:
            os.unlink(session_local)
        except OSError:
            return
    os.makedirs(session_local, exist_ok=True)
    dst = os.path.join(session_local, "bin")
    if not os.path.exists(dst) and not os.path.islink(dst):
        os.symlink(real_bin, dst)


def ensure_account_library_entries(account_home, entries=None):
    import mms_launchers as _launchers

    entries = _launchers._CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST if entries is None else entries
    account_library = os.path.join(account_home, "Library")
    os.makedirs(account_library, exist_ok=True)
    for entry in entries:
        normalized = str(entry or "").strip()
        if not normalized:
            continue
        os.makedirs(os.path.join(account_library, normalized), exist_ok=True)
    return account_library


def link_account_library_entries(session_home, account_home, entries=None):
    import mms_launchers as _launchers

    entries = _launchers._CLAUDE_SESSION_LIBRARY_ENTRY_ALLOWLIST if entries is None else entries
    account_library = _launchers._ensure_account_library_entries(account_home, entries=entries)
    session_library = os.path.join(session_home, "Library")
    if os.path.islink(session_library):
        if os.path.realpath(session_library) == os.path.realpath(account_library):
            return
        os.unlink(session_library)
    elif os.path.exists(session_library) and not os.path.isdir(session_library):
        os.unlink(session_library)
    if not os.path.exists(session_library) and not os.path.islink(session_library):
        os.symlink(account_library, session_library)


def link_claude_persistent_entry(session_claude_dir, entry, target):
    import mms_launchers as _launchers

    dst = os.path.join(session_claude_dir, entry)
    target = os.path.abspath(os.path.expanduser(str(target)))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if entry.endswith(".jsonl"):
        if not os.path.exists(target):
            Path(target).touch()
    else:
        os.makedirs(target, exist_ok=True)

    if os.path.islink(dst):
        if os.path.realpath(dst) == os.path.realpath(target):
            return
        os.unlink(dst)
    elif os.path.exists(dst):
        if entry == "projects" and os.path.isdir(dst):
            _launchers._copy_tree_files_if_missing(dst, target)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        else:
            os.unlink(dst)

    os.symlink(target, dst)


def prepare_claude_session_tree(
    session_home,
    session_claude_dir,
    *,
    account_id="",
    account_home="",
    runtime_kind="api_key",
    resume_model="",
    skip_real_entries=None,
    source_claude_dir=None,
    allowed_source_entries=None,
):
    import mms_launchers as _launchers

    current_cwd = os.path.realpath(_launchers._safe_getcwd())
    normalized_account_id = str(account_id or "").strip()
    store = _launchers.ensure_claude_project_store(current_cwd, account_id=normalized_account_id)
    skip_real_entries = set(skip_real_entries or ())
    allowed_source_entries = [
        str(entry).strip()
        for entry in (
            allowed_source_entries
            if allowed_source_entries is not None
            else _launchers._CLAUDE_SESSION_SOURCE_ENTRY_ALLOWLIST
        )
        if str(entry or "").strip()
    ]
    allowed_source_entry_set = set(allowed_source_entries)
    scoped_claude_dir = source_claude_dir or _launchers._real_user_path(".claude")
    if os.path.islink(session_claude_dir):
        os.unlink(session_claude_dir)
    os.makedirs(session_claude_dir, exist_ok=True)
    for entry in os.listdir(session_claude_dir):
        if entry in _launchers.CLAUDE_PERSISTENT_ENTRIES or entry in allowed_source_entry_set:
            continue
        dst = os.path.join(session_claude_dir, entry)
        if os.path.islink(dst):
            try:
                os.unlink(dst)
            except OSError:
                pass
    if os.path.isdir(scoped_claude_dir):
        for entry in allowed_source_entries:
            if entry in skip_real_entries or entry in _launchers.CLAUDE_PERSISTENT_ENTRIES:
                continue
            src = os.path.join(scoped_claude_dir, entry)
            dst = os.path.join(session_claude_dir, entry)
            if (not os.path.exists(src) and not os.path.islink(src)) or os.path.exists(dst) or os.path.islink(dst):
                continue
            os.symlink(src, dst)
    for entry in _launchers.CLAUDE_PERSISTENT_ENTRIES:
        target = str(
            _launchers.claude_raw_entry_path(
                entry,
                current_cwd,
                account_id=normalized_account_id,
            )
        )
        if entry == "projects":
            _launchers._backfill_claude_project_resume_files(
                target,
                current_cwd,
                normalized_account_id,
                current_session_home=session_home,
            )
        _launchers._link_claude_persistent_entry(session_claude_dir, entry, target)
    _launchers.record_claude_session_start(
        cwd=current_cwd,
        account_id=normalized_account_id,
        pid=os.getpid(),
        runtime_kind=runtime_kind,
        slot_home=session_home,
        resume_model=resume_model,
    )
    _launchers.write_slot_marker(
        session_home,
        cwd=current_cwd,
        project_key_value=store["project_key"],
        account_id=normalized_account_id,
        runtime_kind=runtime_kind,
        account_home=account_home,
    )


def sync_claude_session_state_to_account_home(session_home, account_home, *, state_mode="oauth"):
    import mms_launchers as _launchers

    account_home = os.path.expanduser(str(account_home or "").strip())
    if not account_home:
        return

    os.makedirs(account_home, exist_ok=True)
    account_claude_dir = os.path.join(account_home, ".claude")
    os.makedirs(account_claude_dir, exist_ok=True)

    sync_pairs = [
        (
            os.path.join(session_home, ".claude.json"),
            os.path.join(account_home, ".claude.json"),
        ),
        (
            os.path.join(session_home, ".claude", "settings.json"),
            os.path.join(account_claude_dir, "settings.json"),
        ),
    ]
    for src, dst in sync_pairs:
        if not os.path.exists(src):
            continue
        try:
            if os.path.basename(dst) == "settings.json":
                with open(src, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if str(state_mode or "").strip() == "ui":
                    cleaned = _launchers._sanitize_claude_inherited_settings_payload(
                        loaded,
                        allow_execution_surfaces=False,
                    )
                else:
                    cleaned = _launchers._sanitize_account_claude_settings_payload(loaded)
                with _launchers.locked_state_file(dst):
                    _launchers.atomic_write_json(dst, cleaned, mode=0o600)
            elif os.path.basename(dst) == ".claude.json":
                with open(src, "r", encoding="utf-8") as f:
                    incoming = json.load(f)
                with _launchers.locked_state_file(dst):
                    existing = _launchers._load_json_dict_unlocked(dst)
                    if str(state_mode or "").strip() == "ui":
                        merged = _launchers._merge_claude_gateway_ui_state_payload(existing, incoming)
                    else:
                        merged = _launchers._merge_oauth_claude_state_payload(existing, incoming)
                    _launchers.atomic_write_json(dst, merged, mode=0o600)
            else:
                shutil.copy2(src, dst)
        except Exception:
            continue


def finalize_claude_slot(session_home, exit_code=None, stale_cleanup=False):
    import mms_launchers as _launchers

    marker = _launchers.read_slot_marker(session_home)
    if not marker:
        return
    try:
        pid = int(os.path.basename(str(session_home)))
    except (TypeError, ValueError):
        return
    cwd = marker.get("cwd") or _launchers._safe_getcwd()
    account_id = str(marker.get("account_id") or "").strip()
    runtime_kind = str(marker.get("runtime_kind") or "").strip()
    account_home = str(marker.get("account_home") or "").strip()
    if not stale_cleanup:
        _launchers._sync_claude_session_state_to_account_home(
            session_home,
            account_home,
            state_mode="oauth" if runtime_kind == "oauth" else "ui",
        )
    session_payload = _launchers.finalize_claude_session(
        cwd=cwd,
        pid=pid,
        account_id=account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
    )
    if not stale_cleanup and isinstance(session_payload, dict):
        _launchers._print_mms_resume_hint("claude", session_payload.get("session_id"))
    _launchers._record_account_guard_finalize(
        account_id,
        exit_code=exit_code,
        stale_cleanup=stale_cleanup,
    )
