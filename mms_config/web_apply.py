# -*- coding: utf-8 -*-
"""Apply/write helpers for the MMS config WebUI."""

from __future__ import annotations

import copy
import difflib
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


def _backend():
    from mms_config import web

    return web


def _call_backend(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(_backend(), name)(*args, **kwargs)


def _load_mms_core() -> Any:
    return _call_backend("_load_mms_core")


def _safe_text(value: Any) -> str:
    return _call_backend("_safe_text", value)


def _truthy(value: Any, default: bool = False) -> bool:
    return _call_backend("_truthy", value, default)


def _now_iso() -> str:
    return _call_backend("_now_iso")


def _backend_web_wrapper(name: str) -> bool:
    func = getattr(_backend(), name, None)
    return callable(func) and getattr(func, "__module__", "") == "mms_config.web" and getattr(func, "__name__", "") == name


def _call_backend_override(name: str, default: Any, *args: Any, **kwargs: Any) -> Any:
    func = getattr(_backend(), name, None)
    if callable(func) and not _backend_web_wrapper(name):
        return func(*args, **kwargs)
    return default(*args, **kwargs)


def _pretty_json(payload: dict[str, Any]) -> str:
    return _call_backend_override("_pretty_json", _pretty_json_impl, payload)


def _toml_key(key: Any) -> str:
    return _call_backend_override("_toml_key", _toml_key_impl, key)


def _toml_scalar(value: Any) -> str:
    return _call_backend_override("_toml_scalar", _toml_scalar_impl, value)


def _fallback_toml_dumps(payload: dict[str, Any]) -> str:
    return _call_backend_override("_fallback_toml_dumps", _fallback_toml_dumps_impl, payload)


def _toml_dumps(payload: dict[str, Any]) -> str:
    return _call_backend_override("_toml_dumps", _toml_dumps_impl, payload)


def _toml_text(payload: dict[str, Any]) -> str:
    return _call_backend_override("_toml_text", _toml_text_impl, payload)


def _atomic_write_preferences_toml(path: str, payload: dict[str, Any]) -> None:
    return _call_backend_override("_atomic_write_preferences_toml", _atomic_write_preferences_toml_impl, path, payload)


def _diff_text(before: str, after: str, *, before_name: str, after_name: str) -> str:
    return _call_backend_override("_diff_text", _diff_text_impl, before, after, before_name=before_name, after_name=after_name)


def _pretty_json_impl(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _toml_key_impl(key: Any) -> str:
    text = str(key)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _toml_scalar_impl(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    if value is None:
        return '""'
    if isinstance(value, datetime):
        return json.dumps(value.isoformat(), ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def _fallback_toml_dumps_impl(payload: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_table(mapping: dict[str, Any], prefix: list[str]) -> None:
        scalars: list[tuple[str, Any]] = []
        nested: list[tuple[str, dict[str, Any]]] = []
        for key, value in mapping.items():
            if isinstance(value, dict):
                nested.append((str(key), value))
            else:
                scalars.append((str(key), value))

        if prefix and scalars:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("[" + ".".join(_toml_key(part) for part in prefix) + "]")
        for key, value in scalars:
            lines.append(f"{_toml_key(key)} = {_toml_scalar(value)}")
        for key, value in nested:
            emit_table(value, [*prefix, key])

    emit_table(payload if isinstance(payload, dict) else {}, [])
    return "\n".join(lines).rstrip() + "\n"


def _toml_dumps_impl(payload: dict[str, Any]) -> str:
    try:
        import tomli_w

        return tomli_w.dumps(payload)
    except Exception:
        pass
    try:
        mms_core = _load_mms_core()
        writer = getattr(mms_core, "tomli_w", None)
        if writer is not None:
            return writer.dumps(payload)
    except Exception:
        pass
    return _fallback_toml_dumps(payload)


def _toml_text_impl(payload: dict[str, Any]) -> str:
    return _toml_dumps(payload)


def _atomic_write_preferences_toml_impl(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_toml_dumps(payload))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _diff_text_impl(before: str, after: str, *, before_name: str, after_name: str) -> str:
    if before == after:
        return ""
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )


def _config_root_for_snapshot(config_path: str = "") -> str:
    return _call_backend("_config_root_for_snapshot", config_path)


def _policy_path_for_config(config_path: str = "") -> str:
    return _call_backend("_policy_path_for_config", config_path)


def _sanitize_for_output(value: Any) -> Any:
    return _call_backend("_sanitize_for_output", value)


def mms_config_root_status(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _call_backend("mms_config_root_status", *args, **kwargs)


def build_config_plan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from mms_config.web_plan import build_config_plan as build_config_plan_impl

    return build_config_plan_impl(*args, **kwargs)


def _expected_bundle_revision_from_payload(payload: dict[str, Any] | None) -> str:
    from mms_config.web_plan import _expected_bundle_revision_from_payload as expected_bundle_revision_from_payload_impl

    return expected_bundle_revision_from_payload_impl(payload)


def _route_scope_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_scope_provider_ids_from_payload as route_scope_provider_ids_from_payload_impl

    return route_scope_provider_ids_from_payload_impl(payload)


def _route_refresh_provider_ids_from_payload(payload: dict[str, Any] | None) -> list[str]:
    from mms_config.web_plan import _route_refresh_provider_ids_from_payload as route_refresh_provider_ids_from_payload_impl

    return route_refresh_provider_ids_from_payload_impl(payload)


_REGISTRY_V2_GENERATED_FILES = tuple(getattr(_backend(), "_REGISTRY_V2_GENERATED_FILES", ()))


def _latest_audit_rows(config_path: str, limit: int = 8) -> list[dict[str, Any]]:
    try:
        mms_core = _load_mms_core()
        audit_path = mms_core._config_audit_path(config_path)  # noqa: SLF001
        if not os.path.exists(audit_path):
            return []
        rows = []
        with open(audit_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]
    except Exception:
        return []


def _copy_backup_file(target_path: str, *, config_path: str, label: str) -> str:
    if not target_path or not os.path.exists(target_path):
        return ""
    mms_core = _load_mms_core()
    backup_root = mms_core._config_backup_root(config_path)  # noqa: SLF001
    backup_dir = os.path.join(backup_root, f"{label}-{mms_core._local_now_slug()}")  # noqa: SLF001
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(target_path))
    shutil.copy2(target_path, backup_path)
    shutil.copy2(target_path, f"{backup_path}.bak")
    return backup_path


def _bak_path_for_backup(backup_path: str) -> str:
    bak_path = f"{backup_path}.bak" if backup_path else ""
    return bak_path if bak_path and os.path.exists(bak_path) else ""


def _registry_v2_snapshot_generated_bundle(config_root: str) -> dict[str, Any]:
    generated_dir = os.path.join(config_root, "generated")
    summary: dict[str, Any] = {
        "schema": "mms.setup_web.registry_v2_generated_snapshot.v1",
        "generated_dir": generated_dir,
        "file_names": list(_REGISTRY_V2_GENERATED_FILES),
    }
    if not os.path.isdir(generated_dir):
        summary.update({"skipped": True, "reason": "missing_generated_dir", "files": []})
        return summary
    existing = [name for name in _REGISTRY_V2_GENERATED_FILES if os.path.isfile(os.path.join(generated_dir, name))]
    if not existing:
        summary.update({"skipped": True, "reason": "no_existing_bundle_files", "files": []})
        return summary
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = os.path.join(config_root, "backups", "generated", f"webui-apply-{slug}")
    os.makedirs(backup_dir, exist_ok=True)
    for name in existing:
        target = os.path.join(backup_dir, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(generated_dir, name), target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    manifest_path = os.path.join(backup_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema": "mms.setup_web.registry_v2_generated_snapshot_manifest.v1",
                "created_at": _now_iso(),
                "generated_dir": generated_dir,
                "files": existing,
            },
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    try:
        os.chmod(manifest_path, 0o600)
    except OSError:
        pass
    summary.update({"skipped": False, "backup_dir": backup_dir, "manifest_path": manifest_path, "files": existing})
    return summary


def _registry_v2_restore_generated_bundle(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {"attempted": False, "reason": "missing_snapshot"}
    generated_dir = str(snapshot.get("generated_dir") or "")
    if not generated_dir:
        return {"attempted": False, "reason": "missing_generated_dir"}
    file_names = [str(name) for name in (snapshot.get("file_names") or _REGISTRY_V2_GENERATED_FILES)]
    removed: list[str] = []
    restored: list[str] = []
    backup_dir = str(snapshot.get("backup_dir") or "")
    if not os.path.isdir(generated_dir) and not backup_dir:
        return {
            "attempted": True,
            "snapshot_skipped": bool(snapshot.get("skipped")),
            "removed": removed,
            "restored": restored,
            "backup_dir": backup_dir,
        }
    os.makedirs(generated_dir, exist_ok=True)
    for name in file_names:
        target = os.path.join(generated_dir, name)
        if os.path.exists(target):
            os.remove(target)
            removed.append(name)
    for name in [str(item) for item in (snapshot.get("files") or [])]:
        source = os.path.join(backup_dir, name)
        target = os.path.join(generated_dir, name)
        if backup_dir and os.path.isfile(source):
            shutil.copy2(source, target)
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
            restored.append(name)
    try:
        if not os.listdir(generated_dir):
            os.rmdir(generated_dir)
    except OSError:
        pass
    return {
        "attempted": True,
        "snapshot_skipped": bool(snapshot.get("skipped")),
        "removed": removed,
        "restored": restored,
        "backup_dir": backup_dir,
    }


def _registry_v2_restore_webui_credential_backend(secret_backend: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(secret_backend, dict) or bool(secret_backend.get("skipped")):
        return {"attempted": False, "reason": "not_written"}
    path = str(secret_backend.get("path") or "")
    if not path:
        return {"attempted": False, "reason": "missing_path"}
    backup_path = str(secret_backend.get("backup_path") or "")
    if backup_path and os.path.isfile(backup_path):
        shutil.copy2(backup_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return {"attempted": True, "restored": True, "removed_new_file": False, "backup_path": backup_path}
    if os.path.exists(path):
        os.remove(path)
        return {"attempted": True, "restored": False, "removed_new_file": True, "path": path}
    return {"attempted": True, "restored": False, "removed_new_file": False, "path": path}


def _registry_v2_restore_db_candidate(candidate: dict[str, Any] | None, *, config_root: str) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return {"attempted": False, "reason": "missing_candidate"}
    backup = candidate.get("backup") if isinstance(candidate.get("backup"), dict) else {}
    backup_path = str(backup.get("backup_path") or "")
    db_path = str(candidate.get("db_path") or backup.get("source_db_path") or "")
    if backup_path:
        from mms_registry.cli import restore_registry_db

        restore = restore_registry_db(
            backup_path,
            config_dir=config_root,
            db_path=db_path or None,
            apply=True,
            reason="webui-registry-v2-preview-apply-rollback",
        )
        return {"attempted": True, "restored": True, "removed_new_db": False, "restore": restore}
    if backup.get("reason") == "new_db" and db_path:
        removed: list[str] = []
        for suffix in ("", "-wal", "-shm"):
            target = f"{db_path}{suffix}"
            if os.path.exists(target):
                os.remove(target)
                removed.append(target)
        return {"attempted": True, "restored": False, "removed_new_db": bool(removed), "removed": removed}
    return {"attempted": False, "reason": "no_candidate_backup", "db_path": db_path}


def _rollback_registry_v2_preview_apply(
    *,
    config_root: str,
    candidate: dict[str, Any] | None,
    secret_backend: dict[str, Any] | None,
    generated_snapshot: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "attempted": True,
        "reason": reason,
        "generated": _registry_v2_restore_generated_bundle(generated_snapshot),
        "credential_backend": _registry_v2_restore_webui_credential_backend(secret_backend),
        "db": _registry_v2_restore_db_candidate(candidate, config_root=config_root),
    }


def _append_audit(*, config_path: str, target_path: str, backup_path: str, reason: str, before_sha1: str, after_sha1: str, function: str) -> None:
    mms_core = _load_mms_core()
    mms_core._append_config_audit_entry(  # noqa: SLF001
        {
            "timestamp": mms_core._iso_now(),  # noqa: SLF001
            "reason": reason,
            "target_path": os.path.abspath(target_path),
            "backup_path": backup_path,
            "caller_path": os.path.abspath(getattr(_backend(), "__file__", __file__)),
            "caller_line": 0,
            "caller_function": function,
            "pid": os.getpid(),
            "before_sha1": before_sha1,
            "after_sha1": after_sha1,
        },
        config_path=config_path,
    )


def _save_provider_credentials_audited(update: dict[str, str], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    target_path = getattr(mms_core, "CREDENTIALS_PATH")
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        backup_path = _copy_backup_file(target_path, config_path=lock_path, label="credentials-write")
        mms_core.save_provider_credentials(
            update["provider_id"],
            update.get("base_url", ""),
            update.get("api_key", ""),
            openai_base_url=update.get("openai_base_url", ""),
            anthropic_base_url=update.get("anthropic_base_url", ""),
            openai_api_key=update.get("openai_api_key") if "openai_api_key" in update else None,
        )
        after_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=target_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_credentials",
        )
    return {"provider_id": update["provider_id"], "target_path": os.path.abspath(target_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def _write_model_policy_audited(policy_path: str, payload: dict[str, Any], *, config_path: str, reason: str) -> dict[str, str]:
    mms_core = _load_mms_core()
    lock_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        backup_path = _copy_backup_file(policy_path, config_path=lock_path, label="model-policy-write")
        os.makedirs(os.path.dirname(policy_path), exist_ok=True)
        tmp_path = f"{policy_path}.tmp-{os.getpid()}-{time.time_ns()}"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(_pretty_json(payload))
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, policy_path)
        os.chmod(policy_path, 0o600)
        after_sha1 = mms_core._sha1_file(policy_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=policy_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_model_policy",
        )
    return {"target_path": os.path.abspath(policy_path), "backup_path": backup_path, "bak_path": _bak_path_for_backup(backup_path)}


def _preferences_target_path(*, config_path: str = "", preferences_path: str = "") -> str:
    preferences_path = _safe_text(preferences_path)
    if preferences_path:
        return os.path.abspath(os.path.expanduser(preferences_path))
    if config_path:
        return os.path.join(os.path.dirname(os.path.abspath(config_path)), "preferences.toml")
    mms_core = _load_mms_core()
    paths = getattr(mms_core, "PREFERENCES_PATHS", None)
    if isinstance(paths, list) and paths:
        return os.path.abspath(os.path.expanduser(str(paths[0])))
    return os.path.abspath(os.path.expanduser("~/.config/mms/preferences.toml"))


def _preferences_lock_path(*, config_path: str = "", preferences_path: str = "") -> str:
    if config_path:
        return os.path.abspath(config_path)
    target = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    return os.path.join(os.path.dirname(target), "config.toml")


def _load_preferences_raw(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    mms_core = _load_mms_core()
    try:
        loaded = mms_core._load_toml_file(path)  # noqa: SLF001
    except Exception:
        loaded = {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_asset_preferences_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    disabled = payload.get("disabled")
    if not isinstance(disabled, dict):
        disabled = ((payload.get("session_surfaces") or {}).get("disabled") if isinstance(payload.get("session_surfaces"), dict) else {})
    launch_payload = payload.get("launch") if isinstance(payload.get("launch"), dict) else {}
    disabled_clis_raw = payload.get("disabled_clis")
    if disabled_clis_raw is None:
        disabled_clis_raw = launch_payload.get("disabled_clis")
    assets = payload.get("assets") if isinstance(payload.get("assets"), dict) else {}
    mms_core = _load_mms_core()
    sanitize_disabled = getattr(mms_core, "_sanitize_disabled_session_surfaces", None)
    if callable(sanitize_disabled):
        disabled_clean = sanitize_disabled(disabled)
    else:
        disabled_clean = {}
    sanitize_disabled_clis = getattr(mms_core, "_sanitize_disabled_clis", None)
    if callable(sanitize_disabled_clis):
        disabled_clis = sanitize_disabled_clis(disabled_clis_raw)
    else:
        disabled_clis = []
    normalized: dict[str, Any] = {"session_surfaces": {"disabled": disabled_clean}, "assets": {}, "launch": {}}
    if disabled_clis_raw is not None:
        normalized["launch"]["disabled_clis"] = disabled_clis
    if "managed_enabled" in assets:
        normalized["assets"]["managed_enabled"] = _truthy(assets.get("managed_enabled"), default=True)
    managed_root = _safe_text(assets.get("managed_root"))
    if managed_root:
        normalized["assets"]["managed_root"] = os.path.abspath(os.path.expanduser(managed_root))
    return normalized


def _merge_asset_preferences(current: dict[str, Any], asset_preferences: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(current) if isinstance(current, dict) else {}
    incoming_launch = asset_preferences.get("launch") if isinstance(asset_preferences.get("launch"), dict) else {}
    if "disabled_clis" in incoming_launch:
        launch = result.get("launch") if isinstance(result.get("launch"), dict) else {}
        launch["disabled_clis"] = copy.deepcopy(incoming_launch.get("disabled_clis") or [])
        result["launch"] = launch

    session_surfaces = result.get("session_surfaces") if isinstance(result.get("session_surfaces"), dict) else {}
    disabled = ((asset_preferences.get("session_surfaces") or {}).get("disabled") if isinstance(asset_preferences.get("session_surfaces"), dict) else {})
    session_surfaces["disabled"] = copy.deepcopy(disabled) if isinstance(disabled, dict) else {}
    result["session_surfaces"] = session_surfaces

    assets = result.get("assets") if isinstance(result.get("assets"), dict) else {}
    incoming_assets = asset_preferences.get("assets") if isinstance(asset_preferences.get("assets"), dict) else {}
    for key in ("managed_enabled", "managed_root"):
        if key in incoming_assets:
            assets[key] = incoming_assets[key]
    result["assets"] = assets
    return result

def build_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    target_path = _preferences_target_path(config_path=config_path, preferences_path=preferences_path)
    current = _load_preferences_raw(target_path)
    asset_preferences = _normalize_asset_preferences_payload(payload)
    next_prefs = _merge_asset_preferences(current, asset_preferences)
    before_text = _toml_text(current)
    after_text = _toml_text(next_prefs)
    diff_text = _diff_text(before_text, after_text, before_name="preferences.toml(before)", after_name="preferences.toml(after)")
    disabled = ((asset_preferences.get("session_surfaces") or {}).get("disabled") or {}) if isinstance(asset_preferences.get("session_surfaces"), dict) else {}
    disabled_clis = ((asset_preferences.get("launch") or {}).get("disabled_clis") or []) if isinstance(asset_preferences.get("launch"), dict) else []
    return {
        "ok": True,
        "schema": "mms.setup_web.preferences_plan.v1",
        "status": "planned",
        "target_path": target_path,
        "exists": os.path.exists(target_path),
        "will_write": bool(diff_text),
        "diff": diff_text,
        "preferences": next_prefs,
        "summary": {
            "disabled_clis": len(disabled_clis),
            "skills": len(disabled.get("skills") or []),
            "mcp": len(disabled.get("mcp") or []),
            "hooks": len(disabled.get("hooks") or []),
            "managed_root": ((asset_preferences.get("assets") or {}).get("managed_root") if isinstance(asset_preferences.get("assets"), dict) else ""),
        },
    }


def _copy_preferences_backup(target_path: str, *, lock_path: str) -> str:
    mms_core = _load_mms_core()
    backup_root = mms_core._config_backup_root(lock_path)  # noqa: SLF001
    backup_dir = os.path.join(backup_root, f"preferences-write-{mms_core._local_now_slug()}")  # noqa: SLF001
    os.makedirs(backup_dir, exist_ok=True)
    if os.path.exists(target_path):
        backup_path = os.path.join(backup_dir, os.path.basename(target_path))
        shutil.copy2(target_path, backup_path)
        shutil.copy2(target_path, f"{backup_path}.bak")
        return backup_path
    marker_path = os.path.join(backup_dir, f"{os.path.basename(target_path) or 'preferences.toml'}.missing")
    with open(marker_path, "w", encoding="utf-8") as handle:
        handle.write(f"missing before preferences write: {target_path}\n")
    os.chmod(marker_path, 0o600)
    return marker_path

def apply_preferences_plan(
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_preferences"), False):
        return {"ok": False, "schema": "mms.setup_web.preferences_save_result.v1", "status": "blocked", "errors": ["保存 Skill/MCP 偏好前必须勾选确认。"]}
    if _safe_text(payload.get("confirm_phrase")) != "保存偏好":
        return {"ok": False, "schema": "mms.setup_web.preferences_save_result.v1", "status": "blocked", "errors": ["确认文字必须输入：保存偏好"]}
    plan = build_preferences_plan(payload, config_path=config_path, preferences_path=preferences_path)
    if not plan.get("will_write"):
        return {
            "ok": True,
            "schema": "mms.setup_web.preferences_save_result.v1",
            "status": "no_change",
            "target_path": plan.get("target_path"),
            "summary": plan.get("summary") or {},
            "message": "preferences.toml 已是当前 Skill/MCP 偏好。",
        }

    mms_core = _load_mms_core()
    target_path = str(plan.get("target_path") or "")
    lock_path = _preferences_lock_path(config_path=config_path, preferences_path=preferences_path)
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:asset-preferences"
    with mms_core._locked_config_write(lock_path):  # noqa: SLF001
        before_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        backup_path = _copy_preferences_backup(target_path, lock_path=lock_path)
        _atomic_write_preferences_toml(target_path, plan["preferences"])
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass
        after_sha1 = mms_core._sha1_file(target_path)  # noqa: SLF001
        _append_audit(
            config_path=lock_path,
            target_path=target_path,
            backup_path=backup_path,
            reason=reason,
            before_sha1=before_sha1,
            after_sha1=after_sha1,
            function="setup_web_save_preferences",
        )
    return {
        "ok": True,
        "schema": "mms.setup_web.preferences_save_result.v1",
        "status": "saved",
        "target_path": target_path,
        "backup_path": backup_path,
        "bak_path": _bak_path_for_backup(backup_path),
        "summary": plan.get("summary") or {},
        "diff": plan.get("diff") or "",
        "audit_tail": _latest_audit_rows(lock_path),
    }


def _expand_reveal_path(raw_path: Any) -> str:
    path = _safe_text(raw_path)
    if not path or "\x00" in path or "\n" in path or "\r" in path or "://" in path:
        return ""
    if path.startswith("~"):
        try:
            mms_core = _load_mms_core()
            real_home = mms_core.resolve_real_user_home()
        except Exception:
            real_home = os.path.expanduser("~")
        if path == "~":
            path = real_home
        elif path.startswith("~/"):
            path = os.path.join(real_home, path[2:])
        else:
            path = os.path.expanduser(path)
    else:
        path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    return path

def reveal_local_path(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Reveal a local file/folder from the local WebUI without shell execution."""
    payload = payload if isinstance(payload, dict) else {}
    target_path = _expand_reveal_path(payload.get("path"))
    if not target_path:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "blocked",
            "errors": ["只能打开本地文件或目录路径。"],
        }

    exists = os.path.exists(target_path)
    reveal_path = target_path if exists else os.path.dirname(target_path)
    if not reveal_path or not os.path.exists(reveal_path):
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "missing",
            "path": target_path,
            "errors": ["路径和父目录都不存在，无法打开。"],
        }

    if sys.platform == "darwin":
        command = ["open", reveal_path] if os.path.isdir(target_path) else ["open", "-R", reveal_path]
    elif sys.platform.startswith("win"):
        command = ["explorer", reveal_path if os.path.isdir(target_path) else f"/select,{reveal_path}"]
    else:
        folder = reveal_path if os.path.isdir(reveal_path) else os.path.dirname(reveal_path)
        opener = shutil.which("xdg-open")
        if not opener:
            return {
                "ok": False,
                "schema": "mms.setup_web.reveal_path_result.v1",
                "status": "blocked",
                "path": target_path,
                "errors": ["当前系统未找到 xdg-open，无法自动打开文件夹。"],
            }
        command = [opener, folder]

    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
    except Exception as exc:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "error",
            "path": target_path,
            "errors": [str(exc)],
        }

    if result.returncode != 0:
        return {
            "ok": False,
            "schema": "mms.setup_web.reveal_path_result.v1",
            "status": "error",
            "path": target_path,
            "errors": [f"打开路径失败，退出码 {result.returncode}。"],
        }
    return {
        "ok": True,
        "schema": "mms.setup_web.reveal_path_result.v1",
        "status": "opened",
        "path": target_path,
        "opened_path": reveal_path,
        "exists": exists,
        "kind": "directory" if os.path.isdir(target_path) else ("file" if exists else "parent"),
    }

def apply_config_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_save"), False):
        return {"ok": False, "errors": ["保存前必须勾选确认保存。"], "status": "blocked"}
    if _safe_text(payload.get("confirm_phrase")) != "保存配置":
        return {"ok": False, "errors": ["确认文字必须输入：保存配置"], "status": "blocked"}
    config_root = _config_root_for_snapshot(config_path)
    try:
        from mms_runtime.state_io import mms_config_root_status

        root_status = mms_config_root_status(command="mms-config-web", config_dir=config_root or None)
    except Exception:
        root_status = {}
    if root_status.get("mode") == "preview":
        return {
            "ok": False,
            "schema": "mms.setup_web.save_result.v1",
            "status": "blocked",
            "errors": ["preview root 已禁用 legacy /api/save；请使用“写入预览 DB + 发布”。"],
            "root": root_status,
        }
    plan = build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, include_secrets=True)
    if not plan.get("ok"):
        return {
            "ok": False,
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "status": "blocked",
            "plan": _sanitize_for_output(plan),
        }

    mms_core = _load_mms_core()
    reason = _safe_text(payload.get("reason")) or "setup-web-ui:interactive-save"
    target_config_path = config_path or mms_core._config_write_target_path()  # noqa: SLF001
    save_report: dict[str, Any] = {"config": {}, "credentials": [], "model_policy": {}, "routes_export": False}
    webui_config_backup_path = _copy_backup_file(target_config_path, config_path=target_config_path, label="setup-web-config-write")
    mms_core.save_config(plan["config"], reason=reason)
    save_report["config"] = {
        "target_path": os.path.abspath(target_config_path),
        "backup_path": webui_config_backup_path,
        "bak_path": _bak_path_for_backup(webui_config_backup_path),
    }

    for update in plan.get("credential_updates") or []:
        save_report["credentials"].append(_save_provider_credentials_audited(update, config_path=target_config_path, reason=f"{reason}:credentials"))

    policy_path = plan.get("paths", {}).get("model_policy") or _policy_path_for_config(target_config_path)
    if policy_path:
        save_report["model_policy"] = _write_model_policy_audited(policy_path, plan["model_policy"], config_path=target_config_path, reason=f"{reason}:model-policy")

    try:
        save_report["routes_export"] = bool(mms_core._refresh_routes_export_for_hive(plan["config"], force=True, quiet=True, startup_safe=True))  # noqa: SLF001
    except Exception:
        save_report["routes_export"] = False

    return {
        "ok": True,
        "schema": "mms.setup_web.save_result.v1",
        "status": "saved",
        "summary": plan.get("summary") or {},
        "warnings": plan.get("warnings") or [],
        "paths": plan.get("paths") or {},
        "save_report": save_report,
        "audit_tail": _latest_audit_rows(target_config_path),
    }

def apply_registry_v2_preview_plan(
    current_cfg: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    *,
    config_path: str = "",
    preferences_path: str = "",
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    if not _truthy(payload.get("confirm_v2_preview"), False):
        return {"ok": False, "errors": ["写入预览 DB 前必须勾选确认。"], "status": "blocked"}
    if _safe_text(payload.get("confirm_phrase")) != "写入预览DB":
        return {"ok": False, "errors": ["确认文字必须输入：写入预览DB"], "status": "blocked"}
    plan = build_config_plan(current_cfg, payload, config_path=config_path, preferences_path=preferences_path, include_secrets=True, command_name="mmf")
    if not plan.get("ok"):
        return {
            "ok": False,
            "errors": plan.get("errors") or [],
            "warnings": plan.get("warnings") or [],
            "status": "blocked",
            "plan": _sanitize_for_output(plan),
        }
    v2_plan = plan.get("registry_v2_save_plan") if isinstance(plan.get("registry_v2_save_plan"), dict) else {}
    blocked_reasons = [str(item) for item in (v2_plan.get("blocked_reasons") or []) if str(item or "").strip()]
    if blocked_reasons:
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "blocked",
            "errors": blocked_reasons,
            "registry_v2_save_plan": v2_plan,
            "route_publish_guard": _sanitize_for_output(v2_plan.get("route_publish_guard") if isinstance(v2_plan.get("route_publish_guard"), dict) else {}),
        }

    config_root = _config_root_for_snapshot(config_path)
    route_publish_guard: dict[str, Any] = {}
    try:
        from mms_registry.cli import registry_v2_route_publish_guard

        route_publish_guard = registry_v2_route_publish_guard(
            config_dir=config_root or None,
            config_payload=plan.get("config") if isinstance(plan.get("config"), dict) else {},
            policy_payload=plan.get("model_policy") if isinstance(plan.get("model_policy"), dict) else {},
            credential_updates=[item for item in (plan.get("credential_updates") or []) if isinstance(item, dict)],
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload),
            route_scope_provider_ids=_route_scope_provider_ids_from_payload(payload),
            route_refresh_provider_ids=_route_refresh_provider_ids_from_payload(payload),
        )
    except Exception as exc:
        route_publish_guard = {
            "ok": False,
            "reason": "route_publish_guard_error",
            "message": f"{type(exc).__name__}: {exc}",
        }
    if not route_publish_guard.get("ok"):
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "blocked",
            "errors": [str(route_publish_guard.get("message") or route_publish_guard.get("reason") or "route publish guard blocked")],
            "registry_v2_save_plan": v2_plan,
            "route_publish_guard": _sanitize_for_output(route_publish_guard),
        }
    candidate: dict[str, Any] | None = None
    secret_backend: dict[str, Any] | None = None
    generated_snapshot: dict[str, Any] | None = None
    try:
        from mms_registry.cli import apply_registry_v2_save_candidate, publish_preview_bundle, verify_approved_bundle, write_registry_v2_webui_secret_backend

        credential_updates = [item for item in (plan.get("credential_updates") or []) if isinstance(item, dict)]
        generated_snapshot = _registry_v2_snapshot_generated_bundle(config_root)
        candidate = apply_registry_v2_save_candidate(
            config_dir=config_root or None,
            config_payload=plan.get("config") if isinstance(plan.get("config"), dict) else {},
            policy_payload=plan.get("model_policy") if isinstance(plan.get("model_policy"), dict) else {},
            credential_updates=credential_updates,
            apply=True,
            command_name="mms-config-web",
            expected_bundle_revision=_expected_bundle_revision_from_payload(payload),
            route_scope_provider_ids=_route_scope_provider_ids_from_payload(payload),
            route_refresh_provider_ids=_route_refresh_provider_ids_from_payload(payload),
        )
        secret_backend = write_registry_v2_webui_secret_backend(
            config_dir=config_root or None,
            credential_updates=credential_updates,
            command_name="mms-config-web",
        )
        publish = publish_preview_bundle(config_dir=config_root or None)
        verify = verify_approved_bundle(config_dir=config_root or None)
    except Exception as exc:
        rollback = _rollback_registry_v2_preview_apply(
            config_root=config_root,
            candidate=candidate,
            secret_backend=secret_backend,
            generated_snapshot=generated_snapshot,
            reason=f"{type(exc).__name__}: {exc}",
        )
        return {
            "ok": False,
            "schema": "mms.setup_web.registry_v2_apply_result.v1",
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "registry_v2_save_plan": v2_plan,
            "rollback": rollback,
        }

    verified = bool(verify.get("verified"))
    runtime_ready = publish.get("runtime_ready") is True
    missing_api_keys = int(publish.get("missing_api_key_count") or 0)
    missing_base_urls = int(publish.get("missing_base_url_count") or 0)
    provider_route_count = int(publish.get("provider_route_count") or 0)
    route_count = int(publish.get("route_count") or 0)
    runtime_next_action = {}
    if verified and not runtime_ready:
        if missing_api_keys:
            runtime_next_action = {
                "label": "填写 API Key 并勾选更新凭据后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里输入 API Key，勾选更新凭据，再点写入预览 DB + 发布",
            }
        elif missing_base_urls:
            runtime_next_action = {
                "label": "补齐 OpenAI/Anthropic base URL 后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里补齐 base URL，再点写入预览 DB + 发布",
            }
        elif provider_route_count <= 0:
            runtime_next_action = {
                "label": "给通道添加至少一个可见模型后重新写入预览 DB + 发布",
                "command": "在 WebUI 通道里添加 fallback/extra/可见模型，再点写入预览 DB + 发布",
            }
    credential_backend = {
        "schema": secret_backend.get("schema"),
        "skipped": bool(secret_backend.get("skipped")),
        "path": secret_backend.get("path"),
        "count": secret_backend.get("updated_secret_count", secret_backend.get("secret_count", 0)),
        "secret_count": secret_backend.get("secret_count", 0),
        "preserved_count": secret_backend.get("preserved_secret_count", 0),
        "backup_path": secret_backend.get("backup_path", ""),
        "plaintext_store": bool(secret_backend.get("plaintext_secret_store")),
    }
    rollback: dict[str, Any] = {}
    if not verified:
        rollback = _rollback_registry_v2_preview_apply(
            config_root=config_root,
            candidate=candidate,
            secret_backend=secret_backend,
            generated_snapshot=generated_snapshot,
            reason="verify_failed",
        )
    return {
        "ok": verified,
        "schema": "mms.setup_web.registry_v2_apply_result.v1",
        "status": "verified" if verified and runtime_ready else "verified_not_runtime_ready" if verified else "failed_verify",
        "runtime_ready": runtime_ready,
        "runtime_ready_reason": publish.get("runtime_ready_reason") or "",
        "runtime_blockers": {
            "missing_api_key_count": missing_api_keys,
            "missing_base_url_count": missing_base_urls,
            "provider_route_count": provider_route_count,
            "route_count": route_count,
        },
        "next_action": runtime_next_action,
        "summary": plan.get("summary") or {},
        "warnings": plan.get("warnings") or [],
        "paths": plan.get("paths") or {},
        "registry_v2_save_plan": v2_plan,
        "route_publish_guard": _sanitize_for_output(route_publish_guard),
        "candidate": _sanitize_for_output(candidate),
        "credential_backend": credential_backend,
        "publish": _sanitize_for_output(publish),
        "verify": _sanitize_for_output(verify),
        "rollback": rollback,
    }
