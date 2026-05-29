import json

import pytest

import mms_config_web
import mms_core


@pytest.fixture(autouse=True)
def _isolate_mms_root_env(monkeypatch):
    # These tests pass explicit config_path values; ambient MMS session env should not reclassify temp roots.
    for key in ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR", "MMS_COMMAND_NAME", "MMS_PREVIEW_MODE"):
        monkeypatch.delenv(key, raising=False)


def test_config_web_snapshot_redacts_secrets_and_summarizes_provider():
    cfg = {
        "providers": [
            {
                "id": "webui-test-direct-qwen",
                "name": "Qwen Direct",
                "enabled": True,
                "api_key": "sk-super-secret-value",
                "anthropic_base_url": "https://qwen.example/v1",
                "protocols": ["anthropic_messages"],
                "supported_clis": ["claude", "opencode"],
                "fallback_models": ["qwen3.6-plus"],
                "claude_1m_mode": "enable",
                "proxy": "http://provider-proxy.example",
                "no_proxy": "provider.internal",
                "timezone": "Asia/Tokyo",
                "note": "primary qwen route",
            }
        ],
        "accounts": [
            {
                "id": "claude-main",
                "name": "Claude Main",
                "cli": "claude",
                "home_dir": "/Users/example/.config/mms/accounts/claude-main",
                "proxy": "http://proxy.example",
                "no_proxy": "localhost",
                "timezone": "Asia/Singapore",
                "note": "human owned claude account",
            }
        ],
        "account": {"defaults": {"claude": "claude-main"}},
        "vision_sidecar": {
            "enabled": True,
            "provider_id": "webui-test-direct-qwen",
            "model": "qwen3.6-plus",
            "api_key": "sk-vision-secret",
        },
        "rescue": {"fallback_model": "deepseek-v4-flash", "hot_fallback_enabled": False},
        "load_balance": {
            "default": "daily",
            "profiles": {
                "daily": {
                    "heavy": {"model": "gpt-5.5", "provider_id": "webui-test-direct-qwen"},
                    "medium": "qwen3.6-plus",
                    "light": "deepseek-v4-flash",
                }
            },
        },
    }

    snapshot = mms_config_web.build_config_snapshot(
        cfg,
        config_path="/tmp/mms/config.toml",
        preferences_path="/tmp/mms/preferences.toml",
        command_name="mms",
    )
    encoded = json.dumps(snapshot, ensure_ascii=False)

    assert snapshot["mode"] == "interactive_audited_save"
    assert snapshot["schema"] == "mms.setup_web.snapshot.v2"
    assert snapshot["providers"][0]["id"] == "webui-test-direct-qwen"
    assert snapshot["providers"][0]["has_api_key"] is True
    assert snapshot["providers"][0]["model_count"] == 1
    assert snapshot["providers"][0]["api_key"] == ""
    assert snapshot["providers"][0]["claude_1m_mode"] == "enable"
    assert snapshot["providers"][0]["proxy_configured"] is True
    assert snapshot["providers"][0]["no_proxy_configured"] is True
    assert snapshot["providers"][0]["timezone"] == "Asia/Tokyo"
    assert snapshot["providers"][0]["note"] == "primary qwen route"
    assert snapshot["providers"][0]["usage"]["launches"] == 0
    assert snapshot["accounts"][0]["id"] == "claude-main"
    assert snapshot["accounts"][0]["is_default"] is True
    assert snapshot["accounts"][0]["home_dir_configured"] is True
    assert snapshot["accounts"][0]["proxy_configured"] is True
    assert snapshot["accounts"][0]["no_proxy_configured"] is True
    assert snapshot["accounts"][0]["note"] == "human owned claude account"
    assert snapshot["accounts"][0]["is_claude_human_only"] is True
    assert snapshot["accounts"][0]["webui_write_policy"] == "claude_human_only_locked"
    assert snapshot["account_defaults"] == {"claude": "claude-main"}
    assert snapshot["account_write_policy"]["claude"] == "human_only_locked"
    assert "http://proxy.example" not in encoded
    assert "http://provider-proxy.example" not in encoded
    assert "provider.internal" not in encoded
    assert "localhost" not in encoded
    assert "/Users/example/.config/mms/accounts/claude-main" not in encoded
    assert snapshot["vision_sidecar"]["api_key"] != "sk-vision-secret"
    assert "sk-vision-secret" not in encoded
    assert "sk-super-secret-value" not in encoded
    assert {item["area"] for item in snapshot["webui_capability_coverage"]} >= {"通道", "账号", "设置", "主屏入口", "负载"}
    assert {item["action_id"] for item in snapshot["settings_actions"]} >= {"refresh-sources", "registry-doctor"}
    mapping = snapshot["tui_webui_mapping"]
    assert snapshot["tui_webui_mapping_summary"]["total"] == len(mapping)
    assert snapshot["tui_webui_mapping_summary"]["counts"] == {
        "native": 21,
        "report": 16,
        "draft_review": 3,
        "human_gate": 22,
        "missing": 0,
    }
    assert snapshot["tui_webui_mapping_summary"]["counts"]["missing"] == 0
    assert snapshot["tui_webui_mapping_summary"]["clickable_rows"] == len(mapping)
    assert snapshot["tui_webui_mapping_summary"]["rows_with_open_target"] == len(mapping)
    assert "每行都可在 WebUI 点击" in snapshot["tui_webui_mapping_summary"]["user_check_policy"]
    assert all(item["clickable"] == "yes" for item in mapping)
    assert all(item["click_targets"] for item in mapping)
    assert all(item["acceptance_check"] for item in mapping)
    assert {item["tui_action_id"] for item in mapping} >= {
        "provider_mgmt",
        "account_mgmt",
        "registry",
        "guard",
        "rescue",
        "language",
        "routes_export",
        "about",
    }
    assert {item["id"] for item in mapping} >= {
        "connect.add_gateway",
        "connect.add_official",
        "channel.provider_browse",
        "channel.family_autosort",
        "load_balance.profile_select",
        "load_balance.delete_recent",
        "provider.credentials",
        "provider.model_patch_reset",
        "provider.advanced_metadata",
        "provider.network_policy",
        "account.login",
        "account.rename",
        "account.edit_metadata",
        "account.network_policy",
        "registry.publish_approved",
        "guard.accept",
    }
    assert next(item for item in mapping if item["id"] == "guard.accept")["status"] == "human_gate"
    assert next(item for item in mapping if item["id"] == "provider.remove")["status"] == "native"
    assert next(item for item in mapping if item["id"] == "settings.language")["status"] == "native"
    assert next(item for item in mapping if item["id"] == "connect.add_official")["status"] == "human_gate"
    assert next(item for item in mapping if item["id"] == "load_balance.profile_select")["status"] == "native"
    assert next(item for item in mapping if item["id"] == "provider.model_patch_reset")["status"] == "native"
    assert next(item for item in mapping if item["id"] == "provider.advanced_metadata")["status"] == "native"
    assert next(item for item in mapping if item["id"] == "provider.network_policy")["status"] == "human_gate"
    assert next(item for item in mapping if item["id"] == "account.rename")["status"] == "human_gate"
    assert next(item for item in mapping if item["id"] == "account.edit_metadata")["status"] == "draft_review"
    assert next(item for item in mapping if item["id"] == "account.network_policy")["status"] == "human_gate"
    verify_approved = next(item for item in mapping if item["id"] == "registry.verify_approved")
    assert verify_approved["status"] == "report"
    assert verify_approved["api_action"] == "verify_approved"
    assert verify_approved["write_policy"] == "read_only_report"
    assert snapshot["ui"]["language"] == "zh"
    assert "Qwen" in snapshot["model_families"]
    assert snapshot["load_balance"]["default_profile"] == "daily"
    assert snapshot["load_balance"]["profiles"][0]["slots"]["heavy"]["provider_id"] == "webui-test-direct-qwen"
    assert "vision_sidecar" in snapshot["snippets"]
    assert [step["id"] for step in snapshot["setup_flow"]] == [
        "channel",
        "model_inventory",
        "capability",
        "validation",
        "fallbacks",
        "runtime",
    ]
    assert {item["id"] for item in snapshot["test_contracts"]} >= {"models_endpoint", "model_ping", "simple_chat"}
    assert snapshot["save_contract"]["requires_confirm_save"] is True


