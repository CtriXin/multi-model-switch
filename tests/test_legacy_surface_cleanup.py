from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _write_latest_approved_router_manifest(
    config_root: Path,
    *,
    router_payload: dict,
    profile_payload: dict | None = None,
    sha_override: str = "",
) -> None:
    import mms_registry

    generated = config_root / "generated"
    router_path = generated / "model-routes.json"
    lineup_path = generated / "model-routes.lineup.json"
    profile_path = generated / "provider-profiles.generated.json"
    policy_path = generated / "model-policy.effective.json"
    capabilities_path = generated / "model-capabilities.approved.json"
    mms_registry.write_json_atomic(router_path, router_payload)
    router_hash = hashlib.sha256(router_path.read_bytes()).hexdigest()
    mms_registry.write_json_atomic(lineup_path, {"version": 1, "routes": {}})
    mms_registry.write_json_atomic(profile_path, profile_payload or {"schema_version": 1, "profiles": {}})
    mms_registry.write_json_atomic(policy_path, {"version": 1, "models": {}})
    mms_registry.write_json_atomic(capabilities_path, {"schema": "mms.model_capabilities.approved.v1", "models": []})
    mms_registry.export_latest_approved_bundle_manifest(
        generated / "model-registry.latest-approved.json",
        bundle_revision="bundle_rescue_test",
        capability_revision="cap_rescue_test",
        route_revision="route_rescue_test",
        policy_revision="policy_rescue_test",
        profile_revision="profile_rescue_test",
        files={
            "router": {"path": router_path, "canonical_path": "generated/model-routes.json", "sha256": sha_override or router_hash, "sensitivity": "secret"},
            "lineup": {"path": lineup_path, "canonical_path": "generated/model-routes.lineup.json", "sensitivity": "non-secret"},
            "profile": {"path": profile_path, "canonical_path": "generated/provider-profiles.generated.json", "sensitivity": "non-secret"},
            "policy": {"path": policy_path, "canonical_path": "generated/model-policy.effective.json", "sensitivity": "non-secret"},
            "capabilities": {"path": capabilities_path, "canonical_path": "generated/model-capabilities.approved.json", "sensitivity": "non-secret"},
        },
    )


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
    routes_export = next(item for item in items if item["id"] == "routes_export")
    assert "Legacy" in routes_export["label"]
    assert "model-routes.json" in routes_export["desc"]
    assert "v2" in routes_export["desc"]


def test_about_release_version_prefers_installed_version(monkeypatch) -> None:
    import mms_core

    monkeypatch.delenv("MMS_COMMAND_NAME", raising=False)
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
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
    assert info["release_track"] == "stable"
    assert info["release_track_version"] == "3.x-stable"
    assert info["release_track_label"] == "3.x Stable"


def test_release_version_info_uses_command_env_for_dev_and_canary_tracks(monkeypatch) -> None:
    import mms_core

    monkeypatch.setenv("MMS_COMMAND_NAME", "mmg")
    monkeypatch.delenv("MMS_PREVIEW_MODE", raising=False)
    monkeypatch.setattr(mms_core, "_load_version_meta", lambda: {"install_channel": "dev", "installed_ref": "dev"})
    monkeypatch.setattr(mms_core, "_git_output", lambda args: "dev" if args[0] == "branch" else "abc123")

    canary = mms_core._release_version_info()

    assert canary["release_track"] == "canary"
    assert canary["release_track_version"] == "4.0.0-canary"
    assert canary["release_track_label"] == "4.0 Canary Preview"

    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "_load_version_meta", lambda: {"install_channel": "canary", "installed_ref": "canary"})
    monkeypatch.setattr(mms_core, "_git_output", lambda args: "canary" if args[0] == "branch" else "abc123")

    dev = mms_core._release_version_info()

    assert dev["release_track"] == "dev"
    assert dev["release_track_version"] == "4.0.0-dev"
    assert dev["release_track_label"] == "4.0 Dev Preview"


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


