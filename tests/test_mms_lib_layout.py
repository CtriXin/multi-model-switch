"""T9a: runtime modules live in lib/, old flat copies cannot shadow them."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from mms_web.update_install import (
    DIRECTORIES,
    FILES,
    GLOBS,
    describe,
    install,
    manifest,
    remove_legacy_flat_modules,
)

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "lib"
CURL = "curl -fsSL https://raw.githubusercontent.com/CtriXin/multi-model-switch/main/install.sh | bash"
PYTHON_ENTRIES = ("mms", "mmf", "mms-web", "mmslogs")
SHELL_ENTRIES = ("mmm", "MMS Pilot.command", "MMS Installer.command")


def _isolated_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "MMS_CONFIG_ROOT",
        "MMS_CONFIG_DIR",
        "REAL_HOME",
        "ORIGINAL_HOME",
        "MMS_REAL_HOME",
        "XDG_CONFIG_HOME",
        "PYTHONPATH",
    ):
        env.pop(key, None)
    env["HOME"] = str(home)
    env["MMS_SKIP_VENV_REEXEC"] = "1"
    env["MMS_TEST_ALLOW_REAL_CONFIG"] = "0"
    return env


def test_new_layout_can_start(tmp_path):
    env = _isolated_env(tmp_path)
    help_run = subprocess.run(
        [sys.executable, str(ROOT / "mms"), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert help_run.returncode == 0, help_run.stderr
    assert "Traceback" not in help_run.stderr
    doctor = subprocess.run(
        [sys.executable, str(ROOT / "mms"), "doctor"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "Traceback" not in doctor.stderr
    assert "ModuleNotFoundError" not in doctor.stderr + doctor.stdout
    assert doctor.returncode in (0, 2), doctor.stderr + doctor.stdout
    module_help = subprocess.run(
        [sys.executable, "-m", "mms_web", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert module_help.returncode == 0, module_help.stderr
    assert "MMS Pilot" in module_help.stdout or "usage" in module_help.stdout.lower()


def test_install_dry_run_plans_lib_not_root_py(tmp_path):
    env = _isolated_env(tmp_path)
    env.update(
        {
            "MMS_INSTALL_LATEST_RELEASE_OVERRIDE": "v4.19.1",
            "MMS_INSTALL_LATEST_TAG_OVERRIDE": "v4.19.1",
        }
    )
    completed = subprocess.run(
        ["bash", str(ROOT / "install.sh"), "--dry-run", "--ref", "v4.19.1"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert f"{tmp_path}/.mms/lib" in completed.stdout or "/lib" in completed.stdout
    assert "runtime module dir" in completed.stdout or "运行时模块目录" in completed.stdout
    assert "would not copy mms_*.py / mmc_*.py onto the install root" in completed.stdout or (
        "不会把 mms_*.py / mmc_*.py 平铺到安装根" in completed.stdout
    )
    assert 'cp "$SOURCE_DIR"/mms_core.py "$MMS_HOME/"' not in completed.stdout


def _extract_shell_function(script: str, name: str) -> str:
    marker = f"{name}() {{"
    start = script.find(marker)
    assert start != -1, name
    body_start = start + len(marker)
    depth = 1
    i = body_start
    while i < len(script):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                return script[start : i + 1]
        i += 1
    raise AssertionError(name)


def test_overwrite_install_removes_exact_flat_copies_and_keeps_user_files(tmp_path):
    home = tmp_path / ".mms"
    lib = home / "lib"
    lib.mkdir(parents=True)
    (lib / "mms_core.py").write_text("NEW=1\n", encoding="utf-8")
    (lib / "mms_version.py").write_text('VERSION = "from-lib"\n', encoding="utf-8")
    (home / "mms_core.py").write_text("OLD=1\n", encoding="utf-8")
    (home / "mms_version.py").write_text('VERSION = "from-root"\n', encoding="utf-8")
    (home / "mms_myhack.py").write_text("keep\n", encoding="utf-8")
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    func = _extract_shell_function(script, "remove_legacy_flat_modules")
    completed = subprocess.run(
        ["bash", "-c", func + '\nremove_legacy_flat_modules "$1"', "cleanup", str(home)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.returncode == 0
    assert not (home / "mms_core.py").exists()
    assert not (home / "mms_version.py").exists()
    assert (home / "mms_myhack.py").read_text(encoding="utf-8") == "keep\n"
    assert (lib / "mms_core.py").is_file()
    removed = remove_legacy_flat_modules(home)
    assert "mms_myhack.py" not in removed


def test_lib_wins_over_a_flat_shadow(tmp_path):
    install_root = tmp_path / "install"
    lib = install_root / "lib"
    lib.mkdir(parents=True)
    (lib / "mms_core.py").write_text("# sentinel\n", encoding="utf-8")
    (lib / "mms_version.py").write_text('VERSION = "from-lib"\n', encoding="utf-8")
    (install_root / "mms_version.py").write_text('VERSION = "from-root"\n', encoding="utf-8")
    (install_root / "mms_core.py").write_text("# old flat\n", encoding="utf-8")
    probe = install_root / "probe.py"
    probe.write_text(
        (ROOT / "mms").read_text(encoding="utf-8").split("if len(sys.argv)", 1)[0]
        + "import mms_version\nprint(mms_version.VERSION)\nprint(mms_version.__file__)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(probe)],
        cwd=install_root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines()[0] == "from-lib"
    assert "/lib/" in completed.stdout.replace("\\", "/")


def _copy_entry(name: str, dest: Path) -> Path:
    src = ROOT / name
    target = dest / name
    shutil.copy2(src, target)
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR)
    return target


def test_old_layout_prints_human_guidance_not_traceback(tmp_path):
    env = _isolated_env(tmp_path)
    for name in PYTHON_ENTRIES:
        entry = _copy_entry(name, tmp_path)
        completed = subprocess.run(
            [sys.executable, str(entry), "--help"],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = completed.stdout + completed.stderr
        assert completed.returncode != 0
        assert CURL in text
        assert "旧布局" in text
        assert "Traceback" not in text
        assert "ModuleNotFoundError" not in text
    for name in SHELL_ENTRIES:
        entry = _copy_entry(name, tmp_path)
        if name == "mmm":
            _copy_entry("mms", tmp_path)
        if name == "MMS Pilot.command":
            _copy_entry("mms-web", tmp_path)
        if name == "MMS Installer.command":
            (tmp_path / "install.sh").write_text("#!/bin/bash\necho should-not-run\n", encoding="utf-8")
        completed = subprocess.run(
            ["bash", str(entry)],
            cwd=tmp_path,
            env=env,
            input="\n",
            capture_output=True,
            text=True,
            timeout=20,
        )
        text = completed.stdout + completed.stderr
        assert completed.returncode != 0
        assert CURL in text
        assert "Traceback" not in text
        assert "ModuleNotFoundError" not in text
        assert "should-not-run" not in text


def test_statusline_old_layout_is_one_line(tmp_path):
    dest = tmp_path / "statusline-command.sh"
    shutil.copy2(ROOT / "statusline-command.sh", dest)
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
    completed = subprocess.run(
        ["bash", str(dest)],
        cwd=tmp_path,
        input="{}\n",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode != 0
    out = completed.stdout.strip("\n")
    assert "\n" not in out
    assert out == "MMS: 需要重新安装"


def test_update_install_layout_matches_install_sh_and_clears_flats(tmp_path):
    assert "mms_*.py" not in GLOBS
    assert "lib" in DIRECTORIES
    copied = set()
    for line in (ROOT / "install.sh").read_text(encoding="utf-8").splitlines():
        if "$MMS_HOME" not in line or not any(
            token in line for token in ("cp", "copy_dir_safely", "copy_hooks_dir_safely")
        ):
            continue
        for pattern in (r'"\$SOURCE_DIR/([^"]+)"', r'"\$SOURCE_DIR"/(\S+)'):
            import re

            for match in re.finditer(pattern, line):
                copied.add(match.group(1).strip('"'))
    known = set(FILES) | set(DIRECTORIES)
    for name in sorted(copied):
        if name in known or name in {n.split("/")[0] for n in known}:
            continue
        if any(Path(name).match(pattern) for pattern in GLOBS):
            continue
        pytest.fail(f"install.sh copies {name!r} into the installation but update_install does not")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "mms").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    lib = candidate / "lib"
    lib.mkdir()
    (lib / "mms_core.py").write_text("new\n", encoding="utf-8")
    (lib / "mms_version.py").write_text('VERSION = "2"\n', encoding="utf-8")
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "mms_core.py").write_text("old\n", encoding="utf-8")
    (installed / "mms_myhack.py").write_text("keep\n", encoding="utf-8")
    names = manifest(candidate)
    assert "lib" in names
    assert "mms_core.py" not in names
    install(candidate, installed, tmp_path / "backup")
    assert not (installed / "mms_core.py").exists()
    assert (installed / "lib" / "mms_core.py").read_text(encoding="utf-8") == "new\n"
    assert (installed / "mms_myhack.py").read_text(encoding="utf-8") == "keep\n"
    (tmp_path / "mixed").mkdir()
    (tmp_path / "mixed" / "mms_core.py").write_text("old\n", encoding="utf-8")
    (tmp_path / "mixed" / "lib").mkdir()
    (tmp_path / "mixed" / "lib" / "mms_core.py").write_text("new\n", encoding="utf-8")
    verdict = describe(tmp_path / "mixed")
    assert verdict["updatesCli"] is False
    assert verdict.get("manualInstallRequired") is True
    assert "需要重新运行安装命令" in verdict["reason"]


def test_entries_insert_lib_not_install_root():
    source = (ROOT / "mms").read_text(encoding="utf-8")
    assert "sys.path.insert(0, lib)" in source
    assert "sys.path.insert(0, ROOT)" not in source
    assert "_mms_use_lib()" in source
