from datetime import datetime, timedelta, timezone
import json
import time

import pytest

from mms_web.bots import (BotRuntime, collaboration_requested, is_trivial_result,
                        looks_like_question, parse_outcome, parse_wait_text)
from mms_web.errors import WebError


class FakeExecutor:
    def __init__(self):
        self.starts = []
        self.cancels = []
        self.sessions = {}

    def available(self):
        return True

    def validate(self, bot):
        return {"model": "fake-model", "capabilities": ["computer", "dispatch"]}

    def start(self, task, bot, context_path):
        session_id = f"session-{len(self.starts) + 1}"
        self.starts.append((task["id"], bot["id"], str(context_path)))
        self.sessions[session_id] = {"taskId": task["id"]}
        return {"sessionId": session_id, "baseline": {}, "artifactBaseline": {}, "model": "fake-model"}

    def snapshot(self, task):
        return {"state": "completed", "alive": False, "events": [{
            "id": f"answer-{task['id']}", "kind": "assistant", "status": "done",
            "text": f"完成 {task['prompt']}",
        }], "artifacts": []}

    def cancel(self, task):
        self.cancels.append(task["id"])

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


class UnavailableExecutor:
    def available(self):
        return False

    def validate(self, bot):
        raise WebError("BOT_EXECUTOR_UNAVAILABLE", "Pi 或 MMS 模型尚未连接。", 409)


def runtime(tmp_path, executor=None, *, max_concurrent=3):
    rt = BotRuntime(state_root=tmp_path, executor=executor or FakeExecutor(), max_concurrent=max_concurrent)
    rt.configure_endpoint("http://127.0.0.1:8765/api/v1/bot-worker")
    return rt


def bot(rt, name="Bot", workspace="ws-1", wake=True):
    return rt.create_bot({"name": name, "description": "test", "systemPrompt": "", "workspaceId": workspace,
                          "presetId": "pi:fake", "wakeEnabled": wake})


def drain_launch(rt):
    for worker in list(rt._workers):
        worker.join(timeout=1)


def complete_one(rt, task_id):
    for _ in range(10):
        rt.tick()
        drain_launch(rt)
        if rt.get_task(task_id)["status"] == "completed":
            return rt.get_task(task_id)
        time.sleep(0.005)
    return rt.get_task(task_id)


def test_executor_is_required_and_unavailable_does_not_simulate(tmp_path):
    rt = runtime(tmp_path, UnavailableExecutor())
    try:
        assert rt.capabilities()["available"] is False
        with pytest.raises(WebError) as failure:
            bot(rt)
        assert failure.value.code == "BOT_EXECUTOR_UNAVAILABLE"
    finally:
        rt.close()


def test_bot_defaults_to_direct_first_and_tasks_do_not_orchestrate_implicitly(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt, "direct worker")
        task = rt.create_task({"requestId": "direct-default", "botId": worker["id"], "prompt": "整理这份结果并回报"})
        assert worker["orchestrationPolicy"] == "direct-first"
        assert task["executionMode"] == "direct"
        assert task["collaborationRequested"] is False
    finally:
        rt.close()


