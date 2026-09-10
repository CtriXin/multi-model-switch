import json
from pathlib import Path

import pytest

from mms_web.cli_sessions import index, summarize, transcript


def write(root: Path, name: str, events: list[dict]) -> Path:
    path = root / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
                    encoding="utf-8")
    return path


def message(role: str, text: str, ident: str = "m1") -> dict:
    return {"type": "message", "id": ident, "timestamp": "2026-09-10T02:00:00.000Z",
            "message": {"role": role, "content": [{"type": "text", "text": text}]}}


def session(ident: str, cwd: str = "/tmp/project") -> dict:
    return {"type": "session", "version": 3, "id": ident,
            "timestamp": "2026-09-10T01:00:00.000Z", "cwd": cwd}


def test_summary_takes_its_title_from_the_first_user_turn(tmp_path):
    path = write(tmp_path, "a", [
        session("01a0-aaaa"),
        {"type": "model_change", "provider": "newapi", "model": "glm-5.3"},
        message("assistant", "先说一句", "m0"),
        message("user", "帮我看一下这个布局", "m1"),
        message("user", "第二句不应该成为标题", "m2"),
    ])
    row = summarize(path)
    assert row["piSessionId"] == "01a0-aaaa"
    assert row["title"] == "帮我看一下这个布局"
    assert row["modelName"] == "glm-5.3"
    assert row["providerName"] == "newapi"
    assert row["cwd"] == "/tmp/project"
    # These are not this page's sessions until one is resumed.
    assert row["owner"] == "cli"
    assert row["id"] == "cli:01a0-aaaa"


def test_long_title_is_truncated_with_an_ellipsis(tmp_path):
    path = write(tmp_path, "a", [session("id-1"), message("user", "长" * 80)])
    assert summarize(path)["title"] == "长" * 42 + "…"


def test_a_transcript_still_being_written_does_not_break_the_index(tmp_path):
    """Pi appends while we read, so the last line can be half a JSON object."""
    path = tmp_path / "partial.jsonl"
    path.write_text(json.dumps(session("id-2")) + "\n"
                    + json.dumps(message("user", "已经写完的一行")) + "\n"
                    + '{"type": "message", "id": "m9", "mess',
                    encoding="utf-8")
    row = summarize(path)
    assert row["piSessionId"] == "id-2"
    assert row["title"] == "已经写完的一行"


@pytest.mark.parametrize("events", [
    [message("user", "没有会话头")],
    [{"type": "session", "version": 3}],
    [],
])
def test_a_file_without_a_session_id_is_skipped(tmp_path, events):
    path = write(tmp_path, "broken", events) if events else (tmp_path / "empty.jsonl")
    if not events:
        path.write_text("", encoding="utf-8")
    assert summarize(path) is None
    assert index(tmp_path) == []


def test_index_is_newest_first_and_bounded(tmp_path):
    import os
    for n in range(4):
        path = write(tmp_path, f"s{n}", [session(f"id-{n}"), message("user", f"第 {n} 个")])
        os.utime(path, (1_700_000_000 + n, 1_700_000_000 + n))
    rows = index(tmp_path)
    assert [r["piSessionId"] for r in rows] == ["id-3", "id-2", "id-1", "id-0"]
    assert [r["piSessionId"] for r in index(tmp_path, limit=2)] == ["id-3", "id-2"]
    assert index(tmp_path / "missing") == []


def tool_call(name: str, call_id: str, arguments: dict, ident: str = "t1") -> dict:
    """One assistant turn whose content is a single tool call."""
    return {"type": "message", "id": ident, "timestamp": "2026-09-10T02:00:01.000Z",
            "message": {"role": "assistant", "content": [
                {"type": "toolCall", "id": call_id, "name": name, "arguments": arguments}]}}


def tool_result(call_id: str, text: str, ident: str = "r1", error: bool = False) -> dict:
    return {"type": "message", "id": ident, "timestamp": "2026-09-10T02:00:02.000Z",
            "message": {"role": "toolResult", "toolCallId": call_id, "toolName": "read",
                        "isError": error, "content": [{"type": "text", "text": text}]}}


def test_transcript_uses_the_kinds_the_page_already_renders(tmp_path):
    """A tool must arrive as one collapsible event, not as a wall of text."""
    path = write(tmp_path, "a", [
        session("id-3"),
        {"type": "thinking_level_change", "level": "high"},
        message("user", "问题", "m1"),
        message("assistant", "回答", "m2"),
        tool_call("read", "call-1", {"path": "/tmp/a.txt"}),
        tool_result("call-1", "文件内容"),
    ])
    rows = transcript(path)
    assert [r["kind"] for r in rows] == ["user", "assistant", "tool"]
    assert rows[0]["text"] == "问题"
    assert [r["sequence"] for r in rows] == [1, 2, 3]
    tool = rows[2]
    # The result is folded back into the call it belongs to.
    assert tool["title"] == "read"
    assert tool["arguments"] == {"path": "/tmp/a.txt"}
    assert tool["text"] == "文件内容"
    assert tool["status"] == "done"
    assert transcript(tmp_path / "missing.jsonl") == []


