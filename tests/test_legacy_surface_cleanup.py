from __future__ import annotations

import json
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


def test_live_settings_menu_exposes_rescue_entry(monkeypatch) -> None:
    import mms_tui

    items = mms_tui._settings_menu()
    ids = [item["id"] for item in items]

    assert "rescue" in ids
    assert "registry" in ids
    assert "guard" in ids
    assert "recommend" not in ids
    assert "fake_upstream" not in ids


def test_about_release_version_prefers_installed_version(monkeypatch) -> None:
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_version_meta",
        lambda: {
            "installed_version": "v9.9.9",
            "installed_ref": "release-ref",
            "install_channel": "latest-tag",
            "source": "install.sh",
        },
    )
    monkeypatch.setattr(mms_core, "_git_output", lambda args: "git-value")

    info = mms_core._release_version_info()

    assert info["release"] == "v9.9.9"
    assert info["install_channel"] == "latest-tag"
    assert info["source"] == "install.sh"


def test_rescue_fallback_candidates_use_recent_models_before_config(monkeypatch) -> None:
    import mms_core

    monkeypatch.setattr(
        mms_core,
        "_load_usage_stats",
        lambda: {
            "last_by_cli": {
                "codex": {"model": "recent-model", "last_used_at": "2026-05-22T10:00:00Z"},
            },
            "sources": {
                "provider:codex:relay": {
                    "models": {"older-model": 2, "failed-model": 9},
                    "model_last_used_at": {
                        "older-model": "2026-05-21T10:00:00Z",
                        "failed-model": "2026-05-22T11:00:00Z",
                    },
                }
            },
        },
    )
    cfg = {
        "providers": [
            {
                "enabled": True,
                "extra_models": ["configured-model"],
                "fallback_models": ["fallback-model"],
            }
        ]
    }

    candidates = mms_core._rescue_fallback_model_candidates(
        cfg,
        {"failed_model": "failed-model"},
        limit=4,
    )

    assert candidates[:4] == ["recent-model", "older-model", "configured-model", "fallback-model"]


def test_rescue_fallback_candidates_include_routed_models(monkeypatch, tmp_path: Path) -> None:
    import mms_core

    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "failed-model": {
                        "primary": {
                            "provider_id": "broken",
                            "openai_base_url": "https://broken.example/v1",
                            "api_key": "sk-test-failed",
                            "model_id": "failed-model",
                        },
                        "fallbacks": [],
                    },
                    "deepseek-v4-flash": {
                        "primary": {
                            "provider_id": "deepseek",
                            "openai_base_url": "https://deepseek.example/v1",
                            "api_key": "sk-test-deepseek",
                            "model_id": "deepseek-v4-flash",
                        },
                        "fallbacks": [],
                    },
                    "no-openai-route": {
                        "primary": {
                            "provider_id": "anthropic-only",
                            "anthropic_base_url": "https://anthropic.example",
                            "api_key": "sk-test-anthropic",
                            "model_id": "no-openai-route",
                        },
                        "fallbacks": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_core, "_load_usage_stats", lambda: {"last_by_cli": {}, "sources": {}})

    route_candidates = mms_core._rescue_route_fallback_model_candidates(
        config_dir=tmp_path,
        failed_model="failed-model",
    )
    all_candidates = mms_core._rescue_fallback_model_candidates(
        {"providers": []},
        {"failed_model": "failed-model"},
        limit=10,
    )

    assert "deepseek-v4-flash" in route_candidates
    assert "deepseek-v4-flash" in all_candidates
    assert "failed-model" not in route_candidates
    assert "no-openai-route" not in route_candidates


def test_rescue_default_fallback_config_roundtrip() -> None:
    import mms_core

    cfg: dict = {}
    mms_core._set_rescue_default_fallback(cfg, model="fallback-model")

    assert mms_core._rescue_default_fallback(cfg) == {"model": "fallback-model", "cli": ""}

    mms_core._set_rescue_default_fallback(cfg, model="")

    assert mms_core._rescue_default_fallback(cfg) == {"model": "", "cli": ""}


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
    assert "registry ..." in out
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
