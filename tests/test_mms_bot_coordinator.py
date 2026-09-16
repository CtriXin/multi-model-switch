from mms_web.bot_coordinator import (make_plan, parse_model_plan, build_planner_prompt, direct_plan,
                                     looks_multi_goal, looks_fleet_review, fleet_presets, fleet_plan,
                                     is_split_plan, normalize_fleet_policy, set_plan_status, transition_plan,
                                     transition_step, normalize_step_status, MAX_PLAN_HISTORY,
                                     UNDERFILLED_REASON)
from mms_web.bot_computer import EgoComputer


def bot(bot_id, name, description=""):
    return {"id": bot_id, "name": name, "description": description, "systemPrompt": ""}


def test_coordinator_keeps_simple_goal_direct():
    owner = bot("a", "总管")
    plan = make_plan("整理这份文件并告诉我结果", owner, [owner, bot("b", "验证员")])
    assert plan["mode"] == "direct"
    assert plan["modelDecision"] is False
    assert plan["steps"][0]["botId"] == "a"


def test_coordinator_records_candidates_without_starting_workers():
    owner = bot("a", "总管")
    checker = bot("b", "验证员", "检查网页和文件")
    writer = bot("c", "文案员", "整理并撰写结果")
    plan = make_plan("请让验证员和文案员并行检查并汇总", owner, [owner, checker, writer])
    assert plan["mode"] == "delegate"
    assert [item["id"] for item in plan["candidates"]] == ["b", "c"]
    assert all(step["status"] == "pending" for step in plan["steps"])


def test_ego_computer_exposes_browser_provider_contract(tmp_path):
    provider = EgoComputer(tmp_path, executable="/usr/bin/false")
    capabilities = provider.capabilities()
    assert provider.provider_id == "ego"
    assert capabilities["provider"] == "ego"
    assert "snapshot" in capabilities["operations"]


def test_model_plan_parses_valid_delegate_json():
    owner = bot("a", "总管")
    writer = bot("b", "写手", "写文件")
    checker = bot("c", "检查员", "核对结果")
    reply = '{"mode":"delegate","reason":"两个独立子目标",' \
            '"steps":[{"id":"s1","botId":"b","goal":"写 b.txt","dependsOn":[],"presetId":null},' \
            '{"id":"s2","botId":"c","goal":"核对 b.txt","dependsOn":["s1"],"presetId":"pi:cheap"}],"merge":"owner"}'
    plan = parse_model_plan(reply, owner, [owner, writer, checker])
    assert plan["mode"] == "delegate"
    assert plan["source"] == "model"
    assert [step["botId"] for step in plan["steps"]] == ["b", "c"]
    assert plan["steps"][1]["dependsOn"] == ["s1"]
    assert plan["steps"][1]["presetId"] == "pi:cheap"
    assert all(step["status"] == "pending" and step["taskId"] is None for step in plan["steps"])


def test_model_plan_drops_unknown_bots_backward_deps_and_self():
    owner = bot("a", "总管")
    writer = bot("b", "写手")
    reply = '{"mode":"delegate","reason":"x","steps":[' \
            '{"id":"s1","botId":"ghost","goal":"不存在的 Bot","dependsOn":[]},' \
            '{"id":"s2","botId":"a","goal":"派给自己","dependsOn":[]},' \
            '{"id":"s3","botId":"b","dependsOn":[]},' \
            '{"id":"s4","botId":"b","goal":"合法步骤","dependsOn":["s9"]}]}'
    plan = parse_model_plan(reply, owner, [owner, writer])
    assert [step["id"] for step in plan["steps"]] == ["s4"]
    assert plan["steps"][0]["dependsOn"] == []


def test_model_plan_drops_self_and_forward_dependencies():
    owner = bot("a", "总管")
    writer = bot("b", "写手")
    reply = '{"mode":"delegate","reason":"x","steps":[' \
            '{"id":"s1","botId":"b","goal":"写文件","dependsOn":["s1","s2"]},' \
            '{"id":"s2","botId":"b","goal":"再检查","dependsOn":["s1"]}]}'
    plan = parse_model_plan(reply, owner, [owner, writer])
    assert [step["dependsOn"] for step in plan["steps"]] == [[], ["s1"]]


def test_model_plan_rejects_missing_fields_and_direct_needs_no_steps():
    owner = bot("a", "总管")
    bots = [owner, bot("b", "写手")]
    assert parse_model_plan('{"mode":"delegate","reason":"x","steps":[]}', owner, bots) is None
    assert parse_model_plan('{"mode":"delegate","reason":"x"}', owner, bots) is None
    assert parse_model_plan('{"mode":"sideways","reason":"x","steps":[{"botId":"b","goal":"g"}]}', owner, bots) is None
    plan = parse_model_plan('{"mode":"direct","reason":"自己做"}', owner, bots)
    assert plan["mode"] == "direct" and plan["source"] == "model"
    assert plan["steps"][0]["botId"] == "a"


