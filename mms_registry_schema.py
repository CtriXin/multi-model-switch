from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 1
PRIVACY_BOUNDARIES = ("private", "team", "public")
REVISION_CLASSES = ("bundle", "capability", "route", "policy", "profile")
REVISION_STATUSES = ("candidate", "approved", "tombstoned")


SCHEMA_V1_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS source_snapshot (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_kind TEXT NOT NULL,
    source_path TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
    schema TEXT NOT NULL DEFAULT '',
    model_count INTEGER NOT NULL DEFAULT 0 CHECK (model_count >= 0),
    payload_json TEXT NOT NULL,
    UNIQUE (source_kind, source_path, content_hash)
);

CREATE TABLE IF NOT EXISTS registry_revision (
    revision_id TEXT PRIMARY KEY,
    revision_class TEXT NOT NULL CHECK (revision_class IN ('bundle', 'capability', 'route', 'policy', 'profile')),
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'approved', 'tombstoned')),
    revision_hash TEXT NOT NULL CHECK (length(revision_hash) = 64),
    bundle_revision TEXT NOT NULL DEFAULT '',
    privacy_boundary TEXT NOT NULL DEFAULT 'private' CHECK (privacy_boundary IN ('private', 'team', 'public')),
    created_at TEXT NOT NULL,
    approved_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    CHECK (status != 'approved' OR approved_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS revision_membership (
    bundle_revision TEXT NOT NULL,
    member_revision TEXT NOT NULL,
    member_class TEXT NOT NULL CHECK (member_class IN ('capability', 'route', 'policy', 'profile')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (bundle_revision, member_revision, member_class),
    FOREIGN KEY (bundle_revision) REFERENCES registry_revision(revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (member_revision) REFERENCES registry_revision(revision_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS tombstone_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    reason TEXT NOT NULL,
    last_approved_revision TEXT NOT NULL,
    event_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS route_group (
    route_group_id TEXT PRIMARY KEY,
    route_revision_id TEXT NOT NULL,
    logical_model TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    privacy_boundary TEXT NOT NULL DEFAULT 'private' CHECK (privacy_boundary IN ('private', 'team', 'public')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'candidate', 'tombstoned')),
    tombstone_event_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (route_revision_id) REFERENCES registry_revision(revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (tombstone_event_id) REFERENCES tombstone_event(event_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS provider_route (
    route_id TEXT PRIMARY KEY,
    route_group_id TEXT NOT NULL,
    route_revision_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    wire_model_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    anthropic_base_url TEXT NOT NULL DEFAULT '',
    openai_base_url TEXT NOT NULL DEFAULT '',
    secret_ref TEXT NOT NULL DEFAULT '',
    privacy_boundary TEXT NOT NULL DEFAULT 'private' CHECK (privacy_boundary IN ('private', 'team', 'public')),
    validation_state TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'candidate', 'tombstoned')),
    tombstone_event_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (route_group_id) REFERENCES route_group(route_group_id) ON DELETE RESTRICT,
    FOREIGN KEY (route_revision_id) REFERENCES registry_revision(revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (tombstone_event_id) REFERENCES tombstone_event(event_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS model_identity (
    model_key TEXT PRIMARY KEY,
    canonical_model_id TEXT NOT NULL DEFAULT '',
    alias TEXT NOT NULL DEFAULT '',
    vendor TEXT NOT NULL DEFAULT '',
    family TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS model_fact (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_key TEXT NOT NULL,
    source_snapshot_id INTEGER,
    revision_id TEXT,
    fact_key TEXT NOT NULL,
    fact_value_json TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT '',
    source_layer TEXT NOT NULL DEFAULT 'unknown' CHECK (source_layer IN ('official', 'provider_catalog', 'runtime', 'local_alias', 'unknown')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (model_key) REFERENCES model_identity(model_key) ON DELETE RESTRICT,
    FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot(snapshot_id) ON DELETE RESTRICT,
    FOREIGN KEY (revision_id) REFERENCES registry_revision(revision_id) ON DELETE RESTRICT,
    UNIQUE (source_snapshot_id, model_key, fact_key)
);

CREATE TABLE IF NOT EXISTS export_snapshot (
    export_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bundle_revision TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_hash TEXT NOT NULL CHECK (length(manifest_hash) = 64),
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'agent',
    event_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_source_snapshot_hash ON source_snapshot(content_hash);
CREATE INDEX IF NOT EXISTS idx_registry_revision_status ON registry_revision(status, revision_class);
CREATE INDEX IF NOT EXISTS idx_revision_membership_bundle ON revision_membership(bundle_revision);
CREATE INDEX IF NOT EXISTS idx_route_group_revision ON route_group(route_revision_id);
CREATE INDEX IF NOT EXISTS idx_provider_route_revision ON provider_route(route_revision_id);
CREATE INDEX IF NOT EXISTS idx_provider_route_group ON provider_route(route_group_id);
CREATE INDEX IF NOT EXISTS idx_model_fact_model ON model_fact(model_key);
CREATE INDEX IF NOT EXISTS idx_model_fact_source ON model_fact(source_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_export_snapshot_bundle ON export_snapshot(bundle_revision);

CREATE TRIGGER IF NOT EXISTS registry_revision_approved_no_update
BEFORE UPDATE ON registry_revision
WHEN OLD.status = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'approved registry_revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS registry_revision_approved_no_delete
BEFORE DELETE ON registry_revision
WHEN OLD.status = 'approved'
BEGIN
    SELECT RAISE(ABORT, 'approved registry_revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS revision_membership_no_insert_into_approved_bundle
BEFORE INSERT ON revision_membership
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = NEW.bundle_revision AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved bundle membership is immutable');
END;

CREATE TRIGGER IF NOT EXISTS revision_membership_no_update_approved
BEFORE UPDATE ON revision_membership
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id IN (OLD.bundle_revision, OLD.member_revision) AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved revision membership is immutable');
END;

CREATE TRIGGER IF NOT EXISTS revision_membership_no_delete_approved
BEFORE DELETE ON revision_membership
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id IN (OLD.bundle_revision, OLD.member_revision) AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved revision membership is immutable');
END;

CREATE TRIGGER IF NOT EXISTS route_group_no_insert_into_approved_revision
BEFORE INSERT ON route_group
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = NEW.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS route_group_no_update_approved
BEFORE UPDATE ON route_group
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS route_group_no_delete_approved
BEFORE DELETE ON route_group
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS provider_route_no_insert_into_approved_revision
BEFORE INSERT ON provider_route
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = NEW.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS provider_route_no_update_approved
BEFORE UPDATE ON provider_route
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS provider_route_no_delete_approved
BEFORE DELETE ON provider_route
WHEN EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.route_revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved route revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS model_fact_no_insert_into_approved_revision
BEFORE INSERT ON model_fact
WHEN NEW.revision_id IS NOT NULL
AND EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = NEW.revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved capability revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS model_fact_no_update_approved
BEFORE UPDATE ON model_fact
WHEN OLD.revision_id IS NOT NULL
AND EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved capability revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS model_fact_no_delete_approved
BEFORE DELETE ON model_fact
WHEN OLD.revision_id IS NOT NULL
AND EXISTS (
    SELECT 1 FROM registry_revision
    WHERE revision_id = OLD.revision_id AND status = 'approved'
)
BEGIN
    SELECT RAISE(ABORT, 'approved capability revision is immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_append_only_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_log_append_only_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""


def migrate(db: sqlite3.Connection) -> None:
    """Apply registry schema migrations to an open SQLite connection."""
    with db:
        db.executescript(SCHEMA_V1_SQL)
        db.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, name) VALUES (?, ?)",
            (SCHEMA_VERSION, "registry_core_v1"),
        )
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
