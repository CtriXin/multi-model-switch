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
            INSERT INTO revision_membership(bundle_revision, member_revision, member_class, metadata_json)
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
