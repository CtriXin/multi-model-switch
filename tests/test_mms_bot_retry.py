from datetime import datetime, timedelta, timezone
import time

import pytest

from mms_web.bot_retry import RETRY_DELAYS, RETRY_LIMIT, classify, exhausted_message, schedule
from mms_web.bots import BotRuntime
from mms_web.errors import WebError


class ScriptedExecutor:
    """Fails `failures` launches with the given error, then succeeds."""

    def __init__(self, failures=0, error=None):
        self.failures = failures
        self.error = error or WebError("BOT_SESSION_BUSY", "Bot 的会话仍在执行或等待确认。", 409)
        self.starts = []

    def available(self):
        return True

    def validate(self, bot):
        return {"model": "fake"}

    def start(self, task, bot, context_path):
        self.starts.append(task["id"])
        if len(self.starts) <= self.failures:
            raise self.error
        return {"sessionId": f"session-{len(self.starts)}", "baseline": 0,
                "artifactBaseline": {}, "model": "fake"}

    def snapshot(self, task):
        return {"state": "completed", "alive": False, "artifacts": [],
                "events": [{"id": "answer", "kind": "assistant", "status": "done", "text": "完成"}]}

    def cancel(self, task):
        pass

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


def runtime(tmp_path, executor):
    rt = BotRuntime(state_root=tmp_path, executor=executor)
    rt.configure_endpoint("http://127.0.0.1:9/api/v1/bot-worker")
    return rt


def make_task(rt, prompt="待办"):
    bot = rt.create_bot({"name": "重试 Bot", "description": "", "systemPrompt": "",
                         "workspaceId": "ws-1", "presetId": "pi:fake", "wakeEnabled": True})
    return rt.create_task({"botId": bot["id"], "prompt": prompt})


