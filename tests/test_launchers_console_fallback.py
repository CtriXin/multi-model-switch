import builtins


def test_launch_status_works_without_rich(monkeypatch, capsys):
    import mms_launchers

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "rich.console" or name.startswith("rich."):
            raise ModuleNotFoundError("No module named 'rich'", name="rich")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    mms_launchers._LazyConsole._instance = None  # noqa: SLF001

    with mms_launchers._launch_status("预读取模型列表中...", spinner="dots") as started_at:  # noqa: SLF001
        assert isinstance(started_at, float)

    output = capsys.readouterr().out
    assert "预读取模型列表中..." in output
    assert "[cyan]" not in output
