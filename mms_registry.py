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

from mms_registry_schema import (
    PRIVACY_BOUNDARIES,
    REVISION_CLASSES,
    REVISION_STATUSES,
    migrate as migrate_schema,
)
from mms_state_io import resolve_mms_config_dir


LATEST_APPROVED_SCHEMA = "mms.model_registry.latest_approved.v1"
CALIBRATION_SOURCE_KIND = "model_capability_calibration"
OPENROUTER_MODELS_SOURCE_KIND = "openrouter_models_api"

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
_MANIFEST_FILE_KEYS = ("router", "lineup", "profile", "policy")
_OPTIONAL_MANIFEST_FILE_KEYS = ("capabilities",)
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
    root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir(env))
    return root / "model-registry.sqlite"


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


def _read_file_hash(path: Path, *, sensitivity: str) -> str:
    raw = path.read_bytes()
    if sensitivity != "secret":
        try:
            validate_non_secret_payload(json.loads(raw.decode("utf-8")), context=str(path))
        except json.JSONDecodeError:
            validate_non_secret_payload(raw.decode("utf-8", errors="replace"), context=str(path))
    return sha256_hex(raw)


def _manifest_file_entry(name: str, spec: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(spec["path"])
    sensitivity = str(spec.get("sensitivity") or "non-secret")
    if sensitivity not in {"secret", "non-secret"}:
        raise RegistryValidationError(f"unknown sensitivity for {name}: {sensitivity}")
    return {
        "canonical_path": str(spec.get("canonical_path") or f"generated/{path.name}"),
        "legacy_alias_path": str(spec.get("legacy_alias_path") or ""),
        "sha256": str(spec.get("sha256") or _read_file_hash(path, sensitivity=sensitivity)),
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
    config_root = Path(config_dir) if config_dir is not None else Path(resolve_mms_config_dir())
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
    verified_files: dict[str, dict[str, Any]] = {}
    for name, entry in (manifest.get("files") or {}).items():
        canonical = str(entry.get("canonical_path") or "").strip()
        if not canonical:
            raise RegistryValidationError(f"manifest file entry missing canonical_path: {name}")
        file_path = base_dir / canonical
        if not file_path.exists():
            raise RegistryValidationError(f"manifest file missing: {file_path}")
        actual_hash = sha256_hex(file_path.read_bytes())
        expected_hash = str(entry.get("sha256") or "")
        if actual_hash != expected_hash:
            raise RegistryValidationError(f"manifest hash mismatch for {name}: {file_path}")
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
        try:
            payloads[name] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payloads[name] = path.read_text(encoding="utf-8", errors="replace")
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
