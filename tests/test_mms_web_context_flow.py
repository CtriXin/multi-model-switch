import hashlib
import json
import subprocess
import sys

import pytest

from mms_web.drivers.pi_rpc import PiRpcDriver
from mms_web.drivers.launch_bridge import probe_mms_pi_seam
from mms_web.errors import WebError
from mms_web.server import WebApplication
from test_mms_web_configuration_flow import connection, model_service
from test_mms_web_interactions import local_app, settle
from test_mms_web_project_materials import save
from test_mms_web_sessions_service import launch_ok, make_service, seeded_seam


@pytest.mark.skipif(not probe_mms_pi_seam()["available"], reason="compatible Pi required")
def test_skill_source_tracks_the_winning_entry_not_its_symlink_target(local_app, tmp_path):
    app, workspace, root = local_app
    shared = tmp_path / "home/.agents/skills"
    shared.mkdir(parents=True)
    implementation = root / "shared-implementation"
    implementation.mkdir()
    (implementation / "SKILL.md").write_text("---\nname: shared-guide\ndescription: Shared fixture\n---\nShared body\n")
    (shared / "shared-guide").symlink_to(implementation, target_is_directory=True)
    old = shared / "duplicate"; old.mkdir()
    (old / "SKILL.md").write_text("---\nname: duplicate\ndescription: Global fixture\n---\nGlobal body\n")
    new = root / ".agents/skills/duplicate"; new.mkdir(parents=True)
    (new / "SKILL.md").write_text("---\nname: duplicate\ndescription: Project fixture\n---\nProject body\n")
    skills = {s["name"]: s for s in app.sessions.skills.snapshot(workspace["id"])["skills"]}
    assert skills["shared-guide"]["source"] == "共享"
    assert skills["shared-guide"]["sourceRoot"] == str(shared)
    assert skills["duplicate"]["source"] == "项目"
    assert skills["duplicate"]["overrides"] == [str(old)]
    content, selected = app.sessions.skills.prepare([skills["duplicate"]["id"]], workspace["id"])
    assert "Project body" in content and "Global body" not in content
    assert selected[0]["filePath"] == str(new / "SKILL.md")


@pytest.mark.skipif(not probe_mms_pi_seam()["available"], reason="compatible Pi required")
def test_native_project_materials_and_explicit_sources_follow_each_request(local_app, tmp_path):
    app, workspace, root = local_app
    (root / "AGENTS.md").write_text("PRIVATE_NATIVE_RULE_MARKER: only a fixture rule.\n")
    guide = root / ".agents/skills/context-guide/SKILL.md"
    guide.parent.mkdir(parents=True)
    guide.write_text("---\nname: context-guide\ndescription: Context source fixture\n---\nUse the guide marker as source.\n")
    skill = next(s for s in app.post(["skills"], {"workspaceId": workspace["id"]})["skills"] if s["name"] == "context-guide")
    note = save(app, workspace, content="MATERIAL_ALPHA_FIRST")['items'][0]
    with model_service() as (url, records):
        connection(app, "Context fixture", url, "context-fixture-key")
        first = app.post(["sessions"], {"requestId": "context-start", "workspaceId": workspace["id"],
            "presetId": "web:pi:context-fixture:gpt-5", "prompt": "First context request", "skills": [skill["id"]], "references": ["notes.md"]})
        sid = first["session"]["id"]
        detail = settle(app, sid)
        event = next(e for e in detail["events"] if e["kind"] == "user")
        usage = event["contextUsage"]
        assert usage["state"] == "submitted" and usage["cwd"] == str(root)
        assert usage["consumed"] is True
        assert usage["native"]["available"] is True
        assert any(r["path"] == str(root / "AGENTS.md") and r["state"] == "loaded" for r in usage["native"]["rules"])
        assert "PRIVATE_NATIVE_RULE_MARKER" not in json.dumps(usage["native"])
        assert any(s["name"] == "context-guide" and not s.get("invoked") for s in usage["native"]["skills"])
        sources = {item["kind"]: item for item in usage["items"]}
        assert set(sources) == {"skill", "reference", "material"}
        assert sources["skill"]["loadState"] == "loaded" and not sources["skill"].get("invoked")
        assert sources["reference"]["loadState"] == "referenced"
        assert sources["skill"]["filePath"] == str(guide)
        assert sources["skill"]["sha256"] == hashlib.sha256(guide.read_bytes()).hexdigest()
        assert sources["material"]["revision"] == 1 and sources["reference"]["path"] == "notes.md"
        def last_user():
            body = [r["body"] for r in records if r["method"] == "POST"][-1]
            return json.dumps([m for m in body["messages"] if m["role"] == "user"][-1], ensure_ascii=False)
        assert "MATERIAL_ALPHA_FIRST" in last_user() and "Use the guide marker as source." in last_user()
        save(app, workspace, id=note["id"], content="MATERIAL_ALPHA_SECOND")
        app.post(["sessions", sid, "messages"], {"requestId": "context-second", "text": "Second context request"})
        detail = settle(app, sid)
        assert "MATERIAL_ALPHA_SECOND" in last_user() and "MATERIAL_ALPHA_FIRST" not in last_user()
        assert [e for e in detail["events"] if e["kind"] == "user"][-1]["contextUsage"]["items"][0]["revision"] == 2
        save(app, workspace, id=note["id"], content="MATERIAL_ALPHA_SECOND", enabled=False)
        app.post(["sessions", sid, "messages"], {"requestId": "context-disabled", "text": "No additional material now"})
        detail = settle(app, sid)
        assert "MATERIAL_ALPHA" not in last_user()
        assert [e for e in detail["events"] if e["kind"] == "user"][-1]["contextUsage"]["items"] == []
        save(app, workspace, id=note["id"], content="MATERIAL_ALPHA_SECOND", enabled=True)
        other_root = tmp_path / "other-project"
        other_root.mkdir()
        other = app.post(["workspaces"], {"path": str(other_root)})
        second = app.post(["sessions"], {"requestId": "other-project", "workspaceId": other["id"],
            "presetId": "web:pi:context-fixture:gpt-5", "prompt": "Separate project"})
        other_detail = settle(app, second["session"]["id"])
        assert "MATERIAL_ALPHA" not in last_user()
        assert next(e for e in other_detail["events"] if e["kind"] == "user")["contextUsage"]["items"] == []
        app.post(["sessions", sid, "messages"], {"requestId": "native-skill-command", "text": "/skill:context-guide Explain this fixture"})
        invoked_detail = settle(app, sid)
        invoked = [e for e in invoked_detail["events"] if e["kind"] == "user"][-1]["contextUsage"]
        assert invoked["consumed"] is True
        assert any(s["name"] == "context-guide" and s.get("invoked") and s.get("proof") == "skill_command" for s in invoked["native"]["skills"])
        app.post(["sessions", sid, "messages"], {"requestId": "web-skill-command", "text": "Use the selected guide", "skills": [skill["id"]], "skillInvocation": skill["id"]})
        web_invoked = [e for e in settle(app, sid)["events"] if e["kind"] == "user"][-1]["contextUsage"]
        assert web_invoked["items"][0]["invoked"] is True
        assert web_invoked["items"][0]["proof"] == "web_skill_command"
        # Old submitted source records survive an edit, disable and process restart.
        state = app.state_root
        app.close()
        restored = WebApplication(state_root=state)
        try:
            original = next(e for e in restored.get(["sessions", sid])["events"] if e["kind"] == "user")
            assert original["contextUsage"] == usage
        finally:
            restored.close()


