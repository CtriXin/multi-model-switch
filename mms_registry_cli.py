from __future__ import annotations

import argparse
import json
import shlex
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

import mms_registry
from mms_capability_resolver import resolve_model_capabilities
from mms_state_io import mms_config_root_status, resolve_mms_config_dir


ROOT = Path(__file__).resolve().parent
DEFAULT_REFERENCE_DIR = ROOT / "docs" / "reference" / "model-capability-calibration"
DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS = 24 * 14
DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS = 24 * 7
OPENROUTER_MODELS_API_URL = "https://openrouter.ai/api/v1/models"
LEGACY_IMPORT_REPORT_SCHEMA = "mms.legacy_import_report.v1"
LEGACY_IMPORT_SOURCE_KIND = "legacy_config_import"
LEGACY_IMPORT_SCHEMA = "mms.legacy_config_import.v1"
LEGACY_SECRET_BACKEND_SCHEMA = "mms.legacy_secret_backend.v1"
REGISTRY_V2_WEBUI_SECRET_BACKEND_SCHEMA = "mms.registry_v2_webui_secret_backend.v1"
CONFIG_ROOT_INIT_SCHEMA = "mms.config_root_init.v1"
REGISTRY_V2_SAVE_PLAN_SCHEMA = "mms.setup_web.registry_v2_save_plan.v1"
REGISTRY_V2_SAVE_CANDIDATE_SCHEMA = "mms.registry_v2_save_candidate.v1"
CONFIG_ROOT_LAYOUT_DIRS = (
    "registry",
    "secrets",
    "generated",
    "backups/db",
    "backups/generated",
    "backups/legacy-import",
    "backups/secret-backend",
    "imports",
    "logs",
    "snapshots",
)


def _sanitize_provider_env_id(provider_id: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in str(provider_id or "").upper())
    cleaned = cleaned.strip("_")
    return cleaned or "DEFAULT"


def _provider_env_name(provider_id: str, field: str) -> str:
    return f"MMS_PROVIDER_{_sanitize_provider_env_id(provider_id)}_{field}"


