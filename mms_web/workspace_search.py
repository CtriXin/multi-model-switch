"""Find familiar project folders without launching a shell or scanning the disk."""
import os
import shutil
import subprocess
from pathlib import Path

from .errors import WebError


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
    return {"workspaces": rows}