@pytest.mark.parametrize("failure,expected", [("rejected", "failed"), ("timeout", "uncertain")])
def test_source_record_does_not_claim_submission_after_rpc_failure(tmp_path, seeded_seam, failure, expected):
    service, drivers = make_service(tmp_path)
    try:
        detail = launch_ok(service)
        if failure == "timeout": drivers[0].timeout_next_prompt = True
        else: drivers[0].fail_next_prompt = {"success": False}
        with pytest.raises(WebError):
            service.send(detail["session"]["id"], {"requestId": "failed-context-send", "text": "Not confirmed"})
        event = [e for e in service.get_session(detail["session"]["id"])["events"] if e["kind"] == "user"][-1]
        assert event["contextUsage"]["state"] == expected and event["status"] == "error"
    finally:
        service.close()


def test_process_eof_after_consuming_prompt_without_ack_is_uncertain(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    marker = tmp_path / "consumed-request.json"
    def spawn(plan, sink):
        code = "import json, pathlib, sys; value=json.loads(sys.stdin.readline()); pathlib.Path(sys.argv[1]).write_text(json.dumps(value)); sys.exit(0)"
        child = subprocess.Popen([sys.executable, "-u", "-c", code, str(marker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return PiRpcDriver(child, sink, response_timeout=2)
    service._spawn_driver = spawn
    try:
        result = launch_ok(service, prompt="ACTUALLY_CONSUMED_NO_ACK")
        assert json.loads(marker.read_text())["message"] == "ACTUALLY_CONSUMED_NO_ACK"
        event = next(item for item in result["events"] if item["kind"] == "user")
        assert event["contextUsage"]["state"] == "uncertain"
    finally:
        service.close()


def test_partial_stdin_write_broken_pipe_is_unconfirmed(tmp_path, seeded_seam):
    service, _ = make_service(tmp_path)
    marker = tmp_path / "consumed-prefix.bin"
    observed = []
    def spawn(plan, sink):
        code = "import os,pathlib,sys,time; value=os.read(0,4096); pathlib.Path(sys.argv[1]).write_bytes(value); os.close(0); time.sleep(0.2)"
        child = subprocess.Popen([sys.executable, "-u", "-c", code, str(marker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        driver = PiRpcDriver(child, sink, response_timeout=2)
        original = driver.send_prompt
        def send(text, **kwargs):
            try:
                return original(text, **kwargs)
            except Exception as exc:
                observed.append(exc)
                raise
        driver.send_prompt = send
        return driver
    service._spawn_driver = spawn
    try:
        result = launch_ok(service, prompt="PARTIAL_BODY_" + "X" * 1_000_000)
        assert b"PARTIAL_BODY_" in marker.read_bytes()
        assert observed and isinstance(observed[0].__cause__, BrokenPipeError)
        event = next(item for item in result["events"] if item["kind"] == "user")
        notice = next(item for item in result["events"] if item["kind"] == "notice" and item.get("status") == "error")
        print("prefixBytes=" + str(marker.stat().st_size) + "; transport=" + repr(observed[0]) + "; state=" + event["contextUsage"]["state"] + "; notice=" + notice["text"])
        assert event["contextUsage"]["state"] == "uncertain"
    finally:
        service.close()
