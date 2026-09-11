"""Borrowing image reading across harnesses.

Pi has had the relay for a while through its own extension. Claude Code and
OpenCode reach the same pool over MCP. The rule is identical everywhere: a
model that cannot read images gets a tool that forwards the picture to one that
can, on the same channel, and nothing is added when it is not needed.
"""

import json
import os
import stat

import pytest

import mms_capability_resolver
import mms_vision_relay
from test_pi_vision_relay import _vision_runtime


@pytest.fixture(autouse=True)
def isolate_capability_root(monkeypatch):
    """Answer from the provider profiles alone.

    Whether a model reads images otherwise depends on the approved bundle the
    developer's own config root happens to hold, so these would pass on one
    machine and fail on another. The sibling Pi suite isolates the same way.
    """
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})


def _catalog(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _model_ids(catalog):
    return sorted(
        str(model.get("id"))
        for provider in catalog["providers"].values()
        for model in provider["models"]
    )


def test_a_model_that_reads_images_gets_no_relay(monkeypatch, tmp_path):
    runtime = _vision_runtime(monkeypatch, ["minimax-m3", "deepseek-v4-pro"])

    assert mms_vision_relay.relay_needed(runtime, "minimax-m3") is False
    assert mms_vision_relay.write_relay_catalog(mms_vision_relay.session_catalog_path(tmp_path), runtime, "minimax-m3") is None


def test_a_text_only_model_gets_a_catalog_of_this_channel(monkeypatch, tmp_path):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])

    assert mms_vision_relay.relay_needed(runtime, "deepseek-v4-pro") is True
    path = mms_vision_relay.write_relay_catalog(mms_vision_relay.session_catalog_path(tmp_path), runtime, "deepseek-v4-pro")
    assert path and os.path.isfile(path)

    catalog = _catalog(path)
    # The catalog is the channel, not a curated list: the relay picks the
    # image-capable entries out of it the same way Pi does.
    assert "minimax-m3" in _model_ids(catalog)
    vision = [
        model
        for provider in catalog["providers"].values()
        for model in provider["models"]
        if "image" in (model.get("input") or [])
    ]
    assert [model["id"] for model in vision] == ["minimax-m3"]


def test_the_catalog_carries_a_key_so_it_stays_owner_only(monkeypatch, tmp_path):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    path = mms_vision_relay.write_relay_catalog(mms_vision_relay.session_catalog_path(tmp_path), runtime, "deepseek-v4-pro")

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "sk-test" in open(path, encoding="utf-8").read()


def test_a_channel_with_nothing_that_sees_gets_no_relay(monkeypatch, tmp_path):
    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "glm-5.2"])

    assert mms_vision_relay.relay_needed(runtime, "deepseek-v4-pro") is False
    assert mms_vision_relay.write_relay_catalog(mms_vision_relay.session_catalog_path(tmp_path), runtime, "deepseek-v4-pro") is None


def test_claude_gets_the_relay_server_only_when_it_needs_one(monkeypatch, tmp_path):
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])

    needed = mms_launchers._inject_vision_relay_mcp_server(
        {}, runtime, "deepseek-v4-pro", session_home=tmp_path / "text-only"
    )
    server = needed["mcpServers"]["vision"]
    assert server["command"] == "node"
    assert server["args"][0].endswith("mms-vision-mcp.mjs")
    assert os.path.isfile(server["env"][mms_vision_relay.RELAY_CONFIG_ENV])

    not_needed = mms_launchers._inject_vision_relay_mcp_server(
        {}, runtime, "minimax-m3", session_home=tmp_path / "multimodal"
    )
    assert "mcpServers" not in not_needed


def test_a_stale_relay_is_removed_rather_than_left_behind(monkeypatch, tmp_path):
    """Switching to a model that sees must take the tool away again."""
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    state = {"mcpServers": {"vision": {"command": "node"}, "other": {"command": "node"}}}

    result = mms_launchers._inject_vision_relay_mcp_server(
        state, runtime, "minimax-m3", session_home=tmp_path / "switch"
    )

    assert "vision" not in result["mcpServers"]
    assert "other" in result["mcpServers"]


def test_disabling_the_surface_keeps_the_relay_out(monkeypatch, tmp_path):
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    runtime["disabled_session_surfaces"] = {"mcp": ["vision"]}

    result = mms_launchers._inject_vision_relay_mcp_server(
        {},
        runtime,
        "deepseek-v4-pro",
        session_home=tmp_path / "disabled",
        disabled_session_surfaces=runtime["disabled_session_surfaces"],
    )

    assert "mcpServers" not in result


def test_opencode_config_carries_the_relay_only_when_needed(monkeypatch, tmp_path):
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])

    relay = mms_launchers._opencode_vision_relay_mcp(
        tmp_path / "text-only" / "opencode.json", runtime, "deepseek-v4-pro"
    )
    assert relay and relay["vision"]["type"] == "local"
    assert relay["vision"]["command"][0] == "node"
    assert relay["vision"]["environment"][mms_vision_relay.RELAY_CONFIG_ENV]

    payload = mms_launchers._build_opencode_config_payload(runtime, "deepseek-v4-pro")
    assert "mcp" not in payload

    content = json.loads(
        mms_launchers._build_opencode_config_content(
            runtime, "deepseek-v4-pro", vision_relay_mcp=relay
        )
    )
    assert content["mcp"]["vision"]["enabled"] is True

    assert (
        mms_launchers._opencode_vision_relay_mcp(
            tmp_path / "multimodal" / "opencode.json", runtime, "minimax-m3"
        )
        is None
    )


