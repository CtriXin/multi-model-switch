import json

import mms_config_web
import mms_core


def test_config_web_snapshot_redacts_secrets_and_summarizes_provider():
    cfg = {
        "providers": [
            {
                "id": "direct-qwen",
                "name": "Qwen Direct",
                "enabled": True,
                "api_key": "sk-super-secret-value",
                "anthropic_base_url": "https://qwen.example/v1",
                "protocols": ["anthropic_messages"],
                "supported_clis": ["claude", "opencode"],
                "fallback_models": ["qwen3.6-plus"],
            }
        ],
        "vision_sidecar": {
            "enabled": True,
            "provider_id": "direct-qwen",
            "model": "qwen3.6-plus",
            "api_key": "sk-vision-secret",
        },
        "rescue": {"fallback_model": "deepseek-v4-flash", "hot_fallback_enabled": False},
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
    assert snapshot["providers"][0]["id"] == "direct-qwen"
    assert snapshot["providers"][0]["has_api_key"] is True
    assert snapshot["providers"][0]["model_count"] == 1
    assert snapshot["providers"][0]["api_key"] == ""
    assert snapshot["vision_sidecar"]["api_key"] != "sk-vision-secret"
    assert "sk-vision-secret" not in encoded
    assert "sk-super-secret-value" not in encoded
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
    assert "mms opencode --profile lite_pro_orchestrated" in out


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
    assert "credentials.sh: update provider demo" in plan["diffs"]["credentials"]
    assert "sk-super-secret-value" not in encoded


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