def test_model_plan_rejects_non_json_and_wraps_fenced_json():
    owner = bot("a", "总管")
    bots = [owner, bot("b", "写手")]
    assert parse_model_plan("", owner, bots) is None
    assert parse_model_plan("我先想一下……没有 JSON", owner, bots) is None
    assert parse_model_plan('{"mode":"delegate","steps":[{]}', owner, bots) is None
    fenced = '好的，计划如下：\n```json\n{"mode":"delegate","reason":"分工","steps":[{"id":"s1","botId":"b","goal":"写文件","dependsOn":[]}]}\n```'
    plan = parse_model_plan(fenced, owner, bots)
    assert plan["mode"] == "delegate" and plan["steps"][0]["botId"] == "b"


def test_planner_prompt_carries_roster_goal_and_schema():
    owner = bot("a", "总管")
    prompt = build_planner_prompt("让写手整理文件", owner, [owner, bot("b", "写手", "写文件")], "用户偏好简洁回报")
    assert "id=b" in prompt and "写手" in prompt
    assert "让写手整理文件" in prompt
    assert "用户偏好简洁回报" in prompt
    assert '"mode"' in prompt and "dependsOn" in prompt
    assert "id=a" not in prompt.split("可分工的其它 Bot")[1]


def test_planner_prompt_includes_recent_success_titles_when_given():
    owner = bot("a", "总管")
    writer = bot("b", "写手", "写文件")
    prompt = build_planner_prompt("分工", owner, [owner, writer], "", {"b": ["整理月报", "核对数据"]})
    assert "近期完成=整理月报；核对数据" in prompt
    bare = build_planner_prompt("分工", owner, [owner, writer])
    assert "近期完成" not in bare


def test_looks_multi_goal_positive_shapes():
    assert looks_multi_goal("分别给我：1）三句话介绍 git rebase；2）三句话介绍 git merge")
    assert looks_multi_goal("1. 写一份总结\n2. 写一份摘要")
    assert looks_multi_goal("- 整理桌面文件\n- 清理下载目录")
    assert looks_multi_goal("请同时检查日志和配置文件")
    writer, checker = bot("b", "写手"), bot("c", "检查员")
    assert looks_multi_goal("请写手处理文案，检查员核对结果", [writer, checker], owner_id="a")


def test_looks_multi_goal_negative_single_goals():
    assert not looks_multi_goal("列出当前目录的 txt 文件")
    assert not looks_multi_goal("用三句话解释 git rebase")
    assert not looks_multi_goal("总结这份文档并告诉我结论")
    assert not looks_multi_goal("把 report.txt 重命名为 final.txt")
    writer, checker = bot("b", "写手"), bot("c", "检查员")
    assert not looks_multi_goal("请写手整理这份文件", [writer, checker], owner_id="a")


def test_looks_fleet_review_is_not_a_single_review():
    assert looks_fleet_review("让几个模型评审这次改动")
    assert looks_fleet_review("用你现在能用的模型一起看这份 diff")
    assert looks_fleet_review("跨家族 review 一下")
    assert not looks_fleet_review("帮我评审这段代码")
    assert not looks_fleet_review("整理这份文件并告诉我结果")
    assert not looks_fleet_review("")


def test_fleet_presets_defaults_to_two_cheap_families():
    presets = [
        {"id": "web:pi:kimi-fast", "harness": "pi", "available": True, "family": "Kimi", "modelName": "kimi-for-coding-highspeed"},
        {"id": "web:pi:kimi-k3", "harness": "pi", "available": True, "family": "Kimi", "modelName": "k3"},
        {"id": "web:pi:glm-turbo", "harness": "pi", "available": True, "family": "GLM", "modelName": "glm-5-turbo"},
        {"id": "web:pi:glm-max", "harness": "pi", "available": True, "family": "GLM", "modelName": "glm-5.2"},
        {"id": "web:pi:opus", "harness": "pi", "available": True, "family": "Claude", "modelName": "claude-opus-4-6-thinking"},
        {"id": "web:pi:qwen", "harness": "codex", "available": True, "family": "Qwen", "modelName": "qwen3"},
        {"id": "web:pi:dead", "harness": "pi", "available": False, "family": "DeepSeek", "modelName": "deepseek-v4-flash"},
        {"id": "web:pi:grok", "harness": "pi", "available": True, "family": "Grok", "modelName": "grok-4.6"},
    ]
    rows = fleet_presets(presets)
    assert len(rows) == 2
    assert {item["family"] for item in rows} == {"Kimi", "GLM"}
    by_family = {item["family"]: item["id"] for item in rows}
    assert by_family["Kimi"] == "web:pi:kimi-fast"
    assert by_family["GLM"] == "web:pi:glm-turbo"
    intense = fleet_presets(presets, policy={"intensity": "intense", "maxFamilies": 2})
    intense_ids = {item["id"] for item in intense}
    assert "web:pi:kimi-k3" in intense_ids or "web:pi:opus" in intense_ids
    pinned = fleet_presets(presets, policy={"families": ["DeepSeek", "Grok"], "maxFamilies": 2})
    assert [item["family"] for item in pinned] == ["Grok"]
    three = fleet_presets(presets, policy={"families": ["Kimi", "GLM", "Grok"], "maxFamilies": 3})
    assert [item["family"] for item in three] == ["Kimi", "GLM", "Grok"]
    remembered = fleet_presets(presets, policy={
        "families": ["Kimi", "GLM"],
        "models": {"Kimi": "web:pi:kimi-k3", "GLM": "web:pi:glm-max"},
    })
    assert {item["family"]: item["id"] for item in remembered} == {
        "Kimi": "web:pi:kimi-k3",
        "GLM": "web:pi:glm-max",
    }


