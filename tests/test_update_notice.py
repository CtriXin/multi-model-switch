from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeTTY:
    def isatty(self) -> bool:
        return True


def test_semver_tag_gap_counts_newer_tags():
    import mms_core

    assert (
        mms_core._semver_tag_gap(
            "v1.16.3",
            ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"],
        )
        == 3
    )


def test_update_notice_prompts_when_install_user_is_three_versions_behind(monkeypatch):
    import mms_core

    saved = {}
    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
    )
    monkeypatch.setattr(
        mms_core,
        "_load_update_check_cache",
        lambda: {
            "latest_tag": "v1.16.6",
            "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"],
        },
    )
    monkeypatch.setattr(mms_core, "_save_update_check_cache", lambda payload: saved.update(payload))
    monkeypatch.setattr(mms_core.time, "time", lambda: 1_000.0)

    notice = mms_core._update_notice()

    assert notice is not None
    assert notice["latest_tag"] == "v1.16.6"
    assert notice["gap_count"] == 3
    assert saved["last_prompted_for"] == "v1.16.6"


def test_update_notice_skips_when_gap_is_below_threshold(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"source": "install.sh", "installed_version": "v1.16.4"},
    )
    monkeypatch.setattr(
        mms_core,
        "_load_update_check_cache",
        lambda: {
            "latest_tag": "v1.16.6",
            "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4"],
        },
    )

    assert mms_core._update_notice() is None


def test_update_notice_still_prompts_major_upgrade_without_cached_gap(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"source": "install.sh", "installed_version": "v1.16.6"},
    )
    monkeypatch.setattr(mms_core, "_load_update_check_cache", lambda: {"latest_tag": "v2.0.0"})
    monkeypatch.setattr(mms_core, "_save_update_check_cache", lambda payload: None)
    monkeypatch.setattr(mms_core.time, "time", lambda: 2_000.0)

    notice = mms_core._update_notice()

    assert notice is not None
    assert notice["latest_tag"] == "v2.0.0"
    assert notice["gap_count"] is None


def test_update_notice_throttles_same_target_version(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"source": "install.sh", "installed_version": "v1.16.3"},
    )
    monkeypatch.setattr(
        mms_core,
        "_load_update_check_cache",
        lambda: {
            "latest_tag": "v1.16.6",
            "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"],
            "last_prompted_for": "v1.16.6",
            "last_prompted_at": 1_000.0,
        },
    )
    monkeypatch.setattr(mms_core.time, "time", lambda: 1_100.0)

    assert mms_core._update_notice() is None


def test_update_notice_ignores_non_install_sources(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"source": "manual", "installed_version": "v1.16.3"},
    )
    monkeypatch.setattr(
        mms_core,
        "_load_update_check_cache",
        lambda: {
            "latest_tag": "v1.16.6",
            "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"],
        },
    )

    assert mms_core._update_notice() is None


def test_update_notice_supports_legacy_install_metadata_without_source(monkeypatch):
    import mms_core

    monkeypatch.setattr(mms_core.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(mms_core.sys, "stdout", _FakeTTY())
    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {"install_channel": "latest-tag", "installed_version": "v1.16.3"},
    )
    monkeypatch.setattr(
        mms_core,
        "_load_update_check_cache",
        lambda: {
            "latest_tag": "v1.16.6",
            "semver_tags": ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"],
        },
    )
    monkeypatch.setattr(mms_core, "_save_update_check_cache", lambda payload: None)
    monkeypatch.setattr(mms_core.time, "time", lambda: 3_000.0)

    notice = mms_core._update_notice()

    assert notice is not None
    assert notice["gap_count"] == 3


def test_about_cli_upgrade_commands_are_individual():
    import mms_core

    assert mms_core._cli_upgrade_shell_command("codex") == "npm install -g @openai/codex@latest"
    assert mms_core._cli_upgrade_shell_command("claude") == "npm install -g @anthropic-ai/claude-code@latest"
