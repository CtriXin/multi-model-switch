"""Pytest safety defaults for MMS config-root tests."""

from __future__ import annotations

import os
import tempfile


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
