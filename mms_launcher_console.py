"""Console helpers for launcher code paths."""

import builtins
import re
import sys


_RICH_MARKUP_RE = re.compile(r"\[/?(?:bold|dim|red|green|yellow|cyan|blue|magenta|white|black)(?:\s+[a-z_]+)*\]")


def strip_rich_markup(value):
    if not isinstance(value, str):
        return value
    return _RICH_MARKUP_RE.sub("", value)


class PlainStatus:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        builtins.print(strip_rich_markup(self.message))
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class PlainConsole:
    def print(self, *objects, sep=" ", end="\n", file=None, **_kwargs):
        rendered = [strip_rich_markup(obj) for obj in objects]
        builtins.print(*rendered, sep=sep, end=end, file=file or sys.stdout)

    def status(self, message, **_kwargs):
        return PlainStatus(message)

    def log(self, *objects, **kwargs):
        self.print(*objects, **kwargs)


class LauncherLazyConsole:
    _instance = None

    def __getattr__(self, name):
        if LauncherLazyConsole._instance is None:
            try:
                from rich.console import Console

                LauncherLazyConsole._instance = Console()
            except ModuleNotFoundError as exc:
                if (exc.name or "").split(".", 1)[0] != "rich":
                    raise
                LauncherLazyConsole._instance = PlainConsole()
        return getattr(LauncherLazyConsole._instance, name)
