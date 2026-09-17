"""T5c: switching a Bot's model from the conversation, effective next round."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mms_web import model_switch
from mms_web.bot_executor import PiBotExecutor, available_presets, match_presets
from mms_web.bots import BotRuntime
from mms_web.errors import WebError


# Both sides read one shared fixture: this file and
# apps/mms-web/tests/bot-model-switch.test.mjs. A matcher drift on either side
# turns one of the two suites red.
FIXTURE = json.loads((Path(__file__).resolve().parents[1]
                      / "apps/mms-web/tests/fixtures/model-match-cases.json").read_text(encoding="utf-8"))
PRESETS = FIXTURE["presets"]
# Production always matches over the launchable subset (available_presets);
# the frontend matcher applies the same filter internally.
AVAILABLE = available_presets({"presets": PRESETS})


class FakeCatalog:
    def __init__(self, presets):
        self._snapshot = {"presets": presets, "workspaces": [{"id": "ws-1"}, {"id": "default"}]}

    def snapshot(self):
        return self._snapshot


class CatalogExecutor:
    """Fake executor for the runtime's own model and session decisions.

    start() serves what the runtime asks for the way those requests are meant
    to be served: a supplied session is continued, so the effective model is
    whatever that session was launched with, and no supplied session means a
    fresh launch on the selected preset.

    The real PiBotExecutor additionally refuses to continue a session that runs
    another model — a backstop for callers that forget to resolve the session
    themselves. That backstop is covered against the real executor in
    test_reused_session_running_another_model_* below. The runtime must decide
    the model/session pairing itself and never lean on the backstop, so this
    double does not implement it: a runtime that handed over a mismatched
    session again would show the old model as effective here, and the override
    tests below would fail on exactly that assertion.
    """

    def __init__(self, presets):
        self.catalog = FakeCatalog(presets)
        self.starts = []
        self.sessions = {}
        self.released = []

    def available(self):
        return True

    def validate(self, bot):
        catalog = self.catalog.snapshot()
        preset = next((p for p in catalog["presets"] if p["id"] == bot.get("presetId")), None)
        if not bot.get("presetId"):
            preset = next((p for p in catalog["presets"] if p.get("harness") == "pi" and p.get("available")), None)
        if not preset or preset.get("harness") != "pi" or not preset.get("available"):
            raise WebError("BOT_MODEL_REQUIRED", "MMS 当前没有可启动的 Pi 模型，请先配置一个模型。", 400)
        return {"model": preset.get("name", ""), "channel": preset.get("channel", ""), "presetId": preset.get("id", "")}

    def start(self, task, bot, context_path):
        selected = self.validate(bot)
        reused = bot.get("sessionId") if bot.get("sessionId") in self.sessions else None
        effective = self.sessions.get(reused) or {"presetId": selected["presetId"], "model": selected["model"]}
        self.starts.append({"taskId": task["id"], "presetId": effective["presetId"], "model": effective["model"],
                            "hadSession": bool(reused)})
        session_id = reused or f"session-{task['id']}-{len(self.starts)}"
        self.sessions.setdefault(session_id, effective)
        return {"sessionId": session_id, "baseline": 0, "artifactBaseline": {}, "model": effective["model"]}

    def snapshot(self, task):
        return {"state": "completed", "alive": False, "events": [{
            "id": f"answer-{task['id']}", "kind": "assistant", "status": "done", "text": "完成",
        }], "artifacts": []}

    def cancel(self, task):
        return None

    def release_session(self, session_id, request_id):
        # Mirrors the real seam: a released session is gone from the list and
        # cannot be continued by a later task.
        self.released.append(session_id)
        self.sessions.pop(session_id, None)

    def artifact(self, session_id, artifact_id, revision):
        return {"content": "", "mimeType": "text/plain"}


def runtime(tmp_path):
    rt = BotRuntime(state_root=tmp_path, executor=CatalogExecutor(PRESETS), max_concurrent=3)
    rt.configure_endpoint("http://127.0.0.1:8765/api/v1/bot-worker")
    return rt


def make_bot(rt, name="Bot", preset="pi:alpha"):
    return rt.create_bot({"name": name, "description": "test", "systemPrompt": "", "workspaceId": "ws-1",
                          "presetId": preset, "wakeEnabled": True})


def drain_launch(rt):
    for worker in list(rt._workers):
        worker.join(timeout=1)


def complete_one(rt, task_id):
    for _ in range(10):
        rt.tick()
        drain_launch(rt)
        if rt.get_task(task_id)["status"] == "completed":
            # One more tick: one-off sessions are released at the top of tick,
            # outside the scheduler lock.
            rt.tick()
            return rt.get_task(task_id)
        time.sleep(0.005)
    return rt.get_task(task_id)


def run_task(rt, bot_id, prompt="任务", override=None):
    task = rt.create_task({"botId": bot_id, "prompt": prompt})
    if override:
        with rt._lock:
            rt._tasks[task["id"]]["presetIdOverride"] = override
    return complete_one(rt, task["id"])


def test_match_presets_agrees_with_the_shared_frontend_fixture():
    assert len(FIXTURE["cases"]) >= 15
    for item in FIXTURE["cases"]:
        assert [p["id"] for p in match_presets(item["query"], AVAILABLE)] == item["expect"], item["query"]


def test_model_list_returns_only_launchable_pi_presets(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        view = rt.worker(task["id"], {"action": "model", "op": "list"})
        ids = [m["id"] for m in view["models"]]
        assert ids == ["pi:alpha", "pi:beta", "pi:gamma-pro", "pi:gamma-mini",
                       "web:pi:tokyo:MiniMax-M3", "web:pi:tokyo:gpt-5.6-luna"]
        assert "codex:gpt" not in ids and "pi:down" not in ids
        assert view["message"]
    finally:
        rt.close()


def test_model_list_marks_current_and_pending(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        rt.worker(task["id"], {"action": "model", "op": "switch", "query": "beta"})
        view = rt.worker(task["id"], {"action": "model", "op": "list"})
        by_id = {m["id"]: m for m in view["models"]}
        assert by_id["pi:alpha"]["current"] is True
        assert by_id["pi:beta"]["pending"] is True
        assert view["current"] == "pi:alpha" and view["pending"] == "pi:beta"
        assert "Beta" in view["message"]
    finally:
        rt.close()


def test_switch_single_match_records_pending_for_next_round(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        result = rt.worker(task["id"], {"action": "model", "op": "switch", "query": "Beta 吧"})
        assert result["pending"]["id"] == "pi:beta"
        assert "Beta · 主通道" in result["message"] and "Alpha" in result["message"]
        assert "下一轮" in result["message"]
        bot = rt.get_bot(worker["id"])
        assert bot["pendingPresetId"] == "pi:beta"
        # The current round is untouched: the default model is only consumed at
        # the next launch.
        assert bot["presetId"] == "pi:alpha"
    finally:
        rt.close()


def test_switch_multiple_matches_is_ambiguous_and_never_picks_first(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        with pytest.raises(WebError) as failure:
            rt.worker(task["id"], {"action": "model", "op": "switch", "query": "gamma"})
        assert failure.value.code == "BOT_MODEL_AMBIGUOUS"
        assert failure.value.status == 409
        assert "Gamma Pro" in failure.value.message and "Gamma Mini" in failure.value.message
        assert rt.get_bot(worker["id"])["pendingPresetId"] == ""
    finally:
        rt.close()


def test_switch_without_match_lists_available_models(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        with pytest.raises(WebError) as failure:
            rt.worker(task["id"], {"action": "model", "op": "switch", "query": "不存在的模型"})
        assert failure.value.code == "BOT_MODEL_NOT_FOUND"
        assert failure.value.status == 404
        assert "Alpha" in failure.value.message and "Beta" in failure.value.message
        assert rt.get_bot(worker["id"])["pendingPresetId"] == ""
    finally:
        rt.close()


def test_switch_to_unavailable_preset_fails_without_fallback(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        with pytest.raises(WebError) as failure:
            rt.worker(task["id"], {"action": "model", "op": "switch", "query": "pi:down"})
        assert failure.value.code == "BOT_MODEL_UNAVAILABLE"
        assert failure.value.status == 409
        assert rt.get_bot(worker["id"])["pendingPresetId"] == ""
    finally:
        rt.close()


def test_switch_to_the_current_model_is_a_noop(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        session_before = rt.get_bot(worker["id"])["sessionId"]
        result = rt.worker(task["id"], {"action": "model", "op": "switch", "query": "alpha"})
        assert result["pending"] is None
        assert "已经在用 Alpha 了" in result["message"]
        bot = rt.get_bot(worker["id"])
        assert bot["pendingPresetId"] == ""
        assert bot["sessionId"] == session_before
    finally:
        rt.close()


def test_pending_equal_to_current_preset_only_gets_cleared(tmp_path):
    # Second defense for the same-model case: a pending that equals presetId
    # (e.g. written via update_bot) is consumed by clearing only — the session
    # must not be reset, or the Pi history would be thrown away for nothing.
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        run_task(rt, worker["id"])
        session_before = rt.get_bot(worker["id"])["sessionId"]
        rt.update_bot(worker["id"], {"pendingPresetId": "pi:alpha"})
        second = run_task(rt, worker["id"], prompt="第二轮")
        assert second["status"] == "completed"
        bot = rt.get_bot(worker["id"])
        assert bot["pendingPresetId"] == ""
        assert bot["sessionId"] == session_before
        assert rt.executor.starts[-1]["hadSession"] is True
    finally:
        rt.close()


def test_switch_takes_effect_on_the_next_round_and_is_consumed(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        executor = rt.executor
        first = run_task(rt, worker["id"])
        rt.worker(first["id"], {"action": "model", "op": "switch", "query": "beta"})
        # The round that requested the switch kept its own preset.
        assert executor.starts[-1]["presetId"] == "pi:alpha"
        second = run_task(rt, worker["id"], prompt="第二轮")
        assert second["status"] == "completed"
        assert executor.starts[-1]["presetId"] == "pi:beta"
        # A model switch starts a fresh Pi session (same semantics as changing
        # presetId via update_bot); reusing the old session would keep running
        # the old model and make "next round" an empty promise.
        assert executor.starts[-1]["hadSession"] is False
        assert executor.starts[0]["hadSession"] is False
        bot = rt.get_bot(worker["id"])
        assert bot["presetId"] == "pi:beta" and bot["pendingPresetId"] == ""
        assert bot["model"] == "Beta"
        assert bot["sessionId"] == second["sessionId"]
        third = run_task(rt, worker["id"], prompt="第三轮")
        assert executor.starts[-1]["presetId"] == "pi:beta"
        # Without a switch the durable session is reused as before.
        assert executor.starts[-1]["hadSession"] is True
        assert third["status"] == "completed"
        kinds = [(m["type"], m["content"]) for m in rt.list_messages(second["id"])]
        assert ("system", "本轮起使用模型 Beta。") in kinds
    finally:
        rt.close()


def test_switch_never_goes_through_session_level_model_switch(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        with patch.object(model_switch, "switch_model", side_effect=AssertionError("session switch called")) as spy:
            rt.worker(task["id"], {"action": "model", "op": "switch", "query": "beta"})
            run_task(rt, worker["id"], prompt="第二轮")
        assert spy.call_count == 0
    finally:
        rt.close()


def test_unavailable_pending_is_cancelled_and_the_round_falls_back_loudly(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        first = run_task(rt, worker["id"])
        session_before = rt.get_bot(worker["id"])["sessionId"]
        rt.worker(first["id"], {"action": "model", "op": "switch", "query": "beta"})
        # The preset becomes unavailable between the request and the next round.
        rt.executor.catalog._snapshot["presets"] = [
            {**p, "available": False} if p["id"] == "pi:beta" else p for p in PRESETS
        ]
        second = run_task(rt, worker["id"], prompt="第二轮")
        # The round still completes, on the model the user is already using;
        # the pending switch is cancelled (never self-retried into a brick) and
        # a system message names the unavailable model.
        assert second["status"] == "completed"
        assert rt.executor.starts[-1]["presetId"] == "pi:alpha"
        assert rt.executor.starts[-1]["hadSession"] is True
        bot = rt.get_bot(worker["id"])
        assert bot["presetId"] == "pi:alpha" and bot["pendingPresetId"] == ""
        assert bot["sessionId"] == session_before
        kinds = [(m["type"], m["content"]) for m in rt.list_messages(second["id"])]
        assert any(t == "system" and "Beta" in c and "已取消这次切换" in c and "Alpha" in c
                   for t, c in kinds), kinds
        # And the Bot keeps working afterwards.
        third = run_task(rt, worker["id"], prompt="第三轮")
        assert third["status"] == "completed"
    finally:
        rt.close()


def test_update_bot_rejects_an_unknown_pending_preset_without_touching_state(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        before = rt.get_bot(worker["id"])
        with pytest.raises(WebError) as failure:
            rt.update_bot(worker["id"], {"pendingPresetId": "pi:nope"})
        assert failure.value.code == "BOT_MODEL_UNAVAILABLE"
        assert failure.value.status == 409
        assert rt.get_bot(worker["id"]) == before
        # An unavailable real preset is rejected the same way.
        with pytest.raises(WebError) as failure:
            rt.update_bot(worker["id"], {"pendingPresetId": "pi:down"})
        assert failure.value.code == "BOT_MODEL_UNAVAILABLE"
        assert rt.get_bot(worker["id"]) == before
    finally:
        rt.close()


def test_preset_override_runs_in_its_own_session_on_the_overridden_model(tmp_path):
    # T5d: a plan step that names a model must actually run on it, even for a
    # Bot that already owns a durable conversation. That was silently false:
    # the override swapped bot["presetId"] but kept the session, and the
    # reused session keeps running the model it was launched with.
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        executor = rt.executor
        first = run_task(rt, worker["id"])
        main_session = rt.get_bot(worker["id"])["sessionId"]
        rt.worker(first["id"], {"action": "model", "op": "switch", "query": "beta"})
        planned = run_task(rt, worker["id"], prompt="计划指定的一步", override="pi:gamma-pro")
        assert planned["status"] == "completed"
        # The step ran on the model the plan named, in a session of its own.
        assert executor.starts[-1]["presetId"] == "pi:gamma-pro"
        assert executor.starts[-1]["model"] == "Gamma Pro"
        assert executor.starts[-1]["hadSession"] is False
        assert planned["sessionId"] != main_session
        assert planned["model"] == "Gamma Pro"
        # The Bot's main conversation is neither replaced nor consumed: the
        # one-off session belongs to the task, not to the Bot.
        assert rt.get_bot(worker["id"])["sessionId"] == main_session
        # The T5c contract holds: a planned step must not eat the pending switch.
        bot = rt.get_bot(worker["id"])
        assert bot["pendingPresetId"] == "pi:beta" and bot["presetId"] == "pi:alpha"
        followup = run_task(rt, worker["id"], prompt="普通任务")
        assert executor.starts[-1]["presetId"] == "pi:beta"
        assert executor.starts[-1]["hadSession"] is False
        assert rt.get_bot(worker["id"])["pendingPresetId"] == ""
        assert followup["status"] == "completed"
        kinds = [(m["type"], m["content"]) for m in rt.list_messages(planned["id"])]
        assert ("system", "本轮由计划指定使用模型 Gamma Pro。") in kinds
    finally:
        rt.close()


def test_preset_override_leaves_the_bot_main_conversation_untouched(tmp_path):
    # The step is a side branch, not a new main line: after it, an ordinary
    # round must still continue the same conversation the Bot had before.
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        executor = rt.executor
        first = run_task(rt, worker["id"])
        main_session = rt.get_bot(worker["id"])["sessionId"]
        run_task(rt, worker["id"], prompt="计划指定的一步", override="pi:gamma-pro")
        third = run_task(rt, worker["id"], prompt="接着刚才聊")
        assert third["status"] == "completed"
        assert executor.starts[-1]["presetId"] == "pi:alpha"
        assert executor.starts[-1]["hadSession"] is True
        assert third["sessionId"] == main_session
        assert first["sessionId"] == main_session
        assert rt.get_bot(worker["id"])["sessionId"] == main_session
    finally:
        rt.close()


def test_preset_override_one_off_session_is_stopped_and_archived(tmp_path):
    # Nothing adopts that session, so nobody would stop it: it must not linger
    # in Pilot's session list next to the Bot's real conversation.
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        executor = rt.executor
        run_task(rt, worker["id"])
        main_session = rt.get_bot(worker["id"])["sessionId"]
        planned = run_task(rt, worker["id"], prompt="计划指定的一步", override="pi:gamma-pro")
        assert planned["sessionId"] != main_session
        assert executor.released == [planned["sessionId"]]
        assert rt.get_bot(worker["id"])["sessionId"] == main_session
    finally:
        rt.close()


def test_an_ordinary_round_never_releases_the_bot_session(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        run_task(rt, worker["id"])
        run_task(rt, worker["id"], prompt="第二轮")
        assert rt.executor.released == []
        assert rt.get_bot(worker["id"])["sessionId"]
    finally:
        rt.close()


class ReuseSessions:
    """Minimal session service for exercising the real PiBotExecutor.start()."""

    def __init__(self, preset_id, model_name="Alpha"):
        self.preset_id, self.model_name = preset_id, model_name
        self.launched, self.sent = [], []

    def capabilities(self):
        return {"launch": True}

    def get_session(self, session_id):
        return {"session": {"id": session_id, "state": "idle", "presetId": self.preset_id,
                            "modelName": self.model_name},
                "events": [], "artifacts": []}

    def send(self, session_id, payload):
        self.sent.append((session_id, payload))
        return {"session": {"id": session_id, "presetId": self.preset_id, "modelName": self.model_name}}

    def launch(self, payload):
        self.launched.append(payload)
        return {"session": {"id": "s-new", "presetId": payload.get("presetId"),
                            "modelName": payload.get("presetId")}}

    def launch_bot(self, payload, bot_id):
        return self.launch({**payload, "owner": "bot", "botId": bot_id})

    def diagnostics(self, session_id):
        return {}


def test_a_reused_session_that_runs_the_selected_model_is_continued(tmp_path):
    sessions = ReuseSessions("pi:alpha")
    executor = PiBotExecutor(sessions, FakeCatalog(PRESETS))
    bot = {"id": "bot_1", "name": "worker", "presetId": "pi:alpha", "workspaceId": "ws-1",
           "sessionId": "s-main"}
    task = {"id": "task_1", "prompt": "继续", "launchRequestId": "launch-1"}
    outcome = executor.start(task, bot, tmp_path / "context.json")
    assert [session_id for session_id, _ in sessions.sent] == ["s-main"]
    assert sessions.launched == []
    assert outcome["sessionId"] == "s-main" and outcome["reusedSession"] is True


def test_reused_session_running_another_model_is_never_silently_reused(tmp_path):
    # The core defense of T5d: a conversation grew on one model. Continuing it
    # under another model runs the session's model while the caller asked for a
    # different one — the guardrails' first counterexample. It must not be
    # ignored: the selected preset wins, in a fresh session.
    sessions = ReuseSessions("pi:alpha", model_name="Alpha")
    executor = PiBotExecutor(sessions, FakeCatalog(PRESETS))
    bot = {"id": "bot_1", "name": "worker", "presetId": "pi:gamma-pro", "workspaceId": "ws-1",
           "sessionId": "s-main"}
    task = {"id": "task_1", "prompt": "换模型跑一步", "launchRequestId": "launch-1"}
    outcome = executor.start(task, bot, tmp_path / "context.json")
    assert sessions.sent == []
    assert sessions.launched[0]["presetId"] == "pi:gamma-pro"
    assert outcome["sessionId"] == "s-new" and outcome["reusedSession"] is False


def test_reused_session_without_a_recorded_preset_is_not_assumed_to_match(tmp_path):
    # Same rule, weaker evidence: a session that does not say which model it
    # runs cannot be proven to run the selected one, so it is not reused.
    sessions = ReuseSessions("")
    executor = PiBotExecutor(sessions, FakeCatalog(PRESETS))
    bot = {"id": "bot_1", "name": "worker", "presetId": "pi:alpha", "workspaceId": "ws-1",
           "sessionId": "s-main"}
    task = {"id": "task_1", "prompt": "继续", "launchRequestId": "launch-1"}
    outcome = executor.start(task, bot, tmp_path / "context.json")
    assert sessions.sent == []
    assert sessions.launched[0]["presetId"] == "pi:alpha"
    assert outcome["reusedSession"] is False


def test_switch_during_overridden_task_says_so_in_the_reply(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = rt.create_task({"botId": worker["id"], "prompt": "计划指定的一步"})
        with rt._lock:
            rt._tasks[task["id"]]["presetIdOverride"] = "pi:gamma-pro"
        result = rt.worker(task["id"], {"action": "model", "op": "switch", "query": "beta"})
        assert "Gamma Pro" in result["message"]
        assert "下一个没有被计划指定模型的任务" in result["message"]
    finally:
        rt.close()


def test_worker_cannot_switch_another_bots_model(tmp_path):
    rt = runtime(tmp_path)
    try:
        owner = make_bot(rt, "A")
        other = make_bot(rt, "B", preset="pi:beta")
        task = run_task(rt, owner["id"])
        with pytest.raises(WebError) as failure:
            rt.worker(task["id"], {"action": "model", "op": "switch", "query": "gamma pro", "botId": other["id"]})
        assert failure.value.code == "BOT_SCOPE"
        assert rt.get_bot(other["id"])["pendingPresetId"] == ""
        with pytest.raises(WebError) as failure:
            rt.worker(task["id"], {"action": "model", "op": "list", "botId": other["id"]})
        assert failure.value.code == "BOT_SCOPE"
    finally:
        rt.close()


def test_update_bot_accepts_pending_preset_id_while_busy(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = rt.create_task({"botId": worker["id"], "prompt": "占用"})
        rt.tick()
        drain_launch(rt)
        # update_bot's BOT_BUSY only guards presetId; the deferred switch path
        # writes pendingPresetId and stays open while a task is active.
        updated = rt.update_bot(worker["id"], {"pendingPresetId": "pi:beta"})
        assert updated["pendingPresetId"] == "pi:beta"
        assert updated["presetId"] == "pi:alpha"
        rt.worker(task["id"], {"action": "complete", "result": "done"})
        complete_one(rt, task["id"])
        # Clearing is possible too.
        updated = rt.update_bot(worker["id"], {"pendingPresetId": ""})
        assert updated["pendingPresetId"] == ""
    finally:
        rt.close()


def test_pending_preset_id_survives_restart(tmp_path):
    rt = runtime(tmp_path)
    try:
        worker = make_bot(rt)
        task = run_task(rt, worker["id"])
        rt.worker(task["id"], {"action": "model", "op": "switch", "query": "beta"})
    finally:
        rt.close()
    reloaded = runtime(tmp_path)
    try:
        assert reloaded.get_bot(worker["id"])["pendingPresetId"] == "pi:beta"
    finally:
        reloaded.close()


def test_switch_back_to_current_model_cancels_pending_switch(tmp_path):
    rt = runtime(tmp_path)
    try:
        bot = make_bot(rt)
        task = rt.create_task({"botId": bot["id"], "prompt": "keep current"})
        rt.worker(task["id"], {"action": "model", "op": "switch", "query": "beta"})
        result = rt.worker(task["id"], {"action": "model", "op": "switch", "query": "alpha"})
        assert result["pending"] is None
        assert not rt.get_bot(bot["id"])["pendingPresetId"]
        assert "取消" in result["message"]
        run_task(rt, bot["id"])
        assert rt.executor.starts[-1]["presetId"] == "pi:alpha"
    finally:
        rt.close()


def test_one_off_release_failure_is_retried_without_losing_marker(tmp_path, monkeypatch):
    rt = runtime(tmp_path)
    try:
        bot = make_bot(rt)
        task = rt.create_task({"botId": bot["id"], "prompt": "done"})
        rt._tasks[task["id"]].update(status="completed", ephemeralSession=True, sessionId="temporary")
        release = rt.executor.release_session
        with monkeypatch.context() as patcher:
            patcher.setattr(rt.executor, "release_session", lambda *_: (_ for _ in ()).throw(OSError("busy")))
            rt._release_finished_one_off_sessions()
        assert rt._tasks[task["id"]]["ephemeralSession"] is True
        rt._release_finished_one_off_sessions()
        assert rt._tasks[task["id"]]["ephemeralSession"] is False
        assert rt.executor.released == ["temporary"]
    finally:
        rt.close()
