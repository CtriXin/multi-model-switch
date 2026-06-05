"""Route export and config backup helpers."""

from __future__ import annotations

import os
import shutil


def trigger_routes_export_after_usage_write(
    *,
    lock,
    is_running,
    set_running,
    get_last_started_at,
    set_last_started_at,
    min_interval_sec,
    refresh_routes_export_for_hive,
    thread_cls,
    monotonic,
):
    now = monotonic()
    with lock:
        if is_running():
            return
        if now - get_last_started_at() < min_interval_sec:
            return
        set_running(True)
        set_last_started_at(now)

    def _run():
        try:
            refresh_routes_export_for_hive(force=True, quiet=True)
        except Exception:
            pass
        finally:
            with lock:
                set_running(False)

    thread_cls(
        target=_run,
        daemon=True,
        name="mms-usage-routes-export",
    ).start()


def backup_config_tree(
    label,
    *,
    resolve_real_user_home,
    primary_config_dir,
    local_now_slug,
    makedirs=os.makedirs,
    path_exists=os.path.exists,
    copytree=shutil.copytree,
):
    backup_root = os.path.join(resolve_real_user_home(), ".config", "mms-backups")
    makedirs(backup_root, exist_ok=True)
    backup_dir = os.path.join(backup_root, f"{label}-{local_now_slug()}")
    makedirs(backup_dir, exist_ok=True)
    if path_exists(primary_config_dir):
        copytree(
            primary_config_dir,
            os.path.join(backup_dir, os.path.basename(primary_config_dir)),
            symlinks=True,
            ignore_dangling_symlinks=True,
        )
    return backup_dir


def refresh_routes_export_for_hive(
    cfg=None,
    *,
    force=True,
    quiet=False,
    startup_safe=False,
    load_config,
    apply_local_overrides,
    export_model_routes,
    console,
):
    try:
        current_cfg = cfg
        if current_cfg is None:
            current_cfg = load_config()
            if current_cfg is None:
                return False
            current_cfg = apply_local_overrides(current_cfg)
        export_model_routes(current_cfg, force=force, startup_safe=startup_safe)
        return True
    except Exception as exc:
        if not quiet:
            console.print(f"[yellow]⚠ Hive routes export 刷新失败: {exc}[/yellow]")
        return False


def trigger_routes_export_after_credentials_write(*, refresh_routes_export_for_hive):
    refresh_routes_export_for_hive(force=True, quiet=True)
