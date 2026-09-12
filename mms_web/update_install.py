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

import shutil
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
GLOBS = ("mms_*.py",)
DIRECTORIES = (
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
    return {"updatesCli": True, "root": str(root), "reason": ""}


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
            staged.rename(target)
            replaced.append((name, existed))
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
    return names
