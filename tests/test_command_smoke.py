from __future__ import annotations


class _FakeTable:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.rows = []

    def add_column(self, *args, **kwargs):
        return None

    def add_row(self, *args, **kwargs):
        self.rows.append((args, kwargs))


class _FakeConsole:
    def print(self, *args, **kwargs):
        return None


class _CollectingConsole:
    def __init__(self):
        self.items = []

    def print(self, *args, **kwargs):
        self.items.append(args[0] if args else "")


def test_usage_main_initializes_rich_before_render(monkeypatch):
    import mms_account_state
    import mms_usage

    def _fake_ensure_rich():
        mms_usage.Table = _FakeTable
        mms_usage.Text = str

    async def _fake_section_claude(_accounts):
        mms_usage.Table(title="Claude")

    monkeypatch.setattr(mms_usage, "Table", None)
    monkeypatch.setattr(mms_usage, "Text", None)
    monkeypatch.setattr(mms_usage, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_usage, "console", _FakeConsole())
    monkeypatch.setattr(mms_usage, "_section_claude", _fake_section_claude)
    monkeypatch.setattr(mms_usage, "_section_codex", lambda _accounts: None)
    monkeypatch.setattr(mms_usage, "_section_providers", lambda _cache=None: None)
    monkeypatch.setattr(mms_usage, "_section_local_stats", lambda: None)
    monkeypatch.setattr(mms_usage, "_load_models_cache", lambda: {})
    monkeypatch.setattr(mms_account_state, "cache_current_claude_token", lambda: None)

    mms_usage.usage_main(
        {"accounts": [{"id": "claude-a", "cli": "claude", "auth_mode": "oauth", "enabled": True}]},
        [],
    )

    assert mms_usage.Table is _FakeTable


def test_handle_session_command_initializes_rich_before_listing(monkeypatch):
    import mms_core
    import mms_session_index

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Text = str

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Text", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", _FakeConsole())
    monkeypatch.setattr(
        mms_session_index,
        "list_indexed_sessions",
        lambda cli_name="claude": [
            {
                "session_id": "session-1",
                "project_path": "/tmp/demo",
                "account_id": "claude-a",
                "last_active_at": "2026-04-16T12:00:00Z",
            }
        ],
    )

    mms_core.handle_session_command(["ls"])

    assert mms_core.Table is _FakeTable


def test_handle_session_prune_dry_run_lists_stale_gateway_sessions(monkeypatch, tmp_path):
    import mms_core

    real_home = tmp_path / "home"
    stale = real_home / ".config" / "mms" / "claude-gateway" / "s" / "999999"
    stale.mkdir(parents=True)
    (stale / "payload.txt").write_text("stale session\n", encoding="utf-8")
    console = _CollectingConsole()

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Text = str

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Text", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", console)
    monkeypatch.setattr(mms_core, "resolve_real_user_home", lambda: str(real_home))

    mms_core.handle_session_command(["prune", "--cli", "claude"])

    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables
    assert tables[0].rows[0][0][0] == "claude"
    assert tables[0].rows[0][0][1] == "999999"
    assert stale.exists()


def test_session_command_parser_dispatches_prune_args():
    import mms_command_tools

    calls = []

    mms_command_tools.handle_session_command(
        ["prune", "--cli", "opencode", "--apply", "--yes"],
        command_name="mmg",
        handle_session_ls=lambda cli: calls.append(("ls", cli)),
        handle_session_info=lambda session_id, cli: calls.append(("info", session_id, cli)),
        handle_session_prune=lambda cli, apply=False, yes=False: calls.append(("prune", cli, apply, yes)),
    )

    assert calls == [("prune", "opencode", True, True)]


def test_command_request_classifiers_preserve_help_and_safe_prune_semantics():
    import mms_command_tools
    import mms_core

    assert mms_command_tools.is_help_request(["config", "preferences.help"]) is True
    assert mms_command_tools.is_help_request(["config", "set", "cache.probe_async_min_interval_sec", "5"]) is False
    assert mms_command_tools.is_setup_web_request(["config", "setup-web"]) is True
    assert mms_command_tools.is_session_prune_dry_run(["session", "prune"]) is True
    assert mms_command_tools.is_session_prune_dry_run(["session", "prune", "--apply"]) is False

    assert mms_core._is_help_request(["config", "human-gate"]) is True
    assert mms_core._is_setup_web_request(["web-setup"]) is True
    assert mms_core._is_config_help_request(["preferences.example"]) is True
    assert mms_core._is_session_prune_dry_run(["session", "ls"]) is False


def test_launch_trace_formatter_preserves_sources_and_override_chain():
    import mms_command_tools

    trace_overrides = [
        ("cli arg", {"cli": "codex", "model": "gpt-5.4"}),
        ("runtime resolve", {"provider": "relay", "runtime": "api_key", "bridge": "http://bridge"}),
        ("empty", {}),
    ]
    runtime = {"auth_mode": "api_key", "provider_id": "relay"}

    report = mms_command_tools.format_launch_trace(
        "codex",
        {"model": "gpt-5.4"},
        runtime,
        trace_overrides,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: "",
        runtime_bridge=lambda runtime: "http://bridge",
    )

    assert "[MMS Trace]" in report
    assert "cli:      codex <- cli arg" in report
    assert "provider: relay <- runtime resolve" in report
    assert "account:  - <- (not set)" in report
    assert "model:    gpt-5.4 <- cli arg" in report
    assert "bridge:   http://bridge <- runtime resolve" in report
    assert "runtime:  api_key <- runtime resolve" in report
    assert "cli arg         -> cli=codex, model=gpt-5.4" in report
    assert "empty           -> (none)" in report


def test_settings_result_display_helpers_format_payload_and_fallback_report():
    import mms_command_tools

    payload = mms_command_tools.settings_result_tui_payload(
        "done",
        [("Key", "value"), ("Blank", "")],
        "note",
        localize=lambda zh, en: zh,
    )
    assert payload == (
        "✓ done",
        [("状态", "成功"), ("Key", "value"), ("Blank", "-"), ("说明", "note")],
        [("back", "返回")],
    )
    assert mms_command_tools.compact_tui_report_value("x" * 12, max_len=5) == "xxxx…"

    console = _CollectingConsole()
    mms_command_tools.display_settings_result_report(
        "failed",
        [("Reason", "line1\nline2")],
        "try again",
        ok=False,
        console=console,
    )
    assert console.items == [
        "[red]✗ failed[/red]",
        "[cyan]Reason[/cyan] line1 line2",
        "[dim]try again[/dim]",
    ]


def test_model_probe_recovery_helpers_preserve_findings_actions_and_details():
    import mms_command_tools

    provider = {"id": "relay", "name": "Relay"}
    probe = {"error_kind": "protocol_unsupported", "details": ["provider: Relay", "error: unsupported"]}

    findings = mms_command_tools.model_validation_findings(
        provider,
        probe,
        provider_label=lambda item: item["name"],
    )
    assert findings[0]["severity"] == "high"
    assert findings[0]["title"] == "当前 provider 不支持模型探测"
    assert "Relay 没有声明" in findings[0]["summary"]
    assert findings[-1]["severity"] == "low"

    actions = mms_command_tools.build_model_recovery_actions(
        {"providers": [{"id": "relay"}, {"id": "backup"}]},
        provider,
        probe,
        provider_map=lambda cfg: {item["id"]: item for item in cfg["providers"]},
    )
    assert [item["id"] for item in actions] == [
        "edit_credentials",
        "switch_provider",
        "show_details",
        "continue_without_validation",
    ]
    assert actions[1]["recommended"] is True

    class FakePanel:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    console = _CollectingConsole()
    mms_command_tools.display_model_probe_details(probe, panel_cls=FakePanel, console=console)
    panel = console.items[0]
    assert panel.body == "- provider: Relay\n- error: unsupported"
    assert panel.kwargs == {"title": "校验详情", "border_style": "yellow"}


def test_rescue_report_payload_helpers_preserve_safe_local_outputs():
    import mms_command_tools

    localize = lambda zh, en: zh
    title, rows, note = mms_command_tools.rescue_default_fallback_report_payload(
        "deepseek-v4-flash",
        localize=localize,
    )
    hot_title, hot_rows, hot_note = mms_command_tools.rescue_default_fallback_report_payload(
        "deepseek-v4-flash",
        hot_fallback_enabled=True,
        localize=localize,
    )
    clear_title, clear_rows, clear_note = mms_command_tools.rescue_default_fallback_report_payload(
        "",
        cleared=True,
        localize=localize,
    )
    blocked_title, blocked_rows, _blocked_note = mms_command_tools.rescue_hot_fallback_toggle_report_payload(
        True,
        has_default=False,
        localize=localize,
    )
    demo_title, demo_rows, _demo_note = mms_command_tools.rescue_demo_packet_report_payload(
        {"artifacts": {"markdown": "/tmp/rescue.md", "json": "/tmp/rescue.json"}},
        localize=localize,
    )
    paths_title, paths_rows, _paths_note = mms_command_tools.rescue_paths_report_payload(
        {"artifact_markdown": "/tmp/current.md", "artifact_json": "/tmp/current.json"},
        localize=localize,
    )
    handover_title, handover_rows, handover_note = mms_command_tools.rescue_handover_report_payload(
        {"artifacts": {"markdown": "/tmp/handover.md", "latest_markdown": "/tmp/latest.md"}},
        "deepseek-v4-flash",
        localize=localize,
    )

    assert title == "全局 fallback 已设置"
    assert ("Model", "deepseek-v4-flash") in rows
    assert ("Hot fallback", "关闭") in rows
    assert "只记录 rescue / fallback handoff" in note
    assert hot_title == "全局 fallback 已设置"
    assert ("Hot fallback", "开启") in hot_rows
    assert "routed model" in hot_note
    assert clear_title == "全局 fallback 已清除"
    assert ("保存位置", "[rescue].fallback_model") in clear_rows
    assert clear_note == ""
    assert blocked_title == "无法开启 hot fallback"
    assert ("原因", "请先设置全局 fallback model") in blocked_rows
    assert demo_title == "测试 rescue packet 已生成"
    assert ("rescue.md", "/tmp/rescue.md") in demo_rows
    assert paths_title == "Rescue 文件路径"
    assert ("rescue.json", "/tmp/current.json") in paths_rows
    assert handover_title == "fallback handover 已生成"
    assert ("latest", "/tmp/latest.md") in handover_rows
    assert "不切换当前 session" in handover_note


