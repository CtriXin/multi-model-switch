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
    assert mms_core._rescue_hot_fallback_enabled_cfg(cfg) is False

    cfg, applied = mms_core._set_rescue_hot_fallback_enabled(cfg, enabled=True)

    assert applied is True
    assert mms_core._rescue_hot_fallback_enabled_cfg(cfg) is True
    assert "enable_hot_fallback" not in cfg["rescue"]

    legacy_cfg = {"rescue": {"fallback_model": "fallback-model", "enable_hot_fallback": True}}
    assert mms_core._rescue_hot_fallback_enabled_cfg(legacy_cfg) is True

    mms_core._set_rescue_default_fallback(cfg, model="")

    assert mms_core._rescue_default_fallback(cfg) == {"model": "", "cli": ""}
    assert mms_core._rescue_hot_fallback_enabled_cfg(cfg) is False
    assert "enable_hot_fallback" not in cfg["rescue"]


def test_rescue_landing_prioritizes_fallback_settings_without_packets() -> None:
    import mms_core

    info_lines, actions = mms_core._rescue_landing_tui_payload(
        "deepseek-v4-flash",
        [],
    )
    action_ids = [action_id for action_id, _label in actions]
    info = dict(info_lines)

    assert info["全局默认"] == "deepseek-v4-flash"
    assert info["Hot fallback"] == "关闭"
    assert info["生效范围"] == "MMS 全局默认；bridge 失败时读取"
    assert info["最近失败"] == "没有 packet"
    assert info["最近 fallback 尝试"] == "-"
    assert action_ids[:3] == ["choose_route_default", "manual_default", "clear_default"]
    assert "enable_hot_fallback" in action_ids
    assert "view_packets" not in action_ids

    enabled_info, enabled_actions = mms_core._rescue_landing_tui_payload(
        "deepseek-v4-flash",
        [],
        hot_fallback_enabled=True,
    )
    assert dict(enabled_info)["Hot fallback"] == "开启"
    assert "disable_hot_fallback" in [action_id for action_id, _label in enabled_actions]


def test_rescue_landing_shows_packets_as_secondary_action() -> None:
    import mms_core

    info_lines, actions = mms_core._rescue_landing_tui_payload(
        "未设置",
        [
            {
                "created_at": "2026-05-23T09:10:11+08:00",
                "failed_model": "gpt-5.5",
                "status_code": 429,
            }
        ],
    )
    action_ids = [action_id for action_id, _label in actions]
    info = dict(info_lines)

    assert info["全局默认"] == "未设置"
    assert "2026-05-23 09:10:11" in info["最近失败"]
    assert "gpt-5.5" in info["最近失败"]
    assert action_ids.index("choose_route_default") < action_ids.index("view_packets")
    assert action_ids.index("manual_default") < action_ids.index("view_packets")


def test_rescue_landing_shows_latest_hot_fallback_event() -> None:
    import mms_core

    info_lines, _actions = mms_core._rescue_landing_tui_payload(
        "deepseek-v4-flash",
        [],
        {
            "type": "fallback",
            "model": "deepseek-v4-flash",
            "at": "2026-05-24T01:02:03+08:00",
            "note": "rescue_hot_fallback from=gpt-5.5 status=503 provider=newapi-deepseek",
        },
    )
    info = dict(info_lines)

    assert "2026-05-24 01:02:03" in info["最近 fallback 尝试"]
    assert "deepseek-v4-flash" in info["最近 fallback 尝试"]
    assert "rescue_hot_fallback" in info["最近 fallback 尝试"]


