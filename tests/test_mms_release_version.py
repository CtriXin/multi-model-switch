"""A release must pass the same version contract as Pilot's update probe."""
import json
from pathlib import Path

from mms_version import VERSION
from mms_web.update_stage import validate_bundle


def test_packaged_release_versions_match_runtime():
    root = Path(__file__).resolve().parents[1]
    for relative in ("package.json", "apps/mms-web/package.json", "apps/mms-web/package-lock.json"):
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
        assert payload["version"] == VERSION, f"{relative} disagrees with the runtime"
        if "lockfileVersion" in payload:
            assert payload["packages"][""]["version"] == VERSION
    validate_bundle(root, f"v{VERSION}")
    assert (root / "docs/mms-web" / f"RELEASE-v{VERSION}.md").is_file()