def test_fleet_plan_uses_owner_bot_not_new_colleagues():
    owner = bot("a", "阿星")
    owner["presetId"] = "web:pi:kimi"
    presets = [
        {"id": "web:pi:kimi", "harness": "pi", "available": True, "family": "Kimi", "modelName": "kimi-k2"},
        {"id": "web:pi:glm", "harness": "pi", "available": True, "family": "GLM", "modelName": "glm-5"},
    ]
    plan = fleet_plan(owner, presets, "让几个模型评审这次改动")
    assert plan["mode"] == "fleet"
    assert is_split_plan(plan)
    assert [step["botId"] for step in plan["steps"]] == ["a", "a"]
    assert {step["presetId"] for step in plan["steps"]} == {"web:pi:kimi", "web:pi:glm"}
    assert all(step["kind"] == "fleet" and step["label"] for step in plan["steps"])
    thin = fleet_plan(owner, presets[:1], "让几个模型评审这次改动")
    assert thin["mode"] == "direct"
    assert thin["source"] == "fleet-underfilled"
    assert thin["reason"] == UNDERFILLED_REASON
    closed = fleet_plan(owner, presets, "让几个模型评审这次改动", {"enabled": False})
    assert closed["mode"] == "direct" and closed["source"] == "fleet-disabled"
    assert normalize_fleet_policy({"maxFamilies": 9})["maxFamilies"] == 9
    assert normalize_fleet_policy({})["maxFamilies"] == 2


def test_plan_transitions_follow_the_table_and_record_history():
    plan = direct_plan(bot("a", "总管"), "r", "test")
    set_plan_status(plan, "auto")
    assert plan["history"] == [{"at": plan["history"][0]["at"], "from": None, "to": "auto", "by": "system"}]
    assert transition_plan(plan, "done") is False  # illegal: auto -> done
    assert plan["status"] == "auto" and len(plan["history"]) == 1
    assert transition_plan(plan, "running") is True
    assert transition_plan(plan, "merging", by="system") is True
    assert transition_plan(plan, "done", by="step:s1") is True
    assert plan["history"][-1]["from"] == "merging" and plan["history"][-1]["by"] == "step:s1"
    assert transition_plan(plan, "running") is False  # done is terminal
    # failed -> running only via the retry-step reopen
    plan2 = direct_plan(bot("a", "总管"), "r", "test")
    set_plan_status(plan2, "auto")
    transition_plan(plan2, "running")
    assert transition_plan(plan2, "failed", by="step:s2") is True
    assert transition_plan(plan2, "running", by="user") is True


def test_plan_history_is_capped_at_fifty():
    plan = direct_plan(bot("a", "总管"), "r", "test")
    set_plan_status(plan, "auto")
    transition_plan(plan, "running")
    for _ in range(40):
        transition_plan(plan, "failed", by="step:s1")
        transition_plan(plan, "running", by="user")
    assert len(plan["history"]) == MAX_PLAN_HISTORY
    assert plan["history"][-1]["to"] == "running"


def test_step_transitions_follow_the_table():
    step = {"id": "s1", "status": "pending"}
    assert transition_step(step, "done") is False  # pending cannot finish directly
    assert transition_step(step, "ready") is True
    assert transition_step(step, "running") is True
    assert transition_step(step, "failed") is True
    assert transition_step(step, "ready") is True   # retry-step reopen
    assert transition_step(step, "skipped") is True
    assert transition_step(step, "running") is False  # skipped is terminal
    legacy = {"id": "s2", "status": "dispatched"}
    assert normalize_step_status("dispatched") == "running"
    assert normalize_step_status("blocked") == "skipped"
    assert transition_step(legacy, "done") is True


def test_sanitize_plan_defaults_and_validates_on_failure():
    owner = bot("a", "总管")
    writer = bot("b", "写手")
    reply = '{"mode":"delegate","reason":"x","steps":[' \
            '{"id":"s1","botId":"b","goal":"写","dependsOn":[],"onFailure":"skip"},' \
            '{"id":"s2","botId":"b","goal":"核","dependsOn":["s1"],"onFailure":"explode"}]}'
    plan = parse_model_plan(reply, owner, [owner, writer])
    assert plan["steps"][0]["onFailure"] == "skip"
    assert plan["steps"][1]["onFailure"] == "retry"
    direct = direct_plan(owner, "r", "test")
    assert direct["steps"][0]["onFailure"] == "retry"
