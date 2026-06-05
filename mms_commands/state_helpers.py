"""State-file and timestamp helpers for command flows."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


def iso_now(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_now_slug(*, now_func=None):
    now = now_func() if now_func is not None else datetime.now()
    return now.strftime("%Y%m%d-%H%M%S")


def load_usage_stats_from_path(usage_path, *, path_exists=os.path.exists):
    if not path_exists(usage_path):
        return {"sources": {}}
    try:
        with open(usage_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("sources", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"sources": {}}


def write_usage_stats_locked(
    usage_path,
    data,
    *,
    ensure_mms_config_guard_files,
    config_write_target_path,
    makedirs=os.makedirs,
    replace=os.replace,
    chmod=os.chmod,
):
    ensure_mms_config_guard_files(config_write_target_path())
    makedirs(os.path.dirname(usage_path), exist_ok=True)
    tmp_path = usage_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    replace(tmp_path, usage_path)
    chmod(usage_path, 0o600)


def load_usage_stats(*, active_usage_path, load_usage_stats_from_path):
    return load_usage_stats_from_path(active_usage_path())


def save_usage_stats(
    data,
    *,
    active_usage_path,
    locked_state_file,
    write_usage_stats_locked,
    trigger_routes_export_after_usage_write,
):
    usage_path = active_usage_path()
    with locked_state_file(usage_path):
        write_usage_stats_locked(usage_path, data)
    trigger_routes_export_after_usage_write()


def update_usage_stats(
    mutator,
    *,
    active_usage_path,
    locked_state_file,
    load_usage_stats_from_path,
    write_usage_stats_locked,
    trigger_routes_export_after_usage_write,
):
    usage_path = active_usage_path()
    with locked_state_file(usage_path):
        stats = load_usage_stats_from_path(usage_path)
        result = mutator(stats)
        write_usage_stats_locked(usage_path, stats)
    trigger_routes_export_after_usage_write()
    return result
