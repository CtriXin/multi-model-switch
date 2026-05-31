from __future__ import annotations

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
