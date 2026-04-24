import json
from pathlib import Path


def test_write_session_packet_uses_toon_without_secrets(monkeypatch, tmp_path):
    from mms_session_packet import write_session_packet

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)
    session_home = tmp_path / "session-home"

    env = write_session_packet(
        session_home,
        cli="codex",
        runtime={
            "id": "relay-a",
            "name": "Relay A",
            "auth_mode": "api_key",
            "api_key": "sk-secret-value",
            "proxy": "http://user:pass@proxy.example.com:7890",
            "caveman_mode": "enable",
        },
        model_info={"model": "gpt-5.4", "lb_light": "gpt-5.4-mini"},
        features={"agent_browser": True},
    )

    packet_path = Path(env["MMS_SESSION_PACKET_JSON"])
    toon_path = Path(env["MMS_SESSION_PACKET_TOON"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    toon_text = toon_path.read_text(encoding="utf-8")
    serialized = packet_path.read_text(encoding="utf-8") + toon_text

    assert env["MMS_SESSION_PACKET_FORMAT"] == "toon"
    assert env["MMS_SESSION_PACKET_PATH"] == str(toon_path)
    assert toon_text.startswith("TOON:\n")
    assert packet["cli"] == "codex"
    assert packet["runtime"]["id"] == "relay-a"
    assert packet["model"]["primary"] == "gpt-5.4"
    assert {"slot": "lb_light", "model": "gpt-5.4-mini"} in packet["model"]["slots"]
    assert "sk-secret-value" not in serialized
    assert "proxy.example.com" not in serialized
