import argparse
import subprocess

from scripts import local_channel_update as update


def _args(tmp_path):
    return argparse.Namespace(
        command="mmf",
        kind="worktree",
        root=str(tmp_path / "repo"),
        branch="dev",
        remote="origin",
        cadence="daily",
        public_entry="",
        fetch=False,
    )


def test_update_message_prompts_manual_update(tmp_path):
    args = _args(tmp_path)

    message, is_error = update.update_message(args, {"ahead": 0, "behind": 2})

    assert is_error is False
    assert "有 2 个远端更新" in message
    assert "`mmf update`" in message
    assert "继续启动当前版本" in message


def test_remind_displays_fast_background_result(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "state.json"))
    args = _args(tmp_path)

    class DoneProcess:
        @staticmethod
        def wait(timeout=None):
            return 0

    def fake_spawn(spawn_args):
        update.store_background_result(
            spawn_args,
            {"head": "a", "remote": "b", "ahead": 0, "behind": 1, "remote_ref": "refs/remotes/origin/dev"},
        )
        return DoneProcess()

    monkeypatch.setattr(update, "spawn_background_check", fake_spawn)

    assert update.remind(args) == 0
    captured = capsys.readouterr()

    assert "有 1 个远端更新" in captured.out
    assert update.take_pending_result(args, update.load_state()) is None


def test_remind_defers_slow_background_result_to_next_start(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MMS_LOCAL_CHANNEL_UPDATE_STATE", str(tmp_path / "state.json"))
    args = _args(tmp_path)

    class SlowProcess:
        @staticmethod
        def wait(timeout=None):
            raise subprocess.TimeoutExpired(["git", "fetch"], timeout=timeout)

    def fake_spawn(spawn_args):
        update.mark_background_check_started(spawn_args)
        return SlowProcess()

    monkeypatch.setattr(update, "spawn_background_check", fake_spawn)

    assert update.remind(args) == 0
    assert capsys.readouterr().out == ""

    update.store_background_result(
        args,
        {"head": "a", "remote": "b", "ahead": 0, "behind": 3, "remote_ref": "refs/remotes/origin/dev"},
    )

    assert update.remind(args) == 0
    captured = capsys.readouterr()

    assert "有 3 个远端更新" in captured.out
    assert update.take_pending_result(args, update.load_state()) is None