def test_rescue_route_candidates_read_verified_latest_approved_router(tmp_path: Path) -> None:
    import mms_core

    _write_latest_approved_router_manifest(
        tmp_path,
        router_payload={
            "version": 1,
            "routes": {
                "verified-fallback": {
                    "primary": {
                        "provider_id": "verified",
                        "openai_base_url": "https://verified.example/v1",
                        "api_key": "sk-test-verified",
                        "model_id": "verified-fallback",
                    },
                    "fallbacks": [],
                }
            },
        },
    )
    (tmp_path / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "stale-root": {
                        "primary": {
                            "provider_id": "stale",
                            "openai_base_url": "https://stale.example/v1",
                            "api_key": "sk-test-stale",
                            "model_id": "stale-root",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    candidates = mms_core._rescue_route_fallback_model_candidates(config_dir=tmp_path)

    assert candidates == ["verified-fallback"]


def test_rescue_route_candidates_fail_closed_on_invalid_latest_approved_manifest(tmp_path: Path) -> None:
    import mms_core

    _write_latest_approved_router_manifest(
        tmp_path,
        router_payload={
            "version": 1,
            "routes": {
                "untrusted-generated": {
                    "primary": {
                        "provider_id": "untrusted",
                        "openai_base_url": "https://untrusted.example/v1",
                        "api_key": "sk-test-untrusted",
                        "model_id": "untrusted-generated",
                    },
                    "fallbacks": [],
                }
            },
        },
        sha_override="0" * 64,
    )
    (tmp_path / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "stale-root": {
                        "primary": {
                            "provider_id": "stale",
                            "openai_base_url": "https://stale.example/v1",
                            "api_key": "sk-test-stale",
                            "model_id": "stale-root",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    candidates = mms_core._rescue_route_fallback_model_candidates(config_dir=tmp_path)

    assert candidates == []


def test_rescue_route_candidates_fail_closed_on_missing_preview_manifest(tmp_path: Path) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    generated = preview_root / "generated"
    generated.mkdir(parents=True)
    (generated / "model-routes.json").write_text(
        json.dumps(
            {
                "version": 1,
                "routes": {
                    "stale-preview-route": {
                        "primary": {
                            "provider_id": "stale",
                            "openai_base_url": "https://stale.example/v1",
                            "api_key": "sk-test-stale",
                            "model_id": "stale-preview-route",
                        },
                        "fallbacks": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    candidates = mms_core._rescue_route_fallback_model_candidates(config_dir=preview_root)

    assert candidates == []


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


def test_model_source_status_tui_payload_is_read_only_chinese_first() -> None:
    import mms_core
    import mms_i18n

    mms_i18n.set_language("zh")
    title, info_lines, actions = mms_core._model_source_status_tui_payload(
        {
            "result": "NOT_READY",
            "status": "needs_init",
            "ready": False,
            "headline": "Preview root needs registry DB initialization.",
            "next_action": {"label": "Initialize preview root", "command": "./mmf preview init --json"},
            "root": {"config_root": "/tmp/mms-next", "mode": "preview"},
            "registry_db": {
                "path": "/tmp/mms-next/registry/model-registry.sqlite",
                "status": "missing",
                "counts": {"source_snapshot": 0, "model_fact": 0, "provider_route": 0},
            },
            "legacy_import": {
                "conflict_count": 2,
                "candidates": {"status": "not_imported", "provider_route_count": 0},
                "next_action": "review_conflicts_before_import",
            },
            "generated_bundle": {
                "status": "missing",
                "verified": False,
                "runtime_ready_status": "unknown",
                "router_missing_api_key_count": 0,
            },
        }
    )
    report_title, rows, note = mms_core._model_source_status_report_payload(
        {
            "result": "NOT_READY",
            "status": "needs_init",
            "ready": False,
            "headline": "Preview root needs registry DB initialization.",
            "next_action": {"label": "Initialize preview root", "command": "./mmf preview init --json"},
            "root": {"config_root": "/tmp/mms-next", "mode": "preview"},
            "registry_db": {"path": "/tmp/mms-next/registry/model-registry.sqlite", "status": "missing", "counts": {}},
            "legacy_import": {
                "conflict_count": 2,
                "candidates": {"status": "not_imported", "provider_route_count": 0},
                "next_action": "review_conflicts_before_import",
            },
            "generated_bundle": {
                "status": "missing",
                "verified": False,
                "runtime_ready_status": "unknown",
                "router_missing_api_key_count": 0,
            },
        }
    )

    assert title == "模型真源 / Registry Truth"
    assert info_lines[:8] == [
        ("结果", "NOT_READY"),
        ("状态", "needs_init"),
        ("Ready", "no"),
        ("一句话", "Preview root needs registry DB initialization."),
        ("Root", "/tmp/mms-next"),
        ("Mode", "preview"),
        ("DB", "/tmp/mms-next/registry/model-registry.sqlite"),
        ("DB 状态", "missing"),
    ]
    assert actions[0] == ("model_source_status", "查看 Model Source Status")
    assert actions[1] == ("consumer_bundle_status", "查看 Consumer Bundle")
    assert actions[2] == ("registry_v2_save_plan", "查看 v2 Save Plan")
    assert actions[3] == ("config_v2_promotion_plan", "查看 Promote Plan")
    assert actions[4] == ("config_v2_release_readiness", "查看 4.0 Readiness")
    assert actions[5] == ("preview_doctor", "运行 Preview Doctor")
    assert report_title == "Model Source Status"
    assert ("Legacy 冲突", 2) in rows
    assert ("Legacy 候选状态", "not_imported") in rows
    assert ("Legacy 候选 routes", 0) in rows
    assert ("Bundle runtime", "unknown") in rows
    assert ("Router 缺失 key", 0) in rows
    assert ("下一步", "Initialize preview root") in rows
    assert ("建议命令", "./mmf preview init --json") in rows
    assert "只读视图" in note

    consumer_title, consumer_rows, consumer_note = mms_core._consumer_bundle_status_report_payload(
        {
            "result": "READY",
            "status": "ok",
            "verified": True,
            "consumer_entrypoint": "/tmp/mms-next/generated/model-registry.latest-approved.json",
            "root": {"config_root": "/tmp/mms-next"},
            "component_revisions": {
                "bundle": "bundle_abc",
                "route": "route_abc",
                "policy": "policy_abc",
                "profile": "profile_abc",
            },
            "files": {
                "router": {"path": "/tmp/mms-next/generated/model-routes.json", "sha256": "abc"},
                "policy": {"path": "/tmp/mms-next/generated/model-policy.effective.json", "sha256": "def"},
            },
            "consumer_rules": ["read manifest first", "do not query SQLite directly"],
            "next_action": {"label": "Consume verified bundle", "command": "/tmp/mms-next/generated/model-registry.latest-approved.json"},
        }
    )
    assert consumer_title == "Consumer Bundle Status"
    assert consumer_rows[:5] == [
        ("结果", "READY"),
        ("状态", "ok"),
        ("Bundle 校验", "yes"),
        ("入口", "/tmp/mms-next/generated/model-registry.latest-approved.json"),
        ("Root", "/tmp/mms-next"),
    ]
    assert ("Bundle revision", "bundle_abc") in consumer_rows
    assert ("Route revision", "route_abc") in consumer_rows
    assert ("Policy revision", "policy_abc") in consumer_rows
    assert ("Profile revision", "profile_abc") in consumer_rows
    assert ("文件数", 2) in consumer_rows
    assert ("消费规则", "read manifest first / do not query SQLite directly") in consumer_rows
    assert ("下一步", "Consume verified bundle") in consumer_rows
    assert ("建议命令", "/tmp/mms-next/generated/model-registry.latest-approved.json") in consumer_rows
    assert "只读视图" in consumer_note
    assert "不读取 SQLite" in consumer_note

    plan_title, plan_rows, plan_note = mms_core._registry_v2_save_plan_report_payload(
        {
            "root": {"config_root": "/tmp/mms-next", "mode": "preview"},
            "execution_state": "plan_only",
            "actual_save_enabled": False,
            "db": {
                "path": "/tmp/mms-next/registry/model-registry.sqlite",
                "exists": True,
                "backup_dir": "/tmp/mms-next/backups/db",
                "would_backup_existing_db": True,
            },
            "would_write": {
                "db_candidate_revision": True,
                "secret_backend": False,
                "generated_latest_approved_bundle": True,
                "legacy_compat_files": {"config_toml": True, "model_policy_json": False, "credentials_sh": False},
            },
            "ordered_steps": ["backup preview registry DB", "verify manifest hashes"],
            "blocked_reasons": [],
            "plan_json": {"name": "webui-plan.json", "redacted": True, "secrets_included": False},
            "apply_plan": {
                "webui_button": "写入预览 DB + 发布",
                "cli_apply_command": "./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json",
            },
            "next_implementation_step": "wire save later",
        }
    )

    assert plan_title == "Registry v2 Save Plan"
    assert ("执行状态", "plan_only") in plan_rows
    assert ("实际保存启用", "no") in plan_rows
    assert ("将备份 DB", "yes") in plan_rows
    assert ("Secret backend", "no") in plan_rows
    assert ("阻塞原因", "-") in plan_rows
    assert ("Plan JSON", "webui-plan.json") in plan_rows
    assert ("Plan JSON 密钥", "redacted") in plan_rows
    assert ("WebUI 写入", "写入预览 DB + 发布") in plan_rows
    assert ("CLI 写入命令", "./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json") in plan_rows
    assert "只读计划" in plan_note

    promotion_title, promotion_rows, promotion_note = mms_core._config_v2_promotion_plan_report_payload(
        {
            "result": "READY_FOR_HUMAN_PROMOTION_REVIEW",
            "status": "human_gate",
            "ready_for_human_review": True,
            "preview": {
                "root": {"config_root": "/tmp/mms-next"},
                "check": {"result": "READY", "ready": True},
                "bundle": {
                    "verified": True,
                    "entrypoint": "/tmp/mms-next/generated/model-registry.latest-approved.json",
                },
            },
            "stable": {"root": {"config_root": "/tmp/mms"}},
            "promotion_safety": {
                "stable_write_policy": "human_only",
                "apply_enabled": False,
                "requires_backup": True,
            },
            "stable_backup_plan": {
                "requires_backup_before_apply": True,
                "would_create_backup": False,
            },
            "bundle_comparison": {
                "comparison_status": "stable_bundle_missing",
                "preview": {"bundle_revision": "bundle_preview"},
                "stable": {"status": "missing"},
            },
            "blocked_reasons": ["stable_root_human_only", "promotion_apply_not_implemented"],
            "next_action": {"label": "Human gate: review promotion plan", "command": "./mmf promote --json"},
        }
    )

    assert promotion_title == "Config v2 Promote Plan"
    assert ("结果", "READY_FOR_HUMAN_PROMOTION_REVIEW") in promotion_rows
    assert ("状态", "human_gate") in promotion_rows
    assert ("Ready for review", "yes") in promotion_rows
    assert ("Preview root", "/tmp/mms-next") in promotion_rows
    assert ("Stable root", "/tmp/mms") in promotion_rows
    assert ("Bundle 校验", "yes") in promotion_rows
    assert ("Stable 写策略", "human_only") in promotion_rows
    assert ("Apply 启用", "no") in promotion_rows
    assert ("必须备份", "yes") in promotion_rows
    assert ("本命令创建备份", "no") in promotion_rows
    assert ("Bundle 对比", "stable_bundle_missing") in promotion_rows
    assert ("Preview bundle", "bundle_preview") in promotion_rows
    assert ("Stable bundle", "missing") in promotion_rows
    assert ("阻塞原因", "stable_root_human_only, promotion_apply_not_implemented") in promotion_rows
    assert ("下一步", "Human gate: review promotion plan") in promotion_rows
    assert "human gate" in promotion_note
    assert "不写 stable root" in promotion_note

    readiness_title, readiness_rows, readiness_note = mms_core._config_v2_release_readiness_report_payload(
        {
            "result": "READY_FOR_4_0_HUMAN_GATE",
            "status": "human_gate",
            "release_complete": False,
            "ready_for_human_gate": True,
            "human_gate_required": True,
            "completion_blocker": "stable_promotion_human_gate",
            "config_root": "/tmp/mms-next",
            "stable_config_root": "/tmp/mms",
            "requirements": [
                {"id": "preview_root_selected", "ok": True},
                {"id": "consumer_bundle_verified", "ok": True},
            ],
            "blocked_requirements": [],
            "promotion_plan": {
                "status": "human_gate",
                "apply_enabled": False,
                "blocked_reasons": ["stable_root_human_only", "promotion_apply_not_implemented"],
            },
            "next_action": {"label": "Human gate: review promotion plan", "command": "./mmf promote --json"},
        }
    )

    assert readiness_title == "Config v2 Release Readiness"
    assert ("结果", "READY_FOR_4_0_HUMAN_GATE") in readiness_rows
    assert ("状态", "human_gate") in readiness_rows
    assert ("Release complete", "no") in readiness_rows
    assert ("Ready for human gate", "yes") in readiness_rows
    assert ("Human gate required", "yes") in readiness_rows
    assert ("完成阻塞", "stable_promotion_human_gate") in readiness_rows
    assert ("Preview root", "/tmp/mms-next") in readiness_rows
    assert ("Stable root", "/tmp/mms") in readiness_rows
    assert ("Requirements", "2/2 ok") in readiness_rows
    assert ("Blocked requirements", "-") in readiness_rows
    assert ("Promotion apply", "no") in readiness_rows
    assert ("下一步", "Human gate: review promotion plan") in readiness_rows
    assert "只读审计" in readiness_note
    assert "不改 Claude config" in readiness_note

    doctor_title, doctor_rows, doctor_note = mms_core._preview_doctor_report_payload(
        {
            "result": "NOT_READY",
            "status": "needs_publish",
            "ready": False,
            "config_root": "/tmp/mms-next",
            "counts": {"candidate_provider_routes": 2, "missing_api_keys": 1, "preview_secret_count": 0},
            "bundle": {"verified": False, "runtime_ready_status": "unknown"},
            "next_actions": [{"label": "Publish and verify preview bundle", "command": "./mmf preview publish --json && ./mmf preview verify --json"}],
        }
    )

    assert doctor_title == "Preview Doctor"
    assert ("状态", "needs_publish") in doctor_rows
    assert ("候选 routes", 2) in doctor_rows
    assert ("Router 缺失 key", 1) in doctor_rows
    assert ("下一步", "Publish and verify preview bundle") in doctor_rows
    assert "只读检查" in doctor_note


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


def test_rescue_fallback_report_points_to_latest_approved_router() -> None:
    import mms_core

    _title, rows, _note = mms_core._rescue_default_fallback_report_payload(
        "fallback-model",
        hot_fallback_enabled=True,
    )

    assert ("生效方式", "bridge failure -> latest-approved Router") in rows
    assert all("model-routes.json" not in str(value) for _label, value in rows)


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
        "版本轨道",
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
    monkeypatch.setattr(sys, "argv", ["mms"])
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda value: value)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda _cfg, _provider: (provider, {"models": []}))
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: ["claude"])
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "_use_tui", lambda: True)
    monkeypatch.setattr(mms_core, "setup_wizard", lambda *_args, **_kwargs: pytest.fail("setup_wizard should not run"))

    def fake_tui_handler(*_args, **_kwargs):
        calls.append("tui")
        return True

    monkeypatch.setattr(mms_core, "_handle_tui_launcher_selection", fake_tui_handler)

    mms_core.main()

    assert calls == ["tui"]


def test_mmf_missing_preview_config_does_not_run_legacy_setup(monkeypatch, tmp_path, capsys) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))
    monkeypatch.setattr(sys, "argv", ["mmf"])
    monkeypatch.setattr(mms_core, "load_config", lambda: None)
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "setup_wizard", lambda *_args, **_kwargs: pytest.fail("legacy setup must not run for preview root"))
    monkeypatch.setattr(mms_core, "save_config", lambda *_args, **_kwargs: pytest.fail("preview root must not get legacy config.toml"))

    with pytest.raises(SystemExit) as exc:
        mms_core.main()

    assert exc.value.code == 2
    assert not (preview_root / "config.toml").exists()
    out = capsys.readouterr().out
    assert "Preview root uses v2 DB truth" in out
    assert "mmf preview prepare" in out


def test_mmf_config_mutation_is_blocked_from_legacy_config_path(monkeypatch, tmp_path, capsys) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))
    monkeypatch.setattr(sys, "argv", ["mmf", "config", "provider.default", "demo"])
    monkeypatch.setattr(mms_core, "load_config", lambda: None)
    monkeypatch.setattr(mms_core, "save_config", lambda *_args, **_kwargs: pytest.fail("legacy config write must be blocked"))

    with pytest.raises(SystemExit) as exc:
        mms_core.main()

    assert exc.value.code == 2
    assert not (preview_root / "config.toml").exists()
    out = capsys.readouterr().out
    assert "legacy config.toml writes are disabled" in out
    assert "config apply-plan" in out


def test_mmf_preview_runtime_can_use_verified_bundle_without_legacy_config(monkeypatch, tmp_path) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    _write_latest_approved_router_manifest(
        preview_root,
        router_payload={
            "version": 1,
            "routes": {
                "gpt-preview": {
                    "primary": {
                        "provider_id": "preview-provider",
                        "openai_base_url": "https://preview.example/v1",
                        "api_key": "sk-preview-secret",
                        "model_id": "gpt-preview",
                    },
                    "fallbacks": [],
                }
            },
        },
        profile_payload={
            "schema_version": 1,
            "profiles": {
                "preview-provider": {
                    "name": "Preview Provider",
                    "role": "fallback",
                    "priority": 123,
                    "models_endpoint": "/api/models/info?",
                    "protocols": ["openai_chat_completions"],
                    "supported_clis": ["codex"],
                    "enabled": True,
                }
            },
        },
    )
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))

    cfg = mms_core._load_config_or_preview_bundle()
    provider = mms_core.resolve_provider_context(cfg, "preview-provider")

    assert cfg["_mms_config_source"] == "latest-approved-bundle"
    assert cfg["provider"]["default"] == "preview-provider"
    assert provider["openai_base_url"] == "https://preview.example/v1"
    assert provider["api_key"] == "sk-preview-secret"
    assert provider["name"] == "Preview Provider"
    assert provider["role"] == "fallback"
    assert provider["priority"] == 123
    assert provider["models_endpoint"] == "/api/models/info?"
    assert provider["supported_clis"] == ["codex"]
    assert "gpt-preview" in provider["fallback_models"]
    assert provider["extra_models"] == []
    assert not (preview_root / "config.toml").exists()


