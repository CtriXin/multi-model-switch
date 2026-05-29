"""Codex bounded resume seed and write-back helpers."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone


def _launchers():
    import mms_launchers as _module

    return _module


def _safe_getcwd():
    return _launchers()._safe_getcwd()


def atomic_write_json(path, data, mode=0o600):
    return _launchers().atomic_write_json(path, data, mode=mode)


def atomic_write_text(path, text, mode=0o600):
    return _launchers().atomic_write_text(path, text, mode=mode)


def locked_state_file(path):
    return _launchers().locked_state_file(path)


def _sync_codex_hook_trust_back(session_codex_dir, target_codex_dir):
    return _launchers()._sync_codex_hook_trust_back(session_codex_dir, target_codex_dir)


def _print_mms_resume_hint(cli_name, session_id):
    return _launchers()._print_mms_resume_hint(cli_name, session_id)


def _bounded_env_int(name, default):
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return max(0, int(raw))
    except ValueError:
        return int(default)


def _first_existing_child(source_roots, entry_name, *, want_dir=False):
    for root in source_roots:
        if not root:
            continue
        candidate = os.path.join(root, entry_name)
        if want_dir:
            if os.path.isdir(candidate):
                return candidate
        elif os.path.isfile(candidate) or os.path.islink(candidate):
            return candidate
    return ""


def _existing_children(source_roots, entry_name, *, want_dir=False):
    children = []
    seen = set()
    for root in source_roots:
        if not root:
            continue
        candidate = os.path.join(root, entry_name)
        try:
            real_candidate = os.path.realpath(candidate)
        except OSError:
            real_candidate = candidate
        if real_candidate in seen:
            continue
        if want_dir:
            exists = os.path.isdir(candidate)
        else:
            exists = os.path.isfile(candidate) or os.path.islink(candidate)
        if exists:
            seen.add(real_candidate)
            children.append(candidate)
    return children


def _copy_tail_lines(src, dst, max_lines):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if max_lines <= 0:
        with open(dst, "w", encoding="utf-8") as handle:
            handle.write("")
        os.chmod(dst, 0o600)
        return {"lines": 0, "bytes": 0}

    from collections import deque

    lines = deque(maxlen=int(max_lines))
    with open(src, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            lines.append(line)
    with open(dst, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    os.chmod(dst, 0o600)
    try:
        size = os.path.getsize(dst)
    except OSError:
        size = 0
    return {"lines": len(lines), "bytes": size}


def _safe_relative_path(root, path):
    rel_path = os.path.relpath(path, root)
    if rel_path == "." or rel_path.startswith(".." + os.sep) or rel_path == "..":
        return ""
    return rel_path


def _codex_session_file_cwd(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
        payload = json.loads(first)
    except Exception:
        return ""
    if not isinstance(payload, dict) or payload.get("type") != "session_meta":
        return ""
    meta = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    return os.path.realpath(str(meta.get("cwd") or "").strip()) if meta.get("cwd") else ""


def _path_is_same_or_child(path, root):
    raw_path = str(path or "").strip()
    raw_root = str(root or "").strip()
    if not raw_path or not raw_root:
        return False
    path = os.path.realpath(raw_path)
    root = os.path.realpath(raw_root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _copy_latest_files_from_roots(src_roots, dst_root, max_files, *, max_file_bytes, project_path=""):
    os.makedirs(dst_root, exist_ok=True)
    summary = {
        "files": 0,
        "bytes": 0,
        "skipped_oversize_files": 0,
        "skipped_oversize_bytes": 0,
    }
    if max_files <= 0:
        return summary
    candidates = []
    project_max_file_bytes = _bounded_env_int(
        "MMS_CODEX_RESUME_PROJECT_MAX_FILE_BYTES",
        _launchers()._CODEX_RESUME_PROJECT_MAX_FILE_BYTES,
    )
    project_path = os.path.realpath(str(project_path or ""))
    for src_root in src_roots:
        if not os.path.isdir(src_root):
            continue
        for current_root, _dirs, files in os.walk(src_root):
            for filename in files:
                if filename == ".DS_Store":
                    continue
                src = os.path.join(current_root, filename)
                if not os.path.isfile(src):
                    continue
                try:
                    stat = os.stat(src)
                except OSError:
                    continue
                session_cwd = _codex_session_file_cwd(src)
                project_match = bool(project_path and _path_is_same_or_child(session_cwd, project_path))
                allowed_bytes = max_file_bytes
                if project_match:
                    allowed_bytes = max(max_file_bytes, project_max_file_bytes)
                if stat.st_size > allowed_bytes:
                    summary["skipped_oversize_files"] += 1
                    summary["skipped_oversize_bytes"] += stat.st_size
                    continue
                candidates.append((1 if project_match else 0, stat.st_mtime, src_root, src))
    seen_rel_paths = set()
    for _project_match, _mtime, src_root, src in sorted(candidates, reverse=True)[: int(max_files)]:
        rel_path = _safe_relative_path(src_root, src)
        if not rel_path or rel_path in seen_rel_paths:
            continue
        seen_rel_paths.add(rel_path)
        dst = os.path.join(dst_root, rel_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        summary["files"] += 1
        try:
            summary["bytes"] += os.path.getsize(dst)
        except OSError:
            pass
    return summary


def _copy_latest_files(src_root, dst_root, max_files, *, max_file_bytes):
    return _copy_latest_files_from_roots([src_root], dst_root, max_files, max_file_bytes=max_file_bytes)


def _codex_sibling_session_roots(sessions_dir, *, exclude_session_home="", max_roots=None):
    sessions_dir = str(sessions_dir or "").strip()
    if not os.path.isdir(sessions_dir):
        return []
    exclude_session_home = os.path.realpath(str(exclude_session_home or ""))
    if max_roots is None:
        max_roots = _bounded_env_int("MMS_CODEX_RESUME_BACKFILL_SESSION_ROOTS", 12)
    candidates = []
    for entry in os.listdir(sessions_dir):
        session_home = os.path.join(sessions_dir, entry)
        if not os.path.isdir(session_home):
            continue
        try:
            if exclude_session_home and os.path.realpath(session_home) == exclude_session_home:
                continue
            stat = os.stat(session_home)
        except OSError:
            continue
        codex_root = os.path.join(session_home, ".codex")
        if os.path.isdir(codex_root):
            candidates.append((stat.st_mtime, codex_root))
    return [root for _mtime, root in sorted(candidates, reverse=True)[: int(max_roots)]]


def _seed_codex_bounded_resume(source_roots, session_codex_dir):
    source_roots = [str(root) for root in source_roots if root and os.path.isdir(root)]
    if not source_roots:
        return

    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "limits": {
            "files": {},
            "dirs": {},
            "max_file_bytes": _bounded_env_int("MMS_CODEX_RESUME_MAX_FILE_BYTES", _launchers()._CODEX_RESUME_MAX_FILE_BYTES),
        },
        "seeded": {
            "files": {},
            "dirs": {},
        },
    }

    for entry, default_lines in _launchers()._CODEX_BOUNDED_RESUME_FILES.items():
        src = _first_existing_child(source_roots, entry, want_dir=False)
        dst = os.path.join(session_codex_dir, entry)
        max_lines = _bounded_env_int(f"MMS_CODEX_{entry.upper().replace('.', '_')}_MAX_LINES", default_lines)
        manifest["limits"]["files"][entry] = {"max_lines": max_lines}
        if os.path.exists(dst) or os.path.islink(dst):
            manifest["seeded"]["files"][entry] = {"status": "preexisting"}
            continue
        if src:
            summary = _copy_tail_lines(src, dst, max_lines)
            manifest["seeded"]["files"][entry] = {
                "status": "seeded",
                **summary,
            }
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as handle:
                handle.write("")
            os.chmod(dst, 0o600)
            manifest["seeded"]["files"][entry] = {"status": "empty", "lines": 0, "bytes": 0}

    max_file_bytes = manifest["limits"]["max_file_bytes"]
    for entry, default_limit in _launchers()._CODEX_BOUNDED_RESUME_DIRS.items():
        dst = os.path.join(session_codex_dir, entry)
        max_files = _bounded_env_int(f"MMS_CODEX_{entry.upper()}_MAX_FILES", default_limit)
        manifest["limits"]["dirs"][entry] = {"max_files": max_files}
        if os.path.exists(dst) or os.path.islink(dst):
            manifest["seeded"]["dirs"][entry] = {"status": "preexisting"}
            continue
        src_roots = _existing_children(source_roots, entry, want_dir=True)
        if src_roots:
            summary = _copy_latest_files_from_roots(
                src_roots,
                dst,
                max_files,
                max_file_bytes=max_file_bytes,
                project_path=_safe_getcwd(),
            )
            manifest["seeded"]["dirs"][entry] = {
                "status": "seeded",
                **summary,
            }
        else:
            os.makedirs(dst, exist_ok=True)
            manifest["seeded"]["dirs"][entry] = {
                "status": "empty",
                "files": 0,
                "bytes": 0,
                "skipped_oversize_files": 0,
                "skipped_oversize_bytes": 0,
            }

    try:
        atomic_write_json(os.path.join(session_codex_dir, _launchers()._CODEX_RESUME_SEED_MANIFEST), manifest, mode=0o600)
    except Exception:
        pass


def _set_codex_resume_writeback_root(env, target_codex_dir):
    target_codex_dir = str(target_codex_dir or "").strip()
    if target_codex_dir:
        env[_launchers()._CODEX_RESUME_WRITEBACK_ROOT_ENV] = target_codex_dir


def _codex_index_records(codex_dir):
    path = os.path.join(str(codex_dir or ""), "session_index.jsonl")
    if not os.path.isfile(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if isinstance(record, dict) and str(record.get("id") or "").strip():
                    records.append(record)
    except OSError:
        return []
    return records


def _codex_resume_record_fingerprint(record):
    try:
        return json.dumps(record if isinstance(record, dict) else {}, sort_keys=True, ensure_ascii=False)
    except Exception:
        return ""


def _codex_resume_index_snapshot(codex_dir):
    snapshot = {}
    for record in _codex_index_records(codex_dir):
        session_id = str(record.get("id") or "").strip()
        if session_id:
            snapshot[session_id] = _codex_resume_record_fingerprint(record)
    return snapshot


def _codex_resume_sort_key(record):
    if not isinstance(record, dict):
        return ""
    return str(record.get("updated_at") or record.get("created_at") or record.get("id") or "").strip()


def _codex_resume_hint_session_id(codex_dir, baseline_snapshot):
    baseline_snapshot = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    changed = []
    for record in _codex_index_records(codex_dir):
        session_id = str(record.get("id") or "").strip()
        if not session_id:
            continue
        if baseline_snapshot.get(session_id) != _codex_resume_record_fingerprint(record):
            changed.append(record)
    if not changed:
        return ""
    changed.sort(key=_codex_resume_sort_key, reverse=True)
    return str(changed[0].get("id") or "").strip()


def _merge_tail_lines(src, dst, max_lines):
    summary = {"status": "missing", "lines": 0, "bytes": 0}
    if not os.path.isfile(src):
        return summary

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with locked_state_file(dst):
        try:
            with open(dst, "r", encoding="utf-8", errors="replace") as handle:
                existing = handle.readlines()
        except FileNotFoundError:
            existing = []
        except OSError:
            existing = []
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as handle:
                incoming = handle.readlines()
        except OSError:
            return summary

        # Session files start with the bounded seed; only append the new suffix.
        existing_lines = set(existing)
        append_from = 0
        while append_from < len(incoming) and incoming[append_from] in existing_lines:
            append_from += 1
        merged = existing + incoming[append_from:]
        if max_lines <= 0:
            merged = []
        else:
            merged = merged[-int(max_lines):]
        atomic_write_text(dst, "".join(merged), mode=0o600)
    try:
        size = os.path.getsize(dst)
    except OSError:
        size = 0
    return {"status": "merged", "lines": len(merged), "bytes": size}


def _copy_resume_dir_back(src_root, dst_root, max_files, *, max_file_bytes):
    summary = {
        "status": "missing",
        "files": 0,
        "bytes": 0,
        "skipped_oversize_files": 0,
        "skipped_oversize_bytes": 0,
    }
    if not os.path.isdir(src_root):
        return summary
    summary["status"] = "merged"
    if max_files <= 0:
        return summary

    candidates = []
    for current_root, _dirs, files in os.walk(src_root):
        for filename in files:
            if filename == ".DS_Store":
                continue
            src = os.path.join(current_root, filename)
            if not os.path.isfile(src):
                continue
            rel_path = _safe_relative_path(src_root, src)
            if not rel_path:
                continue
            try:
                stat = os.stat(src)
            except OSError:
                continue
            session_cwd = _codex_session_file_cwd(src)
            project_match = bool(_path_is_same_or_child(session_cwd, _safe_getcwd()))
            allowed_bytes = max_file_bytes
            if project_match:
                allowed_bytes = max(
                    max_file_bytes,
                    _bounded_env_int(
                        "MMS_CODEX_RESUME_PROJECT_MAX_FILE_BYTES",
                        _launchers()._CODEX_RESUME_PROJECT_MAX_FILE_BYTES,
                    ),
                )
            if stat.st_size > allowed_bytes:
                summary["skipped_oversize_files"] += 1
                summary["skipped_oversize_bytes"] += stat.st_size
                continue
            candidates.append((1 if project_match else 0, stat.st_mtime, rel_path, src, stat.st_size))

    for _project_match, _mtime, rel_path, src, src_size in sorted(candidates, reverse=True)[: int(max_files)]:
        dst = os.path.join(dst_root, rel_path)
        should_copy = True
        try:
            dst_stat = os.stat(dst)
            should_copy = dst_stat.st_size != src_size or os.path.getmtime(src) > dst_stat.st_mtime
        except OSError:
            should_copy = True
        if not should_copy:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        summary["files"] += 1
        try:
            summary["bytes"] += os.path.getsize(dst)
        except OSError:
            pass
    return summary


def _sync_codex_bounded_resume_back(session_codex_dir, target_codex_dir):
    session_codex_dir = str(session_codex_dir or "").strip()
    target_codex_dir = str(target_codex_dir or "").strip()
    if not session_codex_dir or not target_codex_dir:
        return {}
    if not os.path.isdir(session_codex_dir):
        return {}
    try:
        if os.path.realpath(session_codex_dir) == os.path.realpath(target_codex_dir):
            return {"status": "same-root"}
    except OSError:
        pass

    os.makedirs(target_codex_dir, exist_ok=True)
    manifest = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": session_codex_dir,
        "target": target_codex_dir,
        "files": {},
        "dirs": {},
    }
    with locked_state_file(os.path.join(target_codex_dir, _launchers()._CODEX_RESUME_WRITEBACK_MANIFEST)):
        for entry, default_lines in _launchers()._CODEX_BOUNDED_RESUME_FILES.items():
            max_lines = _bounded_env_int(f"MMS_CODEX_{entry.upper().replace('.', '_')}_MAX_LINES", default_lines)
            manifest["files"][entry] = _merge_tail_lines(
                os.path.join(session_codex_dir, entry),
                os.path.join(target_codex_dir, entry),
                max_lines,
            )
        max_file_bytes = _bounded_env_int("MMS_CODEX_RESUME_MAX_FILE_BYTES", _launchers()._CODEX_RESUME_MAX_FILE_BYTES)
        for entry, default_limit in _launchers()._CODEX_BOUNDED_RESUME_DIRS.items():
            max_files = _bounded_env_int(f"MMS_CODEX_{entry.upper()}_MAX_FILES", default_limit)
            manifest["dirs"][entry] = _copy_resume_dir_back(
                os.path.join(session_codex_dir, entry),
                os.path.join(target_codex_dir, entry),
                max_files,
                max_file_bytes=max_file_bytes,
            )
        hook_trust = _sync_codex_hook_trust_back(session_codex_dir, target_codex_dir)
        if hook_trust:
            manifest["hook_trust"] = hook_trust
        try:
            atomic_write_json(os.path.join(target_codex_dir, _launchers()._CODEX_RESUME_WRITEBACK_MANIFEST), manifest, mode=0o600)
        except Exception:
            pass
    return manifest


def _sync_codex_bounded_resume_back_from_env(env):
    env = env if isinstance(env, dict) else {}
    target_codex_dir = str(env.get(_launchers()._CODEX_RESUME_WRITEBACK_ROOT_ENV) or "").strip()
    session_home = str(env.get("MMS_SESSION_HOME") or env.get("HOME") or "").strip()
    if not target_codex_dir or not session_home:
        return {}
    return _sync_codex_bounded_resume_back(os.path.join(session_home, ".codex"), target_codex_dir)


def _codex_resume_writeback_callback(env):
    env = env if isinstance(env, dict) else {}
    session_home = str(env.get("MMS_SESSION_HOME") or env.get("HOME") or "").strip()
    session_codex_dir = os.path.join(session_home, ".codex") if session_home else ""
    baseline_snapshot = _codex_resume_index_snapshot(session_codex_dir)

    def _callback(_exit_code=None):
        session_id = ""
        try:
            _sync_codex_bounded_resume_back_from_env(env)
        except Exception:
            pass
        try:
            session_id = _codex_resume_hint_session_id(session_codex_dir, baseline_snapshot)
        except Exception:
            session_id = ""
        _print_mms_resume_hint("codex", session_id)
    return _callback


def _codex_bounded_resume_entries():
    return set(_launchers()._CODEX_BOUNDED_RESUME_FILES) | set(_launchers()._CODEX_BOUNDED_RESUME_DIRS)
