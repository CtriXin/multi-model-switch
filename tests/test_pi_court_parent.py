from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import mms_pi_court_parent


ROOT = Path(__file__).resolve().parents[1]


def _result(*, successful_domains: tuple[str, ...], same_model: bool = False, status: str = "partial") -> dict:
    domains = ("design", "product", "development", "testing")
    members = []
    results = []
    for index, domain in enumerate(domains, start=1):
        member_id = f"{domain}-seat"
        model = "k3" if same_model and domain in {"design", "development"} else f"model-{domain}"
        member = {
            "member_id": member_id,
            "model": model,
            "family": "Kimi" if model == "k3" else f"Family-{domain}",
            "lens": domain,
            "domain": domain,
            "role_id": f"role-{domain}",
            "required_domain": True,
            "route_chain": [],
        }
        members.append(member)
        if domain in successful_domains:
            results.append(
                {
                    **member,
                    "status": "success",
                    "terminal_reason": "completed",
                    "response": {
                        "verdict": f"{domain} verdict",
                        "confidence": 0.8,
                        "findings": [{"claim": f"{domain} claim", "evidence": [f"{domain}.md"], "severity": "medium"}],
                        "risks": [],
                        "recommendation": "continue",
                    },
                    "attempts": [],
                }
            )
    return {
        "schema": "mms.pi_committee.result.v1",
        "mission_id": "court-test",
        "status": status,
        "plan": {
            "schema": "mms.pi_court.plan.v1",
            "mission_id": "court-test",
            "task": "Review",
            "route_source": "test",
            "selection": {},
            "court": {
                "schema": "mms.pi_court.profile.v1",
                "profile_id": "test",
                "required_domains": list(domains),
                "seats": [],
            },
            "members": members,
        },
        "results": results,
    }


def test_all_required_domains_and_member_floor_are_synthesis_ready() -> None:
    packet = mms_pi_court_parent.build_parent_packet(
        _result(successful_domains=("design", "product", "development", "testing"), status="success")
    )

    assert packet["schema"] == "mms.pi_court.parent_packet.v1"
    assert packet["ready_for_synthesis"] is True
    assert packet["synthesis_readiness"]["reason"] == "sufficient_member_and_domain_coverage"
    assert packet["role_coverage"]["missing_required_domains"] == []


def test_missing_required_domain_blocks_synthesis_even_when_member_floor_passes() -> None:
    packet = mms_pi_court_parent.build_parent_packet(
        _result(successful_domains=("design", "product", "development"))
    )

    assert packet["synthesis_readiness"]["member_coverage_met"] is True
    assert packet["ready_for_synthesis"] is False
    assert packet["synthesis_readiness"]["reason"] == "insufficient_domain_coverage"
    assert packet["role_coverage"]["missing_required_domains"] == ["testing"]


def test_same_model_multi_seat_is_reported_as_correlation() -> None:
    packet = mms_pi_court_parent.build_parent_packet(
        _result(successful_domains=("design", "product", "development", "testing"), same_model=True, status="success")
    )

    assert packet["independence"]["same_model_multi_seat"] == {
        "k3": ["design-seat", "development-seat"]
    }
    assert "cross_role_model_corroboration" in packet["independence"]["consensus_classes"]


def test_dry_run_is_never_synthesis_ready() -> None:
    result = _result(successful_domains=(), status="dry_run")
    result["results"] = []

    packet = mms_pi_court_parent.build_parent_packet(result)

    assert packet["ready_for_synthesis"] is False
    assert packet["synthesis_readiness"]["reason"] == "dry_run"


def test_parent_cli_converts_saved_court_result_without_dispatch(tmp_path: Path) -> None:
    result_path = tmp_path / "court-result.json"
    result_path.write_text(
        json.dumps(_result(successful_domains=("design", "product", "development", "testing"), status="success")),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pi_court_parent.py"),
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
    assert json.loads(completed.stdout)["schema"] == "mms.pi_court.parent_packet.v1"


def test_bundled_pi_court_skill_is_explicit_and_runner_locates_parent_cli() -> None:
    skill = ROOT / "assets" / "session-assets" / "skills" / "pi-court"
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    metadata = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "$pi-court" in skill_text
    assert "agent-soul runtime" in skill_text
    assert "allow_implicit_invocation: false" in metadata
    assert (skill / "references" / "profile-contract.md").is_file()

    env = dict(os.environ)
    env["MMS_PI_COURT_ROOT"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, str(skill / "scripts" / "run_pi_court.py"), "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--profile" in completed.stdout
    assert "--seat-model" in completed.stdout