def test_mmf_preview_runtime_prefers_verified_bundle_over_legacy_config(monkeypatch, tmp_path) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    (preview_root / "config.toml").write_text(
        """
[provider]
default = "stale-provider"

[[providers]]
id = "stale-provider"
name = "Stale Provider"
enabled = true
protocols = ["openai_chat_completions"]
supported_clis = ["codex"]
default_openai_base_url = "https://stale.example/v1"
fallback_models = ["stale-model"]
""".lstrip(),
        encoding="utf-8",
    )
    _write_latest_approved_router_manifest(
        preview_root,
        router_payload={
            "version": 1,
            "routes": {
                "gpt-preview": {
                    "primary": {
                        "provider_id": "preview-provider",
                        "openai_base_url": "https://preview.example/v1",
                        "api_key": "sk-preview-secret",
                        "model_id": "gpt-preview",
                    },
                    "fallbacks": [],
                }
            },
        },
    )
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))

    cfg = mms_core._load_config_or_preview_bundle()

    assert cfg["_mms_config_source"] == "latest-approved-bundle"
    assert cfg["provider"]["default"] == "preview-provider"
    assert [item["id"] for item in cfg["providers"]] == ["preview-provider"]


def test_mmf_preview_runtime_uses_explicit_bundle_default(monkeypatch, tmp_path) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    _write_latest_approved_router_manifest(
        preview_root,
        router_payload={
            "version": 1,
            "routes": {
                "first-model": {
                    "primary": {
                        "provider_id": "first-provider",
                        "openai_base_url": "https://first.example/v1",
                        "api_key": "sk-first",
                        "model_id": "first-model",
                    },
                    "fallbacks": [],
                },
                "default-model": {
                    "primary": {
                        "provider_id": "default-provider",
                        "openai_base_url": "https://default.example/v1",
                        "api_key": "sk-default",
                        "model_id": "default-model",
                    },
                    "fallbacks": [],
                },
            },
        },
        profile_payload={
            "schema_version": 1,
            "provider": {"default": "default-provider"},
            "profiles": {
                "first-provider": {"name": "First Provider", "protocols": ["openai_chat_completions"]},
                "default-provider": {"name": "Default Provider", "protocols": ["openai_chat_completions"]},
            },
        },
    )
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))

    cfg = mms_core._load_config_or_preview_bundle()

    assert cfg["_mms_config_source"] == "latest-approved-bundle"
    assert cfg["provider"]["default"] == "default-provider"


