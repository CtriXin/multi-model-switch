"""Dead-model rescue through production readers, driver sink, persistence and API.

All histories, workspaces, credentials and drivers are task-owned fixtures.
"""
import json
from pathlib import Path

import pytest

from mms_web.cli_sessions import transcript
from mms_web.drivers.pi_rpc import PiRpcDriver
from mms_web.errors import WebError
from mms_web.server import WebApplication
from mms_web.session_recovery import recovery_packet, recovery_state
from test_mms_web_cli_sessions import message, session, tool_call, write
from test_mms_web_sessions_service import make_service, launch_ok, seeded_seam


def application(config, service=None):
    app = WebApplication.__new__(WebApplication)
    app.config_root = config
    app.catalog = None
    app.sessions = service
    return app


def failed(ident):
    return {"type": "message", "id": ident, "message": {
        "role": "assistant", "content": [], "stopReason": "error",
        "errorMessage": "504 Connection error Bearer secret-value-12345"}}


def test_cli_error_only_tail_is_visible_and_recoverable_without_model(tmp_path):
    root = tmp_path / "pi-gateway" / "sessions"
    root.mkdir(parents=True)
    path = write(root, "dead", [session("dead"), message("user", "保留我的布局"),
        tool_call("bash", "write-1", {"command": "deploy pending"}),
        *[failed(f"e{n}") for n in range(3)]])
    with path.open("a") as f:
        f.write('{"incomplete":')
    before = path.read_bytes()
    app = application(tmp_path)
    detail = app.get(["sessions", "cli:dead"])
    assert detail["recovery"]["consecutiveFailures"] == 3
    assert detail["recovery"]["suggested"] is True
    assert "504 Connection error" in detail["events"][-1]["text"]
    assert "secret-value-12345" not in json.dumps(detail)
    packet = app.get(["sessions", "cli:dead", "recovery"])
    assert packet["nativeHistoryAvailable"] is True
    assert str(path) in packet["prompt"]
    assert "保留我的布局" in packet["prompt"]
    assert "执行结果待确认" in packet["prompt"]
    assert "deploy pending" in packet["prompt"]
    assert "不要自动重放" in packet["prompt"]
    assert path.read_bytes() == before
    with pytest.raises(WebError) as e:
        app.get(["sessions", "cli:../../outside", "recovery"])
    assert e.value.status == 404


def test_cli_successful_tool_call_resets_old_failure_streak(tmp_path):
    path = write(tmp_path, "reset", [session("reset"), *[failed(f"e{n}") for n in range(3)],
         tool_call("read", "ok", {"path": "/tmp/file"}), failed("latest")])
    assert recovery_state(transcript(path))["consecutiveFailures"] == 1
    assert recovery_state(transcript(path))["suggested"] is False


def protocol_driver(sink):
    # Exercise the real dispatcher/message-end mapping without a provider.
    driver = PiRpcDriver.__new__(PiRpcDriver)
    driver._sink = sink
    driver._streaming = False
    driver._open_assistant_id = None
    return driver


