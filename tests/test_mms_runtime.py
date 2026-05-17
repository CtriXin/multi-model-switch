import sys


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

    assert resolved == str(claude.resolve())


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

    assert binary == str(claude.resolve())
    assert cmd[0] == str(claude.resolve())
    assert env["PATH"].split(":")[0] == str(node22.resolve())
