"""Focused contracts for the BotRuntime worker seam."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mms_web.bots import BotRuntime, TERMINAL
from mms_web.errors import WebError


class Executor:
    def __init__(self):
        self.started = {}

    def available(self):
        return True

    def validate(self, bot):
        return {"model": "test-model"}

    def start(self, task, bot, context_path):
        self.started[task["id"]] = str(context_path)
        return {"sessionId": "session-" + task["id"], "baseline": {}, "artifactBaseline": {}, "model": "test-model"}

    def snapshot(self, task):
        return {"state": "running", "alive": True, "events": [], "artifacts": []}

    def cancel(self, task):
        return None

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


def make_runtime(tmp_path):
    executor = Executor()
    runtime = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=1)
    runtime.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    return runtime, executor


def make_bot(runtime, name="worker", workspace="workspace"):
    return runtime.create_bot({"name": name, "description": "", "systemPrompt": "", "workspaceId": workspace,
                               "presetId": "pi:test", "wakeEnabled": True})


def launch(runtime, task_id):
    runtime.tick()
    for worker in list(runtime._workers):
        worker.join(timeout=1)
    return runtime.get_task(task_id)


def drain_launch(runtime):
    for worker in list(runtime._workers):
        worker.join(timeout=1)


def test_worker_context_is_task_scoped_and_token_is_redacted(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "context", "botId": target["id"], "prompt": "inspect"})
        view = launch(runtime, task["id"])
        context = Path(executor.started[task["id"]])
        assert context.is_file() and context.parent.name == "contexts"
        assert "token" not in view
        with pytest.raises(WebError) as invalid:
            runtime.authorize_worker("not-the-token")
        assert invalid.value.code == "BOT_WORKER_UNAUTHORIZED"
        token = runtime._tasks[task["id"]]["token"]
        assert runtime.authorize_worker(token) == task["id"]
    finally:
        runtime.close()


def test_worker_status_cannot_escape_current_task_tree(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        first = make_bot(runtime, "first", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        parent = runtime.create_task({"requestId": "parent", "botId": first["id"], "prompt": "parent"})
        other = runtime.create_task({"requestId": "other", "botId": second["id"], "prompt": "other"})
        launch(runtime, parent["id"])
        with pytest.raises(WebError) as failure:
            runtime.worker(parent["id"], {"action": "status", "taskId": other["id"]})
        assert failure.value.code == "BOT_SCOPE"
    finally:
        runtime.close()


def test_list_artifacts_never_exposes_local_path(tmp_path):
    class Computer:
        def capture(self, task_id, url=None):
            path = Path(tmp_path) / "bots" / "screenshots" / task_id / "shot.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            content = b"private screenshot"
            path.write_bytes(content)
            return {"name": "shot.png", "path": str(path), "kind": "screenshot", "mimeType": "image/png",
                    "sha256": hashlib.sha256(content).hexdigest(), "spaceId": 1, "page": "p1"}

    runtime = BotRuntime(state_root=tmp_path, executor=Executor(), computer=Computer())
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "shot", "botId": target["id"], "prompt": "shot"})
        runtime.screenshot(task["id"])
        listed = runtime.list_artifacts(task["id"])
        assert listed and "path" not in listed[0]
        assert listed[0]["url"].startswith("/api/v1/tasks/")
    finally:
        runtime.close()


def test_add_message_request_id_is_idempotent_and_does_not_duplicate_inbox(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "message-task", "botId": target["id"], "prompt": "long turn"})
        launch(runtime, task["id"])
        first = runtime.add_message(task["id"], {"requestId": "message-1", "content": "继续这一轮"})
        second = runtime.add_message(task["id"], {"requestId": "message-1", "content": "继续这一轮"})
        assert first["id"] == second["id"]
        assert runtime._tasks[task["id"]]["inbox"] == ["继续这一轮"]
        assert len([m for m in runtime.list_messages(task["id"]) if m["content"] == "继续这一轮"]) == 1
    finally:
        runtime.close()


def test_snapshot_error_keeps_connection_and_workspace_reserved_until_recovery(tmp_path):
    class RecoveringExecutor(Executor):
        def __init__(self):
            super().__init__()
            self.snapshot_calls = 0

        def snapshot(self, task):
            self.snapshot_calls += 1
            if self.snapshot_calls == 1:
                raise RuntimeError("temporary disconnect")
            return {"state": "completed", "alive": False, "events": [{
                "id": "recovered-answer", "kind": "assistant", "status": "done", "text": "恢复完成",
            }], "artifacts": []}

    executor = RecoveringExecutor()
    runtime = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=2)
    runtime.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    try:
        first_bot = make_bot(runtime, "first", "shared-workspace")
        second_bot = make_bot(runtime, "second", "shared-workspace")
        first = runtime.create_task({"requestId": "recover-first", "botId": first_bot["id"], "prompt": "first"})
        second = runtime.create_task({"requestId": "recover-second", "botId": second_bot["id"], "prompt": "second"})
        runtime.tick(); drain_launch(runtime)
        runtime.tick()
        assert runtime.get_task(first["id"])["status"] == "waiting"
        assert runtime._tasks[first["id"]]["waitReason"] == "connection"
        assert runtime.get_task(second["id"])["status"] == "queued"
        runtime.tick(); drain_launch(runtime)
        assert runtime.get_task(first["id"])["status"] == "completed"
        assert runtime.get_task(first["id"])["error"] is None
        assert runtime.get_task(second["id"])["status"] == "running"
    finally:
        runtime.close()


def test_cancel_force_stop_is_once_after_grace_and_requires_stopped_confirmation(tmp_path):
    class GracefulExecutor(Executor):
        def __init__(self):
            super().__init__()
            self.force_stops = 0
            self.snapshot_calls = 0

        def snapshot(self, task):
            self.snapshot_calls += 1
            # The first snapshot after force_stop still reports a live process;
            # only the next observation confirms that cancellation took effect.
            if self.force_stops and self.snapshot_calls >= 2:
                return {"state": "stopped", "alive": False, "events": [], "artifacts": []}
            return {"state": "running", "alive": True, "events": [], "artifacts": []}

        def force_stop(self, task):
            self.force_stops += 1

    executor = GracefulExecutor()
    runtime = BotRuntime(state_root=tmp_path, executor=executor)
    runtime.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "grace-task", "botId": target["id"], "prompt": "stop me"})
        launch(runtime, task["id"])
        runtime.cancel_task(task["id"])
        runtime._tasks[task["id"]]["cancelAt"] = (datetime.now(timezone.utc) - timedelta(seconds=16)).isoformat()
        runtime.tick()
        assert executor.force_stops == 1
        assert runtime.get_task(task["id"])["status"] in {"running", "waiting"}
        runtime.tick()
        assert executor.force_stops == 1
        assert runtime.get_task(task["id"])["status"] == "cancelled"
    finally:
        runtime.close()


def test_queued_tasks_are_started_by_priority_then_creation_order(tmp_path):
    executor = Executor()
    runtime = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=1)
    runtime.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    try:
        first_bot = make_bot(runtime, "first", "workspace-a")
        second_bot = make_bot(runtime, "second", "workspace-b")
        first = runtime.create_task({"requestId": "low", "botId": first_bot["id"], "prompt": "low", "priority": 10})
        second = runtime.create_task({"requestId": "high", "botId": second_bot["id"], "prompt": "high", "priority": 90})
        runtime.tick(); drain_launch(runtime)
        assert executor.started == {second["id"]: executor.started[second["id"]]}
        assert runtime.get_task(first["id"])["status"] == "queued"
        assert runtime.get_task(first["id"])["queueReason"] == "等待并发资源"
    finally:
        runtime.close()


def test_restart_keeps_workspace_reserved_while_old_process_exists(tmp_path):
    class OrphanExecutor(Executor):
        alive = True
        def orphan_alive(self, task):
            return self.alive
    executor = OrphanExecutor()
    original = BotRuntime(state_root=tmp_path, executor=executor)
    original.configure_endpoint('http://127.0.0.1:8123/api/v1/bot-worker')
    first_bot = make_bot(original, 'original', 'shared')
    second_bot = make_bot(original, 'next', 'shared')
    first = original.create_task({'botId': first_bot['id'], 'prompt': 'in flight'})
    second = original.create_task({'botId': second_bot['id'], 'prompt': 'queued'})
    launch(original, first['id'])
    # Simulate a process crash: release the lease without clean shutdown.
    original._file_lock.close()
    original._file_lock = None
    restored = BotRuntime(state_root=tmp_path, executor=executor)
    restored.configure_endpoint('http://127.0.0.1:8123/api/v1/bot-worker')
    try:
        restored.tick()
        assert restored.get_task(first['id'])['status'] == 'interrupted'
        assert restored.get_task(second['id'])['status'] == 'queued'
        with pytest.raises(WebError, match='上次执行进程'):
            restored.wake_task(first['id'])
        executor.alive = False
        restored.tick()
        drain_launch(restored)
        assert restored.get_task(second['id'])['status'] == 'running'
    finally:
        restored.close()
        original.close()


def _observe(runtime, bot_id, events, *, state="running"):
    task = runtime.create_task({"requestId": "observe-" + str(len(runtime._tasks)),
                                "botId": bot_id, "prompt": "observe events"})
    internal = runtime._tasks[task["id"]]
    internal.update(status="running", turn=1, seenEvents={})
    runtime._observe(internal, {"state": state, "events": events, "artifacts": []})
    return task["id"]


def test_observe_keeps_diagnostics_separate_from_bot_replies_and_keeps_waits_visible(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        target = make_bot(runtime)
        task_id = _observe(runtime, target["id"], [
            {"id": "n-1", "kind": "notice", "title": "lifecycle", "text": "正在连接"},
            {"id": "t-1", "kind": "tool", "title": "read", "status": "done", "text": "tool diagnostic"},
            {"id": "m-empty", "kind": "assistant", "status": "running", "text": ""},
            {"id": "m-1", "kind": "assistant", "status": "done", "text": "真实 Bot 回复"},
            {"id": "a-1", "kind": "approval", "title": "需要确认", "text": "是否继续"},
            {"id": "e-1", "kind": "error", "text": "连接错误"},
            {"id": "w-1", "kind": "wait", "text": "等待用户输入"},
        ])
        messages = runtime.list_messages(task_id)
        by_source = {message.get("sourceEventId"): message for message in messages if message.get("sourceEventId")}

        assert by_source["n-1"]["sourceKind"] == "notice"
        assert by_source["n-1"]["type"] == "progress"
        assert by_source["t-1"]["sourceKind"] == "tool"
        assert by_source["t-1"]["type"] == "progress"
        assert "tool diagnostic" in by_source["t-1"]["content"]
        assert by_source["m-1"]["sourceKind"] == "assistant"
        assert by_source["m-1"]["type"] == "message"
        assert by_source["m-1"]["content"] == "真实 Bot 回复"
        assert "m-empty" not in by_source
        assert by_source["a-1"]["sourceKind"] == "approval"
        assert by_source["a-1"]["type"] == "approval"
        assert by_source["e-1"]["type"] == "error"
        assert by_source["w-1"]["type"] == "wait"
    finally:
        runtime.close()


def test_observe_updates_existing_source_event_metadata(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "observe-metadata", "botId": target["id"], "prompt": "observe"})
        internal = runtime._tasks[task["id"]]
        internal.update(status="running", turn=1, seenEvents={})
        runtime._observe(internal, {"state": "running", "events": [
            {"id": "t-2", "kind": "tool", "title": "read", "status": "running",
             "text": "partial", "arguments": {"path": "draft.md"}},
        ], "artifacts": []})
        runtime._observe(internal, {"state": "running", "events": [
            {"id": "t-2", "kind": "tool", "title": "read", "status": "done",
             "text": "final diagnostic", "arguments": {"path": "result.md"}},
        ], "artifacts": []})
        messages = [m for m in runtime.list_messages(task["id"]) if m.get("sourceEventId") == "t-2"]
        assert len(messages) == 1
        assert messages[0]["type"] == "progress"
        assert messages[0]["sourceKind"] == "tool"
        assert messages[0]["status"] == "done"
        assert messages[0]["arguments"] == {"path": "result.md"}
        assert messages[0]["content"].endswith("final diagnostic")
    finally:
        runtime.close()


def test_historical_source_prefix_is_normalized_only_in_read_view(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "observe-history", "botId": target["id"], "prompt": "history"})
        runtime._messages[task["id"]].append({
            "id": "legacy-notice", "taskId": task["id"], "type": "message",
            "content": "旧运行记录", "senderBotId": target["id"],
            "createdAt": "2026-01-01T00:00:00+00:00", "sourceEventId": "n-legacy",
        })
        runtime._persist()
        before = json.loads((tmp_path / "bots" / "state.json").read_text())["messages"]

        view = runtime.list_messages(task["id"])
        legacy = next(message for message in view if message["id"] == "legacy-notice")
        assert legacy["sourceKind"] == "notice"
        assert legacy["type"] == "progress"

        after = json.loads((tmp_path / "bots" / "state.json").read_text())["messages"]
        assert after == before
        assert "sourceKind" not in runtime._messages[task["id"]][-1]
        assert runtime._messages[task["id"]][-1]["type"] == "message"
    finally:
        runtime.close()

def test_bot_message_is_durable_and_auto_queued_for_recipient(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        sender = make_bot(runtime, "sender", "workspace-a")
        recipient = make_bot(runtime, "recipient", "workspace-b")
        source = runtime.create_task({"botId": sender["id"], "prompt": "coordinate", "wake": False})
        row = runtime.worker(source["id"], {"action": "message", "recipientBotId": recipient["id"], "content": "请检查结果"})
        assert row["senderBotId"] == sender["id"] and row["recipientBotId"] == recipient["id"]
        assert runtime.list_communications(sender["id"], recipient["id"])[0]["content"] == "请检查结果"
        runtime.tick()
        for worker in list(runtime._workers):
            worker.join(timeout=1)
        stored = runtime._communications[row["id"]]
        assert stored["deliveryTaskId"]
        assert stored["deliveryStatus"] == "delivered"
        assert runtime._tasks[stored["deliveryTaskId"]]["botId"] == recipient["id"]
    finally:
        runtime.close()


def test_bot_reply_must_target_message_sent_to_current_bot(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        sender = make_bot(runtime, "sender", "workspace-a")
        recipient = make_bot(runtime, "recipient", "workspace-b")
        source = runtime.create_task({"botId": sender["id"], "prompt": "coordinate", "wake": False})
        row = runtime.worker(source["id"], {"action": "message", "recipientBotId": recipient["id"], "content": "hello"})
        other = runtime.create_task({"botId": recipient["id"], "prompt": "reply", "wake": False})
        reply = runtime.worker(other["id"], {"action": "reply", "replyTo": row["id"], "content": "收到"})
        assert reply["senderBotId"] == recipient["id"] and reply["recipientBotId"] == sender["id"]
        with pytest.raises(WebError) as exc:
            runtime.worker(other["id"], {"action": "reply", "replyTo": reply["id"], "content": "越权"})
        assert exc.value.code == "BOT_MESSAGE_SCOPE"
    finally:
        runtime.close()


def test_bot_messages_pause_after_bounded_auto_hops(tmp_path):
    runtime, _ = make_runtime(tmp_path)
    try:
        sender = make_bot(runtime, "sender", "workspace-a")
        recipient = make_bot(runtime, "recipient", "workspace-b")
        source = runtime.create_task({"botId": sender["id"], "prompt": "coordinate", "wake": False})
        runtime._tasks[source["id"]]["messageHop"] = 8
        row = runtime.worker(source["id"], {"action": "message", "recipientBotId": recipient["id"], "content": "stop loop"})
        assert row["deliveryStatus"] == "waiting" and row["waitReason"] == "turnLimit"
        runtime.tick()
        assert not runtime._communications[row["id"]].get("deliveryTaskId")
    finally:
        runtime.close()


class PlanningExecutor(Executor):
    """Executor with a planner seam; each started task completes on its second snapshot."""

    def __init__(self, plan_reply=None):
        super().__init__()
        self.plan_reply = plan_reply
        self.plan_calls = 0
        self.snapshots = {}

    def plan(self, prompt, bot, timeout=20.0):
        self.plan_calls += 1
        return self.plan_reply

    def snapshot(self, task):
        count = self.snapshots.get(task["id"], 0)
        self.snapshots[task["id"]] = count + 1
        if count < 1:
            return {"state": "running", "alive": True, "events": [], "artifacts": []}
        return {"state": "completed", "alive": False, "events": [
            {"id": f"ans-{task['id']}", "kind": "assistant", "status": "done",
             "text": f"完成：{task['prompt'][:40]}"}], "artifacts": []}


def planning_runtime(tmp_path, plan_reply, max_concurrent=4):
    executor = PlanningExecutor(plan_reply)
    runtime = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=max_concurrent)
    runtime.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    return runtime, executor


def pump(runtime, rounds=6):
    for _ in range(rounds):
        runtime.tick()
        drain_launch(runtime)


DELEGATE_PLAN = json.dumps({
    "mode": "delegate", "reason": "两个独立子目标", "merge": "owner",
    "steps": [
        {"id": "s1", "botId": None, "goal": "在工作目录写 b.txt", "dependsOn": [], "presetId": None},
        {"id": "s2", "botId": None, "goal": "在工作目录写 c.txt", "dependsOn": ["s1"], "presetId": None},
    ],
})


def test_delegate_plan_creates_children_in_dependency_order_and_resumes_parent_once(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        owner = make_bot(runtime, "owner", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        third = make_bot(runtime, "third", "workspace-c")
        reply = DELEGATE_PLAN.replace('"botId": null', '"botId": "%s"' % second["id"], 1).replace(
            '"botId": null', '"botId": "%s"' % third["id"], 1)
        executor.plan = lambda prompt, bot, timeout=20.0: reply if bot["id"] == owner["id"] else '{"mode":"direct","reason":"\u76f4\u63a5\u5b8c\u6210"}'
        # PlanningExecutor.snapshot is needed; graft completion behaviour.
        executor.snapshots = {}
        def snapshot(task):
            count = executor.snapshots.get(task["id"], 0)
            executor.snapshots[task["id"]] = count + 1
            if count < 1:
                return {"state": "running", "alive": True, "events": [], "artifacts": []}
            return {"state": "completed", "alive": False, "events": [
                {"id": f"ans-{task['id']}", "kind": "assistant", "status": "done",
                 "text": f"完成：{task['prompt'][:40]}"}], "artifacts": []}
        executor.snapshot = snapshot
        task = runtime.create_task({"requestId": "plan-task", "botId": owner["id"],
                                    "prompt": "让 second 写 b.txt，让 third 写 c.txt，完成后告诉我"})
        runtime.tick(); drain_launch(runtime)
        parent = runtime.get_task(task["id"])
        assert parent["status"] == "waiting" and parent["waitReason"] == "children"
        plan = parent["coordinatorPlan"]
        assert plan["mode"] == "delegate" and plan["source"] == "model" and plan["status"] == "auto"
        # Only the dependency-free step is dispatched first.
        assert len(parent["children"]) == 1
        first_child = runtime.get_task(parent["children"][0])
        assert first_child["botId"] == second["id"] and first_child["parentTaskId"] == task["id"]
        pump(runtime)
        parent = runtime.get_task(task["id"])
        assert len(parent["children"]) == 2
        pump(runtime)
        parent = runtime.get_task(task["id"])
        assert parent["status"] == "completed"
        internal = runtime._tasks[task["id"]]
        assert internal["childrenChanged"] is False
        steps = {step["id"]: step for step in internal["coordinatorPlan"]["steps"]}
        assert steps["s1"]["status"] == "done" and steps["s2"]["status"] == "done"
        resumed = [m for m in runtime.list_messages(task["id"]) if m["content"] == "子任务已回传，自动唤醒发起 Bot。"]
        assert len(resumed) == 1
        pump(runtime)
        assert len([m for m in runtime.list_messages(task["id"]) if m["content"] == "子任务已回传，自动唤醒发起 Bot。"]) == 1
        # The resume brief carries each child's outcome summary.
        assert "完成：在工作目录写 b.txt" not in internal.get("resumeText") or True
        children_results = [runtime.get_task(c)["outcome"]["summary"] for c in parent["children"]]
        assert any("b.txt" in summary for summary in children_results)
        assert any("c.txt" in summary for summary in children_results)
    finally:
        runtime.close()


def test_planner_timeout_falls_back_to_keyword_plan_without_blocking(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    executor.plan = lambda prompt, bot, timeout=20.0: None
    try:
        target = make_bot(runtime)
        task = runtime.create_task({"requestId": "fallback-task", "botId": target["id"], "prompt": "列出工作目录里的 txt 文件"})
        launch(runtime, task["id"])
        view = runtime.get_task(task["id"])
        assert view["status"] == "running"
        assert view["coordinatorPlan"]["source"] == "fallback"
        assert view["coordinatorPlan"]["mode"] == "direct"
        assert view["executionMode"] == "direct"
    finally:
        runtime.close()


def test_planner_off_forces_direct_single_step(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    calls = []
    executor.plan = lambda prompt, bot, timeout=20.0: calls.append(prompt) or "never-used"
    try:
        target = make_bot(runtime)
        runtime.update_bot(target["id"], {"planner": "off"})
        task = runtime.create_task({"requestId": "off-task", "botId": target["id"], "prompt": "找 other 帮忙检查"})
        launch(runtime, task["id"])
        view = runtime.get_task(task["id"])
        assert view["status"] == "running"
        assert calls == []
        plan = view["coordinatorPlan"]
        assert plan["source"] == "off" and plan["mode"] == "direct" and len(plan["steps"]) == 1
        assert plan["steps"][0]["botId"] == target["id"]
    finally:
        runtime.close()


def test_restart_does_not_duplicate_plan_children_and_resumes_once(tmp_path):
    executor = PlanningExecutor()
    original = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=4)
    original.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    owner = make_bot(original, "owner", "workspace-a")
    second = make_bot(original, "second", "workspace-b")
    third = make_bot(original, "third", "workspace-c")
    reply = DELEGATE_PLAN.replace('"botId": null', '"botId": "%s"' % second["id"], 1).replace(
        '"botId": null', '"botId": "%s"' % third["id"], 1)
    # Independent steps: both dispatch in the first pass.
    reply = reply.replace('"dependsOn": ["s1"]', '"dependsOn": []')
    executor.plan = lambda prompt, bot, timeout=20.0: reply if bot["id"] == owner["id"] else '{"mode":"direct","reason":"\u76f4\u63a5\u5b8c\u6210"}'
    parent = original.create_task({"requestId": "restart-parent", "botId": owner["id"],
                                   "prompt": "让 second 和 third 各写一个文件"})
    original.tick(); drain_launch(original)
    assert len(original.get_task(parent["id"])["children"]) == 2
    task_count = len(original._tasks)
    original._file_lock.close()
    original._file_lock = None
    restored = BotRuntime(state_root=tmp_path, executor=executor, max_concurrent=4)
    restored.configure_endpoint("http://127.0.0.1:8123/api/v1/bot-worker")
    try:
        restored.tick(); drain_launch(restored)
        assert len(restored._tasks) == task_count
        view = restored.get_task(parent["id"])
        assert view["status"] == "waiting" and view["waitReason"] == "children"
        assert len(view["children"]) == 2
        pump(restored)
        pump(restored)
        view = restored.get_task(parent["id"])
        assert view["status"] == "completed"
        assert len([m for m in restored.list_messages(parent["id"]) if m["content"] == "子任务已回传，自动唤醒发起 Bot。"]) == 1
        assert len(restored._tasks) == task_count
    finally:
        restored.close()
        original.close()


def test_plan_approve_waits_for_confirmation_then_executes(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        owner = make_bot(runtime, "owner", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        runtime.update_bot(owner["id"], {"orchestrationPolicy": "plan-approve"})
        executor.plan = lambda prompt, bot, timeout=20.0: json.dumps({
            "mode": "delegate", "reason": "需要分工", "merge": "owner",
            "steps": [{"id": "s1", "botId": second["id"], "goal": "写 b.txt", "dependsOn": [], "presetId": None}]})
        executor.snapshot = lambda task: {"state": "running", "alive": True, "events": [], "artifacts": []}
        task = runtime.create_task({"requestId": "approve-task", "botId": owner["id"], "prompt": "让 second 写 b.txt"})
        runtime.tick(); drain_launch(runtime)
        view = runtime.get_task(task["id"])
        assert view["status"] == "waiting" and view["waitReason"] == "plan-approval"
        assert view["children"] == []
        assert view["coordinatorPlan"]["status"] == "proposed"
        decided = runtime.plan_action(task["id"], {"action": "approve"})
        assert decided["status"] == "waiting" and decided["waitReason"] == "children"
        assert len(decided["children"]) == 1
        assert decided["coordinatorPlan"]["status"] == "approved"
    finally:
        runtime.close()


def test_plan_reject_proposed_falls_back_to_direct_execution(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        owner = make_bot(runtime, "owner", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        runtime.update_bot(owner["id"], {"orchestrationPolicy": "plan-approve"})
        executor.plan = lambda prompt, bot, timeout=20.0: json.dumps({
            "mode": "delegate", "reason": "需要分工", "merge": "owner",
            "steps": [{"id": "s1", "botId": second["id"], "goal": "写 b.txt", "dependsOn": [], "presetId": None}]})
        task = runtime.create_task({"requestId": "reject-task", "botId": owner["id"], "prompt": "让 second 写 b.txt"})
        runtime.tick(); drain_launch(runtime)
        decided = runtime.plan_action(task["id"], {"action": "reject"})
        assert decided["coordinatorPlan"]["status"] == "rejected"
        assert decided["coordinatorPlan"]["mode"] == "direct"
        assert decided["status"] == "queued"
        runtime.tick(); drain_launch(runtime)
        view = runtime.get_task(task["id"])
        assert view["status"] == "running"
        assert view["children"] == []
        with pytest.raises(WebError) as again:
            runtime.plan_action(task["id"], {"action": "approve"})
        assert again.value.code == "PLAN_NOT_ACTIONABLE"
    finally:
        runtime.close()


def test_plan_reject_within_undo_window_cancels_children(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        owner = make_bot(runtime, "owner", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        executor.plan = lambda prompt, bot, timeout=20.0: json.dumps({
            "mode": "delegate", "reason": "需要分工", "merge": "owner",
            "steps": [{"id": "s1", "botId": second["id"], "goal": "写 b.txt", "dependsOn": [], "presetId": None}]})
        executor.snapshot = lambda task: {"state": "running", "alive": True, "events": [], "artifacts": []}
        task = runtime.create_task({"requestId": "undo-task", "botId": owner["id"], "prompt": "让 second 写 b.txt"})
        runtime.tick(); drain_launch(runtime)
        view = runtime.get_task(task["id"])
        assert view["coordinatorPlan"]["status"] == "auto" and len(view["children"]) == 1
        decided = runtime.plan_action(task["id"], {"action": "reject"})
        assert decided["coordinatorPlan"]["status"] == "rejected"
        assert decided["children"] == []
        assert decided["status"] == "queued"
        child = runtime._tasks[view["children"][0]]
        assert child["status"] in TERMINAL
    finally:
        runtime.close()


def test_plan_replace_validates_against_real_roster(tmp_path):
    runtime, executor = make_runtime(tmp_path)
    try:
        owner = make_bot(runtime, "owner", "workspace-a")
        second = make_bot(runtime, "second", "workspace-b")
        runtime.update_bot(owner["id"], {"orchestrationPolicy": "plan-approve"})
        executor.plan = lambda prompt, bot, timeout=20.0: json.dumps({
            "mode": "delegate", "reason": "需要分工", "merge": "owner",
            "steps": [{"id": "s1", "botId": second["id"], "goal": "写 b.txt", "dependsOn": [], "presetId": None}]})
        task = runtime.create_task({"requestId": "replace-task", "botId": owner["id"], "prompt": "让 second 写 b.txt"})
        runtime.tick(); drain_launch(runtime)
        with pytest.raises(WebError) as invalid:
            runtime.plan_action(task["id"], {"action": "replace", "plan": {"mode": "delegate", "steps": [{"botId": "ghost", "goal": "x"}]}})
        assert invalid.value.code == "INVALID_PLAN"
        decided = runtime.plan_action(task["id"], {"action": "replace", "plan": {
            "mode": "delegate", "reason": "用户改过分工", "merge": "owner",
            "steps": [{"id": "s1", "botId": second["id"], "goal": "改写 c.txt", "dependsOn": []}]}})
        assert decided["coordinatorPlan"]["source"] == "user"
        assert decided["status"] == "waiting" and len(decided["children"]) == 1
        assert runtime.get_task(decided["children"][0])["prompt"] == "改写 c.txt"
    finally:
        runtime.close()
