"""Codex session asset materialization helpers."""

from __future__ import annotations

import os
import re
import shutil


def _launchers():
    import mms_launchers as _module

    return _module


def overlay_codex_shared_resume(home_dir, session_home, *, disabled_session_surfaces=None):
    account_codex_dir = os.path.join(home_dir, ".codex")
    real_codex_dir = _launchers()._real_user_path(".codex")
    if os.path.realpath(account_codex_dir) == os.path.realpath(real_codex_dir):
        return ""
    os.makedirs(account_codex_dir, exist_ok=True)

    session_codex_dir = os.path.join(session_home, ".codex")
    if os.path.islink(session_codex_dir):
        os.unlink(session_codex_dir)
    os.makedirs(session_codex_dir, exist_ok=True)
    _launchers()._overlay_codex_plugin_marketplace_cache(
        session_codex_dir,
        [account_codex_dir, real_codex_dir],
    )

    bounded_resume_entries = _launchers()._codex_bounded_resume_entries()
    for entry in os.listdir(account_codex_dir):
        if entry in bounded_resume_entries or _launchers()._codex_entry_is_session_local(entry):
            continue
        src = os.path.join(account_codex_dir, entry)
        dst = os.path.join(session_codex_dir, entry)
        _launchers()._materialize_codex_session_entry_filtered(
            entry,
            src,
            dst,
            disabled_session_surfaces=disabled_session_surfaces,
        )

    source_roots = [account_codex_dir]
    source_roots.extend(
        _launchers()._codex_sibling_session_roots(
            os.path.join(home_dir, "s"),
            exclude_session_home=session_home,
        )
    )
    if os.path.isdir(real_codex_dir) and os.path.realpath(real_codex_dir) != os.path.realpath(account_codex_dir):
        source_roots.append(real_codex_dir)
    _launchers()._seed_codex_bounded_resume(source_roots, session_codex_dir)
    return account_codex_dir


def materialize_codex_session_entry(entry, src, dst, *, disabled_session_surfaces=None):
    return materialize_codex_session_entry_filtered(
        entry,
        src,
        dst,
        disabled_session_surfaces=disabled_session_surfaces,
    )


def materialize_codex_session_entry_filtered(entry, src, dst, *, disabled_session_surfaces=None):
    if entry == "skills" and os.path.isdir(src):
        disabled_names = _launchers()._disabled_skill_names_for_cli(disabled_session_surfaces, "codex")
        if disabled_names or (os.path.isdir(dst) and not os.path.islink(dst)):
            if os.path.islink(dst):
                os.unlink(dst)
            os.makedirs(dst, exist_ok=True)
            for child in os.listdir(src):
                child_dst = os.path.join(dst, child)
                if child in disabled_names:
                    if os.path.islink(child_dst) or os.path.isfile(child_dst):
                        os.unlink(child_dst)
                    elif os.path.isdir(child_dst):
                        shutil.rmtree(child_dst)
                    continue
                child_src = os.path.join(src, child)
                if os.path.exists(child_dst) or os.path.islink(child_dst):
                    continue
                os.symlink(child_src, child_dst)
            return
    if os.path.isdir(src) and os.path.isdir(dst):
        os.makedirs(dst, exist_ok=True)
        for child in os.listdir(src):
            child_src = os.path.join(src, child)
            child_dst = os.path.join(dst, child)
            if os.path.exists(child_dst) or os.path.islink(child_dst):
                continue
            os.symlink(child_src, child_dst)
        return
    if os.path.exists(dst) or os.path.islink(dst):
        return
    if entry in _launchers()._CODEX_COPY_INTO_SESSION_FILES and os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return
    os.symlink(src, dst)


def overlay_codex_plugin_marketplace_cache(session_codex_dir, source_codex_dirs):
    """Seed Codex marketplace cache without exposing the whole volatile .tmp tree."""
    session_codex_dir = str(session_codex_dir or "").strip()
    if not session_codex_dir:
        return
    source_codex_dirs = [str(item or "").strip() for item in (source_codex_dirs or [])]
    tmp_dir = os.path.join(session_codex_dir, ".tmp")
    for entry in _launchers()._CODEX_PLUGIN_MARKETPLACE_CACHE_ENTRIES:
        dst = os.path.join(tmp_dir, entry)
        if os.path.exists(dst) or os.path.islink(dst):
            continue
        for source_codex_dir in source_codex_dirs:
            if not source_codex_dir or os.path.realpath(source_codex_dir) == os.path.realpath(session_codex_dir):
                continue
            src = os.path.join(source_codex_dir, ".tmp", entry)
            if not os.path.exists(src):
                continue
            os.makedirs(tmp_dir, exist_ok=True)
            os.symlink(src, dst)
            break


def codex_entry_is_session_local(entry):
    name = str(entry or "").strip()
    if not name:
        return True
    if name in _launchers()._CODEX_SESSION_LOCAL_ONLY_ENTRIES:
        return True
    if any(name.startswith(prefix) for prefix in _launchers()._CODEX_SESSION_LOCAL_ONLY_PREFIXES):
        return True
    if re.match(r"^(state|logs)_\d+\.sqlite(?:-(?:shm|wal))?$", name):
        return True
    return False