def test_the_relay_server_and_the_pi_extension_agree_on_endpoints():
    """Two files build the same endpoints; they must not drift apart."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server = open(os.path.join(root, "scripts", "mms-vision-mcp.mjs"), encoding="utf-8").read()
    extension = open(os.path.join(root, "scripts", "pi-vision-extension.ts"), encoding="utf-8").read()

    for rule in (
        'if (api === "anthropic-messages") return `${b}/v1/messages`;',
        'if (api === "openai-completions")',
        'if (api === "openai-responses")',
        'b.endsWith("/v1") ? `${b}/chat/completions` : `${b}/v1/chat/completions`',
        'b.endsWith("/v1") ? `${b}/responses` : `${b}/v1/responses`',
    ):
        assert rule in server, rule
        assert rule in extension, rule


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node is not installed")
def test_the_relay_server_picks_a_vision_model_and_never_returns_the_key(tmp_path):
    """The whole point, end to end: an image goes out, text comes back.

    Also pins the two things that would be silently wrong: it must choose the
    model that declares image input rather than the first one listed, and the
    channel key must never appear in anything the main model can read.
    """
    import http.server
    import shutil
    import subprocess
    import threading

    seen = {}

    class Upstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["model"] = body.get("model")
            seen["had_image"] = "image_url" in json.dumps(body)
            seen["authorization"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = {"choices": [{"delta": {"content": "a red square"}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode())

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        catalog = tmp_path / "models.json"
        catalog.write_text(
            json.dumps(
                {
                    "providers": {
                        "demo": {
                            "name": "demo",
                            "api": "openai-completions",
                            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1",
                            "apiKey": "sk-relay-secret",
                            "models": [
                                {"id": "text-only", "input": ["text"]},
                                {"id": "sees-images", "input": ["text", "image"]},
                            ],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        image = tmp_path / "shot.png"
        image.write_bytes(bytes.fromhex("89504e470d0a1a0a"))

        requests = "\n".join(
            json.dumps(message)
            for message in (
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "describe_image",
                        "arguments": {"path": str(image), "question": "what is this"},
                    },
                },
            )
        )
        result = subprocess.run(
            [shutil.which("node"), mms_vision_relay.relay_server_path()],
            input=requests + "\n",
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, mms_vision_relay.RELAY_CONFIG_ENV: str(catalog)},
        )
    finally:
        server.shutdown()
        server.server_close()

    replies = {json.loads(line)["id"]: json.loads(line) for line in result.stdout.splitlines() if line.strip()}
    assert replies[1]["result"]["serverInfo"]["name"] == "mms-vision"
    assert [tool["name"] for tool in replies[2]["result"]["tools"]] == ["describe_image"]

    call = replies[3]["result"]
    assert call["isError"] is False
    assert "a red square" in call["content"][0]["text"]
    assert seen["model"] == "sees-images"
    assert seen["had_image"] is True
    assert seen["authorization"] == "Bearer sk-relay-secret"
    assert "sk-relay-secret" not in result.stdout


def test_two_channels_do_not_share_one_catalog(monkeypatch, tmp_path):
    """OpenCode keeps its configs in one shared directory, one per channel.

    A single catalog file there would hand the second channel's key to the
    first, so the catalog is named after the config it serves.
    """
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "minimax-m3"])
    exports = tmp_path / "exports"

    first = mms_launchers._opencode_vision_relay_mcp(
        exports / "channel-a-deepseek.json", runtime, "deepseek-v4-pro"
    )
    second = mms_launchers._opencode_vision_relay_mcp(
        exports / "channel-b-deepseek.json", runtime, "deepseek-v4-pro"
    )

    first_path = first["vision"]["environment"][mms_vision_relay.RELAY_CONFIG_ENV]
    second_path = second["vision"]["environment"][mms_vision_relay.RELAY_CONFIG_ENV]
    assert first_path != second_path
    assert os.path.isfile(first_path) and os.path.isfile(second_path)


def test_the_pilot_vision_toggle_reaches_the_new_harnesses(monkeypatch, tmp_path):
    """Ticking "can read images" in Pilot must change what Claude and OpenCode get.

    That setting is written as model policy, which outranks every curated
    source. If the relay read capabilities from anywhere else, a user could tick
    the box and still have no way to use a screenshot.
    """
    import mms_launchers

    runtime = _vision_runtime(monkeypatch, ["deepseek-v4-pro", "glm-5.2"])
    # Neither model declares image input anywhere, so there is nothing to borrow.
    assert mms_vision_relay.relay_needed(runtime, "deepseek-v4-pro") is False

    monkeypatch.setattr(
        mms_capability_resolver,
        "load_default_model_policy",
        lambda: {"models": {"glm-5.2": {"capabilities": {"supports_vision": True}}}},
    )

    plan = mms_vision_relay.relay_plan(runtime, "deepseek-v4-pro")
    assert [entry["selector"] for entry in plan["pool"]] == ["glm-5.2"]

    state = mms_launchers._inject_vision_relay_mcp_server(
        {}, runtime, "deepseek-v4-pro", session_home=tmp_path / "toggled"
    )
    catalog = json.load(
        open(state["mcpServers"]["vision"]["env"][mms_vision_relay.RELAY_CONFIG_ENV], encoding="utf-8")
    )
    sees = [
        model["id"]
        for provider in catalog["providers"].values()
        for model in provider["models"]
        if "image" in (model.get("input") or [])
    ]
    assert sees == ["glm-5.2"]