def test_registry_report_payload_helpers_preserve_compact_outputs():
    import mms_command_tools

    localize = lambda zh, en: zh
    source_title, source_rows, _source_note = mms_command_tools.registry_source_staleness_report_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "due_count": 2,
            "source_count": 6,
            "sources": [
                {"due": True, "reason": "age", "checked_at": "2026-05-28", "source_path": f"/tmp/source-{idx}"}
                for idx in range(6)
            ],
        },
        localize=localize,
    )
    refresh_title, refresh_rows, refresh_note = mms_command_tools.registry_refresh_sources_report_payload(
        {"db_path": "/tmp/db.sqlite", "imported_count": 1, "model_count": 2, "fact_count": 3},
        localize=localize,
    )
    scheduled_title, scheduled_rows, scheduled_note = mms_command_tools.registry_scheduled_refresh_report_payload(
        {
            "db_path": "/tmp/db.sqlite",
            "dry_run": True,
            "source_due_count": 2,
            "source_refresh": {"imported_count": 0},
            "openrouter_due": False,
            "openrouter_fetch": {},
        },
        localize=localize,
    )
    fetch_title, fetch_rows, fetch_note = mms_command_tools.registry_openrouter_fetch_report_payload(
        {"db_path": "/tmp/db.sqlite", "snapshot_id": "snap-1", "model_count": 9},
        localize=localize,
    )
    diff_title, diff_rows, diff_note = mms_command_tools.registry_openrouter_diff_report_payload(
        {
            "change_count": 6,
            "stored_count": 6,
            "missing_reference_count": 1,
            "untracked_catalog_count": 3,
            "changes": [
                {"field_key": "context_window", "model_key": f"gpt-{idx}", "provider_model_id": f"openai/gpt-{idx}"}
                for idx in range(6)
            ],
        },
        localize=localize,
    )
    publish_title, publish_rows, publish_note = mms_command_tools.registry_publish_approved_report_payload(
        {"manifest_path": "/tmp/manifest.json", "bundle_revision": "rev-1"},
        localize=localize,
    )
    verify_title, verify_rows, verify_note = mms_command_tools.registry_verify_approved_report_payload(
        {
            "manifest_path": "/tmp/manifest.json",
            "manifest": {"bundle_revision": "rev-1"},
            "verified_files": {"a": "hash", "b": "hash"},
        },
        localize=localize,
    )
    doctor_title, doctor_rows, doctor_note = mms_command_tools.registry_doctor_report_payload(
        {"db_path": "/tmp/db.sqlite", "user_version": 1, "counts": {"models": 2, "facts": 3}},
        localize=localize,
    )

    assert source_title == "模型真源 Source Staleness"
    assert ("到期 Source", "2 / 6") in source_rows
    assert ("更多 Source", 1) in source_rows
    assert refresh_title == "刷新 Sources 完成"
    assert ("跳过", 0) in refresh_rows
    assert "不改变当前 runtime defaults" in refresh_note
    assert scheduled_title == "定时刷新结果"
    assert ("OpenRouter", "No Network 模式未拉取") in scheduled_rows
    assert "不接入 startup" in scheduled_note
    assert fetch_title == "OpenRouter Catalog 拉取完成"
    assert ("Snapshot", "snap-1") in fetch_rows
    assert "provider_catalog source snapshot" in fetch_note
    assert diff_title == "OpenRouter Candidate Diff"
    assert ("缺少 reference", 1) in diff_rows
    assert ("更多变化", 1) in diff_rows
    assert "candidate_change evidence" in diff_note
    assert publish_title == "发布 Approved Bundle 完成"
    assert ("Bundle", "rev-1") in publish_rows
    assert "不改 root aliases" in publish_note
    assert verify_title == "Latest-approved hash 验证完成"
    assert ("文件", 2) in verify_rows
    assert verify_note == ""
    assert doctor_title == "Registry Doctor / 状态"
    assert doctor_rows == [("DB", "/tmp/db.sqlite"), ("user_version", 1), ("facts", 3), ("models", 2)]
    assert doctor_note == ""


def test_about_and_snapshot_payload_helpers_preserve_version_actions():
    import mms_command_tools

    localize = lambda zh, en: zh
    title, info_lines, actions = mms_command_tools.about_tui_payload(
        {
            "version_info": {
                "release": "v9.9.9",
                "git_branch": "main",
                "git_commit": "abc123",
                "install_channel": "latest-tag",
                "source": "install.sh",
            },
            "mms": {
                "current": "v9.9.9",
                "latest": "v9.9.10",
                "status": "有新版 v9.9.10",
                "outdated": True,
                "last_error": "SSL handshake failed",
            },
            "clis": {
                "codex": {
                    "label": "codex-cli 0.132.0",
                    "latest": "0.133.0",
                    "status": "有新版 0.133.0",
                    "outdated": True,
                },
                "claude": {"label": "2.1.148 (Claude Code)", "latest": "", "status": "最新"},
            },
        },
        config_path="/tmp/mms/config.toml",
        localize=localize,
    )
    guard_title, guard_info, guard_actions = mms_command_tools.snapshot_guard_tui_payload(
        command_name="mmg",
        localize=localize,
    )
    console = _CollectingConsole()
    mms_command_tools.display_about_version_summary(
        {"mms": {"current": "dev", "status": "最新"}},
        payload_builder=lambda snapshot: ("关于 / About", [("MMS", snapshot["mms"]["current"])], [("back", "返回")]),
        console=console,
    )

    assert title == "关于 / About"
    assert ("MMS", "v9.9.9 · 有新版 v9.9.10") in info_lines
    assert ("Codex", "codex-cli 0.132.0 · 有新版") in info_lines
    assert ("Claude 最新", "未检查") in info_lines
    assert ("Config", "/tmp/mms/config.toml") in info_lines
    assert ("检查错误", "MMS latest 检查失败：SSL handshake，可稍后重试") in info_lines
    assert ("upgrade_mms", "升级 MMS") in actions
    assert ("upgrade_codex_cli", "升级 Codex CLI") in actions
    assert ("upgrade_claude_cli", "升级 Claude CLI") not in actions
    assert guard_title == "启动快照 / Snapshot Guard"
    assert ("CLI", "mmg guard status / accept") in guard_info
    assert guard_actions == [("status", "查看当前 Snapshot 状态"), ("accept", "接受当前 Snapshot"), ("back", "返回")]
    assert console.items == ["[cyan]关于 / About[/cyan]", "[cyan]MMS[/cyan] dev"]


def test_mms_config_guard_renderers_preserve_human_gate_text():
    import mms_command_tools

    agents_text = mms_command_tools.render_mms_config_agents_guard()
    claude_text = mms_command_tools.render_mms_config_claude_guard()

    assert agents_text.startswith("# AGENTS.md")
    assert "human confirmation before write" in agents_text
    assert "Never overwrite in place without a backup" in agents_text
    assert "`~/.config/mms`" in agents_text
    assert claude_text.startswith("# CLAUDE.md")
    assert "human-only config" in claude_text
    assert "Claude must never auto-write MMS user config" in claude_text
    assert "before/after values" in claude_text


