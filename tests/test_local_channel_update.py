from __future__ import annotations

import subprocess
from argparse import Namespace


def _args() -> Namespace:
    return Namespace(
        command="mmg",
        kind="worktree",
        root="/tmp/mms-canary",
        branch="canary",
        remote="origin",
        cadence="always",
        public_entry="",
    )


def _daily_args(tmp_path) -> Namespace:
    return Namespace(
        command="mmf",
        kind="worktree",
        root=str(tmp_path / "repo"),
        branch="dev",
        remote="origin",
        cadence="daily",
        public_entry="",
        fetch=False,
    )


def test_cached_remind_prints_previous_remote_update_once(monkeypatch, tmp_path, capsys):
    from scripts import local_channel_update

    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "updates.json"))
    args = _args()
    state = {}
    local_channel_update.mark_checked(
        args,
        state,
        {
            "head": "local-a",
            "remote": "remote-b",
            "ahead": 0,
            "behind": 2,
            "remote_ref": "refs/remotes/origin/canary",
        },
    )

    assert local_channel_update.cached_remind(args) == 0
    first = capsys.readouterr().out
    assert "mmg/canary 有 2 个远端更新" in first
    assert "mmg update" in first

    assert local_channel_update.cached_remind(args) == 0
    assert capsys.readouterr().out == ""

    state = local_channel_update.load_state()
    local_channel_update.mark_checked(
        args,
        state,
        {
            "head": "local-a",
            "remote": "remote-c",
            "ahead": 0,
            "behind": 3,
            "remote_ref": "refs/remotes/origin/canary",
        },
    )

    assert local_channel_update.cached_remind(args) == 0
    assert "mmg/canary 有 3 个远端更新" in capsys.readouterr().out


def test_update_message_prompts_manual_update(tmp_path):
    from scripts import local_channel_update

    args = _daily_args(tmp_path)

    message, is_error = local_channel_update.update_message(args, {"ahead": 0, "behind": 2})

    assert is_error is False
    assert "有 2 个远端更新" in message
    assert "`mmf update`" in message
    assert "继续启动当前版本" in message


def test_remind_displays_fast_background_result(monkeypatch, tmp_path, capsys):
    from scripts import local_channel_update

    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "state.json"))
    args = _daily_args(tmp_path)

    class DoneProcess:
        @staticmethod
        def wait(timeout=None):
            return 0

    def fake_spawn(spawn_args):
        local_channel_update.store_background_result(
            spawn_args,
            {"head": "a", "remote": "b", "ahead": 0, "behind": 1, "remote_ref": "refs/remotes/origin/dev"},
        )
        return DoneProcess()

    monkeypatch.setattr(local_channel_update, "spawn_background_check", fake_spawn)

    assert local_channel_update.remind(args) == 0
    captured = capsys.readouterr()

    assert "有 1 个远端更新" in captured.out
    assert local_channel_update.take_pending_result(args, local_channel_update.load_state()) is None


def test_remind_defers_slow_background_result_to_next_start(monkeypatch, tmp_path, capsys):
    from scripts import local_channel_update

    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "state.json"))
    args = _daily_args(tmp_path)

    class SlowProcess:
        @staticmethod
        def wait(timeout=None):
            raise subprocess.TimeoutExpired(["git", "fetch"], timeout=timeout)

    def fake_spawn(spawn_args):
        local_channel_update.mark_background_check_started(spawn_args)
        return SlowProcess()

    monkeypatch.setattr(local_channel_update, "spawn_background_check", fake_spawn)

    assert local_channel_update.remind(args) == 0
    assert capsys.readouterr().out == ""

    local_channel_update.store_background_result(
        args,
        {"head": "a", "remote": "b", "ahead": 0, "behind": 3, "remote_ref": "refs/remotes/origin/dev"},
    )

    assert local_channel_update.remind(args) == 0
    captured = capsys.readouterr()

    assert "有 3 个远端更新" in captured.out
    assert local_channel_update.take_pending_result(args, local_channel_update.load_state()) is None


def test_cached_remind_does_not_notify_ahead_only_by_default(monkeypatch, tmp_path, capsys):
    from scripts import local_channel_update

    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "updates.json"))
    args = _args()
    local_channel_update.mark_checked(
        args,
        {},
        {
            "head": "local-a",
            "remote": "remote-a",
            "ahead": 74,
            "behind": 0,
            "remote_ref": "refs/remotes/origin/canary",
        },
    )

    assert local_channel_update.cached_remind(args) == 0
    assert capsys.readouterr().out == ""
