from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def test_review_launch_help_is_real_subcommand(capsys):
    from mms_review_launch import handle_review_launch_command

    with pytest.raises(SystemExit) as exc:
        handle_review_launch_command(["--help"], command_name="mms")

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "review-launch" in out
    assert "multi-review" in out
    assert "reviewer" in out


def test_review_launch_contract_json_has_required_env(capsys):
    from mms_review_launch import handle_review_launch_command

    assert handle_review_launch_command(["--contract-json"], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "mms.review_launch_contract.v1"
    assert payload["model_dispatch_implemented"] is False
    assert "MOEBIUS_REVIEWER_ID" in payload["required_env"]
    assert "MOEBIUS_REVIEW_EXPECTED_OUTPUT" in payload["required_env"]


def test_review_launch_validate_env_accepts_moebius_contract(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "p50"
    gate_path = run_dir / "review-dispatch-gate.json"
    expected_output = repo_root / ".ai" / "reviews" / "gemini-cli" / "p50-review-20260506.md"
    repo_root.mkdir()
    run_dir.mkdir(parents=True)
    gate_path.write_text(json.dumps({"gate_status": "approved"}) + "\n", encoding="utf-8")

    env = {
        "MOEBIUS_RUN_ID": "p50",
        "MOEBIUS_RUN_DIR": str(run_dir),
        "MOEBIUS_REPO_ROOT": str(repo_root),
        "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG": str(run_dir / "adapter.json"),
        "MOEBIUS_REVIEW_DISPATCH_GATE": str(gate_path),
        "MOEBIUS_REVIEW_DISPATCH_PLAN": str(run_dir / "plan.json"),
        "MOEBIUS_REVIEWER_ID": "gemini-cli",
        "MOEBIUS_REVIEW_EXPECTED_OUTPUT": str(expected_output),
        "MULTI_REVIEW_REVIEWER": "gemini-cli",
        "MOEBIUS_REVIEW_PACK": str(repo_root / ".ai" / "plan" / "review-packs" / "p50.json"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert handle_review_launch_command(["--validate-env"], command_name="mms") == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "mms.review_launch_validation.v1"
    assert payload["ok"] is True
    assert payload["reviewer_id"] == "gemini-cli"
    assert payload["model_calls"] == 0
    assert payload["review_file_writes"] == 0
    assert payload["warnings"]


def test_review_launch_validate_env_rejects_wrapper_only_id(tmp_path, monkeypatch, capsys):
    from mms_review_launch import handle_review_launch_command

    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "runs" / "p50"
    gate_path = run_dir / "review-dispatch-gate.json"
    expected_output = repo_root / ".ai" / "reviews" / "codex" / "p50-review-20260506.md"
    repo_root.mkdir()
    run_dir.mkdir(parents=True)
    gate_path.write_text(json.dumps({"gate_status": "approved"}) + "\n", encoding="utf-8")

    env = {
        "MOEBIUS_RUN_ID": "p50",
        "MOEBIUS_RUN_DIR": str(run_dir),
        "MOEBIUS_REPO_ROOT": str(repo_root),
        "MOEBIUS_REVIEW_DISPATCH_ADAPTER_CONFIG": str(run_dir / "adapter.json"),
        "MOEBIUS_REVIEW_DISPATCH_GATE": str(gate_path),
        "MOEBIUS_REVIEW_DISPATCH_PLAN": str(run_dir / "plan.json"),
        "MOEBIUS_REVIEWER_ID": "codex",
        "MOEBIUS_REVIEW_EXPECTED_OUTPUT": str(expected_output),
        "MULTI_REVIEW_REVIEWER": "codex",
        "MOEBIUS_REVIEW_PACK": str(repo_root / ".ai" / "plan" / "review-packs" / "p50.json"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert handle_review_launch_command(["--validate-env"], command_name="mms") == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert any("wrapper/tool id" in item for item in payload["errors"])


def test_mms_core_routes_review_launch_help():
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "mms"), "review-launch", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "review-launch" in completed.stdout
    assert "multi-review" in completed.stdout
    assert "reviewer" in completed.stdout