def test_a_tool_that_never_returned_is_not_reported_as_finished(tmp_path):
    """A session killed mid-tool has no result; saying "done" would be a lie."""
    path = write(tmp_path, "a", [
        session("id-4"),
        tool_call("bash", "call-2", {"command": "sleep 900"}),
    ])
    assert transcript(path)[0]["status"] == "running"


def test_a_failed_tool_keeps_its_error_status(tmp_path):
    path = write(tmp_path, "a", [
        session("id-5"),
        tool_call("read", "call-3", {"path": "/nope"}),
        tool_result("call-3", "ENOENT", error=True),
    ])
    assert transcript(path)[0]["status"] == "error"


def test_assistant_thinking_is_kept_beside_its_answer(tmp_path):
    path = write(tmp_path, "a", [
        session("id-6"),
        {"type": "message", "id": "m5", "timestamp": "2026-09-10T02:00:00.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "先想一下"},
             {"type": "text", "text": "结论"}]}},
    ])
    row = transcript(path)[0]
    assert row["text"] == "结论" and row["thinking"] == "先想一下"


def test_transcript_keeps_the_tail(tmp_path):
    path = write(tmp_path, "a", [session("id-7"),
                                 message("user", "第一句", "m1"),
                                 message("assistant", "第二句", "m2"),
                                 message("user", "第三句", "m3")])
    # A long session is read from the end, which is what someone wants to see.
    assert [r["id"] for r in transcript(path, limit=2)] == ["m2", "m3"]


def test_pilot_lists_command_line_sessions_beside_its_own(tmp_path):
    """One list holds both, newest first, and neither store is written to."""
    from mms_web.server import WebApplication

    config_root = tmp_path / "mms-next"
    sessions = config_root / "pi-gateway" / "sessions"
    sessions.mkdir(parents=True)
    write(sessions, "one", [session("aaaa-1", cwd="/tmp/a"), message("user", "终端里问的问题")])

    app = WebApplication(state_root=tmp_path / "state", config_root=config_root)
    try:
        rows = app.all_sessions(include_cli=True)
        assert [r["id"] for r in rows] == ["cli:aaaa-1"]
        row = rows[0]
        assert row["owner"] == "cli"
        assert row["title"] == "终端里问的问题"
        # Nothing about it is actionable until it is resumed.
        assert row["capabilities"] == {"send": False, "stop": False, "fork": False, "archive": False}

        detail = app.get(["sessions", "cli:aaaa-1"])
        assert [e["kind"] for e in detail["events"]] == ["user"]
        # Arrays the session view reads without checking must be present.
        assert detail["artifacts"] == [] and detail["approvals"] == []
        assert detail["events"][0]["text"] == "终端里问的问题"
        # The transcript path is Pi's business, not the browser's.
        assert "path" not in detail["session"]
    finally:
        app.close()
    # Read-only: the reader must not have touched Pi's directory.
    assert sorted(p.name for p in sessions.iterdir()) == ["one.jsonl"]


def test_the_page_decides_whether_command_line_sessions_are_listed(tmp_path):
    """The switch lives in the browser, so it takes effect on the next read."""
    from mms_web.server import WebApplication

    config_root = tmp_path / "mms-next"
    sessions = config_root / "pi-gateway" / "sessions"
    sessions.mkdir(parents=True)
    write(sessions, "one", [session("bbbb-1"), message("user", "终端里的会话")])
    app = WebApplication(state_root=tmp_path / "hidden", config_root=config_root)
    try:
        assert app.all_sessions() == []
        assert app.get(["sessions"], {"cli": ["0"]})["sessions"] == []
        assert [s["id"] for s in app.get(["sessions"], {"cli": ["1"]})["sessions"]] == ["cli:bbbb-1"]
        # Readable by id either way, so a link to one keeps working.
        assert app.get(["sessions", "cli:bbbb-1"])["session"]["title"] == "终端里的会话"
    finally:
        app.close()


def test_a_missing_gateway_directory_does_not_break_the_list(tmp_path):
    from mms_web.server import WebApplication

    app = WebApplication(state_root=tmp_path / "state", config_root=tmp_path / "empty")
    try:
        assert app.all_sessions() == []
        with pytest.raises(Exception):
            app.get(["sessions", "cli:nope"])
    finally:
        app.close()


