"""A `/btw` model answer runs on the session's own route.

No second model, no extra configuration: the same provider, model and key the
main task launched with, sent as one separate stateless request. These tests
use a stub transport; nothing here reaches a network or reads real config.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mms_web import side_question_model as model  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or json.dumps(payload)

    def json(self):
        return self._payload


def make_session(tmp_path, runtime, model_info=None, root=True):
    root_dir = tmp_path / "runtime"
    root_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / "resume.json").write_text(json.dumps({
        "runtime": runtime,
        "modelInfo": model_info if model_info is not None else {"model": "MiniMax-M2.7"},
        "cwd": str(tmp_path),
    }))

    class Session:
        meta = {"runtimeRoot": str(root_dir) if root else ""}

    return Session()


ANTHROPIC_RUNTIME = {
    "id": "prov-1",
    "protocols": ["anthropic_messages", "openai_chat_completions"],
    "anthropic_base_url": "http://127.0.0.1:4003",
    "openai_base_url": "http://127.0.0.1:4003",
    "api_key": "sk-secret-key-value",
    "openai_api_key": "sk-secret-key-value",
}
OPENAI_ONLY_RUNTIME = {
    "id": "prov-2",
    "protocols": ["openai_chat_completions"],
    "openai_base_url": "https://example.invalid/v1",
    "openai_api_key": "sk-other-key-value",
}

CONTEXT = {
    "kind": "mms-web-btw-context/v1",
    "question": "现在进行到哪一步了？",
    "state": "running",
    "recentTools": [{"title": "pytest", "status": "done"}],
}


def capture(monkeypatch, response):
    """Record the one outbound request instead of sending it."""
    seen = {}

    def fake_request(method, url, *, runtime=None, **kwargs):
        seen.update(method=method, url=url, runtime=runtime, **kwargs)
        return response

    monkeypatch.setattr("mms_core._runtime_httpx_request", fake_request)
    return seen


def test_route_is_read_from_the_session_own_resume(tmp_path):
    session = make_session(tmp_path, ANTHROPIC_RUNTIME)
    runtime, wire_model = model.session_route(session)
    assert runtime["id"] == "prov-1"
    assert wire_model == "MiniMax-M2.7"


def test_a_session_without_a_private_runtime_has_no_route(tmp_path):
    assert model.session_route(make_session(tmp_path, ANTHROPIC_RUNTIME, root=False)) is None


def test_a_route_that_declares_anthropic_uses_v1_messages(tmp_path, monkeypatch):
    seen = capture(monkeypatch, FakeResponse({
        "content": [{"type": "text", "text": "正在跑测试。"}],
        "usage": {"input_tokens": 120, "output_tokens": 8},
    }))
    run = model.runner_for(make_session(tmp_path, ANTHROPIC_RUNTIME))
    result = run(CONTEXT, cancel_event=threading.Event(), timeout=30)
    assert seen["url"] == "http://127.0.0.1:4003/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-secret-key-value"
    assert seen["json"]["model"] == "MiniMax-M2.7"
    assert result["answer"] == "正在跑测试。"
    assert result["usage"]["totalTokens"] == 128


def test_only_a_route_without_anthropic_falls_back_to_chat_completions(tmp_path, monkeypatch):
    seen = capture(monkeypatch, FakeResponse({
        "choices": [{"message": {"content": "还在等审批。"}}],
        "usage": {"prompt_tokens": 90, "completion_tokens": 6, "total_tokens": 96},
    }))
    run = model.runner_for(make_session(tmp_path, OPENAI_ONLY_RUNTIME))
    result = run(CONTEXT, cancel_event=threading.Event(), timeout=30)
    assert seen["url"] == "https://example.invalid/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-other-key-value"
    # One answer, not a stream the caller would have to assemble.
    assert seen["json"]["stream"] is False
    assert result["answer"] == "还在等审批。"
    assert result["usage"]["totalTokens"] == 96


def test_the_request_carries_only_the_snapshot_it_was_given(tmp_path, monkeypatch):
    seen = capture(monkeypatch, FakeResponse({"content": [{"type": "text", "text": "ok"}]}))
    run = model.runner_for(make_session(tmp_path, ANTHROPIC_RUNTIME))
    run(CONTEXT, cancel_event=threading.Event(), timeout=30)
    body = json.dumps(seen["json"], ensure_ascii=False)
    assert "现在进行到哪一步了？" in body
    assert "pytest" in body
    # No key, no tools, no transcript, and the model is told what it is missing.
    assert "sk-secret-key-value" not in body
    assert "tools" not in seen["json"]
    # The model is told what it does not know, so it cannot narrate the main task.
    assert "读不到它的对话" in seen["json"]["system"]


def test_no_endpoint_is_probed(tmp_path, monkeypatch):
    """A sensitive relay must not gain a probe because someone asked a question."""
    def explode(*args, **kwargs):
        raise AssertionError("a side question probed an Anthropic endpoint")

    monkeypatch.setattr("mms_launchers._resolve_anthropic_base_url", explode)
    capture(monkeypatch, FakeResponse({"content": [{"type": "text", "text": "ok"}]}))
    run = model.runner_for(make_session(tmp_path, ANTHROPIC_RUNTIME))
    assert run(CONTEXT, cancel_event=threading.Event(), timeout=30)["answer"] == "ok"


def test_a_route_declaring_anthropic_without_a_url_does_not_invent_one(tmp_path, monkeypatch):
    runtime = dict(ANTHROPIC_RUNTIME, anthropic_base_url="")
    seen = capture(monkeypatch, FakeResponse({
        "choices": [{"message": {"content": "ok"}}], "usage": {},
    }))
    run = model.runner_for(make_session(tmp_path, runtime))
    run(CONTEXT, cancel_event=threading.Event(), timeout=30)
    assert seen["url"].endswith("/chat/completions")


def test_a_route_with_no_credentials_has_no_runner(tmp_path):
    runtime = dict(ANTHROPIC_RUNTIME, api_key="", openai_api_key="")
    assert model.runner_for(make_session(tmp_path, runtime)) is None


def test_a_route_with_no_address_has_no_runner(tmp_path):
    runtime = {"id": "p", "protocols": [], "api_key": "sk-key-value-here"}
    assert model.runner_for(make_session(tmp_path, runtime)) is None


def test_an_http_error_is_raised_with_its_status_not_swallowed(tmp_path, monkeypatch):
    capture(monkeypatch, FakeResponse({}, status_code=429, text="rate limited"))
    run = model.runner_for(make_session(tmp_path, ANTHROPIC_RUNTIME))
    with pytest.raises(RuntimeError, match="429"):
        run(CONTEXT, cancel_event=threading.Event(), timeout=30)


def test_a_cancelled_question_sends_nothing(tmp_path, monkeypatch):
    seen = capture(monkeypatch, FakeResponse({"content": []}))
    run = model.runner_for(make_session(tmp_path, ANTHROPIC_RUNTIME))
    cancelled = threading.Event()
    cancelled.set()
    assert run(CONTEXT, cancel_event=cancelled, timeout=30) == {}
    assert not seen


def test_the_service_uses_the_session_route_when_nothing_is_injected(tmp_path, monkeypatch):
    """End to end through SessionService, with the transport stubbed."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_mms_web_sessions_service import make_service, launch_ok

    service, drivers = make_service(tmp_path / "svc", monkeypatch=monkeypatch)
    detail = launch_ok(service)
    session_id = detail["session"]["id"]
    live = service._get(session_id)
    root = tmp_path / "route"
    root.mkdir()
    (root / "resume.json").write_text(json.dumps({
        "runtime": ANTHROPIC_RUNTIME, "modelInfo": {"model": "MiniMax-M2.7"},
    }))
    live.meta["runtimeRoot"] = str(root)
    capture(monkeypatch, FakeResponse({
        "content": [{"type": "text", "text": "主任务在跑测试，已经 3 分钟。"}],
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }))
    row = service.ask_side_question(
        session_id, {"question": "帮我判断这个设计是否合理", "sourceHint": "completion"})
    for _ in range(200):
        row = service.get_side_question(session_id, row["btwId"])
        if row["status"] in {"completed", "failed", "cancelled", "uncertain"}:
            break
        import time
        time.sleep(0.02)
    assert row["status"] == "completed", row["error"]
    assert row["answer"] == "主任务在跑测试，已经 3 分钟。"
    assert row["usage"]["totalTokens"] == 110
    # The main task is untouched: no extra prompt, no new events.
    assert drivers[0].prompts == ["hi"]
    assert len(service._get(session_id).detail_view()["events"]) == len(detail["events"])
    service.close()