def test_driver_to_api_survives_death_restart_and_does_not_replay(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    try:
        sid = launch_ok(service, prompt="只检查，不要部署")["session"]["id"]
        live = service._get(sid)
        live.secrets = ["private-session-secret"]
        driver = protocol_driver(drivers[0]._sink)
        for n in range(3):
            driver._handle_message_end({"message": {"role": "assistant", "content": [],
                "stopReason": "error", "errorMessage": "504 private-session-secret"}})
        driver._handle_event({"type": "auto_retry_end", "success": False, "attempt": 8, "finalError": "504 private-session-secret"})
        app = application(tmp_path / "config", service)
        state = app.get(["sessions", sid, "recovery"])["recovery"]
        assert state["suggested"] and state["retryExhausted"]
        assert state["consecutiveFailures"] == 3
        assert "private-session-secret" not in json.dumps(state)
        calls = list(drivers[0].prompts)
        drivers[0].kill()
        first = app.get(["sessions", sid, "recovery"])
        assert first["nativeHistoryAvailable"] is False
        assert "只检查，不要部署" in first["prompt"]
        assert drivers[0].prompts == calls
        service.close()
        restarted, new_drivers = make_service(tmp_path)
        try:
            packet = application(tmp_path / "config", restarted).get(["sessions", sid, "recovery"])
            assert packet["recovery"]["suggested"] is True
            assert "只检查，不要部署" in packet["prompt"]
            assert new_drivers == []  # GET does not resurrect or send a turn.
        finally:
            restarted.close()
    finally:
        service.close()


def test_driver_success_reset_and_cancel_are_not_provider_failure(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    try:
        sid = launch_ok(service)["session"]["id"]
        driver = protocol_driver(drivers[0]._sink)
        driver._handle_event({"type": "auto_retry_start", "attempt": 1, "maxAttempts": 8, "errorMessage": "504"})
        assert not service.get_session(sid)["recovery"]["suggested"]
        driver._handle_event({"type": "auto_retry_end", "attempt": 8, "success": False, "finalError": "504"})
        assert service.get_session(sid)["recovery"]["suggested"]
        driver._handle_message_end({"message": {"role": "assistant", "content": [{"type": "text", "text": "好了"}], "stopReason": "stop"}})
        assert not service.get_session(sid)["recovery"]["suggested"]
        driver._handle_message_end({"message": {"role": "assistant", "content": [], "stopReason": "aborted"}})
        assert service.get_session(sid)["recovery"]["consecutiveFailures"] == 0
    finally:
        service.close()


def test_owned_native_path_only_and_original_file_untouched(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    try:
        sid = launch_ok(service)["session"]["id"]
        live = service._get(sid)
        native_root = tmp_path / "state" / "runtimes" / "r1"
        native_root.mkdir(parents=True)
        native = native_root / "conversation.jsonl"
        native.write_text("fixture history")
        live.meta["runtimeRoot"] = str(native_root)
        app = application(tmp_path / "config", service)
        assert str(native) in app.get(["sessions", sid, "recovery"])["prompt"]
        assert native.read_text() == "fixture history"
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "conversation.jsonl").write_text("private")
        live.meta["runtimeRoot"] = str(outside)
        assert not app.get(["sessions", sid, "recovery"])["nativeHistoryAvailable"]
        link = native_root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        live.meta["runtimeRoot"] = str(link)
        assert not app.get(["sessions", sid, "recovery"])["nativeHistoryAvailable"]
    finally:
        service.close()


def test_packet_bounds_masks_secrets_and_labels_claims():
    detail = {"session": {"id": "s", "title": "我的任务", "cwd": "/tmp/ws"},
        "events": [{"kind": "user", "text": 'API_KEY="abc123" Bearer hidden987 sk-123456789abcdef ' + "长" * 50000},
                   {"kind": "assistant", "text": "声称完成 password=p4ss", "modelOutcome": "success"}],
        "artifacts": [{"path": f"/tmp/{n}.md"} for n in range(30)]}
    packet = recovery_packet(detail)
    assert len(packet["prompt"]) < 22000
    for value in ("abc123", "hidden987", "sk-123456789abcdef", "p4ss"):
        assert value not in packet["prompt"]
    assert "尚需核对" in packet["prompt"]
    assert "不是已验收" in packet["prompt"]
    assert "/tmp/0.md" not in packet["prompt"]

# Real Pi with the existing loopback-only provider fixture. This verifies the
# create-session consumer, not merely the shape of the recovery helper.
from test_mms_web_interactions import local_app, native, settle


def test_native_fresh_session_only_sends_reviewed_packet_and_preserves_source(native):
    app, workspace, records = native
    preset = "web:pi:local-vision:gpt-5"
    old = app.post(["sessions"], {"requestId": "recovery-old", "workspaceId": workspace["id"],
        "presetId": preset, "prompt": "不要部署，请检查布局"})["session"]["id"]
    settle(app, old)
    live = app.sessions._get(old)
    native_path = Path(live.meta["runtimeRoot"]) / "conversation.jsonl"
    live.driver.close(graceful_timeout=2)
    before = native_path.read_bytes()
    request_count = len(records)
    packet = app.get(["sessions", old, "recovery"])
    assert len(records) == request_count
    assert packet["nativeHistoryAvailable"]
    new = app.post(["sessions"], {"requestId": "recovery-new", "workspaceId": workspace["id"],
        "presetId": preset, "prompt": packet["prompt"] + "\n我已核对，请继续检查。"})["session"]["id"]
    result = settle(app, new)
    assert result["session"]["state"] == "idle"
    assert new != old
    sent = records[-1]["messages"]
    assert len([m for m in sent if m["role"] == "user"]) == 1
    assert not any(m["role"] in {"assistant", "tool"} for m in sent)
    assert "我已核对" in json.dumps(sent, ensure_ascii=False)
    assert native_path.read_bytes() == before
    assert app.sessions._get(new).meta["runtimeRoot"] != live.meta["runtimeRoot"]

@pytest.mark.parametrize('status', ['cancelled', 'interrupted', 'queued', 'failed', 'uncertain'])
def test_undelivered_requests_keep_status_in_recovery(status):
    packet = recovery_packet({'session': {'id': 's'}, 'events': [
        {'kind': 'user', 'text': '这条没有确认执行的消息', 'status': status}]})
    assert f'[消息状态：{status}]' in packet['prompt']
    assert '未执行或执行结果待确认' in packet['prompt']


def test_retry_error_is_redacted_before_truncation_and_persistence(tmp_path, seeded_seam):
    service, drivers = make_service(tmp_path)
    try:
        sid = launch_ok(service)['session']['id']
        live = service._get(sid)
        secret = 'synthetic-private-' + 'a1b2c3' * 18
        live.secrets = [secret]
        driver = protocol_driver(drivers[0]._sink)
        for prefix in (380, 780):
            driver._handle_event({'type': 'auto_retry_end', 'success': False,
                'finalError': 'x' * prefix + secret + 'y' * 1000})
        packet = application(tmp_path / 'config', service).get(['sessions', sid, 'recovery'])
        assert secret[:20] not in json.dumps(packet)
        assert secret[:20] not in json.dumps(live.events)
        assert secret[:20] not in (service._state_dir / f'{sid}.json').read_text()
    finally:
        service.close()
