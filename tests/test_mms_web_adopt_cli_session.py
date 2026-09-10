"""Adopting a terminal-started session into Pilot.

The terminal's transcript is copied, never shared: Pi appends to its session
file, so two processes on one file would interleave and corrupt it. Adoption
therefore continues from the same history while leaving that session alone.

Uses the task-owned fake Pi child (tests/fixtures/mms_web/pi_fake_child.py)
through the same launch_plan_builder seam the server uses.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_CHILD = str(Path(__file__).resolve().parent / "fixtures" / "mms_web" / "pi_fake_child.py")
sys.path.insert(0, str(REPO_ROOT))

from mms_web.drivers import launch_bridge  # noqa: E402
from mms_web.errors import WebError  # noqa: E402
from mms_web.sessions import SessionService  # noqa: E402


def wait_for(predicate, timeout: float = 10.0, message: str = "condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError(f"timeout waiting for {message}")


def transcript_file(root: Path, cwd: str) -> Path:
    """A Pi session file shaped the way a terminal launch leaves one."""
    rows = [
        {"type": "session", "version": 3, "id": "01a0-term",
         "timestamp": "2026-09-01T01:00:00.000Z", "cwd": cwd},
        {"type": "model_change", "provider": "newapi", "model": "glm-5.3"},
        {"type": "message", "id": "m1", "timestamp": "2026-09-01T01:01:00.000Z",
         "message": {"role": "user", "content": [{"type": "text", "text": "在终端里问的"}]}},
        {"type": "message", "id": "m2", "timestamp": "2026-09-01T01:02:00.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "先想一下"},
             {"type": "text", "text": "终端里的回答"},
             {"type": "toolCall", "id": "call-1", "name": "read",
              "arguments": {"path": "/tmp/a.txt"}}]}},
        {"type": "message", "id": "m3", "timestamp": "2026-09-01T01:03:00.000Z",
         "message": {"role": "toolResult", "toolCallId": "call-1", "toolName": "read",
                     "isError": False, "content": [{"type": "text", "text": "文件内容"}]}},
        # Killed mid-tool: this call never got a result.
        {"type": "message", "id": "m4", "timestamp": "2026-09-01T01:04:00.000Z",
         "message": {"role": "assistant", "content": [
             {"type": "toolCall", "id": "call-2", "name": "bash",
              "arguments": {"command": "sleep 900"}}]}},
    ]
    path = root / "2026-09-01T01-00-00-000Z_01a0-term.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")
    return path


class RuntimeRootCatalog:
    """Mirrors the real catalog: a fresh private runtime root per resolve."""

    def __init__(self, state_root: Path, cwd: str) -> None:
        self._state_root = state_root
        self._cwd = cwd
        self.roots: list[Path] = []

    def resolve_launch(self, preset_id: str, workspace_id: str) -> dict:
        root = self._state_root / "runtimes" / f"r{len(self.roots)}"
        root.mkdir(parents=True, exist_ok=True)
        self.roots.append(root)
        return {
            "harness": "pi",
            "modelInfo": {"model": "fake-model"},
            "runtime": {"id": "prov", "name": "Fixture Provider", "channel": "chat",
                        "auth_mode": "api_key", "_webConfigRoot": str(root)},
            "launchOptions": {"supportedThinkingLevels": ["low", "high"]},
            "cwd": self._cwd,
        }


@pytest.fixture()
def adopting(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mms_web.sessions.probe_mms_pi_seam", lambda: {"available": True, "injected": True}
    )
    gateway = tmp_path / "gateway"
    gateway.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    catalog = RuntimeRootCatalog(tmp_path / "state", str(fallback))
    service = SessionService(
        config_root=tmp_path / "config",
        state_root=tmp_path / "state",
        catalog=catalog,
        launch_plan_builder=launch_bridge.fixed_command_plan_builder(
            [sys.executable, FIXTURE_CHILD]
        ),
        real_launch=True,
    )
    path = transcript_file(gateway, str(work))
    row = {"piSessionId": "01a0-term", "title": "在终端里问的", "cwd": str(work),
           "path": str(path), "workspaceId": "ws"}
    yield service, row, path, work, fallback, catalog
    service.close()


def test_adoption_continues_the_terminal_history_here(adopting):
    service, row, path, work, _fallback, _catalog = adopting
    before = path.read_bytes()

    detail = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                 "workspaceId": "ws"})
    session = detail["session"]
    assert session["state"] == "idle"
    assert session["title"] == "在终端里问的"
    # The Pi session it continues, which is what hides the read-only row.
    assert session["piSessionId"] == "01a0-term"
    # It starts where the terminal was working, not in the workspace root.
    assert session["cwd"] == str(work)

    kinds = [e["kind"] for e in detail["events"]]
    assert kinds == ["user", "assistant", "tool", "tool", "notice"]
    assert detail["events"][0]["text"] == "在终端里问的"
    assert detail["events"][1]["thinking"] == "先想一下"
    # The original turn times survive; they are not restamped to now.
    assert detail["events"][0]["createdAt"] == "2026-09-01T01:01:00.000Z"
    assert [e["sequence"] for e in detail["events"]] == [1, 2, 3, 4, 5]
    finished, unfinished = detail["events"][2], detail["events"][3]
    assert (finished["title"], finished["status"], finished["text"]) == ("read", "done", "文件内容")
    # Nothing here will ever report that call complete, so it is not "done".
    assert unfinished["status"] == "error"

    # Read-only, still: the terminal's own transcript is byte-identical.
    assert path.read_bytes() == before


def test_the_adopted_session_can_be_sent_to_and_the_original_stays_put(adopting):
    service, row, path, _work, _fallback, _catalog = adopting
    detail = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                 "workspaceId": "ws"})
    session_id = detail["session"]["id"]
    before = path.read_bytes()

    service.send(session_id, {"requestId": "send-1", "text": "接着做"})
    wait_for(lambda: service.get_session(session_id)["session"]["state"] == "idle",
             message="agent settle")
    events = service.get_session(session_id)["events"]
    assert "echo: 接着做" in [e["text"] for e in events if e["kind"] == "assistant"]
    # The whole point of copying: the terminal's session is untouched.
    assert path.read_bytes() == before


def test_pi_is_started_on_the_copy_not_on_the_terminals_file(adopting):
    service, row, path, _work, _fallback, catalog = adopting
    service.adopt(row, {"requestId": "adopt-1", "presetId": "preset", "workspaceId": "ws"})
    copy = catalog.roots[0] / "conversation.jsonl"
    assert copy.read_bytes() == path.read_bytes()
    # Resume must find the same copy again, not a blank session.
    saved = json.loads((catalog.roots[0] / "resume.json").read_text(encoding="utf-8"))
    assert saved["cwd"] == row["cwd"]


def test_the_same_request_replays_instead_of_starting_a_second_process(adopting):
    service, row, _path, _work, _fallback, _catalog = adopting
    first = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                "workspaceId": "ws"})
    again = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                "workspaceId": "ws"})
    assert again["session"]["id"] == first["session"]["id"]
    assert len(service.list_sessions()) == 1


def test_a_deleted_working_folder_falls_back_and_says_so(adopting):
    service, row, _path, work, fallback, _catalog = adopting
    row = {**row, "cwd": str(work / "gone")}
    detail = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                 "workspaceId": "ws"})
    assert detail["session"]["cwd"] == str(fallback)
    assert "原来的工作目录已经不在" in detail["events"][-1]["text"]


def test_a_transcript_that_is_gone_is_refused(adopting):
    service, row, path, _work, _fallback, _catalog = adopting
    path.unlink()
    with pytest.raises(WebError) as caught:
        service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                            "workspaceId": "ws"})
    assert caught.value.code == "NOT_FOUND"


def test_an_effort_the_channel_does_not_support_is_refused(adopting):
    service, row, _path, _work, _fallback, _catalog = adopting
    with pytest.raises(WebError) as caught:
        service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                            "workspaceId": "ws", "thinkingLevel": "max"})
    assert caught.value.code == "EFFORT_UNSUPPORTED"
    # A refused adoption leaves no half-made session behind.
    assert service.list_sessions() == []


def test_an_adopted_session_hides_the_read_only_row_for_the_same_conversation(tmp_path):
    """One conversation, one row: the live Pilot session replaces the copy."""
    from mms_web.server import WebApplication

    config_root = tmp_path / "mms-next"
    sessions = config_root / "pi-gateway" / "sessions"
    sessions.mkdir(parents=True)
    transcript_file(sessions, str(tmp_path))

    app = WebApplication(state_root=tmp_path / "state", config_root=config_root)
    try:
        assert [s["id"] for s in app.all_sessions(include_cli=True)] == ["cli:01a0-term"]

        class Claimed:
            def list_sessions(self):
                return [{"id": "s-abc", "piSessionId": "01a0-term",
                         "updatedAt": "2026-09-02T00:00:00.000Z", "owner": "web"}]

            def close(self):
                pass

        app.sessions = Claimed()
        assert [s["id"] for s in app.all_sessions(include_cli=True)] == ["s-abc"]
    finally:
        app.close()


def test_only_a_terminal_session_can_be_adopted(tmp_path):
    from mms_web.server import WebApplication

    app = WebApplication(state_root=tmp_path / "state", config_root=tmp_path / "config")
    try:
        with pytest.raises(WebError) as caught:
            app.adopt_cli_session("s-already-ours", {"presetId": "preset"})
        assert caught.value.code == "NOT_FOUND"
    finally:
        app.close()


def test_a_half_written_last_line_does_not_travel_into_the_copy(adopting):
    """The terminal may be mid-append while this reads, and Pi has to be able
    to parse every line of the file it is handed."""
    service, row, path, _work, _fallback, catalog = adopting
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type": "message", "id": "m9", "mess')

    detail = service.adopt(row, {"requestId": "adopt-1", "presetId": "preset",
                                 "workspaceId": "ws"})
    copy = catalog.roots[0] / "conversation.jsonl"
    for line in copy.read_text(encoding="utf-8").splitlines():
        json.loads(line)
    assert copy.read_bytes() != path.read_bytes()
    # And the partial line is not shown as a turn either.
    assert [e["kind"] for e in detail["events"]][:4] == ["user", "assistant", "tool", "tool"]
