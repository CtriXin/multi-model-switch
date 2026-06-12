from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _mission_root(tmp_path: Path, *, state: str = "ready-for-agent") -> Path:
    root = tmp_path / "mission-root"
    (root / ".mission").mkdir(parents=True)
    (root / ".work-gate" / "state").mkdir(parents=True)
    (root / ".mission" / "readiness.json").write_text(
        json.dumps({"state": state}) + "\n",
        encoding="utf-8",
    )
    (root / ".mission" / "agent-brief.md").write_text("# Agent Brief\n", encoding="utf-8")
    (root / ".mission" / "mission-prd.md").write_text("# Mission PRD\n", encoding="utf-8")
    (root / ".work-gate" / "state" / "check-spec.json").write_text(
        json.dumps({"checks": [{"id": "WD-1", "description": "review dispatch"}]}) + "\n",
        encoding="utf-8",
    )
    return root


def test_review_dispatch_dry_run_is_codex_claude_callable(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "dry-run-review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["models"] == ["gpt-5.4", "qwen3.7-max"]
    assert payload["opencode_profile"] == "review"
    assert payload["opencode_launch_command"][:5] == [
        sys.executable,
        str(REPO_ROOT / "mms"),
        "opencode",
        "--profile",
        "review",
    ]
    assert payload["review_hub_prompt"].startswith("/review-hub ")
    assert not Path(payload["request_root"]).exists()


def test_review_dispatch_blocks_unready_mission_root(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path, state="needs-info")
    code = handle_review_dispatch_command(["--root", str(root), "--json"], command_name="mms")

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "readiness state blocks dispatch: needs-info" in payload["errors"]


def test_mms_review_dispatch_entrypoint_works_for_codex_claude(tmp_path):
    root = _mission_root(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "mms"),
            "review-dispatch",
            "--root",
            str(root),
            "--request-id",
            "entrypoint-review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--dry-run",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["request_id"] == "entrypoint-review"
    assert payload["opencode_profile"] == "review"


def test_review_dispatch_fake_run_writes_multi_model_results(tmp_path, capsys):
    if shutil.which("review-hub") is None:
        pytest.skip("review-hub CLI is not installed")

    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "fake-review",
            "--title",
            "Fake multi-model review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--fake-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["fake_run"] is True
    assert payload["worker_plan"]["worker_count"] == 2
    assert payload["aggregate"]["reviewers_complete"] == 2
    request_root = Path(payload["request_root"])
    assert (request_root / "mms-review-dispatch.json").exists()
    assert (request_root / "aggregate" / "aggregate.json").exists()
    for result in payload["fake_results"]:
        verify_root = Path(result["verify_root"])
        assert (verify_root / "04-final-verdict.md").exists()
