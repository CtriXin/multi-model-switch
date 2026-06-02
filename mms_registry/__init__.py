from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from mms_registry.schema import (
    PRIVACY_BOUNDARIES,
    REVISION_CLASSES,
    REVISION_STATUSES,
    migrate as migrate_schema,
)
from mms_runtime.state_io import mms_config_root_mode, resolve_mms_config_dir


LATEST_APPROVED_SCHEMA = "mms.model_registry.latest_approved.v1"
CALIBRATION_SOURCE_KIND = "model_capability_calibration"
OPENROUTER_MODELS_SOURCE_KIND = "openrouter_models_api"
REGISTRY_DB_BACKUP_SCHEMA = "mms.registry_db_backup.v1"

_SECRET_FIELD_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "auth_header",
    "auth_token",
    "access_token",
    "refresh_token",
    "oauth",
    "password",
    "passwd",
    "credential",
    "cookie",
)
_SECRET_REFERENCE_KEYS = {
    "secret_ref",
    "secret_refs",
    "secret_fingerprint",
    "secret_hash",
    "key_fingerprint",
}
_NON_SECRET_SCHEMA_KEYS = {
    "auth_headers",
    "auth_header_names",
    "required_auth_headers",
    "header_aliases",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bsk_live_[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_MANIFEST_FILE_CONTRACT = {
    "router": {"canonical_path": "generated/model-routes.json", "sensitivity": "secret"},
    "lineup": {"canonical_path": "generated/model-routes.lineup.json", "sensitivity": "non-secret"},
    "profile": {"canonical_path": "generated/provider-profiles.generated.json", "sensitivity": "non-secret"},
    "policy": {"canonical_path": "generated/model-policy.effective.json", "sensitivity": "non-secret"},
    "capabilities": {"canonical_path": "generated/model-capabilities.approved.json", "sensitivity": "non-secret"},
}
_MANIFEST_FILE_KEYS = tuple(_MANIFEST_FILE_CONTRACT)
_OPTIONAL_MANIFEST_FILE_KEYS: tuple[str, ...] = ()
_MANIFEST_REVISION_KEYS = ("bundle_revision", "capability_revision", "route_revision", "policy_revision", "profile_revision")
APPROVED_CAPABILITIES_SCHEMA = "mms.model_capabilities.approved.v1"


class RegistryValidationError(ValueError):
    """Raised when registry data violates local safety contracts."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _source_model_count(payload: Mapping[str, Any]) -> int:
    for key in ("models", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def default_registry_db_path(config_dir: str | os.PathLike[str] | None = None, *, env: Mapping[str, str] | None = None) -> Path:
    source_env = env or os.environ
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir(source_env))
    root = root.expanduser()
    explicit_paths = []
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR"):
        raw = str(source_env.get(key) or "").strip()
        if raw:
            explicit_paths.append(Path(raw).expanduser())
    if root.name == "mms-next" or any(path.absolute() == root.absolute() for path in explicit_paths):
        return root / "registry" / "model-registry.sqlite"
    return root / "model-registry.sqlite"


def _registry_config_root(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> Path:
    if config_dir is not None:
        return Path(config_dir).expanduser()
    if db_path is not None:
        return Path(db_path).expanduser().parent
    return Path(resolve_mms_config_dir())


def _timestamp_slug(value: str | None = None) -> str:
    return re.sub(r"[^0-9]", "", value or utc_now())[:14] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _sqlite_integrity(path: Path) -> str:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return str(db.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        db.close()


def backup_registry_db(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    backup_dir: str | os.PathLike[str] | None = None,
    reason: str = "manual",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Create a self-contained SQLite backup for the local registry DB."""
    config_root = _registry_config_root(config_dir=config_dir, db_path=db_path)
    source = Path(db_path) if db_path is not None else default_registry_db_path(config_root)
    source = source.expanduser()
    backup_root = Path(backup_dir).expanduser() if backup_dir is not None else config_root / "backups" / "db"
    created_at = generated_at or utc_now()
    if not source.exists():
        return {
            "schema": REGISTRY_DB_BACKUP_SCHEMA,
            "skipped": True,
            "reason": "missing_db",
            "source_db_path": str(source),
            "backup_dir": str(backup_root),
            "created_at": created_at,
        }

    backup_root.mkdir(parents=True, exist_ok=True)
    slug = _timestamp_slug(created_at)
    fd, temp_name = tempfile.mkstemp(prefix=f"model-registry.{slug}.", suffix=".tmp.sqlite", dir=str(backup_root))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        dst = sqlite3.connect(str(temp_path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        integrity = _sqlite_integrity(temp_path)
        if integrity.lower() != "ok":
            raise RegistryValidationError(f"registry backup integrity check failed: {integrity}")
        digest = sha256_hex(temp_path.read_bytes())
        backup_path = backup_root / f"model-registry.{slug}.{digest[:12]}.sqlite"
        os.replace(temp_path, backup_path)
        os.chmod(backup_path, 0o600)
        manifest_path = backup_path.with_name(f"{backup_path.name}.json")
        manifest = {
            "schema": REGISTRY_DB_BACKUP_SCHEMA,
            "skipped": False,
            "reason": str(reason or "manual"),
            "created_at": created_at,
            "source_db_path": str(source),
            "backup_path": str(backup_path),
            "sha256": digest,
            "size_bytes": backup_path.stat().st_size,
            "integrity_check": integrity,
        }
        write_json_atomic(manifest_path, manifest)
        manifest["manifest_path"] = str(manifest_path)
        return manifest
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def restore_registry_db(
    backup_path: str | os.PathLike[str],
    *,
    config_dir: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    apply: bool = False,
    reason: str = "manual",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Restore registry DB from a backup. Dry-run unless apply=True."""
    backup = Path(backup_path).expanduser()
    if not backup.exists():
        raise RegistryValidationError(f"registry backup not found: {backup}")
    config_root = _registry_config_root(config_dir=config_dir, db_path=db_path)
    target = Path(db_path) if db_path is not None else default_registry_db_path(config_root)
    target = target.expanduser()
    if backup.resolve() == target.resolve():
        raise RegistryValidationError("backup path and target DB path are identical")
    integrity = _sqlite_integrity(backup)
    if integrity.lower() != "ok":
        raise RegistryValidationError(f"registry backup integrity check failed: {integrity}")
    summary: dict[str, Any] = {
        "schema": REGISTRY_DB_BACKUP_SCHEMA,
        "apply": bool(apply),
        "reason": str(reason or "manual"),
        "created_at": generated_at or utc_now(),
        "backup_path": str(backup),
        "target_db_path": str(target),
        "backup_sha256": sha256_hex(backup.read_bytes()),
        "backup_size_bytes": backup.stat().st_size,
        "integrity_check": integrity,
    }
    if not apply:
        summary["skipped"] = True
        summary["skip_reason"] = "dry_run_apply_required"
        return summary

    pre_restore = backup_registry_db(
        config_dir=config_root,
        db_path=target,
        reason=f"pre-restore:{reason or 'manual'}",
        generated_at=generated_at,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    copy_file_atomic(backup, target, mode=0o600)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{target}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    restored_integrity = _sqlite_integrity(target)
    if restored_integrity.lower() != "ok":
        raise RegistryValidationError(f"restored registry integrity check failed: {restored_integrity}")
    summary.update(
        {
            "skipped": False,
            "pre_restore_backup": pre_restore,
            "restored_integrity_check": restored_integrity,
            "target_sha256": sha256_hex(target.read_bytes()),
        }
    )
    return summary


def connect_registry(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else default_registry_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.execute("PRAGMA journal_mode = WAL")
    return db


def migrate(db: sqlite3.Connection) -> None:
    migrate_schema(db)


def open_registry(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    db = connect_registry(db_path)
    migrate(db)
    return db


def normalize_privacy_boundary(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in PRIVACY_BOUNDARIES:
        return "private"
    return normalized


def _validate_revision_class(value: str) -> None:
    if value not in REVISION_CLASSES:
        raise RegistryValidationError(f"unknown revision_class: {value}")


def _validate_revision_status(value: str) -> None:
    if value not in REVISION_STATUSES:
        raise RegistryValidationError(f"unknown revision status: {value}")


def _revision_hash(
    revision_id: str,
    revision_class: str,
    *,
    metadata: Mapping[str, Any] | None = None,
    privacy_boundary: str = "private",
) -> str:
    return sha256_hex(
        _canonical_json_bytes(
            {
                "revision_id": revision_id,
                "revision_class": revision_class,
                "privacy_boundary": privacy_boundary,
                "metadata": metadata or {},
            }
        )
    )


def create_revision(
    db: sqlite3.Connection,
    revision_id: str,
    revision_class: str,
    *,
    status: str = "candidate",
    revision_hash: str | None = None,
    bundle_revision: str = "",
    privacy_boundary: Any = None,
    created_at: str | None = None,
    approved_at: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    _validate_revision_class(revision_class)
    _validate_revision_status(status)
    privacy = normalize_privacy_boundary(privacy_boundary)
    if revision_hash is None:
        revision_hash = _revision_hash(
            revision_id,
            revision_class,
            metadata=metadata,
            privacy_boundary=privacy,
        )
    if not re.fullmatch(r"[0-9a-f]{64}", revision_hash):
        raise RegistryValidationError("revision_hash must be a sha256 hex digest")
    if status == "approved" and not approved_at:
        approved_at = utc_now()
    with db:
        db.execute(
            """
            INSERT INTO registry_revision(
                revision_id,
                revision_class,
                status,
                revision_hash,
                bundle_revision,
                privacy_boundary,
                created_at,
                approved_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                revision_class,
                status,
                revision_hash,
                str(bundle_revision or ""),
                privacy,
                created_at or utc_now(),
                approved_at,
                _json_text(metadata or {}),
            ),
        )
    return revision_id


def approve_revision(db: sqlite3.Connection, revision_id: str, *, actor: str = "agent") -> None:
    approved_at = utc_now()
    with db:
        cursor = db.execute(
            """
            UPDATE registry_revision
            SET status = 'approved', approved_at = ?
            WHERE revision_id = ? AND status = 'candidate'
            """,
            (approved_at, revision_id),
        )
        if cursor.rowcount != 1:
            raise RegistryValidationError(f"revision is not approvable: {revision_id}")
        db.execute(
            """
            INSERT INTO audit_log(event_type, actor, target_type, target_id, details_json)
            VALUES ('revision.approved', ?, 'registry_revision', ?, ?)
            """,
            (actor, revision_id, _json_text({"approved_at": approved_at})),
        )


def add_revision_membership(
    db: sqlite3.Connection,
    bundle_revision: str,
    member_revision: str,
    member_class: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    if member_class not in {"capability", "route", "policy", "profile"}:
        raise RegistryValidationError(f"unknown member_class: {member_class}")
    with db:
        db.execute(
            """
            INSERT OR IGNORE INTO revision_membership(bundle_revision, member_revision, member_class, metadata_json)
            VALUES (?, ?, ?, ?)
            """,
            (bundle_revision, member_revision, member_class, _json_text(metadata or {})),
        )


def _secret_key_marker(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in _SECRET_FIELD_PARTS)


def looks_like_plaintext_secret(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return False
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or text in {"<redacted>", "[redacted]", "***", "****"}:
        return False
    return any(pattern.search(text) for pattern in _SECRET_VALUE_PATTERNS)


def validate_non_secret_payload(payload: Any, *, context: str = "payload") -> None:
    """Reject obvious plaintext secrets before writing non-secret registry/export data."""

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = str(raw_key)
                normalized_key = key.lower().replace("-", "_")
                child_path = f"{path}.{key}" if path else key
                if normalized_key in _NON_SECRET_SCHEMA_KEYS:
                    walk(item, child_path)
                    continue
                if normalized_key in _SECRET_REFERENCE_KEYS:
                    if looks_like_plaintext_secret(item):
                        raise RegistryValidationError(f"{child_path} contains a plaintext secret, not a reference")
                    continue
                if _secret_key_marker(normalized_key) and item not in (None, "", [], {}):
                    raise RegistryValidationError(f"{child_path} is a secret-looking field in non-secret data")
                walk(item, child_path)
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
            return
        if looks_like_plaintext_secret(value):
            raise RegistryValidationError(f"{path} contains a plaintext secret-looking value")

    walk(payload, context)


def insert_route_group(
    db: sqlite3.Connection,
    route_group_id: str,
    route_revision_id: str,
    *,
    logical_model: str = "",
    display_name: str = "",
    privacy_boundary: Any = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    validate_non_secret_payload(metadata or {}, context=f"route_group.{route_group_id}.metadata")
    with db:
        db.execute(
            """
            INSERT INTO route_group(
                route_group_id,
                route_revision_id,
                logical_model,
                display_name,
                privacy_boundary,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                route_group_id,
                route_revision_id,
                logical_model,
                display_name,
                normalize_privacy_boundary(privacy_boundary),
                _json_text(metadata or {}),
            ),
        )
    return route_group_id


def insert_provider_route(
    db: sqlite3.Connection,
    route_id: str,
    route_group_id: str,
    route_revision_id: str,
    *,
    provider_id: str,
    wire_model_id: str,
    priority: int = 0,
    anthropic_base_url: str = "",
    openai_base_url: str = "",
    secret_ref: str = "",
    privacy_boundary: Any = None,
    validation_state: str = "unknown",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    route_payload = {
        "provider_id": provider_id,
        "wire_model_id": wire_model_id,
        "anthropic_base_url": anthropic_base_url,
        "openai_base_url": openai_base_url,
        "validation_state": validation_state,
        "metadata": metadata or {},
    }
    validate_non_secret_payload(route_payload, context=f"provider_route.{route_id}")
    if secret_ref and looks_like_plaintext_secret(secret_ref):
        raise RegistryValidationError(f"provider_route.{route_id}.secret_ref contains a plaintext secret")
    with db:
        db.execute(
            """
            INSERT INTO provider_route(
                route_id,
                route_group_id,
                route_revision_id,
                provider_id,
                wire_model_id,
                priority,
                anthropic_base_url,
                openai_base_url,
                secret_ref,
                privacy_boundary,
                validation_state,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                route_id,
                route_group_id,
                route_revision_id,
                provider_id,
                wire_model_id,
                int(priority),
                anthropic_base_url or "",
                openai_base_url or "",
                secret_ref or "",
                normalize_privacy_boundary(privacy_boundary),
                validation_state or "unknown",
                _json_text(metadata or {}),
            ),
        )
    return route_id


def record_tombstone_event(
    db: sqlite3.Connection,
    *,
    target_type: str,
    target_id: str,
    reason: str,
    last_approved_revision: str,
    actor: str = "agent",
    details: Mapping[str, Any] | None = None,
) -> int:
    if not reason.strip():
        raise RegistryValidationError("tombstone reason is required")
    with db:
        cursor = db.execute(
            """
            INSERT INTO tombstone_event(
                target_type,
                target_id,
                actor,
                reason,
                last_approved_revision,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                target_type,
                target_id,
                actor,
                reason,
                last_approved_revision,
                _json_text(details or {}),
            ),
        )
    return int(cursor.lastrowid)


def import_source_snapshot(
    db: sqlite3.Connection,
    source_path: str | os.PathLike[str],
    *,
    source_kind: str = CALIBRATION_SOURCE_KIND,
    captured_at: str | None = None,
) -> dict[str, Any]:
    path = Path(source_path)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    content_hash = sha256_hex(raw)
    models = payload.get("models")
    model_rows = models if isinstance(models, list) else []
    captured = captured_at or utc_now()

    with db:
        db.execute(
            """
            INSERT OR IGNORE INTO source_snapshot(
                source_kind,
                source_path,
                captured_at,
                content_hash,
                schema,
                model_count,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_kind,
                str(path),
                captured,
                content_hash,
                str(payload.get("schema") or ""),
                len(model_rows),
                _json_text(payload),
            ),
        )
        snapshot = db.execute(
            """
            SELECT snapshot_id
            FROM source_snapshot
            WHERE source_kind = ? AND source_path = ? AND content_hash = ?
            """,
            (source_kind, str(path), content_hash),
        ).fetchone()
        if snapshot is None:
            raise RegistryValidationError("source_snapshot insert failed")
        snapshot_id = int(snapshot["snapshot_id"])
        db.execute(
            """
            INSERT INTO source_check(
                source_kind,
                source_path,
                checked_at,
                content_hash,
                snapshot_id,
                status,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'ok', ?)
            ON CONFLICT(source_kind, source_path) DO UPDATE SET
                checked_at = excluded.checked_at,
                content_hash = excluded.content_hash,
                snapshot_id = excluded.snapshot_id,
                status = excluded.status,
                metadata_json = excluded.metadata_json
            """,
            (
                source_kind,
                str(path),
                captured,
                content_hash,
                snapshot_id,
                _json_text({"schema": str(payload.get("schema") or ""), "model_count": len(model_rows)}),
            ),
        )
        fact_count = 0
        for model in model_rows:
            if not isinstance(model, Mapping):
                continue
            alias = str(model.get("alias") or model.get("canonical_model_id") or model.get("routed_model_id") or "").strip()
            if not alias:
                continue
            canonical = str(model.get("canonical_model_id") or model.get("routed_model_id") or alias)
            metadata = {
                "provider_id": model.get("provider_id") or "",
                "alias_status": model.get("alias_status") or "",
                "confidence": model.get("confidence") or "",
            }
            db.execute(
                """
                INSERT INTO model_identity(model_key, canonical_model_id, alias, vendor, family, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_key) DO UPDATE SET
                    canonical_model_id = excluded.canonical_model_id,
                    alias = excluded.alias,
                    vendor = excluded.vendor,
                    family = excluded.family,
                    metadata_json = excluded.metadata_json
                """,
                (
                    alias,
                    canonical,
                    alias,
                    str(model.get("vendor") or ""),
                    str(model.get("family") or ""),
                    _json_text(metadata),
                ),
            )
            for fact_key in (
                "official_context_window_tokens",
                "official_max_output_tokens",
                "supports_vision",
                "supports_thinking",
                "one_million_context",
                "expected_protocol",
                "thinking_control",
                "provider_catalog_references",
                "evidence",
            ):
                if fact_key not in model:
                    continue
                source_layer = "provider_catalog" if fact_key == "provider_catalog_references" else "official"
                if fact_key == "expected_protocol":
                    source_layer = "runtime"
                db.execute(
                    """
                    INSERT INTO model_fact(
                        model_key,
                        source_snapshot_id,
                        fact_key,
                        fact_value_json,
                        confidence,
                        source_layer
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_snapshot_id, model_key, fact_key) DO UPDATE SET
                        fact_value_json = excluded.fact_value_json,
                        confidence = excluded.confidence,
                        source_layer = excluded.source_layer
                    """,
                    (
                        alias,
                        snapshot_id,
                        fact_key,
                        _json_text(model.get(fact_key)),
                        str(model.get("confidence") or ""),
                        source_layer,
                    ),
                )
                fact_count += 1

    return {
        "snapshot_id": snapshot_id,
        "source_kind": source_kind,
        "source_path": str(path),
        "captured_at": captured,
        "content_hash": content_hash,
        "model_count": len(model_rows),
        "fact_count": fact_count,
    }


def import_raw_source_payload(
    db: sqlite3.Connection,
    payload: Mapping[str, Any],
    *,
    source_kind: str,
    source_path: str,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """Store non-secret raw source evidence without promoting runtime facts."""
    if not source_kind:
        raise RegistryValidationError("source_kind is required")
    if not source_path:
        raise RegistryValidationError("source_path is required")
    validate_non_secret_payload(payload, context=f"source_payload:{source_kind}")
    captured = captured_at or utc_now()
    payload_text = _json_text(payload)
    content_hash = sha256_hex(payload_text)
    model_count = _source_model_count(payload)

    with db:
        db.execute(
            """
            INSERT OR IGNORE INTO source_snapshot(
                source_kind,
                source_path,
                captured_at,
                content_hash,
                schema,
                model_count,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_kind,
                source_path,
                captured,
                content_hash,
                str(payload.get("schema") or ""),
                model_count,
                payload_text,
            ),
        )
        snapshot = db.execute(
            """
            SELECT snapshot_id
            FROM source_snapshot
            WHERE source_kind = ? AND source_path = ? AND content_hash = ?
            """,
            (source_kind, source_path, content_hash),
        ).fetchone()
        if snapshot is None:
            raise RegistryValidationError("source_snapshot insert failed")
        snapshot_id = int(snapshot["snapshot_id"])
        db.execute(
            """
            INSERT INTO source_check(
                source_kind,
                source_path,
                checked_at,
                content_hash,
                snapshot_id,
                status,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, 'ok', ?)
            ON CONFLICT(source_kind, source_path) DO UPDATE SET
                checked_at = excluded.checked_at,
                content_hash = excluded.content_hash,
                snapshot_id = excluded.snapshot_id,
                status = excluded.status,
                metadata_json = excluded.metadata_json
            """,
            (
                source_kind,
                source_path,
                captured,
                content_hash,
                snapshot_id,
                _json_text({"model_count": model_count}),
            ),
        )
    return {
        "snapshot_id": snapshot_id,
        "source_kind": source_kind,
        "source_path": source_path,
        "captured_at": captured,
        "content_hash": content_hash,
        "model_count": model_count,
        "fact_count": 0,
    }


def record_candidate_changes(
    db: sqlite3.Connection,
    changes: list[Mapping[str, Any]],
    *,
    source_snapshot_id: int,
    baseline_snapshot_id: int,
) -> dict[str, Any]:
    """Persist provider/official source diffs as candidate evidence only."""
    source_id = int(source_snapshot_id)
    baseline_id = int(baseline_snapshot_id)
    with db:
        db.execute(
            """
            UPDATE candidate_change
            SET status = 'superseded'
            WHERE source_snapshot_id = ? AND baseline_snapshot_id = ? AND status = 'candidate'
            """,
            (source_id, baseline_id),
        )
        recorded = 0
        for change in changes:
            field_key = str(change.get("field_key") or "").strip()
            if not field_key:
                continue
            old_value = change.get("old_value")
            new_value = change.get("new_value")
            validate_non_secret_payload(old_value, context=f"candidate_change.old.{field_key}")
            validate_non_secret_payload(new_value, context=f"candidate_change.new.{field_key}")
            db.execute(
                """
                INSERT INTO candidate_change(
                    source_snapshot_id,
                    baseline_snapshot_id,
                    change_kind,
                    model_key,
                    provider_model_id,
                    field_key,
                    old_value_json,
                    new_value_json,
                    status,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)
                ON CONFLICT(source_snapshot_id, baseline_snapshot_id, model_key, provider_model_id, field_key)
                DO UPDATE SET
                    change_kind = excluded.change_kind,
                    old_value_json = excluded.old_value_json,
                    new_value_json = excluded.new_value_json,
                    status = 'candidate',
                    metadata_json = excluded.metadata_json
                """,
                (
                    source_id,
                    baseline_id,
                    str(change.get("change_kind") or "provider_catalog_changed"),
                    str(change.get("model_key") or ""),
                    str(change.get("provider_model_id") or ""),
                    field_key,
                    _json_text(old_value),
                    _json_text(new_value),
                    _json_text(change.get("metadata") or {}),
                ),
            )
            recorded += 1
    return {
        "source_snapshot_id": source_id,
        "baseline_snapshot_id": baseline_id,
        "recorded_count": recorded,
    }


def _parse_bundle_json_object(raw: bytes, *, path: Path, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RegistryValidationError(f"manifest file is not valid JSON for {name}: {path}") from exc
    if not isinstance(payload, dict):
        raise RegistryValidationError(f"manifest file must be a JSON object for {name}: {path}")
    return payload


def _read_file_hash(path: Path, *, sensitivity: str, name: str) -> str:
    raw = path.read_bytes()
    payload = _parse_bundle_json_object(raw, path=path, name=name)
    if sensitivity != "secret":
        validate_non_secret_payload(payload, context=str(path))
    return sha256_hex(raw)


def _manifest_file_entry(name: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(spec["path"])
    expected = _MANIFEST_FILE_CONTRACT.get(name)
    if expected is None:
        raise RegistryValidationError(f"unexpected manifest file entry: {name}")
    sensitivity = str(spec.get("sensitivity") or "non-secret")
    if sensitivity not in {"secret", "non-secret"}:
        raise RegistryValidationError(f"unknown sensitivity for {name}: {sensitivity}")
    if sensitivity != expected["sensitivity"]:
        raise RegistryValidationError(f"unexpected sensitivity for {name}: {sensitivity}")
    canonical_path = str(spec.get("canonical_path") or f"generated/{path.name}")
    if canonical_path != expected["canonical_path"]:
        raise RegistryValidationError(f"unexpected canonical_path for {name}: {canonical_path}")
    _validate_manifest_canonical_path(canonical_path, name=name)
    return {
        "canonical_path": canonical_path,
        "legacy_alias_path": str(spec.get("legacy_alias_path") or ""),
        "sha256": str(spec.get("sha256") or _read_file_hash(path, sensitivity=sensitivity, name=name)),
        "sensitivity": sensitivity,
        "legacy_alias_compat": bool(spec.get("legacy_alias_compat", False)),
    }


def build_latest_approved_bundle_manifest(
    *,
    bundle_revision: str,
    capability_revision: str,
    route_revision: str,
    policy_revision: str,
    profile_revision: str,
    files: Mapping[str, Mapping[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    missing = [key for key in _MANIFEST_FILE_KEYS if key not in files]
    if missing:
        raise RegistryValidationError(f"manifest files missing: {', '.join(missing)}")
    unexpected = sorted(str(key) for key in files if key not in _MANIFEST_FILE_CONTRACT)
    if unexpected:
        raise RegistryValidationError(f"unexpected manifest files: {', '.join(unexpected)}")
    revisions = {
        "bundle_revision": bundle_revision,
        "capability_revision": capability_revision,
        "route_revision": route_revision,
        "policy_revision": policy_revision,
        "profile_revision": profile_revision,
    }
    missing_revisions = [key for key, value in revisions.items() if not str(value or "").strip()]
    if missing_revisions:
        raise RegistryValidationError(f"manifest revisions missing: {', '.join(missing_revisions)}")
    manifest_files = {name: _manifest_file_entry(name, files[name]) for name in _MANIFEST_FILE_KEYS}
    for name in _OPTIONAL_MANIFEST_FILE_KEYS:
        if name in files:
            manifest_files[name] = _manifest_file_entry(name, files[name])
    manifest = {
        "schema": LATEST_APPROVED_SCHEMA,
        "bundle_revision": bundle_revision,
        "model_registry_revision": bundle_revision,
        "capability_revision": capability_revision,
        "route_revision": route_revision,
        "policy_revision": policy_revision,
        "profile_revision": profile_revision,
        "generated_at": generated_at or utc_now(),
        "files": manifest_files,
    }
    validate_non_secret_payload(manifest, context="latest_approved_manifest")
    return manifest


def write_json_atomic(path: str | os.PathLike[str], payload: Mapping[str, Any], *, mode: int = 0o600) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        os.chmod(target, mode)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def export_latest_approved_bundle_manifest(
    output_path: str | os.PathLike[str],
    *,
    bundle_revision: str,
    capability_revision: str,
    route_revision: str,
    policy_revision: str,
    profile_revision: str,
    files: Mapping[str, Mapping[str, Any]],
    generated_at: str | None = None,
    db: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    manifest = build_latest_approved_bundle_manifest(
        bundle_revision=bundle_revision,
        capability_revision=capability_revision,
        route_revision=route_revision,
        policy_revision=policy_revision,
        profile_revision=profile_revision,
        files=files,
        generated_at=generated_at,
    )
    write_json_atomic(output_path, manifest)
    if db is not None:
        manifest_text = _json_text(manifest)
        with db:
            db.execute(
                """
                INSERT INTO export_snapshot(
                    bundle_revision,
                    generated_at,
                    manifest_path,
                    manifest_hash,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    bundle_revision,
                    manifest["generated_at"],
                    str(output_path),
                    sha256_hex(manifest_text),
                    manifest_text,
                ),
            )
    return manifest


def _write_bytes_atomic(path: str | os.PathLike[str], data: bytes, *, mode: int = 0o600) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        os.chmod(target, mode)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def copy_file_atomic(src: str | os.PathLike[str], dst: str | os.PathLike[str], *, mode: int = 0o600) -> None:
    src_path = Path(src)
    dst_path = Path(dst)
    data = src_path.read_bytes()
    _write_bytes_atomic(dst_path, data, mode=mode)


def _deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(override, Mapping):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    if override is None:
        return base
    return override


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_effective_provider_profiles_payload(config_root: Path) -> dict[str, Any]:
    """Build the non-secret consumer-facing profile export from builtin + overlays."""
    repo_root = Path(__file__).resolve().parent
    payload: dict[str, Any] = _read_json_mapping(repo_root / "config" / "provider-profiles.json")
    if not payload:
        payload = {"schema_version": 1, "profiles": {}}
    for basename in ("provider-profiles.json", "model-profiles.json"):
        overlay = _read_json_mapping(config_root / basename)
        if overlay:
            payload = _deep_merge(payload, overlay)
    if not isinstance(payload.get("profiles"), dict):
        payload["profiles"] = {}
    validate_non_secret_payload(payload, context="effective_provider_profiles")
    return payload


def _json_loads_safe(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def build_approved_capabilities_payload(
    db: sqlite3.Connection,
    *,
    capability_revision: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a non-secret approved capability export from registry facts."""
    rows = db.execute(
        """
        SELECT
            mi.model_key,
            mi.canonical_model_id,
            mi.alias,
            mi.vendor,
            mi.family,
            mf.fact_key,
            mf.fact_value_json,
            mf.confidence,
            mf.source_layer
        FROM model_identity mi
        LEFT JOIN model_fact mf ON mf.model_key = mi.model_key
        ORDER BY lower(mi.model_key), lower(mf.fact_key), mf.source_snapshot_id, mf.fact_id
        """
    ).fetchall()
    by_model: dict[str, dict[str, Any]] = {}
    for row in rows:
        model_key = str(row["model_key"] or "").strip()
        if not model_key:
            continue
        item = by_model.setdefault(
            model_key,
            {
                "alias": str(row["alias"] or model_key),
                "model": model_key,
                "canonical_model_id": str(row["canonical_model_id"] or model_key),
                "vendor": str(row["vendor"] or ""),
                "family": str(row["family"] or ""),
                "source_layers": {},
                "confidence_by_fact": {},
            },
        )
        fact_key = str(row["fact_key"] or "").strip()
        if not fact_key:
            continue
        item[fact_key] = _json_loads_safe(row["fact_value_json"])
        item["source_layers"][fact_key] = str(row["source_layer"] or "")
        item["confidence_by_fact"][fact_key] = str(row["confidence"] or "")

    payload = {
        "schema": APPROVED_CAPABILITIES_SCHEMA,
        "capability_revision": capability_revision,
        "generated_at": generated_at or utc_now(),
        "models": list(by_model.values()),
    }
    validate_non_secret_payload(payload, context="approved_capabilities")
    return payload


def _config_file(config_dir: Path, name: str) -> Path:
    path = config_dir / name
    if not path.exists():
        raise RegistryValidationError(f"required config artifact is missing: {path}")
    return path


def _revision_slug(prefix: str, content_hash: str, *, generated_at: str) -> str:
    stamp = re.sub(r"[^0-9]", "", generated_at)[:14] or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{stamp}_{content_hash[:10]}"


def _create_revision_for_publish(
    db: sqlite3.Connection,
    revision_id: str,
    revision_class: str,
    *,
    revision_hash: str,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    with db:
        db.execute(
            """
            INSERT OR IGNORE INTO registry_revision(
                revision_id,
                revision_class,
                status,
                revision_hash,
                bundle_revision,
                privacy_boundary,
                created_at,
                metadata_json
            )
            VALUES (?, ?, 'candidate', ?, '', 'private', ?, ?)
            """,
            (revision_id, revision_class, revision_hash, utc_now(), _json_text(metadata or {})),
        )


def _approve_if_candidate(db: sqlite3.Connection, revision_id: str, *, actor: str) -> None:
    row = db.execute("SELECT status FROM registry_revision WHERE revision_id = ?", (revision_id,)).fetchone()
    if row is None:
        raise RegistryValidationError(f"revision not found: {revision_id}")
    if str(row["status"]) == "approved":
        return
    approve_revision(db, revision_id, actor=actor)


def _metadata_dict(value: Any) -> dict[str, Any]:
    parsed = _json_loads_safe(str(value or "{}"))
    return parsed if isinstance(parsed, dict) else {}


_PREVIEW_ROUTE_SOURCE_LABELS = {
    "legacy-import": "registry-preview-legacy-import",
    "registry-v2-save-candidate": "registry-preview-v2-save-candidate",
}


def _latest_preview_route_revision(db: sqlite3.Connection) -> tuple[sqlite3.Row, str]:
    rows = db.execute(
        """
        SELECT revision_id, status, metadata_json
        FROM registry_revision
        WHERE revision_class = 'route' AND status IN ('candidate', 'approved')
        ORDER BY created_at DESC, revision_id DESC
        """
    ).fetchall()
    for row in rows:
        metadata = _metadata_dict(row["metadata_json"])
        source = str(metadata.get("source") or "")
        if source in _PREVIEW_ROUTE_SOURCE_LABELS:
            return row, source
    raise RegistryValidationError("no preview route candidate found; run legacy-import --apply or v2-save-candidate --apply first")


def _latest_legacy_import_route_revision(db: sqlite3.Connection) -> sqlite3.Row:
    row, source = _latest_preview_route_revision(db)
    if source == "legacy-import":
        return row
    raise RegistryValidationError("latest preview route candidate is not a legacy import candidate")


def _latest_revision_payload_for_source(
    db: sqlite3.Connection,
    revision_class: str,
    source: str,
    *,
    candidate_id: str = "",
) -> tuple[str, dict[str, Any]]:
    rows = db.execute(
        """
        SELECT revision_id, metadata_json
        FROM registry_revision
        WHERE revision_class = ? AND status IN ('candidate', 'approved')
        ORDER BY created_at DESC, revision_id DESC
        """,
        (revision_class,),
    ).fetchall()
    for row in rows:
        metadata = _metadata_dict(row["metadata_json"])
        if str(metadata.get("source") or "") != source:
            continue
        if candidate_id and str(metadata.get("candidate_id") or "") != candidate_id:
            continue
        payload = metadata.get("payload") if isinstance(metadata.get("payload"), dict) else {}
        if payload:
            return str(row["revision_id"] or ""), payload
    return "", {}


def _legacy_route_role_rank(value: Any) -> int:
    role = str(value or "auto").strip().lower()
    return {"primary": 0, "auto": 1, "fallback": 2}.get(role, 1)


def _route_leaf_from_provider_row(row: sqlite3.Row, secret_values: Mapping[str, str] | None = None) -> dict[str, Any]:
    secrets = secret_values or {}
    secret_ref = str(row["secret_ref"] or "").strip()
    leaf = {
        "provider_id": str(row["provider_id"] or ""),
        "anthropic_base_url": str(row["anthropic_base_url"] or ""),
        "openai_base_url": str(row["openai_base_url"] or ""),
        "api_key": str(secrets.get(secret_ref) or ""),
        "model_id": str(row["wire_model_id"] or row["logical_model"] or ""),
    }
    if secret_ref:
        leaf["secret_ref"] = secret_ref
    return leaf


def _lineup_leaf_from_route_leaf(leaf: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": str(leaf.get("provider_id") or ""),
        "model_id": str(leaf.get("model_id") or ""),
    }


def _build_preview_bundle_payloads_from_route_revision(
    db: sqlite3.Connection,
    *,
    route_revision_id: str,
    generated_at: str,
    secret_values: Mapping[str, str] | None = None,
    source_label: str = "registry-preview-legacy-import",
    policy_payload: Mapping[str, Any] | None = None,
    profile_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT
            rg.logical_model,
            rg.display_name,
            pr.route_id,
            pr.provider_id,
            pr.wire_model_id,
            pr.priority,
            pr.anthropic_base_url,
            pr.openai_base_url,
            pr.secret_ref,
            pr.metadata_json
        FROM provider_route pr
        JOIN route_group rg ON rg.route_group_id = pr.route_group_id
        WHERE pr.route_revision_id = ?
        ORDER BY lower(rg.logical_model), pr.route_id
        """,
        (route_revision_id,),
    ).fetchall()
    if not rows:
        raise RegistryValidationError(f"route revision has no provider routes: {route_revision_id}")

    by_model: dict[str, list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    for row in rows:
        metadata = _metadata_dict(row["metadata_json"])
        model = str(row["logical_model"] or row["wire_model_id"] or "").strip()
        if not model:
            continue
        leaf = _route_leaf_from_provider_row(row, secret_values)
        sort_key = (
            _legacy_route_role_rank(metadata.get("role")),
            -int(row["priority"] or 0),
            str(row["provider_id"] or ""),
            str(row["route_id"] or ""),
        )
        by_model.setdefault(model, []).append((sort_key, leaf, metadata))
        provider_id = str(row["provider_id"] or "").strip()
        if provider_id and provider_id not in profiles:
            protocols = metadata.get("protocols") if isinstance(metadata.get("protocols"), list) else []
            profiles[provider_id] = {
                "source": "registry-preview-legacy-import",
                "protocols": [str(item) for item in protocols if str(item or "").strip()],
                "models_endpoint": str(metadata.get("models_endpoint") or ""),
            }

    routes: dict[str, dict[str, Any]] = {}
    lineup_routes: dict[str, dict[str, Any]] = {}
    for model in sorted(by_model):
        ordered = [item for _, item, _ in sorted(by_model[model], key=lambda value: value[0])]
        routes[model] = {"primary": ordered[0], "fallbacks": ordered[1:]}
        lineup_routes[model] = {
            "primary": _lineup_leaf_from_route_leaf(ordered[0]),
            "fallbacks": [_lineup_leaf_from_route_leaf(item) for item in ordered[1:]],
        }

    leaves = [info["primary"] for info in routes.values()]
    for info in routes.values():
        leaves.extend(info.get("fallbacks") or [])
    missing_api_key_count = sum(1 for item in leaves if not str(item.get("api_key") or "").strip())
    missing_base_url_count = sum(
        1
        for item in leaves
        if not str(item.get("anthropic_base_url") or "").strip()
        and not str(item.get("openai_base_url") or "").strip()
    )
    runtime_ready = bool(leaves) and missing_api_key_count == 0 and missing_base_url_count == 0
    not_ready_reasons = []
    if missing_api_key_count:
        not_ready_reasons.append("missing plaintext secrets in preview secret backend")
    if missing_base_url_count:
        not_ready_reasons.append("missing route base URLs")
    router_payload = {
        "version": 1,
        "generated_at": generated_at,
        "source": source_label,
        "route_revision": route_revision_id,
        "runtime_ready": runtime_ready,
        "runtime_ready_reason": "" if runtime_ready else "; ".join(not_ready_reasons),
        "routes": routes,
    }
    lineup_payload = {
        "version": 1,
        "generated_at": generated_at,
        "source": source_label,
        "source_routes_hash": sha256_hex(_canonical_json_bytes({"version": 1, "routes": routes})),
        "routes": lineup_routes,
    }
    if policy_payload:
        effective_policy_payload = dict(policy_payload)
        effective_policy_payload.setdefault("version", 1)
        effective_policy_payload["generated_at"] = generated_at
        effective_policy_payload["source"] = source_label
    else:
        effective_policy_payload = {
            "version": 1,
            "generated_at": generated_at,
            "source": source_label,
            "models": {model: {"visible": True, "source": source_label} for model in sorted(routes)},
        }
    if profile_payload:
        raw_profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), Mapping) else {}
        raw_provider = profile_payload.get("provider") if isinstance(profile_payload.get("provider"), Mapping) else {}
        effective_profile_payload = {
            "schema_version": 1,
            "generated_at": generated_at,
            "source": source_label,
            "provider": dict(raw_provider),
            "profiles": dict(raw_profiles),
        }
        if not effective_profile_payload["provider"] and str(profile_payload.get("default_provider") or "").strip():
            effective_profile_payload["provider"] = {"default": str(profile_payload.get("default_provider") or "").strip()}
    else:
        effective_profile_payload = {
            "schema_version": 1,
            "generated_at": generated_at,
            "source": source_label,
            "provider": {},
            "profiles": profiles,
        }
    validate_non_secret_payload(lineup_payload, context="preview_lineup")
    validate_non_secret_payload(effective_policy_payload, context="preview_policy")
    validate_non_secret_payload(effective_profile_payload, context="preview_profile")
    return {
        "router": router_payload,
        "lineup": lineup_payload,
        "policy": effective_policy_payload,
        "profile": effective_profile_payload,
        "route_count": len(routes),
        "provider_route_count": len(rows),
        "runtime_ready": runtime_ready,
        "missing_api_key_count": missing_api_key_count,
        "missing_base_url_count": missing_base_url_count,
    }


def _load_preview_secret_values(config_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (config_root / "secrets" / "legacy-secrets.json", config_root / "secrets" / "webui-secrets.json"):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload.get("secrets") if isinstance(payload.get("secrets"), list) else []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            ref = str(item.get("secret_ref") or "").strip()
            value = str(item.get("value") or "").strip()
            if ref and value:
                values[ref] = value
    return values


def publish_latest_approved_bundle_from_legacy_candidates(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    generated_at: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Publish a preview latest-approved bundle from DB preview candidates.

    This is an explicit preview bridge toward DB truth. It does not read root
    legacy artifacts and it resolves plaintext secrets only from the selected
    preview secret backend; otherwise router entries carry `secret_ref`.
    """
    config_root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    generated_dir = config_root / "generated"
    generated = generated_at or utc_now()
    db = open_registry(db_path or default_registry_db_path(config_root))
    try:
        route_revision_row, preview_source = _latest_preview_route_revision(db)
        source_label = _PREVIEW_ROUTE_SOURCE_LABELS.get(preview_source, "registry-preview")
        route_revision = str(route_revision_row["revision_id"] or "")
        route_metadata = _metadata_dict(route_revision_row["metadata_json"])
        candidate_id = str(route_metadata.get("candidate_id") or "")
        policy_revision_override, policy_payload_override = _latest_revision_payload_for_source(
            db,
            "policy",
            preview_source,
            candidate_id=candidate_id,
        )
        profile_revision_override, profile_payload_override = _latest_revision_payload_for_source(
            db,
            "profile",
            preview_source,
            candidate_id=candidate_id,
        )
        if preview_source == "registry-v2-save-candidate" and candidate_id and (not policy_revision_override or not profile_revision_override):
            raise RegistryValidationError(
                f"registry v2 candidate {candidate_id} is missing matching policy/profile revisions"
            )
        payloads = _build_preview_bundle_payloads_from_route_revision(
            db,
            route_revision_id=route_revision,
            generated_at=generated,
            secret_values=_load_preview_secret_values(config_root),
            source_label=source_label,
            policy_payload=policy_payload_override,
            profile_payload=profile_payload_override,
        )
        output_files = {
            "router": generated_dir / "model-routes.json",
            "lineup": generated_dir / "model-routes.lineup.json",
            "profile": generated_dir / "provider-profiles.generated.json",
            "policy": generated_dir / "model-policy.effective.json",
            "capabilities": generated_dir / "model-capabilities.approved.json",
        }
        for name in ("router", "lineup", "profile", "policy"):
            write_json_atomic(output_files[name], payloads[name])

        capability_revision_seed = sha256_hex(
            _canonical_json_bytes(
                {
                    "source": source_label,
                    "preview_source": preview_source,
                    "route_revision": route_revision,
                    "route_count": payloads["route_count"],
                    "generated_at": generated,
                }
            )
        )
        capability_revision = _revision_slug("cap", capability_revision_seed, generated_at=generated)
        capabilities_payload = build_approved_capabilities_payload(
            db,
            capability_revision=capability_revision,
            generated_at=generated,
        )
        write_json_atomic(output_files["capabilities"], capabilities_payload)

        file_hashes = {name: sha256_hex(path.read_bytes()) for name, path in output_files.items()}
        policy_revision = policy_revision_override or _revision_slug("policy", file_hashes["policy"], generated_at=generated)
        profile_revision = profile_revision_override or _revision_slug("profile", file_hashes["profile"], generated_at=generated)
        bundle_hash = sha256_hex(
            _canonical_json_bytes(
                {
                    "source": source_label,
                    "preview_source": preview_source,
                    "capability_revision": capability_revision,
                    "route_revision": route_revision,
                    "policy_revision": policy_revision,
                    "profile_revision": profile_revision,
                    "file_hashes": file_hashes,
                }
            )
        )
        bundle_revision = _revision_slug("bundle", bundle_hash, generated_at=generated)

        revisions_to_create = [(capability_revision, "capability", file_hashes["capabilities"])]
        if not policy_revision_override:
            revisions_to_create.append((policy_revision, "policy", file_hashes["policy"]))
        if not profile_revision_override:
            revisions_to_create.append((profile_revision, "profile", file_hashes["profile"]))
        revisions_to_create.append((bundle_revision, "bundle", bundle_hash))
        for revision_id, revision_class, revision_hash in revisions_to_create:
            _create_revision_for_publish(
                db,
                revision_id,
                revision_class,
                revision_hash=revision_hash,
                metadata={"source": source_label, "preview_source": preview_source, "publish_generated_at": generated},
            )

        for revision_id, revision_class in (
            (capability_revision, "capability"),
            (route_revision, "route"),
            (policy_revision, "policy"),
            (profile_revision, "profile"),
        ):
            add_revision_membership(
                db,
                bundle_revision,
                revision_id,
                revision_class,
                metadata={"source": source_label, "preview_source": preview_source, "publish_generated_at": generated},
            )

        for revision_id in (capability_revision, route_revision, policy_revision, profile_revision, bundle_revision):
            _approve_if_candidate(db, revision_id, actor=actor)

        manifest_path = generated_dir / "model-registry.latest-approved.json"
        manifest = export_latest_approved_bundle_manifest(
            manifest_path,
            bundle_revision=bundle_revision,
            capability_revision=capability_revision,
            route_revision=route_revision,
            policy_revision=policy_revision,
            profile_revision=profile_revision,
            files={
                "router": {
                    "path": output_files["router"],
                    "canonical_path": "generated/model-routes.json",
                    "legacy_alias_path": "model-routes.json",
                    "sensitivity": "secret",
                    "legacy_alias_compat": True,
                },
                "lineup": {
                    "path": output_files["lineup"],
                    "canonical_path": "generated/model-routes.lineup.json",
                    "legacy_alias_path": "model-routes.lineup.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": True,
                },
                "profile": {
                    "path": output_files["profile"],
                    "canonical_path": "generated/provider-profiles.generated.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": False,
                },
                "policy": {
                    "path": output_files["policy"],
                    "canonical_path": "generated/model-policy.effective.json",
                    "legacy_alias_path": "model-policy.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": True,
                },
                "capabilities": {
                    "path": output_files["capabilities"],
                    "canonical_path": "generated/model-capabilities.approved.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": False,
                },
            },
            generated_at=generated,
            db=db,
        )
        with db:
            db.execute(
                """
                INSERT INTO audit_log(event_type, actor, target_type, target_id, details_json)
                VALUES ('preview_bundle.published', ?, 'registry_revision', ?, ?)
                """,
                (
                    actor,
                    bundle_revision,
                    _json_text(
                        {
                            "manifest_path": str(manifest_path),
                            "route_revision": route_revision,
                            "preview_source": preview_source,
                            "candidate_id": candidate_id,
                            "runtime_ready": False,
                        }
                    ),
                ),
            )
        return {
            "schema": "mms.preview_bundle_publish.v1",
            "source": source_label,
            "preview_source": preview_source,
            "candidate_id": candidate_id,
            "manifest": manifest,
            "manifest_path": str(manifest_path),
            "generated_dir": str(generated_dir),
            "bundle_revision": bundle_revision,
            "capability_revision": capability_revision,
            "route_revision": route_revision,
            "policy_revision": policy_revision,
            "profile_revision": profile_revision,
            "route_count": payloads["route_count"],
            "provider_route_count": payloads["provider_route_count"],
            "runtime_ready": payloads["runtime_ready"],
            "runtime_ready_reason": str((payloads.get("router") or {}).get("runtime_ready_reason") or ""),
            "missing_api_key_count": payloads["missing_api_key_count"],
            "missing_base_url_count": payloads["missing_base_url_count"],
            "files": {name: str(path) for name, path in output_files.items()},
        }
    finally:
        db.close()


def assert_legacy_artifact_publish_allowed(
    *,
    config_dir: str | os.PathLike[str] | None = None,
) -> Path:
    """Return config root or reject legacy-artifact publish for preview roots."""
    config_root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
    try:
        root_mode = mms_config_root_mode(config_root)
    except Exception:
        root_mode = "stable"
    if root_mode == "preview":
        raise RegistryValidationError(
            "publish-approved from legacy root artifacts is disabled for preview config roots; "
            "use publish-preview so the latest-approved bundle is generated from DB candidates"
        )
    return config_root


def publish_latest_approved_bundle(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    generated_at: str | None = None,
    actor: str = "agent",
) -> dict[str, Any]:
    """Publish a hash-verified latest-approved bundle from current local artifacts.

    This writes generated/* and the manifest only. It does not alter live root
    aliases such as model-routes.json, and it does not read/write credentials.
    """
    config_root = assert_legacy_artifact_publish_allowed(config_dir=config_dir)
    generated_dir = config_root / "generated"
    generated = generated_at or utc_now()
    db = open_registry(db_path or default_registry_db_path(config_root))
    try:
        source_files = {
            "router": _config_file(config_root, "model-routes.json"),
            "lineup": _config_file(config_root, "model-routes.lineup.json"),
            "policy": _config_file(config_root, "model-policy.json"),
        }
        output_files = {
            "router": generated_dir / "model-routes.json",
            "lineup": generated_dir / "model-routes.lineup.json",
            "profile": generated_dir / "provider-profiles.generated.json",
            "policy": generated_dir / "model-policy.effective.json",
            "capabilities": generated_dir / "model-capabilities.approved.json",
        }

        for name, src in source_files.items():
            copy_file_atomic(src, output_files[name], mode=0o600)
        write_json_atomic(output_files["profile"], _build_effective_provider_profiles_payload(config_root))

        capability_revision_seed = sha256_hex(
            _canonical_json_bytes(
                {
                    "source_snapshot_count": db.execute("SELECT count(*) FROM source_snapshot").fetchone()[0],
                    "model_fact_count": db.execute("SELECT count(*) FROM model_fact").fetchone()[0],
                    "generated_at": generated,
                }
            )
        )
        capability_revision = _revision_slug("cap", capability_revision_seed, generated_at=generated)
        capabilities_payload = build_approved_capabilities_payload(
            db,
            capability_revision=capability_revision,
            generated_at=generated,
        )
        write_json_atomic(output_files["capabilities"], capabilities_payload)

        file_hashes = {name: sha256_hex(path.read_bytes()) for name, path in output_files.items()}
        route_revision = _revision_slug("route", file_hashes["router"], generated_at=generated)
        policy_revision = _revision_slug("policy", file_hashes["policy"], generated_at=generated)
        profile_revision = _revision_slug("profile", file_hashes["profile"], generated_at=generated)
        bundle_hash = sha256_hex(
            _canonical_json_bytes(
                {
                    "capability_revision": capability_revision,
                    "route_revision": route_revision,
                    "policy_revision": policy_revision,
                    "profile_revision": profile_revision,
                    "file_hashes": file_hashes,
                }
            )
        )
        bundle_revision = _revision_slug("bundle", bundle_hash, generated_at=generated)

        for revision_id, revision_class, revision_hash in (
            (capability_revision, "capability", file_hashes["capabilities"]),
            (route_revision, "route", file_hashes["router"]),
            (policy_revision, "policy", file_hashes["policy"]),
            (profile_revision, "profile", file_hashes["profile"]),
            (bundle_revision, "bundle", bundle_hash),
        ):
            _create_revision_for_publish(
                db,
                revision_id,
                revision_class,
                revision_hash=revision_hash,
                metadata={"publish_generated_at": generated},
            )

        for revision_id, revision_class in (
            (capability_revision, "capability"),
            (route_revision, "route"),
            (policy_revision, "policy"),
            (profile_revision, "profile"),
        ):
            add_revision_membership(
                db,
                bundle_revision,
                revision_id,
                revision_class,
                metadata={"publish_generated_at": generated},
            )

        for revision_id in (capability_revision, route_revision, policy_revision, profile_revision, bundle_revision):
            _approve_if_candidate(db, revision_id, actor=actor)

        manifest_path = generated_dir / "model-registry.latest-approved.json"
        manifest = export_latest_approved_bundle_manifest(
            manifest_path,
            bundle_revision=bundle_revision,
            capability_revision=capability_revision,
            route_revision=route_revision,
            policy_revision=policy_revision,
            profile_revision=profile_revision,
            files={
                "router": {
                    "path": output_files["router"],
                    "canonical_path": "generated/model-routes.json",
                    "legacy_alias_path": "model-routes.json",
                    "sensitivity": "secret",
                    "legacy_alias_compat": True,
                },
                "lineup": {
                    "path": output_files["lineup"],
                    "canonical_path": "generated/model-routes.lineup.json",
                    "legacy_alias_path": "model-routes.lineup.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": True,
                },
                "profile": {
                    "path": output_files["profile"],
                    "canonical_path": "generated/provider-profiles.generated.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": False,
                },
                "policy": {
                    "path": output_files["policy"],
                    "canonical_path": "generated/model-policy.effective.json",
                    "legacy_alias_path": "model-policy.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": True,
                },
                "capabilities": {
                    "path": output_files["capabilities"],
                    "canonical_path": "generated/model-capabilities.approved.json",
                    "sensitivity": "non-secret",
                    "legacy_alias_compat": False,
                },
            },
            generated_at=generated,
            db=db,
        )
        with db:
            db.execute(
                """
                INSERT INTO audit_log(event_type, actor, target_type, target_id, details_json)
                VALUES ('bundle.published', ?, 'registry_revision', ?, ?)
                """,
                (
                    actor,
                    bundle_revision,
                    _json_text(
                        {
                            "manifest_path": str(manifest_path),
                            "files": manifest["files"],
                        }
                    ),
                ),
            )
        return {
            "manifest": manifest,
            "manifest_path": str(manifest_path),
            "generated_dir": str(generated_dir),
            "bundle_revision": bundle_revision,
            "capability_revision": capability_revision,
            "route_revision": route_revision,
            "policy_revision": policy_revision,
            "profile_revision": profile_revision,
            "files": {name: str(path) for name, path in output_files.items()},
        }
    finally:
        db.close()


def _manifest_base_dir(manifest_path: Path, config_dir: str | os.PathLike[str] | None = None) -> Path:
    if config_dir is not None:
        return Path(config_dir)
    if manifest_path.parent.name == "generated":
        return manifest_path.parent.parent
    return manifest_path.parent


def _validate_manifest_canonical_path(canonical_path: str, *, name: str) -> Path:
    relative = Path(canonical_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RegistryValidationError(f"manifest file entry escapes config root: {name}")
    return relative


def _manifest_file_path(base_dir: Path, canonical_path: Any, *, name: str) -> Path:
    canonical = str(canonical_path or "").strip()
    if not canonical:
        raise RegistryValidationError(f"manifest file entry missing canonical_path: {name}")
    relative = _validate_manifest_canonical_path(canonical, name=name)
    path = base_dir / relative
    try:
        resolved_base = base_dir.expanduser().resolve()
        resolved_path = path.expanduser().resolve()
        resolved_path.relative_to(resolved_base)
    except Exception as exc:
        raise RegistryValidationError(f"manifest file entry escapes config root: {name}") from exc
    return path


def verify_latest_approved_bundle(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path is not None else Path(config_dir or resolve_mms_config_dir()) / "generated" / "model-registry.latest-approved.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != LATEST_APPROVED_SCHEMA:
        raise RegistryValidationError(f"unexpected latest-approved schema: {manifest.get('schema')}")
    base_dir = _manifest_base_dir(path, config_dir)
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise RegistryValidationError("latest-approved manifest has no files")
    missing = [key for key in _MANIFEST_FILE_KEYS if key not in files]
    if missing:
        raise RegistryValidationError(f"manifest files missing: {', '.join(missing)}")
    unexpected = sorted(str(key) for key in files if key not in _MANIFEST_FILE_CONTRACT)
    if unexpected:
        raise RegistryValidationError(f"unexpected manifest files: {', '.join(unexpected)}")
    missing_revisions = [key for key in _MANIFEST_REVISION_KEYS if not str(manifest.get(key) or "").strip()]
    if missing_revisions:
        raise RegistryValidationError(f"manifest revisions missing: {', '.join(missing_revisions)}")
    verified_files: dict[str, dict[str, Any]] = {}
    for name, entry in files.items():
        if not isinstance(entry, dict):
            raise RegistryValidationError(f"invalid manifest file entry: {name}")
        expected = _MANIFEST_FILE_CONTRACT.get(str(name))
        if expected is None:
            raise RegistryValidationError(f"unexpected manifest file entry: {name}")
        canonical = str(entry.get("canonical_path") or "").strip()
        if canonical != expected["canonical_path"]:
            raise RegistryValidationError(f"unexpected manifest canonical_path for {name}: {canonical}")
        sensitivity = str(entry.get("sensitivity") or "").strip()
        if sensitivity != expected["sensitivity"]:
            raise RegistryValidationError(f"unexpected manifest sensitivity for {name}: {sensitivity}")
        file_path = _manifest_file_path(base_dir, entry.get("canonical_path"), name=str(name))
        if not file_path.exists():
            raise RegistryValidationError(f"manifest file missing: {file_path}")
        raw = file_path.read_bytes()
        actual_hash = sha256_hex(raw)
        expected_hash = str(entry.get("sha256") or "")
        if actual_hash != expected_hash:
            raise RegistryValidationError(f"manifest hash mismatch for {name}: {file_path}")
        payload = _parse_bundle_json_object(raw, path=file_path, name=str(name))
        if sensitivity != "secret":
            validate_non_secret_payload(payload, context=str(file_path))
        verified_files[name] = {
            "path": str(file_path),
            "sha256": actual_hash,
            "sensitivity": entry.get("sensitivity") or "",
        }
    return {
        "manifest_path": str(path),
        "base_dir": str(base_dir),
        "manifest": manifest,
        "verified_files": verified_files,
        "verified": True,
    }


def load_latest_approved_bundle(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
    include_secret: bool = False,
) -> dict[str, Any]:
    verified = verify_latest_approved_bundle(config_dir=config_dir, manifest_path=manifest_path)
    payloads: dict[str, Any] = {}
    for name, info in verified["verified_files"].items():
        if info.get("sensitivity") == "secret" and not include_secret:
            continue
        path = Path(info["path"])
        payloads[name] = _parse_bundle_json_object(path.read_bytes(), path=path, name=str(name))
    result = dict(verified)
    result["payloads"] = payloads
    return result


def try_load_latest_approved_payload(
    name: str,
    *,
    config_dir: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
    include_secret: bool = False,
) -> dict[str, Any]:
    """Return one verified latest-approved payload, or empty when unavailable."""
    try:
        bundle = load_latest_approved_bundle(
            config_dir=config_dir,
            manifest_path=manifest_path,
            include_secret=include_secret,
        )
    except (OSError, json.JSONDecodeError, TypeError, RegistryValidationError):
        return {}
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), Mapping) else {}
    payload = payloads.get(str(name or ""))
    return payload if isinstance(payload, dict) else {}


def latest_approved_capability_facts_path(
    *,
    config_dir: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
) -> str:
    verified = verify_latest_approved_bundle(config_dir=config_dir, manifest_path=manifest_path)
    files = verified.get("verified_files") or {}
    target = files.get("capabilities") or files.get("lineup") or {}
    return str(target.get("path") or "")
