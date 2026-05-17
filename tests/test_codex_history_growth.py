from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def _import_mms_launchers(monkeypatch, tmp_path):
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path / "mms-config"))
    sys.modules.pop("mms_core", None)
    sys.modules.pop("mms_launchers", None)
    import mms_launchers

    return mms_launchers


def _write_lines(path: Path, prefix: str, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{prefix}-{index}\n" for index in range(count)), encoding="utf-8")


def _write_file(path: Path, text: str, *, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_seed_codex_bounded_resume_caps_files_and_directories(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    source = tmp_path / "source" / ".codex"
    session_codex = tmp_path / "session" / ".codex"
    session_codex.mkdir(parents=True)
    _write_lines(source / "history.jsonl", "history", 8)
    _write_lines(source / "session_index.jsonl", "index", 6)
    for index in range(5):
        _write_file(
            source / "sessions" / "2026" / "04" / f"session-{index}.jsonl",
            f"session {index}\n",
            mtime=100 + index,
        )
    for index in range(3):
        _write_file(
            source / "shell_snapshots" / f"snapshot-{index}.sh",
            f"snapshot {index}\n",
            mtime=200 + index,
        )
    _write_file(source / "archived_sessions" / "old.jsonl", "old\n", mtime=1)

    monkeypatch.setenv("MMS_CODEX_HISTORY_JSONL_MAX_LINES", "3")
    monkeypatch.setenv("MMS_CODEX_SESSION_INDEX_JSONL_MAX_LINES", "2")
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "2")
    monkeypatch.setenv("MMS_CODEX_SHELL_SNAPSHOTS_MAX_FILES", "1")
    monkeypatch.setenv("MMS_CODEX_ARCHIVED_SESSIONS_MAX_FILES", "0")

    mms_launchers._seed_codex_bounded_resume([str(source)], str(session_codex))

    assert not (session_codex / "history.jsonl").is_symlink()
    assert _lines(session_codex / "history.jsonl") == ["history-5", "history-6", "history-7"]
    assert _lines(session_codex / "session_index.jsonl") == ["index-4", "index-5"]
    copied_sessions = sorted(
        path.name for path in (session_codex / "sessions").glob("2026/04/*.jsonl")
    )
    assert copied_sessions == ["session-3.jsonl", "session-4.jsonl"]
    copied_snapshots = sorted(path.name for path in (session_codex / "shell_snapshots").glob("*.sh"))
    assert copied_snapshots == ["snapshot-2.sh"]
    assert list((session_codex / "archived_sessions").glob("*")) == []
    manifest = json.loads((session_codex / "mms-resume-seed.json").read_text(encoding="utf-8"))
    assert manifest["limits"]["files"]["history.jsonl"]["max_lines"] == 3
    assert manifest["limits"]["dirs"]["sessions"]["max_files"] == 2
    assert manifest["seeded"]["files"]["history.jsonl"]["lines"] == 3
    assert manifest["seeded"]["dirs"]["sessions"]["files"] == 2


def test_seed_codex_bounded_resume_defaults_are_resume_friendly_and_skip_oversize(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    source = tmp_path / "source" / ".codex"
    session_codex = tmp_path / "session" / ".codex"
    session_codex.mkdir(parents=True)
    _write_lines(source / "history.jsonl", "history", 240)
    _write_lines(source / "session_index.jsonl", "index", 70)
    for index in range(30):
        _write_file(
            source / "sessions" / "2026" / "04" / f"session-{index}.jsonl",
            f"session {index}\n",
            mtime=100 + index,
        )
    _write_file(
        source / "sessions" / "2026" / "04" / "session-big.jsonl",
        "x" * (2_000_000 + 1),
        mtime=1000,
    )

    mms_launchers._seed_codex_bounded_resume([str(source)], str(session_codex))

    assert len(_lines(session_codex / "history.jsonl")) == 200
    assert len(_lines(session_codex / "session_index.jsonl")) == 50
    copied_sessions = sorted(
        path.name for path in (session_codex / "sessions").glob("2026/04/*.jsonl")
    )
    assert len(copied_sessions) == 25
    assert "session-big.jsonl" not in copied_sessions
    manifest = json.loads((session_codex / "mms-resume-seed.json").read_text(encoding="utf-8"))
    assert manifest["limits"]["max_file_bytes"] == 2_000_000
    assert manifest["limits"]["dirs"]["sessions"]["max_files"] == 25
    assert manifest["seeded"]["dirs"]["sessions"]["skipped_oversize_files"] == 1


def test_codex_resume_writeback_merges_session_tail_and_files(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    store_codex = tmp_path / "store" / ".codex"
    session_codex = tmp_path / "session" / ".codex"
    _write_lines(store_codex / "history.jsonl", "history", 3)
    _write_lines(store_codex / "session_index.jsonl", "index", 3)
    _write_lines(session_codex / "history.jsonl", "history", 4)
    _write_lines(session_codex / "session_index.jsonl", "index", 4)
    _write_file(
        session_codex / "sessions" / "2026" / "04" / "session-new.jsonl",
        "new session\n",
        mtime=200,
    )
    _write_file(
        session_codex / "shell_snapshots" / "snapshot-new.sh",
        "snapshot\n",
        mtime=201,
    )

    monkeypatch.setenv("MMS_CODEX_HISTORY_JSONL_MAX_LINES", "3")
    monkeypatch.setenv("MMS_CODEX_SESSION_INDEX_JSONL_MAX_LINES", "2")
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "1")
    monkeypatch.setenv("MMS_CODEX_SHELL_SNAPSHOTS_MAX_FILES", "1")

    manifest = mms_launchers._sync_codex_bounded_resume_back(
        str(session_codex),
        str(store_codex),
    )

    assert _lines(store_codex / "history.jsonl") == ["history-1", "history-2", "history-3"]
    assert _lines(store_codex / "session_index.jsonl") == ["index-2", "index-3"]
    assert (store_codex / "sessions" / "2026" / "04" / "session-new.jsonl").read_text(encoding="utf-8") == "new session\n"
    assert (store_codex / "shell_snapshots" / "snapshot-new.sh").read_text(encoding="utf-8") == "snapshot\n"
    assert manifest["files"]["history.jsonl"]["status"] == "merged"
    writeback_manifest = json.loads((store_codex / "mms-resume-writeback.json").read_text(encoding="utf-8"))
    assert writeback_manifest["dirs"]["sessions"]["files"] == 1


def test_codex_resume_writeback_makes_next_seed_visible(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    store_codex = tmp_path / "store" / ".codex"
    first_session = tmp_path / "first" / ".codex"
    second_session = tmp_path / "second" / ".codex"
    _write_lines(store_codex / "history.jsonl", "history", 2)
    _write_lines(first_session / "history.jsonl", "history", 3)
    _write_file(
        first_session / "sessions" / "2026" / "04" / "session-current.jsonl",
        "current session\n",
        mtime=300,
    )

    monkeypatch.setenv("MMS_CODEX_HISTORY_JSONL_MAX_LINES", "5")
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "5")

    mms_launchers._sync_codex_bounded_resume_back(str(first_session), str(store_codex))
    mms_launchers._seed_codex_bounded_resume([str(store_codex)], str(second_session))

    assert _lines(second_session / "history.jsonl") == ["history-0", "history-1", "history-2"]
    copied = list((second_session / "sessions").glob("2026/04/session-current.jsonl"))
    assert len(copied) == 1
    assert copied[0].read_text(encoding="utf-8") == "current session\n"


def test_seed_codex_bounded_resume_backfills_current_project_oversize_sibling(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    seed_codex = tmp_path / "gateway" / ".codex"
    sibling_codex = tmp_path / "gateway" / "s" / "old-pid" / ".codex"
    new_session_codex = tmp_path / "gateway" / "s" / "new-pid" / ".codex"
    _write_file(
        seed_codex / "sessions" / "2026" / "04" / "old.jsonl",
        '{"timestamp":"2026-04-01T00:00:00Z","type":"session_meta","payload":{"id":"old","cwd":"/tmp/other"}}\n',
        mtime=100,
    )
    current_payload = (
        '{"timestamp":"2026-04-28T00:00:00Z","type":"session_meta",'
        f'"payload":{{"id":"current","cwd":"{repo_dir}"}}}}\n'
        + ("x" * 200)
    )
    _write_file(
        sibling_codex / "sessions" / "2026" / "04" / "current.jsonl",
        current_payload,
        mtime=200,
    )

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "1")
    monkeypatch.setenv("MMS_CODEX_RESUME_MAX_FILE_BYTES", "64")
    monkeypatch.setenv("MMS_CODEX_RESUME_PROJECT_MAX_FILE_BYTES", "1024")

    mms_launchers._seed_codex_bounded_resume(
        [str(seed_codex), str(sibling_codex)],
        str(new_session_codex),
    )

    copied = list((new_session_codex / "sessions").glob("2026/04/*.jsonl"))
    assert [path.name for path in copied] == ["current.jsonl"]
    assert copied[0].read_text(encoding="utf-8") == current_payload


def test_account_codex_env_materializes_bounded_resume_without_global_symlinks(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    account_home = tmp_path / "account-home"
    account_codex = account_home / ".codex"
    real_home = tmp_path / "real-home"
    real_codex = real_home / ".codex"
    _write_lines(account_codex / "history.jsonl", "account-history", 5)
    _write_lines(real_codex / "history.jsonl", "real-history", 5)
    (account_codex / "installation_id").parent.mkdir(parents=True, exist_ok=True)
    (account_codex / "installation_id").write_text("account-installation\n", encoding="utf-8")
    for index in range(3):
        _write_file(
            account_codex / "sessions" / "2026" / "04" / f"account-session-{index}.jsonl",
            f"account session {index}\n",
            mtime=100 + index,
        )

    monkeypatch.setenv("MMS_CODEX_HISTORY_JSONL_MAX_LINES", "2")
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "1")
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._account_env(
        {"id": "codex-a", "cli": "codex", "home_dir": str(account_home)},
        validate_proxy=False,
    )

    session_codex = Path(env["CODEX_HOME"])
    assert not (session_codex / "history.jsonl").is_symlink()
    assert _lines(session_codex / "history.jsonl") == ["account-history-3", "account-history-4"]
    assert not (session_codex / "sessions").is_symlink()
    copied_sessions = list((session_codex / "sessions").glob("2026/04/*.jsonl"))
    assert len(copied_sessions) == 1
    assert copied_sessions[0].name == "account-session-2.jsonl"
    assert not (session_codex / "installation_id").is_symlink()
    assert (session_codex / "installation_id").read_text(encoding="utf-8") == "account-installation\n"
    assert env["CODEX_HOME"] == str(session_codex)
    assert env["MMS_CODEX_RESUME_WRITEBACK_ROOT"] == str(account_codex)
    manifest = json.loads((session_codex / "mms-resume-seed.json").read_text(encoding="utf-8"))
    assert manifest["seeded"]["files"]["history.jsonl"]["bytes"] > 0


def test_codex_gateway_env_prefers_gateway_bounded_resume(monkeypatch, tmp_path):
    mms_launchers = _import_mms_launchers(monkeypatch, tmp_path)

    real_home = tmp_path / "real-home"
    gateway_codex = real_home / ".config" / "mms" / "codex-gateway" / ".codex"
    real_codex = real_home / ".codex"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _write_lines(gateway_codex / "history.jsonl", "gateway-history", 4)
    _write_lines(real_codex / "history.jsonl", "real-history", 4)
    for index in range(2):
        _write_file(
            gateway_codex / "sessions" / "2026" / "04" / f"gateway-session-{index}.jsonl",
            f"gateway session {index}\n",
            mtime=100 + index,
        )
    (real_codex / "memories").mkdir(parents=True)
    (real_codex / "installation_id").write_text("real-installation\n", encoding="utf-8")

    monkeypatch.chdir(repo_dir)
    monkeypatch.setenv("MMS_CODEX_HISTORY_JSONL_MAX_LINES", "2")
    monkeypatch.setenv("MMS_CODEX_SESSIONS_MAX_FILES", "1")
    monkeypatch.setattr(mms_launchers, "_cleanup_stale_sessions", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_link_shared_dotfiles", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_sync_codex_session_claude_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_command_wrappers", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_install_session_packet_env", lambda *args, **kwargs: None)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_network_profile", lambda env, runtime, validate_proxy=True: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_locale_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_apply_runtime_ip_stack_profile", lambda env, runtime: env)
    monkeypatch.setattr(mms_launchers, "_resolve_web_access_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_agent_browser_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_toon_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_resolve_token_saver_root", lambda: "")
    monkeypatch.setattr(mms_launchers, "_real_user_path", lambda *parts: str(real_home.joinpath(*parts)))

    env = mms_launchers._codex_gateway_env(
        {"id": "relay-a", "api_key": "sk-runtime"},
        base_url="http://127.0.0.1:12345/v1",
    )

    session_codex = Path(env["CODEX_HOME"])
    assert not (session_codex / "history.jsonl").is_symlink()
    assert _lines(session_codex / "history.jsonl") == ["gateway-history-2", "gateway-history-3"]
    assert not (session_codex / "sessions").is_symlink()
    copied_sessions = list((session_codex / "sessions").glob("2026/04/*.jsonl"))
    assert len(copied_sessions) == 1
    assert copied_sessions[0].name == "gateway-session-1.jsonl"
    assert (session_codex / "memories").is_symlink()
    assert not (session_codex / "installation_id").is_symlink()
    assert (session_codex / "installation_id").read_text(encoding="utf-8") == "real-installation\n"
    assert env["CODEX_HOME"] == str(session_codex)
    assert env["MMS_CODEX_RESUME_WRITEBACK_ROOT"] == str(gateway_codex)
    manifest = json.loads((session_codex / "mms-resume-seed.json").read_text(encoding="utf-8"))
    assert manifest["seeded"]["files"]["history.jsonl"]["lines"] == 2
