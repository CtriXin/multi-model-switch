"""A release must pass the same version contract as Pilot's update probe."""
import hashlib
import json
from pathlib import Path

from mms_version import VERSION
from mms_web.update_stage import validate_bundle


def compute_web_source_sha256(app_root: Path) -> str:
    source_hash = hashlib.sha256()
    inputs = [
        *sorted((app_root / "src").rglob("*")),
        app_root / "package.json",
        app_root / "package-lock.json",
        app_root / "index.html",
        app_root / "vite.config.ts",
        app_root / "tsconfig.json",
    ]
    for path in inputs:
        if path.is_file():
            source_hash.update(path.relative_to(app_root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return source_hash.hexdigest()


def test_packaged_release_versions_match_runtime():
    root = Path(__file__).resolve().parents[1]
    for relative in ("package.json", "apps/mms-web/package.json", "apps/mms-web/package-lock.json"):
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
        assert payload["version"] == VERSION, f"{relative} disagrees with the runtime"
        if "lockfileVersion" in payload:
            assert payload["packages"][""]["version"] == VERSION
    validate_bundle(root, f"v{VERSION}")
    assert (root / "docs/mms-web" / f"RELEASE-v{VERSION}.md").is_file()


def test_packaged_web_bundle_matches_source():
    root = Path(__file__).resolve().parents[1]
    app = root / "apps/mms-web"
    target = root / "mms_web_static"
    build_json = target / "build.json"
    assert build_json.is_file(), "mms_web_static/build.json does not exist"
    manifest = json.loads(build_json.read_text(encoding="utf-8"))
    expected_sha = compute_web_source_sha256(app)
    assert manifest.get("sourceSha256") == expected_sha, (
        f"mms_web_static bundle sourceSha256 ({manifest.get('sourceSha256')}) "
        f"does not match apps/mms-web source fingerprint ({expected_sha}). "
        f"Run python3 scripts/build_mms_web_release.py to rebuild the release bundle."
    )

