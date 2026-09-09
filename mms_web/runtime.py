"""Private launch snapshots. Source MMS configuration is only ever read."""
from __future__ import annotations
import json
import os
import tempfile
import uuid
from pathlib import Path
from .errors import WebError


def real_home() -> Path:
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "HOME"):
        if os.environ.get(key):
            return Path(os.environ[key]).expanduser().resolve()
    return Path.home().resolve()


def require_private_root(root: Path) -> Path:
    root = root.resolve()
    for name in ("mms", "mms-next"):
        protected = (real_home() / ".config" / name).resolve()
        if root == protected or root.is_relative_to(protected) or protected.is_relative_to(root):
            raise WebError("PROTECTED_STATE_ROOT", "Web 运行目录必须位于独立目录。", 409)
    return root


def private_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".web-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def snapshot_config(source: Path, state_root: Path, *, published_credentials_only: bool = False) -> Path:
    destination = require_private_root(state_root) / "runtimes" / uuid.uuid4().hex
    destination.mkdir(parents=True, mode=0o700)
    names = {"config.toml", "override.toml", "preferences.toml", "credentials.sh", "model-policy.json"}
    # Never copy accounts, global auth, history or existing runtime directories.
    manifest = source / "generated/model-registry.latest-approved.json"
    if manifest.is_file():
        if published_credentials_only:
            names.discard("credentials.sh")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        names.add("generated/model-registry.latest-approved.json")
        for entry in data.get("files", {}).values():
            name = Path(str(entry.get("canonical_path", "")))
            if name.is_absolute() or ".." in name.parts or not name.name:
                raise WebError("INVALID_BUNDLE", "模型目录包含无效的文件引用。", 409)
            names.add(str(name))
    captured = {}
    for name in names:
        path = source / name
        if path.is_file():
            captured[name] = path.read_bytes()
    if any((source / name).read_bytes() != content for name, content in captured.items()):
        raise WebError("CONFIG_STALE", "模型配置刚刚发生变化，请重新启动。", 409)
    for name, content in captured.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
    return destination
