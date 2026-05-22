import json
from pathlib import Path


def test_write_file_only_rescue_redacts_and_indexes(tmp_path):
    from mms_rescue import is_secret_safe, write_file_only_rescue

    repo = tmp_path / "repo"
    config_root = tmp_path / "mms-config"
    repo.mkdir()
    event = {
        "registry_revision": "reg_test",
        "failed": {
            "model": "gpt-5.5",
            "provider_id": "private-relay",
            "status_code": 429,
            "error_type": "rate_limit",
            "error_summary": "Authorization: Bearer sk-secret-token-1234567890 hit quota",
        },
        "git": {"status_short": " M mms_bridge.py"},
        "next_action": "Resume from rescue packet.",
    }

    payload = write_file_only_rescue(
        event,
        repo_root=repo,
        config_root=config_root,
        raw_artifacts={
            "upstream-response.json": {
                "Authorization": "Bearer sk-raw-secret-token-1234567890",
                "message": "quota",
            }
        },
        created_at="2026-05-22T01:00:00+00:00",
    )

    latest_json = repo / ".mms" / "rescue" / "latest.json"
    latest_md = repo / ".mms" / "rescue" / "latest.md"
    index_path = config_root / "rescue" / "index.jsonl"
    assert latest_json.exists()
    assert latest_md.exists()
    assert index_path.exists()

    latest_text = latest_json.read_text(encoding="utf-8")
    raw_text = Path(payload["artifacts"]["raw_written"][0]).read_text(encoding="utf-8")
    index_text = index_path.read_text(encoding="utf-8")
    assert "sk-secret" not in latest_text
    assert "sk-raw-secret" not in raw_text
    assert "Authorization" not in index_text
    assert is_secret_safe(latest_text)
    assert is_secret_safe(raw_text)
    assert json.loads(latest_text)["rescue_level"] == "L3_file_only"
    assert json.loads(index_text.splitlines()[0])["schema"] == "mms.rescue_index.v1"


def test_write_file_only_rescue_skips_auth_bearing_raw_files(tmp_path):
    from mms_rescue import write_file_only_rescue

    repo = tmp_path / "repo"
    repo.mkdir()
    payload = write_file_only_rescue(
        {"failed": {"model": "glm-5.1"}},
        repo_root=repo,
        config_root=tmp_path / "mms-config",
        raw_artifacts={
            "~/.codex/auth.json": '{"access_token":"secret"}',
            "safe-log.txt": "plain error",
        },
        created_at="2026-05-22T01:01:00+00:00",
    )

    assert payload["artifacts"]["raw_skipped_auth_bearing"] == ["~/.codex/auth.json"]
    assert len(payload["artifacts"]["raw_written"]) == 1
    assert Path(payload["artifacts"]["raw_written"][0]).name == "safe-log.txt"


def test_rescue_config_root_uses_real_home_not_gateway_session(monkeypatch, tmp_path):
    from mms_rescue import resolve_real_mms_config_dir

    real_home = tmp_path / "home"
    session_home = real_home / ".config" / "mms" / "codex-gateway" / "s" / "12345"
    monkeypatch.delenv("MMS_REAL_HOME", raising=False)
    monkeypatch.delenv("REAL_HOME", raising=False)
    monkeypatch.delenv("ORIGINAL_HOME", raising=False)
    monkeypatch.setenv("HOME", str(session_home))

    assert resolve_real_mms_config_dir() == real_home / ".config" / "mms"
