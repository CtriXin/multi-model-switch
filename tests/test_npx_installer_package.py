"""The npx wrapper is published to npm, so its shape is checked here rather
than only at publish time. Nothing in this file reaches the network."""

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "packages" / "mms-install"
MANIFEST = PACKAGE_DIR / "package.json"
ENTRY = PACKAGE_DIR / "bin" / "mms-install.mjs"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_package_is_publishable_as_a_public_scoped_package():
    manifest = _manifest()

    assert manifest["name"] == "@ctrixin/mms"
    assert manifest["publishConfig"]["access"] == "public"
    assert manifest["license"] == "Apache-2.0"
    assert manifest["bin"] == {"mms-install": "bin/mms-install.mjs"}
    assert "bin" in manifest["files"]
    assert "README.md" in manifest["files"]
    assert manifest["repository"]["directory"] == "packages/mms-install"


def test_package_declares_the_platforms_it_can_actually_run_on():
    manifest = _manifest()

    # global fetch and the node: prefix both need a modern runtime
    assert manifest["engines"]["node"] == ">=18.17"
    assert manifest["os"] == ["darwin", "linux"]


def test_entrypoint_is_executable_and_parses():
    assert ENTRY.exists()
    assert os.access(ENTRY, os.X_OK), "npm needs the bin file to be executable"
    assert ENTRY.read_text(encoding="utf-8").startswith("#!/usr/bin/env node\n")

    node = shutil.which("node")
    if node is None:  # pragma: no cover - node is present in this repo's toolchain
        return
    subprocess.run([node, "--check", str(ENTRY)], check=True, capture_output=True)


def test_wrapper_pins_the_source_host_and_verifies_the_payload():
    text = ENTRY.read_text(encoding="utf-8")

    assert 'const RAW_HOST = "raw.githubusercontent.com"' in text
    assert 'const REPO = "CtriXin/multi-model-switch"' in text
    # a redirect away from the pinned host must abort, not be followed silently
    assert "refusing a redirect off" in text
    # the payload is checked before it is executed
    assert 'REPO_NAME="multi-model-switch"' in text
    assert "does not look like the MMS installer" in text


def test_wrapper_holds_no_install_logic_of_its_own():
    """Install behavior belongs in install.sh so a cached wrapper stays correct."""
    text = ENTRY.read_text(encoding="utf-8")

    for leaked in ("~/.mms", "npm install -g", "pi-coding-agent", "MMS_CONFIG_ROOT"):
        assert leaked not in text, leaked
    assert len(text.splitlines()) < 140


def test_wrapper_keeps_the_script_and_the_installed_sources_on_one_ref():
    text = ENTRY.read_text(encoding="utf-8")

    for flag in ("--ref", "--channel", "--dev", "--canary"):
        assert flag in text, flag
    assert "function resolveRef" in text


def test_wrapper_refuses_windows_with_a_readable_message():
    text = ENTRY.read_text(encoding="utf-8")

    assert 'process.platform === "win32"' in text
    assert "WSL" in text


def test_package_is_part_of_the_repo_workspaces():
    root_manifest = json.loads((ROOT_DIR / "package.json").read_text(encoding="utf-8"))

    assert "packages/*" in root_manifest["workspaces"]
    assert root_manifest.get("private") is True, "only the wrapper is published"
