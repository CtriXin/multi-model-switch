from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mms_pi_executor
import mms_pi_watchdog


MODEL = "kimi-for-coding"
API_KEY = "sk-pi-executor-test-secret-123456"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(root: Path) -> Path:
    generated = root / "generated"
    provider = "direct-kimi-test"
    payloads = {
        "router": (
            "model-routes.json",
            {
                "version": 1,
                "routes": {
                    MODEL: {
                        "primary": {
                            "provider_id": provider,
                            "anthropic_base_url": "https://kimi.example.test/coding",
                            "openai_base_url": "",
                            "api_key": API_KEY,
                            "model_id": MODEL,
                        },
                        "fallbacks": [],
                    }
                },
            },
            "secret",
        ),
        "lineup": (
            "model-routes.lineup.json",
            {"version": 1, "routes": {MODEL: {"primary": {"provider_id": provider, "model_id": MODEL, "max_context_tokens": 200_000}}}},
            "non-secret",
        ),
        "profile": ("provider-profiles.generated.json", {"version": 1, "profiles": {provider: {}}}, "non-secret"),
        "policy": (
            "model-policy.effective.json",
            {"version": 1, "models": {MODEL: {"visible": True, "capabilities": {"text": True}}}},
            "non-secret",
        ),
        "capabilities": (
            "model-capabilities.approved.json",
            {"version": 1, "models": [{"alias": MODEL, "model": MODEL, "official_context_window_tokens": 200_000}]},
            "non-secret",
        ),
    }
    files = {}
    for key, (filename, payload, sensitivity) in payloads.items():
        path = generated / filename
        _write_json(path, payload)
        files[key] = {"canonical_path": f"generated/{filename}", "legacy_alias_path": "", "sha256": _sha256(path), "sensitivity": sensitivity}
    _write_json(
        generated / "model-registry.latest-approved.json",
        {
            "schema": "mms.model_registry.latest_approved.v1",
            "bundle_revision": "bundle_pi_executor_test",
            "model_registry_revision": "bundle_pi_executor_test",
            "capability_revision": "cap_pi_executor_test",
            "route_revision": "route_pi_executor_test",
            "policy_revision": "policy_pi_executor_test",
            "profile_revision": "profile_pi_executor_test",
            "files": files,
        },
    )
    return root


def _repo(root: Path) -> tuple[Path, str]:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Pi Executor Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "pi-executor@test.invalid"], cwd=repo, check=True)
    (repo / "app.txt").write_text("before\n", encoding="utf-8")
    (repo / "readonly.txt").write_text("fixed\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, commit


def _pack(path: Path, commit: str, *, writable: list[str] | None = None, validation: list[str] | None = None) -> Path:
    payload = {
        "schema": "executor.pack.v1",
        "task_id": "executor-test",
        "title": "Bounded change",
        "objective": "Change app.txt from before to after.",
        "task_kind": "implement",
        "difficulty": "D2",
        "commit": commit,
        "status": "ready_for_executor",
        "allowed": True,
        "blocking_count": 0,
        "writable_files": writable or ["app.txt"],
        "read_only_files": ["readonly.txt"],
        "forbidden_files": [".env"],
        "success_criteria": ["app.txt contains after"],
        "validation_commands": validation if validation is not None else [f"{sys.executable} -c 'from pathlib import Path; assert Path(\"app.txt\").read_text() == \"after\\n\"'"],
        "non_goals": ["Do not modify readonly.txt"],
    }
    _write_json(path, payload)
    return path


def _pi_outcome(text: str | None = None) -> mms_pi_watchdog.ProcessOutcome:
    response = text or json.dumps(
        {
            "verdict": "implemented",
            "summary": "changed app",
            "changed_files": ["app.txt"],
            "criteria": [],
            "self_assessment": {"confidence": 90, "completion": 100, "risk": "low"},
            "residual_risks": [],
        }
    )
    stdout = json.dumps(
        {
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "stopReason": "stop",
                "content": [{"type": "text", "text": response}],
                "usage": {"input": 10, "output": 20},
            },
        }
    ) + "\n"
    return mms_pi_watchdog.ProcessOutcome(
        terminal_reason="completed",
        returncode=0,
        stdout=stdout,
        stderr="",
        elapsed_ms=10,
        stdout_bytes=len(stdout),
        stderr_bytes=0,
        peak_repeated_events=1,
        terminated=False,
        forced_kill=False,
    )


def _validation_outcome(*, returncode: int = 0) -> mms_pi_watchdog.ProcessOutcome:
    return mms_pi_watchdog.ProcessOutcome(
        terminal_reason="completed",
        returncode=returncode,
        stdout="validation ok\n" if returncode == 0 else "",
        stderr="" if returncode == 0 else "validation failed\n",
        elapsed_ms=5,
        stdout_bytes=14 if returncode == 0 else 0,
        stderr_bytes=0 if returncode == 0 else 18,
        peak_repeated_events=1,
        terminated=False,
        forced_kill=False,
    )


