import json

import mms_config_web


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

    assert snapshot["mode"] == "read_only"
    assert snapshot["providers"][0]["id"] == "direct-qwen"
    assert snapshot["providers"][0]["has_api_key"] is True
    assert snapshot["providers"][0]["model_count"] == 1
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
    assert payload["schema"] == "mms.setup_web.snapshot.v1"
    assert payload["paths"]["config"] == "/tmp/config.toml"
    assert payload["recommendations"]


def test_config_web_markdown_contains_manual_snippets(capsys):
    rc = mms_config_web.run_config_web(
        {"providers": []},
        ["--print-markdown"],
        command_name="mms",
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "# MMS Setup Plan" in out
    assert "[vision_sidecar]" in out
    assert "[rescue]" in out
    assert "## Visual Setup Flow" in out
    assert "Model list test" in out
    assert "hidden_models" in out
    assert "preferred_cli.default" in out
    assert "mms opencode --profile lite_pro_orchestrated" in out
