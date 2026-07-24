from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import mms_pi_executor_parent


def _result(tmp_path=None) -> dict:
    patch_path = "/tmp/a.patch"
    patch_hash = "a" * 64
    patch_bytes = 42
    if tmp_path is not None:
        content = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
        path = tmp_path / "a.patch"
        path.write_text(content, encoding="utf-8")
        patch_path = str(path)
        patch_hash = hashlib.sha256(content.encode()).hexdigest()
        patch_bytes = len(content.encode())
    return {
        "schema": "mms.pi_executor.result.v1",
        "run_id": "pi-exec-test",
        "task_id": "task-test",
        "status": "partial",
        "summary": {"candidates": 3, "admissible": 1, "rejected": 1, "failed": 1},
        "plan": {"pack": {"base_commit": "abc", "writable_files": ["app.py"], "read_only_files": [], "forbidden_files": [], "validation_commands": ["pytest"]}},
        "results": [
            {
                "candidate_id": "executor-01",
                "model": "model-a",
                "status": "success",
                "admissible": True,
                "changed_files": ["app.py"],
                "scope_violations": [],
                "validation_mutated_worktree": False,
                "rejection_reasons": [],
                "patch": {"path": patch_path, "sha256": patch_hash, "bytes": patch_bytes},
                "validation": [{"status": "passed"}],
            },
            {"candidate_id": "executor-02", "model": "model-b", "status": "rejected", "admissible": False},
            {"candidate_id": "executor-03", "model": "model-c", "status": "failed", "admissible": False},
        ],
    }


def test_parent_packet_separates_admissible_rejected_and_failed(tmp_path) -> None:
    raw = _result(tmp_path)
    packet = mms_pi_executor_parent.build_parent_packet(raw, source="live")

    assert packet["status"] == "ready_for_intake"
    assert packet["health"] == {"planned": 3, "returned": 3, "admissible": 1, "rejected": 1, "failed": 1}
    assert [row["candidate_id"] for row in packet["admissible_candidates"]] == ["executor-01"]
    assert packet["patch_index"][0]["sha256"] == raw["results"][0]["patch"]["sha256"]
    assert packet["host_intake_contract"]["auto_apply"] is False


def test_parent_packet_does_not_mutate_raw_result(tmp_path) -> None:
    raw = _result(tmp_path)
    before = copy.deepcopy(raw)
    mms_pi_executor_parent.build_parent_packet(raw, source="live")
    assert raw == before


def test_parent_packet_rejects_unknown_schema() -> None:
    with pytest.raises(mms_pi_executor_parent.ExecutorParentError, match="unsupported"):
        mms_pi_executor_parent.build_parent_packet({"schema": "other"})


def test_saved_result_never_claims_ready_without_host_revalidation(tmp_path) -> None:
    patch = tmp_path / "candidate.patch"
    content = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    patch.write_text(content, encoding="utf-8")
    raw = _result()
    raw["plan"]["pack"].update({"writable_files": ["app.py"], "read_only_files": [], "forbidden_files": [], "validation_commands": []})
    raw["results"] = [
        {
            "candidate_id": "executor-01",
            "model": "model-a",
            "status": "success",
            "admissible": True,
            "changed_files": ["app.py"],
            "scope_violations": [],
            "validation": [],
            "validation_mutated_worktree": False,
            "rejection_reasons": [],
            "patch": {"path": str(patch), "sha256": __import__("hashlib").sha256(content.encode()).hexdigest(), "bytes": len(content.encode())},
        }
    ]

    packet = mms_pi_executor_parent.build_parent_packet(raw, source="saved")

    assert packet["status"] == "saved_result_requires_host_revalidation"
    assert packet["source_trust"] == "saved"
    assert packet["host_intake_contract"]["saved_result_validation_is_advisory"] is True


def test_saved_result_cli_returns_success_for_advisory_packet(tmp_path) -> None:
    raw = _result(tmp_path)
    result_path = tmp_path / "raw-result.json"
    result_path.write_text(json.dumps(raw), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "pi_executor_parent.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--result", str(result_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout)["status"] == "saved_result_requires_host_revalidation"


def test_forged_saved_result_is_rejected(tmp_path) -> None:
    raw = _result()
    raw["plan"]["pack"].update({"writable_files": ["app.py"], "read_only_files": [], "forbidden_files": [], "validation_commands": ["pytest"]})
    raw["results"][0]["patch"] = {"path": str(tmp_path / "missing.patch"), "sha256": "a" * 64, "bytes": 42}

    packet = mms_pi_executor_parent.build_parent_packet(raw, source="saved")

    assert packet["status"] == "no_admissible_candidate"
    assert packet["rejected_candidates"][0]["terminal_reason"] == "parent_intake_rejected"
    assert "patch_missing_or_unsafe" in packet["rejected_candidates"][0]["intake_rejection_reasons"]


def test_patch_under_symlinked_ancestor_is_rejected(tmp_path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(real, target_is_directory=True)
    content = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    patch = real / "candidate.patch"
    patch.write_text(content, encoding="utf-8")
    raw = _result()
    raw["plan"]["pack"].update({"writable_files": ["app.py"], "read_only_files": [], "forbidden_files": [], "validation_commands": []})
    raw["results"] = [
        {
            "candidate_id": "executor-01",
            "model": "model-a",
            "status": "success",
            "admissible": True,
            "changed_files": ["app.py"],
            "scope_violations": [],
            "validation": [],
            "validation_mutated_worktree": False,
            "rejection_reasons": [],
            "patch": {"path": str(link / "candidate.patch"), "sha256": hashlib.sha256(content.encode()).hexdigest(), "bytes": len(content.encode())},
        }
    ]

    packet = mms_pi_executor_parent.build_parent_packet(raw, source="saved")

    assert packet["status"] == "no_admissible_candidate"
    assert "patch_missing_or_unsafe" in packet["rejected_candidates"][0]["intake_rejection_reasons"]
