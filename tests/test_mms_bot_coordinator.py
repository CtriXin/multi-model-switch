from mms_web.bot_coordinator import make_plan
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