def test_manage_target_helpers_build_sorted_targets_and_fallback_selection():
    import mms_command_tools

    cfg = {
        "provider": {"default": "relay"},
        "account": {"defaults": {"claude": "claude-main"}},
        "providers": [
            {"id": "backup", "name": "Backup"},
            {"id": "relay", "name": "Relay"},
        ],
        "accounts": [
            {"id": "codex-alt", "cli": "codex", "name": "Codex Alt"},
            {"id": "claude-main", "cli": "claude", "name": "Claude Main"},
        ],
    }
    usage = {
        ("provider", "relay"): (2, "2026-05-28"),
        ("provider", "backup"): (5, "2026-05-27"),
        ("account", "claude-main"): (3, "2026-05-28"),
        ("account", "codex-alt"): (1, "2026-05-26"),
    }
    targets = mms_command_tools.build_manage_targets(
        cfg,
        default_provider_id="relay",
        resolve_provider_context=lambda _cfg, provider_id: {"base_url": "https://relay", "api_key": "k"} if provider_id == "relay" else {},
        usage_summary_for_runtime=lambda kind, runtime_id: usage[(kind, runtime_id)],
        probe_account_status=lambda account: {"summary": f"{account['cli']}:ok"},
    )

    assert [item["id"] for item in targets] == ["claude-main", "relay", "codex-alt", "backup"]
    assert targets[0]["summary"] == "官方通道 · CLAUDE / 默认"
    assert targets[1]["summary"] == "默认网关通道"
    assert targets[1]["status"] == "已配置"
    assert targets[3]["status"] == "未配置"

    class FakePanel:
        def __init__(self, body, **kwargs):
            self.body = body
            self.kwargs = kwargs

    class FakePrompt:
        calls = ["9", "2"]

        @classmethod
        def ask(cls, *args, **kwargs):
            return cls.calls.pop(0)

    console = _CollectingConsole()
    selected = mms_command_tools.select_manage_target_fallback(
        targets,
        ensure_rich=lambda: None,
        panel_cls=FakePanel,
        table_cls=_FakeTable,
        prompt_cls=FakePrompt,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("1", "官方", "Claude Main", "CLAUDE", "claude:ok", "3")
    assert selected["id"] == "relay"
    assert any("请输入 1-4 的编号" in str(item) for item in console.items)


def test_rescue_and_registry_tui_payload_helpers_preserve_actions():
    import mms_command_tools

    info_lines, actions = mms_command_tools.rescue_landing_tui_payload(
        "deepseek-v4-flash",
        [{"created_at": "2026-05-23T09:10:11+08:00", "failed_model": "gpt-5.5", "status_code": 429}],
        latest_fallback_event={
            "at": "2026-05-24T01:02:03+08:00",
            "model": "deepseek-v4-flash",
            "note": "rescue_hot_fallback provider=relay",
        },
        hot_fallback_enabled=True,
    )
    info = dict(info_lines)
    action_ids = [action_id for action_id, _label in actions]

    assert info["全局默认"] == "deepseek-v4-flash"
    assert info["Hot fallback"] == "开启"
    assert "1 个 packet" in info["最近失败"]
    assert "2026-05-23 09:10:11" in info["最近失败"]
    assert "2026-05-24 01:02:03" in info["最近 fallback 尝试"]
    assert "rescue_hot_fallback provider=relay" in info["最近 fallback 尝试"]
    assert action_ids[:3] == ["choose_route_default", "manual_default", "clear_default"]
    assert "disable_hot_fallback" in action_ids
    assert "view_packets" in action_ids

    title, registry_info, registry_actions = mms_command_tools.registry_truth_tui_payload(
        {
            "db_path": "/tmp/model-registry.sqlite",
            "counts": {"source_snapshot": 2, "model_identity": 39, "model_fact": 338},
            "source_freshness": {"due_count": 1},
            "latest_source_snapshot": {"source_path": "https://openrouter.ai/api/v1/models"},
        },
        localize=lambda zh, en: zh,
    )
    assert title == "模型真源 / Registry Truth"
    assert [label for label, _value in registry_info] == ["DB", "来源快照", "模型身份", "模型事实", "待刷新来源", "最新来源"]
    assert [action_id for action_id, _label in registry_actions][:4] == [
        "check_staleness",
        "refresh_due_sources",
        "scheduled_dry_run",
        "scheduled_no_network",
    ]
    assert ("doctor", "Registry Doctor / 状态") in registry_actions


def test_model_source_and_speed_labels_preserve_thresholds():
    import mms_command_tools

    assert mms_command_tools.model_source_label("remote") == "远端列表"
    assert mms_command_tools.model_source_label("fallback") == "内置回退"
    assert mms_command_tools.model_source_label("manual") == "手工列表"
    assert mms_command_tools.model_source_label("extra") == "手工补充"
    assert mms_command_tools.model_source_label("derived_alias") == "本地别名"
    assert mms_command_tools.model_source_label("custom") == "custom"
    assert mms_command_tools.model_source_label("") == "-"
    assert mms_command_tools.ttfb_label(None) == "暂无数据"
    assert mms_command_tools.ttfb_label(1199) == "很快"
    assert mms_command_tools.ttfb_label(1200) == "正常"
    assert mms_command_tools.ttfb_label(2500) == "偏慢"
    assert mms_command_tools.ttfb_label(4500) == "很慢"
    assert mms_command_tools.tps_label(None) == "暂无数据"
    assert mms_command_tools.tps_label(80) == "很快"
    assert mms_command_tools.tps_label(40) == "正常"
    assert mms_command_tools.tps_label(20) == "偏慢"
    assert mms_command_tools.tps_label(19.9) == "很慢"


def test_runtime_map_helpers_filter_invalid_and_disabled_entries():
    import mms_command_tools

    cfg = {
        "providers": [
            {"id": "relay", "name": "Relay"},
            {"name": "Missing ID"},
            "bad",
        ],
        "accounts": [
            {"id": "claude-main", "cli": "claude", "enabled": True},
            {"id": "claude-off", "cli": "claude", "enabled": False},
            {"id": "codex-main", "cli": "codex"},
            {"cli": "claude"},
            "bad",
        ],
    }

    assert list(mms_command_tools.provider_map(cfg)) == ["relay"]
    assert list(mms_command_tools.account_map(cfg)) == ["claude-main", "claude-off", "codex-main"]
    assert [item["id"] for item in mms_command_tools.accounts_for_cli(cfg, "claude")] == ["claude-main"]
    assert [item["id"] for item in mms_command_tools.accounts_for_cli(cfg, "codex")] == ["codex-main"]


def test_provider_endpoint_helpers_preserve_config_resolution_semantics():
    import mms_command_tools

    assert mms_command_tools.provider_label({}, default_provider_id="default") == "default"
    assert mms_command_tools.provider_label({"id": "relay", "name": "Relay"}, default_provider_id="default") == "Relay"
    assert mms_command_tools.provider_openai_base_url({"base_url": "https://relay.example"}) == "https://relay.example/v1"
    assert mms_command_tools.provider_openai_base_url({"base_url": "https://relay.example/v1/"}) == "https://relay.example/v1"
    assert mms_command_tools.provider_openai_base_url({"openai_base_url": "https://openai.example/v1/"}) == "https://openai.example/v1"
    assert mms_command_tools.provider_anthropic_base_url({"base_url": "https://anthropic.example", "protocols": "anthropic_messages"}) == "https://anthropic.example"
    assert mms_command_tools.provider_anthropic_base_url({"base_url": "https://relay.example", "protocols": ["openai_chat_completions"]}) == ""
    assert mms_command_tools.provider_has_configured_base_url({"base_url": "https://relay.example"}) is True
    assert mms_command_tools.provider_has_configured_base_url({}) is False
    assert mms_command_tools.provider_id_variants("crs_oracle-gpt") == ["crs_oracle-gpt", "crs-oracle-gpt", "crs_oracle_gpt"]
    assert mms_command_tools.provider_id_variants("") == []
    assert (
        mms_command_tools.resolve_config_provider_id(
            {"crs-oracle-gpt": {}, "backup": {}},
            "crs_oracle_gpt",
        )
        == "crs-oracle-gpt"
    )


def test_env_file_helpers_preserve_shell_parsing_and_paths(tmp_path):
    import mms_command_tools

    env_path = tmp_path / "credentials.sh"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "export MMS_PROVIDER_RELAY_API_KEY='sk test'",
                'MMS_PROVIDER_RELAY_BASE_URL=\"https://relay.example/v1\"',
                "NO_EQUALS",
                "BROKEN='unterminated",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert mms_command_tools.env_file_path("claude", env_dir=str(tmp_path)) == str(tmp_path / "claude.sh")
    assert mms_command_tools.shell_quote("a'b") == "'a'\"'\"'b'"
    assert mms_command_tools.parse_shell_value("'sk test'") == "sk test"
    assert mms_command_tools.parse_shell_value('"quoted"') == "quoted"
    assert mms_command_tools.parse_shell_value("'unterminated") == "unterminated"
    assert mms_command_tools.load_env_file(str(tmp_path / "missing.sh")) == {}
    assert mms_command_tools.load_env_file(str(env_path)) == {
        "MMS_PROVIDER_RELAY_API_KEY": "sk test",
        "MMS_PROVIDER_RELAY_BASE_URL": "https://relay.example/v1",
        "BROKEN": "unterminated",
    }


def test_config_truthy_and_csv_helpers_preserve_cli_prompt_semantics():
    import pytest

    import mms_command_tools

    console = _CollectingConsole()

    assert mms_command_tools.config_truthy(None, default=True) is True
    assert mms_command_tools.config_truthy(None, default=False) is False
    assert mms_command_tools.config_truthy(True) is True
    assert mms_command_tools.config_truthy("disabled") is False
    assert mms_command_tools.config_truthy("yes") is True
    assert mms_command_tools.parse_csv_values(" codex, claude, codex, ,opencode ") == ["codex", "claude", "opencode"]
    assert mms_command_tools.parse_csv_values("codex,claude", allowed_values=["codex", "claude"]) == ["codex", "claude"]
    with pytest.raises(SystemExit) as exc_info:
        mms_command_tools.parse_csv_values("codex,bad", allowed_values=["codex", "claude"], console=console)
    assert exc_info.value.code == 1
    assert console.items == [
        "[red]不支持的值: bad[/red]",
        "[dim]可选值: codex, claude[/dim]",
    ]


def test_model_family_visibility_helpers_preserve_display_filter_semantics():
    import mms_command_tools

    model_families = [
        {"family": "Claude", "keywords": ("claude",), "category": "Claude 系 ⭐"},
        {"family": "GPT", "keywords": ("gpt-", "codex-"), "category": "GPT 系"},
        {"family": "Qwen", "keywords": ("qwen",), "category": "国产系"},
        {"family": "Kimi", "keywords": ("kimi", "k2.6"), "category": "国产系"},
    ]

    def infer_family(model_id):
        return mms_command_tools.infer_model_family(model_id, model_families=model_families)

    assert mms_command_tools.infer_model_family("anthropic/claude-opus-4.7", model_families=model_families) == (
        "Claude",
        "Claude 系 ⭐",
    )
    assert mms_command_tools.infer_model_family("deepseek-v4-pro", model_families=model_families) == ("其他", "其他")
    assert mms_command_tools.model_info_looks_domestic(
        {"model": "gpt-5.5", "backup": "qwen3.6-plus"},
        infer_model_family=infer_family,
        domestic_model_families={"Qwen", "Kimi"},
        domestic_model_keywords=("qwen", "kimi"),
    ) is True
    assert mms_command_tools.mms_model_visible(
        "hidden-model",
        infer_model_family=infer_family,
        hidden_models={"hidden-model"},
        hidden_model_families=set(),
    ) is False
    visible = mms_command_tools.filter_visible_models(
        [" claude-sonnet-4.5 ", "", "hidden-model", "qwen3.6-plus"],
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    )
    assert visible == ["claude-sonnet-4.5", "qwen3.6-plus"]
    assert mms_command_tools.model_info_has_visible_models(
        {"opus": "hidden-model", "sonnet": "claude-sonnet-4.5"},
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    ) is True
    assert mms_command_tools.model_info_has_visible_models(
        {"model": "hidden-model"},
        mms_model_visible=lambda model_id: model_id != "hidden-model",
    ) is False


def test_preference_primitive_helpers_preserve_allowlist_semantics():
    import mms_command_tools

    assert mms_command_tools.merge_dicts(
        {"launch": {"defaults": {"bypass": False}, "cli": {"codex": {"reasoning_effort": "low"}}}},
        {"launch": {"defaults": {"thinking_mode": "enable"}}},
    ) == {
        "launch": {
            "defaults": {"bypass": False, "thinking_mode": "enable"},
            "cli": {"codex": {"reasoning_effort": "low"}},
        }
    }
    assert mms_command_tools.pref_bool("enabled") is True
    assert mms_command_tools.pref_bool("off") is False
    assert mms_command_tools.pref_bool("maybe") is None
    assert mms_command_tools.pref_enable_disable(True) == "enable"
    assert mms_command_tools.pref_enable_disable("disabled") == "disable"
    assert mms_command_tools.pref_enable_disable("maybe") == ""
    assert mms_command_tools.pref_reasoning_effort("XHIGH") == "xhigh"
    assert mms_command_tools.pref_reasoning_effort("extreme") == ""
    assert mms_command_tools.pref_agent_pack("everything_claude_code") == "ecc"
    assert mms_command_tools.pref_agent_pack("oh-my-claude-code") == "omc"
    assert mms_command_tools.pref_agent_pack("off") == "none"
    assert mms_command_tools.sanitize_surface_list(["web-access", "web-access", "", None, "xmem"]) == ["web-access", "xmem"]
    assert mms_command_tools.sanitize_disabled_session_surfaces(
        {"skill": ["web-access"], "mcps": "pilot", "hook": ["/tmp/a", "/tmp/a"], "unknown": ["drop"]}
    ) == {
        "skills": ["web-access"],
        "mcp": ["pilot"],
        "hooks": ["/tmp/a"],
    }


def test_preference_allowlist_sanitizers_preserve_runtime_shape(tmp_path):
    import mms_command_tools

    skill_root = tmp_path / "web-access"
    asset_keys = {"web_access": "web_access", "web-access": "web_access", "xmem": "xmem"}
    raw = {
        "launch": {
            "defaults": {
                "thinking_mode": "enabled",
                "reasoning_effort": "xhigh",
                "caveman_mode": "off",
                "nsr_mode": True,
                "bypass": "no",
                "agent_pack": "oh-my-claude-code",
                "api_key": "ignored",
            },
            "cli": {
                "Codex": {"reasoning_effort": "low", "disabled_session_surfaces": {"skills": ["agent-browser"]}},
                "gemini": {"bypass": True},
                "unknown": {"bypass": True},
            },
        },
        "session_surfaces": {"disabled": {"mcps": ["pilot"], "hook": "/tmp/drop.sh"}},
        "assets": {"roots": {"web-access": str(skill_root), "credentials": "/tmp/ignored"}},
        "provider": {"base_url": "https://ignored.example"},
    }

    assert mms_command_tools.sanitize_launch_preferences(raw["launch"]["defaults"]) == {
        "thinking_mode": "enable",
        "reasoning_effort": "xhigh",
        "caveman_mode": "disable",
        "nsr_mode": "enable",
        "bypass": False,
        "agent_pack": "omc",
        "ecc_mode": "disable",
        "omc_mode": "enable",
    }
    assert mms_command_tools.sanitize_asset_roots(
        {"web-access": str(skill_root), "credentials": "/tmp/ignored"},
        asset_root_keys=asset_keys,
    ) == {"web_access": str(skill_root)}
    assert mms_command_tools.sanitize_user_preferences(raw, cli_names=["claude", "codex"], asset_root_keys=asset_keys) == {
        "launch": {
            "defaults": {
                "thinking_mode": "enable",
                "reasoning_effort": "xhigh",
                "caveman_mode": "disable",
                "nsr_mode": "enable",
                "bypass": False,
                "agent_pack": "omc",
                "ecc_mode": "disable",
                "omc_mode": "enable",
            },
            "cli": {
                "codex": {"reasoning_effort": "low", "disabled_session_surfaces": {"skills": ["agent-browser"]}},
                "gemini": {"bypass": True},
            },
        },
        "session_surfaces": {"disabled": {"mcp": ["pilot"], "hooks": ["/tmp/drop.sh"]}},
        "assets": {"roots": {"web_access": str(skill_root)}},
    }


def test_preference_runtime_overlay_helpers_preserve_merge_order():
    import mms_command_tools

    prefs = {
        "launch": {
            "defaults": {
                "thinking_mode": "enable",
                "reasoning_effort": "xhigh",
                "disabled_session_surfaces": {"skills": ["token-saver"]},
            },
            "cli": {
                "codex": {
                    "reasoning_effort": "low",
                    "disabled_session_surfaces": {"mcp": ["pilot"], "skills": ["token-saver"]},
                }
            },
        },
        "session_surfaces": {"disabled": {"skills": ["web-access"], "hooks": ["/tmp/drop.sh"]}},
    }
    runtime = {
        "id": "relay",
        "reasoning_effort": "medium",
        "disabled_session_surfaces": {"skills": ["existing", "web-access"]},
    }

    assert mms_command_tools.merge_disabled_session_surfaces(
        {"skills": ["existing", "web-access"]},
        {"skills": ["web-access", "token-saver"], "mcps": ["pilot"]},
    ) == {"mcp": ["pilot"], "skills": ["existing", "web-access", "token-saver"]}
    assert mms_command_tools.preference_runtime_overlay(prefs, "codex") == {
        "thinking_mode": "enable",
        "reasoning_effort": "low",
        "disabled_session_surfaces": {
            "skills": ["web-access", "token-saver"],
            "hooks": ["/tmp/drop.sh"],
            "mcp": ["pilot"],
        },
    }

    result = mms_command_tools.runtime_with_launch_preferences(
        {"_mms_preferences": prefs},
        runtime,
        "codex",
        load_user_preferences=lambda: (_ for _ in ()).throw(AssertionError("unused")),
    )
    assert result is not runtime
    assert runtime["reasoning_effort"] == "medium"
    assert result["thinking_mode"] == "enable"
    assert result["reasoning_effort"] == "low"
    assert result["disabled_session_surfaces"] == {
        "skills": ["existing", "web-access", "token-saver"],
        "hooks": ["/tmp/drop.sh"],
        "mcp": ["pilot"],
    }
    assert result["_mms_preferences_applied"] is True
    assert mms_command_tools.runtime_with_launch_preferences(
        {},
        {"_mms_preferences_applied": True},
        "codex",
        load_user_preferences=lambda: prefs,
    ) == {"_mms_preferences_applied": True}
    assert mms_command_tools.runtime_with_launch_preferences(
        {},
        "not-runtime",
        "codex",
        load_user_preferences=lambda: prefs,
    ) == "not-runtime"


def test_vision_sidecar_candidate_helpers_preserve_order_and_overrides():
    import mms_command_tools

    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("direct-mimo") == ["mimo-v2.5", "mimo-v2-omni"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("newapi-personal-kimi") == ["K2.6", "K2.6-code-preview", "kimi-k2.5"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("direct-qwen") == ["qwen3.6-plus", "qwen3.6-flash"]
    assert mms_command_tools.vision_sidecar_model_candidates_for_provider("other")[:3] == ["mimo-v2.5", "mimo-v2-omni", "K2.6"]

    configured = {
        "routes": [
            {"provider": "configured", "vision_model": "vision-a"},
            {"provider_id": "configured", "model": "vision-a"},
            {"provider_id": "second", "model": "vision-b"},
            "bad",
        ]
    }
    assert mms_command_tools.vision_sidecar_candidate_pairs(configured, ["direct-mimo"])[:3] == [
        ("configured", "vision-a"),
        ("second", "vision-b"),
        ("mimo-direct-anthropic", "mimo-v2.5"),
    ]
    assert mms_command_tools.vision_sidecar_candidate_pairs({}, ["a", "b"], explicit_model="chosen") == [
        ("a", "chosen"),
        ("b", "chosen"),
    ]
    assert mms_command_tools.vision_sidecar_candidate_pairs({}, ["ignored"], explicit_provider_id="direct-qwen") == [
        ("direct-qwen", "qwen3.6-plus"),
        ("direct-qwen", "qwen3.6-flash"),
    ]


def test_model_capability_helpers_preserve_native_bridge_and_tags():
    import mms_command_tools

    def infer_family(model_name):
        normalized = str(model_name or "").lower()
        if normalized.startswith("claude-"):
            return "Claude", "Claude 系 ⭐"
        if normalized.startswith(("gpt-", "o1-", "o3-", "o4-", "codex-")):
            return "GPT", "GPT 系"
        if "qwen" in normalized:
            return "Qwen", "国产系"
        return "其他", "其他"

    assert mms_command_tools.native_clis_for_model("claude-sonnet-4.5") == ["claude"]
    assert mms_command_tools.native_clis_for_model("gpt-5.5") == ["codex"]
    assert mms_command_tools.native_clis_for_model("gemini-3.1-pro-preview") == []
    assert mms_command_tools.bridge_clis_for_model("qwen3.6-plus", infer_model_family=infer_family) == ["claude", "codex"]
    assert mms_command_tools.model_cli_modes("gpt-5.5", infer_model_family=infer_family) == {
        "claude": "bridge",
        "codex": "native",
    }
    assert mms_command_tools.model_cli_summary("claude-sonnet-4.5", infer_model_family=infer_family) == "claude:native, codex:bridge"

    tags = mms_command_tools.model_capability_tags(
        "qwen3.6-plus",
        infer_model_family=infer_family,
        model_context_window=lambda _model: 1_000_000,
        reasoning_model_hints=("gpt-5",),
        tool_use_families={"Claude", "GPT", "Qwen"},
        vision_capable_model_names={"qwen3.6-plus"},
        vision_capable_model_hints=("gemini-",),
    )
    assert tags == ["vision", "tool_use", "long_context", "bridge_required"]
    assert (
        mms_command_tools.model_capability_summary(
            "qwen3.6-plus",
            model_capability_tags=lambda model_id: tags if model_id == "qwen3.6-plus" else [],
        )
        == "vision, tool_use, long_context, bridge_required"
    )


def test_runtime_normalization_helpers_preserve_provider_and_model_semantics():
    import mms_command_tools

    assert mms_command_tools.normalize_provider_id_input(" CRS Oracle! ", default_provider_id="default") == "crs-oracle"
    assert mms_command_tools.normalize_provider_id_input("!!!", default_provider_id="default") == "default"
    assert mms_command_tools.sanitize_provider_id("crs-oracle/gpt", default_provider_id="default") == "CRS_ORACLE_GPT"
    assert mms_command_tools.sanitize_provider_id("!!!", default_provider_id="default") == "DEFAULT"
    assert mms_command_tools.normalize_model_id_list("gpt-5.5, ,gpt-5.4,gpt-5.5") == ["gpt-5.5", "gpt-5.4"]
    assert mms_command_tools.normalize_model_id_list([" a ", None, "a", "b"]) == ["a", "b"]
    assert mms_command_tools.unique_runtime_id({"relay", "relay-2"}, "relay") == "relay-3"
    assert mms_command_tools.unique_runtime_id(set(), "") == "default"
    assert mms_command_tools.normalize_models_endpoint("") == "/models"
    assert mms_command_tools.normalize_models_endpoint("manual") == "manual"
    assert mms_command_tools.normalize_models_endpoint("api/models") == "/api/models"
    assert mms_command_tools.normalize_models_endpoint("/v1/models") == "/v1/models"
    assert (
        mms_command_tools.provider_env_name("crs-oracle/gpt", "API_KEY", default_provider_id="default")
        == "MMS_PROVIDER_CRS_ORACLE_GPT_API_KEY"
    )
    assert (
        mms_command_tools.provider_env_value(
            "crs-oracle/gpt",
            "API_KEY",
            default_provider_id="default",
            environ={"MMS_PROVIDER_CRS_ORACLE_GPT_API_KEY": " key "},
        )
        == "key"
    )


def test_runtime_priority_and_supported_cli_helpers_preserve_normalization():
    import mms_command_tools

    model_families = [{"family": "GPT"}, {"family": "Claude"}]
    cli_names = ["claude", "codex", "opencode"]
    legacy_aliases = {"provider", "gateway"}

    assert mms_command_tools.normalize_supported_clis(
        "provider",
        protocols=["anthropic_messages", "openai_chat_completions"],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_aliases,
    ) == ["claude", "codex"]
    assert mms_command_tools.normalize_supported_clis(
        ["codex", "unknown", "codex", "opencode"],
        protocols=[],
        cli_names=cli_names,
        legacy_provider_cli_aliases=legacy_aliases,
    ) == ["codex", "opencode"]
    assert mms_command_tools.normalize_priority("7", default_priority=50) == 7
    assert mms_command_tools.normalize_priority("0", default_priority=50) == 1
    assert mms_command_tools.normalize_priority("bad", default_priority=50) == 50
    assert mms_command_tools.canonical_model_family("gpt", model_families=model_families) == "GPT"
    assert mms_command_tools.canonical_model_family("unknown", model_families=model_families) == ""
    assert mms_command_tools.normalize_family_priority_overrides(
        {"gpt": "9", "Claude": 0, "unknown": 99},
        model_families=model_families,
        default_priority=50,
    ) == {"GPT": 9, "Claude": 1}
    assert mms_command_tools.normalize_family_priority_overrides([], model_families=model_families, default_priority=50) == {}
    assert mms_command_tools.normalize_role("PRIMARY", valid_roles={"primary", "auto", "fallback"}) == "primary"
    assert mms_command_tools.normalize_role("bad", valid_roles={"primary", "auto", "fallback"}) == "auto"
    assert mms_command_tools.normalize_positive_seconds("0", 30, minimum=5) == 5
    assert mms_command_tools.normalize_positive_seconds("42", 30, minimum=5) == 42
    assert mms_command_tools.normalize_positive_seconds("bad", 30, minimum=5) == 30


def test_account_mode_timezone_and_ipv4_helpers_preserve_normalization():
    import mms_command_tools

    valid_modes = {"auto", "enable", "disable"}
    assert mms_command_tools.normalize_claude_1m_mode("", default="auto", valid_modes=valid_modes) == "auto"
    assert mms_command_tools.normalize_claude_1m_mode("enabled", default="auto", valid_modes=valid_modes) == "enable"
    assert mms_command_tools.normalize_claude_1m_mode("off", default="auto", valid_modes=valid_modes) == "disable"
    assert mms_command_tools.normalize_claude_1m_mode("bad", default="enable", valid_modes=valid_modes) == "enable"
    assert mms_command_tools.normalize_claude_1m_mode("bad", default="unknown", valid_modes=valid_modes) == "auto"
    assert mms_command_tools.normalize_timezone_name("Asia/Singapore", default="UTC") == "Asia/Singapore"
    assert mms_command_tools.normalize_timezone_name("Bad/Timezone", default="UTC") == "UTC"
    assert mms_command_tools.normalize_timezone_name("", default="Asia/Shanghai") == "Asia/Shanghai"
    assert mms_command_tools.normalize_account_id(" Claude Main! ") == "claude-main"
    assert mms_command_tools.normalize_account_id("!!!") == "account"
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": True}) is True
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "enabled"}) is True
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "off"}) is False
    assert mms_command_tools.runtime_force_ipv4({"force_ipv4": "surprise"}) is False
    assert mms_command_tools.runtime_force_ipv4(None) is False


