from __future__ import annotations

import json


def test_session_catalog_scans_claude_index_and_raw_jsonl(monkeypatch, tmp_path):
    import mms_session_catalog

    projects_root = tmp_path / "projects"
    project_store = projects_root / "proj1"
    state_sessions = project_store / "claude" / "state" / "sessions"
    raw_projects = project_store / "claude" / "raw" / "projects" / "-tmp-repo"
    state_sessions.mkdir(parents=True)
    raw_projects.mkdir(parents=True)
    (project_store / "claude" / "state" / "metadata.json").write_text(
        json.dumps(
            {
                "canonical_path": str(tmp_path / "repo"),
                "account_id": "provider-a",
                "display_name": "repo",
            }
        ),
        encoding="utf-8",
    )
    (state_sessions / "indexed.json").write_text(
        json.dumps(
            {
                "cli": "claude",
                "session_id": "11111111-1111-4111-8111-111111111111",
                "project_path": str(tmp_path / "repo"),
                "account_id": "provider-a",
                "runtime_kind": "api_key",
                "resume_model": "mimo-v2.5",
                "started_at": "2026-06-04T01:00:00+00:00",
                "last_active_at": "2026-06-04T02:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (raw_projects / "22222222-2222-4222-8222-222222222222.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"type": "last-prompt", "sessionId": "22222222-2222-4222-8222-222222222222"}),
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-06-04T03:00:00.000Z",
                        "cwd": str(tmp_path / "repo"),
                        "sessionId": "22222222-2222-4222-8222-222222222222",
                        "message": {"content": [{"type": "text", "text": "继续做 session center"}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-06-04T03:01:00.000Z",
                        "cwd": str(tmp_path / "repo"),
                        "sessionId": "22222222-2222-4222-8222-222222222222",
                        "message": {
                            "model": "qwen3.7-max",
                            "content": [{"type": "text", "text": "好的"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    subagent_dir = raw_projects / "22222222-2222-4222-8222-222222222222" / "subagents"
    subagent_dir.mkdir(parents=True)
    (subagent_dir / "agent-a.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [projects_root])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [])

    rows = mms_session_catalog.list_session_records(cli="claude")

    assert [row["session_id"] for row in rows] == [
        "22222222-2222-4222-8222-222222222222",
        "11111111-1111-4111-8111-111111111111",
    ]
    assert rows[0]["title"] == "继续做 session center"
    assert rows[0]["account_id"] == "provider-a"
    assert rows[0]["model"] == "qwen3.7-max"
    assert rows[0]["model_source"] == "Claude 原始记录"
    assert rows[1]["model"] == "mimo-v2.5"
    assert rows[1]["model_source"] == "MMS 启动记录"
    assert all(not row["session_id"].startswith("agent-") for row in rows)


def test_session_catalog_previews_claude_recent_and_search(monkeypatch, tmp_path):
    import mms_session_catalog

    projects_root = tmp_path / "projects"
    project_store = projects_root / "proj1"
    raw_projects = project_store / "claude" / "raw" / "projects" / "-tmp-repo"
    raw_projects.mkdir(parents=True)
    (project_store / "claude" / "state").mkdir(parents=True)
    (project_store / "claude" / "state" / "metadata.json").write_text(
        json.dumps({"canonical_path": str(tmp_path / "repo")}),
        encoding="utf-8",
    )
    session_path = raw_projects / "33333333-3333-4333-8333-333333333333.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-06-04T01:00:00Z",
                        "sessionId": "33333333-3333-4333-8333-333333333333",
                        "message": {"content": [{"type": "text", "text": "第一条需求"}]},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "timestamp": "2026-06-04T01:01:00Z",
                        "message": {"content": [{"type": "text", "text": "第二条回复"}]},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [projects_root])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [])
    record = mms_session_catalog.list_session_records(cli="claude")[0]

    recent = mms_session_catalog.preview_session_record(record["session_id"], cli="claude", record=record, limit=1)
    matched = mms_session_catalog.preview_session_record(record["session_id"], cli="claude", record=record, query="第一条")

    assert recent["ok"] is True
    assert recent["read_only"] is True
    assert [item["text"] for item in recent["items"]] == ["第二条回复"]
    assert matched["mode"] == "search"
    assert matched["items"][0]["role"] == "用户"
    assert matched["items"][0]["text"] == "第一条需求"


def test_session_catalog_preview_defaults_to_latest_20_newest_first(tmp_path):
    import mms_session_catalog

    session_path = tmp_path / "latest.jsonl"
    session_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": f"2026-06-04T01:{index:02d}:00Z",
                    "message": {"content": [{"type": "text", "text": f"消息 {index}"}]},
                }
            )
            for index in range(25)
        )
        + "\n",
        encoding="utf-8",
    )
    record = {"cli": "claude", "session_id": "latest", "source_path": str(session_path)}

    preview = mms_session_catalog.preview_session_record("latest", cli="claude", record=record)

    assert preview["order"] == "newest_first"
    assert len(preview["items"]) == 20
    assert preview["items"][0]["text"] == "消息 24"
    assert preview["items"][-1]["text"] == "消息 5"


def test_session_catalog_scans_codex_index_and_jsonl(monkeypatch, tmp_path):
    import mms_session_catalog

    codex_root = tmp_path / "codex"
    session_dir = codex_root / "sessions" / "2026" / "06" / "04"
    session_dir.mkdir(parents=True)
    (codex_root / "session_index.jsonl").write_text(
        json.dumps({"id": "019e9000-0000-7000-8000-000000000000", "updated_at": "2026-06-04T01:00:00Z"})
        + "\n",
        encoding="utf-8",
    )
    (session_dir / "rollout-019e9001-0000-7000-8000-000000000000.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "019e9001-0000-7000-8000-000000000000",
                            "cwd": str(tmp_path / "codex-project"),
                            "model_provider": "custom",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:00:30Z",
                        "type": "turn_context",
                        "payload": {"model": "gpt-5.5"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "恢复 Codex 会话"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [codex_root])

    rows = mms_session_catalog.list_session_records(cli="codex")

    assert [row["session_id"] for row in rows] == [
        "019e9001-0000-7000-8000-000000000000",
        "019e9000-0000-7000-8000-000000000000",
    ]
    assert rows[0]["project_name"] == "codex-project"
    assert rows[0]["title"] == "恢复 Codex 会话"
    assert rows[0]["model"] == "gpt-5.5"
    assert rows[0]["model_source"] == "Codex 原始记录"


def test_session_catalog_previews_codex_messages(monkeypatch, tmp_path):
    import mms_session_catalog

    codex_root = tmp_path / "codex"
    session_dir = codex_root / "sessions" / "2026" / "06" / "04"
    session_dir.mkdir(parents=True)
    session_path = session_dir / "rollout-019e9002-0000-7000-8000-000000000000.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "019e9002-0000-7000-8000-000000000000",
                            "cwd": str(tmp_path / "codex-project"),
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "帮我找历史会话"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-04T02:02:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "可以，先扫描 catalog"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [codex_root])
    record = mms_session_catalog.list_session_records(cli="codex")[0]

    preview = mms_session_catalog.preview_session_record(record["session_id"], cli="codex", record=record)

    assert preview["order"] == "newest_first"
    assert [item["role"] for item in preview["items"]] == ["助手", "用户"]
    assert preview["items"][0]["text"] == "可以，先扫描 catalog"


def test_session_catalog_resolves_prefix(monkeypatch, tmp_path):
    import mms_session_catalog

    codex_root = tmp_path / "codex"
    codex_root.mkdir()
    (codex_root / "session_index.jsonl").write_text(
        json.dumps({"id": "019e9000-aaaa-7000-8000-000000000000", "updated_at": "2026-06-04T01:00:00Z"})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [codex_root])

    session_id, record, error = mms_session_catalog.resolve_catalog_ref("019e9000-aa", cli="codex")

    assert error is None
    assert session_id == "019e9000-aaaa-7000-8000-000000000000"
    assert record["cli"] == "codex"


def test_session_catalog_scans_current_and_legacy_pi_sessions(monkeypatch, tmp_path):
    import mms_session_catalog

    pi_root = tmp_path / "pi-gateway"
    current_path = pi_root / "sessions" / "current.jsonl"
    legacy_path = pi_root / "s" / "1234" / ".pi" / "agent" / "sessions" / "legacy.jsonl"
    current_path.parent.mkdir(parents=True)
    legacy_path.parent.mkdir(parents=True)
    session_id = "019fa700-aaaa-7000-8000-000000000001"
    current_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session",
                        "version": 3,
                        "id": session_id,
                        "timestamp": "2026-07-27T01:00:00Z",
                        "cwd": str(tmp_path / "project"),
                    }
                ),
                json.dumps(
                    {
                        "type": "model_change",
                        "timestamp": "2026-07-27T01:01:00Z",
                        "provider": "mms-relay-a",
                        "modelId": "qwen3.6-plus",
                    }
                ),
                json.dumps(
                    {
                        "type": "message",
                        "timestamp": "2026-07-27T01:02:00Z",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "恢复 Pi 会话"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    legacy_path.write_text(
        json.dumps(
            {
                "type": "session",
                "version": 3,
                "id": "019fa700-bbbb-7000-8000-000000000002",
                "timestamp": "2026-07-26T01:00:00Z",
                "cwd": str(tmp_path / "legacy-project"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mms_session_catalog, "claude_project_roots", lambda: [])
    monkeypatch.setattr(mms_session_catalog, "codex_roots", lambda: [])
    monkeypatch.setattr(mms_session_catalog, "pi_roots", lambda: [pi_root])

    rows = mms_session_catalog.list_session_records(cli="pi")

    assert {row["session_id"] for row in rows} == {
        session_id,
        "019fa700-bbbb-7000-8000-000000000002",
    }
    current = next(row for row in rows if row["session_id"] == session_id)
    assert current["model"] == "qwen3.6-plus"
    assert current["provider_id"] == "mms-relay-a"
    assert current["title"] == "恢复 Pi 会话"
    preview = mms_session_catalog.preview_session_record(
        session_id,
        cli="pi",
        record=current,
    )
    assert preview["items"][0]["text"] == "恢复 Pi 会话"