def test_bundle_runtime_provider_options_ignore_probe_cache(monkeypatch) -> None:
    import mms_core

    provider = {
        "id": "preview-provider",
        "enabled": True,
        "api_key": "sk-preview-secret",
        "protocols": ["anthropic_messages"],
        "supported_clis": ["claude"],
        "anthropic_base_url": "https://preview.example/v1",
        "models_endpoint": "manual",
        "fallback_models": ["visible-model"],
        "_mms_bundle_runtime": True,
    }
    monkeypatch.setattr(
        mms_core,
        "_provider_candidates",
        lambda *_args, **_kwargs: [(provider, ["visible-model", "hidden-remote-model"])],
    )
    monkeypatch.setattr(mms_core, "_account_options_for_model", lambda *_args, **_kwargs: [])

    visible = mms_core._provider_options_for_model(
        {},
        "claude",
        provider,
        [],
        model_info={"model": "visible-model"},
    )
    hidden = mms_core._provider_options_for_model(
        {},
        "claude",
        provider,
        [],
        model_info={"model": "hidden-remote-model"},
    )

    assert [item["id"] for item in visible] == ["preview-provider"]
    assert hidden == []


def test_bundle_runtime_provider_options_honor_hidden_derived_alias(monkeypatch) -> None:
    import mms_core

    provider = {
        "id": "tokyo-provider",
        "enabled": True,
        "api_key": "sk-preview-secret",
        "protocols": ["anthropic_messages"],
        "supported_clis": ["claude"],
        "anthropic_base_url": "https://tokyo.example/v1",
        "models_endpoint": "manual",
        "fallback_models": ["anthropic/claude-opus-4.6", "anthropic/claude-opus-4.7"],
        "hidden_models": ["claude-opus-4-6"],
        "_mms_bundle_runtime": True,
    }
    monkeypatch.setattr(mms_core, "_provider_candidates", lambda *_args, **_kwargs: [(provider, None)])
    monkeypatch.setattr(mms_core, "_account_options_for_model", lambda *_args, **_kwargs: [])

    visible_raw = mms_core._provider_options_for_model(
        {},
        "claude",
        provider,
        [],
        model_info={"model": "anthropic/claude-opus-4.6"},
    )
    hidden_alias = mms_core._provider_options_for_model(
        {},
        "claude",
        provider,
        [],
        model_info={"model": "claude-opus-4-6"},
    )

    assert [item["id"] for item in visible_raw] == ["tokyo-provider"]
    assert hidden_alias == []


