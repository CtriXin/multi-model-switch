import builtins


def test_plain_console_strips_rich_markup(capsys):
    from mms_launcher.console import PlainConsole

    console = PlainConsole()
    console.print("[green]ready[/green]", "[dim]now[/dim]")

    assert capsys.readouterr().out == "ready now\n"


def test_launcher_lazy_console_falls_back_when_rich_is_missing(monkeypatch, capsys):
    import mms_launcher.console as mms_launcher_console

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rich.console":
            raise ModuleNotFoundError("No module named 'rich'", name="rich")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(mms_launcher_console.LauncherLazyConsole, "_instance", None)

    console = mms_launcher_console.LauncherLazyConsole()
    console.print("[red]fallback[/red]")

    assert capsys.readouterr().out == "fallback\n"
    assert isinstance(mms_launcher_console.LauncherLazyConsole._instance, mms_launcher_console.PlainConsole)
