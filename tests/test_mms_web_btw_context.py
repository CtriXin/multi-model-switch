"""Pilot ``/btw`` completion context: the recent-turn excerpt.

The side model may see the last few user/assistant texts the session already
mirrored into its redacted event list, budgeted and labelled as an excerpt.
It may not see tool output bodies, thinking, files or the driver, and asking
must still leave the main transcript untouched.
"""

from __future__ import annotations

import json

from mms_web.side_questions import _MAX_TURN_TEXT, _MAX_TURNS

from test_mms_web_btw_backend import wait_btw  # noqa: E402
from test_mms_web_sessions_service import launch_ok, make_service  # noqa: E402


def _capturing_runner(seen: dict):
    def runner(context, *, cancel_event, timeout):
        seen.update(context)
        return {"answer": "看过摘录了。"}
    return runner


def test_completion_context_carries_recent_turn_text_only(tmp_path, monkeypatch):
    seen: dict = {}
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=_capturing_runner(seen))
    session_id = launch_ok(service, prompt="请读一下 README 并总结")["session"]["id"]
    sink = drivers[0]._sink
    sink.upsert_event({"id": "t-1", "kind": "tool", "title": "read", "status": "done",
                       "text": "TOOL-OUTPUT-BODY " * 50})
    sink.upsert_event({"id": "m-1", "kind": "assistant", "text": "README 说这是一个 CLI。",
                       "thinking": "SECRET-THOUGHT"})
    live = service._get(session_id)
    before = live.last_sequence

    row = service.ask_side_question(session_id, {"question": "它总结出什么了？", "sourceHint": "completion"})
    final = wait_btw(service, session_id, row["btwId"], {"completed"})

    assert seen["recentTurns"] == [
        {"role": "user", "text": "请读一下 README 并总结"},
        {"role": "assistant", "text": "README 说这是一个 CLI。"},
    ]
    dumped = json.dumps(seen, ensure_ascii=False)
    assert "TOOL-OUTPUT-BODY" not in dumped
    assert "SECRET-THOUGHT" not in dumped
    assert seen["contextScope"] == {"recentTurns": 2, "totalTurns": 2, "truncated": False}
    assert final["contextScope"] == {"recentTurns": 2, "totalTurns": 2, "truncated": False}
    # The excerpt is read from the mirror; nothing was written back.
    assert live.last_sequence == before
    assert drivers[0].prompts == ["请读一下 README 并总结"]
    service.close()


def test_recent_turns_are_budgeted_truncated_and_redacted(tmp_path, monkeypatch):
    seen: dict = {}
    service, drivers = make_service(tmp_path, monkeypatch=monkeypatch, sidecar_runner=_capturing_runner(seen))
    session_id = launch_ok(service)["session"]["id"]
    live = service._get(session_id)
    live.secrets.append("sk-livesecret456")
    sink = drivers[0]._sink
    for index in range(10):
        sink.upsert_event({"id": f"m-{index}", "kind": "assistant",
                           "text": f"第{index}轮 " + ("很长的回答。" * 400) + " key=sk-livesecret456"})

    row = service.ask_side_question(session_id, {"question": "前面说了什么", "sourceHint": "completion"})
    final = wait_btw(service, session_id, row["btwId"], {"completed"})

    turns = seen["recentTurns"]
    assert 0 < len(turns) <= _MAX_TURNS
    assert all(len(turn["text"]) <= _MAX_TURN_TEXT + 1 for turn in turns)
    # Newest last, and the newest turn is the one that survives the budget.
    assert turns[-1]["text"].startswith("第9轮")
    assert "sk-livesecret456" not in json.dumps(seen, ensure_ascii=False)
    assert seen["contextScope"]["truncated"] is True
    assert seen["contextScope"]["totalTurns"] == 11  # launch prompt + 10 replies
    assert final["contextScope"]["truncated"] is True
    service.close()


def test_state_answer_leaves_context_scope_empty(tmp_path, monkeypatch):
    service, _ = make_service(tmp_path, monkeypatch=monkeypatch)
    session_id = launch_ok(service)["session"]["id"]
    row = service.ask_side_question(session_id, {"question": "现在进度如何"})
    assert row["source"] == "state"
    assert row["status"] == "completed"
    assert row["contextScope"] is None
    service.close()


def test_prompt_labels_the_excerpt_as_partial():
    from mms_web.side_question_model import _SYSTEM, _prompt

    text = _prompt({
        "question": "刚才做了什么",
        "state": "running",
        "recentTurns": [{"role": "user", "text": "读 README"}, {"role": "assistant", "text": "读完了"}],
        "contextScope": {"recentTurns": 2, "totalTurns": 9, "truncated": True},
    })
    assert "[user] 读 README" in text and "[assistant] 读完了" in text
    assert "可能截断" in text
    assert '"recentTurns": [' not in text  # the excerpt is rendered once, as text
    assert "读不到它的对话" in _SYSTEM and "摘录" in _SYSTEM
