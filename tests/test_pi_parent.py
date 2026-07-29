from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import mms_pi_parent


ROOT = Path(__file__).resolve().parents[1]


def _result_fixture() -> dict:
    return {
        "schema": "mms.pi_committee.result.v1",
        "mission_id": "pi-parent-test",
        "status": "partial",
        "elapsed_ms": 1234,
        "summary": {"members": 3, "succeeded": 2, "failed": 1},
        "plan": {
            "mission_id": "pi-parent-test",
            "task": "Review the target",
            "route_source": "mms:latest-approved:test",
            "selection": {"profile": "frontier"},
            "members": [
                {
                    "member_id": "member-01",
                    "model": "gpt-test",
                    "family": "GPT",
                    "lens": "architecture",
                    "route_chain": [{"provider_id": "gpt-provider"}],
                },
                {
                    "member_id": "member-02",
                    "model": "qwen-test",
                    "family": "Qwen",
                    "lens": "failure-risk",
                    "route_chain": [{"provider_id": "qwen-provider"}],
                },
                {
                    "member_id": "member-03",
                    "model": "glm-test",
                    "family": "GLM",
                    "lens": "verification",
                    "route_chain": [{"provider_id": "glm-provider"}],
                },
                {
                    "member_id": "member-04",
                    "model": "kimi-test",
                    "family": "Kimi",
                    "lens": "counterexample",
                    "route_chain": [{"provider_id": "kimi-provider"}],
                },
            ],
        },
        "results": [
            {
                "member_id": "member-01",
                "model": "gpt-test",
                "family": "GPT",
                "lens": "architecture",
                "status": "success",
                "response": {
                    "verdict": "one issue",
                    "confidence": 0.8,
                    "findings": [
                        {
                            "claim": "state can drift",
                            "evidence": ["src/state.py:10"],
                            "severity": "high",
                            "extra": "preserve me",
                        }
                    ],
                    "risks": ["silent fallback"],
                    "recommendation": "fail closed",
                },
                "fallback_used": False,
                "attempts": [
                    {
                        "provider_id": "gpt-provider",
                        "status": "success",
                        "error": "",
                        "cache_transport_evidence": {
                            "protocol": "openai_responses",
                            "request_path": "/v1/responses",
                            "fallback_used": False,
                        },
                    }
                ],
            },
            {
                "member_id": "member-02",
                "model": "qwen-test",
                "family": "Qwen",
                "lens": "failure-risk",
                "status": "success",
                "response": {"raw_text": "malformed but useful opinion"},
                "fallback_used": True,
                "fallback_reason": "primary failed",
                "attempts": [],
            },
            {
                "member_id": "member-03",
                "model": "glm-test",
                "family": "GLM",
                "lens": "verification",
                "status": "failed",
                "error": "request_error",
                "attempts": [{"provider_id": "glm-provider", "status": "request_error", "error": "upstream"}],
            },
        ],
    }


def test_build_parent_packet_is_lossless_and_synthesis_ready() -> None:
    packet = mms_pi_parent.build_parent_packet(_result_fixture())

    assert packet["schema"] == "mms.pi_committee.parent_packet.v1"
    assert packet["status"] == "partial"
    assert packet["ready_for_synthesis"] is True
    assert packet["committee_health"] == {
        "planned_members": 4,
        "returned_members": 3,
        "succeeded": 2,
        "failed_or_missing": 2,
        "structured_responses": 1,
        "raw_responses": 1,
        "fallback_members": 1,
        "status_counts": {"failed": 1, "missing_result": 1, "success": 2},
        "family_counts": {"GLM": 1, "GPT": 1, "Qwen": 1},
    }
    assert packet["opinions"][0]["response"]["findings"][0]["extra"] == "preserve me"
    assert packet["opinions"][1]["response"] == {"raw_text": "malformed but useful opinion"}
    assert packet["evidence_index"][0]["evidence_id"] == "member-01-finding-01"
    assert {item["status"] for item in packet["failures"]} == {"failed", "missing_result"}
    assert packet["synthesis_contract"]["owner"] == "current_parent"
    assert packet["synthesis_contract"]["semantic_grouping"] == "parent_reasoning_required"


def test_dry_run_packet_is_not_ready_for_synthesis() -> None:
    result = _result_fixture()
    result["status"] = "dry_run"
    result["results"] = []

    packet = mms_pi_parent.build_parent_packet(result)

    assert packet["ready_for_synthesis"] is False
    assert packet["committee_health"]["planned_members"] == 4
    assert packet["committee_health"]["failed_or_missing"] == 0
    assert packet["committee_health"]["status_counts"] == {}
    assert [item["model"] for item in packet["committee_plan"]["members"]] == [
        "gpt-test",
        "qwen-test",
        "glm-test",
        "kimi-test",
    ]


def test_invalid_result_schema_fails_closed() -> None:
    with pytest.raises(mms_pi_parent.ParentPacketError, match="expected mms.pi_committee.result.v1"):
        mms_pi_parent.build_parent_packet({"schema": "wrong"})


def test_invalid_result_shapes_fail_closed() -> None:
    result = _result_fixture()
    result["results"] = {"member-01": {}}

    with pytest.raises(mms_pi_parent.ParentPacketError, match="results must be an array"):
        mms_pi_parent.build_parent_packet(result)


def test_run_parent_committee_delegates_to_existing_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_run_committee(**kwargs):
        captured.update(kwargs)
        result = _result_fixture()
        result["status"] = "success"
        result["plan"]["members"] = result["plan"]["members"][:1]
        result["results"] = result["results"][:1]
        return result

    monkeypatch.setattr("mms_pi_committee.run_committee", fake_run_committee)

    packet = mms_pi_parent.run_parent_committee(
        config_root="/explicit/root",
        task="Inspect",
        cwd="/target",
        dry_run=True,
    )

    assert captured["config_root"] == "/explicit/root"
    assert captured["task"] == "Inspect"
    assert captured["dry_run"] is True
    assert packet["opinions"][0]["member_id"] == "member-01"


def test_parent_cli_converts_saved_result_without_config_or_provider_call(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps(_result_fixture()), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pi_committee_parent.py"),
            "--result",
            str(result_path),
            "--compact",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    packet = json.loads(completed.stdout)
    assert packet["schema"] == "mms.pi_committee.parent_packet.v1"
    assert packet["mission"]["mission_id"] == "pi-parent-test"


def test_parent_cli_requires_explicit_config_for_task() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pi_committee_parent.py"), "--task", "Inspect"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--config-root is required" in completed.stderr


def test_bundled_skill_is_explicit_and_runner_locates_parent_cli() -> None:
    skill = ROOT / "assets" / "session-assets" / "skills" / "pi-committee"
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    metadata = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "$pi-committee" in skill_text
    assert "current Codex or Claude" in skill_text
    assert "Do not assume the MMS launcher auto-injected it" in skill_text
    assert "allow_implicit_invocation: false" in metadata
    completed = subprocess.run(
        [sys.executable, str(skill / "scripts" / "run_pi_committee.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--result" in completed.stdout
    assert "--config-root" in completed.stdout