def test_semver_and_http_status_helpers_preserve_update_semantics():
    import mms_command_tools

    assert mms_command_tools.parse_semver_tag("v1.2.3") == (1, 2, 3)
    assert mms_command_tools.parse_semver_tag("1.2.3") is None
    assert mms_command_tools.normalize_semver_tags(["v1.2.0", "v1.10.0", "bad", "v1.2.0"]) == ["v1.10.0", "v1.2.0"]
    assert mms_command_tools.extract_semver_text("codex-cli 0.133.0-beta.1") == "0.133.0-beta.1"
    assert mms_command_tools.parse_semver_text("codex-cli 0.133.0-beta.1") == (0, 133, 0)
    assert mms_command_tools.compare_semver_text("0.132.0", "0.133.0") == -1
    assert mms_command_tools.compare_semver_text("0.134.0", "0.133.0") == 1
    assert mms_command_tools.compare_semver_text("0.133.0", "0.133.0") == 0
    assert mms_command_tools.compare_semver_text("dev", "0.133.0") is None
    assert mms_command_tools.semver_tag_gap("v1.16.3", ["v1.16.6", "v1.16.5", "v1.16.4", "v1.16.3"]) == 3
    assert mms_command_tools.semver_tag_gap("v1.16.6", ["v1.16.6", "v1.16.5"]) == 0
    assert mms_command_tools.semver_tag_gap("v1.16.6", [], "v2.0.0") is None
    assert mms_command_tools.http_status_is_success("200") is True
    assert mms_command_tools.http_status_is_success("299") is True
    assert mms_command_tools.http_status_is_success("300") is False
    assert mms_command_tools.http_status_is_success("bad") is False


