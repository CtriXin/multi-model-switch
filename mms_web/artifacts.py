"""Expose actual output files named by successful write/edit tools."""
from __future__ import annotations
import hashlib
from pathlib import Path


def collect_artifacts(meta: dict, events: list[dict]) -> list[dict]:
    if not meta.get("cwd"):
        return []
    root = Path(meta["cwd"]).resolve()
    outputs = {}
    for event in events:
        if event.get("kind") != "tool" or event.get("status") != "done":
            continue
        if event.get("title") not in {"write", "edit"}:
            continue
        arguments = event.get("arguments") or {}
        raw = arguments.get("path") or arguments.get("file_path")
        if not isinstance(raw, str):
            continue
        path = (root / raw).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.name.lower() in {"credentials.sh", "config.toml", "auth.json"}:
            continue
        try:
            if path.stat().st_size > 1024 * 1024:
                continue
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = str(path.relative_to(root))
        outputs[relative] = {
            "id": hashlib.sha256(relative.encode()).hexdigest()[:16],
            "name": path.name, "path": relative, "content": content,
            "kind": "markdown" if path.suffix.lower() in {".md", ".markdown"} else "text",
        }
    return list(outputs.values())
