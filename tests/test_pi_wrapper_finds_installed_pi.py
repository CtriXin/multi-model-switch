"""The wrapper must use an installed Pi, not only the npx cache.

A machine with pi installed globally but its bin directory outside the
launching process's PATH used to fail with "cache warmup did not produce an
executable": npx exits 0 without filling the cache while a global copy
exists, so the cache was the only option and it was always empty.
"""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "pi-cli-wrapper.sh"


def _fake_pi(path: Path, *, marker: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\necho "{marker}"\n')
    path.chmod(0o755)
    return path


def _cached(cache: Path, *, marker: str) -> Path:
    binary = cache / "_npx" / "abc123" / "node_modules" / ".bin" / "pi"
    manifest = binary.parent.parent / "@earendil-works" / "pi-coding-agent" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}")
    return _fake_pi(binary, marker=marker)


def _run(tmp_path, *, path_dirs, cache, npm=None, timeout=60):
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join([*(str(d) for d in path_dirs), "/usr/bin", "/bin"]),
        "MMS_PI_NPX_CACHE": str(cache),
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    if npm:
        env["PATH"] = os.pathsep.join([str(npm), env["PATH"]])
    return subprocess.run(["sh", str(WRAPPER), "--version"], env=env,
                          capture_output=True, text=True, timeout=timeout)


def test_a_pi_on_path_is_used_even_with_an_empty_cache(tmp_path):
    bin_dir = tmp_path / "global-bin"
    _fake_pi(bin_dir / "pi", marker="global-pi")
    cache = tmp_path / "cache"
    cache.mkdir()

    result = _run(tmp_path, path_dirs=[bin_dir], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "global-pi"


def test_npms_global_prefix_is_consulted_when_path_has_no_pi(tmp_path):
    """npm install -g succeeded, but its bin is not on this PATH."""
    prefix = tmp_path / "npm-prefix"
    _fake_pi(prefix / "bin" / "pi", marker="prefix-pi")
    npm_dir = tmp_path / "npm-stub"
    npm_dir.mkdir()
    npm = npm_dir / "npm"
    npm.write_text(f'#!/bin/sh\nif [ "$1" = "prefix" ]; then echo "{prefix}"; exit 0; fi\nexit 1\n')
    npm.chmod(0o755)
    cache = tmp_path / "cache"
    cache.mkdir()

    result = _run(tmp_path, path_dirs=[], cache=cache, npm=npm_dir)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "prefix-pi"


def test_the_cache_still_wins_when_nothing_is_installed(tmp_path):
    cache = tmp_path / "cache"
    _cached(cache, marker="cached-pi")

    result = _run(tmp_path, path_dirs=[], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cached-pi"


def test_a_pi_on_path_that_is_this_wrapper_is_not_executed_again(tmp_path):
    """`pi` on PATH can be a symlink to this script; execing it would loop."""
    bin_dir = tmp_path / "loop-bin"
    bin_dir.mkdir()
    (bin_dir / "pi").symlink_to(WRAPPER)
    cache = tmp_path / "cache"
    _cached(cache, marker="cached-pi")

    result = _run(tmp_path, path_dirs=[bin_dir], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "cached-pi"


def test_the_failure_message_names_both_places_it_looked(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    npm_dir = tmp_path / "npm-stub"
    npm_dir.mkdir()
    # npx exits 0 without filling the cache, the shape that produced the bug.
    for name in ("npx", "npm"):
        stub = npm_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)

    result = _run(tmp_path, path_dirs=[], cache=cache, npm=npm_dir)

    assert result.returncode != 0
    assert "npm's global prefix" in result.stderr
