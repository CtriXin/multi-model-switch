"""An in-page update replaces the installation too, or says why it cannot (#193)."""
import json
import re
import shutil
from pathlib import Path

import pytest

from mms_web.update_install import DIRECTORIES, FILES, GLOBS, describe, install, manifest
from mms_web.updates import upgrade_notice

ROOT = Path(__file__).resolve().parents[1]


def _release(root: Path, *, version: str) -> Path:
    """A staged source shaped like the release tarball, only smaller."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "mms").write_text(f"#!/usr/bin/env python3\n# {version}\n")
    (root / "mmf").write_text(f"#!/bin/sh\n# {version}\n")
    (root / "mms_core.py").write_text(f'VERSION_MARK = "{version}"\n')
    (root / "mms_version.py").write_text(f'VERSION = "{version}"\n')
    (root / "mms_web").mkdir()
    (root / "mms_web" / "__main__.py").write_text(f"# {version}\n")
    (root / "config").mkdir()
    (root / "config" / "provider-profiles.json").write_text("{}\n")
    return root


def test_the_manifest_covers_everything_install_sh_copies():
    """The two copy lists have to agree, or an update leaves files behind."""
    copied = set()
    for line in (ROOT / "install.sh").read_text(encoding="utf-8").splitlines():
        # Only statements that put a source path into the installation count;
        # the installer also reads templates it never copies.
        if "$MMS_HOME" not in line or not re.search(r"\b(cp|copy_dir_safely|copy_hooks_dir_safely)\b", line):
            continue
        # Both spellings the installer uses, including paths with a space.
        for pattern in (r'"\$SOURCE_DIR/([^"]+)"', r'"\$SOURCE_DIR"/(\S+)'):
            for match in re.finditer(pattern, line):
                copied.add(match.group(1).strip('"'))
    assert copied, "install.sh copy statements are no longer recognisable"
    known = set(FILES) | set(DIRECTORIES)
    for name in sorted(copied):
        if name in known or name in {n.split("/")[0] for n in known}:
            continue
        if any(Path(name).match(pattern) for pattern in GLOBS):
            continue
        pytest.fail(f"install.sh copies {name!r} into the installation but update_install does not")


def test_manifest_lists_only_what_the_release_actually_has(tmp_path):
    names = manifest(_release(tmp_path / "candidate", version="9.9.9"))
    assert names == ["config", "mmf", "mms", "mms_core.py", "mms_version.py", "mms_web"]
    assert "vendor" not in names and "MMS Pilot.command" not in names


def test_a_source_checkout_is_never_written_to(tmp_path):
    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    verdict = describe(checkout)
    assert verdict["updatesCli"] is False
    assert "源码检出" in verdict["reason"]
    # A directory nested inside a checkout is still the checkout.
    nested = checkout / "worktrees" / "issue-1"
    nested.mkdir(parents=True)
    assert describe(nested)["updatesCli"] is False


def test_a_real_installation_is_installable(tmp_path):
    verdict = describe(_release(tmp_path / "installed", version="1.0.0"))
    assert verdict["updatesCli"] is True and verdict["reason"] == ""


def test_install_replaces_the_installation_and_keeps_local_state(tmp_path):
    installed = _release(tmp_path / "installed", version="1.0.0")
    # Local state the release does not carry must survive the update.
    (installed / ".venv").mkdir()
    (installed / ".venv" / "pyvenv.cfg").write_text("home = /usr\n")
    (installed / "logs").mkdir()
    (installed / "logs" / "mms-web.log").write_text("old log\n")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    (candidate / "mmslogs").write_text("#!/bin/sh\n# 2.0.0\n")

    names = install(candidate, installed, tmp_path / "backup")

    assert "mmslogs" in names
    assert 'VERSION = "2.0.0"' in (installed / "mms_version.py").read_text()
    assert "# 2.0.0" in (installed / "mms_web" / "__main__.py").read_text()
    assert (installed / "mmslogs").is_file()
    assert (installed / ".venv" / "pyvenv.cfg").read_text() == "home = /usr\n"
    assert (installed / "logs" / "mms-web.log").read_text() == "old log\n"
    assert not list(installed.glob("*.mms-update-new"))
    assert 'VERSION = "1.0.0"' in (tmp_path / "backup" / "mms_version.py").read_text()


def test_a_failed_install_puts_the_previous_version_back(tmp_path, monkeypatch):
    installed = _release(tmp_path / "installed", version="1.0.0")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    real_copytree = shutil.copytree
    calls = {"n": 0}

    def explode(source, target, **kwargs):
        # Fail on the directory, after the plain files have been replaced.
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("disk full")
        return real_copytree(source, target, **kwargs)

    monkeypatch.setattr("mms_web.update_install.shutil.copytree", explode)
    with pytest.raises(OSError):
        install(candidate, installed, tmp_path / "backup")

    # Every replaced path is back at the version that was serving.
    assert 'VERSION = "1.0.0"' in (installed / "mms_version.py").read_text()
    assert "# 1.0.0" in (installed / "mms_web" / "__main__.py").read_text()
    assert (installed / "mms").read_text().endswith("# 1.0.0\n")
    assert not list(installed.glob("*.mms-update-new"))


def test_an_added_path_is_removed_again_when_the_install_fails(tmp_path, monkeypatch):
    installed = _release(tmp_path / "installed", version="1.0.0")
    candidate = _release(tmp_path / "candidate", version="2.0.0")
    (candidate / "mmslogs").write_text("new file\n")
    real_copy = shutil.copy2

    def explode(source, target, **kwargs):
        if Path(source).name == "mms_version.py":
            raise OSError("disk full")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr("mms_web.update_install.shutil.copy2", explode)
    with pytest.raises(OSError):
        install(candidate, installed, tmp_path / "backup")
    assert not (installed / "mmslogs").exists()


def test_the_upgrade_notice_is_the_release_section_and_nothing_else():
    body = """# v4.15.0 标题

