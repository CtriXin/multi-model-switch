from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_tui_settings_action_descriptors_have_stable_labels() -> None:
    from mms_tui_settings_actions import get_tui_settings_action, list_tui_settings_actions

    labels = {descriptor.action_id: descriptor.label for descriptor in list_tui_settings_actions()}

    assert labels == {
        "refresh-sources": "Refresh Sources",
        "probe-selected": "Probe Selected / Small Health Check",
        "registry-doctor": "Registry Doctor",
        "recoverable-models": "Recoverable Models",
        "interrupted-sessions": "Interrupted Sessions / Rescue",
        "export-approved-bundle": "Export Approved Bundle",
        "legacy-tools-emergency-debug": "Legacy Tools / Emergency Debug",
        "usage-health-overlay": "Usage / Last Used / Health overlay view",
    }
    assert get_tui_settings_action("export-approved-bundle").requires_confirmation is True
    assert get_tui_settings_action("legacy-tools-emergency-debug").emergency_access is True


def test_legacy_chat_and_discuss_help_expose_migration_notice(capsys) -> None:
    import mms_chat
    import mms_discuss

    with pytest.raises(SystemExit) as chat_exit:
        mms_chat.parse_chat_args(["--help"])
    with pytest.raises(SystemExit) as discuss_exit:
        mms_discuss.parse_discuss_args(["--help"])

    assert chat_exit.value.code == 0
    assert discuss_exit.value.code == 0
    out = capsys.readouterr().out
    assert "mms chat 是 legacy/maintenance-only 子命令" in out
    assert "mms discuss 是 legacy/maintenance-only 子命令" in out
    assert "`mms` TUI" in out
    assert "TUI Settings / Maintenance" in out


def test_mmc_help_is_migration_shim_not_live_launch(capsys) -> None:
    import mmc_core

    with pytest.raises(SystemExit) as exc:
        mmc_core.main(["--help"])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "mmc public command is retired" in out
    assert "launcher-owned OAuth Claude adapter" in out


def test_mms_help_keeps_review_launch_outside_legacy_bucket(monkeypatch, capsys) -> None:
    import mms_core

    monkeypatch.setattr(sys, "argv", ["mms", "--help"])
    monkeypatch.setattr(mms_core, "load_config", lambda: {"user": {}, "recommend": {}})

    with pytest.raises(SystemExit) as exc:
        mms_core.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "review-launch" in out
    assert "Legacy / emergency-only" in out
    assert "chat ...        legacy/maintenance-only" in out
    assert "discuss ...     legacy/maintenance-only" in out


def test_mms_default_path_still_uses_tui_launcher_handler(monkeypatch) -> None:
    import mms_core

    calls: list[str] = []
    cfg = {"user": {}, "recommend": {}}
    provider = {"id": "default-provider"}
    scenes = {"Code": {"cli": "claude", "emoji": ">", "desc": "Code"}}

    monkeypatch.setattr(sys, "argv", ["mms"])
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda value: value)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda _cfg, _provider: (provider, {"models": []}))
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: ["claude"])
    monkeypatch.setattr(mms_core, "_filter_scenes_by_visible_clis", lambda _clis: scenes)
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "_use_tui", lambda: True)
    monkeypatch.setattr(mms_core, "setup_wizard", lambda *_args, **_kwargs: pytest.fail("setup_wizard should not run"))
    monkeypatch.setattr(mms_core, "select_scene_fallback", lambda *_args, **_kwargs: pytest.fail("fallback should not run"))

    def fake_tui_handler(*_args, **_kwargs):
        calls.append("tui")
        return True

    monkeypatch.setattr(mms_core, "_handle_tui_scene_selection", fake_tui_handler)

    mms_core.main()

    assert calls == ["tui"]


def test_review_launch_is_not_legacy_cleanup_target() -> None:
    from mms_tui_settings_actions import list_tui_settings_actions

    text = (ROOT / "docs" / "LEGACY_SURFACE_CLEANUP.md").read_text(encoding="utf-8")
    replacements = {
        replacement
        for descriptor in list_tui_settings_actions()
        for replacement in descriptor.replacement_for
    }

    assert "| Review launch |" in text
    assert "not a legacy chat/discuss cleanup target" in text
    assert "mms review-launch" not in replacements


def test_legacy_modules_remain_importable_until_physical_delete_phase() -> None:
    import mmc_core
    import mms_action_bar
    import mms_chat
    import mms_discuss
    import mms_usage

    assert mms_chat.chat_main
    assert mms_discuss.discuss_main
    assert mms_action_bar.run_chat_loop
    assert mms_usage.usage_main
    assert mmc_core.main
