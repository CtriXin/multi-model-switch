import json
import os
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT_DIR / "hooks"
WRAPPER = HOOKS_DIR / "nsr-stop-wrapper.py"
NSRCTL = HOOKS_DIR / "nsrctl.py"


def _run_wrapper(repo: Path, payload: dict, *, host: str = "codex", extra_env: dict[str, str] | None = None):
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(repo.parent / "home"),
            "REAL_HOME": str(repo.parent / "home"),
            "MMS_REAL_HOME": str(repo.parent / "home"),
            "LOOP_STATE_FILE": ".loop_state_mms_test.json",
            "LOOP_MAX_NO_CHANGE": "99",
            "LOOP_MAX_STEPS": "2",
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["python3", str(WRAPPER), host],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=repo,
        env=env,
        check=False,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    return repo


def test_bundled_nsr_wrapper_is_inactive_until_marker(tmp_path):
    repo = _init_repo(tmp_path)

    completed = _run_wrapper(repo, {"hook_event_name": "Stop", "cwd": str(repo)})

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {}
    assert not (repo / ".loop_state_mms_test.json").exists()


def test_bundled_nsr_wrapper_noops_non_stop_events_when_active(tmp_path):
    repo = _init_repo(tmp_path)
    subprocess.run(["python3", str(NSRCTL), "enable", str(repo)], check=True, capture_output=True, text=True)

    codex_result = _run_wrapper(repo, {"hook_event_name": "PreCompact", "cwd": str(repo)}, host="codex")
    claude_result = _run_wrapper(repo, {"hook_event_name": "PreCompact", "cwd": str(repo)}, host="claude")

    assert json.loads(codex_result.stdout) == {}
    assert json.loads(claude_result.stdout) == {"continue": True}
    assert not (repo / ".loop_state_mms_test.json").exists()


def test_bundled_nsr_wrapper_delegates_stop_loop_and_disables_after_allow(tmp_path):
    repo = _init_repo(tmp_path)
    status = subprocess.run(["python3", str(NSRCTL), "enable", str(repo)], check=True, capture_output=True, text=True)
    marker = Path(status.stdout.strip().split(": ", 1)[1])

    first = _run_wrapper(repo, {"hook_event_name": "Stop", "cwd": str(repo)})
    second = _run_wrapper(repo, {"hook_event_name": "Stop", "cwd": str(repo)})

    assert first.returncode == 0
    assert json.loads(first.stdout)["decision"] == "block"
    assert second.returncode == 0
    assert json.loads(second.stdout) == {}
    assert not marker.exists()
