from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from pathlib import Path

import pytest

import mms_registry


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_JSON = ROOT / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"


def _open_temp_registry(tmp_path: Path) -> sqlite3.Connection:
    return mms_registry.open_registry(tmp_path / "model-registry.sqlite")


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _bundle_file_specs(tmp_path: Path) -> dict[str, dict[str, object]]:
    router = _write_json(
        tmp_path / "generated/model-routes.json",
        {
            "version": 1,
            "routes": {
                "kimi-k2.5": {
                    "primary": {
                        "provider_id": "kimi-private",
                        "api_key": "sk-secret-value-123456789",
                        "model_id": "kimi-k2.5",
                    },
                    "fallbacks": [],
                }
            },
        },
    )
    lineup = _write_json(
        tmp_path / "generated/model-routes.lineup.json",
        {"version": 1, "routes": {"kimi-k2.5": {"primary": {"max_context_tokens": 256000}}}},
    )
    profile = _write_json(
        tmp_path / "generated/provider-profiles.generated.json",
        {"version": 1, "profiles": {"kimi-private": {"protocol": "anthropic_messages"}}},
    )
    policy = _write_json(
        tmp_path / "generated/model-policy.effective.json",
        {"version": 1, "models": {"kimi-k2.5": {"visible": True}}},
    )
    return {
        "router": {
            "path": router,
            "canonical_path": "generated/model-routes.json",
            "legacy_alias_path": "model-routes.json",
            "sensitivity": "secret",
            "legacy_alias_compat": True,
        },
        "lineup": {
            "path": lineup,
            "canonical_path": "generated/model-routes.lineup.json",
            "legacy_alias_path": "model-routes.lineup.json",
            "sensitivity": "non-secret",
            "legacy_alias_compat": True,
        },
        "profile": {
            "path": profile,
            "canonical_path": "generated/provider-profiles.generated.json",
            "legacy_alias_path": "",
            "sensitivity": "non-secret",
            "legacy_alias_compat": False,
        },
        "policy": {
            "path": policy,
            "canonical_path": "generated/model-policy.effective.json",
            "legacy_alias_path": "model-policy.json",
            "sensitivity": "non-secret",
            "legacy_alias_compat": True,
        },
    }


