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
    assert "stable legacy 保存写入 config.toml 的 [rescue] / [vision_sidecar]" in html
    assert "preview root 走 DB candidate + latest-approved publish" in html
    assert "stable 写 credentials.sh；preview 写 secret backend" in html
    assert "这里会写入 config.toml 的 [rescue]" not in html
    assert "保存时更新 credentials.sh（需要填写 API Key；会 backup + audit）" not in html
    assert "function renderSaveControls()" in html
    assert "saveBtn').disabled=preview" in html
    assert "document.querySelectorAll('.legacy-save-action').forEach" in html
    assert "applyV2Preview').disabled=!preview" in html
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
    assert "当前通道补充模型库（extra_models）" in html
    assert "不是待删除列表，也不是全局模型池" in html
    assert "编辑补充模型库" in html
    assert "从补充库移除" in html
    assert "移除全部通道过期隐藏记录" in html
    assert "过期隐藏记录（不在当前通道模型列表）" in html
    assert "移除记录不会影响其他通道" in html
    assert "移除隐藏记录" in html
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
    assert second["registry_v2_save_plan"]["route_publish_work"]["has_draft_changes"] is False
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