def _parse_shell_value(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        parts = shlex.split(f"v {text}")
    except ValueError:
        return text.strip("\"'")
    return parts[1] if len(parts) > 1 else ""


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, raw_value = line.partition("=")
        if not sep:
            continue
        values[key.strip()] = _parse_shell_value(raw_value)
    return values


def _load_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python < 3.11 fallback
        import tomli as tomllib  # type: ignore
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_json_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json_mapping(path: str | Path, *, label: str = "json") -> dict[str, Any]:
    json_path = Path(path).expanduser()
    if not json_path.exists():
        raise mms_registry.RegistryValidationError(f"{label} not found: {json_path}")
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise mms_registry.RegistryValidationError(f"{label} is invalid JSON: {json_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise mms_registry.RegistryValidationError(f"{label} must be a JSON object: {json_path}")
    return payload


def _secret_fingerprint(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return mms_registry.sha256_hex(text)[:12]


def _secret_ref(source_key: str) -> str:
    return f"legacy-env:{source_key}"


def _secret_ref_part(value: Any, default: str = "default") -> str:
    text = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    token = "_".join(part for part in "".join(chars).split("_") if part)
    return token or default


def _legacy_secret_ref(source: str, provider_id: str = "") -> str:
    token = str(source or "").split(":", 1)[-1].strip()
    if not token:
        token = "unknown"
    prefix = "legacy-env" if str(source or "").startswith("credentials.sh:") else "legacy-config"
    return f"{prefix}:{_secret_ref_part(provider_id)}:{_secret_ref_part(token, 'secret')}"


def _safe_value(field: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "key" in field.lower() or "token" in field.lower() or "secret" in field.lower():
        return f"sha256:{_secret_fingerprint(text)}"
    return text


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, tuple):
        raw = list(value)
    elif isinstance(value, str):
        raw = [item.strip() for item in value.replace("\n", ",").split(",")]
    else:
        raw = []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _credential_value(values: dict[str, str], key: str) -> str:
    return str(values.get(key) or "").strip()


def _provider_config_values(provider: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        "base_url": (str(provider.get("base_url") or "").strip().rstrip("/"), "config.toml:providers.base_url"),
        "openai_base_url": (
            str(provider.get("openai_base_url") or provider.get("default_openai_base_url") or "").strip().rstrip("/"),
            "config.toml:providers.openai_base_url",
        ),
        "anthropic_base_url": (
            str(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url") or "").strip().rstrip("/"),
            "config.toml:providers.anthropic_base_url",
        ),
        "api_key": (str(provider.get("api_key") or "").strip(), "config.toml:providers.api_key"),
        "openai_api_key": (str(provider.get("openai_api_key") or "").strip(), "config.toml:providers.openai_api_key"),
    }


def _provider_credential_values(provider_id: str, values: dict[str, str]) -> dict[str, tuple[str, str]]:
    keys = {
        "base_url": _provider_env_name(provider_id, "BASE_URL"),
        "openai_base_url": _provider_env_name(provider_id, "OPENAI_BASE_URL"),
        "anthropic_base_url": _provider_env_name(provider_id, "ANTHROPIC_BASE_URL"),
        "api_key": _provider_env_name(provider_id, "API_KEY"),
        "openai_api_key": _provider_env_name(provider_id, "OPENAI_API_KEY"),
    }
    result = {field: (_credential_value(values, key).rstrip("/") if "url" in field else _credential_value(values, key), f"credentials.sh:{key}") for field, key in keys.items()}
    if provider_id == "default":
        if not result["base_url"][0] and values.get("MMS_API_BASE_URL"):
            result["base_url"] = (str(values.get("MMS_API_BASE_URL") or "").strip().rstrip("/"), "credentials.sh:MMS_API_BASE_URL")
        if not result["api_key"][0] and values.get("MMS_API_KEY"):
            result["api_key"] = (str(values.get("MMS_API_KEY") or "").strip(), "credentials.sh:MMS_API_KEY")
    return result


def legacy_import_report(
    *,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a read-only legacy config/import report with conflict evidence."""
    root = Path(config_dir) if config_dir is not None else mms_registry.default_registry_db_path().parent
    root = root.expanduser()
    config_path = root / "config.toml"
    credentials_path = root / "credentials.sh"
    config = _load_toml_file(config_path)
    credentials = _load_env_file(credentials_path)
    raw_providers = config.get("providers") if isinstance(config.get("providers"), list) else []
    providers = [item for item in raw_providers if isinstance(item, dict)]
    if not providers:
        providers = [{"id": "default", "name": "Default Gateway"}]

    conflicts: list[dict[str, Any]] = []
    secret_refs: list[dict[str, Any]] = []
    provider_reports: list[dict[str, Any]] = []
    legacy_api = config.get("api") if isinstance(config.get("api"), dict) else {}

    for provider in providers:
        provider_id = str(provider.get("id") or "default").strip() or "default"
        config_values = _provider_config_values(provider)
        if provider_id == "default":
            if legacy_api.get("base_url") and not config_values["base_url"][0]:
                config_values["base_url"] = (str(legacy_api.get("base_url") or "").strip().rstrip("/"), "config.toml:api.base_url")
            if legacy_api.get("api_key") and not config_values["api_key"][0]:
                config_values["api_key"] = (str(legacy_api.get("api_key") or "").strip(), "config.toml:api.api_key")
        credential_values = _provider_credential_values(provider_id, credentials)
        provider_conflicts = []
        imported_fields = []
        seen_secret_refs: set[tuple[str, str, str]] = set()
        for field in ("base_url", "openai_base_url", "anthropic_base_url", "api_key", "openai_api_key"):
            config_value, config_source = config_values[field]
            credential_value, credential_source = credential_values[field]
            for secret_value, secret_source in ((config_value, config_source), (credential_value, credential_source)):
                if not secret_value or "key" not in field:
                    continue
                ref = _legacy_secret_ref(secret_source, provider_id)
                dedupe_key = (provider_id, field, ref)
                if dedupe_key in seen_secret_refs:
                    continue
                seen_secret_refs.add(dedupe_key)
                secret_refs.append(
                    {
                        "provider_id": provider_id,
                        "field": field,
                        "secret_ref": ref,
                        "fingerprint": _secret_fingerprint(secret_value),
                        "source": secret_source,
                    }
                )
            if config_value:
                imported_fields.append({"field": field, "source": config_source, "value": _safe_value(field, config_value)})
            if credential_value:
                imported_fields.append({"field": field, "source": credential_source, "value": _safe_value(field, credential_value)})
            if config_value and credential_value and config_value != credential_value:
                conflict = {
                    "provider_id": provider_id,
                    "field": field,
                    "config_source": config_source,
                    "credentials_source": credential_source,
                    "config_value": _safe_value(field, config_value),
                    "credentials_value": _safe_value(field, credential_value),
                    "winner": "credentials.sh",
                    "severity": "warning",
                }
                conflicts.append(conflict)
                provider_conflicts.append(conflict)
        provider_reports.append(
            {
                "provider_id": provider_id,
                "name": str(provider.get("name") or provider_id),
                "enabled": bool(provider.get("enabled", True)),
                "protocols": provider.get("protocols") if isinstance(provider.get("protocols"), list) else [],
                "role": str(provider.get("role") or "auto"),
                "priority": provider.get("priority"),
                "models_endpoint": str(provider.get("models_endpoint") or ""),
                "fallback_models": _as_string_list(provider.get("fallback_models")),
                "extra_models": _as_string_list(provider.get("extra_models")),
                "hidden_models": _as_string_list(provider.get("hidden_models")),
                "imported_fields": imported_fields,
                "conflict_count": len(provider_conflicts),
            }
        )

    file_status = {
        "config_toml": {"path": str(config_path), "exists": config_path.exists()},
        "credentials_sh": {"path": str(credentials_path), "exists": credentials_path.exists()},
        "model_policy": {"path": str(root / "model-policy.json"), "exists": (root / "model-policy.json").exists()},
        "provider_profiles": {"path": str(root / "provider-profiles.json"), "exists": (root / "provider-profiles.json").exists()},
        "lineup": {"path": str(root / "model-routes.lineup.json"), "exists": (root / "model-routes.lineup.json").exists()},
        "routes": {"path": str(root / "model-routes.json"), "exists": (root / "model-routes.json").exists()},
    }
    return {
        "schema": LEGACY_IMPORT_REPORT_SCHEMA,
        "config_root": str(root),
        "read_only": True,
        "files": file_status,
        "provider_count": len(provider_reports),
        "providers": provider_reports,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "secret_refs": secret_refs,
        "plaintext_secret_in_db": False,
        "next_action": "review_conflicts_before_import" if conflicts else "ready_for_preview_import",
    }


def _empty_legacy_import_candidate_summary() -> dict[str, Any]:
    return {
        "status": "not_imported",
        "source_snapshot_count": 0,
        "route_revision_count": 0,
        "route_group_count": 0,
        "provider_route_count": 0,
        "latest_snapshot": {},
        "latest_route_revision": {},
    }


def _read_only_legacy_import_candidate_summary(
    db: sqlite3.Connection,
    table_names: set[str],
) -> dict[str, Any]:
    summary = _empty_legacy_import_candidate_summary()
    if "source_snapshot" in table_names:
        summary["source_snapshot_count"] = int(
            db.execute(
                "SELECT count(*) FROM source_snapshot WHERE source_kind = ?",
                (LEGACY_IMPORT_SOURCE_KIND,),
            ).fetchone()[0]
        )
        row = db.execute(
            """
            SELECT snapshot_id, captured_at, source_path, model_count, content_hash
            FROM source_snapshot
            WHERE source_kind = ?
            ORDER BY snapshot_id DESC
            LIMIT 1
            """,
            (LEGACY_IMPORT_SOURCE_KIND,),
        ).fetchone()
        if row:
            summary["latest_snapshot"] = {
                "snapshot_id": int(row[0]),
                "captured_at": str(row[1] or ""),
                "source_path": str(row[2] or ""),
                "model_count": int(row[3] or 0),
                "content_hash": str(row[4] or ""),
            }

    legacy_route_revision_ids: list[str] = []
    if "registry_revision" in table_names:
        rows = db.execute(
            """
            SELECT revision_id, created_at, revision_hash, metadata_json, status
            FROM registry_revision
            WHERE revision_class = 'route' AND status IN ('candidate', 'approved')
            ORDER BY created_at DESC, revision_id DESC
            """
        ).fetchall()
        for row in rows:
            metadata: dict[str, Any] = {}
            try:
                parsed = json.loads(str(row[3] or "{}"))
                metadata = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                metadata = {}
            if metadata.get("source") != "legacy-import":
                continue
            revision_id = str(row[0] or "")
            if not revision_id:
                continue
            legacy_route_revision_ids.append(revision_id)
            if not summary["latest_route_revision"]:
                summary["latest_route_revision"] = {
                    "revision_id": revision_id,
                    "created_at": str(row[1] or ""),
                    "revision_hash": str(row[2] or ""),
                    "status": str(row[4] or ""),
                }

    summary["route_revision_count"] = len(legacy_route_revision_ids)
    if legacy_route_revision_ids:
        placeholders = ",".join("?" for _ in legacy_route_revision_ids)
        if "route_group" in table_names:
            summary["route_group_count"] = int(
                db.execute(
                    f"SELECT count(*) FROM route_group WHERE route_revision_id IN ({placeholders})",
                    legacy_route_revision_ids,
                ).fetchone()[0]
            )
        if "provider_route" in table_names:
            summary["provider_route_count"] = int(
                db.execute(
                    f"SELECT count(*) FROM provider_route WHERE route_revision_id IN ({placeholders})",
                    legacy_route_revision_ids,
                ).fetchone()[0]
            )
    if summary["source_snapshot_count"] or summary["route_revision_count"]:
        summary["status"] = "imported"
    return summary


def _read_only_registry_summary(db_path: Path) -> dict[str, Any]:
    legacy_candidates = _empty_legacy_import_candidate_summary()
    if not db_path.exists():
        return {
            "path": str(db_path),
            "exists": False,
            "status": "missing",
            "counts": {},
            "legacy_import_candidates": legacy_candidates,
        }
    counts: dict[str, int] = {}
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            table_names = {
                str(row[0])
                for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            for table in (
                "source_snapshot",
                "source_check",
                "candidate_change",
                "model_identity",
                "model_fact",
                "registry_revision",
                "route_group",
                "provider_route",
                "export_snapshot",
            ):
                if table in table_names:
                    counts[table] = int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            legacy_candidates = _read_only_legacy_import_candidate_summary(db, table_names)
        finally:
            db.close()
    except sqlite3.Error as exc:
        return {
            "path": str(db_path),
            "exists": True,
            "status": "error",
            "counts": counts,
            "legacy_import_candidates": legacy_candidates,
            "error": str(exc),
        }
    return {
        "path": str(db_path),
        "exists": True,
        "status": "ok",
        "counts": counts,
        "legacy_import_candidates": legacy_candidates,
    }


def _generated_bundle_summary(root: Path) -> dict[str, Any]:
    manifest_path = root / "generated" / "model-registry.latest-approved.json"
    if not manifest_path.exists():
        return {"manifest_path": str(manifest_path), "exists": False, "verified": False, "status": "missing"}
    try:
        verified = mms_registry.verify_latest_approved_bundle(config_dir=root, manifest_path=manifest_path)
    except Exception as exc:
        return {
            "manifest_path": str(manifest_path),
            "exists": True,
            "verified": False,
            "status": "invalid",
            "error": f"{type(exc).__name__}: {exc}",
        }
    manifest = verified.get("manifest") if isinstance(verified.get("manifest"), dict) else {}
    runtime_summary = _generated_router_runtime_summary(verified)
    return {
        "manifest_path": str(manifest_path),
        "exists": True,
        "verified": True,
        "status": "ok",
        "bundle_revision": manifest.get("bundle_revision") or "",
        "file_count": len(verified.get("verified_files") or {}),
        **runtime_summary,
    }


def _generated_router_runtime_summary(verified: dict[str, Any]) -> dict[str, Any]:
    files = verified.get("verified_files") if isinstance(verified.get("verified_files"), dict) else {}
    router = files.get("router") if isinstance(files.get("router"), dict) else {}
    path = str(router.get("path") or "").strip()
    if not path:
        return {"runtime_ready": None, "runtime_ready_status": "unknown"}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"runtime_ready": None, "runtime_ready_status": "unknown", "runtime_ready_error": f"{type(exc).__name__}: {exc}"}
    routes = payload.get("routes") if isinstance(payload.get("routes"), dict) else {}
    leaves = []
    for route in routes.values():
        if not isinstance(route, dict):
            continue
        primary = route.get("primary")
        if isinstance(primary, dict):
            leaves.append(primary)
        fallbacks = route.get("fallbacks") if isinstance(route.get("fallbacks"), list) else []
        leaves.extend(item for item in fallbacks if isinstance(item, dict))
    missing_api_key_count = sum(1 for item in leaves if not str(item.get("api_key") or "").strip())
    missing_base_url_count = sum(
        1
        for item in leaves
        if not str(item.get("anthropic_base_url") or "").strip()
        and not str(item.get("openai_base_url") or "").strip()
    )
    secret_ref_count = sum(1 for item in leaves if str(item.get("secret_ref") or "").strip())
    runtime_ready = payload.get("runtime_ready")
    derived_ready = bool(leaves) and missing_api_key_count == 0 and missing_base_url_count == 0
    if isinstance(runtime_ready, bool):
        ready_value: bool | None = runtime_ready and derived_ready
    elif leaves:
        ready_value = derived_ready
    else:
        ready_value = None
    status = "ready" if ready_value is True else "not_ready" if ready_value is False else "unknown"
    runtime_ready_reason = str(payload.get("runtime_ready_reason") or "")
    derived_reasons = []
    if missing_api_key_count:
        derived_reasons.append("missing plaintext secrets in preview secret backend")
    if missing_base_url_count:
        derived_reasons.append("missing route base URLs")
    if ready_value is False and not runtime_ready_reason:
        runtime_ready_reason = "; ".join(derived_reasons)
    return {
        "runtime_ready": ready_value,
        "runtime_ready_status": status,
        "runtime_ready_reason": runtime_ready_reason,
        "router_route_count": len(routes),
        "router_leaf_count": len(leaves),
        "router_missing_api_key_count": missing_api_key_count,
        "router_missing_base_url_count": missing_base_url_count,
        "router_secret_ref_count": secret_ref_count,
    }


def _preview_secret_backend_summary(root: Path) -> dict[str, Any]:
    paths = [root / "secrets" / "legacy-secrets.json", root / "secrets" / "webui-secrets.json"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            rows.append({"path": str(path), "exists": False, "status": "missing", "secret_count": 0})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"path": str(path), "exists": True, "status": "invalid", "secret_count": 0})
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        items = payload.get("secrets") if isinstance(payload.get("secrets"), list) else []
        rows.append(
            {
                "path": str(path),
                "exists": True,
                "status": "ok",
                "secret_count": len(items),
                "schema": payload.get("schema") or "",
            }
        )
    existing = [item for item in rows if item.get("exists")]
    secret_count = sum(int(item.get("secret_count") or 0) for item in rows)
    status = "invalid" if errors else "ok" if existing else "missing"
    return {
        "path": str(paths[0]),
        "paths": rows,
        "exists": bool(existing),
        "status": status,
        "secret_count": secret_count,
        "error": "; ".join(errors),
    }


def model_source_status(
    *,
    config_dir: str | Path | None = None,
    command_name: str = "mms",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    legacy = legacy_import_report(config_dir=root)
    db_path = mms_registry.default_registry_db_path(config_dir=root)
    registry_db = _read_only_registry_summary(db_path)
    return {
        "schema": "mms.model_source_status.v1",
        "root": mms_config_root_status(command=command_name.split()[0] if command_name else "mms", config_dir=root),
        "registry_db": registry_db,
        "legacy_import": {
            "read_only": True,
            "provider_count": legacy.get("provider_count", 0),
            "conflict_count": legacy.get("conflict_count", 0),
            "candidates": registry_db.get("legacy_import_candidates", _empty_legacy_import_candidate_summary()),
            "next_action": legacy.get("next_action", ""),
            "files": legacy.get("files", {}),
        },
        "generated_bundle": _generated_bundle_summary(root),
        "read_only": True,
    }


def _config_root_from_config_path(config_path: str | Path | None = None) -> Path | None:
    if not str(config_path or "").strip():
        return None
    path = Path(str(config_path)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.parent


def registry_v2_save_plan(
    *,
    config_dir: str | Path | None = None,
    config_path: str | Path | None = None,
    command_name: str = "mms config save-plan",
    plan_summary: dict[str, Any] | None = None,
    credential_updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Describe the future DB-truth save path without writing anything."""
    root = Path(config_dir).expanduser() if config_dir is not None else _config_root_from_config_path(config_path)
    if root is None:
        root = Path(resolve_mms_config_dir()).expanduser()
    root_status = mms_config_root_status(
        command=command_name.split()[0] if command_name else "mms",
        config_dir=root,
    )
    db_path = mms_registry.default_registry_db_path(config_dir=root)
    summary = plan_summary if isinstance(plan_summary, dict) else {}
    credentials = credential_updates if isinstance(credential_updates, list) else []
    mode = str(root_status.get("mode") or "")
    has_changes = any(
        bool(summary.get(key))
        for key in ("will_write_config", "will_write_policy", "will_write_credentials")
    )
    backup_dir = root / "backups" / "db"
    blocked_reasons: list[str] = []
    if mode != "preview":
        blocked_reasons.append("stable_root_human_only")
    if not has_changes:
        blocked_reasons.append("no_draft_changes")
    return {
        "schema": REGISTRY_V2_SAVE_PLAN_SCHEMA,
        "read_only": True,
        "execution_state": "plan_only",
        "actual_save_enabled": False,
        "root": root_status,
        "db": {
            "path": str(db_path),
            "exists": db_path.exists(),
            "backup_dir": str(backup_dir),
            "would_backup_existing_db": bool(db_path.exists() and has_changes and mode == "preview"),
        },
        "would_write": {
            "db_candidate_revision": bool(has_changes and mode == "preview"),
            "secret_backend": bool(credentials and mode == "preview"),
            "generated_latest_approved_bundle": bool(has_changes and mode == "preview"),
            "legacy_compat_files": {
                "config_toml": bool(summary.get("will_write_config")),
                "model_policy_json": bool(summary.get("will_write_policy")),
                "credentials_sh": bool(summary.get("will_write_credentials")),
            },
        },
        "ordered_steps": [
            "backup preview registry DB",
            "write DB candidate revisions for route/policy/profile facts",
            "write secret backend only for explicit credential updates",
            "publish generated/latest-approved bundle",
            "verify manifest hashes",
            "rollback to backup on failure",
        ],
        "blocked_reasons": blocked_reasons,
        "next_implementation_step": "wire WebUI/TUI/mms config save to DB writer after rollback tests pass",
    }


def preview_doctor(
    *,
    config_dir: str | Path | None = None,
    command_name: str = "mmf preview doctor",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    source = model_source_status(config_dir=root, command_name=command_name)
    root_status = source.get("root") if isinstance(source.get("root"), dict) else {}
    registry_db = source.get("registry_db") if isinstance(source.get("registry_db"), dict) else {}
    legacy = source.get("legacy_import") if isinstance(source.get("legacy_import"), dict) else {}
    candidates = legacy.get("candidates") if isinstance(legacy.get("candidates"), dict) else {}
    bundle = source.get("generated_bundle") if isinstance(source.get("generated_bundle"), dict) else {}
    secrets = _preview_secret_backend_summary(root)

    checks = [
        {
            "id": "preview_root",
            "ok": root_status.get("mode") == "preview",
            "detail": root_status.get("mode") or "unknown",
        },
        {
            "id": "registry_db",
            "ok": registry_db.get("status") == "ok",
            "detail": registry_db.get("status") or "missing",
        },
        {
            "id": "legacy_candidates",
            "ok": int(candidates.get("provider_route_count") or 0) > 0,
            "detail": f"provider_routes={int(candidates.get('provider_route_count') or 0)}",
        },
        {
            "id": "latest_bundle",
            "ok": bool(bundle.get("verified")),
            "detail": bundle.get("status") or "missing",
        },
        {
            "id": "runtime_ready",
            "ok": bundle.get("runtime_ready") is True,
            "detail": bundle.get("runtime_ready_status") or "unknown",
        },
    ]

    next_actions: list[dict[str, str]] = []
    if root_status.get("mode") != "preview":
        overall = "wrong_root"
        next_actions.append({"label": "Use mmf preview root", "command": "./mmf config root --json"})
    elif registry_db.get("status") != "ok":
        overall = "needs_init"
        next_actions.append({"label": "Initialize preview root", "command": "./mmf preview init --json"})
    elif int(candidates.get("provider_route_count") or 0) <= 0:
        overall = "needs_import"
        next_actions.append({"label": "Import legacy config into preview DB", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --json"})
    elif not bundle.get("verified"):
        overall = "needs_publish"
        next_actions.append({"label": "Publish and verify preview bundle", "command": "./mmf preview publish --json && ./mmf preview verify --json"})
    elif bundle.get("runtime_ready") is not True:
        overall = "verified_not_runtime_ready"
        if int(bundle.get("router_missing_base_url_count") or 0) > 0:
            next_actions.append({"label": "Rebuild preview routes from legacy source", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --json && ./mmf preview publish --json && ./mmf preview verify --json"})
        elif int(bundle.get("router_missing_api_key_count") or 0) > 0:
            next_actions.append({"label": "Optional: import keys into preview secret backend", "command": "./mmf preview import-legacy --from ~/.config/mms --apply --include-secrets --json && ./mmf preview publish --json"})
        else:
            next_actions.append({"label": "Inspect preview bundle readiness", "command": "./mmf config doctor --json"})
    else:
        overall = "ready"
        next_actions.append({"label": "Optional: run read-only watchdog check", "command": "scripts/mms_health_watchdog.py --config-dir \"$MMS_CONFIG_ROOT\" --require-bundle --dry-run --print-json"})

    return {
        "schema": "mms.preview_doctor.v1",
        "status": overall,
        "ready": overall == "ready",
        "result": "READY" if overall == "ready" else "VERIFIED_NOT_RUNTIME_READY" if overall == "verified_not_runtime_ready" else "NOT_READY",
        "config_root": str(root),
        "checks": checks,
        "counts": {
            "legacy_provider_count": legacy.get("provider_count", 0),
            "legacy_conflict_count": legacy.get("conflict_count", 0),
            "candidate_provider_routes": candidates.get("provider_route_count", 0),
            "bundle_files": bundle.get("file_count", 0),
            "bundle_routes": bundle.get("router_route_count", 0),
            "missing_api_keys": bundle.get("router_missing_api_key_count", 0),
            "missing_base_urls": bundle.get("router_missing_base_url_count", 0),
            "preview_secret_count": secrets.get("secret_count", 0),
        },
        "bundle": {
            "verified": bool(bundle.get("verified")),
            "runtime_ready": bundle.get("runtime_ready"),
            "runtime_ready_status": bundle.get("runtime_ready_status") or "unknown",
            "manifest_path": bundle.get("manifest_path") or "",
        },
        "secrets": {
            "status": secrets.get("status"),
            "path": secrets.get("path"),
            "secret_count": secrets.get("secret_count", 0),
        },
        "next_actions": next_actions,
        "read_only": True,
    }


def preview_prepare(
    *,
    config_dir: str | Path | None = None,
    source_config_dir: str | Path | None = None,
    include_secrets: bool = False,
    command_name: str = "mmf preview prepare",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    source_root = Path(source_config_dir).expanduser() if source_config_dir is not None else root
    init_summary = init_config_root(config_dir=root, create_db=True, command_name=command_name)
    pre_import_backup = backup_registry_db(config_dir=root, reason="preview-prepare") if not bool(init_summary.get("db_created")) else {"skipped": True, "reason": "new_db"}
    import_summary = import_legacy_config(
        config_dir=root,
        source_config_dir=source_root,
        apply=True,
        include_secrets=bool(include_secrets),
        command_name=command_name,
    )
    publish_summary = publish_preview_bundle(config_dir=root)
    verify_summary = verify_approved_bundle(config_dir=root)
    doctor_summary = preview_doctor(config_dir=root, command_name=command_name)
    route_candidates = import_summary.get("route_candidates") if isinstance(import_summary.get("route_candidates"), dict) else {}
    secret_backend = import_summary.get("secret_backend") if isinstance(import_summary.get("secret_backend"), dict) else {}
    return {
        "schema": "mms.preview_prepare.v1",
        "ok": bool(verify_summary.get("verified")) and doctor_summary.get("status") in {"ready", "verified_not_runtime_ready"},
        "ready": doctor_summary.get("status") == "ready",
        "result": "READY" if doctor_summary.get("status") == "ready" else "VERIFIED_NOT_RUNTIME_READY" if doctor_summary.get("status") == "verified_not_runtime_ready" else "NOT_READY",
        "config_root": str(root),
        "source_config_root": str(source_root),
        "include_secrets": bool(include_secrets),
        "stages": {
            "init": {
                "db_initialized": bool(init_summary.get("db_initialized")),
                "db_created": bool(init_summary.get("db_created")),
                "layout_dirs": len(init_summary.get("layout_dirs") or []),
            },
            "backup": {
                "skipped": bool(pre_import_backup.get("skipped")),
                "reason": str(pre_import_backup.get("reason") or ""),
                "backup_path": str(pre_import_backup.get("backup_path") or ""),
            },
            "import": {
                "provider_count": import_summary.get("provider_count", 0),
                "model_count": import_summary.get("model_count", 0),
                "conflict_count": import_summary.get("conflict_count", 0),
                "provider_route_count": route_candidates.get("provider_route_count", 0),
                "secret_backend_count": secret_backend.get("secret_count", 0),
            },
            "publish": {
                "route_count": publish_summary.get("route_count", 0),
                "provider_route_count": publish_summary.get("provider_route_count", 0),
                "runtime_ready": publish_summary.get("runtime_ready"),
                "missing_api_key_count": publish_summary.get("missing_api_key_count", 0),
                "missing_base_url_count": publish_summary.get("missing_base_url_count", 0),
            },
            "verify": {
                "verified": bool(verify_summary.get("verified")),
                "file_count": verify_summary.get("file_count", 0),
            },
        },
        "doctor": {
            "status": doctor_summary.get("status"),
            "next_actions": doctor_summary.get("next_actions") or [],
        },
        "writes": {
            "target_preview_root": True,
            "source_root": False,
            "secret_backend": bool(include_secrets),
        },
    }


def init_config_root(
    *,
    config_dir: str | Path | None = None,
    create_db: bool = True,
    allow_stable: bool = False,
    command_name: str = "mms registry",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    command = command_name.split()[0] if command_name else "mms"
    root_status = mms_config_root_status(command=command, config_dir=root)
    if root_status.get("mode") != "preview" and not allow_stable:
        raise mms_registry.RegistryValidationError(
            "refusing to initialize stable config root without --allow-stable"
        )

    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass

    dirs: list[dict[str, Any]] = []
    for rel in CONFIG_ROOT_LAYOUT_DIRS:
        path = root / rel
        path.mkdir(parents=True, exist_ok=True)
        mode = 0o700 if rel == "secrets" else 0o755
        try:
            path.chmod(mode)
        except OSError:
            pass
        dirs.append({"path": str(path), "relative_path": rel, "mode": oct(mode)})

    db_path = mms_registry.default_registry_db_path(config_dir=root)
    db_created = False
    if create_db:
        existed_before = db_path.exists()
        db = mms_registry.open_registry(db_path)
        try:
            db.execute("PRAGMA user_version").fetchone()
        finally:
            db.close()
        db_created = not existed_before and db_path.exists()

    manifest_root = {
        key: root_status.get(key)
        for key in ("command", "mode", "root_source", "config_root", "stable_root", "preview_root", "explicit_root")
    }
    manifest = {
        "schema": CONFIG_ROOT_INIT_SCHEMA,
        "created_at": mms_registry.utc_now(),
        "command": command,
        "root": manifest_root,
        "layout_dirs": dirs,
        "db_path": str(db_path),
        "db_created": db_created,
        "db_initialized": bool(create_db),
        "read_only": False,
        "stable_init_allowed": bool(allow_stable),
    }
    mms_registry.validate_non_secret_payload(manifest, context="config_root_init")
    manifest_path = root / "root-manifest.json"
    mms_registry.write_json_atomic(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _slug_id(value: Any, default: str = "item") -> str:
    text = str(value or "").strip().lower()
    chars = [ch if ch.isalnum() else "_" for ch in text]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or default


def _timestamp_slug(value: str | None = None) -> str:
    text = "".join(ch for ch in str(value or mms_registry.utc_now()) if ch.isdigit())
    return text[:14] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _import_field_map(provider: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in provider.get("imported_fields") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        value = str(item.get("value") or "").strip()
        if field and value and not value.startswith("sha256:"):
            values[field] = value
    if not values.get("openai_base_url") and values.get("base_url"):
        values["openai_base_url"] = values["base_url"]
    return values


def _provider_secret_ref(report: dict[str, Any], provider_id: str) -> str:
    for item in report.get("secret_refs") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("provider_id") or "") != provider_id:
            continue
        if str(item.get("field") or "") in {"api_key", "openai_api_key"}:
            return str(item.get("secret_ref") or "")
    return ""


def _provider_route_models(provider: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    def add(model_id: Any) -> None:
        text = str(model_id or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        result.append(text)

    for key in ("fallback_models", "extra_models"):
        for model in _as_string_list(provider.get(key)):
            add(model)
    hidden = set(_as_string_list(provider.get("hidden_models")))
    models = provider.get("models") if isinstance(provider.get("models"), list) else []
    for item in models:
        if isinstance(item, Mapping):
            model_id = str(item.get("id") or item.get("model") or "").strip()
            if item.get("visible") is False or model_id in hidden:
                continue
            add(model_id)
        else:
            model_id = str(item or "").strip()
            if model_id and model_id not in hidden:
                add(model_id)
    return result


def _provider_route_secret_ref(provider: Mapping[str, Any], credential_provider_ids: set[str]) -> tuple[str, str]:
    provider_id = str(provider.get("id") or provider.get("provider_id") or "default").strip() or "default"
    explicit_ref = str(provider.get("secret_ref") or "").strip()
    if explicit_ref:
        return explicit_ref, "provider.secret_ref"
    if provider_id in credential_provider_ids:
        return f"pending-webui:{_secret_ref_part(provider_id)}:api_key", "credential_update"
    for field in ("api_key", "openai_api_key", "anthropic_api_key"):
        value = str(provider.get(field) or "").strip()
        if value:
            return f"legacy-config:{_secret_ref_part(provider_id)}:{field}", f"config.{field}"
    return "", ""


def _registry_v2_profile_payload(config_payload: Mapping[str, Any]) -> dict[str, Any]:
    providers = [item for item in (config_payload.get("providers") or []) if isinstance(item, Mapping)]
    profiles: dict[str, dict[str, Any]] = {}
    for provider in providers:
        provider_id = str(provider.get("id") or provider.get("provider_id") or "").strip()
        if not provider_id:
            continue
        profiles[provider_id] = {
            "name": str(provider.get("name") or provider_id),
            "role": str(provider.get("role") or "auto"),
            "priority": int(provider.get("priority") or 0),
            "models_endpoint": str(provider.get("models_endpoint") or ""),
            "protocols": _as_string_list(provider.get("protocols")),
            "supported_clis": _as_string_list(provider.get("supported_clis")),
            "enabled": provider.get("enabled", True) is not False,
        }
    payload = {
        "schema": "mms.registry_v2.profile_candidate.v1",
        "source": "registry-v2-save-candidate",
        "profiles": profiles,
    }
    mms_registry.validate_non_secret_payload(payload, context="registry_v2_profile_candidate")
    return payload


def _registry_v2_policy_payload(policy_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(policy_payload or {})
    if not payload:
        payload = {
            "version": 1,
            "description": "Registry v2 candidate policy placeholder.",
            "models": {},
            "projects": {},
        }
    payload.setdefault("source", "registry-v2-save-candidate")
    mms_registry.validate_non_secret_payload(payload, context="registry_v2_policy_candidate")
    return payload


def _registry_v2_candidate_payload(
    config_payload: Mapping[str, Any],
    *,
    policy_payload: Mapping[str, Any] | None = None,
    credential_updates: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    providers = [item for item in (config_payload.get("providers") or []) if isinstance(item, Mapping)]
    credential_provider_ids = {
        str(item.get("provider_id") or item.get("id") or "").strip()
        for item in (credential_updates or [])
        if isinstance(item, Mapping)
    }
    route_entries: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for provider in providers:
        provider_id = str(provider.get("id") or provider.get("provider_id") or "").strip()
        if not provider_id:
            skipped.append({"reason": "missing_provider_id"})
            continue
        if provider.get("enabled", True) is False:
            skipped.append({"provider_id": provider_id, "reason": "provider_disabled"})
            continue
        models = _provider_route_models(provider)
        if not models:
            skipped.append({"provider_id": provider_id, "reason": "no_configured_models"})
            continue
        openai_base = str(
            provider.get("openai_base_url")
            or provider.get("default_openai_base_url")
            or provider.get("base_url")
            or ""
        ).strip().rstrip("/")
        anthropic_base = str(provider.get("anthropic_base_url") or provider.get("default_anthropic_base_url") or "").strip().rstrip("/")
        secret_ref, secret_source = _provider_route_secret_ref(provider, credential_provider_ids)
        key_fingerprint = ""
        for field in ("api_key", "openai_api_key", "anthropic_api_key"):
            if provider.get(field):
                key_fingerprint = _secret_fingerprint(provider.get(field))
                break
        for model in models:
            route_entries.append(
                {
                    "provider_id": provider_id,
                    "model": model,
                    "priority": int(provider.get("priority") or 0),
                    "anthropic_base_url": anthropic_base,
                    "openai_base_url": openai_base,
                    "secret_ref": secret_ref,
                    "metadata": {
                        "source": "registry-v2-save-candidate",
                        "name": str(provider.get("name") or provider_id),
                        "role": str(provider.get("role") or "auto"),
                        "models_endpoint": str(provider.get("models_endpoint") or ""),
                        "protocols": _as_string_list(provider.get("protocols")),
                        "supported_clis": _as_string_list(provider.get("supported_clis")),
                        "secret_source": secret_source,
                        "secret_fingerprint": key_fingerprint,
                    },
                }
            )
    payload = {
        "schema": REGISTRY_V2_SAVE_CANDIDATE_SCHEMA,
        "source": "registry-v2-save-candidate",
        "captured_at": mms_registry.utc_now(),
        "route_entries": route_entries,
        "policy": _registry_v2_policy_payload(policy_payload),
        "profile": _registry_v2_profile_payload(config_payload),
        "skipped": skipped,
    }
    mms_registry.validate_non_secret_payload(payload, context="registry_v2_save_candidate")
    return payload


def _insert_registry_v2_candidate_revisions(db: sqlite3.Connection, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
    route_entries = [item for item in (payload.get("route_entries") or []) if isinstance(item, dict)]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    source = "registry-v2-save-candidate"
    result: dict[str, Any] = {
        "route": {"revision_id": "", "route_group_count": 0, "provider_route_count": 0},
        "policy": {"revision_id": "", "model_count": 0},
        "profile": {"revision_id": "", "provider_count": 0},
    }
    if route_entries:
        digest = mms_registry.sha256_hex(json.dumps(route_entries, ensure_ascii=False, sort_keys=True))
        route_revision_id = f"registry_v2_route_{stamp}_{digest[:12]}"
        mms_registry.create_revision(
            db,
            route_revision_id,
            "route",
            status="candidate",
            revision_hash=digest,
            metadata={"source": source, "route_count": len(route_entries)},
        )
        groups: set[str] = set()
        for idx, entry in enumerate(route_entries, start=1):
            model = str(entry.get("model") or "").strip()
            provider_id = str(entry.get("provider_id") or "").strip()
            group_id = f"{route_revision_id}_{_slug_id(model, 'model')}"
            if group_id not in groups:
                mms_registry.insert_route_group(
                    db,
                    group_id,
                    route_revision_id,
                    logical_model=model,
                    display_name=model,
                    metadata={"source": source},
                )
                groups.add(group_id)
            mms_registry.insert_provider_route(
                db,
                f"{group_id}_{_slug_id(provider_id, 'provider')}_{idx}",
                group_id,
                route_revision_id,
                provider_id=provider_id,
                wire_model_id=model,
                priority=int(entry.get("priority") or 0),
                anthropic_base_url=str(entry.get("anthropic_base_url") or ""),
                openai_base_url=str(entry.get("openai_base_url") or ""),
                secret_ref=str(entry.get("secret_ref") or ""),
                validation_state="candidate",
                metadata=entry.get("metadata") or {},
            )
        result["route"] = {
            "revision_id": route_revision_id,
            "route_group_count": len(groups),
            "provider_route_count": len(route_entries),
        }

    policy_payload = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    policy_digest = mms_registry.sha256_hex(json.dumps(policy_payload, ensure_ascii=False, sort_keys=True))
    policy_revision_id = f"registry_v2_policy_{stamp}_{policy_digest[:12]}"
    policy_models = policy_payload.get("models") if isinstance(policy_payload.get("models"), dict) else {}
    mms_registry.create_revision(
        db,
        policy_revision_id,
        "policy",
        status="candidate",
        revision_hash=policy_digest,
        metadata={"source": source, "payload": policy_payload, "model_count": len(policy_models)},
    )
    result["policy"] = {"revision_id": policy_revision_id, "model_count": len(policy_models)}

    profile_payload = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    profile_digest = mms_registry.sha256_hex(json.dumps(profile_payload, ensure_ascii=False, sort_keys=True))
    profile_revision_id = f"registry_v2_profile_{stamp}_{profile_digest[:12]}"
    profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), dict) else {}
    mms_registry.create_revision(
        db,
        profile_revision_id,
        "profile",
        status="candidate",
        revision_hash=profile_digest,
        metadata={"source": source, "payload": profile_payload, "provider_count": len(profiles)},
    )
    result["profile"] = {"revision_id": profile_revision_id, "provider_count": len(profiles)}

    with db:
        db.execute(
            """
            INSERT INTO audit_log(event_type, actor, target_type, target_id, details_json)
            VALUES ('registry_v2_save.candidate', ?, 'registry_revision', ?, ?)
            """,
            (
                actor,
                result["route"].get("revision_id") or policy_revision_id,
                json.dumps(result, ensure_ascii=False, sort_keys=True),
            ),
        )
    return result


def _legacy_artifact_summary(root: Path) -> dict[str, Any]:
    policy = _load_json_mapping(root / "model-policy.json")
    profiles = _load_json_mapping(root / "provider-profiles.json")
    lineup = _load_json_mapping(root / "model-routes.lineup.json")
    routes = _load_json_mapping(root / "model-routes.json")
    policy_models = policy.get("models") if isinstance(policy.get("models"), dict) else {}
    profile_items = profiles.get("profiles") if isinstance(profiles.get("profiles"), dict) else {}
    lineup_routes = lineup.get("routes") if isinstance(lineup.get("routes"), dict) else {}
    route_items = routes.get("routes") if isinstance(routes.get("routes"), dict) else {}
    return {
        "model_policy": {"model_count": len(policy_models), "project_count": len(policy.get("projects") or {}) if isinstance(policy.get("projects"), dict) else 0},
        "provider_profiles": {"profile_count": len(profile_items)},
        "lineup": {"route_count": len(lineup_routes), "model_keys": sorted(str(key) for key in lineup_routes.keys())[:200]},
        "routes": {"route_count": len(route_items), "model_keys": sorted(str(key) for key in route_items.keys())[:200]},
    }


def _legacy_import_models(report: dict[str, Any], artifact_summary: dict[str, Any]) -> list[dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}

    def add_model(model_id: str, *, provider_id: str = "", source: str = "legacy_config", protocols: list[str] | None = None, hidden: bool = False) -> None:
        model = str(model_id or "").strip()
        if not model:
            return
        entry = models.setdefault(
            model,
            {
                "alias": model,
                "canonical_model_id": model,
                "routed_model_id": model,
                "provider_id": provider_id,
                "vendor": provider_id,
                "family": "",
                "confidence": "legacy_candidate",
                "evidence": {"sources": []},
            },
        )
        if provider_id and not entry.get("provider_id"):
            entry["provider_id"] = provider_id
            entry["vendor"] = provider_id
        if protocols and "expected_protocol" not in entry:
            entry["expected_protocol"] = protocols[0]
        entry["evidence"]["sources"].append(source)
        if hidden:
            entry["evidence"]["hidden"] = True

    for provider in report.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("provider_id") or "").strip()
        protocols = _as_string_list(provider.get("protocols"))
        hidden = set(_as_string_list(provider.get("hidden_models")))
        for model in _as_string_list(provider.get("fallback_models")):
            add_model(model, provider_id=provider_id, source="config.toml:providers.fallback_models", protocols=protocols, hidden=model in hidden)
        for model in _as_string_list(provider.get("extra_models")):
            add_model(model, provider_id=provider_id, source="config.toml:providers.extra_models", protocols=protocols, hidden=model in hidden)
        for model in hidden:
            add_model(model, provider_id=provider_id, source="config.toml:providers.hidden_models", protocols=protocols, hidden=True)

    for source_name in ("lineup", "routes"):
        source = artifact_summary.get(source_name) if isinstance(artifact_summary.get(source_name), dict) else {}
        for model in source.get("model_keys") or []:
            add_model(str(model), source=f"{source_name}:model_key")

    return sorted(models.values(), key=lambda item: str(item.get("alias") or "").lower())


def _db_safe_legacy_report(report: dict[str, Any]) -> dict[str, Any]:
    files = report.get("files") if isinstance(report.get("files"), dict) else {}
    file_rows = []
    for name, item in files.items():
        item = item if isinstance(item, dict) else {}
        file_rows.append(
            {
                "kind": str(name or ""),
                "path": str(item.get("path") or ""),
                "exists": bool(item.get("exists")),
            }
        )
    conflicts = []
    for item in report.get("conflicts") or []:
        if not isinstance(item, dict):
            continue
        conflicts.append(
            {
                "provider_id": item.get("provider_id") or "",
                "field": item.get("field") or "",
                "config_source": item.get("config_source") or "",
                "env_source": item.get("credentials_source") or "",
                "config_fingerprint_or_value": item.get("config_value") or "",
                "env_fingerprint_or_value": item.get("credentials_value") or "",
                "winner": item.get("winner") or "",
                "severity": item.get("severity") or "",
            }
        )
    providers = []
    for item in report.get("providers") or []:
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "provider_id": item.get("provider_id") or "",
                "name": item.get("name") or "",
                "enabled": bool(item.get("enabled", True)),
                "protocols": _as_string_list(item.get("protocols")),
                "role": item.get("role") or "auto",
                "priority": item.get("priority"),
                "models_endpoint": item.get("models_endpoint") or "",
                "fallback_models": _as_string_list(item.get("fallback_models")),
                "extra_models": _as_string_list(item.get("extra_models")),
                "hidden_models": _as_string_list(item.get("hidden_models")),
                "conflict_count": item.get("conflict_count", 0),
            }
        )
    return {
        "schema": report.get("schema") or LEGACY_IMPORT_REPORT_SCHEMA,
        "config_root": report.get("config_root") or "",
        "read_only": True,
        "files": file_rows,
        "providers": providers,
        "provider_count": report.get("provider_count", 0),
        "conflict_count": report.get("conflict_count", 0),
        "conflicts": conflicts,
        "secret_refs": report.get("secret_refs") or [],
        "contains_plaintext_sensitive_value": False,
        "next_action": report.get("next_action") or "",
    }


def _legacy_import_payload(report: dict[str, Any]) -> dict[str, Any]:
    root = Path(report.get("config_root") or "").expanduser()
    artifact_summary = _legacy_artifact_summary(root)
    payload = {
        "schema": LEGACY_IMPORT_SCHEMA,
        "config_root": str(root),
        "captured_at": mms_registry.utc_now(),
        "report": _db_safe_legacy_report(report),
        "legacy_artifacts": artifact_summary,
        "models": _legacy_import_models(report, artifact_summary),
    }
    mms_registry.validate_non_secret_payload(payload, context="legacy_import_payload")
    return payload


def _legacy_route_artifact_url_map(root: Path) -> dict[tuple[str, str], dict[str, str]]:
    routes = _load_json_mapping(root / "model-routes.json")
    result: dict[tuple[str, str], dict[str, str]] = {}
    for logical_model, entry in (routes.get("routes") if isinstance(routes.get("routes"), dict) else {}).items():
        if not isinstance(entry, dict):
            continue
        leaves: list[dict[str, Any]] = []
        primary = entry.get("primary")
        if isinstance(primary, dict):
            leaves.append(primary)
        fallbacks = entry.get("fallbacks") if isinstance(entry.get("fallbacks"), list) else []
        leaves.extend(item for item in fallbacks if isinstance(item, dict))
        for leaf in leaves:
            provider_id = str(leaf.get("provider_id") or "").strip()
            if not provider_id:
                continue
            urls = {
                "anthropic_base_url": str(leaf.get("anthropic_base_url") or "").strip().rstrip("/"),
                "openai_base_url": str(leaf.get("openai_base_url") or "").strip().rstrip("/"),
            }
            if not urls["anthropic_base_url"] and not urls["openai_base_url"]:
                continue
            for model_key in {str(logical_model or "").strip(), str(leaf.get("model_id") or "").strip()}:
                if model_key:
                    result.setdefault((provider_id, model_key), urls)
    return result


def _insert_legacy_route_candidates(db: sqlite3.Connection, report: dict[str, Any], *, actor: str) -> dict[str, Any]:
    route_entries: list[dict[str, Any]] = []
    root = Path(report.get("config_root") or "").expanduser()
    route_artifact_urls = _legacy_route_artifact_url_map(root)
    for provider in report.get("providers") or []:
        if not isinstance(provider, dict):
            continue
        provider_id = str(provider.get("provider_id") or "").strip()
        if not provider_id:
            continue
        if provider.get("enabled") is False:
            continue
        fields = _import_field_map(provider)
        models = _as_string_list(provider.get("fallback_models")) + _as_string_list(provider.get("extra_models"))
        seen_models: set[str] = set()
        for model in models:
            if model in seen_models:
                continue
            seen_models.add(model)
            artifact_urls = route_artifact_urls.get((provider_id, model), {})
            anthropic_base_url = fields.get("anthropic_base_url", "") or artifact_urls.get("anthropic_base_url", "")
            openai_base_url = fields.get("openai_base_url", "") or artifact_urls.get("openai_base_url", "")
            route_url_source = "legacy-route-artifact" if artifact_urls and (
                artifact_urls.get("anthropic_base_url") or artifact_urls.get("openai_base_url")
            ) else "legacy-provider-fields"
            route_entries.append(
                {
                    "provider_id": provider_id,
                    "model": model,
                    "priority": int(provider.get("priority") or 0),
                    "anthropic_base_url": anthropic_base_url,
                    "openai_base_url": openai_base_url,
                    "secret_ref": _provider_secret_ref(report, provider_id),
                    "metadata": {
                        "role": provider.get("role") or "auto",
                        "models_endpoint": provider.get("models_endpoint") or "",
                        "protocols": _as_string_list(provider.get("protocols")),
                        "source": "legacy-import",
                        "route_url_source": route_url_source,
                    },
                }
            )
    if not route_entries:
        return {"route_revision_id": "", "route_group_count": 0, "provider_route_count": 0}

    digest = mms_registry.sha256_hex(json.dumps(route_entries, ensure_ascii=False, sort_keys=True))
    revision_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    route_revision_id = f"legacy_route_{revision_stamp}_{digest[:12]}"
    mms_registry.create_revision(
        db,
        route_revision_id,
        "route",
        status="candidate",
        revision_hash=digest,
        metadata={"source": "legacy-import", "route_count": len(route_entries)},
    )
    groups: set[str] = set()
    for idx, entry in enumerate(route_entries, start=1):
        model = str(entry["model"])
        group_id = f"{route_revision_id}_{_slug_id(model, 'model')}"
        if group_id not in groups:
            mms_registry.insert_route_group(
                db,
                group_id,
                route_revision_id,
                logical_model=model,
                display_name=model,
                metadata={"source": "legacy-import"},
            )
            groups.add(group_id)
        mms_registry.insert_provider_route(
            db,
            f"{group_id}_{_slug_id(entry['provider_id'], 'provider')}_{idx}",
            group_id,
            route_revision_id,
            provider_id=str(entry["provider_id"]),
            wire_model_id=model,
            priority=int(entry["priority"] or 0),
            anthropic_base_url=str(entry["anthropic_base_url"] or ""),
            openai_base_url=str(entry["openai_base_url"] or ""),
            secret_ref=str(entry["secret_ref"] or ""),
            validation_state="candidate",
            metadata=entry.get("metadata") or {},
        )
    db.execute(
        """
        INSERT INTO audit_log(event_type, actor, target_type, target_id, details_json)
        VALUES ('legacy_import.route_candidates', ?, 'registry_revision', ?, ?)
        """,
        (actor, route_revision_id, json.dumps({"provider_route_count": len(route_entries)}, ensure_ascii=False, sort_keys=True)),
    )
    return {
        "route_revision_id": route_revision_id,
        "route_group_count": len(groups),
        "provider_route_count": len(route_entries),
    }


def _legacy_secret_entries(source_root: Path) -> list[dict[str, Any]]:
    config = _load_toml_file(source_root / "config.toml")
    credentials = _load_env_file(source_root / "credentials.sh")
    raw_providers = config.get("providers") if isinstance(config.get("providers"), list) else []
    providers = [item for item in raw_providers if isinstance(item, dict)]
    if not providers:
        providers = [{"id": "default", "name": "Default Gateway"}]
    legacy_api = config.get("api") if isinstance(config.get("api"), dict) else {}
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for provider in providers:
        provider_id = str(provider.get("id") or "default").strip() or "default"
        config_values = _provider_config_values(provider)
        if provider_id == "default":
            if legacy_api.get("api_key") and not config_values["api_key"][0]:
                config_values["api_key"] = (str(legacy_api.get("api_key") or "").strip(), "config.toml:api.api_key")
        credential_values = _provider_credential_values(provider_id, credentials)
        for field in ("api_key", "openai_api_key"):
            for value, source in (config_values[field], credential_values[field]):
                secret_value = str(value or "").strip()
                if not secret_value:
                    continue
                secret_ref = _legacy_secret_ref(source, provider_id)
                key = (provider_id, field, secret_ref)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(
                    {
                        "provider_id": provider_id,
                        "field": field,
                        "source": source,
                        "secret_ref": secret_ref,
                        "fingerprint": _secret_fingerprint(secret_value),
                        "value": secret_value,
                    }
                )
    return entries


def _write_legacy_secret_backend(*, target_root: Path, source_root: Path) -> dict[str, Any]:
    entries = _legacy_secret_entries(source_root)
    secret_dir = target_root / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    try:
        secret_dir.chmod(0o700)
    except OSError:
        pass
    path = secret_dir / "legacy-secrets.json"
    backup_path = ""
    if path.exists():
        backup_dir = target_root / "backups" / "legacy-import"
        backup_dir.mkdir(parents=True, exist_ok=True)
        digest = mms_registry.sha256_hex(path.read_bytes())
        backup = backup_dir / f"legacy-secrets.{_timestamp_slug()}.{digest[:12]}.json"
        mms_registry.copy_file_atomic(path, backup, mode=0o600)
        backup_path = str(backup)
    payload = {
        "schema": LEGACY_SECRET_BACKEND_SCHEMA,
        "source_config_root": str(source_root),
        "written_at": mms_registry.utc_now(),
        "secrets": entries,
    }
    mms_registry.write_json_atomic(path, payload, mode=0o600)
    return {
        "schema": LEGACY_SECRET_BACKEND_SCHEMA,
        "path": str(path),
        "secret_count": len(entries),
        "backup_path": backup_path,
        "plaintext_secret_store": True,
    }


def _registry_v2_webui_secret_entries(credential_updates: list[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in credential_updates or []:
        if not isinstance(item, Mapping):
            continue
        provider_id = str(item.get("provider_id") or item.get("id") or "").strip()
        secret_value = str(item.get("api_key") or "").strip()
        if not provider_id or not secret_value or "*" in secret_value:
            continue
        secret_ref = f"pending-webui:{_secret_ref_part(provider_id)}:api_key"
        if secret_ref in seen:
            continue
        seen.add(secret_ref)
        entries.append(
            {
                "provider_id": provider_id,
                "field": "api_key",
                "source": "webui-credential-update",
                "secret_ref": secret_ref,
                "fingerprint": _secret_fingerprint(secret_value),
                "value": secret_value,
            }
        )
    return entries


def write_registry_v2_webui_secret_backend(
    *,
    config_dir: str | Path | None = None,
    credential_updates: list[Mapping[str, Any]] | None = None,
    allow_stable: bool = False,
    command_name: str = "mms registry",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    root_status = mms_config_root_status(command=command_name.split()[0] if command_name else "mms", config_dir=root)
    if root_status.get("mode") != "preview" and not allow_stable:
        raise mms_registry.RegistryValidationError("refusing to write registry v2 WebUI secrets into stable config root without --allow-stable")
    entries = _registry_v2_webui_secret_entries(credential_updates)
    if not entries:
        return {
            "schema": REGISTRY_V2_WEBUI_SECRET_BACKEND_SCHEMA,
            "skipped": True,
            "skip_reason": "no_plaintext_credential_updates",
            "path": str(root / "secrets" / "webui-secrets.json"),
            "secret_count": 0,
            "plaintext_secret_store": True,
        }
    secret_dir = root / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    try:
        secret_dir.chmod(0o700)
    except OSError:
        pass
    path = secret_dir / "webui-secrets.json"
    backup_path = ""
    if path.exists():
        backup_dir = root / "backups" / "secret-backend"
        backup_dir.mkdir(parents=True, exist_ok=True)
        digest = mms_registry.sha256_hex(path.read_bytes())
        backup = backup_dir / f"webui-secrets.{_timestamp_slug()}.{digest[:12]}.json"
        mms_registry.copy_file_atomic(path, backup, mode=0o600)
        backup_path = str(backup)
    payload = {
        "schema": REGISTRY_V2_WEBUI_SECRET_BACKEND_SCHEMA,
        "written_at": mms_registry.utc_now(),
        "source": "webui-credential-update",
        "secrets": entries,
    }
    mms_registry.write_json_atomic(path, payload, mode=0o600)
    return {
        "schema": REGISTRY_V2_WEBUI_SECRET_BACKEND_SCHEMA,
        "skipped": False,
        "path": str(path),
        "secret_count": len(entries),
        "backup_path": backup_path,
        "plaintext_secret_store": True,
    }


def import_legacy_config(
    *,
    config_dir: str | Path | None = None,
    source_config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    apply: bool = False,
    allow_stable: bool = False,
    include_secrets: bool = False,
    command_name: str = "mms registry",
) -> dict[str, Any]:
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    source_root = Path(source_config_dir).expanduser() if source_config_dir is not None else root
    root_status = mms_config_root_status(command=command_name.split()[0] if command_name else "mms", config_dir=root)
    if root_status.get("mode") != "preview" and not allow_stable:
        raise mms_registry.RegistryValidationError("refusing to import into stable config root without --allow-stable")
    report = legacy_import_report(config_dir=source_root)
    payload = _legacy_import_payload(report)
    target_db = Path(db_path).expanduser() if db_path is not None else mms_registry.default_registry_db_path(config_dir=root)
    summary: dict[str, Any] = {
        "schema": LEGACY_IMPORT_SCHEMA,
        "apply": bool(apply),
        "config_root": str(root),
        "source_config_root": str(source_root),
        "db_path": str(target_db),
        "conflict_count": report.get("conflict_count", 0),
        "provider_count": report.get("provider_count", 0),
        "model_count": len(payload.get("models") or []),
        "plaintext_secret_in_db": False,
        "include_secrets": bool(include_secrets),
        "read_only_report": report,
    }
    if not apply:
        summary["skipped"] = True
        summary["skip_reason"] = "dry_run_apply_required"
        if include_secrets:
            summary["secret_backend"] = {
                "skipped": True,
                "skip_reason": "dry_run_apply_required",
                "secret_count": len(_legacy_secret_entries(source_root)),
            }
        return summary

    init_summary = init_config_root(config_dir=root, create_db=True, allow_stable=allow_stable, command_name=command_name)
    import_dir = root / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    payload_hash = mms_registry.sha256_hex(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    import_path = import_dir / f"legacy-import.{_timestamp_slug()}.{payload_hash[:12]}.json"
    mms_registry.write_json_atomic(import_path, payload)
    db = mms_registry.open_registry(target_db)
    try:
        source_summary = mms_registry.import_source_snapshot(db, import_path, source_kind=LEGACY_IMPORT_SOURCE_KIND)
        with db:
            route_summary = _insert_legacy_route_candidates(db, report, actor=command_name.split()[0] if command_name else "mms")
    finally:
        db.close()
    summary.update(
        {
            "skipped": False,
            "init": init_summary,
            "import_path": str(import_path),
            "source_snapshot": source_summary,
            "route_candidates": route_summary,
        }
    )
    if include_secrets:
        summary["secret_backend"] = _write_legacy_secret_backend(target_root=root, source_root=source_root)
    return summary



def apply_registry_v2_save_candidate(
    *,
    config_dir: str | Path | None = None,
    config_payload: Mapping[str, Any] | None = None,
    policy_payload: Mapping[str, Any] | None = None,
    credential_updates: list[Mapping[str, Any]] | None = None,
    db_path: str | Path | None = None,
    apply: bool = False,
    allow_stable: bool = False,
    command_name: str = "mms registry",
) -> dict[str, Any]:
    """Write preview DB candidate revisions for the future v2 save path."""
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    root = root.expanduser()
    root_status = mms_config_root_status(command=command_name.split()[0] if command_name else "mms", config_dir=root)
    if root_status.get("mode") != "preview" and not allow_stable:
        raise mms_registry.RegistryValidationError("refusing to write registry v2 save candidate into stable config root without --allow-stable")
    config_payload = config_payload if isinstance(config_payload, Mapping) else {}
    candidate_payload = _registry_v2_candidate_payload(
        config_payload,
        policy_payload=policy_payload if isinstance(policy_payload, Mapping) else {},
        credential_updates=credential_updates or [],
    )
    target_db = Path(db_path).expanduser() if db_path is not None else mms_registry.default_registry_db_path(config_dir=root)
    route_entries = candidate_payload.get("route_entries") if isinstance(candidate_payload.get("route_entries"), list) else []
    policy = candidate_payload.get("policy") if isinstance(candidate_payload.get("policy"), dict) else {}
    profile = candidate_payload.get("profile") if isinstance(candidate_payload.get("profile"), dict) else {}
    summary: dict[str, Any] = {
        "schema": REGISTRY_V2_SAVE_CANDIDATE_SCHEMA,
        "apply": bool(apply),
        "config_root": str(root),
        "db_path": str(target_db),
        "root": root_status,
        "plaintext_secret_in_db": False,
        "candidate": {
            "route_entry_count": len(route_entries),
            "policy_model_count": len(policy.get("models") if isinstance(policy.get("models"), dict) else {}),
            "profile_provider_count": len(profile.get("profiles") if isinstance(profile.get("profiles"), dict) else {}),
            "skipped": candidate_payload.get("skipped") or [],
        },
        "writes": {
            "target_preview_root": root_status.get("mode") == "preview",
            "db_candidate_revision": bool(apply),
            "secret_backend": False,
            "generated_latest_approved_bundle": False,
            "legacy_files": False,
        },
    }
    if not apply:
        summary["skipped"] = True
        summary["skip_reason"] = "dry_run_apply_required"
        return summary

    db_existed_before = target_db.exists()
    init_summary = init_config_root(config_dir=root, create_db=True, allow_stable=allow_stable, command_name=command_name)
    backup_summary = (
        mms_registry.backup_registry_db(config_dir=root, db_path=target_db, reason="pre-registry-v2-save-candidate")
        if db_existed_before
        else {"skipped": True, "reason": "new_db", "source_db_path": str(target_db)}
    )
    summary["init"] = init_summary
    summary["backup"] = backup_summary
    db = None
    try:
        db = mms_registry.open_registry(target_db)
        revisions = _insert_registry_v2_candidate_revisions(
            db,
            candidate_payload,
            actor=command_name.split()[0] if command_name else "mms",
        )
    except Exception as exc:
        if db is not None:
            db.close()
            db = None
        rollback: dict[str, Any] = {"attempted": False, "restored": False}
        backup_path = str(backup_summary.get("backup_path") or "") if isinstance(backup_summary, dict) else ""
        if backup_path:
            rollback["attempted"] = True
            try:
                rollback["restore"] = mms_registry.restore_registry_db(
                    backup_path,
                    config_dir=root,
                    db_path=target_db,
                    apply=True,
                    reason="registry-v2-save-candidate-failure",
                )
                rollback["restored"] = True
            except Exception as rollback_exc:  # pragma: no cover - defensive path
                rollback["error"] = f"{type(rollback_exc).__name__}: {rollback_exc}"
        summary["rollback"] = rollback
        summary["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        if db is not None:
            db.close()
    summary.update(
        {
            "skipped": False,
            "route_candidates": revisions.get("route", {}),
            "policy_candidate": revisions.get("policy", {}),
            "profile_candidate": revisions.get("profile", {}),
        }
    )
    return summary


def _registry_v2_candidate_inputs_from_files(
    *,
    plan_json: str = "",
    config_json: str = "",
    policy_json: str = "",
) -> tuple[dict[str, Any], dict[str, Any], list[Mapping[str, Any]]]:
    plan = _read_json_mapping(plan_json, label="plan-json") if str(plan_json or "").strip() else {}
    if plan:
        config_payload = plan.get("config") if isinstance(plan.get("config"), dict) else {}
        policy_payload = plan.get("model_policy") if isinstance(plan.get("model_policy"), dict) else {}
        credentials = plan.get("credential_updates") if isinstance(plan.get("credential_updates"), list) else []
    else:
        config_payload = _read_json_mapping(config_json, label="config-json") if str(config_json or "").strip() else {}
        policy_payload = _read_json_mapping(policy_json, label="policy-json") if str(policy_json or "").strip() else {}
        credentials = []
    if not config_payload:
        raise mms_registry.RegistryValidationError("registry v2 save candidate requires --plan-json or --config-json")
    credential_updates = [item for item in credentials if isinstance(item, Mapping)]
    return config_payload, policy_payload, credential_updates


def _reference_snapshot_paths(paths: Iterable[str | Path] | None = None) -> list[Path]:
    if paths:
        candidates = [Path(path).expanduser() for path in paths]
    else:
        candidates = sorted(DEFAULT_REFERENCE_DIR.glob("*.json"))
    return [path for path in candidates if path.exists() and path.is_file()]


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def source_freshness(
    *,
    db_path: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Report local source-reference staleness without importing new facts."""
    snapshot_paths = _reference_snapshot_paths(paths)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    max_age_seconds = max(0, int(max_age_hours or 0)) * 3600
    db = mms_registry.open_registry(db_path)
    sources: list[dict[str, Any]] = []
    try:
        for path in snapshot_paths:
            raw = path.read_bytes()
            content_hash = mms_registry.sha256_hex(raw)
            row = db.execute(
                """
                SELECT checked_at, content_hash, snapshot_id, status
                FROM source_check
                WHERE source_kind = ? AND source_path = ?
                """,
                (mms_registry.CALIBRATION_SOURCE_KIND, str(path)),
            ).fetchone()
            checked_at = str(row["checked_at"]) if row is not None else ""
            checked_dt = _parse_utc(checked_at)
            age_seconds = int((current - checked_dt).total_seconds()) if checked_dt is not None else None
            missing = row is None
            changed = row is not None and str(row["content_hash"]) != content_hash
            stale = age_seconds is None or age_seconds >= max_age_seconds
            due = bool(missing or changed or stale)
            if missing:
                reason = "never_checked"
            elif changed:
                reason = "source_content_changed"
            elif stale:
                reason = "max_age_exceeded"
            else:
                reason = "fresh"
            sources.append(
                {
                    "source_kind": mms_registry.CALIBRATION_SOURCE_KIND,
                    "source_path": str(path),
                    "checked_at": checked_at,
                    "age_seconds": age_seconds,
                    "max_age_hours": int(max_age_hours or 0),
                    "content_hash": content_hash,
                    "last_checked_hash": str(row["content_hash"]) if row is not None else "",
                    "snapshot_id": int(row["snapshot_id"]) if row is not None and row["snapshot_id"] is not None else None,
                    "status": str(row["status"]) if row is not None else "missing",
                    "due": due,
                    "reason": reason,
                }
            )
    finally:
        db.close()
    due_sources = [source for source in sources if source.get("due")]
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "max_age_hours": int(max_age_hours or 0),
        "source_count": len(sources),
        "due_count": len(due_sources),
        "fresh_count": len(sources) - len(due_sources),
        "sources": sources,
    }


def _openrouter_file_content_hash(path: str | Path) -> str:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return mms_registry.sha256_hex(canonical)


def _row_age_status(
    row,
    *,
    max_age_hours: int,
    now: datetime | None = None,
    expected_content_hash: str | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    checked_at = str(row["checked_at"]) if row is not None else ""
    checked_dt = _parse_utc(checked_at)
    age_seconds = int((current - checked_dt).total_seconds()) if checked_dt is not None else None
    stale = age_seconds is None or age_seconds >= max(0, int(max_age_hours or 0)) * 3600
    changed = row is not None and bool(expected_content_hash) and str(row["content_hash"]) != expected_content_hash
    if row is None:
        reason = "never_checked"
    elif changed:
        reason = "source_content_changed"
    elif stale:
        reason = "max_age_exceeded"
    else:
        reason = "fresh"
    return {
        "checked_at": checked_at,
        "age_seconds": age_seconds,
        "max_age_hours": int(max_age_hours or 0),
        "due": bool(row is None or changed or stale),
        "reason": reason,
    }


def openrouter_catalog_freshness(
    *,
    db_path: str | Path | None = None,
    max_age_hours: int = DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS,
    now: datetime | None = None,
    source_path: str | Path | None = None,
    expected_content_hash: str | None = None,
) -> dict[str, Any]:
    catalog_source_path = str(Path(source_path).expanduser() if source_path else OPENROUTER_MODELS_API_URL)
    db = mms_registry.open_registry(db_path)
    try:
        row = db.execute(
            """
            SELECT checked_at, content_hash, snapshot_id, status
            FROM source_check
            WHERE source_kind = ? AND source_path = ?
            """,
            (mms_registry.OPENROUTER_MODELS_SOURCE_KIND, catalog_source_path),
        ).fetchone()
    finally:
        db.close()
    status = _row_age_status(
        row,
        max_age_hours=max_age_hours,
        now=now,
        expected_content_hash=expected_content_hash,
    )
    status.update(
        {
            "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
            "source_kind": mms_registry.OPENROUTER_MODELS_SOURCE_KIND,
            "source_path": catalog_source_path,
            "content_hash": str(row["content_hash"]) if row is not None else "",
            "expected_content_hash": expected_content_hash or "",
            "snapshot_id": int(row["snapshot_id"]) if row is not None and row["snapshot_id"] is not None else None,
            "status": str(row["status"]) if row is not None else "missing",
        }
    )
    return status


def refresh_source_snapshots(
    *,
    db_path: str | Path | None = None,
    paths: Iterable[str | Path] | None = None,
    if_due: bool = False,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Import local source snapshots into the registry DB without promotion."""
    snapshot_paths = _reference_snapshot_paths(paths)
    freshness = None
    if if_due:
        freshness = source_freshness(db_path=db_path, paths=snapshot_paths, max_age_hours=max_age_hours)
        due_paths = {str(item.get("source_path")) for item in freshness.get("sources", []) if item.get("due")}
        snapshot_paths = [path for path in snapshot_paths if str(path) in due_paths]
    db = mms_registry.open_registry(db_path)
    imported: list[dict[str, Any]] = []
    try:
        for path in snapshot_paths:
            imported.append(mms_registry.import_source_snapshot(db, path))
    finally:
        db.close()
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "source_paths": [str(path) for path in snapshot_paths],
        "imported": imported,
        "imported_count": len(imported),
        "skipped_count": len(_reference_snapshot_paths(paths)) - len(snapshot_paths) if if_due else 0,
        "model_count": sum(int(item.get("model_count", 0) or 0) for item in imported),
        "fact_count": sum(int(item.get("fact_count", 0) or 0) for item in imported),
        "freshness": freshness or source_freshness(db_path=db_path, paths=_reference_snapshot_paths(paths), max_age_hours=max_age_hours),
    }


def fetch_openrouter_catalog(
    *,
    db_path: str | Path | None = None,
    url: str = OPENROUTER_MODELS_API_URL,
    from_file: str | Path | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Fetch or import OpenRouter model catalog as provider_catalog evidence."""
    source_url = str(url or OPENROUTER_MODELS_API_URL)
    if from_file:
        file_path = Path(from_file).expanduser()
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        source_path = str(file_path)
        transport = "file"
    else:
        request = Request(
            source_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MMS-Registry/1.0 (+https://github.com/CtriXin/multi-model-switch)",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        source_path = source_url
        transport = "network"
    if not isinstance(payload, dict):
        raise mms_registry.RegistryValidationError("OpenRouter catalog payload must be a JSON object")
    db = mms_registry.open_registry(db_path)
    try:
        summary = mms_registry.import_raw_source_payload(
            db,
            payload,
            source_kind=mms_registry.OPENROUTER_MODELS_SOURCE_KIND,
            source_path=source_path,
        )
    finally:
        db.close()
    summary.update(
        {
            "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
            "transport": transport,
            "url": source_url,
        }
    )
    return summary


def _latest_source_payload(db, source_kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row = db.execute(
        """
        SELECT snapshot_id, source_kind, source_path, captured_at, content_hash, model_count, payload_json
        FROM source_snapshot
        WHERE source_kind = ?
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        (source_kind,),
    ).fetchone()
    if row is None:
        raise mms_registry.RegistryValidationError(f"missing source snapshot: {source_kind}")
    payload = json.loads(str(row["payload_json"] or "{}"))
    if not isinstance(payload, dict):
        raise mms_registry.RegistryValidationError(f"source snapshot payload must be object: {source_kind}")
    return dict(row), payload


def _openrouter_items(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    items = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            items[model_id] = item
    return items


def _calibration_openrouter_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for model in payload.get("models") or []:
        if not isinstance(model, dict):
            continue
        alias = str(model.get("alias") or model.get("canonical_model_id") or "").strip()
        for ref in model.get("provider_catalog_references") or []:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("source") or "").lower() != "openrouter":
                continue
            provider_model_id = str(ref.get("model_id") or model.get("openrouter_model_id") or "").strip()
            if not provider_model_id:
                continue
            top_provider = ref.get("top_provider") if isinstance(ref.get("top_provider"), dict) else {}
            refs.append(
                {
                    "model_key": alias,
                    "provider_model_id": provider_model_id,
                    "context_length": ref.get("context_length"),
                    "max_completion_tokens": top_provider.get("max_completion_tokens"),
                    "pricing": ref.get("pricing_raw_usd_per_unit") or model.get("provider_pricing_raw_usd_per_unit") or {},
                    "supported_parameters": sorted(ref.get("supported_parameters") or model.get("provider_supported_parameters") or []),
                }
            )
    return refs


def _candidate_value(item: dict[str, Any], field_key: str) -> Any:
    if field_key == "context_length":
        return item.get("context_length")
    if field_key == "max_completion_tokens":
        top_provider = item.get("top_provider") if isinstance(item.get("top_provider"), dict) else {}
        return top_provider.get("max_completion_tokens")
    if field_key == "pricing":
        return item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    if field_key == "supported_parameters":
        return sorted(item.get("supported_parameters") or [])
    return None


def _canonical_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":")) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def diff_openrouter_catalog(
    *,
    db_path: str | Path | None = None,
    store: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Compare latest OpenRouter catalog source with calibration OpenRouter refs."""
    db = mms_registry.open_registry(db_path)
    try:
        openrouter_snapshot, openrouter_payload = _latest_source_payload(db, mms_registry.OPENROUTER_MODELS_SOURCE_KIND)
        baseline_snapshot, baseline_payload = _latest_source_payload(db, mms_registry.CALIBRATION_SOURCE_KIND)
        catalog = _openrouter_items(openrouter_payload)
        refs = _calibration_openrouter_refs(baseline_payload)
        changes: list[dict[str, Any]] = []
        missing = 0
        for ref in refs:
            item = catalog.get(ref["provider_model_id"])
            if item is None:
                missing += 1
                changes.append(
                    {
                        "change_kind": "provider_catalog_missing",
                        "model_key": ref["model_key"],
                        "provider_model_id": ref["provider_model_id"],
                        "field_key": "presence",
                        "old_value": "present_in_baseline",
                        "new_value": "missing_in_catalog",
                        "metadata": {},
                    }
                )
                continue
            for field_key in ("context_length", "max_completion_tokens", "pricing", "supported_parameters"):
                old_value = ref.get(field_key)
                new_value = _candidate_value(item, field_key)
                if _canonical_equal(old_value, new_value):
                    continue
                changes.append(
                    {
                        "change_kind": "provider_catalog_changed",
                        "model_key": ref["model_key"],
                        "provider_model_id": ref["provider_model_id"],
                        "field_key": field_key,
                        "old_value": old_value,
                        "new_value": new_value,
                        "metadata": {"source": "openrouter"},
                    }
                )
        referenced_ids = {ref["provider_model_id"] for ref in refs}
        untracked_count = len(set(catalog) - referenced_ids)
        record = {"recorded_count": 0}
        if store:
            record = mms_registry.record_candidate_changes(
                db,
                changes,
                source_snapshot_id=int(openrouter_snapshot["snapshot_id"]),
                baseline_snapshot_id=int(baseline_snapshot["snapshot_id"]),
            )
        stored_count = int(record.get("recorded_count", 0) or 0)
    finally:
        db.close()
    return {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "source_snapshot_id": int(openrouter_snapshot["snapshot_id"]),
        "baseline_snapshot_id": int(baseline_snapshot["snapshot_id"]),
        "matched_reference_count": len(refs),
        "missing_reference_count": missing,
        "untracked_catalog_count": untracked_count,
        "change_count": len(changes),
        "stored_count": stored_count,
        "changes": changes[: max(0, int(limit or 0))],
    }


def scheduled_refresh(
    *,
    db_path: str | Path | None = None,
    max_age_hours: int = DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS,
    openrouter_max_age_hours: int = DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS,
    include_openrouter: bool = True,
    no_network: bool = False,
    openrouter_from_file: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Safe entrypoint for cron/launchd/manual scheduled refresh runs."""
    source_status = source_freshness(db_path=db_path, max_age_hours=max_age_hours)
    openrouter_source_path = str(Path(openrouter_from_file).expanduser()) if openrouter_from_file else OPENROUTER_MODELS_API_URL
    openrouter_expected_hash = _openrouter_file_content_hash(openrouter_from_file) if openrouter_from_file else None
    openrouter_status = openrouter_catalog_freshness(
        db_path=db_path,
        max_age_hours=openrouter_max_age_hours,
        source_path=openrouter_source_path,
        expected_content_hash=openrouter_expected_hash,
    )
    result: dict[str, Any] = {
        "db_path": str(Path(db_path) if db_path else mms_registry.default_registry_db_path()),
        "dry_run": bool(dry_run),
        "source_due_count": source_status.get("due_count", 0),
        "source_status": source_status,
        "openrouter_due": bool(openrouter_status.get("due")),
        "openrouter_status": openrouter_status,
        "source_refresh": {"skipped": True},
        "openrouter_fetch": {"skipped": True},
        "openrouter_diff": {"skipped": True},
    }
    if dry_run:
        return result
    if int(source_status.get("due_count", 0) or 0) > 0:
        result["source_refresh"] = refresh_source_snapshots(
            db_path=db_path,
            if_due=True,
            max_age_hours=max_age_hours,
        )
    else:
        result["source_refresh"] = {"skipped": True, "reason": "not_due"}
    if not include_openrouter:
        result["openrouter_fetch"] = {"skipped": True, "reason": "no_openrouter"}
        result["openrouter_diff"] = {"skipped": True, "reason": "no_openrouter"}
        return result
    if include_openrouter and bool(openrouter_status.get("due")):
        if no_network and not openrouter_from_file:
            result["openrouter_fetch"] = {"skipped": True, "reason": "no_network"}
        else:
            try:
                result["openrouter_fetch"] = fetch_openrouter_catalog(
                    db_path=db_path,
                    from_file=openrouter_from_file,
                )
            except Exception as exc:  # Network scheduled jobs should record failure, not alter runtime truth.
                result["openrouter_fetch"] = {
                    "skipped": True,
                    "status": "error",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
                return result
            try:
                result["openrouter_diff"] = diff_openrouter_catalog(db_path=db_path, limit=20)
            except mms_registry.RegistryValidationError as exc:
                result["openrouter_diff"] = {"skipped": True, "reason": str(exc)}
    else:
        result["openrouter_fetch"] = {"skipped": True, "reason": "not_due"}
        result["openrouter_diff"] = {"skipped": True, "reason": "not_due"}
    return result


def registry_status(*, db_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path else mms_registry.default_registry_db_path()
    exists_before = path.exists()
    db = mms_registry.open_registry(path)
    try:
        counts = {}
        for table in (
            "source_snapshot",
            "source_check",
            "candidate_change",
            "model_identity",
            "model_fact",
            "registry_revision",
            "export_snapshot",
            "tombstone_event",
        ):
            counts[table] = int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
        latest = db.execute(
            """
            SELECT source_kind, source_path, captured_at, model_count, content_hash
            FROM source_snapshot
            ORDER BY snapshot_id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_snapshot = dict(latest) if latest is not None else {}
        user_version = int(db.execute("PRAGMA user_version").fetchone()[0])
        journal_mode = str(db.execute("PRAGMA journal_mode").fetchone()[0])
    finally:
        db.close()
    freshness = source_freshness(db_path=path)
    return {
        "db_path": str(path),
        "existed_before": exists_before,
        "user_version": user_version,
        "journal_mode": journal_mode,
        "counts": counts,
        "latest_source_snapshot": latest_snapshot,
        "source_freshness": freshness,
    }


def publish_approved_bundle(
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    return mms_registry.publish_latest_approved_bundle(config_dir=config_dir, db_path=db_path, actor="mms")


def publish_preview_bundle(
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    return mms_registry.publish_latest_approved_bundle_from_legacy_candidates(
        config_dir=config_dir,
        db_path=db_path,
        actor="mms",
    )


def verify_approved_bundle(
    *,
    config_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    return mms_registry.verify_latest_approved_bundle(config_dir=config_dir, manifest_path=manifest_path)


def resolve_approved_model(
    model_name: str,
    *,
    config_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    facts_path = mms_registry.latest_approved_capability_facts_path(
        config_dir=config_dir,
        manifest_path=manifest_path,
    )
    return resolve_model_capabilities(model_name, approved_facts_path=facts_path)


def backup_registry_db(
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
    reason: str = "manual",
) -> dict[str, Any]:
    return mms_registry.backup_registry_db(
        config_dir=config_dir,
        db_path=db_path,
        backup_dir=backup_dir,
        reason=reason,
    )


def restore_registry_db(
    backup_path: str | Path,
    *,
    config_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    apply: bool = False,
    reason: str = "manual",
) -> dict[str, Any]:
    return mms_registry.restore_registry_db(
        backup_path,
        config_dir=config_dir,
        db_path=db_path,
        apply=apply,
        reason=reason,
    )


def _print_status(status: dict[str, Any]) -> None:
    counts = status.get("counts") if isinstance(status.get("counts"), dict) else {}
    latest = status.get("latest_source_snapshot") if isinstance(status.get("latest_source_snapshot"), dict) else {}
    freshness = status.get("source_freshness") if isinstance(status.get("source_freshness"), dict) else {}
    print("MMS Registry")
    print(f"db_path={status.get('db_path')}")
    print(f"user_version={status.get('user_version')}")
    print(f"journal_mode={status.get('journal_mode')}")
    for key in sorted(counts):
        print(f"{key}={counts[key]}")
    print(f"source_due_count={freshness.get('due_count', 0)}")
    print(f"source_fresh_count={freshness.get('fresh_count', 0)}")
    if latest:
        print(f"latest_source_kind={latest.get('source_kind')}")
        print(f"latest_source_path={latest.get('source_path')}")
        print(f"latest_model_count={latest.get('model_count')}")
        print(f"latest_captured_at={latest.get('captured_at')}")
    else:
        print("latest_source_snapshot=none")


def _print_freshness(summary: dict[str, Any]) -> None:
    print("MMS Registry Source Staleness")
    print(f"db_path={summary.get('db_path')}")
    print(f"max_age_hours={summary.get('max_age_hours')}")
    print(f"source_count={summary.get('source_count')}")
    print(f"due_count={summary.get('due_count')}")
    print(f"fresh_count={summary.get('fresh_count')}")
    for item in summary.get("sources") or []:
        print(
            "source="
            f"due={item.get('due')} "
            f"reason={item.get('reason')} "
            f"checked_at={item.get('checked_at') or '-'} "
            f"path={item.get('source_path')}"
        )


def _print_publish(summary: dict[str, Any]) -> None:
    print("MMS Registry Publish Approved Bundle")
    print(f"manifest_path={summary.get('manifest_path')}")
    print(f"bundle_revision={summary.get('bundle_revision')}")
    print(f"capability_revision={summary.get('capability_revision')}")
    print(f"route_revision={summary.get('route_revision')}")
    print(f"policy_revision={summary.get('policy_revision')}")
    print(f"profile_revision={summary.get('profile_revision')}")
    files = summary.get("files") if isinstance(summary.get("files"), dict) else {}
    for name in sorted(files):
        print(f"file_{name}={files[name]}")


def _print_verify(summary: dict[str, Any]) -> None:
    manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    files = summary.get("verified_files") if isinstance(summary.get("verified_files"), dict) else {}
    print("MMS Registry Verify Approved Bundle")
    print(f"verified={summary.get('verified')}")
    print(f"manifest_path={summary.get('manifest_path')}")
    print(f"bundle_revision={manifest.get('bundle_revision')}")
    for name in sorted(files):
        print(f"verified_file={name} path={files[name].get('path')} sha256={files[name].get('sha256')}")


def _print_resolve(model_name: str, caps: dict[str, Any]) -> None:
    print("MMS Registry Resolve")
    print(f"model={model_name}")
    for key in (
        "context_window_tokens",
        "max_output_tokens",
        "supports_thinking",
        "expected_protocol",
    ):
        print(f"{key}={caps.get(key)} source={caps.get('sources', {}).get(key)}")
    thinking = caps.get("thinking_control") if isinstance(caps.get("thinking_control"), dict) else {}
    print(f"thinking_control_type={thinking.get('control_type') or ''}")
    print(f"thinking_control_path={thinking.get('path') or ''}")


def _print_refresh(summary: dict[str, Any]) -> None:
    print("MMS Registry Refresh Sources")
    print(f"db_path={summary.get('db_path')}")
    print(f"imported_count={summary.get('imported_count')}")
    print(f"skipped_count={summary.get('skipped_count', 0)}")
    print(f"model_count={summary.get('model_count')}")
    print(f"fact_count={summary.get('fact_count')}")
    for item in summary.get("imported") or []:
        print(
            "source_snapshot="
            f"{item.get('snapshot_id')} "
            f"models={item.get('model_count')} "
            f"facts={item.get('fact_count')} "
            f"path={item.get('source_path')}"
        )


def _print_fetch_catalog(summary: dict[str, Any]) -> None:
    print("MMS Registry Fetch OpenRouter Catalog")
    print(f"db_path={summary.get('db_path')}")
    print(f"transport={summary.get('transport')}")
    print(f"source_kind={summary.get('source_kind')}")
    print(f"source_path={summary.get('source_path')}")
    print(f"snapshot_id={summary.get('snapshot_id')}")
    print(f"model_count={summary.get('model_count')}")
    print(f"content_hash={summary.get('content_hash')}")


def _print_openrouter_diff(summary: dict[str, Any]) -> None:
    print("MMS Registry OpenRouter Candidate Diff")
    print(f"db_path={summary.get('db_path')}")
    print(f"source_snapshot_id={summary.get('source_snapshot_id')}")
    print(f"baseline_snapshot_id={summary.get('baseline_snapshot_id')}")
    print(f"matched_reference_count={summary.get('matched_reference_count')}")
    print(f"missing_reference_count={summary.get('missing_reference_count')}")
    print(f"untracked_catalog_count={summary.get('untracked_catalog_count')}")
    print(f"change_count={summary.get('change_count')}")
    print(f"stored_count={summary.get('stored_count')}")
    for item in summary.get("changes") or []:
        print(
            "candidate_change="
            f"{item.get('model_key')} "
            f"{item.get('provider_model_id')} "
            f"{item.get('field_key')} "
            f"{item.get('change_kind')}"
        )


def _print_scheduled_refresh(summary: dict[str, Any]) -> None:
    print("MMS Registry Scheduled Refresh")
    print(f"db_path={summary.get('db_path')}")
    print(f"dry_run={summary.get('dry_run')}")
    print(f"source_due_count={summary.get('source_due_count')}")
    print(f"openrouter_due={summary.get('openrouter_due')}")
    source_refresh = summary.get("source_refresh") if isinstance(summary.get("source_refresh"), dict) else {}
    openrouter_fetch = summary.get("openrouter_fetch") if isinstance(summary.get("openrouter_fetch"), dict) else {}
    openrouter_diff = summary.get("openrouter_diff") if isinstance(summary.get("openrouter_diff"), dict) else {}
    openrouter_status = summary.get("openrouter_status") if isinstance(summary.get("openrouter_status"), dict) else {}
    print(f"source_imported={source_refresh.get('imported_count', 0)}")
    print(f"source_skipped={source_refresh.get('skipped_count', 0) if 'skipped_count' in source_refresh else source_refresh.get('skipped')}")
    print(f"source_skip_reason={source_refresh.get('reason', '')}")
    print(f"openrouter_source_path={openrouter_status.get('source_path', '')}")
    print(f"openrouter_fetched={not bool(openrouter_fetch.get('skipped', False))}")
    print(f"openrouter_fetch_reason={openrouter_fetch.get('reason', '')}")
    print(f"openrouter_model_count={openrouter_fetch.get('model_count', 0)}")
    print(f"candidate_changes={openrouter_diff.get('stored_count', 0)}")
    print(f"candidate_skip_reason={openrouter_diff.get('reason', '')}")


def _print_backup(summary: dict[str, Any]) -> None:
    print("MMS Registry DB Backup")
    print(f"skipped={summary.get('skipped', False)}")
    print(f"reason={summary.get('reason', '')}")
    print(f"source_db_path={summary.get('source_db_path', '')}")
    print(f"backup_path={summary.get('backup_path', '')}")
    print(f"manifest_path={summary.get('manifest_path', '')}")
    print(f"sha256={summary.get('sha256', '')}")
    print(f"integrity_check={summary.get('integrity_check', '')}")


def _print_restore(summary: dict[str, Any]) -> None:
    print("MMS Registry DB Restore")
    print(f"apply={summary.get('apply', False)}")
    print(f"skipped={summary.get('skipped', False)}")
    print(f"skip_reason={summary.get('skip_reason', '')}")
    print(f"backup_path={summary.get('backup_path', '')}")
    print(f"target_db_path={summary.get('target_db_path', '')}")
    print(f"backup_sha256={summary.get('backup_sha256', '')}")
    print(f"integrity_check={summary.get('integrity_check', '')}")
    pre_restore = summary.get("pre_restore_backup") if isinstance(summary.get("pre_restore_backup"), dict) else {}
    print(f"pre_restore_backup_path={pre_restore.get('backup_path', '')}")
    print(f"restored_integrity_check={summary.get('restored_integrity_check', '')}")


def _print_legacy_import_report(summary: dict[str, Any]) -> None:
    print("MMS Legacy Import Report")
    print(f"config_root={summary.get('config_root')}")
    print(f"read_only={summary.get('read_only')}")
    print(f"provider_count={summary.get('provider_count')}")
    print(f"conflict_count={summary.get('conflict_count')}")
    print(f"next_action={summary.get('next_action')}")
    files = summary.get("files") if isinstance(summary.get("files"), dict) else {}
    for name in sorted(files):
        item = files[name] if isinstance(files[name], dict) else {}
        print(f"file_{name}_exists={item.get('exists', False)} path={item.get('path', '')}")
    for item in summary.get("conflicts") or []:
        print(
            "conflict="
            f"provider={item.get('provider_id')} "
            f"field={item.get('field')} "
            f"config={item.get('config_source')} "
            f"credentials={item.get('credentials_source')} "
            f"winner={item.get('winner')}"
        )
    for item in summary.get("secret_refs") or []:
        print(
            "secret_ref="
            f"provider={item.get('provider_id')} "
            f"field={item.get('field')} "
            f"ref={item.get('secret_ref')} "
            f"fingerprint={item.get('fingerprint')}"
        )


def _print_model_source_status(summary: dict[str, Any]) -> None:
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    registry_db = summary.get("registry_db") if isinstance(summary.get("registry_db"), dict) else {}
    legacy = summary.get("legacy_import") if isinstance(summary.get("legacy_import"), dict) else {}
    bundle = summary.get("generated_bundle") if isinstance(summary.get("generated_bundle"), dict) else {}
    counts = registry_db.get("counts") if isinstance(registry_db.get("counts"), dict) else {}
    candidates = legacy.get("candidates") if isinstance(legacy.get("candidates"), dict) else {}
    print("MMS Model Source Status")
    print(f"command={root.get('command')}")
    print(f"mode={root.get('mode')}")
    print(f"config_root={root.get('config_root')}")
    print(f"registry_db_path={registry_db.get('path')}")
    print(f"registry_db_status={registry_db.get('status')}")
    print(f"registry_source_snapshots={counts.get('source_snapshot', 0)}")
    print(f"registry_model_facts={counts.get('model_fact', 0)}")
    print(f"registry_provider_routes={counts.get('provider_route', 0)}")
    print(f"legacy_provider_count={legacy.get('provider_count', 0)}")
    print(f"legacy_conflict_count={legacy.get('conflict_count', 0)}")
    print(f"legacy_candidate_status={candidates.get('status', 'not_imported')}")
    print(f"legacy_candidate_snapshots={candidates.get('source_snapshot_count', 0)}")
    print(f"legacy_candidate_route_revisions={candidates.get('route_revision_count', 0)}")
    print(f"legacy_candidate_provider_routes={candidates.get('provider_route_count', 0)}")
    print(f"legacy_next_action={legacy.get('next_action', '')}")
    print(f"bundle_manifest_path={bundle.get('manifest_path')}")
    print(f"bundle_status={bundle.get('status')}")
    print(f"bundle_verified={bundle.get('verified', False)}")
    print(f"bundle_runtime_ready={bundle.get('runtime_ready')}")
    print(f"bundle_runtime_ready_status={bundle.get('runtime_ready_status', 'unknown')}")
    print(f"bundle_router_missing_api_key_count={bundle.get('router_missing_api_key_count', 0)}")
    print(f"bundle_router_missing_base_url_count={bundle.get('router_missing_base_url_count', 0)}")
    print(f"read_only={summary.get('read_only', False)}")


def _print_registry_v2_save_plan(plan: dict[str, Any]) -> None:
    root = plan.get("root") if isinstance(plan.get("root"), dict) else {}
    db = plan.get("db") if isinstance(plan.get("db"), dict) else {}
    would_write = plan.get("would_write") if isinstance(plan.get("would_write"), dict) else {}
    legacy = would_write.get("legacy_compat_files") if isinstance(would_write.get("legacy_compat_files"), dict) else {}
    print("MMS Registry v2 Save Plan")
    print(f"schema={plan.get('schema')}")
    print(f"read_only={plan.get('read_only', False)}")
    print(f"execution_state={plan.get('execution_state')}")
    print(f"actual_save_enabled={plan.get('actual_save_enabled', False)}")
    print(f"command={root.get('command')}")
    print(f"mode={root.get('mode')}")
    print(f"config_root={root.get('config_root')}")
    print(f"registry_db_path={db.get('path')}")
    print(f"registry_db_exists={db.get('exists', False)}")
    print(f"backup_dir={db.get('backup_dir')}")
    print(f"would_backup_existing_db={db.get('would_backup_existing_db', False)}")
    print(f"would_write_db_candidate_revision={would_write.get('db_candidate_revision', False)}")
    print(f"would_write_secret_backend={would_write.get('secret_backend', False)}")
    print(f"would_write_generated_latest_approved_bundle={would_write.get('generated_latest_approved_bundle', False)}")
    print(f"would_write_legacy_config_toml={legacy.get('config_toml', False)}")
    print(f"would_write_legacy_model_policy_json={legacy.get('model_policy_json', False)}")
    print(f"would_write_legacy_credentials_sh={legacy.get('credentials_sh', False)}")
    print(f"blocked_reasons={','.join(str(item) for item in (plan.get('blocked_reasons') or []))}")
    for index, step in enumerate(plan.get("ordered_steps") or [], start=1):
        print(f"step_{index}={step}")
    print(f"next_implementation_step={plan.get('next_implementation_step', '')}")


def _print_registry_v2_save_candidate(summary: dict[str, Any]) -> None:
    candidate = summary.get("candidate") if isinstance(summary.get("candidate"), dict) else {}
    route = summary.get("route_candidates") if isinstance(summary.get("route_candidates"), dict) else {}
    policy = summary.get("policy_candidate") if isinstance(summary.get("policy_candidate"), dict) else {}
    profile = summary.get("profile_candidate") if isinstance(summary.get("profile_candidate"), dict) else {}
    backup = summary.get("backup") if isinstance(summary.get("backup"), dict) else {}
    print("MMS Registry v2 Save Candidate")
    print(f"schema={summary.get('schema')}")
    print(f"apply={summary.get('apply', False)}")
    print(f"skipped={summary.get('skipped', False)}")
    print(f"skip_reason={summary.get('skip_reason', '')}")
    print(f"config_root={summary.get('config_root')}")
    print(f"db_path={summary.get('db_path')}")
    print(f"route_entry_count={candidate.get('route_entry_count', 0)}")
    print(f"policy_model_count={candidate.get('policy_model_count', 0)}")
    print(f"profile_provider_count={candidate.get('profile_provider_count', 0)}")
    print(f"route_revision_id={route.get('revision_id', '')}")
    print(f"provider_route_count={route.get('provider_route_count', 0)}")
    print(f"policy_revision_id={policy.get('revision_id', '')}")
    print(f"profile_revision_id={profile.get('revision_id', '')}")
    print(f"backup_skipped={backup.get('skipped', '')}")
    print(f"backup_path={backup.get('backup_path', '')}")
    print(f"plaintext_secret_in_db={summary.get('plaintext_secret_in_db', False)}")


def _print_preview_doctor(summary: dict[str, Any]) -> None:
    print("MMF Preview Doctor")
    print(f"result={summary.get('result')}")
    print(f"ready={summary.get('ready')}")
    print(f"status={summary.get('status')}")
    print(f"config_root={summary.get('config_root')}")
    print(f"read_only={summary.get('read_only', False)}")
    for item in summary.get("checks") or []:
        if not isinstance(item, dict):
            continue
        state = "ok" if item.get("ok") else "fail"
        print(f"check_{item.get('id')}={state} detail={item.get('detail', '')}")
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    print(f"candidate_provider_routes={counts.get('candidate_provider_routes', 0)}")
    print(f"bundle_routes={counts.get('bundle_routes', 0)}")
    print(f"missing_api_keys={counts.get('missing_api_keys', 0)}")
    print(f"missing_base_urls={counts.get('missing_base_urls', 0)}")
    print(f"preview_secret_count={counts.get('preview_secret_count', 0)}")
    bundle = summary.get("bundle") if isinstance(summary.get("bundle"), dict) else {}
    print(f"bundle_verified={bundle.get('verified', False)}")
    print(f"bundle_runtime_ready={bundle.get('runtime_ready')}")
    next_actions = [item for item in (summary.get("next_actions") or []) if isinstance(item, dict)]
    if next_actions:
        first = next_actions[0]
        print(f"next_action={first.get('label', '')}")
        print(f"next_command={first.get('command', '')}")


def _print_preview_prepare(summary: dict[str, Any]) -> None:
    print("MMF Preview Prepare")
    print(f"result={summary.get('result')}")
    print(f"ready={summary.get('ready')}")
    print(f"ok={summary.get('ok')}")
    print(f"config_root={summary.get('config_root')}")
    print(f"source_config_root={summary.get('source_config_root')}")
    print(f"include_secrets={summary.get('include_secrets')}")
    stages = summary.get("stages") if isinstance(summary.get("stages"), dict) else {}
    for name in ("init", "backup", "import", "publish", "verify"):
        stage = stages.get(name) if isinstance(stages.get(name), dict) else {}
        compact = " ".join(f"{key}={stage[key]}" for key in sorted(stage))
        print(f"stage_{name}={compact}")
    doctor = summary.get("doctor") if isinstance(summary.get("doctor"), dict) else {}
    print(f"doctor_status={doctor.get('status')}")
    next_actions = [item for item in (doctor.get("next_actions") or []) if isinstance(item, dict)]
    if next_actions:
        first = next_actions[0]
        print(f"next_action={first.get('label', '')}")
        print(f"next_command={first.get('command', '')}")


def _print_init_config_root(summary: dict[str, Any]) -> None:
    root = summary.get("root") if isinstance(summary.get("root"), dict) else {}
    print("MMS Config Root Init")
    print(f"config_root={root.get('config_root')}")
    print(f"mode={root.get('mode')}")
    print(f"db_path={summary.get('db_path')}")
    print(f"db_initialized={summary.get('db_initialized')}")
    print(f"db_created={summary.get('db_created')}")
    print(f"manifest_path={summary.get('manifest_path')}")
    print(f"layout_dirs={len(summary.get('layout_dirs') or [])}")


def _print_legacy_import(summary: dict[str, Any]) -> None:
    route_candidates = summary.get("route_candidates") if isinstance(summary.get("route_candidates"), dict) else {}
    source_snapshot = summary.get("source_snapshot") if isinstance(summary.get("source_snapshot"), dict) else {}
    secret_backend = summary.get("secret_backend") if isinstance(summary.get("secret_backend"), dict) else {}
    print("MMS Legacy Import")
    print(f"apply={summary.get('apply')}")
    print(f"skipped={summary.get('skipped', False)}")
    if summary.get("skip_reason"):
        print(f"skip_reason={summary.get('skip_reason')}")
    print(f"config_root={summary.get('config_root')}")
    print(f"source_config_root={summary.get('source_config_root')}")
    print(f"db_path={summary.get('db_path')}")
    print(f"provider_count={summary.get('provider_count')}")
    print(f"model_count={summary.get('model_count')}")
    print(f"conflict_count={summary.get('conflict_count')}")
    print(f"import_path={summary.get('import_path', '')}")
    print(f"source_snapshot_id={source_snapshot.get('snapshot_id', '')}")
    print(f"route_revision_id={route_candidates.get('route_revision_id', '')}")
    print(f"provider_route_count={route_candidates.get('provider_route_count', 0)}")
    print(f"include_secrets={summary.get('include_secrets', False)}")
    print(f"secret_backend_path={secret_backend.get('path', '')}")
    print(f"secret_backend_count={secret_backend.get('secret_count', 0)}")
    print(f"plaintext_secret_in_db={summary.get('plaintext_secret_in_db')}")


def handle_registry_command(argv: list[str], *, command_name: str = "mms registry") -> int:
    parser = argparse.ArgumentParser(
        prog=command_name,
        description="Manage MMS local model registry source truth.",
    )
    parser.add_argument("--db", default="", help="Override registry sqlite path")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("status", help="Show local registry DB status")
    subparsers.add_parser("doctor", help="Alias of status for now; does not change runtime truth")
    source_status_parser = subparsers.add_parser("source-status", help="Read-only model source status summary")
    source_status_parser.add_argument("--config-dir", default="", help="Override MMS config dir to inspect")
    source_status_parser.add_argument("--json", action="store_true", help="Print the full status as JSON")
    save_plan_parser = subparsers.add_parser("save-plan", help="Read-only v2 DB-truth save plan; does not write")
    save_plan_parser.add_argument("--config-dir", default="", help="Override MMS config dir to inspect")
    save_plan_parser.add_argument("--json", action="store_true", help="Print the full save plan as JSON")
    save_candidate_parser = subparsers.add_parser(
        "v2-save-candidate",
        help="Write preview DB candidate revisions from a WebUI plan/config JSON; dry-run unless --apply",
    )
    save_candidate_parser.add_argument("--config-dir", default="", help="Override MMS config dir to write")
    save_candidate_parser.add_argument("--plan-json", default="", help="WebUI build_config_plan JSON containing config/model_policy")
    save_candidate_parser.add_argument("--config-json", default="", help="Config JSON object to convert into DB candidates")
    save_candidate_parser.add_argument("--policy-json", default="", help="Optional model policy JSON object")
    save_candidate_parser.add_argument("--apply", action="store_true", help="Actually write candidate revisions into the preview DB")
    save_candidate_parser.add_argument("--allow-stable", action="store_true", help="Allow writing into a stable root explicitly")
    save_candidate_parser.add_argument("--json", action="store_true", help="Print the full candidate summary as JSON")
    preview_doctor_parser = subparsers.add_parser("preview-doctor", help="Read-only preview root doctor with one next action")
    preview_doctor_parser.add_argument("--config-dir", default="", help="Override MMS config dir to inspect")
    preview_doctor_parser.add_argument("--json", action="store_true", help="Print the full doctor summary as JSON")
    preview_doctor_parser.add_argument("--strict-exit", action="store_true", help="Exit non-zero unless preview root is runtime-ready")
    preview_prepare_parser = subparsers.add_parser("preview-prepare", help="Initialize, import, publish, verify, and doctor a preview root")
    preview_prepare_parser.add_argument("--config-dir", default="", help="Override MMS config dir to prepare")
    preview_prepare_parser.add_argument("--source-config-dir", default="", help="Read legacy config artifacts from this root")
    preview_prepare_parser.add_argument("--include-secrets", action="store_true", help="Also copy legacy API keys into the preview secret backend")
    preview_prepare_parser.add_argument("--json", action="store_true", help="Print the full prepare summary as JSON")
    preview_prepare_parser.add_argument("--strict-exit", action="store_true", help="Exit non-zero unless preview root is runtime-ready")
    init_root_parser = subparsers.add_parser("init-root", help="Initialize selected config root layout")
    init_root_parser.add_argument("--config-dir", default="", help="Override MMS config dir to initialize")
    init_root_parser.add_argument("--no-db", action="store_true", help="Create directories/manifest only; do not initialize SQLite")
    init_root_parser.add_argument("--allow-stable", action="store_true", help="Allow initializing a stable root explicitly")
    init_root_parser.add_argument("--json", action="store_true", help="Print init summary as JSON")
    backup_parser = subparsers.add_parser("backup-db", help="Create a SQLite backup of the registry DB")
    backup_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    backup_parser.add_argument("--backup-dir", default="", help="Override backup output dir")
    backup_parser.add_argument("--reason", default="manual", help="Audit reason for this backup")
    restore_parser = subparsers.add_parser("restore-db", help="Restore registry DB from a backup; dry-run unless --apply")
    restore_parser.add_argument("backup_path", help="Backup sqlite path to restore")
    restore_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    restore_parser.add_argument("--apply", action="store_true", help="Actually replace the target DB after pre-restore backup")
    restore_parser.add_argument("--reason", default="manual", help="Audit reason for this restore")
    legacy_report_parser = subparsers.add_parser(
        "legacy-report",
        help="Read legacy config artifacts and report import conflicts without writing DB",
    )
    legacy_report_parser.add_argument("--config-dir", default="", help="Override MMS config dir to inspect")
    legacy_report_parser.add_argument("--json", action="store_true", help="Print the full report as JSON")
    legacy_import_parser = subparsers.add_parser(
        "legacy-import",
        help="Import sanitized legacy config evidence into the preview registry DB; dry-run unless --apply",
    )
    legacy_import_parser.add_argument("--config-dir", default="", help="Override MMS config dir to import")
    legacy_import_parser.add_argument("--source-config-dir", default="", help="Read legacy config artifacts from this root while writing into --config-dir")
    legacy_import_parser.add_argument("--apply", action="store_true", help="Write sanitized import evidence into the selected preview DB")
    legacy_import_parser.add_argument("--include-secrets", action="store_true", help="Also copy legacy API keys into the preview secret backend")
    legacy_import_parser.add_argument("--allow-stable", action="store_true", help="Allow importing into a stable root explicitly")
    legacy_import_parser.add_argument("--json", action="store_true", help="Print import summary as JSON")
    refresh_parser = subparsers.add_parser(
        "refresh-sources",
        help="Import local reference snapshots as source_truth/candidate evidence",
    )
    refresh_parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Reference JSON snapshot path; may be repeated. Defaults to docs/reference/model-capability-calibration/*.json",
    )
    refresh_parser.add_argument("--if-due", action="store_true", help="Only import sources that are missing, changed, or stale")
    refresh_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS, help="Staleness threshold for --if-due")
    fetch_openrouter_parser = subparsers.add_parser(
        "fetch-openrouter-catalog",
        help="Fetch OpenRouter /api/v1/models into source_snapshot evidence",
    )
    fetch_openrouter_parser.add_argument("--url", default=OPENROUTER_MODELS_API_URL, help="OpenRouter models API URL")
    fetch_openrouter_parser.add_argument("--from-file", default="", help="Import catalog JSON from a local file instead of network")
    fetch_openrouter_parser.add_argument("--timeout", type=float, default=20.0, help="Network timeout in seconds")
    openrouter_diff_parser = subparsers.add_parser(
        "diff-openrouter-catalog",
        help="Compare latest OpenRouter catalog snapshot with calibration references",
    )
    openrouter_diff_parser.add_argument("--no-store", action="store_true", help="Do not write candidate_change rows")
    openrouter_diff_parser.add_argument("--limit", type=int, default=50, help="Max candidate changes to print")
    scheduled_parser = subparsers.add_parser(
        "scheduled-refresh",
        help="Run safe if-due registry refresh for cron/launchd/manual scheduling",
    )
    scheduled_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS)
    scheduled_parser.add_argument("--openrouter-max-age-hours", type=int, default=DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS)
    scheduled_parser.add_argument("--no-openrouter", action="store_true", help="Skip OpenRouter catalog refresh")
    scheduled_parser.add_argument("--no-network", action="store_true", help="Do not perform network fetches")
    scheduled_parser.add_argument("--openrouter-from-file", default="", help="Import OpenRouter catalog JSON from a file")
    scheduled_parser.add_argument("--dry-run", action="store_true", help="Only report due state")
    staleness_parser = subparsers.add_parser("check-staleness", help="Check source reference staleness without importing")
    staleness_parser.add_argument("--path", action="append", default=[], help="Reference JSON snapshot path; may be repeated")
    staleness_parser.add_argument("--max-age-hours", type=int, default=DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS, help="Staleness threshold")
    publish_parser = subparsers.add_parser(
        "publish-approved",
        help="Publish generated/latest-approved bundle from current local artifacts",
    )
    publish_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    publish_parser.add_argument("--refresh-sources", action="store_true", help="Refresh source snapshots before publishing")
    preview_publish_parser = subparsers.add_parser(
        "publish-preview",
        help="Publish generated/latest-approved bundle from preview DB candidates",
    )
    preview_publish_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    preview_publish_parser.add_argument("--json", action="store_true", help="Print publish summary as JSON")
    verify_parser = subparsers.add_parser("verify", help="Verify latest-approved manifest hashes")
    verify_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    verify_parser.add_argument("--manifest", default="", help="Override manifest path")
    verify_parser.add_argument("--json", action="store_true", help="Print verify summary as JSON")
    resolve_parser = subparsers.add_parser("resolve", help="Resolve one model through latest-approved capability facts")
    resolve_parser.add_argument("model")
    resolve_parser.add_argument("--config-dir", default="", help="Override MMS config dir")
    resolve_parser.add_argument("--manifest", default="", help="Override manifest path")

    args = parser.parse_args(argv)
    db_path = args.db or None
    if args.subcommand in {None, "status", "doctor"}:
        _print_status(registry_status(db_path=db_path))
        return 0
    if args.subcommand == "source-status":
        summary = model_source_status(config_dir=args.config_dir or None, command_name=command_name)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_model_source_status(summary)
        return 0
    if args.subcommand == "save-plan":
        plan = registry_v2_save_plan(config_dir=args.config_dir or None, command_name=command_name)
        if args.json:
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_registry_v2_save_plan(plan)
        return 0
    if args.subcommand == "v2-save-candidate":
        try:
            config_payload, policy_payload, credential_updates = _registry_v2_candidate_inputs_from_files(
                plan_json=args.plan_json or "",
                config_json=args.config_json or "",
                policy_json=args.policy_json or "",
            )
            summary = apply_registry_v2_save_candidate(
                config_dir=args.config_dir or None,
                config_payload=config_payload,
                policy_payload=policy_payload,
                credential_updates=credential_updates,
                db_path=db_path,
                apply=bool(args.apply),
                allow_stable=bool(args.allow_stable),
                command_name=command_name,
            )
        except mms_registry.RegistryValidationError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"error={exc}")
            return 2
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_registry_v2_save_candidate(summary)
        return 0
    if args.subcommand == "preview-doctor":
        summary = preview_doctor(config_dir=args.config_dir or None, command_name=command_name)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_preview_doctor(summary)
        return 0 if not bool(args.strict_exit) or summary.get("ready") is True else 2
    if args.subcommand == "preview-prepare":
        try:
            summary = preview_prepare(
                config_dir=args.config_dir or None,
                source_config_dir=args.source_config_dir or None,
                include_secrets=bool(args.include_secrets),
                command_name=command_name,
            )
        except mms_registry.RegistryValidationError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"error={exc}")
            return 2
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_preview_prepare(summary)
        return 0 if not bool(args.strict_exit) or summary.get("ready") is True else 2
    if args.subcommand == "init-root":
        try:
            summary = init_config_root(
                config_dir=args.config_dir or None,
                create_db=not bool(args.no_db),
                allow_stable=bool(args.allow_stable),
                command_name=command_name,
            )
        except mms_registry.RegistryValidationError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"error={exc}")
            return 2
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_init_config_root(summary)
        return 0
    if args.subcommand == "backup-db":
        summary = backup_registry_db(
            config_dir=args.config_dir or None,
            db_path=db_path,
            backup_dir=args.backup_dir or None,
            reason=args.reason or "manual",
        )
        _print_backup(summary)
        return 0
    if args.subcommand == "restore-db":
        summary = restore_registry_db(
            args.backup_path,
            config_dir=args.config_dir or None,
            db_path=db_path,
            apply=bool(args.apply),
            reason=args.reason or "manual",
        )
        _print_restore(summary)
        return 0
    if args.subcommand == "legacy-report":
        summary = legacy_import_report(config_dir=args.config_dir or None)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_legacy_import_report(summary)
        return 0
    if args.subcommand == "legacy-import":
        try:
            summary = import_legacy_config(
                config_dir=args.config_dir or None,
                source_config_dir=args.source_config_dir or None,
                db_path=db_path,
                apply=bool(args.apply),
                allow_stable=bool(args.allow_stable),
                include_secrets=bool(args.include_secrets),
                command_name=command_name,
            )
        except mms_registry.RegistryValidationError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"error={exc}")
            return 2
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_legacy_import(summary)
        return 0
    if args.subcommand == "refresh-sources":
        summary = refresh_source_snapshots(
            db_path=db_path,
            paths=args.path or None,
            if_due=bool(args.if_due),
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
        )
        _print_refresh(summary)
        return 0
    if args.subcommand == "check-staleness":
        summary = source_freshness(
            db_path=db_path,
            paths=args.path or None,
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
        )
        _print_freshness(summary)
        return 0
    if args.subcommand == "fetch-openrouter-catalog":
        summary = fetch_openrouter_catalog(
            db_path=db_path,
            url=args.url or OPENROUTER_MODELS_API_URL,
            from_file=args.from_file or None,
            timeout=float(args.timeout or 20.0),
        )
        _print_fetch_catalog(summary)
        return 0
    if args.subcommand == "diff-openrouter-catalog":
        summary = diff_openrouter_catalog(
            db_path=db_path,
            store=not bool(args.no_store),
            limit=int(args.limit or 50),
        )
        _print_openrouter_diff(summary)
        return 0
    if args.subcommand == "scheduled-refresh":
        summary = scheduled_refresh(
            db_path=db_path,
            max_age_hours=int(args.max_age_hours or DEFAULT_SOURCE_REFRESH_MAX_AGE_HOURS),
            openrouter_max_age_hours=int(args.openrouter_max_age_hours or DEFAULT_OPENROUTER_REFRESH_MAX_AGE_HOURS),
            include_openrouter=not bool(args.no_openrouter),
            no_network=bool(args.no_network),
            openrouter_from_file=args.openrouter_from_file or None,
            dry_run=bool(args.dry_run),
        )
        _print_scheduled_refresh(summary)
        return 0
    if args.subcommand == "publish-approved":
        config_dir = args.config_dir or None
        if args.refresh_sources:
            refresh_source_snapshots(db_path=db_path)
        summary = publish_approved_bundle(config_dir=config_dir, db_path=db_path)
        _print_publish(summary)
        return 0
    if args.subcommand == "publish-preview":
        try:
            summary = publish_preview_bundle(config_dir=args.config_dir or None, db_path=db_path)
        except mms_registry.RegistryValidationError as exc:
            if args.json:
                print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(f"error={exc}")
            return 2
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_publish(summary)
        return 0
    if args.subcommand == "verify":
        summary = verify_approved_bundle(config_dir=args.config_dir or None, manifest_path=args.manifest or None)
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            _print_verify(summary)
        return 0
    if args.subcommand == "resolve":
        caps = resolve_approved_model(args.model, config_dir=args.config_dir or None, manifest_path=args.manifest or None)
        _print_resolve(args.model, caps)
        return 0
    return 2


__all__ = [
    "DEFAULT_REFERENCE_DIR",
    "handle_registry_command",
    "fetch_openrouter_catalog",
    "diff_openrouter_catalog",
    "legacy_import_report",
    "import_legacy_config",
    "init_config_root",
    "model_source_status",
    "preview_doctor",
    "preview_prepare",
    "apply_registry_v2_save_candidate",
    "registry_v2_save_plan",
    "scheduled_refresh",
    "backup_registry_db",
    "publish_approved_bundle",
    "publish_preview_bundle",
    "refresh_source_snapshots",
    "registry_status",
    "restore_registry_db",
    "resolve_approved_model",
    "source_freshness",
    "verify_approved_bundle",
    "write_registry_v2_webui_secret_backend",
]