def test_load_pack_normalizes_commit_and_argv(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    pack = mms_pi_executor.load_pack(_pack(tmp_path / "pack.json", commit), target_repo=repo)

    assert pack["base_commit"] == commit
    assert pack["validation_commands"][0][0] == sys.executable
    assert pack["writable_files"] == ["app.txt"]


@pytest.mark.parametrize("unsafe", ["/tmp/escape", "../escape", "dir\\escape"])
def test_pack_rejects_unsafe_writable_path(tmp_path: Path, unsafe: str) -> None:
    repo, commit = _repo(tmp_path)
    with pytest.raises(mms_pi_executor.ExecutorError, match="unsafe path"):
        mms_pi_executor.load_pack(_pack(tmp_path / "pack.json", commit, writable=[unsafe]), target_repo=repo)


def test_dry_run_uses_explicit_model_and_never_exposes_key(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    result = mms_pi_executor.run_executor(
        config_root=_bundle(tmp_path / "config"),
        pack_path=_pack(tmp_path / "pack.json", commit),
        target_repo=repo,
        explicit_models=[MODEL],
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["plan"]["selection"]["models"] == [MODEL]
    assert result["plan"]["isolation"]["worker_tools"] == "read,grep,find,ls,edit,write"
    assert result["plan"]["isolation"]["bash_enabled"] is False
    rendered = json.dumps(result)
    assert API_KEY not in rendered
    assert "/coding/v1/messages" in rendered


def test_scope_audit_protected_and_unspecified_paths() -> None:
    pack = {"writable_files": ["src/**"], "read_only_files": ["src/fixed.py"], "forbidden_files": [".env"]}
    violations = mms_pi_executor._scope_violations(["src/ok.py", "src/fixed.py", ".env", "README.md"], pack)

    assert violations == [
        {"path": "src/fixed.py", "reason": "read_only"},
        {"path": ".env", "reason": "forbidden"},
        {"path": "README.md", "reason": "outside_writable_scope"},
    ]


def test_capture_change_set_includes_tracked_and_untracked(tmp_path: Path) -> None:
    repo, commit = _repo(tmp_path)
    (repo / "app.txt").write_text("after\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    captured = mms_pi_executor._capture_change_set(repo, commit)

    assert captured["changed_files"] == ["app.txt", "new.txt"]
    assert "before" in captured["patch"]
    assert "new.txt" in captured["patch"]


@pytest.mark.skipif(not Path("/usr/bin/sandbox-exec").is_file(), reason="macOS sandbox-exec only")
def test_sandbox_profile_allows_worktree_and_denies_external_write(tmp_path: Path) -> None:
    temp_root = tmp_path / "allowed"
    worktree = temp_root / "worktree"
    cache = temp_root / "cache"
    denied = tmp_path / "denied.txt"
    worktree.mkdir(parents=True)
    cache.mkdir()
    profile = mms_pi_executor._sandbox_profile(temp_root=temp_root, worktree=worktree)
    code = (
        "from pathlib import Path; "
        f"Path({str(worktree / 'ok.txt')!r}).write_text('ok'); "
        f"Path({str(denied)!r}).write_text('bad')"
    )
    proc = subprocess.run(["/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    assert proc.returncode != 0
    assert (worktree / "ok.txt").read_text() == "ok"
    assert not denied.exists()


def test_shared_pi_cache_is_not_a_sandbox_write_surface(tmp_path: Path) -> None:
    temp_root = tmp_path / "temp"
    worktree = temp_root / "worktree"
    worktree.mkdir(parents=True)
    shared_cache = tmp_path / "shared-cache"
    shared_cache.mkdir()

    profile = mms_pi_executor._sandbox_profile(temp_root=temp_root, worktree=worktree)

    assert str(shared_cache) not in profile
    assert '(deny file-write*)' in profile


def test_cached_pi_executable_must_resolve_inside_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    binary = cache / "_npx" / "hash" / "node_modules" / ".bin" / "pi"
    target = cache / "_npx" / "hash" / "node_modules" / "pkg" / "cli.js"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    target.chmod(0o755)
    binary.parent.mkdir(parents=True)
    binary.symlink_to(Path("../pkg/cli.js"))

    assert mms_pi_executor._cached_pi_executable(cache) == target.resolve()

    binary.unlink()
    binary.symlink_to(Path(sys.executable))
    assert mms_pi_executor._cached_pi_executable(cache) is None


def test_live_candidate_produces_admissible_patch_without_touching_checkout(tmp_path: Path, monkeypatch) -> None:
    repo, commit = _repo(tmp_path)
    worktrees: list[Path] = []

    def fake_run(command, *, cwd, env, policy, cancellation=None):
        cwd = Path(cwd)
        if "--provider" in command:
            worktrees.append(cwd)
            assert Path(env["MMS_PI_NPX_CACHE"]).is_relative_to(cwd.parent)
            (cwd / "app.txt").write_text("after\n", encoding="utf-8")
            return _pi_outcome(API_KEY + " should be redacted")
        return _validation_outcome()

    monkeypatch.setattr(mms_pi_executor.mms_pi_watchdog, "run_process", fake_run)
    result = mms_pi_executor.run_executor(
        config_root=_bundle(tmp_path / "config"),
        pack_path=_pack(tmp_path / "pack.json", commit),
        target_repo=repo,
        explicit_models=[MODEL],
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["status"] == "success"
    row = result["results"][0]
    assert row["admissible"] is True
    assert row["changed_files"] == ["app.txt"]
    assert row["validation"][0]["status"] == "passed"
    assert Path(row["patch"]["path"]).is_file()
    assert API_KEY not in json.dumps(result)
    assert (repo / "app.txt").read_text() == "before\n"
    assert all(not path.exists() for path in worktrees)
    listed = subprocess.check_output(["git", "worktree", "list", "--porcelain"], cwd=repo, text=True)
    assert "mms-pi-executor" not in listed


def test_out_of_scope_change_is_rejected_and_not_applied(tmp_path: Path, monkeypatch) -> None:
    repo, commit = _repo(tmp_path)

    def fake_run(command, *, cwd, env, policy, cancellation=None):
        cwd = Path(cwd)
        if "--provider" in command:
            (cwd / "app.txt").write_text("after\n", encoding="utf-8")
            (cwd / "readonly.txt").write_text("changed\n", encoding="utf-8")
            return _pi_outcome()
        pytest.fail("validation must not run for a scope violation")

    monkeypatch.setattr(mms_pi_executor.mms_pi_watchdog, "run_process", fake_run)
    result = mms_pi_executor.run_executor(
        config_root=_bundle(tmp_path / "config"),
        pack_path=_pack(tmp_path / "pack.json", commit),
        target_repo=repo,
        explicit_models=[MODEL],
        artifact_dir=tmp_path / "artifacts",
    )

    row = result["results"][0]
    assert result["status"] == "failed"
    assert row["status"] == "rejected"
    assert row["rejection_reasons"] == ["scope_violation"]
    assert row["scope_violations"] == [{"path": "readonly.txt", "reason": "read_only"}]
    assert (repo / "readonly.txt").read_text() == "fixed\n"


def test_validation_failure_rejects_candidate(tmp_path: Path, monkeypatch) -> None:
    repo, commit = _repo(tmp_path)

    def fake_run(command, *, cwd, env, policy, cancellation=None):
        if "--provider" in command:
            (Path(cwd) / "app.txt").write_text("after\n", encoding="utf-8")
            return _pi_outcome()
        return _validation_outcome(returncode=1)

    monkeypatch.setattr(mms_pi_executor.mms_pi_watchdog, "run_process", fake_run)
    result = mms_pi_executor.run_executor(
        config_root=_bundle(tmp_path / "config"),
        pack_path=_pack(tmp_path / "pack.json", commit),
        target_repo=repo,
        explicit_models=[MODEL],
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["results"][0]["rejection_reasons"] == ["validation_failed"]


def test_validation_source_mutation_rejects_candidate(tmp_path: Path, monkeypatch) -> None:
    repo, commit = _repo(tmp_path)

    def fake_run(command, *, cwd, env, policy, cancellation=None):
        cwd = Path(cwd)
        if "--provider" in command:
            (cwd / "app.txt").write_text("after\n", encoding="utf-8")
            return _pi_outcome()
        (cwd / "app.txt").write_text("mutated by validation\n", encoding="utf-8")
        return _validation_outcome()

    monkeypatch.setattr(mms_pi_executor.mms_pi_watchdog, "run_process", fake_run)
    result = mms_pi_executor.run_executor(
        config_root=_bundle(tmp_path / "config"),
        pack_path=_pack(tmp_path / "pack.json", commit),
        target_repo=repo,
        explicit_models=[MODEL],
        artifact_dir=tmp_path / "artifacts",
    )

    assert result["results"][0]["rejection_reasons"] == ["validation_mutated_worktree"]


def test_live_execution_fails_closed_without_sandbox(tmp_path: Path, monkeypatch) -> None:
    repo, commit = _repo(tmp_path)
    monkeypatch.setattr(mms_pi_executor.shutil, "which", lambda _name: None)

    with pytest.raises(mms_pi_executor.ExecutorError, match="sandbox-exec is required"):
        mms_pi_executor.run_executor(
            config_root=_bundle(tmp_path / "config"),
            pack_path=_pack(tmp_path / "pack.json", commit),
            target_repo=repo,
            explicit_models=[MODEL],
            artifact_dir=tmp_path / "artifacts",
        )


def test_pi_wrapper_executes_explicit_read_only_cached_binary(tmp_path: Path) -> None:
    executable = tmp_path / "fake-pi"
    executable.write_text("#!/bin/sh\nprintf 'fake-pi:%s\\n' \"$*\"\n", encoding="utf-8")
    executable.chmod(0o755)
    env = dict(os.environ)
    env["MMS_PI_EXECUTABLE"] = str(executable)

    proc = subprocess.run(
        [str(Path(__file__).resolve().parents[1] / "scripts" / "pi-cli-wrapper.sh"), "--probe", "ok"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert proc.returncode == 0
    assert proc.stdout == "fake-pi:--probe ok\n"
