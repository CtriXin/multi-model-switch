# -*- coding: utf-8 -*-
"""Read-only helper for MMS latest-approved consumer bundles.

This module is intentionally small and independent of the registry DB code so
Hive/Pilot/Ant/Mobius-style consumers can verify the bundle boundary without
querying SQLite or legacy root files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

LATEST_APPROVED_SCHEMA = "mms.model_registry.latest_approved.v1"
DEFAULT_MANIFEST_RELATIVE_PATH = Path("generated") / "model-registry.latest-approved.json"
EXPECTED_BUNDLE_FILES = {
    "router": {"canonical_path": "generated/model-routes.json", "sensitivity": "secret"},
    "lineup": {"canonical_path": "generated/model-routes.lineup.json", "sensitivity": "non-secret"},
    "profile": {"canonical_path": "generated/provider-profiles.generated.json", "sensitivity": "non-secret"},
    "policy": {"canonical_path": "generated/model-policy.effective.json", "sensitivity": "non-secret"},
    "capabilities": {"canonical_path": "generated/model-capabilities.approved.json", "sensitivity": "non-secret"},
}
REQUIRED_BUNDLE_FILES = tuple(EXPECTED_BUNDLE_FILES)
REQUIRED_REVISION_FIELDS = ("bundle_revision", "capability_revision", "route_revision", "policy_revision", "profile_revision")


class ConsumerBundleError(RuntimeError):
    """Raised when a consumer bundle cannot be safely verified."""


def _env_mapping(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return env if env is not None else os.environ


def resolve_consumer_config_root(
    config_root: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    allow_default_root: bool = False,
) -> Path:
    """Resolve the config root for a downstream consumer.

    Downstream consumers should pass an explicit root or inherit
    ``MMS_CONFIG_ROOT`` from the selected runtime. Falling back to stable
    ``~/.config/mms`` is opt-in so preview consumers do not silently cross root
    boundaries when their environment is incomplete.
    """
    if config_root is not None and str(config_root).strip():
        return Path(config_root).expanduser()
    environ = _env_mapping(env)
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR"):
        value = str(environ.get(key) or "").strip()
        if value:
            return Path(value).expanduser()
    if allow_default_root:
        return Path.home() / ".config" / "mms"
    raise ConsumerBundleError("MMS_CONFIG_ROOT is required for consumer bundle resolution")


def _manifest_base_dir(manifest_path: Path, config_root: Path | None = None) -> Path:
    if config_root is not None:
        return config_root
    if manifest_path.parent.name == "generated":
        return manifest_path.parent.parent
    return manifest_path.parent


def _safe_manifest_file_path(base_dir: Path, canonical_path: Any, *, name: str) -> Path:
    text = str(canonical_path or "").strip()
    if not text:
        raise ConsumerBundleError(f"manifest file entry missing canonical_path: {name}")
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConsumerBundleError(f"manifest file entry escapes config root: {name}")
    path = base_dir / relative
    try:
        resolved_base = base_dir.resolve()
        resolved_path = path.resolve()
        resolved_path.relative_to(resolved_base)
    except Exception as exc:
        raise ConsumerBundleError(f"manifest file entry escapes config root: {name}") from exc
    return path


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_manifest_file_contract(name: str, entry: Mapping[str, Any]) -> None:
    expected = EXPECTED_BUNDLE_FILES.get(name)
    if expected is None:
        raise ConsumerBundleError(f"unexpected manifest file entry: {name}")
    canonical = str(entry.get("canonical_path") or "").strip()
    if canonical != expected["canonical_path"]:
        raise ConsumerBundleError(f"unexpected manifest canonical_path for {name}: {canonical}")
    sensitivity = str(entry.get("sensitivity") or "").strip()
    if sensitivity != expected["sensitivity"]:
        raise ConsumerBundleError(f"unexpected manifest sensitivity for {name}: {sensitivity}")


def load_verified_consumer_bundle(
    *,
    config_root: str | os.PathLike[str] | None = None,
    manifest_path: str | os.PathLike[str] | None = None,
    include_secret: bool = False,
    env: Mapping[str, str] | None = None,
    allow_default_root: bool = False,
) -> dict[str, Any]:
    """Load a hash-verified MMS latest-approved bundle.

    The function reads the manifest first, verifies each referenced file hash,
    and loads only manifest-referenced generated files. Secret-bearing payloads
    are verified but omitted unless ``include_secret`` is true.
    """
    root = None if config_root is None else Path(config_root).expanduser()
    if root is None and manifest_path is None:
        root = resolve_consumer_config_root(env=env, allow_default_root=allow_default_root)
    manifest = Path(manifest_path).expanduser() if manifest_path is not None else root / DEFAULT_MANIFEST_RELATIVE_PATH
    base_dir = _manifest_base_dir(manifest, root)
    if not manifest.exists():
        raise ConsumerBundleError(f"latest-approved manifest is missing: {manifest}")
    try:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConsumerBundleError(f"latest-approved manifest is not valid JSON: {manifest}") from exc
    if not isinstance(manifest_payload, dict):
        raise ConsumerBundleError("latest-approved manifest must be a JSON object")
    if manifest_payload.get("schema") != LATEST_APPROVED_SCHEMA:
        raise ConsumerBundleError(f"unexpected latest-approved schema: {manifest_payload.get('schema')}")
    files = manifest_payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ConsumerBundleError("latest-approved manifest has no files")
    missing_files = [name for name in REQUIRED_BUNDLE_FILES if name not in files]
    if missing_files:
        raise ConsumerBundleError("latest-approved manifest missing required files: " + ", ".join(missing_files))
    missing_revisions = [name for name in REQUIRED_REVISION_FIELDS if not str(manifest_payload.get(name) or "").strip()]
    if missing_revisions:
        raise ConsumerBundleError("latest-approved manifest missing required revisions: " + ", ".join(missing_revisions))

    verified_files: dict[str, dict[str, Any]] = {}
    payloads: dict[str, Any] = {}
    skipped_secret_files: list[str] = []
    for name, entry in files.items():
        name_text = str(name or "")
        if not isinstance(entry, dict):
            raise ConsumerBundleError(f"invalid manifest file entry: {name_text}")
        _validate_manifest_file_contract(name_text, entry)
        path = _safe_manifest_file_path(base_dir, entry.get("canonical_path"), name=name_text)
        if not path.exists():
            raise ConsumerBundleError(f"manifest file missing: {path}")
        actual = _sha256_file(path)
        expected = str(entry.get("sha256") or "").strip()
        if not expected:
            raise ConsumerBundleError(f"manifest file entry missing sha256: {name_text}")
        if actual != expected:
            raise ConsumerBundleError(f"manifest hash mismatch for {name_text}: {path}")
        sensitivity = str(entry.get("sensitivity") or "").strip()
        verified_files[name_text] = {
            "path": str(path),
            "canonical_path": str(entry.get("canonical_path") or ""),
            "legacy_alias_path": str(entry.get("legacy_alias_path") or ""),
            "legacy_alias_compat": bool(entry.get("legacy_alias_compat", False)),
            "sha256": actual,
            "sensitivity": sensitivity,
        }
        if sensitivity == "secret" and not include_secret:
            skipped_secret_files.append(name_text)
            continue
        try:
            payloads[name_text] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConsumerBundleError(f"manifest file is not valid JSON for {name_text}: {path}") from exc

    component_revisions = {
        "bundle": manifest_payload.get("bundle_revision") or "",
        "model_registry": manifest_payload.get("model_registry_revision") or "",
        "capability": manifest_payload.get("capability_revision") or "",
        "route": manifest_payload.get("route_revision") or "",
        "policy": manifest_payload.get("policy_revision") or "",
        "profile": manifest_payload.get("profile_revision") or "",
    }
    return {
        "schema": "mms.consumer_bundle.verified.v1",
        "verified": True,
        "config_root": str(base_dir),
        "manifest_path": str(manifest),
        "manifest": manifest_payload,
        "component_revisions": component_revisions,
        "verified_files": verified_files,
        "payloads": payloads,
        "skipped_secret_files": skipped_secret_files,
    }


__all__ = [
    "ConsumerBundleError",
    "DEFAULT_MANIFEST_RELATIVE_PATH",
    "EXPECTED_BUNDLE_FILES",
    "LATEST_APPROVED_SCHEMA",
    "REQUIRED_BUNDLE_FILES",
    "REQUIRED_REVISION_FIELDS",
    "load_verified_consumer_bundle",
    "resolve_consumer_config_root",
]