def test_config_web_settings_report_is_read_only_and_lists_gap_status(tmp_path):
    cfg = {
        "providers": [{"id": "demo", "name": "Demo", "fallback_models": ["gpt-5.5"]}],
        "accounts": [{"id": "codex-main", "name": "Codex Main", "cli": "codex", "proxy": "http://proxy.example"}],
        "account": {"defaults": {"codex": "codex-main"}},
        "load_balance": {
            "default": "fast",
            "profiles": {
                "fast": {
                    "heavy": {"model": "gpt-5.5", "provider_id": "demo"},
                    "light": "qwen3.6-flash",
                }
            },
        },
    }
    report = mms_config_web.build_settings_report(
        cfg,
        {"action": "coverage"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    accounts = mms_config_web.build_settings_report(
        cfg,
        {"action": "accounts"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    registry = mms_config_web.build_settings_report(
        cfg,
        {"action": "registry_status"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    mapping = mms_config_web.build_settings_report(
        cfg,
        {"action": "tui_mapping"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    guard = mms_config_web.build_settings_report(
        cfg,
        {"action": "guard_status"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    guard_accept = mms_config_web.build_settings_report(
        cfg,
        {"action": "guard_accept_gate"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    language = mms_config_web.build_settings_report(
        cfg,
        {"action": "language_status"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    load_balance = mms_config_web.build_settings_report(
        cfg,
        {"action": "load_balance_status"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    channel_status = mms_config_web.build_settings_report(
        cfg,
        {"action": "provider_channel_status"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    official_gate = mms_config_web.build_settings_report(
        cfg,
        {"action": "connect_official_gate"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    autosort_gate = mms_config_web.build_settings_report(
        cfg,
        {"action": "family_autosort_gate"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    encoded = json.dumps(accounts, ensure_ascii=False)

    assert report["ok"] is True
    assert report["write_policy"] == "read_only"
    assert any(item["webui"] == "draft_review_human_gate" for item in report["coverage"])
    assert accounts["write_policy"] == "draft_review_human_gate"
    assert accounts["accounts"][0]["id"] == "codex-main"
    assert accounts["accounts"][0]["is_default"] is True
    assert accounts["account_defaults"] == {"codex": "codex-main"}
    assert accounts["account_write_policy"]["blocked_fields"]
    assert "http://proxy.example" not in encoded
    assert registry["ok"] is True
    assert registry["write_policy"] == "read_only"
    assert "can initialize SQLite" in registry["note"]
    assert mapping["ok"] is True
    assert mapping["summary"]["counts"]["human_gate"] > 0
    assert mapping["summary"]["counts"]["missing"] == 0
    assert mapping["summary"]["clickable_rows"] == mapping["summary"]["total"]
    assert any(item["tui_action_id"] == "provider_mgmt" for item in mapping["mapping"])
    assert guard["write_policy"] == "manual_cli_human_gate"
    assert "mmf guard status" in guard["commands"]
    assert guard["blocked_auto_execute"] is True
    assert guard["manual_steps"]
    assert any("snapshots/startup/accepted.json" in item for item in guard["writes"])
    assert guard_accept["status"] == "human_gate"
    assert guard_accept["requires_human_confirmation"] is True
    assert "mmf guard accept" in guard_accept["commands"]
    assert language["status"] == "native"
    assert load_balance["write_policy"] == "draft_review_confirmed_save"
    assert load_balance["status"] == "native"
    assert load_balance["load_balance"]["default_profile"] == "fast"
    assert channel_status["status"] == "native"
    assert channel_status["provider_default"] == "demo"
    assert official_gate["status"] == "human_gate"
    assert official_gate["blocked_auto_execute"] is True
    assert "mmf config account.add codex" in official_gate["commands"]
    assert "Claude OAuth 独立入口已下线" in " ".join(official_gate["manual_steps"])
    assert autosort_gate["write_policy"] == "speed_stats_write_human_gate"
    assert "WebUI 已提供手工 family priority 草稿" in autosort_gate["safe_alternative"]
    assert any(item["id"] == "provider.network_policy" for item in mapping["mapping"])
    assert any(item["id"] == "account.rename" for item in mapping["mapping"])
    assert any(item["id"] == "account.network_policy" for item in mapping["mapping"])
    assert not (tmp_path / "mms-next" / "registry").exists()


def test_config_web_human_gate_reports_are_actionable(tmp_path):
    cfg = {
        "providers": [{"id": "demo", "name": "Demo", "fallback_models": ["gpt-5.5"]}],
        "accounts": [{"id": "codex-main", "name": "Codex Main", "cli": "codex"}],
    }
    mapping = mms_config_web.build_settings_report(
        cfg,
        {"action": "tui_mapping"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )["mapping"]
    gate_actions = sorted({row["api_action"] for row in mapping if row["status"] == "human_gate" and row.get("api_action")})

    assert gate_actions
    assert "about_upgrade_gate" in gate_actions
    assert "refresh_due_sources_gate" in gate_actions
    assert "provider_network_gate" in gate_actions
    assert "account_rename_gate" in gate_actions
    assert "account_network_gate" in gate_actions
    assert "verify_approved_gate" not in gate_actions
    for action in gate_actions:
        report = mms_config_web.build_settings_report(
            cfg,
            {"action": action},
            config_path=str(tmp_path / "mms-next" / "config.toml"),
            command_name="mmf",
        )
        assert report["ok"] is True
        assert report["status"] == "human_gate"
        assert report["blocked_auto_execute"] is True
        assert report["requires_human_confirmation"] is True
        assert report["manual_steps"], action
        assert report["commands"], action
        assert "risk_level" in report

    scheduled = mms_config_web.build_settings_report(
        cfg,
        {"action": "scheduled_refresh_gate"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    publish = mms_config_web.build_settings_report(
        cfg,
        {"action": "publish_approved_gate"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )

    assert "mmf registry scheduled-refresh --dry-run --no-network" in scheduled["commands"]
    assert "mmf registry publish-approved" in publish["commands"]
    assert any("model-registry.latest-approved.json" in item for item in publish["writes"])


def test_config_web_usage_reports_include_tui_detail_rows(monkeypatch, tmp_path):
    def fake_usage_rows(runtime_kind, runtime_id):
        return [
            {
                "cli": "codex",
                "runtime_kind": runtime_kind,
                "id": runtime_id,
                "name": f"{runtime_kind}:{runtime_id}",
                "launches": 7,
                "last_model": "qwen3.6-plus",
                "last_used_at": "2026-05-30T10:00:00+08:00",
                "models": {"qwen3.6-plus": 5, "gpt-5.5": 2},
            }
        ]

    monkeypatch.setattr(mms_core, "_usage_rows_for_runtime", fake_usage_rows)
    cfg = {
        "providers": [{"id": "demo", "name": "Demo", "fallback_models": ["qwen3.6-plus"]}],
        "accounts": [{"id": "codex-main", "name": "Codex Main", "cli": "codex"}],
        "account": {"defaults": {"codex": "codex-main"}},
    }

    provider_report = mms_config_web.build_settings_report(
        cfg,
        {"action": "provider_usage_summary"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )
    account_report = mms_config_web.build_settings_report(
        cfg,
        {"action": "accounts"},
        config_path=str(tmp_path / "mms-next" / "config.toml"),
        command_name="mmf",
    )

    provider_rows = provider_report["providers"][0]["usage_rows"]
    account_rows = account_report["accounts"][0]["usage_rows"]
    assert provider_rows[0]["runtime_kind"] == "provider"
    assert provider_rows[0]["launches"] == 7
    assert provider_rows[0]["top_models"][0] == {"model": "qwen3.6-plus", "launches": 5}
    assert account_rows[0]["runtime_kind"] == "account"
    assert account_rows[0]["id"] == "codex-main"


def test_config_web_verify_approved_report_is_read_only(monkeypatch, tmp_path):
    import mms_registry_cli

    calls = {}

    def fake_verify_approved_bundle(**kwargs):
        calls.update(kwargs)
        return {"verified": True, "manifest_path": "generated/model-registry.latest-approved.json"}

    monkeypatch.setattr(mms_registry_cli, "verify_approved_bundle", fake_verify_approved_bundle)

    config_root = tmp_path / "mms-next"
    report = mms_config_web.build_settings_report(
        {},
        {"action": "verify_approved"},
        config_path=str(config_root / "config.toml"),
        command_name="mmf",
    )

    assert report["ok"] is True
    assert report["status"] == "report"
    assert report["write_policy"] == "read_only_report"
    assert report["report"]["verified"] is True
    assert calls["config_dir"] == str(config_root)
    assert "不会 publish" in report["note"]
    assert not config_root.exists()


def test_config_web_json_response_redacts_account_protected_paths():
    _status, body, _content_type = mms_config_web._json_response(
        {
            "config": {
                "accounts": [
                    {
                        "id": "codex-main",
                        "home_dir": "/Users/example/.config/mms/accounts/codex-main",
                        "proxy": "http://proxy.example",
                        "no_proxy": "localhost",
                    }
                ]
            }
        }
    )
    encoded = body.decode("utf-8")

    assert "/Users/example/.config/mms/accounts/codex-main" not in encoded
    assert "http://proxy.example" not in encoded
    assert "localhost" not in encoded
    assert '"home_dir": true' in encoded
    assert '"proxy": true' in encoded
    assert '"no_proxy": true' in encoded


def test_config_web_bundle_runtime_models_are_not_manual_extra_models():
    cfg = {
        "providers": [
            {
                "id": "preview-provider",
                "name": "Preview Provider",
                "enabled": True,
                "api_key": "sk-super-secret-value",
                "openai_base_url": "https://preview.example/v1",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex"],
                "models_endpoint": "manual",
                "fallback_models": ["gpt-preview"],
                "extra_models": [],
                "_mms_bundle_runtime": True,
            }
        ],
    }

    snapshot = mms_config_web.build_config_snapshot(
        cfg,
        config_path="/tmp/mms/config.toml",
        command_name="mms",
    )
    provider = snapshot["providers"][0]

    assert provider["fallback_models"] == []
    assert provider["approved_route_models"] == ["gpt-preview"]
    assert provider["extra_models"] == []
    assert provider["models"][0]["id"] == "gpt-preview"
    assert provider["models"][0]["source"] == "approved"


def test_config_web_bundle_runtime_exposes_derived_aliases_for_hiding():
    cfg = {
        "providers": [
            {
                "id": "newapi-personal-tokyo",
                "name": "Tokyo",
                "enabled": True,
                "api_key": "sk-super-secret-value",
                "anthropic_base_url": "https://tokyo.example/v1",
                "protocols": ["anthropic_messages"],
                "supported_clis": ["claude"],
                "models_endpoint": "manual",
                "fallback_models": ["anthropic/claude-opus-4.6"],
                "hidden_models": ["claude-opus-4-6"],
                "_mms_bundle_runtime": True,
            }
        ],
    }

    snapshot = mms_config_web.build_config_snapshot(
        cfg,
        config_path="/tmp/mms/config.toml",
        command_name="mms",
    )
    provider = snapshot["providers"][0]
    rows = {row["id"]: row for row in provider["models"]}

    assert "claude-opus-4-6" in rows
    assert rows["claude-opus-4-6"]["source"] == "derived_alias"
    assert rows["claude-opus-4-6"]["visible"] is False
    assert provider["stale_hidden_models"] == []


def test_config_web_bundle_runtime_ignores_remote_probe_cache(monkeypatch):
    monkeypatch.setattr(
        mms_config_web._load_mms_core(),
        "_load_probe_file_cache",
        lambda *_args, **_kwargs: {"raw_models": ["gpt-preview", "hidden-remote"], "base_source": "remote"},
    )
    cfg = {
        "providers": [
            {
                "id": "preview-provider",
                "name": "Preview Provider",
                "enabled": True,
                "api_key": "sk-super-secret-value",
                "openai_base_url": "https://preview.example/v1",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex"],
                "models_endpoint": "manual",
                "fallback_models": ["gpt-preview"],
                "_mms_bundle_runtime": True,
            }
        ],
    }

    snapshot = mms_config_web.build_config_snapshot(
        cfg,
        config_path="/tmp/mms/config.toml",
        command_name="mms",
    )
    rows = snapshot["providers"][0]["models"]

    assert [row["id"] for row in rows] == ["gpt-preview"]
    assert rows[0]["source"] == "approved"


def test_config_web_json_response_keeps_non_secret_counts_visible():
    _status, body, _content_type = mms_config_web._json_response(
        {
            "api_key": "sk-super-secret-value",
            "has_api_key": True,
            "missing_api_key_count": 32,
            "runtime_blockers": {"missing_api_key_count": 32, "missing_base_url_count": 0},
            "secret_count": 2,
            "secrets": [{"value": "sk-super-secret-value"}],
        }
    )
    payload = json.loads(body)

    assert payload["api_key"] != "sk-super-secret-value"
    assert payload["has_api_key"] is True
    assert payload["missing_api_key_count"] == 32
    assert payload["runtime_blockers"]["missing_api_key_count"] == 32
    assert payload["runtime_blockers"]["missing_base_url_count"] == 0
    assert payload["secret_count"] == 2
    assert payload["secrets"] != [{"value": "sk-super-secret-value"}]
    assert "sk-super-secret-value" not in body.decode("utf-8")


def test_config_web_secret_ref_without_value_is_not_key_set():
    summary = mms_config_web._provider_summary(
        {
            "id": "secret-ref-only-provider",
            "enabled": True,
            "secret_ref": "pending-webui:secret_ref_only_provider:api_key",
            "openai_base_url": "https://provider.example/v1",
            "protocols": ["openai_chat_completions"],
            "fallback_models": ["demo-model"],
        },
        policy_payload={},
    )

    assert summary["has_api_key"] is False


def test_config_web_snapshot_includes_read_only_model_source_status(tmp_path):
    config_root = tmp_path / "mms-next"
    snapshot = mms_config_web.build_config_snapshot(
        {"providers": []},
        config_path=str(config_root / "config.toml"),
        command_name="mmf",
    )
    status = snapshot["model_source_status"]

    assert status["schema"] == "mms.model_source_status.v1"
    assert status["read_only"] is True
    assert status["result"] == "NOT_READY"
    assert status["ready"] is False
    assert status["status"] == "needs_init"
    assert "registry DB initialization" in status["headline"]
    assert status["root"]["command"] == "mmf"
    assert status["root"]["mode"] == "preview"
    assert status["root"]["config_root"] == str(config_root)
    assert status["registry_db"]["status"] == "missing"
    assert status["registry_db"]["path"] == str(config_root / "registry" / "model-registry.sqlite")
    assert status["legacy_import"]["candidates"]["status"] == "not_imported"
    assert status["legacy_import"]["candidates"]["provider_route_count"] == 0
    assert status["generated_bundle"]["status"] == "missing"
    consumer = snapshot["consumer_bundle_status"]
    assert consumer["schema"] == "mms.consumer_bundle_status.v1"
    assert consumer["read_only"] is True
    assert consumer["verified"] is False
    assert consumer["status"] == "missing"
    assert consumer["consumer_entrypoint"] == str(config_root / "generated" / "model-registry.latest-approved.json")
    assert "do not query SQLite directly" in consumer["consumer_rules"]
    promotion = snapshot["config_v2_promotion_plan"]
    assert promotion["schema"] == "mms.config_v2_promotion_plan.v1"
    assert promotion["read_only"] is True
    assert promotion["apply_enabled"] is False
    assert promotion["ready_for_human_review"] is False
    assert promotion["promotion_safety"]["stable_write_policy"] == "human_only"
    assert promotion["stable_backup_plan"]["would_create_backup"] is False
    assert promotion["bundle_comparison"]["preview"]["verified"] is False
    assert "stable_root_human_only" in promotion["blocked_reasons"]
    readiness = snapshot["config_v2_release_readiness"]
    assert readiness["schema"] == "mms.config_v2_release_readiness.v1"
    assert readiness["read_only"] is True
    assert readiness["release_complete"] is False
    assert readiness["ready_for_human_gate"] is False
    assert readiness["human_gate_required"] is True
    assert readiness["completion_blocker"] == "stable_promotion_human_gate"
    assert readiness["config_root"] == str(config_root)
    assert "preview_runtime_ready" in readiness["blocked_requirements"]
    assert "consumer_bundle_verified" in readiness["blocked_requirements"]
    assert not (config_root / "registry").exists()


def test_config_web_snapshot_separates_stale_hidden_models():
    cfg = {
        "providers": [
            {
                "id": "stale-hidden-demo",
                "name": "Stale Hidden Demo",
                "fallback_models": ["qwen3.6-plus"],
                "hidden_models": ["qwen3.6-plus", "retired-qwen-alias"],
            }
        ]
    }

    snapshot = mms_config_web.build_config_snapshot(cfg, config_path="/tmp/mms/config.toml")
    provider = snapshot["providers"][0]
    model_ids = [row["id"] for row in provider["models"]]
    current = next(row for row in provider["models"] if row["id"] == "qwen3.6-plus")

    assert "retired-qwen-alias" not in model_ids
    assert provider["stale_hidden_models"] == ["retired-qwen-alias"]
    assert current["visible"] is False


def test_config_web_print_summary_exits_without_server(capsys):
    rc = mms_config_web.run_config_web(
        {"providers": []},
        ["--print-summary"],
        command_name="mms",
        config_path="/tmp/config.toml",
        preferences_path="/tmp/preferences.toml",
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "mms.setup_web.snapshot.v2"
    assert payload["paths"]["config"] == "/tmp/config.toml"
    assert payload["paths"]["model_policy"] == "/tmp/model-policy.json"
    save_contract = payload["save_contract"]
    assert save_contract["stable_legacy_writes"] == [
        "config.toml",
        "credentials.sh(仅当输入新 key 并勾选更新凭据)",
        "model-policy.json",
    ]
    assert "registry/model-registry.sqlite(candidate revisions)" in save_contract["preview_v2_writes"]
    assert "generated/model-registry.latest-approved.json" in save_contract["preview_v2_writes"]
    assert save_contract["preview_confirm_phrase"] == "写入预览DB"
    assert payload["recommendations"]


def test_config_web_markdown_contains_manual_snippets(capsys):
    rc = mms_config_web.run_config_web(
        {"providers": []},
        ["--print-markdown"],
        command_name="mms",
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "# MMS Setup Configuration" in out
    assert "[vision_sidecar]" in out
    assert "[rescue]" in out
    assert "## Visual Setup Flow" in out
    assert "模型列表测试" in out
    assert "hidden_models" in out
    assert "[opencode]" in out
    assert "mms opencode --profile agent" in out


def test_config_web_channel_html_has_sticky_editor_and_enabled_sort():
    html = mms_config_web._HTML_PAGE

    assert "['source','真源状态','DB / legacy / bundle']" in html
    assert 'data-section="source"' in html
    assert "function renderSourceStatus()" in html
    assert "status.headline" in html
    assert "consumer_bundle_status" in html
    assert "Consumer Bundle" in html
    assert "Promotion Plan / Human Gate" in html
    assert "config_v2_promotion_plan" in html
    assert "4.0 Release Readiness" in html
    assert "config_v2_release_readiness" in html
    assert "release_complete 仍为 false" in html
    assert "stable promotion human gate" in html
    assert "blocked requirements" in html
    assert "stable backup + bundle comparison" in html
    assert "apply 仍停在 human gate" in html
    assert "不读 SQLite" in html
    assert "mmf config bundle --json" in html
    assert "candidate routes" in html
    assert "missing keys" in html
    assert "registry_v2_save_plan" in html
    assert "applyV2Preview" in html
    assert "downloadPlanJson" in html
    assert "copyApplyCommand" in html
    assert "WebUI plan JSON = “生成保存预览”的 redacted review artifact" in html
    assert "Advanced / Recovery：plan JSON 与 CLI fallback" in html
    assert "日常只需要“生成保存预览” → “写入预览 DB + 发布”" in html
    assert "function planJsonHint(plan)" in html
    assert "function renderApplyResult(data)" in html
    assert "已发布，但 runtime 未就绪" in html
    assert "mmf 会读到这次保存后的最新 bundle" in html
    assert "missing key/base URL" in html
    assert "currentApplyCommand()" in html
    assert "/api/registry-v2/apply" in html
    assert "写入预览DB" in html
    assert "旧版“确认保存”在 mmf 中已隐藏" in html
    assert "stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish" in html
    assert "stable legacy 保存写入 config.toml 的 [rescue] / [load_balance] / [vision_sidecar]" in html
    assert "preview root 走 DB candidate + latest-approved publish" in html
    assert "stable 写 credentials.sh；preview 写 secret backend" in html
    assert "这里会写入 config.toml 的 [rescue]" not in html
    assert "保存时更新 credentials.sh（需要填写 API Key；会 backup + audit）" not in html
    assert "function renderSaveControls()" in html
    assert "saveBtn').disabled=preview" in html
    assert "document.querySelectorAll('.legacy-save-action').forEach" in html
    assert "applyV2Preview').disabled=!preview" in html
    assert "['settings','能力整合','accounts / reports / parity']" in html
    assert 'data-section="settings"' in html
    assert "Settings / Channel 能力" in html
    assert "settingsCommand" in html
    assert "MMX / WEBUI TAKEOVER MAP" in html
    assert "Settings moved out of TUI" in html
    assert "当前配置没有 OAuth account" in html
    assert "function renderSettingsCommand" in html
    assert "accountTable" in html
    assert "function syncAccounts()" in html
    assert "data-account-default" in html
    assert "Claude human-only" in html
    assert "account_defaults:state.account_defaults" in html
    assert "uiLanguage" in html
    assert "saveUiLanguage" in html
    assert "settingsGapSummary" in html
    assert "ui:state.ui" in html
    assert "settingsCoverage" in html
    assert "主屏 O/P/L/S 入口覆盖" in html
    assert "entryAudit" in html
    assert "function renderEntryAudit" in html
    assert "Load Balance profiles" in html
    assert "loadBalanceTable" in html
    assert "function renderLoadBalance" in html
    assert "lbUpsert" in html
    assert "load_balance profile 已暂存" in html
    assert "load_balance_status" in html
    assert "family_priority_overrides" in html
    assert "function familyPriorityInputs" in html
    assert "providerFamilyPriority" in html
    assert "pClaude1m" in html
    assert "pTimezone" in html
    assert "pNote" in html
    assert "network policy" in html
    assert "data-account-family" in html
    assert "data-account-claude-1m" in html
    assert "data-account-timezone" in html
    assert "data-account-note" in html
    assert "TUI ↔ WebUI 对照表" in html
    assert "tuiMappingTable" in html
    assert "mappingFilters" in html
    assert "acceptancePanel" in html
    assert "逐项验收 checklist" in html
    assert "mapCheckProgress" in html
    assert "data-map-check" in html
    assert "function renderAcceptancePanel" in html
    assert "function copyAcceptanceReport" in html
    assert "function acceptanceReportText" in html
    assert "Click evidence" in html or "click evidence" in html
    assert "function renderTuiMapping" in html
    assert "data-map-filter" in html
    assert "data-section-jump" in html
    assert "pDeleteConfirm" in html
    assert "deleteProvider" in html
    assert "function deleteCurrentProviderDraft()" in html
    assert "tui_mapping" in html
    assert "maintenanceActions" in html
    assert "/api/settings/report" in html
    assert "human-gated" in html
    assert "Human Gate 操作卡" in html
    assert "function renderGateReport" in html
    assert "function copyGateCommand" in html
    assert "data-copy-gate-command" in html
    assert "blocked_auto_execute" in html
    assert "requires_human_confirmation" in html
    assert "Copyable commands" in html
    assert "Manual steps" in html
    assert "function renderSettings()" in html
    assert "renderStatus();renderSaveControls();renderSourceStatus();" in html
    assert "pending key" in html
    assert "已输入新 key，保存前会保留（不回显）" in html
    assert "keyEl.dataset.touched='1'" in html
    assert "p.pending_api_key=true" in html
    assert "p.update_credentials=!!(updateEl&&updateEl.checked)" in html
    assert "p.api_key=$('pKey').value" not in html
    assert "data.ok&&Array.isArray(data.models)" in html
    assert "模型拉取失败，请看测试结果" in html
    assert "card provider-editor" in html
    assert ".provider-editor {" in html
    assert "position: sticky;" in html
    assert "provider-tabs" in html
    assert "saveProviderForm" in html
    assert "function providerEntries()" in html
    assert "a.p.enabled?-1:1" in html
    assert "renderProviderList();renderTestSelectors();" in html
    assert "通道修改已暂存，生成保存预览后再写入" in html
    assert "这是当前通道的模型清单，不是全局模型池" in html
    assert "手动补充当前通道模型（extra_models" in html
    assert "添加到补充模型库" in html
    assert "restoreModelPatch" in html
    assert "恢复默认模型补丁" in html
    assert "已恢复默认模型补丁" in html
    assert "当前通道补充模型库（extra_models）" in html
    assert "不是待删除列表，也不是全局模型池" in html
    assert "编辑补充模型库" in html
    assert "从补充库移除" in html
    assert "移除全部通道未匹配隐藏规则" in html
    assert "未匹配隐藏规则（hidden_models）" in html
    assert "不等于远端不存在" in html
    assert "拉取后自动标记缺失旧 route 为待清理" in html
    assert "移除当前通道未匹配隐藏规则" in html
    assert "function providerEntries()" in html
    assert "a.p.enabled?-1:1" in html
    assert "renderProviderList();renderTestSelectors();" in html
    assert "通道修改已暂存，生成保存预览后再写入" in html


def test_config_web_fetch_models_does_not_persist_to_fallback_models():
    html = mms_config_web._HTML_PAGE

    assert "不会自动写入 fallback_models" in html
    assert "p.fallback_models=[...new Set(data.models)]" not in html


def test_config_web_plan_does_not_materialize_empty_fallback_models(tmp_path):
    cfg = {
        "provider": {"default": "demo"},
        "providers": [
            {
                "id": "demo",
                "name": "Demo",
                "enabled": True,
                "role": "auto",
                "priority": 100,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["opencode"],
                "models_endpoint": "/models",
                "default_openai_base_url": "https://demo.example/v1",
                "extra_models": ["gpt-5.5"],
            }
        ],
    }
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")}

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))

    provider = plan["config"]["providers"][0]
    assert "fallback_models" not in provider
    assert "fallback_models" not in plan["diffs"]["config_toml"]


def test_config_web_opencode_agent_overrides_are_advanced_ui():
    html = mms_config_web._HTML_PAGE

    assert "OpenCode default profile" in html
    assert "OpenCode Agent Roster" in html
    assert "Order 是 priority/fallback order, not round-robin" in html
    assert "Agent overrides" in html
    assert "Enabled agents" in html
    assert 'id="opencodeOverrideSummary"' in html
    assert 'id="opencodeAdvanced"' in html
    assert "<details" in html
    assert "Advanced: OpenCode per-agent roster" in html
    assert "只看改动项" in html
    assert "+ Add Vision Agent" in html
    assert "+ Add Executor Agent" in html
    assert "全部自动" in html
    assert "['execute','执行/协调']" in html
    assert "enabledOnly=false" in html
    assert "decodeModelSelection" in html
    assert "modelOptionValue" in html
    assert "providerOptions(provider,{auto:true,enabledOnly:true})" in html
    assert "modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})" in html
    assert "const entry=rosterEntry(agent,row);tr.querySelector" in html
    assert "state.opencode.agent_models={};" in html
    assert "state.opencode.agent_roster={};" in html
    assert "session-local opencode.json" in html


def test_config_web_snapshot_has_agent_roster_catalog():
    snapshot = mms_config_web.build_config_snapshot({"providers": []}, config_path="/tmp/mms/config.toml")
    catalog = snapshot["opencode"]["agent_catalog"]
    agents = {row["agent"] for row in catalog}

    assert len(catalog) == 18
    assert catalog[0]["agent"] == "mobius-builder-pro"
    assert catalog[0]["preset"] == "builder"
    assert {
        "mobius-explore-qwen",
        "mobius-bughunt-qwen",
        "mobius-executor-gpt54",
        "mobius-vision-qwen",
        "mobius-reviewer-gpt55",
    } <= agents
    assert {row["category"] for row in catalog} >= {"执行/协调", "探索", "找茬", "Vision", "审查"}


def test_config_web_plan_noops_credential_backed_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(
        mms_config_web,
        "_provider_credentials_status",
        lambda _provider_id: {
            "has_api_key": True,
            "base_url": "",
            "openai_base_url": "http://127.0.0.1:18080",
            "anthropic_base_url": "http://127.0.0.1:18080",
        },
    )
    cfg, _ = mms_core._ensure_provider_config(
        {
            "provider": {"default": "local"},
            "providers": [
                {
                    "id": "local",
                    "name": "Local",
                    "enabled": True,
                    "role": "auto",
                    "priority": 100,
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["claude", "codex", "opencode"],
                    "models_endpoint": "/models",
                    "fallback_models": ["local-model"],
                    "default_openai_base_url": "",
                    "default_anthropic_base_url": "",
                }
            ],
        }
    )
    config_path = str(tmp_path / "config.toml")
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=config_path)
    provider = snapshot["providers"][0]
    draft = {key: snapshot[key] for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")}

    assert provider["openai_base_url"] == "http://127.0.0.1:18080"
    assert provider["openai_base_url_source"] == "credentials"

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=config_path)

    assert plan["summary"]["will_write_config"] is False
    assert plan["summary"]["will_write_policy"] is False
    assert plan["review_summary"]["risks"] == []
    assert plan["review_summary"]["items"][0]["kind"] == "no_change"


def test_config_web_plan_account_default_draft_reviews_safe_non_claude_changes(tmp_path):
    cfg = {
        "accounts": [
            {"id": "claude-main", "name": "Claude Main", "cli": "claude", "priority": 100},
            {"id": "codex-a", "name": "Codex A", "cli": "codex", "priority": 50},
            {"id": "codex-b", "name": "Codex B", "cli": "codex", "priority": 40},
        ],
        "account": {"defaults": {"claude": "claude-main", "codex": "codex-a"}},
    }
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("accounts", "account_defaults")}
    codex_b = next(account for account in draft["accounts"] if account["id"] == "codex-b")
    codex_b["name"] = "Codex B Edited"
    codex_b["enabled"] = False
    codex_b["priority"] = 120
    codex_b["family_priority_overrides"] = {"GPT": 125}
    codex_b["claude_1m_mode"] = "disable"
    codex_b["timezone"] = "Asia/Tokyo"
    codex_b["note"] = "non-claude metadata ok"
    draft["account_defaults"]["codex"] = "codex-b"

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))
    review = plan["review_summary"]

    assert plan["ok"] is True
    assert plan["config"]["account"]["defaults"] == {"claude": "claude-main", "codex": "codex-b"}
    after_codex_b = next(account for account in plan["config"]["accounts"] if account["id"] == "codex-b")
    assert after_codex_b["name"] == "Codex B Edited"
    assert after_codex_b["enabled"] is False
    assert after_codex_b["priority"] == 120
    assert after_codex_b["family_priority_overrides"] == {"GPT": 125}
    assert after_codex_b["claude_1m_mode"] == "disable"
    assert after_codex_b["timezone"] == "Asia/Tokyo"
    assert after_codex_b["note"] == "non-claude metadata ok"
    assert any(item["kind"] == "account_default" and item["meta"]["cli"] == "codex" for item in review["items"])
    assert any(item["kind"] == "account_metadata" and item["meta"]["account_id"] == "codex-b" for item in review["items"])
    assert any(risk["id"] == "account_default_changed" for risk in review["risks"])
    assert review["counts"]["account_changes"] == 2


def test_config_web_plan_family_priority_and_load_balance_drafts_are_reviewed(tmp_path):
    cfg = {
        "provider": {"default": "demo"},
        "providers": [
            {
                "id": "demo",
                "name": "Demo",
                "enabled": True,
                "role": "auto",
                "priority": 100,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["opencode"],
                "models_endpoint": "/models",
                "fallback_models": ["gpt-5.5"],
            }
        ],
        "accounts": [{"id": "codex-main", "name": "Codex Main", "cli": "codex", "priority": 100}],
    }
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("providers", "accounts", "account_defaults", "load_balance")}
    draft["providers"][0]["family_priority_overrides"] = {"GPT": 145, "Qwen": 90}
    draft["accounts"][0]["family_priority_overrides"] = {"GPT": 130}
    draft["load_balance"] = {
        "default_profile": "daily",
        "profiles": [
            {
                "name": "daily",
                "label": "daily",
                "slots": {
                    "heavy": {"model": "gpt-5.5", "provider_id": "demo"},
                    "medium": {"model": "qwen3.6-plus"},
                    "light": {"model": "deepseek-v4-flash"},
                },
            }
        ],
    }

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))
    review = plan["review_summary"]

    assert plan["ok"] is True
    provider = plan["config"]["providers"][0]
    assert provider["family_priority_overrides"] == {"GPT": 145, "Qwen": 90}
    assert plan["config"]["accounts"][0]["family_priority_overrides"] == {"GPT": 130}
    assert plan["config"]["load_balance"]["default"] == "daily"
    assert plan["config"]["load_balance"]["profiles"]["daily"]["heavy"] == {"model": "gpt-5.5", "provider": "demo"}
    assert any(item["kind"] == "provider_family_priority" for item in review["items"])
    assert any(item["kind"] == "account_metadata" for item in review["items"])
    assert any(item["kind"] == "load_balance" for item in review["items"])
    assert "family_priority_overrides" in plan["diffs"]["config_toml"]
    assert "[load_balance]" in plan["diffs"]["config_toml"]


def test_config_web_plan_ui_language_draft_is_reviewed(tmp_path):
    cfg = {"ui": {"language": "zh"}}
    plan = mms_config_web.build_config_plan(
        cfg,
        {"draft": {"ui": {"language": "en"}}},
        config_path=str(tmp_path / "config.toml"),
    )

    assert plan["ok"] is True
    assert plan["config"]["ui"]["language"] == "en"
    assert any(item["kind"] == "ui_language" for item in plan["review_summary"]["items"])
    assert 'language = "en"' in plan["diffs"]["config_toml"]


def test_config_web_plan_provider_delete_draft_is_reviewed(tmp_path):
    cfg = {
        "provider": {"default": "first"},
        "providers": [
            {"id": "first", "name": "First", "models_endpoint": "/models"},
            {"id": "second", "name": "Second", "models_endpoint": "/models"},
        ],
    }
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("providers", "provider_default")}
    draft["providers"] = [provider for provider in draft["providers"] if provider["id"] == "second"]
    draft["provider_default"] = "second"

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))
    review = plan["review_summary"]

    assert plan["ok"] is True
    assert [provider["id"] for provider in plan["config"]["providers"]] == ["second"]
    assert plan["config"]["provider"]["default"] == "second"
    assert any(item["kind"] == "provider_removed" and item["provider_id"] == "first" for item in review["items"])
    assert any(risk["id"] == "provider_removed" and risk["provider_id"] == "first" for risk in review["risks"])


def test_config_web_plan_account_snapshot_noops_without_materializing_defaults(tmp_path):
    cfg, _ = mms_core._ensure_provider_config({
        "provider": {"default": "demo"},
        "providers": [
            {
                "id": "demo",
                "name": "Demo",
                "enabled": True,
                "role": "auto",
                "priority": 100,
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["codex"],
                "models_endpoint": "manual",
            }
        ],
    })
    cfg.update({
        "accounts": [
            {"id": "codex-a", "name": "Codex A", "cli": "codex"},
        ],
        "account": {"defaults": {"codex": "codex-a"}},
    })
    cfg["providers"][0].pop("fallback_models", None)
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("accounts", "account_defaults")}

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))

    assert plan["ok"] is True
    assert plan["summary"]["will_write_config"] is False
    assert "priority" not in plan["config"]["accounts"][0]
    assert "enabled" not in plan["config"]["accounts"][0]
    assert plan["review_summary"]["items"][0]["kind"] == "no_change"


def test_config_web_plan_blocks_claude_account_default_and_metadata_changes(tmp_path):
    cfg = {
        "accounts": [
            {"id": "claude-main", "name": "Claude Main", "cli": "claude", "priority": 100},
            {"id": "claude-alt", "name": "Claude Alt", "cli": "claude", "priority": 90},
        ],
        "account": {"defaults": {"claude": "claude-main"}},
    }
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=str(tmp_path / "config.toml"))
    draft = {key: snapshot[key] for key in ("accounts", "account_defaults")}
    draft["accounts"][0]["name"] = "Claude Edited"
    draft["account_defaults"]["claude"] = "claude-alt"

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=str(tmp_path / "config.toml"))

    assert plan["ok"] is False
    assert any("Claude account" in error or "Claude 默认账号" in error for error in plan["errors"])
    assert plan["config"]["account"]["defaults"] == {"claude": "claude-main"}
    assert next(account for account in plan["config"]["accounts"] if account["id"] == "claude-main")["name"] == "Claude Main"


def test_config_web_review_summary_ignores_unchanged_http_config(tmp_path):
    cfg, _ = mms_core._ensure_provider_config(
        {
            "provider": {"default": "local"},
            "providers": [
                {
                    "id": "local",
                    "name": "Local",
                    "enabled": True,
                    "role": "auto",
                    "priority": 100,
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["claude", "codex", "opencode"],
                    "models_endpoint": "/models",
                    "fallback_models": ["local-model"],
                    "default_openai_base_url": "http://127.0.0.1:18080",
                    "default_anthropic_base_url": "http://127.0.0.1:18080",
                }
            ],
        }
    )
    config_path = str(tmp_path / "config.toml")
    snapshot = mms_config_web.build_config_snapshot(cfg, config_path=config_path)
    draft = {key: snapshot[key] for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")}

    plan = mms_config_web.build_config_plan(cfg, {"draft": draft}, config_path=config_path)

    assert plan["summary"]["will_write_config"] is False
    assert not any(risk["id"] == "http_base_url" for risk in plan["review_summary"]["risks"])


def _draft_payload():
    return {
        "draft": {
            "provider_default": "demo",
            "providers": [
                {
                    "original_id": "demo",
                    "id": "demo",
                    "name": "Demo Gateway",
                    "enabled": True,
                    "role": "primary",
                    "priority": 150,
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["claude", "codex", "opencode"],
                    "models_endpoint": "/models",
                    "openai_base_url": "https://demo.example/v1",
                    "anthropic_base_url": "https://demo.example/v1",
                    "api_key": "sk-super-secret-value",
                    "update_credentials": True,
                    "fallback_models": ["gpt-5.5"],
                    "extra_models": ["qwen3.6-plus"],
                    "hidden_models": ["noisy-model"],
                    "models": [
                        {
                            "id": "qwen3.6-plus",
                            "visible": True,
                            "favorite": True,
                            "capabilities": {
                                "text": True,
                                "vision": True,
                                "tool_use": True,
                                "reasoning": True,
                                "long_context": True,
                                "cache_sensitive": True,
                            },
                            "policy_touched": True,
                        }
                    ],
                }
            ],
            "rescue": {
                "fallback_model": "deepseek-v4-flash",
                "fallback_cli": "codex",
                "hot_fallback_enabled": False,
            },
            "vision_sidecar": {
                "enabled": True,
                "provider_id": "demo",
                "model": "qwen3.6-plus",
                "candidates": [{"provider_id": "demo", "model": "qwen3.6-plus"}],
            },
            "runtime": {"preferred_cli": "opencode", "coding_preset_model": "gpt-5.5"},
            "opencode": {
                "default_profile": "lite_pro_orchestrated",
                "agent_models": {
                    "mobius-explore-glm": {"provider_id": "demo", "model": "qwen3.6-plus"},
                    "mobius-reviewer-gpt55": {"model": "gpt-5.5"},
                },
            },
        }
    }


def _large_route_draft_payload(count=12):
    models = [f"model-{index:02d}" for index in range(count)]
    return {
        "draft": {
            "provider_default": "bulk",
            "providers": [
                {
                    "original_id": "bulk",
                    "id": "bulk",
                    "name": "Bulk Gateway",
                    "enabled": True,
                    "role": "primary",
                    "priority": 200,
                    "protocols": ["anthropic_messages", "openai_chat_completions"],
                    "supported_clis": ["claude", "codex", "opencode"],
                    "models_endpoint": "manual",
                    "openai_base_url": "https://bulk.example/v1",
                    "anthropic_base_url": "https://bulk.example/v1",
                    "api_key": "sk-bulk-secret-value",
                    "update_credentials": True,
                    "fallback_models": models,
                    "extra_models": [],
                    "hidden_models": [],
                    "models": [{"id": model, "visible": True} for model in models],
                }
            ],
            "rescue": {},
            "vision_sidecar": {},
            "runtime": {"preferred_cli": "opencode", "coding_preset_model": models[0]},
            "opencode": {"default_profile": "lite_pro_orchestrated", "agent_models": {}},
        }
    }


def test_config_web_plan_builds_diff_without_echoing_credentials(tmp_path):
    cfg = {"provider": {"default": "demo"}, "providers": [{"id": "demo", "name": "Old"}]}
    payload = _draft_payload()

    plan = mms_config_web.build_config_plan(
        cfg,
        payload,
        config_path=str(tmp_path / "config.toml"),
        preferences_path=str(tmp_path / "preferences.toml"),
    )
    encoded = json.dumps(plan, ensure_ascii=False)

    assert plan["ok"] is True
    assert plan["summary"]["credential_updates"] == 1
    assert plan["config"]["providers"][0]["hidden_models"] == ["noisy-model"]
    assert plan["config"]["opencode"]["agent_models"]["mobius-explore-glm"] == {
        "provider_id": "demo",
        "model": "qwen3.6-plus",
    }
    assert plan["config"]["opencode"]["agent_models"]["mobius-reviewer-gpt55"] == {"model": "gpt-5.5"}
    assert plan["model_policy"]["models"]["qwen3.6-plus"]["capabilities"]["vision"] is True
    assert "Demo Gateway" in plan["diffs"]["config_toml"]
    assert "credential update: provider demo" in plan["diffs"]["credentials"]
    assert "preview secret backend" in plan["diffs"]["credentials"]
    assert plan["review_summary"]["schema"] == "mms.setup_web.review_summary.v1"
    assert any(item["kind"] == "provider_url" for item in plan["review_summary"]["items"])
    credentials_item = next(item for item in plan["review_summary"]["items"] if item["kind"] == "credentials")
    credential_risk = next(risk for risk in plan["review_summary"]["risks"] if risk["id"] == "credential_update")
    assert "stable legacy 写 credentials.sh；preview 写 secret backend" in credentials_item["detail"]
    assert "preview 目标是 secret backend" in credential_risk["detail"]
    assert "将更新 credentials.sh" not in json.dumps(plan["review_summary"], ensure_ascii=False)
    assert "sk-super-secret-value" not in encoded


def test_config_web_plan_includes_read_only_registry_v2_save_plan(tmp_path):
    config_root = tmp_path / "mms-next"
    registry_dir = config_root / "registry"
    registry_dir.mkdir(parents=True)
    db_path = registry_dir / "model-registry.sqlite"
    db_path.write_bytes(b"not-a-real-db")
    cfg = {"provider": {"default": "demo"}, "providers": [{"id": "demo", "name": "Old"}]}
    payload = _draft_payload()

    plan = mms_config_web.build_config_plan(
        cfg,
        payload,
        config_path=str(config_root / "config.toml"),
    )
    v2_plan = plan["registry_v2_save_plan"]
    encoded = json.dumps(v2_plan, ensure_ascii=False)

    assert v2_plan["schema"] == "mms.setup_web.registry_v2_save_plan.v1"
    assert v2_plan["read_only"] is True
    assert v2_plan["execution_state"] == "plan_only"
    assert v2_plan["actual_save_enabled"] is False
    assert v2_plan["root"]["mode"] == "preview"
    assert v2_plan["db"]["path"] == str(db_path)
    assert v2_plan["db"]["would_backup_existing_db"] is True
    assert v2_plan["would_write"]["db_candidate_revision"] is True
    assert v2_plan["would_write"]["secret_backend"] is True
    assert v2_plan["would_write"]["generated_latest_approved_bundle"] is True
    assert v2_plan["blocked_reasons"] == []
    assert "rollback" in " ".join(v2_plan["ordered_steps"])
    assert v2_plan["plan_json"]["name"] == "webui-plan.json"
    assert v2_plan["plan_json"]["redacted"] is True
    assert v2_plan["plan_json"]["secrets_included"] is False
    assert v2_plan["apply_plan"]["webui_endpoint"] == "/api/registry-v2/apply"
    assert v2_plan["apply_plan"]["confirm_phrase"] == "写入预览DB"
    assert "--confirm-preview-apply" in v2_plan["apply_plan"]["cli_apply_command"]
    assert "credential updates should be applied through WebUI" in v2_plan["apply_plan"]["credential_note"]
    assert "WebUI and mms config apply-plan are wired" in v2_plan["next_implementation_step"]
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_save_plan_blocks_stable_root(tmp_path):
    config_root = tmp_path / "mms"
    cfg = {"provider": {"default": "demo"}, "providers": [{"id": "demo", "name": "Old"}]}
    payload = _draft_payload()

    plan = mms_config_web.build_config_plan(
        cfg,
        payload,
        config_path=str(config_root / "config.toml"),
    )
    v2_plan = plan["registry_v2_save_plan"]

    assert v2_plan["root"]["mode"] == "stable"
    assert v2_plan["would_write"]["db_candidate_revision"] is False
    assert v2_plan["would_write"]["secret_backend"] is False
    assert v2_plan["would_write"]["generated_latest_approved_bundle"] is False
    assert "stable_root_human_only" in v2_plan["blocked_reasons"]


def test_config_web_plan_clears_empty_opencode_agent_overrides(tmp_path):
    cfg = {
        "opencode": {
            "default_profile": "lite_pro_orchestrated",
            "agent_models": {
                "mobius-explore-glm": {"provider_id": "demo", "model": "qwen3.6-plus"},
            },
        }
    }
    payload = {
        "draft": {
            "opencode": {
                "default_profile": "lite_pro_orchestrated",
                "agent_models": {},
            }
        }
    }

    plan = mms_config_web.build_config_plan(cfg, payload, config_path=str(tmp_path / "config.toml"))

    assert "agent_models" not in plan["config"]["opencode"]
    assert any(item["kind"] == "opencode_agent_models" for item in plan["review_summary"]["items"])


def test_config_web_plan_persists_opencode_agent_roster_delta(tmp_path):
    cfg = {"opencode": {"default_profile": "lite_pro_orchestrated"}}
    payload = {
        "draft": {
            "opencode": {
                "default_profile": "lite_pro_orchestrated",
                "agent_roster": {
                    "mobius-vision-mimo": {"enabled": False, "preset": "vision", "priority": 100},
                    "mobius-vision-custom-1": {
                        "enabled": True,
                        "custom": True,
                        "preset": "vision",
                        "provider_id": "demo",
                        "model": "qwen3.6-plus",
                        "priority": 910,
                    },
                },
            }
        }
    }

    plan = mms_config_web.build_config_plan(cfg, payload, config_path=str(tmp_path / "config.toml"))
    roster = plan["config"]["opencode"]["agent_roster"]
    item = next(item for item in plan["review_summary"]["items"] if item["kind"] == "opencode_agent_roster")

    assert roster["mobius-vision-mimo"]["enabled"] is False
    assert roster["mobius-vision-custom-1"] == {
        "preset": "vision",
        "custom": True,
        "enabled": True,
        "provider_id": "demo",
        "model": "qwen3.6-plus",
        "priority": 910,
    }
    assert item["meta"]["disabled_agents"] == ["mobius-vision-mimo"]
    assert item["meta"]["custom_agents"] == ["mobius-vision-custom-1"]


def test_config_web_plan_ignores_disabled_required_builder(tmp_path):
    payload = {
        "draft": {
            "opencode": {
                "default_profile": "lite_pro_orchestrated",
                "agent_roster": {
                    "mobius-builder-pro": {"enabled": False, "preset": "builder"},
                },
            }
        }
    }

    plan = mms_config_web.build_config_plan({"opencode": {"default_profile": "lite_pro_orchestrated"}}, payload, config_path=str(tmp_path / "config.toml"))

    assert "agent_roster" not in plan["config"].get("opencode", {})


def test_config_web_review_summary_lists_only_changed_opencode_agents(tmp_path):
    cfg = {
        "opencode": {
            "default_profile": "lite_pro_orchestrated",
            "agent_models": {
                "same-agent": {"model": "gpt-5.4"},
                "updated-agent": {"provider_id": "demo", "model": "glm-5"},
                "removed-agent": {"model": "glm-5"},
            },
        }
    }
    payload = {
        "draft": {
            "opencode": {
                "default_profile": "lite_pro_orchestrated",
                "agent_models": {
                    "same-agent": {"model": "gpt-5.4"},
                    "updated-agent": {"provider_id": "demo", "model": "glm-5.1"},
                    "new-agent": {"model": "qwen3.6-plus"},
                },
            }
        }
    }

    plan = mms_config_web.build_config_plan(cfg, payload, config_path=str(tmp_path / "config.toml"))
    item = next(item for item in plan["review_summary"]["items"] if item["kind"] == "opencode_agent_models")

    assert item["meta"]["agents"] == ["new-agent", "removed-agent", "updated-agent"]
    assert item["meta"]["added_agents"] == ["new-agent"]
    assert item["meta"]["removed_agents"] == ["removed-agent"]
    assert item["meta"]["updated_agents"] == ["updated-agent"]
    assert "新增 1" in item["detail"]
    assert "移除 1" in item["detail"]
    assert "修改 1" in item["detail"]
    assert "same-agent" not in item["detail"]


def test_config_web_review_summary_flags_http_and_hidden_cleanup(tmp_path):
    cfg = {
        "provider": {"default": "demo"},
        "providers": [
            {
                "id": "demo",
                "name": "Demo",
                "enabled": True,
                "default_openai_base_url": "",
                "protocols": ["openai_chat_completions"],
                "supported_clis": ["opencode"],
                "fallback_models": ["keep-hidden"],
                "hidden_models": ["keep-hidden", "retired-model"],
            }
        ],
    }
    payload = {
        "draft": {
            "provider_default": "demo",
            "providers": [
                {
                    "original_id": "demo",
                    "id": "demo",
                    "name": "Demo",
                    "enabled": True,
                    "protocols": ["openai_chat_completions"],
                    "supported_clis": ["opencode"],
                    "openai_base_url": "http://demo.example/v1",
                    "fallback_models": ["keep-hidden"],
                    "hidden_models": ["keep-hidden"],
                    "models": [{"id": "keep-hidden", "visible": False, "capabilities": {"text": True}}],
                },
                {
                    "id": "new-http",
                    "name": "New HTTP",
                    "enabled": True,
                    "protocols": ["openai_chat_completions"],
                    "supported_clis": ["opencode"],
                    "openai_base_url": "http://new.example/v1",
                    "models": [],
                }
            ],
        }
    }

    plan = mms_config_web.build_config_plan(cfg, payload, config_path=str(tmp_path / "config.toml"))
    review = plan["review_summary"]

    assert review["counts"]["hidden_removed"] == 1
    assert any(item["kind"] == "provider_added" and item["provider_id"] == "new-http" for item in review["items"])
    assert any(item["kind"] == "hidden_removed" and "retired-model" in item["detail"] for item in review["items"])
    assert any(risk["id"] == "http_base_url" and risk["provider_id"] == "demo" for risk in review["risks"])
    assert any(risk["id"] == "http_base_url" and risk["provider_id"] == "new-http" for risk in review["risks"])


def test_config_web_save_requires_explicit_confirmation(tmp_path):
    cfg = {"providers": [{"id": "demo"}]}
    result = mms_config_web.apply_config_plan(
        cfg,
        _draft_payload(),
        config_path=str(tmp_path / "config.toml"),
    )

    assert result["ok"] is False
    assert "确认" in result["errors"][0]


def test_config_web_save_uses_audited_writers(monkeypatch, tmp_path):
    config_path = tmp_path / "config.toml"
    credentials_path = tmp_path / "credentials.sh"
    policy_path = tmp_path / "model-policy.json"
    config_path.write_text('[[providers]]\nid = "demo"\nname = "Old"\n', encoding="utf-8")
    credentials_path.write_text('MMS_PROVIDER_DEMO_API_KEY="old-secret"\n', encoding="utf-8")
    policy_path.write_text('{"version":1,"models":{},"projects":{}}\n', encoding="utf-8")

    monkeypatch.setattr(mms_core, "_config_write_target_path", lambda: str(config_path))
    monkeypatch.setattr(mms_core, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(mms_core, "CREDENTIALS_PATH", str(credentials_path))
    monkeypatch.setattr(mms_core, "_trigger_routes_export_after_credentials_write", lambda: None)
    monkeypatch.setattr(mms_core, "_refresh_routes_export_for_hive", lambda *args, **kwargs: True)

    payload = _draft_payload()
    payload["confirm_save"] = True
    payload["confirm_phrase"] = "保存配置"
    result = mms_config_web.apply_config_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    encoded = json.dumps(result, ensure_ascii=False)

    assert result["ok"] is True
    assert config_path.exists()
    assert credentials_path.exists()
    assert "sk-super-secret-value" in credentials_path.read_text(encoding="utf-8")
    assert policy_path.exists()
    assert (tmp_path / "config-audit.jsonl").exists()
    assert "setup-web-ui:interactive-save" in (tmp_path / "config-audit.jsonl").read_text(encoding="utf-8")
    assert result["save_report"]["config"]["bak_path"].endswith(".bak")
    bak_paths = list((tmp_path / "backups").rglob("*.bak"))
    assert any(path.name == "config.toml.bak" for path in bak_paths)
    assert any(path.name == "credentials.sh.bak" for path in bak_paths)
    assert any(path.name == "model-policy.json.bak" for path in bak_paths)
    assert "sk-super-secret-value" not in encoded


def test_config_web_legacy_save_blocks_preview_root(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    credentials_path = config_root / "credentials.sh"
    payload = _draft_payload()
    payload["confirm_save"] = True
    payload["confirm_phrase"] = "保存配置"

    result = mms_config_web.apply_config_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["root"]["mode"] == "preview"
    assert "legacy /api/save" in result["errors"][0]
    assert not config_path.exists()
    assert not credentials_path.exists()
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_blocks_stable_root(tmp_path):
    config_root = tmp_path / "mms"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_root / "config.toml"),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "stable_root_human_only" in result["errors"]
    assert not config_root.exists()


def test_config_web_registry_v2_apply_writes_preview_candidates_and_bundle(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    credentials_path = config_root / "credentials.sh"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    router_path = config_root / "generated" / "model-routes.json"
    manifest_path = config_root / "generated" / "model-registry.latest-approved.json"
    secret_path = config_root / "secrets" / "webui-secrets.json"
    router = json.loads(router_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["schema"] == "mms.setup_web.registry_v2_apply_result.v1"
    assert result["status"] == "verified"
    assert result["candidate"]["route_candidates"]["provider_route_count"] == 2
    assert result["credential_backend"]["count"] == 1
    assert result["publish"]["preview_source"] == "registry-v2-save-candidate"
    assert result["publish"]["runtime_ready"] is True
    assert result["verify"]["verified"] is True
    assert router["source"] == "registry-preview-v2-save-candidate"
    assert router["routes"]["gpt-5.5"]["primary"]["secret_ref"] == "pending-webui:demo:api_key"
    assert router["routes"]["gpt-5.5"]["primary"]["api_key"] == "sk-super-secret-value"
    assert manifest_path.exists()
    assert secret_path.exists()
    assert "sk-super-secret-value" in secret_path.read_text(encoding="utf-8")
    assert not config_path.exists()
    assert not credentials_path.exists()
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_routes_visible_model_rows_without_fallback_lists(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = json.loads(json.dumps(_draft_payload()))
    provider = payload["draft"]["providers"][0]
    provider["fallback_models"] = []
    provider["extra_models"] = []
    provider["hidden_models"] = ["noisy-model"]
    provider["models"] = [
        {"id": "qwen3.6-plus", "visible": True},
        {"id": "noisy-model", "visible": False},
    ]
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    profile = json.loads((config_root / "generated" / "provider-profiles.generated.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["candidate"]["route_candidates"]["provider_route_count"] == 1
    assert set(router["routes"]) == {"qwen3.6-plus"}
    assert router["routes"]["qwen3.6-plus"]["primary"]["provider_id"] == "demo"
    assert profile["profiles"]["demo"]["hidden_models"] == ["noisy-model"]
    assert profile["provider"]["default"] == "demo"


def test_config_web_registry_v2_apply_routes_visible_model_rows_with_existing_fallback_lists(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = json.loads(json.dumps(_draft_payload()))
    provider = payload["draft"]["providers"][0]
    provider["fallback_models"] = ["gpt-5.5"]
    provider["extra_models"] = []
    provider["models"] = [
        {"id": "gpt-5.5", "visible": True},
        {"id": "qwen3.6-plus", "visible": True},
        {"id": "hidden-remote", "visible": False},
    ]
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert set(router["routes"]) == {"gpt-5.5", "qwen3.6-plus"}
    assert router["routes"]["qwen3.6-plus"]["primary"]["provider_id"] == "demo"
    assert "hidden-remote" not in router["routes"]


def test_config_web_registry_v2_apply_scoped_provider_routes_preserve_other_channels(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"

    def provider(provider_id, priority, models):
        return {
            "original_id": provider_id,
            "id": provider_id,
            "name": provider_id,
            "enabled": True,
            "role": "primary",
            "priority": priority,
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "opencode"],
            "models_endpoint": "manual",
            "openai_base_url": f"https://{provider_id}.example/v1",
            "anthropic_base_url": f"https://{provider_id}.example/v1",
            "api_key": f"sk-{provider_id}-secret",
            "update_credentials": True,
            "fallback_models": models,
            "extra_models": [],
            "hidden_models": [],
            "models": [{"id": model, "visible": True} for model in models],
        }

    first_payload = {
        "draft": {
            "provider_default": "tokyo",
            "providers": [
                provider("tokyo", 200, ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5[1m]"]),
                provider("tencent", 100, ["mimo-v2.5", "mimo-v2.5-pro"]),
            ],
            "rescue": {},
            "vision_sidecar": {},
            "runtime": {"preferred_cli": "opencode", "coding_preset_model": "mimo-v2.5"},
            "opencode": {"default_profile": "lite_pro_orchestrated", "agent_models": {}},
        },
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }
    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        first_payload,
        config_path=str(config_path),
    )

    second_payload = json.loads(json.dumps(first_payload))
    second_payload["draft"]["route_scope_provider_ids"] = ["tencent"]
    second_payload["draft"]["providers"][0]["models"] = [{"id": "mimo-v2.5[1m]", "visible": True}]
    second_payload["draft"]["providers"][0]["fallback_models"] = ["mimo-v2.5[1m]"]
    second_payload["draft"]["providers"][1]["models"] = [
        {"id": "mimo-v2.5", "visible": True},
        {"id": "mimo-v2.5-pro", "visible": True},
        {"id": "mimo-v2.5[1m]", "visible": True},
    ]
    second_payload["draft"]["providers"][1]["fallback_models"] = ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5[1m]"]
    second = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        second_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    def providers_for(model):
        route = router["routes"][model]
        leaves = [route["primary"], *(route.get("fallbacks") or [])]
        return {leaf["provider_id"] for leaf in leaves}

    assert first["ok"] is True
    assert second["ok"] is True
    assert providers_for("mimo-v2.5") == {"tokyo", "tencent"}
    assert providers_for("mimo-v2.5-pro") == {"tokyo", "tencent"}
    assert providers_for("mimo-v2.5[1m]") == {"tokyo", "tencent"}
    assert router["routes"]["mimo-v2.5"]["primary"]["provider_id"] == "tokyo"
    assert second["candidate"]["route_candidates"]["provider_route_count"] == 6


def test_config_web_registry_v2_apply_scoped_provider_manual_add_preserves_provider_routes(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"

    def provider(provider_id, priority, models):
        return {
            "original_id": provider_id,
            "id": provider_id,
            "name": provider_id,
            "enabled": True,
            "role": "primary",
            "priority": priority,
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "opencode"],
            "models_endpoint": "manual",
            "openai_base_url": f"https://{provider_id}.example/v1",
            "anthropic_base_url": f"https://{provider_id}.example/v1",
            "api_key": f"sk-{provider_id}-secret",
            "update_credentials": True,
            "fallback_models": models,
            "extra_models": [],
            "hidden_models": [],
            "models": [{"id": model, "visible": True} for model in models],
        }

    first_payload = {
        "draft": {
            "provider_default": "tokyo",
            "providers": [
                provider("tokyo", 200, ["mimo-v2.5", "mimo-v2.5-pro", "mimo-v2.5[1m]"]),
                provider("tencent", 100, ["mimo-v2.5", "mimo-v2.5-pro"]),
            ],
            "rescue": {},
            "vision_sidecar": {},
            "runtime": {"preferred_cli": "opencode", "coding_preset_model": "mimo-v2.5"},
            "opencode": {"default_profile": "lite_pro_orchestrated", "agent_models": {}},
        },
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }
    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        first_payload,
        config_path=str(config_path),
    )

    second_payload = json.loads(json.dumps(first_payload))
    second_payload["draft"]["route_scope_provider_ids"] = ["tencent"]
    second_payload["draft"]["providers"][1]["fallback_models"] = []
    second_payload["draft"]["providers"][1]["models"] = []
    second_payload["draft"]["providers"][1]["extra_models"] = ["mimo-v2.5[1m]"]
    second = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        second_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    def providers_for(model):
        route = router["routes"][model]
        leaves = [route["primary"], *(route.get("fallbacks") or [])]
        return {leaf["provider_id"] for leaf in leaves}

    assert first["ok"] is True
    assert second["ok"] is True
    assert providers_for("mimo-v2.5") == {"tokyo", "tencent"}
    assert providers_for("mimo-v2.5-pro") == {"tokyo", "tencent"}
    assert providers_for("mimo-v2.5[1m]") == {"tokyo", "tencent"}
    assert second["candidate"]["route_candidates"]["provider_route_count"] == 6


def test_config_web_registry_v2_apply_refreshed_provider_preserves_stale_routes_until_explicit_cleanup(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"

    def provider(models):
        return {
            "original_id": "tokyo",
            "id": "tokyo",
            "name": "Tokyo",
            "enabled": True,
            "role": "primary",
            "priority": 200,
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "opencode"],
            "models_endpoint": "/models",
            "openai_base_url": "https://tokyo.example/v1",
            "anthropic_base_url": "https://tokyo.example/v1",
            "api_key": "sk-tokyo-secret",
            "update_credentials": True,
            "fallback_models": ["claude-opus-4.7", "claude-opus-4-6-thinking"],
            "extra_models": [],
            "hidden_models": [],
            "models": [{"id": model, "source": "remote", "visible": True} for model in models],
        }

    first_payload = {
        "draft": {
            "provider_default": "tokyo",
            "providers": [provider(["claude-opus-4.7", "claude-opus-4-6-thinking"])],
            "rescue": {},
            "vision_sidecar": {},
            "runtime": {"preferred_cli": "opencode", "coding_preset_model": "claude-opus-4-6-thinking"},
            "opencode": {"default_profile": "lite_pro_orchestrated", "agent_models": {}},
        },
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }
    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        first_payload,
        config_path=str(config_path),
    )

    no_cleanup_payload = json.loads(json.dumps(first_payload))
    no_cleanup_payload["draft"]["route_scope_provider_ids"] = ["tokyo"]
    no_cleanup_payload["draft"]["providers"] = [provider(["claude-opus-4-6-thinking"])]
    no_cleanup = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        no_cleanup_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    assert first["ok"] is True
    assert no_cleanup["ok"] is True
    assert set(router["routes"]) == {"claude-opus-4.7", "claude-opus-4-6-thinking"}
    assert no_cleanup["candidate"]["route_candidates"]["provider_route_count"] == 2

    cleanup_payload = json.loads(json.dumps(no_cleanup_payload))
    cleanup_payload["draft"]["route_refresh_provider_ids"] = ["tokyo"]
    cleanup = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "tokyo", "name": "Old"}], "provider": {"default": "tokyo"}},
        cleanup_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    assert cleanup["ok"] is True
    assert set(router["routes"]) == {"claude-opus-4-6-thinking"}
    assert "claude-opus-4.7" not in router["routes"]
    assert cleanup["candidate"]["route_candidates"]["provider_route_count"] == 1
    assert cleanup["route_publish_guard"]["diff"]["removed_models_sample"] == ["claude-opus-4.7"]


def test_config_web_registry_v2_apply_blocks_route_shrink_from_stale_small_draft(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    large_payload = _large_route_draft_payload(12)
    large_payload["confirm_v2_preview"] = True
    large_payload["confirm_phrase"] = "写入预览DB"

    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "bulk", "name": "Old"}], "provider": {"default": "bulk"}},
        large_payload,
        config_path=str(config_path),
    )
    router_path = config_root / "generated" / "model-routes.json"
    before_router = json.loads(router_path.read_text(encoding="utf-8"))

    small_payload = _draft_payload()
    small_payload["confirm_v2_preview"] = True
    small_payload["confirm_phrase"] = "写入预览DB"
    second = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "bulk", "name": "Old"}], "provider": {"default": "bulk"}},
        small_payload,
        config_path=str(config_path),
    )
    after_router = json.loads(router_path.read_text(encoding="utf-8"))
    encoded = json.dumps(second, ensure_ascii=False, sort_keys=True)

    assert first["ok"] is True
    assert len(before_router["routes"]) == 12
    assert second["ok"] is False
    assert second["status"] == "blocked"
    assert second["route_publish_guard"]["reason"] == "route_shrink_guard"
    assert second["route_publish_guard"]["current"]["route_count"] == 12
    assert second["route_publish_guard"]["candidate"]["route_count"] == 2
    assert len(after_router["routes"]) == 12
    assert after_router["routes"] == before_router["routes"]
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_blocks_stale_bundle_revision(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    manifest_path = config_root / "generated" / "model-registry.latest-approved.json"
    before_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale_payload = _draft_payload()
    stale_payload["draft"]["expected_bundle_revision"] = "bundle_stale_revision"
    stale_payload["confirm_v2_preview"] = True
    stale_payload["confirm_phrase"] = "写入预览DB"

    second = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        stale_payload,
        config_path=str(config_path),
    )
    after_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    encoded = json.dumps(second, ensure_ascii=False, sort_keys=True)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status"] == "blocked"
    assert second["route_publish_guard"]["reason"] == "stale_preview_bundle_revision"
    assert second["route_publish_guard"]["expected_bundle_revision"] == "bundle_stale_revision"
    assert second["route_publish_guard"]["current"]["bundle_revision"] == before_manifest["bundle_revision"]
    assert after_manifest["bundle_revision"] == before_manifest["bundle_revision"]
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_republishes_no_diff_when_manifest_missing(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    app = mms_config_web.ConfigWebApp(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        config_path=str(config_path),
        command_name="mmf",
    )
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    first = app.registry_v2_apply(payload)
    snapshot = app.snapshot()
    manifest_path = config_root / "generated" / "model-registry.latest-approved.json"
    manifest_path.unlink()
    republish_payload = {
        "draft": {
            key: snapshot[key]
            for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")
        },
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }

    second = app.registry_v2_apply(republish_payload)

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["registry_v2_save_plan"]["route_publish_work"]["has_route_publish_work"] is True
    assert "no_draft_changes" not in second["registry_v2_save_plan"]["blocked_reasons"]
    assert manifest_path.exists()


def test_config_web_registry_v2_apply_publishes_route_delta_without_config_diff(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    snapshot = mms_config_web.build_config_snapshot(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        config_path=str(config_path),
        command_name="mmf",
    )
    draft = {
        key: snapshot[key]
        for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")
    }
    provider = draft["providers"][0]
    provider["fallback_models"] = [*provider["fallback_models"], "new-webui-model"]
    provider["models"] = [*provider["models"], {"id": "new-webui-model", "visible": True}]
    current_cfg = mms_config_web.build_config_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        {"draft": draft},
        config_path=str(config_path),
        command_name="mmf",
    )["config"]
    route_delta_payload = {
        "draft": draft,
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }

    second = mms_config_web.apply_registry_v2_preview_plan(
        current_cfg,
        route_delta_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["registry_v2_save_plan"]["route_publish_work"]["has_draft_changes"] is False
    assert second["registry_v2_save_plan"]["route_publish_work"]["has_route_publish_work"] is True
    assert "no_draft_changes" not in second["registry_v2_save_plan"]["blocked_reasons"]
    assert "new-webui-model" in router["routes"]


def test_config_web_preview_snapshot_hydrates_channels_from_latest_bundle(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    apply_result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        payload,
        config_path=str(config_path),
    )

    snapshot = mms_config_web.build_config_snapshot(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        config_path=str(config_path),
        command_name="mmf",
    )
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    provider = snapshot["providers"][0]

    assert apply_result["ok"] is True
    assert snapshot["provider_default"] == "demo"
    assert [item["id"] for item in snapshot["providers"]] == ["demo"]
    assert provider["name"] == "Demo Gateway"
    assert provider["openai_base_url"] == "https://demo.example/v1"
    assert provider["anthropic_base_url"] == "https://demo.example/v1"
    assert provider["has_api_key"] is True
    assert provider["fallback_models"] == ["gpt-5.5", "qwen3.6-plus"]
    assert [row["id"] for row in provider["models"]] == ["gpt-5.5", "qwen3.6-plus"]
    assert "sk-super-secret-value" not in encoded


def test_config_web_preview_snapshot_merges_profile_only_channels_from_latest_bundle(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = json.loads(json.dumps(_draft_payload()))
    payload["draft"]["providers"].append(
        {
            "original_id": "newapi-tencent",
            "id": "newapi-tencent",
            "name": "newapi-tencent",
            "enabled": True,
            "role": "fallback",
            "priority": 100,
            "protocols": ["anthropic_messages", "openai_chat_completions"],
            "supported_clis": ["claude", "codex", "opencode"],
            "models_endpoint": "/api/models/info?",
            "openai_base_url": "https://apple.example",
            "anthropic_base_url": "https://apple.example",
            "api_key": "sk-tencent-secret",
            "update_credentials": True,
            "fallback_models": [],
            "extra_models": [],
            "hidden_models": [],
            "models": [],
        }
    )
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    apply_result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        payload,
        config_path=str(config_path),
    )
    runtime_cfg = {
        "providers": [
            {
                "id": "demo",
                "name": "Demo Gateway",
                "enabled": True,
                "role": "primary",
                "priority": 1000,
                "protocols": ["anthropic_messages", "openai_chat_completions"],
                "supported_clis": ["claude", "codex", "opencode"],
                "models_endpoint": "manual",
                "openai_base_url": "https://demo.example/v1",
                "anthropic_base_url": "https://demo.example/v1",
                "api_key": "sk-super-secret-value",
                "fallback_models": ["gpt-5.5", "qwen3.6-plus"],
            }
        ],
        "provider": {"default": "demo"},
    }

    snapshot = mms_config_web.build_config_snapshot(
        runtime_cfg,
        config_path=str(config_path),
        command_name="mmf",
    )
    ids = [item["id"] for item in snapshot["providers"]]
    tencent = next(item for item in snapshot["providers"] if item["id"] == "newapi-tencent")
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

    assert apply_result["ok"] is True
    assert apply_result["runtime_ready"] is True
    assert "demo" in ids
    assert "newapi-tencent" in ids
    assert tencent["has_api_key"] is True
    assert tencent["models_endpoint"] == "/api/models/info?"
    assert "sk-tencent-secret" not in encoded
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_republish_reuses_preview_secret_refs(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    first = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        payload,
        config_path=str(config_path),
    )
    snapshot = mms_config_web.build_config_snapshot(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        config_path=str(config_path),
        command_name="mmf",
    )
    snapshot["providers"][0]["api_key"] = ""
    snapshot["providers"][0]["update_credentials"] = False
    republish_payload = {
        "draft": {
            key: snapshot[key]
            for key in ("providers", "provider_default", "rescue", "vision_sidecar", "runtime", "opencode")
        },
        "confirm_v2_preview": True,
        "confirm_phrase": "写入预览DB",
    }

    second = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        republish_payload,
        config_path=str(config_path),
    )
    router = json.loads((config_root / "generated" / "model-routes.json").read_text(encoding="utf-8"))
    leaves = [router["routes"]["gpt-5.5"]["primary"], router["routes"]["qwen3.6-plus"]["primary"]]
    encoded = json.dumps(second, ensure_ascii=False, sort_keys=True)

    assert first["runtime_ready"] is True
    assert second["ok"] is True
    assert second["status"] == "verified"
    assert second["runtime_ready"] is True
    assert second["credential_backend"]["skipped"] is True
    assert {leaf["secret_ref"] for leaf in leaves} == {"pending-webui:demo:api_key"}
    assert all(leaf["api_key"] == "sk-super-secret-value" for leaf in leaves)
    assert "sk-super-secret-value" not in encoded


def test_config_web_provider_model_fetch_resolves_preview_secret_ref(monkeypatch, tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    apply_result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        payload,
        config_path=str(config_path),
    )
    snapshot = mms_config_web.build_config_snapshot(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        config_path=str(config_path),
        command_name="mmf",
    )
    provider_payload = dict(snapshot["providers"][0])
    provider_payload["api_key"] = ""
    seen = {}

    def fake_probe(provider, *, force_refresh=False):
        seen["api_key"] = provider.get("api_key")
        seen["secret_ref"] = provider.get("secret_ref")
        return {"models": ["gpt-5.5"], "raw_models": ["gpt-5.5"], "base_source": "remote", "working_url": provider.get("openai_base_url")}

    monkeypatch.setattr(mms_config_web, "probe_provider_models", fake_probe)

    result = mms_config_web.test_provider_models(
        {"providers": [{"id": "default", "name": "Default Gateway"}], "provider": {"default": "default"}},
        {"provider": provider_payload, "force_refresh": True},
        config_path=str(config_path),
        command_name="mmf",
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert apply_result["ok"] is True
    assert result["ok"] is True
    assert result["models"] == ["gpt-5.5"]
    assert seen["secret_ref"] == "pending-webui:demo:api_key"
    assert seen["api_key"] == "sk-super-secret-value"
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_surfaces_runtime_not_ready_without_keys(tmp_path):
    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    provider = payload["draft"]["providers"][0]
    provider["api_key"] = ""
    provider["update_credentials"] = False
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)
    secret_path = config_root / "secrets" / "webui-secrets.json"

    assert result["ok"] is True
    assert result["status"] == "verified_not_runtime_ready"
    assert result["runtime_ready"] is False
    assert "missing plaintext secrets" in result["runtime_ready_reason"]
    assert result["runtime_blockers"]["missing_api_key_count"] > 0
    assert result["runtime_blockers"]["provider_route_count"] == result["publish"]["provider_route_count"]
    assert result["credential_backend"]["skipped"] is True
    assert result["credential_backend"]["count"] == 0
    assert result["next_action"]["label"].startswith("填写 API Key")
    assert result["verify"]["verified"] is True
    assert not secret_path.exists()
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_updates_in_memory_snapshot(tmp_path):
    config_root = tmp_path / "mms-next"
    app = mms_config_web.ConfigWebApp(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        config_path=str(config_root / "config.toml"),
        command_name="mmf",
    )
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"

    result = app.registry_v2_apply(payload)
    snapshot = app.snapshot()
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

    assert result["ok"] is True
    assert snapshot["providers"][0]["name"] == "Demo Gateway"
    assert snapshot["providers"][0]["hidden_models"] == ["noisy-model"]
    assert snapshot["mode"] == "interactive_audited_save"
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_rolls_back_on_verify_failure(monkeypatch, tmp_path):
    import mms_registry_cli

    config_root = tmp_path / "mms-next"
    config_path = config_root / "config.toml"
    payload = _draft_payload()
    payload["confirm_v2_preview"] = True
    payload["confirm_phrase"] = "写入预览DB"
    monkeypatch.setattr(mms_registry_cli, "verify_approved_bundle", lambda **kwargs: {"verified": False, "errors": ["forced verify failure"]})

    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        payload,
        config_path=str(config_path),
    )
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert result["ok"] is False
    assert result["status"] == "failed_verify"
    assert result["rollback"]["db"]["removed_new_db"] is True
    assert result["rollback"]["credential_backend"]["removed_new_file"] is True
    assert "model-registry.latest-approved.json" in result["rollback"]["generated"]["removed"]
    assert not (config_root / "registry" / "model-registry.sqlite").exists()
    assert not (config_root / "secrets" / "webui-secrets.json").exists()
    assert not (config_root / "generated" / "model-registry.latest-approved.json").exists()
    assert "sk-super-secret-value" not in encoded


def test_config_web_registry_v2_apply_requires_explicit_preview_confirmation(tmp_path):
    config_root = tmp_path / "mms-next"
    result = mms_config_web.apply_registry_v2_preview_plan(
        {"providers": [{"id": "demo", "name": "Old"}], "provider": {"default": "demo"}},
        _draft_payload(),
        config_path=str(config_root / "config.toml"),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "确认" in result["errors"][0]
    assert not config_root.exists()


def test_config_web_provider_model_fetch_can_be_stubbed(monkeypatch):
    monkeypatch.setattr(
        mms_config_web,
        "probe_provider_models",
        lambda provider, force_refresh=False: {
            "models": ["m-a", "m-b"],
            "raw_models": ["m-a", "m-b"],
            "base_source": "remote",
            "working_url": "https://demo.example/v1",
            "details": ["ok"],
        },
    )

    payload = {"provider": {"id": "demo", "openai_base_url": "https://demo.example/v1", "api_key": "sk-secret"}}
    result = mms_config_web.test_provider_models({"providers": []}, payload)

    assert result["ok"] is True
    assert result["models"] == ["m-a", "m-b"]
    assert result["cache_transport_evidence"]["request_path"] == "/models"
    assert "sk-secret" not in json.dumps(result, ensure_ascii=False)


def test_setup_web_requests_are_guard_exempt():
    assert mms_core._is_setup_web_request(["setup"])
    assert mms_core._is_setup_web_request(["config", "web"])
    assert mms_core._is_config_help_request(["web"])
    assert not mms_core._config_subcommand_mutates_legacy_config(["web"])
    assert not mms_core._config_subcommand_mutates_legacy_config(["web", "--print-summary"])
