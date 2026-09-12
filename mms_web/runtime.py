"""Private launch snapshots. Source MMS configuration is only ever read."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
import time
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


def is_registry_root(root: Path) -> bool:
    """True when the root keeps v2 registry truth instead of legacy config files.

    The marker is the root manifest, written only by the v2 initializer, which
    refuses stable roots. A published bundle alone is not enough: a stable root
    can export one while config.toml remains its truth.
    """
    return (Path(root) / "root-manifest.json").is_file()


_ADOPTION_MARKER = "web-config-adopted.json"
# Runtime scratch that belongs to the Web install, not to the configuration.
_ADOPTION_SKIP_NAMES = frozenset({"previews", "launch-home", "runtimes", "sessions", "logs"})


def _root_has_configuration(root: Path) -> bool:
    if is_registry_root(root):
        return True
    if (root / "generated" / "model-registry.latest-approved.json").is_file():
        return True
    config_path = root / "config.toml"
    try:
        return config_path.is_file() and "[[providers]]" in config_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _copy_root_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    try:
        destination.chmod(0o700)
    except OSError:
        pass
    for entry in sorted(source.iterdir()):
        if entry.name in _ADOPTION_SKIP_NAMES or entry.name.endswith(".lock"):
            continue
        target = destination / entry.name
        if target.exists():
            continue
        if entry.is_dir():
            shutil.copytree(entry, target, symlinks=False)
        else:
            shutil.copy2(entry, target)


def adopt_web_owned_config(state_root: Path, shared: Path) -> Path:
    """Move a Web-owned configuration into the shared root, once.

    Installs made before the roots converged keep their channels inside the
    Web data directory, where the CLI never looks. Copy that configuration
    into the shared root when the shared root has none, verify the published
    bundle there, and leave the original in place as a backup. Any failure
    keeps the Web-owned root in use.
    """
    web_owned = Path(state_root) / "config"
    if _root_has_configuration(shared):
        return shared
    staging = shared.parent / f".{shared.name}.adopting-{os.getpid()}"
    try:
        if staging.exists():
            shutil.rmtree(staging)
        _copy_root_contents(web_owned, staging)
        private_json(
            staging / _ADOPTION_MARKER,
            {
                "schema": "mms.web_config_adoption.v1",
                "source": str(web_owned),
                "adopted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )
        from .catalog import _ensure_repo_on_path

        _ensure_repo_on_path()
        from mms_registry_cli import verify_approved_bundle

        verified = verify_approved_bundle(config_dir=str(staging))
        if not verified.get("verified"):
            raise WebError("ADOPTION_UNVERIFIED", "采用的配置未通过校验", 409)
        _copy_root_contents(staging, shared)
    except Exception:
        return web_owned
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return shared


def default_config_root(state_root: Path) -> Path:
    """Pick the config root a Pilot without ``--config-root`` should use.

    Everything shares the v2 root the CLI uses, so one setup serves both
    entrances. A Web install that already owns configuration is copied into
    that shared root once; failed adoption never creates a second runtime root.
    """
    web_owned = Path(state_root) / "config"
    try:
        from .catalog import _ensure_repo_on_path

        _ensure_repo_on_path()
        from mms_state_io import mms_config_root_status

        shared = Path(mms_config_root_status()["preview_root"])
    except Exception:
        return web_owned
    if _root_has_configuration(web_owned):
        # Keep the shared root as the only runtime source. Adoption is best
        # effort; a failed verification must not recreate a private Web root.
        adopt_web_owned_config(state_root, shared)
    return shared


def require_publishable_root(root: Path) -> Path:
    """Config roots the Web may publish into: its own private root, or a v2 root.

    A v2 root is written through the Registry publish path, the same one MMS
    uses, so sharing it with the CLI does not reintroduce hand-written config.
    A legacy stable root stays human-gated.
    """
    if is_registry_root(root):
        return Path(root).resolve()
    return require_private_root(root)


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
