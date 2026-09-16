"""Contract tests for 4.x ↔ 5.x channel switching (T6a).

Two hard rules, pinned as tests so a future change goes red first:

1. The Bot store schemas never advance. ``bots/state.json`` stays schema 2,
   bot memory stays ``SCHEMA = 1`` and the notify stores stay schema 1. New
   fields arrive by tolerant reads only, because an older 5.x install must
   keep reading what a newer 5.x wrote. On the 4.x line these modules do not
   exist at all, and the inverse rule is pinned instead: nothing under
   ``mms_web/`` may reference the ``bots/`` state subtree.

2. A state root written by 5.x must be *ignored* by 4.x, never an error:
   the process boots, bootstrap answers 200 and the session list works even
   when ``bots/`` contains bytes this line cannot parse.
"""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from mms_web.server import WebApplication, create_server

REPO_ROOT = Path(__file__).resolve().parents[1]
MMS_WEB = REPO_ROOT / "mms_web"

BOT_STORE_MODULES = ("bots.py", "bot_memory.py", "bot_notify.py")


def test_bot_store_schema_literals_are_pinned():
    present = {name: MMS_WEB / name for name in BOT_STORE_MODULES if (MMS_WEB / name).exists()}
    if not present:
        # 4.x line: the whole bots/ state subtree belongs to the other line
        # and must stay invisible here — no store module, no path literal.
        for path in sorted(MMS_WEB.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert '"bots"' not in text, f"{path.name} references the bots state subtree"
        return
    assert set(present) == set(BOT_STORE_MODULES), f"partial Bot store: {sorted(present)}"

    bots = present["bots.py"].read_text(encoding="utf-8")
    assert 'data.get("schema") != 2' in bots, "bots.py no longer hard-validates schema 2"
    assert '"schema": 2' in bots, "bots.py no longer persists schema 2"

    memory = present["bot_memory.py"].read_text(encoding="utf-8")
    assert "SCHEMA = 1" in memory, "bot_memory.py SCHEMA advanced past 1"

    notify = present["bot_notify.py"].read_text(encoding="utf-8")
    assert notify.count('"schema": 1') == 2, "bot_notify.py no longer persists both stores at schema 1"


class ForeignStateRootIgnoreTests(unittest.TestCase):
    """A 5.x-shaped state root, including unparsable Bot bytes, boots clean."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "public").mkdir()
        (self.root / "public/index.html").write_text("<h1>MMS</h1>")
        state_root = self.root / "state"
        # The other line's store: valid shape plus deliberately broken bytes.
        bot_root = state_root / "bots"
        (bot_root / "memory" / "bot_1").mkdir(parents=True)
        (bot_root / "state.json").write_text(
            json.dumps({"schema": 2, "bots": {"bot_1": {}}, "tasks": {},
                        "messages": {}, "artifacts": {}}),
            encoding="utf-8",
        )
        (bot_root / "memory" / "bot_1" / "memory.json").write_bytes(b"\xff\xfe not json")
        self.bot_files = {
            path: path.read_bytes()
            for path in sorted(bot_root.rglob("*"))
            if path.is_file()
        }
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

    def test_bootstrap_and_session_list_survive_foreign_state(self):
        for path in ("/api/v1/bootstrap", "/api/v1/sessions", "/api/v1/ui-preferences"):
            status, body = self.request(path)
            self.assertEqual(status, 200, f"{path}: {body[:200]!r}")

    def test_foreign_files_are_never_touched(self):
        self.request("/api/v1/bootstrap")
        self.request("/api/v1/sessions")
        for path, content in self.bot_files.items():
            self.assertTrue(path.is_file(), f"{path} disappeared")
            self.assertEqual(path.read_bytes(), content, f"{path} was rewritten")


if __name__ == "__main__":
    unittest.main()