def test_update_status_helpers_preserve_install_and_about_status_semantics():
    import mms_command_tools

    update_sources = {"install.sh", "homebrew"}
    localize = lambda zh, en: zh

    assert mms_command_tools.installed_update_semver(
        {"source": "install.sh", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == ("v1.2.3", (1, 2, 3))
    assert mms_command_tools.installed_update_semver(
        {"install_channel": "latest-tag", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == ("v1.2.3", (1, 2, 3))
    assert mms_command_tools.installed_update_semver(
        {"source": "manual", "installed_version": "v1.2.3"},
        update_notice_sources=update_sources,
    ) == (None, None)
    assert mms_command_tools.installed_update_semver(
        {"source": "install.sh", "installed_version": "dev"},
        update_notice_sources=update_sources,
    ) == (None, None)

    outdated = mms_command_tools.mms_update_status(
        {"installed_version": "v1.2.3"},
        {"latest_tag": "v1.2.4", "last_error": "net"},
        localize=localize,
    )
    assert outdated == {
        "current": "v1.2.3",
        "latest": "v1.2.4",
        "status": "有新版 v1.2.4",
        "outdated": True,
        "last_error": "net",
    }
    assert mms_command_tools.mms_update_status({"release": "dev"}, {"latest_tag": "v1.2.4"}, localize=localize)["status"] == "开发版/无法判断"
    assert mms_command_tools.mms_update_status({"installed_version": "v1.2.4"}, {}, localize=localize)["status"] == "未检查 latest"
    assert mms_command_tools.mms_update_status({"installed_version": "v1.2.4"}, {"latest_tag": "v1.2.4"}, localize=localize)["status"] == "最新"


def test_runtime_usage_model_and_hint_helpers_preserve_tracking_shape():
    import mms_command_tools

    provider_runtime = {
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "id": "relay",
        "provider_id": "relay",
    }
    account_runtime = {
        "runtime_kind": "account",
        "auth_mode": "oauth",
        "id": "claude-main",
        "account_id": "claude-main",
    }

    assert mms_command_tools.runtime_usage_key(provider_runtime, "codex") == "provider:codex:relay"
    assert mms_command_tools.runtime_usage_key({}, "claude") == "provider:claude:default"
    assert mms_command_tools.resolve_model_name({"model": "gpt-5.5", "sonnet": "claude-sonnet"}) == "gpt-5.5"
    assert mms_command_tools.resolve_model_name({"sonnet": "claude-sonnet"}) == "claude-sonnet"
    assert mms_command_tools.resolve_model_name({}) == "official-default"
    assert mms_command_tools.resolve_model_name("") == "official-default"
    assert mms_command_tools.resolve_model_name("gpt-5.4") == "gpt-5.4"
    assert mms_command_tools.runtime_hint_from_runtime(
        provider_runtime,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: runtime.get("account_id", ""),
    ) == {
        "runtime_kind": "provider",
        "auth_mode": "api_key",
        "provider_id": "relay",
        "runtime_id": "relay",
    }
    assert mms_command_tools.runtime_hint_from_runtime(
        account_runtime,
        runtime_provider_id=lambda runtime: runtime.get("provider_id", ""),
        runtime_account_id=lambda runtime: runtime.get("account_id", ""),
    ) == {
        "runtime_kind": "account",
        "auth_mode": "oauth",
        "account_id": "claude-main",
        "runtime_id": "claude-main",
    }
    assert mms_command_tools.runtime_hint_from_runtime(None, runtime_provider_id=lambda runtime: "", runtime_account_id=lambda runtime: "") == {}


def test_env_command_renders_and_writes_export_file(tmp_path):
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {"presets": {"demo": {"cli": "claude", "provider": "relay"}}}
    env_path = tmp_path / "demo.sh"

    def resolve_runtime(_cfg, preset, provider_override=None, stderr_only=False):
        assert preset["provider"] == "relay"
        assert provider_override == "override"
        assert stderr_only is False
        return "claude", {"ANTHROPIC_BASE_URL": "https://relay.example/v1", "API_KEY": "a b"}, {"id": "relay"}

    mms_command_tools.handle_env_command(
        cfg,
        ["demo", "--provider", "override", "--apply"],
        command_name="mmg",
        resolve_named_preset=lambda cfg_arg, name: cfg_arg["presets"][name],
        resolve_preset_export_runtime=resolve_runtime,
        env_dir=str(tmp_path),
        preset_env_file_path=lambda name: str(env_path),
        display_title=lambda: "MMS",
        console=console,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# Generated by MMS" in text
    assert "export ANTHROPIC_BASE_URL=https://relay.example/v1" in text
    assert "export API_KEY='a b'" in text
    assert any("已写入" in str(item) for item in console.items)


def test_activate_command_outputs_eval_exports(capsys):
    import mms_command_tools

    mms_command_tools.handle_activate_command(
        {"presets": {"demo": {"cli": "codex"}}},
        ["demo", "--provider", "relay"],
        command_name="mmg",
        resolve_named_preset=lambda cfg, name, stderr_only=False: cfg["presets"][name],
        resolve_preset_export_runtime=lambda cfg, preset, provider_override=None, stderr_only=False: (
            "codex",
            {"OPENAI_BASE_URL": "https://relay.example/v1", "OPENAI_API_KEY": "k v"},
            {"id": provider_override},
        ),
    )

    out = capsys.readouterr().out
    assert "export OPENAI_BASE_URL=https://relay.example/v1" in out
    assert "export OPENAI_API_KEY='k v'" in out


def test_preset_helper_path_and_missing_preset_message(tmp_path):
    import mms_command_tools

    messages = []
    path = mms_command_tools.preset_env_file_path("Demo Preset!", env_dir=str(tmp_path))
    assert path == str(tmp_path / "demo-preset.sh")

    result = mms_command_tools.resolve_named_preset(
        {"presets": {"demo": {"cli": "claude"}}},
        "missing",
        normalize_preset_entry=lambda name, preset: {"name": name, **preset},
        emit_preset_error=lambda message, stderr_only=False: messages.append((message, stderr_only)),
    )

    assert result is None
    assert messages == [
        ("预设 'missing' 不存在", False),
        ("可用预设: demo", False),
    ]


def test_preset_export_runtime_uses_provider_override_and_exports():
    import mms_command_tools

    calls = []

    result = mms_command_tools.resolve_preset_export_runtime(
        {"providers": []},
        {"cli": "claude", "provider": "relay"},
        provider_override="override",
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        emit_preset_error=lambda message, stderr_only=False: calls.append(("error", message, stderr_only)),
        ensure_provider_credentials=lambda cfg, provider_id: calls.append(("provider", provider_id)) or {"id": provider_id},
        validate_provider_for_cli=lambda cli, runtime: calls.append(("validate", cli, runtime["id"])),
        get_export_env=lambda cli, runtime: calls.append(("exports", cli, runtime["id"])) or {"A": "B"},
    )

    assert result == ("claude", {"A": "B"}, {"id": "override"})
    assert calls == [
        ("provider", "override"),
        ("validate", "claude", "override"),
        ("exports", "claude", "override"),
    ]


def test_preset_export_runtime_rejects_oauth_without_resolving_provider():
    import mms_command_tools

    messages = []

    result = mms_command_tools.resolve_preset_export_runtime(
        {"providers": []},
        {"cli": "claude", "account": "claude-a"},
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        emit_preset_error=lambda message, stderr_only=False: messages.append((message, stderr_only)),
        ensure_provider_credentials=lambda cfg, provider_id: (_ for _ in ()).throw(AssertionError("must not resolve provider")),
        validate_provider_for_cli=lambda cli, runtime: None,
        get_export_env=lambda cli, runtime: {},
    )

    assert result is None
    assert messages == [("此预设使用 oauth 模式，不支持 env export", False)]


def test_presets_command_renders_only_visible_presets():
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {
        "presets": {
            "visible": {
                "cli": "claude",
                "provider": "relay",
                "model": "sonnet",
                "description": "daily",
            },
            "hidden": {"cli": "claude", "account": "official"},
        }
    }

    mms_command_tools.handle_presets_command(
        cfg,
        preset_has_visible_model_options=lambda preset: "model" in preset,
        infer_preset_auth_mode=mms_command_tools.infer_preset_auth_mode,
        default_provider_id="default",
        table_cls=_FakeTable,
        console=console,
    )

    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert len(tables) == 1
    assert tables[0].rows == [(("visible", "claude", "relay", "sonnet", "daily", "api_key"), {})]


def test_models_command_dispatches_selected_provider():
    import mms_command_tools

    calls = []

    mms_command_tools.handle_models_command(
        {"providers": [{"id": "relay"}]},
        [],
        command_name="mmg",
        provider_map=lambda cfg: {"relay": cfg["providers"][0]},
        select_provider_for_models=lambda cfg: "relay",
        manage_provider_models=lambda cfg, provider_id: calls.append((cfg, provider_id)),
        text_cls=str,
        console=_CollectingConsole(),
    )

    assert calls == [({"providers": [{"id": "relay"}]}, "relay")]


def test_models_command_unknown_provider_exits_with_available_list():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_models_command(
            {"providers": [{"id": "relay"}]},
            ["missing"],
            command_name="mmg",
            provider_map=lambda cfg: {"relay": cfg["providers"][0]},
            select_provider_for_models=lambda cfg: "relay",
            manage_provider_models=lambda cfg, provider_id: None,
            text_cls=str,
            console=console,
        )

    assert exc.value.code == 1
    assert any("未找到模型源: missing" in str(item) for item in console.items)
    assert any("relay" in str(item) for item in console.items)


def test_warm_command_uses_recent_models_without_live_requests():
    import mms_command_tools

    class Panel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Prompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            return "1"

    class Confirm:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise AssertionError("recent warm path should not ask confirm")

    calls = []
    console = _CollectingConsole()
    provider = {"id": "relay", "name": "Relay"}

    mms_command_tools.handle_warm_command(
        {"providers": [provider]},
        ["relay"],
        command_name="mmg",
        provider_map=lambda cfg: {"relay": provider},
        select_provider_for_warm=lambda cfg: "relay",
        resolve_provider_context=lambda cfg, provider_id: provider,
        probe_models=lambda provider_arg, emit_output=False: {"models": ["gpt-5.5", "gpt-5.4"]},
        recent_models_for_provider=lambda provider_id: ["gpt-5.4"],
        pick_manual_models=lambda models: (_ for _ in ()).throw(AssertionError("manual picker should not run")),
        warm_model_request=lambda provider_arg, model_name: calls.append((provider_arg["id"], model_name)) or (True, "ok"),
        text_cls=str,
        panel_cls=Panel,
        prompt_cls=Prompt,
        confirm_cls=Confirm,
        table_cls=_FakeTable,
        console=console,
    )

    assert calls == [("relay", "gpt-5.4")]
    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables
    assert tables[0].rows[0][0] == ("gpt-5.4", "成功", "ok")


def test_warm_command_unknown_provider_exits_before_probe():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_warm_command(
            {"providers": [{"id": "relay"}]},
            ["missing"],
            command_name="mmg",
            provider_map=lambda cfg: {"relay": cfg["providers"][0]},
            select_provider_for_warm=lambda cfg: "relay",
            resolve_provider_context=lambda cfg, provider_id: (_ for _ in ()).throw(AssertionError("must not resolve")),
            probe_models=lambda provider, emit_output=False: (_ for _ in ()).throw(AssertionError("must not probe")),
            recent_models_for_provider=lambda provider_id: [],
            pick_manual_models=lambda models: [],
            warm_model_request=lambda provider, model: (True, "ok"),
            text_cls=str,
            panel_cls=object,
            prompt_cls=object,
            confirm_cls=object,
            table_cls=_FakeTable,
            console=console,
        )

    assert exc.value.code == 1
    assert any("未找到模型源: missing" in str(item) for item in console.items)


def test_export_command_writes_temp_env_file(tmp_path):
    import mms_command_tools

    console = _CollectingConsole()
    env_path = tmp_path / "claude.sh"

    mms_command_tools.handle_export(
        "claude",
        {"id": "relay"},
        apply=True,
        cli_names=["claude", "codex"],
        get_export_env=lambda cli, provider: {"ANTHROPIC_BASE_URL": "https://relay.example/v1", "API_KEY": "a b"},
        env_dir=str(tmp_path),
        env_file_path=lambda cli: str(env_path),
        display_title=lambda: "MMS",
        export_command_hint=lambda cli: f"mmg --export {cli} --apply",
        console=console,
    )

    text = env_path.read_text(encoding="utf-8")
    assert "# Generated by MMS" in text
    assert "export ANTHROPIC_BASE_URL=https://relay.example/v1" in text
    assert "export API_KEY='a b'" in text
    assert any("不会自动修改 ~/.zshrc" in str(item) for item in console.items)


def test_export_command_rejects_unsupported_cli_before_export_lookup():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.handle_export(
        "unknown",
        {"id": "relay"},
        cli_names=["claude", "codex"],
        get_export_env=lambda cli, provider: (_ for _ in ()).throw(AssertionError("must not lookup exports")),
        env_dir="/tmp",
        env_file_path=lambda cli: "/tmp/out.sh",
        display_title=lambda: "MMS",
        export_command_hint=lambda cli: f"mmg --export {cli} --apply",
        console=console,
    )

    assert any("不支持的 CLI: unknown" in str(item) for item in console.items)
    assert any("claude, codex" in str(item) for item in console.items)


def test_config_help_display_helpers_render_expected_sections(tmp_path):
    import mms_command_tools

    active_path = tmp_path / "preferences.toml"
    active_path.write_text("# prefs\n", encoding="utf-8")
    missing_path = tmp_path / "missing.toml"
    console = _CollectingConsole()

    mms_command_tools.display_config_help(command_name="mmg", console=console)
    mms_command_tools.display_preferences_path(
        preference_paths=[str(active_path), str(missing_path)],
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_preferences_help(
        command_name="mmg",
        preference_paths=[str(active_path)],
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_human_gate_help(
        command_name="mmg",
        preferences_doc_path="/docs/prefs.md",
        console=console,
    )
    mms_command_tools.display_preferences_example(
        preferences_example_toml="[launch.defaults]\nreasoning_effort = \"high\"\n",
        console=console,
    )

    text = "\n".join(str(item) for item in console.items)
    assert "mmg config provider.list" in text
    assert "active" in text
    assert "create-if-needed" in text
    assert "preferences.toml" in text
    assert "human-only" in text
    assert "[launch.defaults]" in text


def test_usage_stats_display_sorts_recent_sources():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.display_usage_stats(
        load_usage_stats=lambda: {
            "sources": {
                "old": {
                    "runtime_kind": "provider",
                    "name": "Old",
                    "cli": "claude",
                    "launches": 2,
                    "last_model": "sonnet",
                    "last_used_at": "2026-01-01T00:00:00Z",
                },
                "new": {
                    "runtime_kind": "account",
                    "name": "New",
                    "cli": "codex",
                    "launches": 1,
                    "last_model": "gpt-5.5",
                    "last_used_at": "2026-05-01T00:00:00Z",
                },
            }
        },
        usage_path="/tmp/usage.json",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0][0] == "account / New"
    assert table.rows[1][0][0] == "provider / Old"


def test_adapter_registry_display_renders_policy():
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.display_adapter_registry(
        top_source_companies=[
            {
                "company": "Example",
                "brand": "Relay",
                "families": ["GPT"],
                "default_adapter": "openai",
                "current_support": "supported",
                "oauth_native": False,
                "claude_bridge_default": True,
            }
        ],
        default_adapter_policy={"gpt": "use openai"},
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("1", "Example / Relay", "GPT", "openai", "supported", "no", "yes")
    assert any("gpt" in str(item) and "use openai" in str(item) for item in console.items)
    assert any("mmg config adapter.registry" in str(item) for item in console.items)


def test_provider_account_display_helpers_render_rows():
    import mms_command_tools

    console = _CollectingConsole()
    cfg = {
        "provider": {"default": "relay"},
        "providers": [
            {
                "id": "relay",
                "name": "Relay",
                "protocols": ["openai"],
                "supported_clis": ["codex"],
                "enabled": True,
                "openai_base_url": "https://relay.example/v1",
            },
            {
                "id": "backup",
                "name": "Backup",
                "protocols": ["anthropic"],
                "supported_clis": ["claude"],
                "enabled": False,
                "anthropic_base_url": "https://anthropic.example/v1",
            },
        ],
    }

    mms_command_tools.display_providers(
        cfg,
        default_provider_id="default",
        default_priority=100,
        resolve_provider_context=lambda cfg_arg, provider_id: next(
            provider for provider in cfg_arg["providers"] if provider["id"] == provider_id
        ),
        provider_openai_base_url=lambda provider: provider.get("openai_base_url", ""),
        provider_anthropic_base_url=lambda provider: provider.get("anthropic_base_url", ""),
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    provider_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert provider_table.rows[0][0] == (
        "relay",
        "Relay",
        "openai",
        "codex",
        "100",
        "默认 启用",
        "https://relay.example/v1",
    )
    assert provider_table.rows[1][0][5] == "禁用"

    console.items.clear()
    mms_command_tools.display_accounts(
        {
            "account": {"defaults": {"codex": "codex-a"}},
            "accounts": [
                {
                    "id": "codex-a",
                    "name": "Codex A",
                    "cli": "codex",
                    "priority": 200,
                    "enabled": True,
                    "home_dir": "/tmp/codex-a",
                }
            ],
        },
        default_priority=100,
        probe_account_status=lambda account: {"summary": "logged-in"},
        command_name="mmg",
        table_cls=_FakeTable,
        console=console,
    )

    account_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert account_table.rows[0][0] == (
        "codex-a",
        "Codex A",
        "codex",
        "200",
        "默认 启用",
        "logged-in",
        "/tmp/codex-a",
    )


def test_runtime_usage_display_handles_tui_empty_and_rows():
    import mms_command_tools

    events = []
    console = _CollectingConsole()

    mms_command_tools.display_runtime_usage(
        "provider",
        "relay",
        "Relay",
        use_tui=lambda: True,
        clear_console=lambda: events.append("clear"),
        usage_rows_for_runtime=lambda kind, runtime_id: [],
        active_usage_path=lambda: "/tmp/usage.json",
        pause_after_tui_report=lambda message: events.append(("pause", message)),
        table_cls=_FakeTable,
        console=console,
    )

    assert events == ["clear", ("pause", "按 Enter 返回通道详情")]
    assert any("Relay 还没有本地启动统计" in str(item) for item in console.items)

    events.clear()
    console.items.clear()
    mms_command_tools.display_runtime_usage(
        "account",
        "codex-a",
        "Codex A",
        use_tui=lambda: False,
        clear_console=lambda: events.append("clear"),
        usage_rows_for_runtime=lambda kind, runtime_id: [
            {"cli": "codex", "launches": 3, "last_model": "gpt-5.5", "last_used_at": "2026-05-28"}
        ],
        active_usage_path=lambda: "/tmp/usage.json",
        pause_after_tui_report=lambda message: events.append(("pause", message)),
        table_cls=_FakeTable,
        console=console,
    )

    assert events == []
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("codex", "3", "gpt-5.5", "2026-05-28")


def test_config_display_renders_summary_and_masks_keys():
    import mms_command_tools

    console = _CollectingConsole()
    provider_calls = []
    account_calls = []
    cfg = {
        "provider": {"default": "relay"},
        "providers": [{"id": "relay"}],
        "account": {},
        "accounts": [],
        "cache": {"probe_async_refresh_after_sec": 10, "probe_async_min_interval_sec": 5},
        "nested": {"api_key": "abcd1234efgh", "plain": "value"},
    }

    mms_command_tools.display_config(
        cfg,
        resolve_provider_context=lambda cfg_arg: {"api_key": "sk-1234567890", "openai_base_url": "https://relay.example/v1"},
        provider_openai_base_url=lambda provider: provider.get("openai_base_url", ""),
        provider_anthropic_base_url=lambda provider: provider.get("anthropic_base_url", ""),
        mask_key=lambda value: "MASKED",
        active_credentials_path=lambda: "/tmp/credentials.sh",
        active_usage_path=lambda: "/tmp/usage.json",
        display_providers=lambda cfg_arg: provider_calls.append(cfg_arg),
        display_accounts=lambda cfg_arg: account_calls.append(cfg_arg),
        probe_async_refresh_after=1800,
        probe_async_min_interval=300,
        existing_override_paths=lambda: [],
        override_paths=["/tmp/override.toml"],
        existing_preferences_paths=lambda: ["/tmp/preferences.toml"],
        preference_paths=["/tmp/default-preferences.toml"],
        command_name="mmg",
        console=console,
    )

    text = "\n".join(str(item) for item in console.items)
    assert provider_calls == [cfg]
    assert account_calls == [cfg]
    assert "openai_base_url" in text
    assert "/tmp/credentials.sh" in text
    assert "probe_async_refresh_after_sec" in text
    assert "mmg config preferences.help" in text
    assert "MASKED" in text
    assert "plain" in text


def test_config_nested_helpers_and_coercion():
    import pytest
    import mms_command_tools
    import mms_core

    data = {}
    assert mms_command_tools.mask_key("abcd1234efgh") == "abcd****efgh"
    assert mms_command_tools.mask_key("short") == "****"

    mms_command_tools.set_nested(data, ["a", "b", "c"], "value")
    assert data == {"a": {"b": {"c": "value"}}}
    assert mms_command_tools.get_nested(data, ["a", "b", "c"]) == ("value", True)
    assert mms_command_tools.get_nested(data, ["a", "missing"]) == (None, False)
    assert mms_command_tools.unset_nested(data, ["a", "b", "c"]) is True
    assert mms_command_tools.unset_nested(data, ["a", "b", "c"]) is False

    coerce = lambda key, value: mms_command_tools.coerce_config_value(
        key,
        value,
        validate_user_role=lambda raw: f"role:{raw}",
        normalize_language=lambda raw: {"zh": "zh", "en": "en"}.get(str(raw).strip()),
        normalize_positive_seconds=lambda raw, minimum: max(int(raw), minimum),
    )
    assert coerce("user.role", "dev") == "role:dev"
    assert coerce("ui.language", "zh") == "zh"
    assert coerce("provider.default", " relay ") == "relay"
    assert coerce("cache.probe_async_min_interval_sec", "0") == 1
    assert coerce("provider.relay.enabled", "yes") is True
    with pytest.raises(ValueError):
        coerce("ui.language", "fr")

    wrapped = {}
    mms_core._set_nested(wrapped, ["x", "y"], "z")
    assert mms_core._get_nested(wrapped, ["x", "y"]) == ("z", True)
    assert mms_core._unset_nested(wrapped, ["x", "y"]) is True
    assert mms_core._mask_key("abcd1234efgh") == "abcd****efgh"


def test_config_validator_reports_provider_account_errors():
    import mms_command_tools
    import mms_core

    kwargs = {
        "default_provider_protocols": {"openai", "anthropic"},
        "cli_names": ["claude", "codex"],
        "legacy_provider_cli_aliases": {"legacy"},
        "default_priority": 100,
        "oauth_capable_clis": {"codex", "agy"},
        "mode_all": "all",
        "mode_recommended": "recommended",
        "canonical_model_family": lambda name: {"GPT": "GPT"}.get(name),
        "normalize_priority": lambda value: value if isinstance(value, int) and value > 0 else 100,
        "normalize_claude_1m_mode": lambda value: value if value in {"auto", "enable", "disable"} else "auto",
        "normalize_user_role": lambda value: value if value in {"all", "recommended"} else "all",
    }
    cfg = {
        "cache": {"probe_async_refresh_after_sec": 0},
        "provider": {"default": "missing"},
        "providers": [
            {
                "id": "relay",
                "protocols": ["bad"],
                "supported_clis": ["badcli"],
                "priority": -1,
                "family_priority_overrides": {"Bad": 1},
                "claude_1m_mode": "bad",
            },
            {"id": "relay"},
        ],
        "accounts": [
            {
                "id": "acct",
                "cli": "claude",
                "auth_mode": "api_key",
                "priority": 0,
                "claude_1m_mode": "bad",
            },
            {"id": "acct", "cli": "codex", "home_dir": "/tmp/a"},
        ],
        "account": {"defaults": {"badcli": "acct", "codex": "missing"}},
    }

    errors = mms_command_tools.validate_config(cfg, **kwargs)
    assert "probe_async_refresh_after_sec 必须是正整数" in errors
    assert "模型源 ID 重复: relay" in errors
    assert "模型源 relay 存在不支持的协议: bad" in errors
    assert "模型源 relay 存在不支持的 CLI: badcli" in errors
    assert "默认模型源不存在: missing" in errors
    assert "账号档案 acct 绑定了不支持的 CLI: claude" in errors
    assert "账号档案 acct 目前只支持 oauth 模式" in errors
    assert "账号档案 acct 缺少 home_dir" in errors
    assert "存在不支持的默认账号 CLI: badcli" in errors
    assert "codex 的默认账号不存在: missing" in errors

    valid_cfg = {
        "provider": {"default": "relay"},
        "providers": [{"id": "relay", "protocols": ["openai"], "supported_clis": ["codex"], "priority": 100}],
        "accounts": [{"id": "codex-a", "cli": "codex", "auth_mode": "oauth", "home_dir": "/tmp/codex-a"}],
        "account": {"defaults": {"codex": "codex-a"}},
        "user": {"role": "all"},
    }
    assert mms_command_tools.validate_config(valid_cfg, **kwargs) == []
    assert mms_core._validate_config({"provider": {"default": "relay"}, "providers": [{"id": "relay"}]}) == []


def test_config_get_set_unset_handlers_use_injected_save():
    import mms_command_tools

    console = _CollectingConsole()
    saved = []
    cfg = {"provider": {"default": "relay"}, "secret": {"api_key": "abcd1234efgh"}}

    mms_command_tools.handle_config_get(cfg, ["secret.api_key"], command_name="mmg", console=console)
    assert any("abcd****efgh" in str(item) for item in console.items)

    mms_command_tools.handle_config_set(
        cfg,
        ["cache.probe_async_min_interval_sec", "0"],
        command_name="mmg",
        coerce_config_value=lambda key, value: 1 if key == "cache.probe_async_min_interval_sec" else value,
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("set", current)),
        console=console,
    )
    assert saved[-1][0] == "set"
    assert saved[-1][1]["cache"]["probe_async_min_interval_sec"] == 1
    assert any("cache.probe_async_min_interval_sec = 1" in str(item) for item in console.items)

    mms_command_tools.handle_config_unset(
        saved[-1][1],
        ["cache.probe_async_min_interval_sec"],
        command_name="mmg",
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("unset", current)),
        console=console,
    )
    assert saved[-1][0] == "unset"
    assert "probe_async_min_interval_sec" not in saved[-1][1]["cache"]
    assert any("已移除 cache.probe_async_min_interval_sec" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_config_unset(
        cfg,
        ["missing.path"],
        command_name="mmg",
        normalize_config_sections=lambda current: current,
        save_config=lambda current: saved.append(("unexpected", current)),
        console=console,
    )
    assert saved[-1][0] == "unset"
    assert any("配置项 'missing.path' 不存在" in str(item) for item in console.items)


def test_config_validate_handler_prints_success_and_failure():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()

    mms_command_tools.handle_config_validate({}, validate_config=lambda cfg: [], console=console)
    assert any("配置校验通过" in str(item) for item in console.items)

    console.items.clear()
    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_config_validate({}, validate_config=lambda cfg: ["bad provider"], console=console)
    assert exc.value.code == 1
    assert any("配置校验失败" in str(item) for item in console.items)
    assert any("bad provider" in str(item) for item in console.items)


def test_session_list_info_display_helpers():
    import pytest
    import mms_command_tools

    console = _CollectingConsole()
    rows = [
        {
            "session_id": "session-1",
            "project_path": "/tmp/demo",
            "account_id": "claude-a",
            "last_active_at": "2026-05-28",
        },
        {
            "pid": 123,
            "project_path": "",
            "runtime_kind": "provider",
            "started_at": "2026-05-27",
            "exit_code": 7,
        },
    ]

    mms_command_tools.handle_session_ls(
        "claude",
        list_indexed_sessions=lambda cli_name: rows,
        table_cls=_FakeTable,
        console=console,
    )
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("session-1", "demo", "claude-a", "active", "2026-05-28")
    assert table.rows[1][0] == ("pid-123", "-", "provider", "active", "2026-05-27")

    console.items.clear()
    mms_command_tools.handle_session_info(
        "session-1",
        "claude",
        get_indexed_session=lambda session_id, cli_name: {"session_id": session_id, "extra": "value"},
        table_cls=_FakeTable,
        console=console,
    )
    info_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert ("session_id", "session-1") in [row for row, _kwargs in info_table.rows]
    assert ("extra", "value") in [row for row, _kwargs in info_table.rows]

    console.items.clear()
    with pytest.raises(SystemExit) as exc:
        mms_command_tools.handle_session_info(
            "missing",
            "claude",
            get_indexed_session=lambda session_id, cli_name: None,
            table_cls=_FakeTable,
            console=console,
        )
    assert exc.value.code == 1
    assert any("找不到 session: missing" in str(item) for item in console.items)


def test_session_prune_handler_dry_run_and_apply_with_injected_remove():
    import mms_command_tools

    rows = [
        {"cli": "claude", "name": "123", "size": 1024, "mtime": "2026-05-28", "path": "/tmp/mms/claude-gateway/s/123"},
        {"cli": "codex", "name": "456", "size": 2048, "mtime": "2026-05-27", "path": "/tmp/mms/codex-gateway/s/456"},
    ]
    console = _CollectingConsole()
    finalized = []
    removed = []

    mms_command_tools.handle_session_prune(
        "all",
        apply=False,
        yes=False,
        list_stale_gateway_sessions=lambda cli_name: rows,
        finalize_claude_slot=lambda *args, **kwargs: finalized.append((args, kwargs)),
        remove_tree=lambda *args, **kwargs: removed.append((args, kwargs)),
        format_bytes=lambda size: f"{size}B",
        table_cls=_FakeTable,
        console=console,
    )
    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == ("claude", "123", "1024B", "2026-05-28", "/tmp/mms/claude-gateway/s/123")
    assert removed == []
    assert any("dry-run only" in str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.handle_session_prune(
        "all",
        apply=True,
        yes=True,
        list_stale_gateway_sessions=lambda cli_name: rows,
        finalize_claude_slot=lambda *args, **kwargs: finalized.append((args, kwargs)),
        remove_tree=lambda *args, **kwargs: removed.append((args, kwargs)),
        format_bytes=lambda size: f"{size}B",
        table_cls=_FakeTable,
        console=console,
    )
    assert finalized == [(("/tmp/mms/claude-gateway/s/123",), {"stale_cleanup": True})]
    assert removed == [
        (("/tmp/mms/claude-gateway/s/123",), {"ignore_errors": True}),
        (("/tmp/mms/codex-gateway/s/456",), {"ignore_errors": True}),
    ]
    assert any("已删除 2 个 stale MMS session" in str(item) for item in console.items)


def test_provider_model_table_display_renders_speed_and_sources():
    import mms_command_tools

    console = _CollectingConsole()
    provider = {"id": "relay", "name": "Relay"}
    probe = {
        "models": ["gpt-5.5", "custom-model"],
        "raw_models": ["gpt-5.5", "custom-model", "hidden-model"],
        "extra_models": ["custom-model"],
        "hidden_models": ["hidden-model"],
        "model_sources": {"custom-model": "manual"},
        "base_source": "remote",
    }

    mms_command_tools.display_provider_model_table(
        provider,
        probe,
        get_speed_entry=lambda model_id, provider=None: {
            "ttfb_avg_ms": 123.4,
            "tps_avg": 45.67,
            "samples": 2,
            "last_updated": "2026-05-28",
            "warming_up": model_id == "custom-model",
            "is_stale": model_id == "custom-model",
        },
        infer_model_family=lambda model_id: ("GPT", None),
        model_capability_summary=lambda model_id: "tools",
        model_cli_summary=lambda model_id: "codex",
        model_source_label=lambda source: f"src:{source}",
        ttfb_label=lambda value: "fast",
        tps_label=lambda value: "quick",
        table_cls=_FakeTable,
        console=console,
    )

    table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert table.rows[0][0] == (
        "gpt-5.5",
        "GPT",
        "tools",
        "codex",
        "src:remote",
        "123ms / fast",
        "45.7 / quick",
        "2",
        "2026-05-28",
    )
    assert table.rows[1][0][4] == "src:manual"
    assert table.rows[1][0][7] == "2（预热中）"
    assert table.rows[1][0][8] == "2026-05-28 (stale)"
    text = "\n".join(str(item) for item in console.items)
    assert "手工补充模型: custom-model" in text
    assert "已隐藏模型: hidden-model" in text
    assert "原始模型数: 3" in text


def test_openrouter_extension_display_helpers_render_summary_and_limits():
    import mms_command_tools

    console = _CollectingConsole()
    rows = [
        {
            "id": "free/model",
            "origin": "openrouter",
            "is_free": True,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "context_length": 128000,
        },
        {
            "id": "paid/model",
            "origin": "openrouter",
            "is_free": False,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "context_length": 200000,
        },
    ]

    mms_command_tools.display_openrouter_extension_help("mmg", console=console)
    assert "mmg config extension.openrouter add" in "\n".join(str(item) for item in console.items)

    console.items.clear()
    mms_command_tools.display_openrouter_model_rows(
        "OpenRouter Text 模型",
        rows,
        limit=1,
        table_cls=_FakeTable,
        console=console,
    )
    text_table = next(item for item in console.items if isinstance(item, _FakeTable))
    assert text_table.kwargs["title"] == "OpenRouter Text 模型"
    assert text_table.rows[0][0] == ("free/model", "openrouter", "yes", "text", "text", "128000")
    assert any("仅展示前 1 / 2 个" in str(item) for item in console.items)

    console.items.clear()
    summary = {
        "account": {"tier": "paid", "reason": "key"},
        "counts": {"visible_text": 2},
        "requests": {"models": {"status": "ok"}},
        "model_source": "api",
        "image_enabled": True,
        "video_enabled": True,
        "free_only": True,
        "text_models": rows,
        "image_models": [{"id": "img/model", "origin": "openrouter", "is_free": False}],
        "video_models": [
            {
                "id": "video/model",
                "origin": "openrouter",
                "supported_resolutions": ["720p"],
                "supported_durations": [5, 10],
            }
        ],
    }
    mms_command_tools.display_openrouter_extension_summary(
        summary,
        provider_label="provider/openrouter",
        limit=1,
        show_models=True,
        table_cls=_FakeTable,
        console=console,
    )
    tables = [item for item in console.items if isinstance(item, _FakeTable)]
    assert tables[0].rows[0][0] == ("provider/key", "provider/openrouter")
    assert tables[0].rows[4][0] == ("image/video", "on / on")
    assert tables[0].rows[5][0] == ("requests", "models:ok")
    assert tables[-1].rows[0][0] == ("video/model", "openrouter", "720p", "5,10")
    assert any("free-only" in str(item) for item in console.items)


def test_choose_runtime_source_initializes_rich_before_interactive_source_table(monkeypatch):
    import mms_core

    class _TTY:
        def isatty(self):
            return True

    class _FakePrompt:
        @staticmethod
        def ask(*args, **kwargs):
            return "1"

    def _fake_ensure_rich():
        mms_core.Table = _FakeTable
        mms_core.Prompt = _FakePrompt

    options = [
        {
            "runtime": {"id": "provider-a", "name": "Provider A", "auth_mode": "api_key"},
            "models": ["gpt-5.4"],
            "launch_cli": "codex",
            "desc": "provider",
        },
        {
            "runtime": {"id": "account-a", "name": "Account A", "auth_mode": "oauth"},
            "models": ["gpt-5.4"],
            "launch_cli": "codex",
            "desc": "account",
        },
    ]

    monkeypatch.setattr(mms_core, "Table", None)
    monkeypatch.setattr(mms_core, "Prompt", None)
    monkeypatch.setattr(mms_core, "_ensure_rich", _fake_ensure_rich)
    monkeypatch.setattr(mms_core, "console", _FakeConsole())
    monkeypatch.setattr(mms_core.sys, "stdin", _TTY())
    monkeypatch.setattr(mms_core, "_list_runtime_sources", lambda *args, **kwargs: (options, 0))

    runtime, models, cli = mms_core._choose_runtime_source(
        {},
        "codex",
        {},
        ["gpt-5.4"],
    )

    assert mms_core.Table is _FakeTable
    assert runtime["id"] == "provider-a"
    assert models == ["gpt-5.4"]
    assert cli == "codex"
