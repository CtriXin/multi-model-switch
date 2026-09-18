"""Replace the installed MMS next to the Pilot, so the CLI never drifts.

An in-page update stages a release under the state directory and points
``updates/active.json`` at it. The web process redirects there at every start,
but ``mms`` and ``mmf`` always load from the directory they were installed
into, so they keep running whatever version was last installed. Once the
candidate has proved it starts and serves, this module copies the same files
``install.sh`` copies into that installation and the pointer is dropped, so
every entrance runs one version.

A source checkout is never written to: on a development machine the running
source is a git worktree, and replacing its files would destroy work.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
import tempfile
from pathlib import Path

# Mirrors the copy list in install.sh. tests/test_update_install.py fails when
# the installer learns to copy something this does not.
FILES = (
    "mms",
    "mms-web",
    "MMS Pilot.command",
    "mmf",
    "mmslogs",
    "statusline-command.sh",
    "config.example.toml",
    "docs/LLM_OPERATION_GUIDE.md",
    "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json",
)
GLOBS: tuple[str, ...] = ()
DIRECTORIES = (
    "lib",
    "mms_web",
    "mms_web_static",
    "docs/mms-web",
    "hooks",
    "assets",
    "config",
    "mms_config_web_static",
    "vendor",
    "scripts",
)
STAGING_SUFFIX = ".mms-update-new"


class UnsupportedRuntimeLayout(ValueError):
    """A known layout mismatch with safe, actionable user guidance."""


def require_runtime_layout(source: Path) -> None:
    """Never install old flat entrypoints over a lib-based runtime."""
    if not all((Path(source) / "lib" / name).is_file()
               for name in ("mms_core.py", "mms_version.py")):
        raise UnsupportedRuntimeLayout(
            "更新包缺少 lib/ 运行模块，不能在 Pilot 内更新。"
            "当前安装与会话已保留；请使用目标版本的安装器重新安装。"
        )


def manifest(source: Path) -> list[str]:
    """Release-owned paths, relative to `source`, that actually exist in it."""
    source = Path(source)
    found = [name for name in FILES if (source / name).is_file()]
    for pattern in GLOBS:
        found += [item.name for item in source.glob(pattern) if item.is_file()]
    found += [name for name in DIRECTORIES if (source / name).is_dir()]
    return sorted(dict.fromkeys(found))


def _is_checkout(root: Path) -> bool:
    return any((parent / ".git").exists() for parent in (root, *root.parents))


def _is_staged_copy(root: Path) -> bool:
    """True for a release unpacked under `<state>/updates/versions/<tag>/source`.

    A Pilot that was updated before this existed serves from such a copy, and
    it is not an installation: writing a newer release into it would leave the
    pointer removed and the next start falling back to whatever the launcher
    points at, which is older. Refusing keeps the pointer, which is correct.
    """
    return any(parent.name == "versions" and parent.parent.name == "updates"
               for parent in root.parents)


def _writable(root: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".mms-write-probe-"):
            return True
    except OSError:
        return False


def describe(source: Path | str) -> dict:
    """Whether an in-page update can replace the installation it runs from."""
    # Total by construction: the update status calls this on every poll, and
    # an unusable value has to read as "cannot install", never as an error.
    root = Path(str(source or ".")).resolve()
    if not root.is_dir():
        return {"updatesCli": False, "root": str(root), "reason": "找不到安装目录，更新只换网页服务。"}
    if _is_checkout(root):
        return {"updatesCli": False, "root": str(root),
                "reason": "这是源码检出，更新不会改工作树；命令行请用 git 更新。"}
    if _is_staged_copy(root):
        return {"updatesCli": False, "root": str(root), "manualInstallRequired": True,
                "reason": "当前服务跑的是上一次更新的暂存副本，不是安装目录；请重新安装一次，之后更新就会同时换掉命令行。"}
    if not _writable(root):
        return {"updatesCli": False, "root": str(root),
                "reason": "安装目录不可写，更新只换网页服务。"}
    if _legacy_or_mixed_layout(root):
        return {"updatesCli": False, "root": str(root), "manualInstallRequired": True,
                "reason": "需要重新运行安装命令。当前安装是旧布局或新旧文件混用，应用内更新不能当成普通的「有新版本」。"}
    return {"updatesCli": True, "root": str(root), "reason": ""}


def _legacy_or_mixed_layout(root: Path) -> bool:
    """True when leftover flat modules can shadow lib/ or lib/ is missing."""
    lib_sentinel = (root / "lib" / "mms_core.py").is_file()
    flat_sentinel = (root / "mms_core.py").is_file()
    if flat_sentinel:
        return True
    if not lib_sentinel:
        return True
    lib = root / "lib"
    for path in (*lib.glob("mms_*.py"), *lib.glob("mmc_*.py")):
        if (root / path.name).is_file() or (root / path.name).is_symlink():
            return True
    return False


def remove_legacy_flat_modules(target: Path) -> list[str]:
    """Delete install-root copies of modules now shipped under lib/, by exact name."""
    lib = Path(target) / "lib"
    removed: list[str] = []
    if not lib.is_dir():
        return removed
    names = {path.name for path in lib.glob("mms_*.py")} | {path.name for path in lib.glob("mmc_*.py")}
    for name in names:
        flat = Path(target) / name
        if flat.is_file() or flat.is_symlink():
            flat.unlink()
            removed.append(name)
    return removed


def _copy(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)


def _replace(saved: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    if saved.exists() or saved.is_symlink():
        saved.rename(target)


def install(candidate: Path, source: Path, backup: Path) -> list[str]:
    """Copy the staged release over the installation, restoring on failure.

    Each path is copied beside its target first, so the slow part happens with
    the installation intact and only a pair of renames replaces it.
    """
    candidate, source, backup = Path(candidate), Path(source), Path(backup)
    require_runtime_layout(candidate)
    names = manifest(candidate)
    if not names:
        raise ValueError("staged release carries no installable files")
    backup.mkdir(parents=True, exist_ok=True)
    replaced: list[tuple[str, bool]] = []
    try:
        for name in names:
            target = source / name
            staged = target.with_name(target.name + STAGING_SUFFIX)
            if staged.exists() or staged.is_symlink():
                if staged.is_dir() and not staged.is_symlink():
                    shutil.rmtree(staged)
                else:
                    staged.unlink()
            _copy(candidate / name, staged)
            existed = target.exists() or target.is_symlink()
            if existed:
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                target.rename(saved)
            # Journal the old file before promotion: rename can fail too.
            replaced.append((name, existed))
            staged.rename(target)
    except Exception:
        for name, existed in reversed(replaced):
            target = source / name
            if existed:
                _replace(backup / name, target)
            elif target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        raise
    remove_legacy_flat_modules(source)
    return names


def record_committed_install(config_root: Path, state_root: Path, operation: dict, version: str) -> str:
    """Record the verified installed copy, including upgrades run by old guardians.

    Called by the NEW candidate at commit. A checkout/staged-only update has
    no successful installation receipt and must not relabel the user's CLI.
    Metadata failure is visible but never rolls back verified source files.
    """
    from .runtime import private_json
    from .updates import fetch_tag_release, read_json
    try:
        operation_id = str(operation.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation_id):
            raise ValueError("invalid operation id")
        receipt = read_json(Path(state_root) / "updates/operations" / operation_id / "installation.json")
        if receipt.get("installed") is not True:
            return ""
        tag = "v" + version
        if operation.get("target") != tag or receipt.get("version") != tag:
            raise ValueError("installation version mismatch")
        prerelease = operation.get("prerelease")
        if not isinstance(prerelease, bool):
            # Old updaters did not retain this flag. Query this exact release,
            # never infer it from a tag or the mutable update-check setting.
            prerelease = fetch_tag_release(tag)["prerelease"]
        if not isinstance(prerelease, bool):
            raise ValueError("unknown release classification")
        path = Path(config_root) / "version.json"
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(previous, dict):
            raise ValueError("invalid installation metadata")
        series = version.split(".", 1)[0] + ".x"
        private_json(path, {**previous, "installed_ref": tag, "installed_version": tag,
                           "install_channel": "preview" if prerelease else "stable",
                           "release_track": "dev" if prerelease else "stable",
                           "release_track_series": series, "release_track_version": version,
                           "release_track_label": series + (" Preview" if prerelease else " Stable"),
                           "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                           "source": "pilot-update"})
    except Exception:
        return "安装版本记录未能更新，代码升级已完成；请检查配置目录的写入权限或稍后重新安装。"
    return ""