def test_bot_avatar_preset_and_color_round_trip(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = rt.create_bot({
            "name": "像素同事",
            "description": "test",
            "systemPrompt": "",
            "workspaceId": "ws-1",
            "presetId": "pi:fake",
            "avatarId": "cat",
            "avatarColor": "#73dfc7",
        })
        assert worker["avatarId"] == "cat"
        assert worker["avatarColor"] == "#73dfc7"
        updated = rt.update_bot(worker["id"], {"avatarId": "rocket", "avatarColor": "#ff9f91"})
        assert updated["avatarId"] == "rocket"
        assert updated["avatarColor"] == "#ff9f91"
    finally:
        rt.close()


def test_bot_accepts_geometric_avatar_ids(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = rt.create_bot({
            "name": "几何同事",
            "description": "test",
            "systemPrompt": "",
            "workspaceId": "ws-1",
            "presetId": "pi:fake",
            "avatarId": "diamond",
        })
        assert worker["avatarId"] == "diamond"
    finally:
        rt.close()


def test_bot_can_be_created_without_user_selected_preset(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = rt.create_bot({"name": "新 Bot", "description": "", "systemPrompt": "", "wakeEnabled": True})
        assert worker["presetId"] == ""
        assert worker["avatarId"]
        assert worker["avatarColor"]
    finally:
        rt.close()


def test_delete_bot_removes_identity_tasks_memory_and_is_idempotent(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt, "待删除 Bot")
        rt.memory.remember(worker["id"], "只属于这个 Bot 的偏好")
        task = rt.create_task({"requestId": "delete-task", "botId": worker["id"], "prompt": "稍后执行"})
        result = rt.delete_bot(worker["id"])
        assert result["deleted"] is True and task["id"] in result["taskIds"]
        assert rt.list_bots() == []
        assert not (tmp_path / "bots" / "memory" / worker["id"]).exists()
        assert rt.delete_bot(worker["id"])["deleted"] is True
    finally:
        rt.close()


def test_delete_bot_rejects_running_task(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt, "执行中 Bot")
        task = rt.create_task({"requestId": "busy-delete", "botId": worker["id"], "prompt": "执行"})
        task["status"] = "running"
        rt._tasks[task["id"]]["status"] = "running"
        with pytest.raises(WebError) as failure:
            rt.delete_bot(worker["id"])
        assert failure.value.code == "BOT_BUSY"
    finally:
        rt.close()


def test_collaboration_is_only_marked_when_user_explicitly_requests_it(tmp_path):
    assert collaboration_requested("先整理结果并回报") is False
    assert collaboration_requested("请找 QA 并行检查") is True


def test_parse_outcome_preserves_raw_and_extracts_v2_sections():
    outcome = parse_outcome("## 结论\n已完成\n\n## 证据\n- shot.png\n\n## 下一步\n无需")
    assert outcome["summary"] == "已完成"
    assert outcome["evidence"] == "- shot.png"
    assert outcome["next"] == "无需"
    assert outcome["raw"].startswith("## 结论")


def test_auto_route_prefers_explicit_bot_name_over_metadata_score(tmp_path):
    rt = runtime(tmp_path)
    try:
        general = bot(rt, "协调员", wake=True)
        specialist = bot(rt, "网页验证员", wake=True)
        result = rt.auto_task({"prompt": "请让网页验证员检查登录页面"})
        assert result["routing"] == "explicit-bot-name"
        assert result["bot"]["id"] == specialist["id"]
        assert result["task"]["botId"] == specialist["id"]
        assert general["id"] != specialist["id"]
    finally:
        rt.close()


def test_request_id_replay_does_not_create_duplicate_bot_or_task(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        first = rt.create_bot({"requestId": "bot-create-1", "name": "重复 Bot", "workspaceId": "ws-1", "presetId": "pi:fake", "wakeEnabled": True})
        second = rt.create_bot({"requestId": "bot-create-1", "name": "重复 Bot", "workspaceId": "ws-1", "presetId": "pi:fake", "wakeEnabled": True})
        assert first["id"] == second["id"] and len(rt.list_bots()) == 1
        task1 = rt.create_task({"requestId": "task-1", "botId": first["id"], "prompt": "检查"})
        task2 = rt.create_task({"requestId": "task-1", "botId": first["id"], "prompt": "检查"})
        assert task1["id"] == task2["id"] and len(rt.list_tasks()) == 1
        with pytest.raises(WebError) as conflict:
            rt.create_task({"requestId": "task-1", "botId": first["id"], "prompt": "另一件事"})
        assert conflict.value.code == "REQUEST_ID_CONFLICT"
    finally:
        rt.close()


def test_distinct_workspaces_can_run_in_parallel_but_same_bot_is_serial(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor, max_concurrent=3)
    try:
        one = bot(rt, "A", "workspace-a")
        two = bot(rt, "B", "workspace-b")
        first = rt.create_task({"requestId": "a", "botId": one["id"], "prompt": "a"})
        second = rt.create_task({"requestId": "b", "botId": two["id"], "prompt": "b"})
        rt.tick(); drain_launch(rt)
        assert {item[0] for item in executor.starts} == {first["id"], second["id"]}

        same_one = rt.create_task({"requestId": "a2", "botId": one["id"], "prompt": "a2"})
        same_two = rt.create_task({"requestId": "a3", "botId": one["id"], "prompt": "a3"})
        rt.tick(); drain_launch(rt)
        assert [item[0] for item in executor.starts].count(same_one["id"]) == 1
        assert [item[0] for item in executor.starts].count(same_two["id"]) == 0
    finally:
        rt.close()


def test_schedule_wake_respects_bot_wake_enabled_and_advances_without_it(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        asleep = bot(rt, "手动 Bot", "ws-a", wake=False)
        awake = bot(rt, "自动 Bot", "ws-b", wake=True)
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rule = {"kind": "interval", "everySeconds": 300}
        blocked = rt.create_schedule(asleep["id"], {"prompt": "off", "rule": rule})
        ready = rt.create_schedule(awake["id"], {"prompt": "on", "rule": rule})
        rt._schedules[blocked["id"]]["nextRunAt"] = past
        rt._schedules[ready["id"]]["nextRunAt"] = past
        rt.tick(); drain_launch(rt)
        # The Bot-level switch blocks the run but never accumulates runs.
        assert rt.list_tasks(bot_id=asleep["id"]) == []
        assert rt.list_schedules(asleep["id"])[0]["nextRunAt"] > datetime.now(timezone.utc).isoformat()
        fired = rt.list_tasks(bot_id=awake["id"])
        assert len(fired) == 1 and fired[0]["scheduleId"] == ready["id"]
        assert any(item[0] == fired[0]["id"] for item in executor.starts)
    finally:
        rt.close()


def test_interval_schedule_fires_once_per_due_time_without_drift(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "周期 Bot", "ws-interval")
        schedule = rt.create_schedule(worker["id"], {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": 300}})
        first_due = schedule["nextRunAt"]
        rt._schedules[schedule["id"]]["nextRunAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rt.tick(); drain_launch(rt)
        after_first = rt.list_schedules(worker["id"])[0]
        assert len(after_first["recentTaskIds"]) == 1
        # The next due time keeps the original cadence (previous + interval),
        # not "now + interval": a late tick must not accumulate drift.
        assert after_first["nextRunAt"] != first_due
        rt._schedules[schedule["id"]]["nextRunAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rt.tick(); drain_launch(rt)
        tasks = rt.list_tasks(bot_id=worker["id"])
        assert len(tasks) == 2 and len({item["id"] for item in tasks}) == 2
        assert all(item["scheduleId"] == schedule["id"] for item in tasks)
    finally:
        rt.close()


def test_child_result_wakes_parent_and_acceptance_is_separate(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        parent_bot = bot(rt, "总控", "ws-parent")
        child_bot = bot(rt, "浏览器", "ws-child")
        parent = rt.create_task({"requestId": "parent", "botId": parent_bot["id"], "prompt": "总任务"})
        complete_one(rt, parent["id"])
        child = rt.create_task({"requestId": "child", "botId": child_bot["id"], "prompt": "子任务", "parentTaskId": parent["id"]})
        assert rt.get_task(parent["id"])["status"] == "waiting"
        complete_one(rt, child["id"])
        for _ in range(10):
            rt.tick(); drain_launch(rt)
            if rt.get_task(parent["id"])["status"] == "completed":
                break
        finished = rt.get_task(parent["id"])
        assert finished["status"] == "completed" and finished["acceptedAt"] is None
        assert any(message.get("childTaskId") == child["id"] for message in rt.list_messages(parent["id"]))
        accepted = rt.accept_task(parent["id"])
        assert accepted["status"] == "completed" and accepted["acceptedAt"]
    finally:
        rt.close()


def test_restart_marks_running_interrupted_without_replay_and_keeps_schedules(tmp_path):
    first_executor = FakeExecutor()
    first = runtime(tmp_path, first_executor)
    running_bot = bot(first, "运行中", "ws-running")
    schedule_bot = bot(first, "计划", "ws-scheduled")
    running = first.create_task({"requestId": "running", "botId": running_bot["id"], "prompt": "不会重跑"})
    schedule = first.create_schedule(schedule_bot["id"], {"prompt": "重启恢复", "rule": {"kind": "interval", "everySeconds": 300}})
    first.tick(); drain_launch(first)
    assert first.get_task(running["id"])["status"] == "running"
    first.close()

    # Simulate the scheduler reaching the persisted due time while Pilot was
    # offline; the schedule fires once and the running task is not replayed.
    state_path = tmp_path / "bots" / "state.json"
    record = json.loads(state_path.read_text())
    record["schedules"][schedule["id"]]["nextRunAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    state_path.write_text(json.dumps(record))

    second_executor = FakeExecutor()
    second = runtime(tmp_path, second_executor)
    try:
        assert second.get_task(running["id"])["status"] == "interrupted"
        second.tick(); drain_launch(second)
        assert not any(item[0] == running["id"] for item in second_executor.starts)
        fired = second.list_tasks(bot_id=schedule_bot["id"])
        assert len(fired) == 1 and fired[0]["scheduleId"] == schedule["id"]
        assert any(item[0] == fired[0]["id"] for item in second_executor.starts)
    finally:
        second.close()


def test_cancel_does_not_change_completed_and_worker_scope_rejects_cycles(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        first_bot = bot(rt, "总控", "ws-1")
        second_bot = bot(rt, "子 Bot", "ws-2")
        task = rt.create_task({"requestId": "done", "botId": first_bot["id"], "prompt": "完成"})
        complete_one(rt, task["id"])
        assert rt.cancel_task(task["id"])["status"] == "completed"
        child = rt.create_task({"requestId": "child-cycle", "botId": second_bot["id"], "prompt": "子", "parentTaskId": task["id"]})
        with pytest.raises(WebError) as cycle:
            rt.worker(child["id"], {"action": "dispatch", "botId": second_bot["id"], "prompt": "循环"})
        assert cycle.value.code == "BOT_DISPATCH_CYCLE"
        with pytest.raises(WebError) as scope:
            rt.authorize_worker("wrong-token")
        assert scope.value.code == "BOT_WORKER_UNAUTHORIZED"
    finally:
        rt.close()


def test_artifact_content_rejects_bare_path_outside_private_screenshots(tmp_path):
    class UnsafeComputer:
        def capture(self, task_id, url=None):
            return {"name": "bad.png", "path": "/etc/passwd", "mimeType": "image/png", "kind": "screenshot", "sha256": "0" * 64}

    executor = FakeExecutor()
    rt = BotRuntime(state_root=tmp_path, executor=executor, computer=UnsafeComputer())
    try:
        target = bot(rt)
        task = rt.create_task({"requestId": "artifact", "botId": target["id"], "prompt": "截图"})
        artifact = rt.screenshot(task["id"])
        with pytest.raises(WebError) as failure:
            rt.artifact_content(task["id"], artifact["id"])
        assert failure.value.code == "ARTIFACT_FORBIDDEN"
    finally:
        rt.close()


@pytest.mark.parametrize("text", [
    "你希望我优先处理哪一项？",
    "需要我把结果发到邮箱吗",
    "请确认是否继续",
    "报告里要包含哪些章节",
    "下一步做什么",
    "是否需要我重跑一次",
])
def test_looks_like_question_accepts_real_questions(text):
    assert looks_like_question(text) is True


@pytest.mark.parametrize("text", [
    "等待子任务或用户",
    "继续等待用户或后续指令。",
    "已确认收到并让我候着，无需再回复。",
    "本轮没有任何文件改动，继续挂起。",
    "已完成，结果在工作目录。",
    "",
])
def test_looks_like_question_rejects_statements(text):
    assert looks_like_question(text) is False


@pytest.mark.parametrize("text", [
    "收到",
    "明白，先候着",
    "已发送给相关同事，沟通完毕。",
    "无待办，本轮先到这里。",
])
def test_is_trivial_result_marks_short_or_acknowledged_text(text):
    assert is_trivial_result(text) is True


@pytest.mark.parametrize("text", [
    '本次核对覆盖了全部三类记录，逐条比对了 2026-09 的变更，结论是无需回滚；相关文件与截图已随成果提交，后续只需按既定节奏观察一天再复核一次。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。',
    '巡检完成：三个站点的主流程都可达，延迟分别落在预期区间；异常日志里只有一条历史噪声，已记录并标注来源，无需在今天处理。为了让下一位同事接手顺利，我把每个站点的入口、账号位置和最近的变更都写进了同一份记录。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。',
    '整理结果：需求清单拆成五个可执行项，其中四项可直接开工；剩下的一项依赖账号权限，已标注负责人和下一步的确认方式。另外把风险项按影响面排序，最高的一项建议在本周内先做一次小范围验证，再决定是否全量。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。',
    '对账完成：两份导出文件的差异集中在两条历史记录，均已核对来源，没有出现新的不一致；相关证据文件已经随成果一起提交备查。如果下周还有新的导出，可以直接用同一套流程再跑一遍，不需要重新配置。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。',
])


def test_is_trivial_result_keeps_real_work(text):
    assert is_trivial_result(text) is False


def test_parse_wait_text_splits_question_and_quick_options():
    question, options = parse_wait_text("请确认发布范围？\n选项：只同步 网文1 | 两个站点都同步")
    assert question == "请确认发布范围？"
    assert options == ["只同步 网文1", "两个站点都同步"]


def finish_task(rt, bot_id, message, prompt="任务", **task_fields):
    task = rt.create_task({"botId": bot_id, "prompt": prompt})
    rt._tasks[task["id"]].update(status="running", **task_fields)
    rt._finish(rt._tasks[task["id"]], "completed", message)
    return [note for note in rt.memory.get(bot_id)["notes"] if note["kind"] == "task"]


def test_memory_skips_greetings_and_acknowledgements(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt)
        notes = finish_task(rt, worker["id"], "收到，好的。", prompt="跟大总管打招呼")
        assert notes == []
    finally:
        rt.close()


class ScriptedPlanExecutor(FakeExecutor):
    """Planner seam plus per-task scripted outcomes."""

    def __init__(self, plan_reply=None):
        super().__init__()
        self.plan_reply = plan_reply
        self.outcomes = {}

    def plan(self, prompt, bot, timeout=20.0):
        return self.plan_reply

    def snapshot(self, task):
        outcome = self.outcomes.get(task["id"])
        if outcome == "failed":
            return {"state": "error", "alive": False, "events": [
                {"id": f"err-{task['id']}", "kind": "error", "status": "error", "text": "执行失败"}], "artifacts": []}
        if outcome == "completed" or outcome is None and task["id"] in self.outcomes:
            return {"state": "completed", "alive": False, "events": [
                {"id": f"answer-{task['id']}", "kind": "assistant", "status": "done",
                 "text": f"完成 {task['prompt']}"}], "artifacts": []}
        return {"state": "running", "alive": True, "events": [], "artifacts": []}


def pump_runtime(rt, rounds=6):
    for _ in range(rounds):
        rt.tick()
        drain_launch(rt)


def test_plan_action_rejects_unknown_action_and_direct_plan(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt, "worker")
        task = rt.create_task({"requestId": "plan-action-guard", "botId": worker["id"], "prompt": "整理文件"})
        complete_one(rt, task["id"])
        with pytest.raises(WebError) as bad:
            rt.plan_action(task["id"], {"action": "explode"})
        assert bad.value.status == 400
        # A direct plan has no actionable delegate steps.
        with pytest.raises(WebError) as not_actionable:
            rt.plan_action(task["id"], {"action": "retry-step", "stepId": "s1"})
        assert not_actionable.value.status == 409
    finally:
        rt.close()


def test_memory_keeps_a_structured_conclusion(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt)
        notes = finish_task(rt, worker["id"], "# 结论\n区域 A 的发布状态已确认。", prompt="检查发布状态")
        assert len(notes) == 1
    finally:
        rt.close()


def test_memory_keeps_a_task_with_artifacts(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt)
        task = rt.create_task({"botId": worker["id"], "prompt": "写文件"})
        rt._tasks[task["id"]]["status"] = "running"
        rt._artifacts[task["id"]].append({"id": "artifact_1", "name": "b.txt", "kind": "file"})
        rt._finish(rt._tasks[task["id"]], "completed", "好了。")
        assert len([n for n in rt.memory.get(worker["id"])["notes"] if n["kind"] == "task"]) == 1
    finally:
        rt.close()


def test_memory_keeps_a_long_non_trivial_result(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt)
        message = '本次核对覆盖了全部三类记录，逐条比对了 2026-09 的变更，结论是无需回滚；相关文件与截图已随成果提交，后续只需按既定节奏观察一天再复核一次。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。相关记录和证据都已放在同一份成果里，方便后续核对与交接。'
        notes = finish_task(rt, worker["id"], message, prompt="核对记录")
        assert len(notes) == 1
    finally:
        rt.close()


def test_memory_skips_pure_peer_message_tasks(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt)
        message = ("调度员发来一条问候，我回复了当前进度；本轮没有任何文件改动，"
                   "也没有新的产物或结论，继续等待后续消息即可。")
        notes = finish_task(rt, worker["id"], message, prompt="处理同事消息",
                            deliveryMessageIds=["comm_1"])
        assert notes == []
    finally:
        rt.close()


def test_retry_step_requires_failed_step_and_skip_step_unblocks_dependents(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor, max_concurrent=4)
    try:
        owner = bot(rt, "总控", "ws-owner")
        writer = bot(rt, "写手", "ws-writer")
        checker = bot(rt, "检查员", "ws-checker")
        executor.plan_reply = json.dumps({
            "mode": "delegate", "reason": "两步", "merge": "owner",
            "steps": [{"id": "s1", "botId": writer["id"], "goal": "写 b 文件", "dependsOn": [], "onFailure": "abort"},
                      {"id": "s2", "botId": checker["id"], "goal": "核对 b 文件", "dependsOn": ["s1"], "onFailure": "abort"}]})
        task = rt.create_task({"requestId": "plan-step-actions", "botId": owner["id"], "prompt": "让写手和检查员各做一步"})
        rt.tick(); drain_launch(rt)
        parent = rt.get_task(task["id"])
        assert len(parent["children"]) == 1  # s2 waits on s1
        # retry-step on a non-failed step returns 4xx.
        with pytest.raises(WebError) as wrong:
            rt.plan_action(task["id"], {"action": "retry-step", "stepId": "s1"})
        assert 400 <= wrong.value.status < 500
        first_child = parent["children"][0]
        executor.outcomes[first_child] = "failed"
        pump_runtime(rt)
        parent = rt.get_task(task["id"])
        assert parent["coordinatorPlan"]["status"] == "failed"
        steps = {step["id"]: step for step in parent["coordinatorPlan"]["steps"]}
        assert steps["s1"]["status"] == "failed" and steps["s2"]["status"] == "skipped"
        # skip-step on the failed step lets the plan settle instead of retrying.
        executor.outcomes[task["id"]] = "completed"
        decided = rt.plan_action(task["id"], {"action": "skip-step", "stepId": "s1"})
        assert decided["coordinatorPlan"]["steps"][0]["status"] == "skipped"
        pump_runtime(rt)
        parent = rt.get_task(task["id"])
        assert parent["status"] == "completed"
        assert parent["coordinatorPlan"]["status"] == "done"
        assert len(parent["childResults"]) == 2
    finally:
        rt.close()


@pytest.mark.parametrize("text", [
    # 问题在开头、解释在后面：旧实现只看整段末尾 60 字，会漏判。
    "报告里要包含哪些章节\n我这边已经把环境准备好了，草稿也写完了一版，随时可以按你定下来的方向继续往下做，本轮不会再额外改动任何文件，结果都留在工作目录里，等你看完再说下一步。",
    "是否需要我重跑一次。我这边已经把环境准备好了，草稿也写完了一版，随时可以按你定下来的方向继续往下做，本轮不会再额外改动任何文件，结果都留在工作目录里，等你看完再说下一步。",
    "请确认同步范围\n\n我这边已经把环境准备好了，草稿也写完了一版，随时可以按你定下来的方向继续往下做，本轮不会再额外改动任何文件，结果都留在工作目录里，等你看完再说下一步。",
])
def test_looks_like_question_scans_the_whole_text(text):
    assert looks_like_question(text) is True


@pytest.mark.parametrize("text", [
    "我先按摘要写一版。等你定了再补。已完成，结果在工作目录。",
    "本轮没有任何文件改动，继续挂起。已确认收到并让我候着。",
])
def test_looks_like_question_still_rejects_multi_sentence_statements(text):
    assert looks_like_question(text) is False


def test_retry_step_runs_when_its_prerequisite_was_skipped(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor, max_concurrent=4)
    try:
        owner = bot(rt, "总控", "ws-owner")
        writer = bot(rt, "写手", "ws-writer")
        checker = bot(rt, "检查员", "ws-checker")
        executor.plan_reply = json.dumps({
            "mode": "delegate", "reason": "两步", "merge": "owner",
            "steps": [{"id": "s1", "botId": writer["id"], "goal": "写 b 文件", "dependsOn": [], "onFailure": "skip"},
                      {"id": "s2", "botId": checker["id"], "goal": "核对 b 文件", "dependsOn": ["s1"], "onFailure": "retry"}]})
        task = rt.create_task({"requestId": "skip-dep", "botId": owner["id"], "prompt": "让写手和检查员各做一步"})
        rt.tick(); drain_launch(rt)

        # 一个跳过的前置 + 一个失败的后继：持久化的计划可以是这个形状
        # （例如用户先跳过前置、后继在更早的一轮已经失败）。
        plan = rt._tasks[task["id"]]["coordinatorPlan"]
        steps = {step["id"]: step for step in plan["steps"]}
        steps["s1"].update(status="skipped", result={"summary": "用户跳过了这个步骤。"}, policyApplied=True)
        steps["s2"].update(status="failed", error="核对失败", taskId=None)
        plan["status"] = "failed"

        after = rt.plan_action(task["id"], {"action": "retry-step", "stepId": "s2"})
        retried = {step["id"]: step for step in after["coordinatorPlan"]["steps"]}["s2"]
        # 前置是 skipped 也算已结算：这一步必须真的派发出去，而不是卡在 ready。
        assert retried["status"] == "running", retried
        assert retried["taskId"]
    finally:
        rt.close()


def test_a_direct_plan_marks_its_only_step_done_when_the_task_finishes(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "独立工")
        done = rt.create_task({"botId": worker["id"], "prompt": "用三句话解释什么是 git rebase"})
        rt.tick(); drain_launch(rt)
        executor.outcomes[done["id"]] = "completed"
        pump_runtime(rt)
        view = rt.get_task(done["id"])
        assert view["status"] == "completed"
        assert view["coordinatorPlan"]["mode"] == "direct"
        # 这一步是 Bot 自己做的，没有别的地方会把它挪出 pending。
        assert view["coordinatorPlan"]["steps"][0]["status"] == "done"

        failed = rt.create_task({"botId": worker["id"], "prompt": "列出当前目录的 txt 文件"})
        rt.tick(); drain_launch(rt)
        executor.outcomes[failed["id"]] = "failed"
        pump_runtime(rt)
        view = rt.get_task(failed["id"])
        assert view["status"] == "failed"
        assert view["coordinatorPlan"]["mode"] == "direct"
        assert view["coordinatorPlan"]["steps"][0]["status"] == "failed"
    finally:
        rt.close()


def test_overlap_skip_and_queue_decide_whether_a_due_run_creates_a_task(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "重叠 Bot", "ws-overlap")
        running = rt.create_task({"requestId": "long-run", "botId": worker["id"], "prompt": "长任务"})
        rt._tasks[running["id"]].update(status="running", sessionId="session-long")
        skip = rt.create_schedule(worker["id"], {"prompt": "跳过我这轮", "rule": {"kind": "interval", "everySeconds": 300}})
        queue = rt.create_schedule(worker["id"], {"prompt": "排队执行", "rule": {"kind": "interval", "everySeconds": 300},
                                                  "overlapPolicy": "queue"})
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rt._schedules[skip["id"]].update(nextRunAt=past, lastTaskId=running["id"])
        rt._schedules[queue["id"]]["nextRunAt"] = past
        rt.tick(); drain_launch(rt)

        tasks = rt.list_tasks(bot_id=worker["id"])
        assert [task["prompt"] for task in tasks] == ["排队执行", "长任务"]
        queued = tasks[0]
        assert queued["status"] == "queued" and queued["scheduleId"] == queue["id"]

        skipped = rt._schedules[skip["id"]]
        assert skipped["lastSkip"]["reason"] == "busy" and skipped["nextRunAt"] > past
        assert any("上一轮仍在运行" in message["content"] for message in rt.list_messages(running["id"]))
    finally:
        rt.close()


def test_scheduled_run_notifies_with_schedule_id(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "通知 Bot", "ws-notify")
        schedule = rt.create_schedule(worker["id"], {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": 300}})
        rt._schedules[schedule["id"]]["nextRunAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rt.tick(); drain_launch(rt)
        assert rt.get_task(rt.list_tasks(bot_id=worker["id"])[0]["id"])["status"] == "running"
        rt.tick()
        events = rt.list_notifications()["events"]
        assert events and events[-1]["type"] == "task.completed"
        assert events[-1]["scheduleId"] == schedule["id"]
        assert events[-1]["taskId"] == rt.list_tasks(bot_id=worker["id"])[0]["id"]
    finally:
        rt.close()


def test_missed_periods_are_skipped_without_a_backlog(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "错过 Bot", "ws-missed")
        schedule = rt.create_schedule(worker["id"], {"prompt": "每三小时", "rule": {"kind": "interval", "everySeconds": 10800}})
        three_days = datetime.now(timezone.utc) - timedelta(days=3)
        rt._schedules[schedule["id"]]["nextRunAt"] = three_days.isoformat()
        rt.tick(); drain_launch(rt)
        assert rt.list_tasks(bot_id=worker["id"]) == []
        updated = rt.list_schedules(worker["id"])[0]
        assert updated["lastSkip"]["skipped"] == 24
        assert updated["nextRunAt"] > datetime.now(timezone.utc).isoformat()
    finally:
        rt.close()


def test_create_task_with_run_at_returns_a_once_schedule_instead(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "一次性 Bot")
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        created = rt.create_task({"requestId": "once-1", "botId": worker["id"], "prompt": "提醒我", "runAt": run_at})
        assert created["kind"] == "schedule" and created["rule"] == {"kind": "once", "at": run_at}
        assert rt.list_tasks(bot_id=worker["id"]) == []
        replay = rt.create_task({"requestId": "once-1", "botId": worker["id"], "prompt": "提醒我", "runAt": run_at})
        assert replay["kind"] == "schedule" and replay["id"] == created["id"] and len(rt.list_schedules(worker["id"])) == 1

        child = rt.create_task({"requestId": "child-1", "botId": worker["id"], "prompt": "父任务"})
        with pytest.raises(WebError) as failure:
            rt.create_task({"botId": worker["id"], "prompt": "定时子任务", "parentTaskId": child["id"], "runAt": run_at})
        assert failure.value.code == "INVALID_REQUEST"
    finally:
        rt.close()


def test_schedule_crud_codes_replay_and_cross_bot_scope(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        first = bot(rt, "A Bot", "ws-a")
        second = bot(rt, "B Bot", "ws-b")
        created = rt.create_schedule(first["id"], {"requestId": "sch-1", "prompt": "查机票",
                                                   "rule": {"kind": "daily", "atLocalTime": "09:00"}})
        assert created["timezone"] and created["nextRunAt"] and created["createdBy"] == "user"
        replayed = rt.create_schedule(first["id"], {"requestId": "sch-1", "prompt": "查机票",
                                                    "rule": {"kind": "daily", "atLocalTime": "09:00"}})
        assert replayed["id"] == created["id"] and len(rt.list_schedules(first["id"])) == 1

        updated = rt.update_schedule(first["id"], created["id"], {"rule": {"kind": "interval", "everySeconds": 10800},
                                                                  "overlapPolicy": "queue", "prompt": "改过的说明"})
        assert updated["rule"] == {"kind": "interval", "everySeconds": 10800} and updated["overlapPolicy"] == "queue"
        assert rt.set_schedule_enabled(first["id"], created["id"], False)["enabled"] is False
        assert rt.set_schedule_enabled(first["id"], created["id"], True)["enabled"] is True
        assert rt.delete_schedule(first["id"], created["id"])["deleted"] is True
        assert rt.list_schedules(first["id"]) == []

        for code, call in (
            ("SCHEDULE_INTERVAL_TOO_SHORT", lambda: rt.create_schedule(first["id"], {"prompt": "太快", "rule": {"kind": "interval", "everySeconds": 60}})),
            ("INVALID_SCHEDULE_RULE", lambda: rt.create_schedule(first["id"], {"prompt": "坏规则", "rule": {"kind": "cron", "expression": "* * * * *"}})),
            ("INVALID_TIMEZONE", lambda: rt.create_schedule(first["id"], {"prompt": "坏时区", "rule": {"kind": "daily", "atLocalTime": "09:00"}, "timezone": "Mars/Olympus"})),
            ("SCHEDULE_NOT_FOUND", lambda: rt.update_schedule(first["id"], "sch_missing", {"prompt": "改"})),
            ("SCHEDULE_NOT_FOUND", lambda: rt.update_schedule(second["id"], "sch_missing", {"prompt": "改"})),
        ):
            with pytest.raises(WebError) as failure:
                call()
            assert failure.value.code == code
        for index in range(20):
            rt.create_schedule(second["id"], {"prompt": f"第 {index} 条", "rule": {"kind": "interval", "everySeconds": 300}})
        with pytest.raises(WebError) as limit:
            rt.create_schedule(second["id"], {"prompt": "第 21 条", "rule": {"kind": "interval", "everySeconds": 300}})
        assert limit.value.code == "SCHEDULE_LIMIT" and limit.value.status == 409
        with pytest.raises(WebError) as scope:
            rt._schedule(first["id"], rt.list_schedules(second["id"])[0]["id"])
        assert scope.value.code == "SCHEDULE_NOT_FOUND"
    finally:
        rt.close()


def test_delete_bot_removes_its_schedules(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = bot(rt, "删定时 Bot")
        rt.create_schedule(worker["id"], {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": 300}})
        rt.delete_bot(worker["id"])
        assert rt._schedules == {}
    finally:
        rt.close()


def test_legacy_scheduled_task_migrates_to_a_once_schedule(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "旧定时 Bot")
        legacy = rt.create_task({"requestId": "legacy-scheduled", "botId": worker["id"], "prompt": "旧的一次性定时"})
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        rt._tasks[legacy["id"]].update(status="scheduled", runAt=run_at, queueReason=None)
        rt._persist()
    finally:
        rt.close()

    reopened = runtime(tmp_path, FakeExecutor())
    try:
        schedules = reopened.list_schedules(worker["id"])
        assert len(schedules) == 1 and schedules[0]["rule"] == {"kind": "once", "at": run_at}
        migrated = reopened.get_task(legacy["id"])
        assert migrated["status"] == "waiting" and migrated["waitReason"] == "manual" and migrated["runAt"] is None
        assert any("迁移" in message["content"] for message in reopened.list_messages(legacy["id"]))
    finally:
        reopened.close()

    # The migration id is derived from the task id, so a load that was never
    # persisted cannot create a second copy of the same schedule.
    again = runtime(tmp_path, FakeExecutor())
    try:
        assert len(again.list_schedules(worker["id"])) == 1
    finally:
        again.close()


def test_state_without_a_schedules_key_still_loads(tmp_path):
    rt = runtime(tmp_path)
    try:
        bot(rt, "老文件 Bot")
        rt.create_schedule(rt.list_bots()[0]["id"], {"prompt": "查机票", "rule": {"kind": "interval", "everySeconds": 300}})
    finally:
        rt.close()
    state_path = tmp_path / "bots" / "state.json"
    record = json.loads(state_path.read_text())
    record.pop("schedules")
    state_path.write_text(json.dumps(record))
    reopened = runtime(tmp_path, FakeExecutor())
    try:
        assert reopened._load_error == "" and reopened.list_schedules(reopened.list_bots()[0]["id"]) == []
    finally:
        reopened.close()


def test_paused_once_schedule_keeps_its_only_chance_until_rearmed(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        asleep = bot(rt, "总闸关的 Bot", "ws-once-off", wake=False)
        awake = bot(rt, "单条关的 Bot", "ws-once-single", wake=True)
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        blocked = rt.create_schedule(asleep["id"], {"prompt": "一次提醒", "rule": {"kind": "once", "at": past}})
        single = rt.create_schedule(awake["id"], {"prompt": "单条提醒", "rule": {"kind": "once", "at": past}})
        rt.set_schedule_enabled(awake["id"], single["id"], False)

        rt.tick(); drain_launch(rt)
        assert rt.list_tasks(bot_id=asleep["id"]) == [] and rt.list_tasks(bot_id=awake["id"]) == []
        for schedule_id, original in ((blocked["id"], blocked["nextRunAt"]), (single["id"], single["nextRunAt"])):
            row = rt._schedules[schedule_id]
            assert row["nextRunAt"] == original, "a paused one-shot must keep its due time"
            assert row["lastSkip"]["reason"] == "paused" and row["lastRunAt"] is None

        # Re-arming the Bot-level switch lets the parked one-shot run once.
        rt.update_bot(asleep["id"], {"wakeEnabled": True})
        rt.tick(); drain_launch(rt)
        fired = rt.list_tasks(bot_id=asleep["id"])
        assert len(fired) == 1 and fired[0]["prompt"] == "一次提醒"
        assert rt._schedules[blocked["id"]]["nextRunAt"] is None
        assert any("延后" in message["content"] for message in rt.list_messages(fired[0]["id"]))

        # The same holds for the per-schedule switch.
        rt.set_schedule_enabled(awake["id"], single["id"], True)
        rt.tick(); drain_launch(rt)
        fired_single = rt.list_tasks(bot_id=awake["id"])
        assert len(fired_single) == 1 and fired_single[0]["prompt"] == "单条提醒"
        assert rt._schedules[single["id"]]["nextRunAt"] is None
        assert any("延后" in message["content"] for message in rt.list_messages(fired_single[0]["id"]))
    finally:
        rt.close()


def test_busy_skip_defers_a_once_schedule_instead_of_dropping_it(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "忙碌 Bot", "ws-busy-once")
        running = rt.create_task({"requestId": "busy-once", "botId": worker["id"], "prompt": "长任务"})
        rt._tasks[running["id"]].update(status="running", sessionId="session-long")
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        once = rt.create_schedule(worker["id"], {"prompt": "一次提醒", "rule": {"kind": "once", "at": past}})
        rt.tick(); drain_launch(rt)
        assert [task["prompt"] for task in rt.list_tasks(bot_id=worker["id"])] == ["长任务"]
        row = rt._schedules[once["id"]]
        assert row["nextRunAt"] == once["nextRunAt"] and row["lastSkip"]["reason"] == "busy"

        executor.outcomes[running["id"]] = "completed"
        rt.tick(); drain_launch(rt)
        rt.tick(); drain_launch(rt)
        fired = next(task for task in rt.list_tasks(bot_id=worker["id"]) if task["prompt"] == "一次提醒")
        assert rt._schedules[once["id"]]["nextRunAt"] is None
        assert any("延后" in message["content"] for message in rt.list_messages(fired["id"]))
    finally:
        rt.close()


def test_legacy_scheduled_task_at_the_limit_reports_the_truth(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "满额 Bot", "ws-limit-migrate")
        for index in range(20):
            rt.create_schedule(worker["id"], {"prompt": f"占位 {index}", "rule": {"kind": "interval", "everySeconds": 300}})
        legacy = rt.create_task({"requestId": "legacy-limit", "botId": worker["id"], "prompt": "旧的一次性定时"})
        rt._tasks[legacy["id"]].update(status="scheduled", runAt=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
        rt._persist()
    finally:
        rt.close()

    reopened = runtime(tmp_path, FakeExecutor())
    try:
        assert len(reopened.list_schedules(worker["id"])) == 20
        assert reopened._tasks[legacy["id"]].get("scheduleId") is None
        assert reopened.get_task(legacy["id"])["status"] == "waiting"
        contents = [message["content"] for message in reopened.list_messages(legacy["id"])]
        assert any("没有迁移" in content and "上限" in content for content in contents), contents
        assert not any("已迁移成" in content for content in contents)
    finally:
        reopened.close()


def test_a_repeating_schedule_gets_no_late_note_after_a_busy_skip(tmp_path):
    executor = ScriptedPlanExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "忙完再跑", "ws-repeating-late")
        running = rt.create_task({"requestId": "busy-interval", "botId": worker["id"], "prompt": "长任务"})
        rt._tasks[running["id"]].update(status="running", sessionId="session-long")
        repeating = rt.create_schedule(worker["id"], {"prompt": "周期提醒", "rule": {"kind": "interval", "everySeconds": 300}})
        past = lambda: (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        rt._schedules[repeating["id"]]["nextRunAt"] = past()
        rt.tick(); drain_launch(rt)
        assert rt._schedules[repeating["id"]]["lastSkip"]["reason"] == "busy"

        executor.outcomes[running["id"]] = "completed"
        rt.tick(); drain_launch(rt)
        rt._schedules[repeating["id"]]["nextRunAt"] = past()
        rt.tick(); drain_launch(rt)
        fired = next(task for task in rt.list_tasks(bot_id=worker["id"]) if task["prompt"] == "周期提醒")
        # The late note belongs to one-shots only: an interval run that fires on
        # its next due time is not late.
        assert not any("延后" in message["content"] for message in rt.list_messages(fired["id"]))
    finally:
        rt.close()


class FlakyValidateExecutor(FakeExecutor):
    """validate() fails while the model catalog is not ready, then recovers."""

    def __init__(self):
        super().__init__()
        self.broken = False

    def validate(self, bot):
        if self.broken:
            raise WebError("BOT_EXECUTOR_UNAVAILABLE", "Pi 执行器尚未连接，请先配置可用的 MMS 模型。", 409)
        return super().validate(bot)


def test_a_failed_create_does_not_consume_a_once_schedule(tmp_path):
    executor = FlakyValidateExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "重启中的 Bot", "ws-once-error")
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        once = rt.create_schedule(worker["id"], {"prompt": "一次提醒", "rule": {"kind": "once", "at": past}})
        executor.broken = True
        rt.tick(); drain_launch(rt)
        row = rt._schedules[once["id"]]
        assert rt.list_tasks(bot_id=worker["id"]) == []
        assert row["nextRunAt"] == once["nextRunAt"], "a failed create must give the one-shot its due time back"
        assert row["lastSkip"]["reason"] == "error"

        # While the executor stays broken the parked row is not rewritten.
        parked_at = row["updatedAt"]
        rt.tick(); rt.tick(); drain_launch(rt)
        assert rt._schedules[once["id"]]["updatedAt"] == parked_at
        assert rt._schedules[once["id"]]["nextRunAt"] == once["nextRunAt"]

        executor.broken = False
        rt.tick(); drain_launch(rt)
        fired = rt.list_tasks(bot_id=worker["id"])
        assert len(fired) == 1 and fired[0]["prompt"] == "一次提醒"
        assert rt._schedules[once["id"]]["nextRunAt"] is None
    finally:
        rt.close()


def test_an_error_parked_once_explains_the_late_run(tmp_path):
    executor = FlakyValidateExecutor()
    rt = runtime(tmp_path, executor)
    try:
        worker = bot(rt, "补触发说明", "ws-once-error-note")
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        once = rt.create_schedule(worker["id"], {"prompt": "一次提醒", "rule": {"kind": "once", "at": past}})
        executor.broken = True
        rt.tick(); drain_launch(rt)
        assert rt._schedules[once["id"]]["lastSkip"]["reason"] == "error"
        executor.broken = False
        rt.tick(); drain_launch(rt)
        fired = rt.list_tasks(bot_id=worker["id"])
        assert len(fired) == 1
        notes = [message["content"] for message in rt.list_messages(fired[0]["id"])]
        assert any("没能建出任务" in content and "现在补触发" in content for content in notes)
        assert not any("因暂停" in content for content in notes)
    finally:
        rt.close()
