"""Fleet selection and execution boundaries, including their real consumers."""
import json
from types import SimpleNamespace

import pytest

from mms_web.bot_coordinator import fleet_plan, fleet_presets
from mms_web.bot_executor import PiBotExecutor
from mms_web.errors import WebError


def presets():
    return [{"id": "pi:" + family, "family": family, "name": family,
             "harness": "pi", "available": True} for family in ("Kimi", "GLM")]


@pytest.mark.parametrize("policy", [
    {"families": ["GPT"]},
    {"families": ["Kimi", "GPT"]},
    {"families": ["Kimi", "GLM"], "models": {"Kimi": "pi:private-kimi"}},
])
def test_explicit_unavailable_choice_never_substitutes(policy):
    with pytest.raises(WebError) as error:
        fleet_presets(presets(), policy=policy)
    assert error.value.code == "BOT_FLEET_SELECTION_UNAVAILABLE"
    assert "重新选择" in error.value.message


def test_available_choices_keep_the_exact_preset_ids():
    policy = {"families": ["GLM", "Kimi"], "models": {"Kimi": "pi:Kimi", "GLM": "pi:GLM"}}
    assert [p["id"] for p in fleet_presets(presets(), policy=policy)] == ["pi:GLM", "pi:Kimi"]


def test_explicit_single_family_does_not_run_the_owners_different_model():
    with pytest.raises(WebError, match="至少两家"):
        fleet_plan({"id": "owner", "presetId": "pi:GLM"}, presets(), "审阅",
                   {"families": ["Kimi"]})


@pytest.mark.parametrize("broken_catalog", [False, True])
def test_fleet_selection_failure_does_not_fall_back_to_execution(tmp_path, broken_catalog):
    from test_mms_web_bots import FakeCatalog, FakeExecutor, bot, drain_launch, runtime

    catalog = FakeCatalog(presets())
    executor = FakeExecutor(catalog)
    rt = runtime(tmp_path, executor)
    try:
        owner = bot(rt, "阿星")
        rt.update_bot(owner["id"], {"fleetPolicy": {"families": ["GPT"]}})
        task = rt.create_task({"requestId": "missing", "botId": owner["id"],
                               "prompt": "请修改文件", "fleetDispatch": True})
        if broken_catalog:
            catalog.snapshot = lambda: (_ for _ in ()).throw(RuntimeError("catalog unavailable"))
        rt.tick()
        drain_launch(rt)
        current = rt.get_task(task["id"])
        assert current["status"] == "interrupted"
        assert not current["children"]
        assert executor.starts == []
        assert current["error"]
        if not broken_catalog:
            assert "GPT" in current["error"]
    finally:
        rt.close()


def test_fleet_executor_requests_read_only_and_never_reuses_main_session(tmp_path):
    captured = {}

    def launch(payload, bot_id, *, read_only=False):
        captured.update(payload=payload, bot_id=bot_id, read_only=read_only)
        return {"session": {"id": "fresh-review", "modelName": "Kimi"}}

    sessions = SimpleNamespace(launch_bot=launch, diagnostics=lambda _: {"pid": None})
    executor = PiBotExecutor(sessions, None)
    executor.validate = lambda _: {"presetId": "pi:Kimi"}
    owner = {"id": "owner", "name": "阿星", "sessionId": "main-session", "workspaceId": "ws"}
    task = {"id": "review", "workerKind": "fleet", "prompt": "请审阅，不执行", "launchRequestId": "review-1"}
    result = executor.start(task, owner, tmp_path / "credentials.json")
    assert result["sessionId"] == "fresh-review" and result["reusedSession"] is False
    assert captured["read_only"] is True
    assert captured["payload"]["presetId"] == "pi:Kimi"
    assert "bot_client.py" not in captured["payload"]["prompt"]
    assert "credentials.json" not in captured["payload"]["prompt"]
    assert owner["sessionId"] == "main-session"


def test_legacy_adapter_cannot_silently_drop_read_only():
    sessions = SimpleNamespace(launch=lambda _: pytest.fail("unsafe fallback"))
    with pytest.raises(WebError, match="只读"):
        PiBotExecutor(sessions, None)._launch_bot_session({}, "owner", read_only=True)


def test_read_only_launch_payload_survives_private_runtime_filter(tmp_path, monkeypatch):
    from mms_web.drivers import launch_bridge

    (tmp_path / "config.toml").write_text("")
    monkeypatch.setattr(launch_bridge, "pi_runtime", lambda: ("/bin/pi", "/bin/node"))
    monkeypatch.setattr(launch_bridge, "_windows_shell_tool_args", lambda: ["--tools", "read,powershell,write"])
    plan = launch_bridge.build_pi_launch_plan({"model": "m"},
        {"auth_mode": "api_key", "_webConfigRoot": str(tmp_path), "_webReadOnly": True}, str(tmp_path))
    payload = json.loads(__import__("pathlib").Path(plan.cmd[-1]).read_text())
    assert payload["readOnly"] is True
    assert "--tools" not in payload["extraArgs"]
    assert "_webReadOnly" not in payload["runtime"]


def capture_native_launch(monkeypatch, read_only, extra_args=None):
    import mms_pi_support

    captured = {}
    monkeypatch.setattr(mms_pi_support, "_pi_gateway_env", lambda *_a, **_k: {
        "MMS_PI_PROVIDER": "exact-provider", "MMS_PI_SKILLS_OVERLAY": "/unsafe-skills"})
    monkeypatch.setattr(mms_pi_support, "_pi_effective_selected_model", lambda *_: "exact-model")
    monkeypatch.setattr(mms_pi_support, "_glint_pi_bridge_path", lambda _: "/glint.ts")
    monkeypatch.setattr(mms_pi_support, "pi_btw_extension_path", lambda *_a, **_k: "/btw.ts")
    monkeypatch.setattr(mms_pi_support, "_exec_or_run", lambda cmd, env, once: captured.update(cmd=cmd))
    mms_pi_support.launch_pi({"model": "exact-model"}, {"auth_mode": "api_key", "_webReadOnly": read_only},
                             extra_args=extra_args or ["--mode", "rpc"])
    return captured["cmd"]


def test_final_native_command_enforces_read_tools_and_no_extensions(monkeypatch):
    cmd = capture_native_launch(monkeypatch, True)
    assert cmd[cmd.index("--provider") + 1] == "exact-provider"
    assert cmd[cmd.index("--model") + 1] == "exact-model"
    assert cmd[cmd.index("--tools") + 1] == "read,grep,find,ls"
    for flag in ("--no-extensions", "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes"):
        assert flag in cmd
    assert "--extension" not in cmd and "--skill" not in cmd


def test_ordinary_native_launch_keeps_extensions_and_default_tools(monkeypatch):
    cmd = capture_native_launch(monkeypatch, False)
    assert "/glint.ts" in cmd and "/btw.ts" in cmd and "/unsafe-skills" in cmd
    assert "--tools" not in cmd and "--no-extensions" not in cmd


@pytest.mark.parametrize("args", [["--tools", "write"], ["-e", "unsafe.ts"], ["--extension=unsafe.ts"], ["--skill", "unsafe"]])
def test_read_only_cannot_load_extra_tools_or_extensions(monkeypatch, args):
    with pytest.raises(ValueError, match="只读"):
        capture_native_launch(monkeypatch, True, args)
