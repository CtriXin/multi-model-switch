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


def test_transcript_keeps_the_tail_and_drops_non_messages(tmp_path):
    path = write(tmp_path, "a", [
        session("id-3"),
        {"type": "thinking_level_change", "level": "high"},
        message("user", "问题", "m1"),
        message("assistant", "回答", "m2"),
        message("toolResult", "工具输出", "m3"),
    ])
    rows = transcript(path)
    assert [r["role"] for r in rows] == ["user", "assistant", "toolResult"]
    assert rows[0]["text"] == "问题"
    # A long session is read from the end, which is what someone wants to see.
    assert [r["id"] for r in transcript(path, limit=2)] == ["m2", "m3"]
    assert transcript(tmp_path / "missing.jsonl") == []