@pytest.mark.parametrize("first_message, title", [
    # A path's head is boilerplate every session shares; its end is the part
    # someone means, so the cut goes in the middle.
    ("/private/tmp/claude-501/-Users-xin-repo-multi-model-switch/run/scratchpad",
     "/private/…/run/scratchpad"),
    # A URL is recognised by its host, so that is the half that survives.
    ("https://adsconflux.feishu.cn/wiki/AbCdEfGhIjKl 帮我看看这个文档",
     "adsconflux.feishu.cn/… 帮我看看这个文档"),
    # The scheme says nothing and costs eight characters.
    ("https://adsconflux.feishu.cn/wiki/AbCdEfGhIjKl",
     "adsconflux.feishu.cn/wiki/AbCdEfGhIjKl"),
    # Cut on the space, never inside the word before it.
    ("check the very long english sentence that keeps going past the limit",
     "check the very long english sentence that…"),
    # Chinese has no spaces; its punctuation is what keeps a cut off a phrase.
    ("使用 stride 完成这个需求，先看一下上游是否有迭代，然后再决定下一步怎么走，注意兼容旧配置",
     "使用 stride 完成这个需求，先看一下上游是否有迭代，然后再决定下一步怎么走，…"),
])
def test_a_long_title_keeps_the_part_that_identifies_it(tmp_path, first_message, title):
    path = write(tmp_path, "a", [session("id-t"), message("user", first_message)])
    assert summarize(path)["title"] == title


def test_a_command_line_session_is_placed_in_the_folder_it_ran_in(tmp_path):
    """Otherwise every project's terminal work piles into one group."""
    from mms_web.cli_sessions import workspace_for

    folders = [
        {"id": "outer", "path": "/Users/x/code"},
        {"id": "inner", "path": "/Users/x/code/repo"},
        {"id": "blank", "path": ""},
    ]
    # The deepest registered folder wins, so a subdirectory does not land in
    # the parent project.
    assert workspace_for("/Users/x/code/repo/apps/web", folders) == "inner"
    assert workspace_for("/Users/x/code/repo", folders) == "inner"
    assert workspace_for("/Users/x/code/other", folders) == "outer"
    # A near-miss is not a match: repo-two is its own directory.
    assert workspace_for("/Users/x/code/repo-two", folders) == "outer"
    assert workspace_for("/elsewhere", folders) == ""
    assert workspace_for("", folders) == ""


def test_folder_matching_resolves_symlinks(tmp_path):
    """macOS reports one directory as both /tmp and /private/tmp."""
    from mms_web.cli_sessions import workspace_for

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert workspace_for(str(link), [{"id": "w", "path": str(real)}]) == "w"


def test_listed_command_line_sessions_carry_their_registered_folder(tmp_path):
    from mms_web.server import WebApplication

    state_root = tmp_path / "state"
    state_root.mkdir()
    project = tmp_path / "project"
    (project / "apps").mkdir(parents=True)
    (state_root / "workspaces.json").write_text(
        json.dumps([{"id": "proj", "name": "project", "path": str(project)}]),
        encoding="utf-8")
    config_root = tmp_path / "mms-next"
    sessions = config_root / "pi-gateway" / "sessions"
    sessions.mkdir(parents=True)
    write(sessions, "inside", [session("cccc-1", cwd=str(project / "apps")),
                               message("user", "在子目录里问的")])
    write(sessions, "outside", [session("cccc-2", cwd="/somewhere/else"),
                                message("user", "在别处问的")])

    app = WebApplication(state_root=state_root, config_root=config_root)
    try:
        rows = {r["id"]: r for r in app.all_sessions(include_cli=True)}
        assert rows["cli:cccc-1"]["workspaceId"] == "proj"
        # No match stays empty, and the page groups it by its own directory.
        assert rows["cli:cccc-2"]["workspaceId"] == ""
        assert app.get(["sessions", "cli:cccc-1"])["session"]["workspaceId"] == "proj"
    finally:
        app.close()


@pytest.mark.parametrize("first_message, title", [
    # A link glued to the words in front of it, with no space between.
    ("使用stride-v3完成https://applink.feishu.cn/client/message/open?token=abcd",
     "使用stride-v3完成applink.feishu.cn/…"),
    # Two ellipses in a row read as a rendering fault; one is the cut.
    ("使用 stride 完成需求 https://applink.feishu.cn/client/message/open?token=abcd 然后检查结果对不对",
     "使用 stride 完成需求 applink.feishu.cn/…"),
    # Structure, not just a slash: this is text, and shortening it would
    # destroy the words.
    ("A/B测试方案需要重新评估一下具体的投放比例和人群定向",
     "A/B测试方案需要重新评估一下具体的投放比例和人群定向"),
])
def test_a_link_inside_a_sentence_shrinks_without_taking_the_words_with_it(
        tmp_path, first_message, title):
    path = write(tmp_path, "a", [session("id-u"), message("user", first_message)])
    assert summarize(path)["title"] == title