def step(rt, task_id, predicate, steps=40):
    """Tick, drain launch workers and fast-forward any pending backoff."""
    for _ in range(steps):
        rt.tick()
        for worker in list(rt._workers):
            worker.join(timeout=1)
        task = rt._tasks[task_id]
        if predicate(task):
            return task
        retry = task.get("retry") or {}
        if retry.get("nextAt"):
            retry["nextAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        time.sleep(0.005)
    return rt._tasks[task_id]


@pytest.mark.parametrize(("code", "message"), [
    ("BOT_EXECUTOR_UNAVAILABLE", "Pi 执行器尚未连接。"),
    ("BOT_SESSION_BUSY", "Bot 的会话仍在执行或等待确认。"),
    ("BOT_ENDPOINT_UNAVAILABLE", "Bot 服务尚未开始监听。"),
    ("", "Pi 进程未启动就退出。"),
    ("", "dial tcp 127.0.0.1:7897: connect: connection refused"),
    ("", "read: connection reset by peer"),
    ("", "upstream request timed out after 30s"),
    ("", "provider returned HTTP 429"),
    ("", "provider returned HTTP 502"),
    ("", "provider returned HTTP 503"),
    ("", "provider returned HTTP 504"),
])
def test_classify_transient_infrastructure_errors(code, message):
    assert classify(code, message) == "transient"


@pytest.mark.parametrize(("code", "message"), [
    ("BOT_MODEL_REQUIRED", "MMS 当前没有可启动的 Pi 模型。"),
    ("BOT_GLOBAL_WORKSPACE_REQUIRED", "共享电脑的默认工作环境不可用。"),
    ("", "用户取消了这个任务。"),
    ("", "模型明确拒绝执行这个请求。"),
    ("", "本轮结束但没有收到结果。"),
    ("", "任务已经开始执行并产生副作用之后的失败。"),
    ("", "无法解析的未知失败"),
])
def test_classify_permanent_decisions(code, message):
    assert classify(code, message) == "permanent"


def test_unknown_failure_without_hints_is_permanent():
    assert classify("BOT_STORE_INVALID", "Bot 记录无法读取。") == "permanent"


@pytest.mark.parametrize(("code", "message", "status", "expected"), [
    # The launch seam itself failed with a 5xx: nothing was delivered yet.
    ("LAUNCH_FAILED", "MMS 未能启动所选模型，请检查本机 Pi 和模型服务。", 502, "transient"),
    ("LAUNCH_FAILED", "Pi 子进程无法启动", 502, "transient"),
    # A missing executable is a local configuration problem, not a hiccup.
    ("LAUNCH_FAILED", "Pi 可执行文件不存在", 502, "permanent"),
    # Unconfirmed delivery must never be replayed.
    ("RPC_UNCONFIRMED", "Pi 在确认前断开，发送结果待确认。", 502, "permanent"),
    ("RPC_TIMEOUT", "Pi 未在超时内确认消息", 504, "permanent"),
    ("SEND_FAILED", "Pi 未接受该消息，请检查所选服务连接后重试。", 502, "permanent"),
    ("LAUNCH_FAILED", "MMS 未能启动所选模型。", 409, "permanent"),
])
def test_classify_uses_launch_status_without_replaying_delivery(code, message, status, expected):
    assert classify(code, message, status=status) == expected


def test_backoff_schedule_is_30s_2min_8min(tmp_path):
    assert RETRY_DELAYS == (30, 120, 480)
    task = {"status": "starting"}
    moment = datetime(2026, 9, 12, 3, 0, 0, tzinfo=timezone.utc)
    expected = [(1, 30), (2, 120), (3, 480)]
    for count, delay in expected:
        record = schedule(task, "connection refused", error_code="BOT_SESSION_BUSY", moment=moment)
        assert record["count"] == count
        assert datetime.fromisoformat(record["nextAt"]) == moment + timedelta(seconds=delay)
        assert task["status"] == "queued"
        assert task["queueReason"].startswith(f"等待重试（第 {count} 次")
    assert schedule(task, "connection refused", moment=moment) is None
    assert len(task["retry"]["history"]) == RETRY_LIMIT


def test_exhausted_message_lists_every_attempt_time_and_reason():
    task = {"retry": {"count": 3, "history": [
        {"attempt": 1, "at": "2026-09-12T03:00:00+00:00", "delaySeconds": 30, "error": "连接被拒绝", "errorCode": "BOT_SESSION_BUSY"},
        {"attempt": 2, "at": "2026-09-12T03:00:30+00:00", "delaySeconds": 120, "error": "连接被拒绝", "errorCode": "BOT_SESSION_BUSY"},
        {"attempt": 3, "at": "2026-09-12T03:02:30+00:00", "delaySeconds": 480, "error": "连接被拒绝", "errorCode": "BOT_SESSION_BUSY"},
    ]}}
    message = exhausted_message(task, "Pi 启动失败。")
    assert message.startswith("三次自动重试均失败：")
    for fragment in ("2026-09-12T03:00:00", "2026-09-12T03:00:30", "2026-09-12T03:02:30", "连接被拒绝"):
        assert fragment in message
    assert message.endswith("最终失败：Pi 启动失败。")


def test_transient_launch_failure_requeues_with_backoff(tmp_path):
    executor = ScriptedExecutor(failures=1)
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        failed_once = step(rt, task["id"], lambda item: bool(item.get("retry")))
        assert failed_once["status"] == "queued"
        assert failed_once["retry"]["count"] == 1
        assert failed_once["queueReason"].startswith("等待重试（第 1 次")
        assert datetime.fromisoformat(failed_once["retry"]["nextAt"]) > datetime.now(timezone.utc)
        assert len(executor.starts) == 1
        assert rt.capabilities()["available"] is True

        # A pending backoff must not launch early.
        rt.tick()
        assert len(executor.starts) == 1

        done = step(rt, task["id"], lambda item: item["status"] == "completed")
        assert done["status"] == "completed"
        assert len(executor.starts) == 2
        assert not done.get("retry")
    finally:
        rt.close()


def test_running_failure_is_never_retried(tmp_path):
    class RunningFailure(ScriptedExecutor):
        def start(self, task, bot, context_path):
            self.starts.append(task["id"])
            return {"sessionId": "session-running", "baseline": 0, "artifactBaseline": {}, "model": "fake"}

        def snapshot(self, task):
            return {"state": "error", "alive": False, "artifacts": [], "events": []}

    executor = RunningFailure()
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        failed = step(rt, task["id"], lambda item: item["status"] == "failed")
        assert failed["status"] == "failed"
        assert not failed.get("retry")
        assert len(executor.starts) == 1
    finally:
        rt.close()


def test_permanent_launch_failure_fails_without_retry(tmp_path):
    executor = ScriptedExecutor(failures=1, error=WebError("BOT_MODEL_REQUIRED", "MMS 当前没有可启动的 Pi 模型。", 400))
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        failed = step(rt, task["id"], lambda item: item["status"] in {"failed", "interrupted"})
        assert failed["status"] == "interrupted"
        assert not failed.get("retry")
        assert len(executor.starts) == 1
    finally:
        rt.close()


def test_launch_seam_502_is_retried_but_missing_executable_is_not(tmp_path):
    seam = ScriptedExecutor(failures=1, error=WebError("LAUNCH_FAILED", "MMS 未能启动所选模型，请检查本机 Pi 和模型服务。", 502))
    rt = runtime(tmp_path, seam)
    try:
        task = make_task(rt)
        retrying = step(rt, task["id"], lambda item: bool(item.get("retry")))
        assert retrying["status"] == "queued" and retrying["retry"]["count"] == 1
        done = step(rt, task["id"], lambda item: item["status"] == "completed")
        assert done["status"] == "completed"
    finally:
        rt.close()

    missing = ScriptedExecutor(failures=1, error=WebError("LAUNCH_FAILED", "Pi 可执行文件不存在", 502))
    rt = runtime(tmp_path / "missing", missing)
    try:
        task = make_task(rt)
        failed = step(rt, task["id"], lambda item: item["status"] in {"failed", "interrupted"})
        assert failed["status"] == "interrupted"
        assert not failed.get("retry")
        assert len(missing.starts) == 1
    finally:
        rt.close()


def test_three_failed_retries_end_failed_with_all_attempts(tmp_path):
    executor = ScriptedExecutor(failures=10)
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        failed = step(rt, task["id"], lambda item: item["status"] == "failed")
        assert failed["status"] == "failed"
        assert not failed.get("retry")
        assert len(executor.starts) == 4  # first launch + three retries
        assert "三次自动重试均失败：" in failed["error"]
        assert failed["error"].count("等待重试") == 0
        history = [message for message in rt.list_messages(task["id"])
                   if message["content"].startswith("基础设施暂时不可用")]
        assert len(history) == 3
    finally:
        rt.close()


def test_cancel_clears_pending_retry(tmp_path):
    executor = ScriptedExecutor(failures=10)
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        retrying = step(rt, task["id"], lambda item: bool(item.get("retry")))
        assert retrying["status"] == "queued"
        cancelled = rt.cancel_task(task["id"])
        assert cancelled["status"] == "cancelled"
        assert not cancelled.get("retry")
        rt.tick()
        assert len(executor.starts) == 1
    finally:
        rt.close()


def test_wake_and_follow_up_clear_pending_retry(tmp_path):
    executor = ScriptedExecutor(failures=10)
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        retrying = step(rt, task["id"], lambda item: bool(item.get("retry")))
        assert retrying["status"] == "queued"
        rt.wake_task(task["id"])
        assert not rt.get_task(task["id"]).get("retry")

        rt2_executor = ScriptedExecutor(failures=10)
        rt2 = runtime(tmp_path / "second", rt2_executor)
        try:
            second = make_task(rt2)
            step(rt2, second["id"], lambda item: bool(item.get("retry")))
            rt2.add_message(second["id"], {"content": "继续"})
            assert not rt2.get_task(second["id"]).get("retry")
        finally:
            rt2.close()
    finally:
        rt.close()


def test_retry_survives_restart_and_resumes_when_due(tmp_path):
    executor = ScriptedExecutor(failures=1)
    rt = runtime(tmp_path, executor)
    try:
        task = make_task(rt)
        step(rt, task["id"], lambda item: bool(item.get("retry")))
    finally:
        rt.close()

    resumed = runtime(tmp_path, executor)
    try:
        stored = resumed.get_task(task["id"])
        assert stored["status"] == "queued" and stored["retry"]["count"] == 1
        short = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        resumed._tasks[task["id"]]["retry"]["nextAt"] = short
        resumed.tick()
        assert len(executor.starts) == 1  # not due yet
        resumed._tasks[task["id"]]["retry"]["nextAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        done = step(resumed, task["id"], lambda item: item["status"] == "completed")
        assert done["status"] == "completed"
        assert len(executor.starts) == 2
    finally:
        resumed.close()