def test_rescue_result_payloads_are_compact_and_safe() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    title, rows, note = mms_core._rescue_default_fallback_report_payload("deepseek-v4-flash")
    hot_title, hot_rows, hot_note = mms_core._rescue_default_fallback_report_payload(
        "deepseek-v4-flash",
        hot_fallback_enabled=True,
    )
    demo_title, demo_rows, _demo_note = mms_core._rescue_demo_packet_report_payload(
        {"artifacts": {"markdown": "/tmp/rescue.md", "json": "/tmp/rescue.json"}}
    )
    handover_title, handover_rows, handover_note = mms_core._rescue_handover_report_payload(
        {"artifacts": {"markdown": "/tmp/handover.md", "latest_markdown": "/tmp/latest.md"}},
        "deepseek-v4-flash",
    )

    assert title == "全局 fallback 已设置"
    assert ("Model", "deepseek-v4-flash") in rows
    assert ("Hot fallback", "关闭") in rows
    assert "只记录 rescue / fallback handoff" in note
    assert hot_title == "全局 fallback 已设置"
    assert ("Hot fallback", "开启") in hot_rows
    assert "routed model" in hot_note
    assert demo_title == "测试 rescue packet 已生成"
    assert ("rescue.md", "/tmp/rescue.md") in demo_rows
    assert handover_title == "fallback handover 已生成"
    assert ("Model", "deepseek-v4-flash") in handover_rows
    assert "不切换当前 session" in handover_note


def test_settings_result_report_uses_tui_when_available(monkeypatch) -> None:
    import builtins
    import mms_core

    calls = []
    printed = []
    mms_core._SETTINGS_RESULT_RENDERED_TUI = False

    monkeypatch.setattr(mms_core, "_settings_result_tui_available", lambda: True)
    monkeypatch.setattr(
        mms_core,
        "_select_settings_result_tui",
        lambda title, rows, note="", ok=True: calls.append((title, list(rows), note, ok)) or "back",
    )
    monkeypatch.setattr(mms_core.console, "print", lambda *args, **kwargs: printed.append((args, kwargs)))
    monkeypatch.setattr(builtins, "input", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pause should be skipped after TUI result")))

    mms_core._print_settings_result_report(
        "hot fallback 已开启",
        [("Hot fallback", "开启")],
        "开关保存到 [rescue].hot_fallback_enabled。",
    )
    mms_core._pause_after_tui_report("按 Enter 返回设置")

    assert calls == [
        (
            "hot fallback 已开启",
            [("Hot fallback", "开启")],
            "开关保存到 [rescue].hot_fallback_enabled。",
            True,
        )
    ]
    assert printed == []
    assert mms_core._SETTINGS_RESULT_RENDERED_TUI is False


def test_settings_result_tui_payload_matches_settings_card_contract() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    title, info_lines, actions = mms_core._settings_result_tui_payload(
        "hot fallback 已开启",
        [("Hot fallback", "开启"), ("前置条件", "[rescue].fallback_model")],
        "关闭时只记录 rescue / handoff",
    )

    assert title == "✓ hot fallback 已开启"
    assert ("状态", "成功") in info_lines
    assert ("Hot fallback", "开启") in info_lines
    assert ("说明", "关闭时只记录 rescue / handoff") in info_lines
    assert actions == [("back", "返回")]


def test_registry_truth_tui_payload_uses_chinese_labels() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    title, info_lines, actions = mms_core._registry_truth_tui_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "counts": {"source_snapshot": 2, "model_identity": 39, "model_fact": 338},
            "source_freshness": {"due_count": 1},
            "latest_source_snapshot": {"source_path": "https://openrouter.ai/api/v1/models"},
        }
    )
    info_labels = [label for label, _value in info_lines]
    action_labels = [label for _action_id, label in actions]

    assert title == "模型真源 / Registry Truth"
    assert info_labels[:6] == ["DB", "来源快照", "模型身份", "模型事实", "待刷新来源", "最新来源"]
    assert action_labels[:4] == ["检查 Source Staleness", "刷新到期 Sources", "定时刷新 Dry Run", "定时刷新 No Network"]
    assert "Registry Doctor / 状态" in action_labels


