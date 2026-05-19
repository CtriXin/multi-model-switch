import sys
from types import SimpleNamespace


def test_runtime_accepts_current_supported_python():
    import mms_runtime

    assert sys.version_info >= mms_runtime.MIN_PYTHON
    assert mms_runtime.ensure_supported_python("MMS") is None


def test_runtime_candidate_list_prefers_explicit_python(monkeypatch):
    import mms_runtime

    monkeypatch.setenv("MMS_PYTHON", "/tmp/custom-python")

    candidates = mms_runtime._candidate_pythons()

    assert candidates[0] == "/tmp/custom-python"
    assert "python3.11" in candidates


def test_runtime_reexecs_even_when_reexec_flag_is_inherited(monkeypatch):
    import mms_runtime

    captured = {}
    fake_sys = SimpleNamespace(
        version_info=(3, 9, 0),
        executable="/usr/bin/python3",
        argv=["mms", "resume", "--help"],
        stderr=SimpleNamespace(write=lambda value: captured.setdefault("stderr", value)),
    )

    monkeypatch.setenv("MMS_PYTHON_REEXEC", "1")
    monkeypatch.setattr(mms_runtime, "sys", fake_sys)
    monkeypatch.setattr(mms_runtime, "_candidate_pythons", lambda: ["python3.13"])
    monkeypatch.setattr(mms_runtime, "_resolve_python", lambda candidate: "/opt/homebrew/bin/python3.13")
    monkeypatch.setattr(mms_runtime, "_supports_min_python", lambda executable: True)

    def fake_execve(executable, argv, env):
        captured["executable"] = executable
        captured["argv"] = argv
        captured["env"] = env
        raise RuntimeError("stop after exec capture")

    monkeypatch.setattr(mms_runtime.os, "execve", fake_execve)

    try:
        mms_runtime.ensure_supported_python("MMS")
    except RuntimeError as exc:
        assert str(exc) == "stop after exec capture"

    assert captured["executable"] == "/opt/homebrew/bin/python3.13"
    assert captured["argv"] == ["/opt/homebrew/bin/python3.13", "mms", "resume", "--help"]
    assert captured["env"]["MMS_PYTHON_REEXEC"] == "1"
    assert "stderr" not in captured


def test_cli_resolver_finds_claude_in_other_nvm_version(tmp_path, monkeypatch):
    import mms_runtime

    home = tmp_path / "home"
    node20 = home / ".nvm" / "versions" / "node" / "v20.19.0" / "bin"
    node22 = home / ".nvm" / "versions" / "node" / "v22.19.0" / "bin"
    node20.mkdir(parents=True)
    node22.mkdir(parents=True)
    (node20 / "node").write_text("#!/bin/sh\n", encoding="utf-8")
    claude = node22 / "claude"
    claude.write_text("#!/bin/sh\n", encoding="utf-8")
    claude.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))

    resolved = mms_runtime.resolve_cli_binary("claude", env={"HOME": str(home), "PATH": str(node20)})

    assert resolved == str(claude)


def test_prepare_cli_command_prepends_resolved_bin_dir(tmp_path):
    import mms_runtime

    home = tmp_path / "home"
    node22 = home / ".nvm" / "versions" / "node" / "v22.19.0" / "bin"
    node22.mkdir(parents=True)
    claude = node22 / "claude"
    claude.write_text("#!/bin/sh\n", encoding="utf-8")
    claude.chmod(0o755)

    cmd, env, binary = mms_runtime.prepare_cli_command(
        ["claude", "--version"],
        env={"HOME": str(home), "PATH": "/usr/bin"},
    )

    assert binary == str(claude)
    assert cmd[0] == str(claude)
    assert env["PATH"].split(":")[0] == str(node22.resolve())


def test_cli_resolver_preserves_nvm_bin_symlink(tmp_path):
    import mms_runtime

    home = tmp_path / "home"
    node22 = home / ".nvm" / "versions" / "node" / "v22.19.0" / "bin"
    package_bin = home / ".nvm" / "versions" / "node" / "v22.19.0" / "lib" / "node_modules" / "pkg" / "bin"
    node22.mkdir(parents=True)
    package_bin.mkdir(parents=True)
    target = package_bin / "claude.js"
    target.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    target.chmod(0o755)
    symlink = node22 / "claude"
    symlink.symlink_to(target)

    cmd, env, binary = mms_runtime.prepare_cli_command(
        ["claude"],
        env={"HOME": str(home), "PATH": "/usr/bin"},
    )

    assert binary == str(symlink)
    assert cmd[0] == str(symlink)
    assert env["PATH"].split(":")[0] == str(node22)
