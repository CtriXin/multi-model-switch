"""Forward compatibility: sessions persisted by a newer line with an owner
this line does not know must be ignored, not adopted as plain chats.

A newer line can persist ``sessions/<id>.json`` whose meta carries an
``owner`` value this line has no concept of (plus extra keys this line does
not read). Web sessions and Bot sessions are known on this line; unknown
future owners stay out of the chat list and cannot be opened by id. Their
files are preserved. Bot details remain addressable for the workspace.

"""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from mms_web.errors import WebError
from mms_web.server import WebApplication, create_server
from mms_web.sessions import SessionService


def _write_session(state_root: Path, session_id: str, **meta_extra) -> Path:
    """Persist a session file the way any line's loader expects to find it."""
    sessions_dir = Path(state_root) / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": session_id,
        "title": f"title-{session_id}",
        "workspaceId": "ws-1",
        "harness": "pi",
        "modelName": "fake-model",
        "providerName": "fake-provider",
        "channel": "default",
        "createdAt": "2026-09-16T00:00:00+00:00",
        "updatedAt": "2026-09-16T00:00:00+00:00",
    }
    meta.update(meta_extra)
    path = sessions_dir / f"{session_id}.json"
    path.write_text(
        json.dumps({"schema": 1, "session": meta, "state": "idle", "events": []}),
        encoding="utf-8",
    )
    return path


def _make_service(state_root: Path) -> SessionService:
    class _Catalog:
        def workspaces(self):
            return []

    return SessionService(
        config_root=None,
        state_root=state_root,
        catalog=_Catalog(),
        driver_factory=None,
    )


class SessionOwnerForwardCompatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state_root = self.root / "state"
        self.web_file = _write_session(self.state_root, "sess-web-1")
        self.foreign_file = _write_session(
            self.state_root, "sess-foreign-1", owner="future-workbench", botId="bot_1",
        )
        self.foreign_bytes = self.foreign_file.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def test_session_view_echoes_persisted_owner_and_defaults_to_web(self):
        service = _make_service(self.state_root)
        views = {row["id"]: row for row in service.list_sessions()}
        self.assertEqual(views["sess-web-1"]["owner"], "web")
        self.assertEqual(views["sess-foreign-1"]["owner"], "future-workbench")

    def test_detail_query_refuses_unknown_owner(self):
        service = _make_service(self.state_root)
        detail = service.get_session("sess-web-1")
        self.assertEqual(detail["session"]["owner"], "web")
        with self.assertRaises(WebError) as caught:
            service.get_session("sess-foreign-1")
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(caught.exception.code, "NOT_FOUND")

    def test_bot_detail_remains_addressable(self):
        _write_session(self.state_root, "sess-bot-1", owner="bot", botId="bot_1")
        detail = _make_service(self.state_root).get_session("sess-bot-1")
        self.assertEqual(detail["session"]["owner"], "bot")

    def test_load_never_rewrites_the_foreign_file(self):
        service = _make_service(self.state_root)
        service.list_sessions()
        with self.assertRaises(WebError):
            service.get_session("sess-foreign-1")
        self.assertEqual(self.foreign_file.read_bytes(), self.foreign_bytes)


class SessionOwnerHttpTests(unittest.TestCase):
    """End to end over HTTP: the list hides the row, the detail 404s."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "public").mkdir()
        (self.root / "public/index.html").write_text("<h1>MMS</h1>")
        state_root = self.root / "state"
        _write_session(state_root, "sess-web-1")
        _write_session(state_root, "sess-foreign-1", owner="future-workbench", botId="bot_1")
        config_root = self.root / "config"
        config_root.mkdir()
        self.app = WebApplication(state_root=state_root, config_root=config_root)
        self.server = create_server(self.app, self.root / "public", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.close()
        self.temp.cleanup()

    def request(self, path):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        connection.request("GET", path)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_list_hides_unknown_owner_and_detail_is_not_found(self):
        status, body = self.request("/api/v1/sessions")
        self.assertEqual(status, 200)
        rows = json.loads(body)["sessions"]
        self.assertEqual([row["id"] for row in rows], ["sess-web-1"])

        status, _ = self.request("/api/v1/sessions/sess-foreign-1")
        self.assertEqual(status, 404)

        status, body = self.request("/api/v1/sessions/sess-web-1")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["session"]["owner"], "web")

    def test_bootstrap_survives_a_state_root_with_foreign_sessions(self):
        status, body = self.request("/api/v1/bootstrap")
        self.assertEqual(status, 200)
        ids = [row["id"] for row in json.loads(body)["sessions"]]
        self.assertNotIn("sess-foreign-1", ids)

    def test_cli_sessions_are_not_caught_by_the_filter(self):
        """Terminal sessions arrive on the cli_sessions path, never through
        session_view, so the owner allow-list must not touch them."""
        sessions_dir = self.root / "config" / "pi-gateway" / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "a.jsonl").write_text(
            json.dumps({"type": "session", "version": 3, "id": "cli-1",
                        "timestamp": "2026-09-10T01:00:00.000Z", "cwd": "/tmp/project"}) + "\n"
            + json.dumps({"type": "message", "id": "m1", "timestamp": "2026-09-10T02:00:00.000Z",
                          "message": {"role": "user", "content": [{"type": "text", "text": "终端里的一句"}]}}) + "\n",
            encoding="utf-8",
        )
        status, body = self.request("/api/v1/sessions?cli=1")
        self.assertEqual(status, 200)
        rows = {row["id"]: row for row in json.loads(body)["sessions"]}
        self.assertIn("cli:cli-1", rows)
        self.assertEqual(rows["cli:cli-1"]["owner"], "cli")
        self.assertIn("sess-web-1", rows)
        self.assertNotIn("sess-foreign-1", rows)


if __name__ == "__main__":
    unittest.main()


def test_retiring_bot_session_reaps_actual_child_and_preserves_history(tmp_path):
    import subprocess
    import sys
    from unittest.mock import Mock
    from mms_web.drivers.pi_rpc import PiRpcDriver
    from mms_web.bot_executor import PiBotExecutor
    state = tmp_path / "state"
    path = _write_session(state, "one-off", owner="bot", botId="bot_1")
    service = _make_service(state)
    live = service._get("one-off")
    live.events = [{"id": "answer", "kind": "assistant", "text": "saved answer"}]
    process = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    live.driver = PiRpcDriver(process, Mock())
    executor = PiBotExecutor.__new__(PiBotExecutor)
    executor.sessions = service
    try:
        assert process.poll() is None
        executor.release_session("one-off", "release-test")
        assert process.poll() is not None
        assert path.is_file()
        detail = service.get_session("one-off")
        assert detail["session"]["archived"] is True
        assert detail["events"][0]["text"] == "saved answer"
    finally:
        service.close()
        process.wait(timeout=5)


def test_retiring_session_refuses_pilot_owner(tmp_path):
    import pytest
    _write_session(tmp_path, "pilot")
    service = _make_service(tmp_path)
    try:
        with pytest.raises(WebError) as caught:
            service.retire_bot_session("pilot")
        assert caught.value.code == "INVALID_SESSION_OWNER"
        assert not service.get_session("pilot")["session"]["archived"]
    finally:
        service.close()
