"""Pytest safety defaults for MMS config-root tests."""

from __future__ import annotations

import os
import tempfile

import pytest


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


@pytest.fixture(autouse=True)
def _restore_mms_ui_language():
    """Undo process-global UI language flips leaked by tests that drive main().

    ``mms_core.main()`` calls ``mms_i18n.set_language`` from locale env, which
    mutates module-global state that monkeypatch cannot see. Without this,
    any main()-driving test on an English-locale machine permanently switches
    later tests to English labels (see T8c report, group R10). Save the value
    on entry and restore it on exit rather than forcing "zh", so tests that
    deliberately set a language keep working.
    """
    import mms_i18n

    previous = mms_i18n.get_language()
    yield
    mms_i18n.set_language(previous)