def test_registry_result_payloads_are_chinese_first_and_compact() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    title, rows, note = mms_core._registry_scheduled_refresh_report_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "dry_run": True,
            "source_due_count": 2,
            "source_refresh": {"imported_count": 0},
            "openrouter_due": False,
            "openrouter_fetch": {"reason": "not fetched in no-network mode"},
        }
    )
    diff_title, diff_rows, diff_note = mms_core._registry_openrouter_diff_report_payload(
        {
            "change_count": 2,
            "stored_count": 2,
            "missing_reference_count": 1,
            "untracked_catalog_count": 3,
            "changes": [
                {
                    "field_key": "context_window",
                    "model_key": "gpt-5.5",
                    "provider_model_id": "openai/gpt-5.5",
                }
            ],
        }
    )

    assert title == "定时刷新结果"
    assert ("到期 Source", 2) in rows
    assert "不接入 startup" in note
    assert diff_title == "OpenRouter Candidate Diff"
    assert ("缺少 reference", 1) in diff_rows
    assert "不改变当前 runtime defaults" in diff_note
    assert mms_core._compact_tui_report_value("x" * 120, max_len=20) == "x" * 19 + "…"


def test_about_and_snapshot_guard_tui_payloads_use_chinese_labels() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    about_title, about_info, about_actions = mms_core._about_tui_payload(
        {
            "version_info": {
                "release": "v9.9.9",
                "git_branch": "main",
                "git_commit": "abc123",
                "install_channel": "latest-tag",
                "source": "install.sh",
            },
            "mms": {"current": "v9.9.9", "latest": "v9.9.9", "status": "最新"},
            "clis": {
                "codex": {"label": "codex-cli 0.133.0", "latest": "0.133.0", "status": "最新"},
                "claude": {"label": "2.1.148 (Claude Code)", "latest": "2.1.148", "status": "最新"},
            },
        }
    )
    guard_title, guard_info, guard_actions = mms_core._snapshot_guard_tui_payload()

    assert about_title == "关于 / About"
    assert [label for label, _value in about_info] == [
        "MMS",
        "MMS 最新",
        "Codex",
        "Codex 最新",
        "Claude",
        "Claude 最新",
        "Git",
        "安装",
        "Config",
    ]
    assert about_actions == [("refresh_versions", "刷新版本检查"), ("back", "返回")]
    assert guard_title == "启动快照 / Snapshot Guard"
    assert guard_info[0][0] == "用途"
    assert [label for _action_id, label in guard_actions] == ["查看当前 Snapshot 状态", "接受当前 Snapshot", "返回"]


def test_about_tui_payload_surfaces_upgrade_actions_for_outdated_versions() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    _title, _info, actions = mms_core._about_tui_payload(
        {
            "version_info": {"release": "v3.0.0"},
            "mms": {"current": "v3.0.0", "latest": "v3.0.2", "status": "有新版 v3.0.2", "outdated": True},
            "clis": {
                "codex": {"label": "codex-cli 0.132.0", "latest": "0.133.0", "status": "有新版 0.133.0", "outdated": True},
                "claude": {"label": "2.1.148 (Claude Code)", "latest": "2.1.148", "status": "最新", "outdated": False},
            },
        }
    )

    assert ("upgrade_mms", "升级 MMS") in actions
    assert ("upgrade_codex_cli", "升级 Codex CLI") in actions
    assert ("upgrade_claude_cli", "升级 Claude CLI") not in actions
    assert ("upgrade_mms_clis", "升级 MMS + Codex/Claude CLI") not in actions


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
    assert "Legacy / emergency-only 模块（默认入口已下线）" in out
    assert "chat/discuss    默认拒绝直接启动" in out
    assert "MMS_ENABLE_LEGACY_CHAT_DISCUSS=1" in out


def test_mms_chat_discuss_direct_commands_are_disabled_by_default(monkeypatch, capsys) -> None:
    import mms_core

    monkeypatch.delenv("MMS_ENABLE_LEGACY_CHAT_DISCUSS", raising=False)
    monkeypatch.setattr(sys, "argv", ["mms", "chat"])
    monkeypatch.setattr(mms_core, "load_config", lambda: {"user": {}, "recommend": {}})
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: pytest.fail("snapshot should not run"))
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: pytest.fail("routes export should not run"))

    mms_core.main()

    out = capsys.readouterr().out
    assert "`mms chat` 已从默认入口下线" in out
    assert "MMS_ENABLE_LEGACY_CHAT_DISCUSS=1" in out


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
