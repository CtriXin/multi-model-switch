"""Find familiar project folders without launching a shell."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .errors import WebError
from .runtime import real_home

# Browsers hand a dropped folder over by name only, so the local service has to
# find it again. These never hold a project the user would drag in.
_SKIP_SCAN = {"node_modules", "Library", "Applications", ".Trash", "__pycache__",
              ".venv", "venv", "dist", "build", ".cache", ".npm", ".git"}
# A project the user drags in usually sits inside a folder Pilot already knows,
# so those are swept deeply and the home folder only near the surface.
_SCAN_DEPTH_KNOWN = 6
_SCAN_DEPTH_HOME = 3
_SCAN_BUDGET = 8000
_SPOTLIGHT_LIMIT = 400
_ZOXIDE_LIMIT = 100
_MATCH_LIMIT = 40
_SCAN_SECONDS = 2.0


def search_workspaces(catalog, payload):
    query = str(payload.get("query") or "").strip()
    if len(query) > 200 or any(ord(char) < 32 for char in query):
        raise WebError("INVALID_WORKSPACE_QUERY", "请用项目名或文件夹路径搜索。", 400)
    terms = query.lower().split()
    known = catalog._workspaces()
    candidates = [w for w in known if not w.get("hidden") and
                  all(term in (w["name"] + " " + w["path"]).lower() for term in terms)]
    binary = shutil.which("zoxide") or next((p for p in ("/opt/homebrew/bin/zoxide", "/usr/local/bin/zoxide")
                                            if os.access(p, os.X_OK)), None)
    if binary:
        try:
            result = subprocess.run([binary, "query", "--list", "--", *query.split()],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                candidates.extend({"path": path, "name": Path(path).name} for path in result.stdout.splitlines()[:100])
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            pass
    if query.startswith(("/", "~/")):
        candidates.insert(0, {"path": query, "name": Path(query).name})
    rows, seen = [], set()
    by_path = {str(Path(w["path"]).expanduser().resolve()): w for w in known if not w.get("hidden")}
    for candidate in candidates:
        try:
            path = Path(candidate["path"]).expanduser().resolve(strict=True)
            if not path.is_dir() or str(path) in seen:
                continue
            seen.add(str(path))
            row = by_path.get(str(path), candidate)
            rows.append({"id": row.get("id", ""), "name": row["name"], "path": str(path)})
        except (OSError, ValueError):
            continue
        if len(rows) == 40:
            break
    if not rows and terms and not query.startswith(("/", "~/")):
        # Nothing familiar matched, so fall back to the folders the system already indexes.
        for path in _spotlight_directories(query, real_home())[0]:
            try:
                resolved = path.resolve(strict=True)
            except (OSError, ValueError):
                continue
            if resolved.is_dir() and str(resolved) not in seen:
                seen.add(str(resolved))
                rows.append({"id": "", "name": resolved.name, "path": str(resolved)})
            if len(rows) == 20:
                break
    return {"workspaces": rows}


def _spotlight_directories(name: str, home: Path) -> tuple[list[Path], bool]:
    """Ask the macOS index for folders with this name; it is already built.

    Returns the hits and whether the answer is complete. An index that was not
    consulted at all, timed out, or returned more rows than we read cannot rule
    out a folder elsewhere, and the caller must not claim certainty on it.
    """
    if sys.platform != "darwin" or name.startswith("-"):
        return [], True
    binary = shutil.which("mdfind") or ("/usr/bin/mdfind" if os.access("/usr/bin/mdfind", os.X_OK) else None)
    if not binary:
        return [], True
    try:
        result = subprocess.run([binary, "-onlyin", str(home), "-name", name],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return [], False
    if result.returncode != 0:
        return [], False
    lines = [line for line in result.stdout.splitlines() if line]
    return [Path(line) for line in lines[:_SPOTLIGHT_LIMIT]], len(lines) <= _SPOTLIGHT_LIMIT


def _scan_directories(name: str, plans: list[tuple[Path, int]]) -> tuple[list[Path], bool]:
    """Sweep likely roots within one budget, retaining same-name alternatives.

    Returns the hits and whether the sweep finished. Running out of budget or
    time means somewhere was never looked at, so a single hit is not proof that
    it is the only one.
    """
    deadline = time.monotonic() + _SCAN_SECONDS
    found: list[Path] = []
    seen: set[str] = set()
    visited = 0
    for root, depth_limit in plans:
        if visited >= _SCAN_BUDGET or time.monotonic() > deadline:
            # Plans left unswept.
            return found, False
        frontier = [(root, 0)]
        while frontier and visited < _SCAN_BUDGET and time.monotonic() < deadline:
            current, depth = frontier.pop(0)
            key = str(current)
            if key in seen:
                continue
            seen.add(key)
            visited += 1
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if entry.name == name:
                    found.append(Path(entry.path))
                if depth + 1 < depth_limit and entry.name not in _SKIP_SCAN:
                    frontier.append((Path(entry.path), depth + 1))
        if frontier:
            # This root still had directories queued when the budget ran out.
            return found, False
    return found, True


def _named_directories(catalog, name: str, *, deep: bool) -> tuple[list[Path], bool]:
    """Collect folders called `name`, nearest-to-the-user first.

    Also reports whether every source answered in full. A partial answer can
    hide the folder that was actually dropped, which is the one case where a
    single candidate must not be treated as the only one.
    """
    home = real_home()
    found: list[Path] = []
    roots: list[Path] = []
    complete = True
    for workspace in catalog._workspaces():
        if workspace.get("hidden"):
            continue
        try:
            path = Path(workspace["path"]).expanduser().resolve()
        except (OSError, ValueError, KeyError):
            continue
        roots.append(path)
        for candidate in (path, path / name, path.parent / name):
            # `path / name` always carries the right name, so existence is the real test.
            if candidate.name == name and candidate.is_dir():
                found.append(candidate)
    binary = shutil.which("zoxide") or next((p for p in ("/opt/homebrew/bin/zoxide", "/usr/local/bin/zoxide")
                                             if os.access(p, os.X_OK)), None)
    if binary:
        try:
            result = subprocess.run([binary, "query", "--list", "--", name],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                found.extend(Path(line) for line in lines[:_ZOXIDE_LIMIT] if Path(line).name == name)
                complete = complete and len(lines) <= _ZOXIDE_LIMIT
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            complete = False
    indexed, indexed_complete = _spotlight_directories(name, home)
    found.extend(path for path in indexed if path.name == name)
    complete = complete and indexed_complete
    if deep:
        plans = [(root, _SCAN_DEPTH_KNOWN) for root in roots if root != home]
        plans += [(root.parent, _SCAN_DEPTH_HOME) for root in roots if root.parent not in (home, root)]
        plans.append((home, _SCAN_DEPTH_HOME))
        swept, swept_complete = _scan_directories(name, plans)
        found.extend(swept)
        complete = complete and swept_complete
    rows, seen = [], set()
    for path in found:
        try:
            resolved = path.expanduser().resolve(strict=True)
        except (OSError, ValueError):
            continue
        if str(resolved) in seen or not resolved.is_dir():
            continue
        seen.add(str(resolved))
        rows.append(resolved)
        if len(rows) == _MATCH_LIMIT:
            complete = False
            break
    return rows, complete


def locate_folder(catalog, payload):
    """Resolve a dropped folder: the browser only reveals its name and contents."""
    name = str(payload.get("name") or "").strip()
    if (not name or len(name) > 200 or name in {".", ".."}
            or "/" in name or "\\" in name or any(ord(char) < 32 for char in name)):
        raise WebError("INVALID_WORKSPACE_QUERY", "拖入的文件夹名无法识别，请手动选择文件夹。", 400)
    raw = payload.get("children")
    children = {item for item in raw[:200] if isinstance(item, str)} if isinstance(raw, list) else set()
    known = {}
    for workspace in catalog._workspaces():
        try:
            known[str(Path(workspace["path"]).expanduser().resolve())] = workspace
        except (OSError, ValueError, KeyError):
            continue
    matches = []
    candidates, complete = _named_directories(catalog, name, deep=True)
    for path in candidates:
        try:
            present = {entry.name for entry in os.scandir(path)}
        except OSError:
            continue
        row = known.get(str(path), {})
        matches.append({"id": row.get("id", ""), "name": row.get("name") or path.name,
                        "path": str(path), "score": len(children & present)})
    matches.sort(key=lambda row: (-row["score"], len(row["path"])))
    return {"matches": [{k: v for k, v in row.items() if k != "score"} for row in matches[:20]],
            "sure": _confident(matches, children, complete=complete)}


def _confident(matches: list[dict], children: set, *, complete: bool) -> bool:
    """Only skip the picker when one folder plainly is the one that was dropped."""
    if not matches:
        return False
    # A search that ran out of budget may simply not have reached the folder
    # that was dropped, so "the only match" is not something it can establish.
    # Adopting the wrong directory silently rewrites where the session works.
    if not complete:
        return False
    # A shared README/src entry is not enough to identify a directory. A
    # missing fingerprint (including a timed-out browser read) needs a choice.
    if not children or matches[0]["score"] != len(children):
        return False
    return len(matches) == 1 or matches[0]["score"] > matches[1]["score"]
