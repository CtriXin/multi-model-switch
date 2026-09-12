from mms_web.bot_coordinator import make_plan, parse_model_plan, build_planner_prompt
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
