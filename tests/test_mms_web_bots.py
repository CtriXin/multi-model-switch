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


def test_scheduled_wake_respects_bot_wake_enabled(tmp_path):
    executor = FakeExecutor()
    rt = runtime(tmp_path, executor)
    try:
        asleep = bot(rt, "手动 Bot", "ws-a", wake=False)
        awake = bot(rt, "自动 Bot", "ws-b", wake=True)
        run_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        blocked = rt.create_task({"requestId": "scheduled-off", "botId": asleep["id"], "prompt": "off", "runAt": run_at})
        ready = rt.create_task({"requestId": "scheduled-on", "botId": awake["id"], "prompt": "on", "runAt": run_at})
        rt.tick(); drain_launch(rt)
        assert rt.get_task(blocked["id"])["status"] == "scheduled"
        assert rt.get_task(ready["id"])["status"] in {"running", "completed"}
        assert any(item[0] == ready["id"] for item in executor.starts)
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


def test_restart_marks_running_interrupted_without_replay_and_recovers_scheduled(tmp_path):
    first_executor = FakeExecutor()
    first = runtime(tmp_path, first_executor)
    running_bot = bot(first, "运行中", "ws-running")
    scheduled_bot = bot(first, "计划", "ws-scheduled")
    running = first.create_task({"requestId": "running", "botId": running_bot["id"], "prompt": "不会重跑"})
    scheduled = first.create_task({"requestId": "scheduled", "botId": scheduled_bot["id"], "prompt": "重启恢复", "runAt": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()})
    first.tick(); drain_launch(first)
    assert first.get_task(running["id"])["status"] == "running"
    first.close()

    # Simulate the scheduler reaching the persisted due time while Pilot was
    # offline; the task remains scheduled and is not replayed as running.
    state_path = tmp_path / "bots" / "state.json"
    record = json.loads(state_path.read_text())
    record["tasks"][scheduled["id"]]["runAt"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    state_path.write_text(json.dumps(record))

    second_executor = FakeExecutor()
    second = runtime(tmp_path, second_executor)
    try:
        assert second.get_task(running["id"])["status"] == "interrupted"
        assert second.get_task(scheduled["id"])["status"] == "scheduled"
        second.tick(); drain_launch(second)
        assert not any(item[0] == running["id"] for item in second_executor.starts)
        assert any(item[0] == scheduled["id"] for item in second_executor.starts)
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
