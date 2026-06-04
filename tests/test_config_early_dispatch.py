from __future__ import annotations


def test_dispatch_config_root_status(monkeypatch):
    from mms_config import display_commands
    from mms_config.early_dispatch import dispatch_early_config_command

    calls = []

    def fake_display_config_root(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(display_commands, "display_config_root", fake_display_config_root)

    console = object()
    status_fn = lambda: {"mode": "preview"}

    handled, code = dispatch_early_config_command(
        ["config", "root", "--json"],
        command_name="mmg",
        primary_config_dir="/tmp/mms-next",
        config_root_status=status_fn,
        console=console,
    )

    assert handled is True
    assert code == 0
    assert calls == [{"json_output": True, "config_root_status": status_fn, "console": console}]


def test_dispatch_consumer_bundle_exit_code(monkeypatch):
    from mms_config import display_commands
    from mms_config.early_dispatch import dispatch_early_config_command

    calls = []

    def fake_display_consumer_bundle_status(**kwargs):
        calls.append(kwargs)
        return 2

    monkeypatch.setattr(display_commands, "display_consumer_bundle_status", fake_display_consumer_bundle_status)

    handled, code = dispatch_early_config_command(
        ["config", "bundle"],
        command_name="mmg",
        primary_config_dir="/tmp/mms-next",
        config_root_status=lambda: {"mode": "preview"},
        console=object(),
    )

    assert handled is True
    assert code == 2
    assert calls == [
        {
            "json_output": False,
            "strict_exit": True,
            "config_dir": "/tmp/mms-next",
            "command_name": "mmg",
        }
    ]


def test_dispatch_ignores_non_early_config_command():
    from mms_config.early_dispatch import dispatch_early_config_command

    handled, code = dispatch_early_config_command(
        ["config", "preferences.help"],
        command_name="mmg",
        primary_config_dir="/tmp/mms-next",
        config_root_status=lambda: {"mode": "preview"},
        console=object(),
    )

    assert handled is False
    assert code == 0