def test_fresh_db_migration_creates_schema_and_wal_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "model-registry.sqlite"
    db = mms_registry.open_registry(db_path)
    try:
        assert db_path.exists()
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2

        tables = {
            row["name"]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {
            "schema_migrations",
            "source_snapshot",
            "source_check",
            "registry_revision",
            "revision_membership",
            "route_group",
            "provider_route",
            "model_identity",
            "model_fact",
            "export_snapshot",
            "audit_log",
            "tombstone_event",
        }.issubset(tables)
        migration_versions = {
            row["version"]
            for row in db.execute("SELECT version FROM schema_migrations")
        }
        assert {1, 2}.issubset(migration_versions)
    finally:
        db.close()


def test_source_calibration_json_imports_as_source_snapshot(tmp_path: Path) -> None:
    db = _open_temp_registry(tmp_path)
    try:
        summary = mms_registry.import_source_snapshot(db, REFERENCE_JSON, captured_at="2026-05-22T00:00:00.000Z")
        expected_hash = hashlib.sha256(REFERENCE_JSON.read_bytes()).hexdigest()

        snapshot = db.execute(
            "SELECT * FROM source_snapshot WHERE snapshot_id = ?",
            (summary["snapshot_id"],),
        ).fetchone()
        assert snapshot["source_kind"] == mms_registry.CALIBRATION_SOURCE_KIND
        assert snapshot["source_path"] == str(REFERENCE_JSON)
        assert snapshot["captured_at"] == "2026-05-22T00:00:00.000Z"
        assert snapshot["content_hash"] == expected_hash
        assert snapshot["schema"] == "mobius.mms_model_capability_calibration.v1"
        assert snapshot["model_count"] == summary["model_count"] >= 39
        source_check = db.execute(
            "SELECT * FROM source_check WHERE source_kind = ? AND source_path = ?",
            (mms_registry.CALIBRATION_SOURCE_KIND, str(REFERENCE_JSON)),
        ).fetchone()
        assert source_check["checked_at"] == "2026-05-22T00:00:00.000Z"
        assert source_check["content_hash"] == expected_hash
        assert source_check["snapshot_id"] == summary["snapshot_id"]

        identity_count = db.execute("SELECT count(*) FROM model_identity").fetchone()[0]
        fact_count = db.execute("SELECT count(*) FROM model_fact").fetchone()[0]
        assert identity_count >= 30
        assert fact_count >= summary["model_count"]
    finally:
        db.close()


def test_approved_revision_and_routes_are_immutable(tmp_path: Path) -> None:
    db = _open_temp_registry(tmp_path)
    try:
        mms_registry.create_revision(db, "route_20260522_001", "route")
        mms_registry.insert_route_group(db, "kimi", "route_20260522_001", logical_model="kimi-k2.5")
        mms_registry.insert_provider_route(
            db,
            "kimi-private-route",
            "kimi",
            "route_20260522_001",
            provider_id="kimi-private",
            wire_model_id="kimi-k2.5",
            secret_ref="env:MMS_KIMI_API_KEY",
        )
        mms_registry.approve_revision(db, "route_20260522_001")

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with db:
                db.execute("UPDATE registry_revision SET metadata_json = '{}' WHERE revision_id = 'route_20260522_001'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with db:
                db.execute("DELETE FROM registry_revision WHERE revision_id = 'route_20260522_001'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with db:
                db.execute("UPDATE provider_route SET provider_id = 'changed' WHERE route_id = 'kimi-private-route'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            with db:
                db.execute("DELETE FROM provider_route WHERE route_id = 'kimi-private-route'")
    finally:
        db.close()


def test_privacy_boundary_defaults_to_private(tmp_path: Path) -> None:
    db = _open_temp_registry(tmp_path)
    try:
        mms_registry.create_revision(db, "route_20260522_002", "route", privacy_boundary="unknown")
        with db:
            db.execute(
                "INSERT INTO route_group(route_group_id, route_revision_id) VALUES (?, ?)",
                ("qwen", "route_20260522_002"),
            )
            db.execute(
                """
                INSERT INTO provider_route(route_id, route_group_id, route_revision_id, provider_id, wire_model_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("qwen-route", "qwen", "route_20260522_002", "qwen-private", "qwen3.5-plus"),
            )

        assert mms_registry.normalize_privacy_boundary("unknown") == "private"
        assert db.execute("SELECT privacy_boundary FROM registry_revision").fetchone()[0] == "private"
        assert db.execute("SELECT privacy_boundary FROM route_group").fetchone()[0] == "private"
        assert db.execute("SELECT privacy_boundary FROM provider_route").fetchone()[0] == "private"
    finally:
        db.close()


def test_secret_looking_values_rejected_from_non_secret_route_and_export_fields(tmp_path: Path) -> None:
    db = _open_temp_registry(tmp_path)
    try:
        with pytest.raises(mms_registry.RegistryValidationError, match="api_key"):
            mms_registry.validate_non_secret_payload(
                {"lineup": {"primary": {"api_key": "sk-secret-value-123456789"}}},
                context="lineup",
            )

        mms_registry.create_revision(db, "route_20260522_003", "route")
        mms_registry.insert_route_group(db, "glm", "route_20260522_003")
        mms_registry.insert_provider_route(
            db,
            "glm-route",
            "glm",
            "route_20260522_003",
            provider_id="glm-private",
            wire_model_id="glm-5.1",
            secret_ref="env:MMS_GLM_API_KEY",
        )

        with pytest.raises(mms_registry.RegistryValidationError, match="secret_ref"):
            mms_registry.insert_provider_route(
                db,
                "bad-secret-ref",
                "glm",
                "route_20260522_003",
                provider_id="glm-private",
                wire_model_id="glm-5.1",
                secret_ref="sk-secret-value-123456789",
            )
        with pytest.raises(mms_registry.RegistryValidationError, match="Authorization"):
            mms_registry.insert_provider_route(
                db,
                "bad-header",
                "glm",
                "route_20260522_003",
                provider_id="glm-private",
                wire_model_id="glm-5.1",
                metadata={"headers": {"Authorization": "Bearer abcdefghijklmnop"}},
            )
    finally:
        db.close()


def test_latest_approved_bundle_manifest_includes_required_fields_and_hashes(tmp_path: Path) -> None:
    files = _bundle_file_specs(tmp_path)
    manifest = mms_registry.build_latest_approved_bundle_manifest(
        bundle_revision="bundle_20260522_001",
        capability_revision="cap_20260522_001",
        route_revision="route_20260522_001",
        policy_revision="policy_20260522_001",
        profile_revision="profile_20260522_001",
        generated_at="2026-05-22T00:00:00.000Z",
        files=files,
    )

    assert manifest["schema"] == "mms.model_registry.latest_approved.v1"
    assert manifest["model_registry_revision"] == manifest["bundle_revision"]
    for field in [
        "bundle_revision",
        "capability_revision",
        "route_revision",
        "policy_revision",
        "profile_revision",
        "generated_at",
        "files",
    ]:
        assert field in manifest
    for name, spec in files.items():
        entry = manifest["files"][name]
        expected_hash = hashlib.sha256(Path(spec["path"]).read_bytes()).hexdigest()
        assert entry["sha256"] == expected_hash
        assert set(entry) == {
            "canonical_path",
            "legacy_alias_path",
            "sha256",
            "sensitivity",
            "legacy_alias_compat",
        }
    assert "sk-secret-value" not in json.dumps(manifest, sort_keys=True)


def test_atomic_export_writes_manifest_and_export_snapshot_to_temp_path(tmp_path: Path) -> None:
    db = _open_temp_registry(tmp_path)
    try:
        output_path = tmp_path / "generated/model-registry.latest-approved.json"
        manifest = mms_registry.export_latest_approved_bundle_manifest(
            output_path,
            bundle_revision="bundle_20260522_002",
            capability_revision="cap_20260522_002",
            route_revision="route_20260522_002",
            policy_revision="policy_20260522_002",
            profile_revision="profile_20260522_002",
            generated_at="2026-05-22T01:00:00.000Z",
            files=_bundle_file_specs(tmp_path),
            db=db,
        )

        written = json.loads(output_path.read_text(encoding="utf-8"))
        assert written == manifest
        assert stat.S_IMODE(output_path.stat().st_mode) == 0o600
        assert list(output_path.parent.glob("*.tmp")) == []

        export_row = db.execute("SELECT * FROM export_snapshot").fetchone()
        assert export_row["bundle_revision"] == "bundle_20260522_002"
        assert export_row["manifest_path"] == str(output_path)
        assert export_row["manifest_hash"] == mms_registry.sha256_hex(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    finally:
        db.close()
