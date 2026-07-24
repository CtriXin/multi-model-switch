from __future__ import annotations

import json
from pathlib import Path

import pytest

import mms_pi_committee
import mms_pi_court


def _candidate(model: str, family: str) -> mms_pi_committee.ModelCandidate:
    route = mms_pi_committee.RouteBinding(
        model=model,
        wire_model=model,
        provider_id=f"provider-{model}",
        protocol="anthropic_messages",
        base_url="https://example.test",
        request_url="https://example.test/v1/messages",
        request_path="/v1/messages",
        api_key=f"secret-{model}",
    )
    return mms_pi_committee.ModelCandidate(
        model=model,
        family=family,
        capabilities={"text": True},
        context_window_tokens=100_000,
        favorite=False,
        tier="frontier",
        route_chain=(route,),
    )


def _candidates() -> list[mms_pi_committee.ModelCandidate]:
    return [
        _candidate("MiniMax-M3", "MiniMax"),
        _candidate("gpt-5.5", "GPT"),
        _candidate("k3", "Kimi"),
        _candidate("gemini-3-flash-agent(high)", "Gemini"),
        _candidate("qwen3.7-max", "Qwen"),
        _candidate("deepseek-v4-flash", "DeepSeek"),
        _candidate("glm-5.2", "GLM"),
        _candidate("kimi-for-coding", "Kimi"),
    ]


def _agent_spec(tmp_path: Path) -> Path:
    root = tmp_path / "agent-spec"
    roles = sorted(
        {
            seat.role_id
            for profile in mms_pi_court.BUILTIN_PROFILES.values()
            for seat in profile.seats
            if seat.role_id
        }
    )
    (root / "roles").mkdir(parents=True)
    (root / "index.json").write_text(
        json.dumps({"roles": [{"id": role_id, "kind": "role", "aliases": []} for role_id in roles]}),
        encoding="utf-8",
    )
    for role_id in roles:
        (root / "roles" / f"{role_id}.min.md").write_text(f"# {role_id}\n\nGATE\n- inspect evidence\n", encoding="utf-8")
    return root


def _mock_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mms_pi_committee,
        "load_candidates",
        lambda *_args, **_kwargs: (
            {"manifest": {"bundle_revision": "bundle-test"}, "component_revisions": {"router": "r1"}},
            _candidates(),
            {},
        ),
    )


def test_builtin_profiles_preserve_required_cross_functional_domains() -> None:
    profile = mms_pi_court.BUILTIN_PROFILES["cross-functional"]

    assert profile.required_domains == ("design", "product", "development", "testing")
    assert len(profile.seats) == 8
    assert {seat.role_id for seat in profile.seats} >= {"designer-soul", "critic", "architect", "qa"}


def test_hybrid_plan_loads_canonical_min_cards_and_dynamic_models(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_catalog(monkeypatch)

    plan, members = mms_pi_court.plan_court(
        config_root=tmp_path / "config",
        task="Review from four domains",
        profile="hybrid",
        agent_spec_root=_agent_spec(tmp_path),
    )

    assert plan["schema"] == "mms.pi_court.plan.v1"
    assert plan["court"]["required_domains"] == ["design", "product", "development", "testing"]
    assert len(members) == 6
    assert len({member.candidate.model for member in members}) == 6
    assert members[0].role_card.startswith("# designer-soul")
    assert members[0].public()["role_card_source"] == "agent-spec:roles/designer-soul.min.md"
    assert len(members[0].public()["role_card_sha256"]) == 64
    assert members[-1].role_id == ""
    assert members[-1].role_card == ""


def test_same_model_can_fill_two_explicit_seats_and_is_marked_correlated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_catalog(monkeypatch)

    plan, members = mms_pi_court.plan_court(
        config_root=tmp_path / "config",
        task="Use K3 for design and development",
        profile="hybrid",
        agent_spec_root=_agent_spec(tmp_path),
        seat_model_overrides={
            "design-direction": "k3",
            "development-architecture": "k3",
        },
        max_seats_per_model=2,
    )

    assert [member.member_id for member in members if member.candidate.model == "k3"] == [
        "design-direction",
        "development-architecture",
    ]
    assert plan["selection"]["same_model_multi_seat"] == {
        "k3": ["design-direction", "development-architecture"]
    }


def test_role_profile_requires_explicit_agent_spec_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_catalog(monkeypatch)

    with pytest.raises(mms_pi_court.CourtError, match="agent-spec-root is required"):
        mms_pi_court.plan_court(
            config_root=tmp_path / "config",
            task="Fail closed",
            profile="hybrid",
        )


def test_general_profile_needs_no_agent_spec_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_catalog(monkeypatch)

    plan, members = mms_pi_court.plan_court(
        config_root=tmp_path / "config",
        task="Legacy comparison",
        profile="general",
    )

    assert plan["court"]["role_source"] == "none"
    assert all(not member.role_card for member in members)


def test_custom_profile_validates_required_domain_and_role_source(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema": "mms.pi_court.profile.v1",
                "profile_id": "copy-test",
                "required_domains": ["copy", "testing"],
                "max_seats_per_model": 2,
                "seats": [
                    {"seat_id": "copy-seat", "domain": "copy", "lens": "copy", "role_id": "copywriter"},
                    {"seat_id": "test-seat", "domain": "testing", "lens": "test", "role_id": "qa"},
                ],
            }
        ),
        encoding="utf-8",
    )

    profile = mms_pi_court.load_profile(profile_file=profile_path)

    assert profile.profile_id == "copy-test"
    assert profile.required_domains == ("copy", "testing")


def test_model_capacity_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_catalog(monkeypatch)

    with pytest.raises(mms_pi_court.CourtError, match="capacity"):
        mms_pi_court.plan_court(
            config_root=tmp_path / "config",
            task="Too many seats",
            profile="hybrid",
            agent_spec_root=_agent_spec(tmp_path),
            explicit_models=["k3"],
            max_seats_per_model=2,
        )


def test_explicit_zero_model_capacity_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _mock_catalog(monkeypatch)

    with pytest.raises(mms_pi_court.CourtError, match="at least 1"):
        mms_pi_court.plan_court(
            config_root=tmp_path / "config",
            task="Zero is not a default sentinel",
            profile="general",
            max_seats_per_model=0,
        )


def test_custom_profile_rejects_duplicate_required_domains(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema": "mms.pi_court.profile.v1",
                "profile_id": "duplicate-domain",
                "required_domains": ["testing", "testing"],
                "seats": [
                    {"seat_id": "test-seat", "domain": "testing", "lens": "test"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(mms_pi_court.CourtError, match="must be unique"):
        mms_pi_court.load_profile(profile_file=profile_path)


def test_run_court_delegates_to_preplanned_committee(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_catalog(monkeypatch)
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"schema": "mms.pi_committee.result.v1", "status": "dry_run", "plan": kwargs["plan"], "results": []}

    monkeypatch.setattr(mms_pi_committee, "run_preplanned_committee", fake_run)
    result = mms_pi_court.run_court(
        config_root=tmp_path / "config",
        task="Delegate",
        cwd=tmp_path,
        profile="general",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert captured["plan"]["schema"] == "mms.pi_court.plan.v1"
    assert [member.member_id for member in captured["members"]][:2] == [
        "general-architecture",
        "general-failure-risk",
    ]