def test_bundle_runtime_hiding_raw_variants_suppresses_derived_alias() -> None:
    import mms_core

    provider = {
        "id": "tokyo-provider",
        "models_endpoint": "manual",
        "fallback_models": ["anthropic/claude-opus-4.6", "anthropic/claude-opus-4.7"],
        "hidden_models": ["anthropic/claude-opus-4.6", "anthropic/claude-opus-4.7"],
    }

    assert mms_core._provider_effective_models(provider, None, {}) == []


def test_mmf_valid_bundle_without_config_reaches_launcher_selection(monkeypatch, tmp_path) -> None:
    import mms_core

    preview_root = tmp_path / "mms-next"
    preview_root.mkdir()
    _write_latest_approved_router_manifest(
        preview_root,
        router_payload={
            "version": 1,
            "routes": {
                "gpt-preview": {
                    "primary": {
                        "provider_id": "preview-provider",
                        "openai_base_url": "https://preview.example/v1",
                        "api_key": "sk-preview-secret",
                        "model_id": "gpt-preview",
                    },
                    "fallbacks": [],
                }
            },
        },
    )
    calls: list[str] = []
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(preview_root))
    monkeypatch.setenv("MMS_COMMAND_NAME", "mmf")
    monkeypatch.setattr(mms_core, "PRIMARY_CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(preview_root))
    monkeypatch.setattr(mms_core, "CONFIG_PATH", str(preview_root / "config.toml"))
    monkeypatch.setattr(sys, "argv", ["mmf"])
    monkeypatch.setattr(mms_core, "load_config", lambda: None)
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "setup_wizard", lambda *_args, **_kwargs: pytest.fail("legacy setup must not run when bundle is valid"))
    monkeypatch.setattr(mms_core, "save_config", lambda *_args, **_kwargs: pytest.fail("bundle runtime must stay transient"))
    monkeypatch.setattr(
        mms_core,
        "ensure_models_ready",
        lambda _cfg, provider: (provider, ["gpt-preview"]),
    )
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: ["codex"])
    monkeypatch.setattr(mms_core, "_use_tui", lambda: True)

    def fake_tui_handler(*_args, **_kwargs):
        calls.append("tui")
        return True

    monkeypatch.setattr(mms_core, "_handle_tui_launcher_selection", fake_tui_handler)

    mms_core.main()

    assert calls == ["tui"]
    assert not (preview_root / "config.toml").exists()


def test_mms_numeric_target_no_longer_launches_builtin_scene(monkeypatch, capsys) -> None:
    import mms_core

    cfg = {"user": {}, "recommend": {}}
    provider = {"id": "default-provider"}

    monkeypatch.setattr(sys, "argv", ["mms", "1"])
    monkeypatch.setattr(mms_core, "load_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_load_command_config", lambda: cfg)
    monkeypatch.setattr(mms_core, "_ensure_startup_snapshot_guard", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "apply_local_overrides", lambda value: value)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "ensure_provider_credentials", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(mms_core, "ensure_models_ready", lambda _cfg, _provider: (provider, {"models": []}))
    monkeypatch.setattr(mms_core, "_warm_probe_cache_async", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mms_core, "_resolve_visible_clis", lambda *_args, **_kwargs: ["claude"])
    monkeypatch.setattr(mms_core, "_update_notice", lambda: None)
    monkeypatch.setattr(mms_core, "_start_async_update_check", lambda: None)
    monkeypatch.setattr(mms_core, "_launch_with_tracking", lambda *_args, **_kwargs: pytest.fail("numeric scene should not launch"))

    mms_core.main()

    out = capsys.readouterr().out
    assert "未知目标: 1" in out


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