- 平常的条目

## 升级须知

- 端口从 8766 回到 8765
- `mmd` 不再可用

### 细节

仍属于须知。

## 其它变化

不该出现。
"""
    notice = upgrade_notice(body)
    assert "端口从 8766 回到 8765" in notice
    assert "仍属于须知" in notice
    assert "不该出现" not in notice
    assert "平常的条目" not in notice
    # A release without the section declares no cost, which is not an error.
    assert upgrade_notice("# v4.15.0\n\n- 只有普通条目\n") == ""
    assert upgrade_notice(None) == ""


def _spec(tmp_path, *, old_source: Path, staged: Path) -> dict:
    state = tmp_path / "state"
    (state / "updates").mkdir(parents=True)
    operation_root = state / "updates" / "operations" / "op-1"
    operation_root.mkdir(parents=True)
    return {"state": str(state), "source": str(staged), "oldSource": str(old_source),
            "target": "v2.0.0", "armed": str(operation_root / "armed")}


def test_a_verified_update_replaces_the_installation_and_drops_the_pointer(tmp_path):
    """With the installation on the new version, the staged copy is not needed."""
    from mms_web.update_handoff import install_alongside

    installed = _release(tmp_path / "installed", version="1.0.0")
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=installed, staged=staged)

    assert install_alongside(spec) is True
    assert 'VERSION = "2.0.0"' in (installed / "mms_version.py").read_text()
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is True and report["root"] == str(installed)


def test_a_checkout_keeps_serving_from_the_staged_copy(tmp_path):
    """Refusing to touch a worktree must not cost the user the update."""
    from mms_web.update_handoff import install_alongside

    checkout = _release(tmp_path / "repo", version="1.0.0")
    (checkout / ".git").mkdir()
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=checkout, staged=staged)

    assert install_alongside(spec) is False
    assert 'VERSION = "1.0.0"' in (checkout / "mms_version.py").read_text()
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is False and "源码检出" in report["reason"]


def test_a_failed_installation_is_reported_and_not_claimed(tmp_path, monkeypatch):
    from mms_web.update_handoff import install_alongside

    installed = _release(tmp_path / "installed", version="1.0.0")
    staged = _release(tmp_path / "staged", version="2.0.0")
    spec = _spec(tmp_path, old_source=installed, staged=staged)
    monkeypatch.setattr("mms_web.update_install.manifest", lambda _source: [])

    assert install_alongside(spec) is False
    report = json.loads((Path(spec["armed"]).parent / "installation.json").read_text())
    assert report["installed"] is False and "ValueError" in report["reason"]
