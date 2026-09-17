"""Read-only folder listing for the in-app workspace picker.

This is not the workspace file tree. `/files/tree` is scoped to a registered
workspace and returns files. The picker has to find a directory that is not a
workspace yet, and it must not open a system dialog to do it.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath
from typing import NoReturn

from .errors import WebError
from .files import EXCLUDED, allowed
from .runtime import real_home
from .workspace_search import _is_explicit_path

BROWSE_LIMIT = 400
GENERIC_CODE = "FOLDER_UNAVAILABLE"
GENERIC_MESSAGE = "无法打开这个文件夹。"
_DRIVE_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_CONTROL = re.compile(r"[\x00-\x1f]")


def _windows_platform() -> bool:
    return os.name == "nt"


def _reject() -> NoReturn:
    raise WebError(GENERIC_CODE, GENERIC_MESSAGE, 409)


def classify_user_path(raw: str, *, windows: bool = False) -> str:
    """Name the path shape without touching the disk.

    Windows forms are recognized with PureWindowsPath so macOS tests can cover
    drive roots, drive-relative paths, and UNC without a Windows host.
    """
    text = str(raw or "").strip()
    if not text:
        return "empty"
    if len(text) > 4096 or _CONTROL.search(text):
        return "invalid"
    win = PureWindowsPath(text)
    if text.startswith("\\\\") or str(win.anchor).startswith("//"):
        return "unc"
    if win.drive:
        rest = text[2:]
        if rest.startswith(("\\", "/")):
            return "drive_root" if rest.strip("\\/") == "" else "drive_abs"
        return "drive_relative"
    if text.startswith(("/", "~/")):
        return "posix"
    if windows and _DRIVE_ABS.match(text):
        return "drive_abs"
    return "other"


def _list_drives() -> list[str]:
    """Drive roots on Windows. Python 3.11 has no os.listdrives()."""
    if not _windows_platform():
        return []
    listed: list[str] = []
    listdrives = getattr(os, "listdrives", None)
    if callable(listdrives):
        try:
            listed = [str(item) for item in listdrives()]
        except OSError:
            listed = []
    if not listed:
        import string
        listed = [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
    drives = []
    seen = set()
    for item in listed:
        text = item if item.endswith(("\\", "/")) else item + "\\"
        key = os.path.normcase(text)
        if key in seen:
            continue
        seen.add(key)
        drives.append(text)
    return drives


def _mounted_volumes() -> list[Path]:
    """POSIX analog of extra drive letters: currently mounted /Volumes entries.

    UNC / unmounted network shares are not enumerated. Paste the path instead.
    """
    if _windows_platform():
        return []
    root = Path("/Volumes")
    if not root.is_dir():
        return []
    found: list[Path] = []
    try:
        for entry in os.scandir(root):
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            found.append(Path(entry.path))
    except OSError:
        return []
    return found


def _workspace_paths(catalog) -> list[Path]:
    if catalog is None:
        return []
    found: list[Path] = []
    try:
        rows = catalog._workspaces()
    except Exception:
        return []
    for workspace in rows:
        if not isinstance(workspace, dict) or workspace.get("hidden") is True:
            continue
        raw = workspace.get("path")
        if not raw:
            continue
        try:
            path = Path(str(raw)).expanduser().resolve(strict=True)
        except (OSError, ValueError):
            continue
        if path.is_dir():
            found.append(path)
    return found


def _ancestors_until_ceiling(path: Path) -> list[Path]:
    """Parents a workspace can walk up to, without opening POSIX `/` or `/Users`."""
    home = real_home()
    items: list[Path] = []
    parent = path.parent
    while parent != parent.parent:
        if not _windows_platform() and parent.as_posix() == "/":
            break
        items.append(parent)
        if not _windows_platform() and _same(parent, home):
            break
        parent = parent.parent
    return items


def _same(left: Path, right: Path) -> bool:
    if _windows_platform():
        return os.path.normcase(str(left)) == os.path.normcase(str(right))
    return left == right


def _is_under(child: Path, parent: Path) -> bool:
    try:
        if _windows_platform():
            child.relative_to(parent)
            return True
        return child == parent or parent in child.parents
    except (ValueError, OSError):
        return False


def _hidden_or_excluded(path: Path) -> bool:
    return any(part.startswith(".") or part in EXCLUDED for part in path.parts) or not allowed(path)


def _expand_user_path(raw: str) -> Path:
    text = raw.strip()
    if text.startswith("~/"):
        return real_home() / text[2:]
    return Path(text)


def _known_roots(catalog, extra: list[Path]) -> list[Path]:
    roots = [real_home(), *extra]
    for workspace in _workspace_paths(catalog):
        roots.append(workspace)
        roots.extend(_ancestors_until_ceiling(workspace))
    if _windows_platform():
        for drive in _list_drives():
            roots.append(Path(drive))
    else:
        roots.extend(_mounted_volumes())
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(str(root)) if _windows_platform() else str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _may_list(path: Path, roots: list[Path]) -> bool:
    return any(_same(path, root) or _is_under(path, root) for root in roots)


def _entry(name: str, path: str, kind: str = "folder") -> dict:
    return {"name": name, "path": path, "kind": kind}


def _computer_listing(catalog) -> dict:
    home = real_home()
    entries = [_entry(home.name or "Home", str(home), "home")]
    seen = {os.path.normcase(str(home)) if _windows_platform() else str(home)}
    for workspace in _workspace_paths(catalog):
        if _is_under(workspace, home) or _same(workspace, home):
            continue
        key = os.path.normcase(str(workspace)) if _windows_platform() else str(workspace)
        if key in seen:
            continue
        seen.add(key)
        entries.append(_entry(workspace.name or str(workspace), str(workspace), "folder"))
    if _windows_platform():
        for drive in _list_drives():
            key = os.path.normcase(drive)
            if key in seen:
                continue
            seen.add(key)
            label = drive.rstrip("\\/") + ":"
            if len(drive) >= 2 and drive[1] == ":":
                label = drive[:2]
            entries.append(_entry(label, drive, "drive"))
    else:
        for volume in _mounted_volumes():
            key = str(volume)
            if key in seen:
                continue
            seen.add(key)
            entries.append(_entry(volume.name, str(volume), "volume"))
    return {
        "path": "",
        "name": "这台电脑",
        "parent": None,
        "selectable": False,
        "truncated": False,
        "entries": entries,
    }


def _parent_payload(path: Path, roots: list[Path]) -> str | None:
    parent = path.parent
    if parent == path:
        return ""
    if not _may_list(parent, roots):
        return ""
    return str(parent)


def _list_directories(folder: Path) -> tuple[list[dict], bool]:
    entries: list[dict] = []
    truncated = False
    try:
        children = list(os.scandir(folder))
    except OSError:
        _reject()
    children.sort(key=lambda item: item.name.lower())
    for child in children:
        try:
            if child.is_symlink() or not child.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if child.name.startswith(".") or child.name in EXCLUDED:
            continue
        candidate = Path(child.path)
        if not allowed(candidate):
            continue
        entries.append(_entry(child.name, str(candidate), "folder"))
        if len(entries) >= BROWSE_LIMIT:
            truncated = True
            break
    return entries, truncated


def browse_workspaces(catalog, payload: dict) -> dict:
    raw = str((payload or {}).get("path") or "").strip()
    windows = _windows_platform()
    kind = classify_user_path(raw, windows=windows)
    if kind == "empty":
        return _computer_listing(catalog)
    if kind in {"invalid", "drive_relative", "other"}:
        _reject()
    if kind == "unc" and not windows:
        # UNC only has meaning on Windows; enumerating shares is out of scope.
        _reject()
    extra: list[Path] = []
    if _is_explicit_path(raw) or kind in {"posix", "drive_root", "drive_abs", "unc"}:
        extra.append(_expand_user_path(raw))
    target = extra[0] if extra else _expand_user_path(raw)
    if _hidden_or_excluded(target):
        _reject()
    roots = _known_roots(catalog, extra)
    if not _may_list(target, roots):
        _reject()
    try:
        if target.is_symlink() or not target.is_dir():
            _reject()
    except OSError:
        _reject()
    entries, truncated = _list_directories(target)
    return {
        "path": str(target),
        "name": target.name or str(target),
        "parent": _parent_payload(target, roots),
        "selectable": True,
        "truncated": truncated,
        "entries": entries,
    }
