"""Pytest safety defaults for MMS config-root tests."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "lib"


def mms_pythonpath(*extra: str | Path) -> str:
    parts = [str(LIB_DIR), str(REPO_ROOT), *[str(item) for item in extra]]
    return os.pathsep.join(parts)


_lib = str(LIB_DIR)
if _lib not in sys.path:
    sys.path.insert(0, _lib)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enable", "enabled"}


if not _truthy(os.environ.get("MMS_TEST_ALLOW_REAL_CONFIG")):
    # Avoid inheriting a developer shell's real XDG_CONFIG_HOME (for example
    # /Users/xin/.config) before test modules import MMS path constants.
    has_explicit_root = any(
        str(os.environ.get(key) or "").strip()
        for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR")
    )
    if not has_explicit_root:
        os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="mms-test-xdg-")


import pytest


@pytest.fixture(autouse=True)
def restore_i18n_language():
    import mms_i18n
    original = mms_i18n._CURRENT_LANGUAGE
    yield
    mms_i18n._CURRENT_LANGUAGE = original


@pytest.fixture
def approved_preview_bundle(monkeypatch, tmp_path):
    from approved_bundle import write_bundle
    from mms_capability_resolver import clear_capability_resolver_caches
    import mms_provider_profiles
    clear_profiles = mms_provider_profiles.load_provider_profiles.cache_clear
    root = tmp_path / "approved-root"
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(root))
    write_bundle(root)
    clear_capability_resolver_caches()
    clear_profiles()
    yield root
    clear_capability_resolver_caches()
    clear_profiles()
