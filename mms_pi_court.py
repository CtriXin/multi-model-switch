"""Role-aware Pi court built on the isolated Pi committee worker runtime."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import mms_pi_committee


PROFILE_SCHEMA = "mms.pi_court.profile.v1"
PLAN_SCHEMA = "mms.pi_court.plan.v1"
DEFAULT_PROFILE = "hybrid"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class CourtError(mms_pi_committee.CommitteeError):
    """Raised when a Pi court profile or seat assignment is unsafe."""


@dataclass(frozen=True)
class SeatTemplate:
    seat_id: str
    domain: str
    lens: str
    role_id: str = ""

    def public(self, *, required_domains: Sequence[str]) -> dict[str, Any]:
        return {
            "seat_id": self.seat_id,
            "domain": self.domain,
            "lens": self.lens,
            "role_id": self.role_id,
            "required_domain": self.domain in set(required_domains),
        }


@dataclass(frozen=True)
class CourtProfile:
    profile_id: str
    seats: tuple[SeatTemplate, ...]
    required_domains: tuple[str, ...]
    max_seats_per_model: int = 2

    def public(self) -> dict[str, Any]:
        return {
            "schema": PROFILE_SCHEMA,
            "profile_id": self.profile_id,
            "required_domains": list(self.required_domains),
            "max_seats_per_model": self.max_seats_per_model,
            "seats": [seat.public(required_domains=self.required_domains) for seat in self.seats],
        }


BUILTIN_PROFILES = {
    "general": CourtProfile(
        profile_id="general",
        seats=tuple(
            SeatTemplate(f"general-{lens}", "independent", lens)
            for lens in mms_pi_committee.DEFAULT_LENSES
        ),
        required_domains=(),
        max_seats_per_model=1,
    ),
    "cross-functional": CourtProfile(
        profile_id="cross-functional",
        seats=(
            SeatTemplate("design-direction", "design", "design-direction", "designer-soul"),
            SeatTemplate("design-delivery", "design", "implementation-fidelity", "frontend-architect"),
            SeatTemplate("product-critique", "product", "product-assumptions", "critic"),
            SeatTemplate("product-scope", "product", "scope-and-complexity", "subtractor"),
            SeatTemplate("development-architecture", "development", "architecture", "architect"),
            SeatTemplate("development-failure", "development", "failure-risk", "challenger"),
            SeatTemplate("testing-contract", "testing", "contract-verification", "qa"),
            SeatTemplate("testing-execution", "testing", "execution-audit", "audit"),
        ),
        required_domains=("design", "product", "development", "testing"),
        max_seats_per_model=2,
    ),
    "hybrid": CourtProfile(
        profile_id="hybrid",
        seats=(
            SeatTemplate("design-direction", "design", "design-direction", "designer-soul"),
            SeatTemplate("product-critique", "product", "product-assumptions", "critic"),
            SeatTemplate("development-architecture", "development", "architecture", "architect"),
            SeatTemplate("testing-contract", "testing", "contract-verification", "qa"),
            SeatTemplate("cross-cutting-challenger", "cross-cutting", "failure-risk", "challenger"),
            SeatTemplate("independent-wildcard", "independent", "counterexample"),
        ),
        required_domains=("design", "product", "development", "testing"),
        max_seats_per_model=2,
    ),
}


def load_profile(*, profile: str = DEFAULT_PROFILE, profile_file: str | Path | None = None) -> CourtProfile:
    if profile_file:
        path = Path(profile_file).expanduser().resolve()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CourtError(f"cannot read Pi court profile: {path}: {exc}") from exc
        return _parse_profile(payload, source=str(path))
    profile_id = str(profile or "").strip().lower()
    try:
        return BUILTIN_PROFILES[profile_id]
    except KeyError as exc:
        raise CourtError(f"unknown Pi court profile: {profile_id}") from exc


def plan_court(
    *,
    config_root: str | Path,
    task: str,
    profile: str = DEFAULT_PROFILE,
    profile_file: str | Path | None = None,
    agent_spec_root: str | Path | None = None,
    explicit_models: Sequence[str] = (),
    frontier_families: Sequence[str] = mms_pi_committee.DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    required_capabilities: Sequence[str] = ("text",),
    seat_model_overrides: Mapping[str, str] | None = None,
    max_seats_per_model: int | None = None,
    mission_id: str | None = None,
    max_bundle_age_days: int = mms_pi_committee.DEFAULT_MAX_BUNDLE_AGE_DAYS,
) -> tuple[dict[str, Any], list[mms_pi_committee.MemberSpec]]:
    task_text = str(task or "").strip()
    if not task_text:
        raise CourtError("task must not be empty")
    court_profile = load_profile(profile=profile, profile_file=profile_file)
    effective_max = (
        court_profile.max_seats_per_model
        if max_seats_per_model is None
        else max_seats_per_model
    )
    if effective_max < 1:
        raise CourtError("max seats per model must be at least 1")
    bundle, candidates, excluded = mms_pi_committee.load_candidates(
        config_root,
        required_capabilities=required_capabilities,
        max_bundle_age_days=max_bundle_age_days,
    )
    pool = _candidate_pool(
        candidates,
        explicit_models=explicit_models,
        frontier_families=frontier_families,
        additional_models=additional_models,
    )
    overrides = {str(key).strip(): str(value).strip() for key, value in (seat_model_overrides or {}).items()}
    assignments = _assign_models(
        court_profile,
        candidates=candidates,
        pool=pool,
        overrides=overrides,
        max_seats_per_model=effective_max,
    )
    role_cards = _load_role_cards(court_profile, agent_spec_root=agent_spec_root)
    members = [
        _member_from_seat(
            seat,
            assignments[seat.seat_id],
            required_domains=court_profile.required_domains,
            role_card=role_cards.get(seat.role_id),
        )
        for seat in court_profile.seats
    ]
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), Mapping) else {}
    use_counts = Counter(member.candidate.model for member in members)
    plan = {
        "schema": PLAN_SCHEMA,
        "mission_id": mission_id or f"court-{uuid.uuid4().hex[:12]}",
        "task": task_text,
        "route_source": f"mms:latest-approved:{manifest.get('bundle_revision') or ''}",
        "component_revisions": dict(bundle.get("component_revisions") or {}),
        "bundle": mms_pi_committee.public_bundle_metadata(bundle),
        "selection": {
            "profile": court_profile.profile_id,
            "model_pool": [candidate.model for candidate in pool],
            "explicit_models": list(explicit_models),
            "target_families": list(frontier_families) if not explicit_models else [],
            "additional_models": list(additional_models),
            "eligible_models": len(candidates),
            "excluded_models": excluded,
            "seat_model_overrides": overrides,
            "max_seats_per_model": effective_max,
            "same_model_multi_seat": {
                model: [member.member_id for member in members if member.candidate.model == model]
                for model, count in sorted(use_counts.items())
                if count > 1
            },
        },
        "court": {
            **court_profile.public(),
            "profile_source": str(Path(profile_file).expanduser().resolve()) if profile_file else "builtin",
            "role_source": "agent-spec:roles/*.min.md" if role_cards else "none",
            "assignment_policy": "least-used model first; avoid same model within a domain; explicit seat override wins",
        },
        "members": [member.public() for member in members],
        "isolation": {
            "global_config_writes": False,
            "global_oauth_fallback": False,
            "opencode_dependency": False,
            "agent_soul_runtime_dependency": False,
            "worker_tools": mms_pi_committee.READ_ONLY_TOOLS,
        },
    }
    return plan, members


def run_court(
    *,
    config_root: str | Path,
    task: str,
    cwd: str | Path,
    profile: str = DEFAULT_PROFILE,
    profile_file: str | Path | None = None,
    agent_spec_root: str | Path | None = None,
    explicit_models: Sequence[str] = (),
    frontier_families: Sequence[str] = mms_pi_committee.DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    required_capabilities: Sequence[str] = ("text",),
    seat_model_overrides: Mapping[str, str] | None = None,
    max_seats_per_model: int | None = None,
    max_concurrency: int = mms_pi_committee.DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = mms_pi_committee.DEFAULT_TIMEOUT_SECONDS,
    kimi_attempt_timeout_seconds: int = mms_pi_committee.DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
    max_bundle_age_days: int = mms_pi_committee.DEFAULT_MAX_BUNDLE_AGE_DAYS,
    idle_timeout_seconds: int = mms_pi_committee.DEFAULT_IDLE_TIMEOUT_SECONDS,
    max_output_bytes: int = mms_pi_committee.DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = mms_pi_committee.DEFAULT_MAX_REPEATED_EVENTS,
    committee_timeout_seconds: int = mms_pi_committee.DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
    quorum_successes: int = mms_pi_committee.DEFAULT_QUORUM_SUCCESSES,
    quorum_grace_seconds: int = mms_pi_committee.DEFAULT_QUORUM_GRACE_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan, members = plan_court(
        config_root=config_root,
        task=task,
        profile=profile,
        profile_file=profile_file,
        agent_spec_root=agent_spec_root,
        explicit_models=explicit_models,
        frontier_families=frontier_families,
        additional_models=additional_models,
        required_capabilities=required_capabilities,
        seat_model_overrides=seat_model_overrides,
        max_seats_per_model=max_seats_per_model,
        max_bundle_age_days=max_bundle_age_days,
    )
    return mms_pi_committee.run_preplanned_committee(
        config_root=config_root,
        plan=plan,
        members=members,
        cwd=cwd,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
        kimi_attempt_timeout_seconds=kimi_attempt_timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        max_output_bytes=max_output_bytes,
        max_repeated_events=max_repeated_events,
        committee_timeout_seconds=committee_timeout_seconds,
        quorum_successes=quorum_successes,
        quorum_grace_seconds=quorum_grace_seconds,
        dry_run=dry_run,
    )


def _parse_profile(payload: Any, *, source: str) -> CourtProfile:
    if not isinstance(payload, Mapping) or payload.get("schema") != PROFILE_SCHEMA:
        raise CourtError(f"expected {PROFILE_SCHEMA} in {source}")
    profile_id = _safe_id(payload.get("profile_id"), field="profile_id")
    raw_seats = payload.get("seats")
    if not isinstance(raw_seats, list) or not raw_seats:
        raise CourtError(f"profile seats must be a non-empty array in {source}")
    seats = tuple(_parse_seat(row, source=source) for row in raw_seats)
    seat_ids = [seat.seat_id for seat in seats]
    if len(set(seat_ids)) != len(seat_ids):
        raise CourtError(f"profile seat ids must be unique in {source}")
    raw_domains = payload.get("required_domains") or []
    if not isinstance(raw_domains, list):
        raise CourtError(f"required_domains must be an array in {source}")
    required_domains = tuple(_safe_id(item, field="required_domain") for item in raw_domains)
    if len(set(required_domains)) != len(required_domains):
        raise CourtError(f"required domains must be unique in {source}")
    missing = sorted(set(required_domains) - {seat.domain for seat in seats})
    if missing:
        raise CourtError("required domains have no seats: " + ", ".join(missing))
    max_seats = _positive_int(payload.get("max_seats_per_model"), default=2)
    return CourtProfile(profile_id, seats, required_domains, max_seats)


def _parse_seat(payload: Any, *, source: str) -> SeatTemplate:
    if not isinstance(payload, Mapping):
        raise CourtError(f"profile seat must be an object in {source}")
    return SeatTemplate(
        seat_id=_safe_id(payload.get("seat_id"), field="seat_id"),
        domain=_safe_id(payload.get("domain"), field="domain"),
        lens=_safe_text(payload.get("lens"), field="lens"),
        role_id=_safe_id(payload.get("role_id"), field="role_id", allow_empty=True),
    )


def _candidate_pool(
    candidates: Sequence[mms_pi_committee.ModelCandidate],
    *,
    explicit_models: Sequence[str],
    frontier_families: Sequence[str],
    additional_models: Sequence[str],
) -> list[mms_pi_committee.ModelCandidate]:
    by_model = {candidate.model: candidate for candidate in candidates}
    if explicit_models:
        if additional_models:
            raise CourtError("--model cannot be combined with --add-model")
        requested = _dedupe(explicit_models)
        missing = [model for model in requested if model not in by_model]
        if missing:
            raise CourtError("requested models are unavailable: " + ", ".join(missing))
        return [by_model[model] for model in requested]
    members = mms_pi_committee.select_members(
        candidates,
        selection_profile="frontier",
        frontier_families=frontier_families,
        additional_models=additional_models,
        lenses=("court-pool",),
    )
    return [member.candidate for member in members]


def _assign_models(
    profile: CourtProfile,
    *,
    candidates: Sequence[mms_pi_committee.ModelCandidate],
    pool: Sequence[mms_pi_committee.ModelCandidate],
    overrides: Mapping[str, str],
    max_seats_per_model: int,
) -> dict[str, mms_pi_committee.ModelCandidate]:
    if not pool:
        raise CourtError("court model pool is empty")
    by_model = {candidate.model: candidate for candidate in candidates}
    seat_ids = {seat.seat_id for seat in profile.seats}
    unknown_seats = sorted(set(overrides) - seat_ids)
    if unknown_seats:
        raise CourtError("seat model overrides reference unknown seats: " + ", ".join(unknown_seats))
    unknown_models = sorted({model for model in overrides.values() if model not in by_model})
    if unknown_models:
        raise CourtError("seat model overrides reference unavailable models: " + ", ".join(unknown_models))
    assigned: dict[str, mms_pi_committee.ModelCandidate] = {}
    use_counts: Counter[str] = Counter()
    domain_models: dict[str, set[str]] = {}
    for seat in profile.seats:
        model = overrides.get(seat.seat_id)
        if not model:
            continue
        if use_counts[model] >= max_seats_per_model:
            raise CourtError(f"model {model} exceeds max seats per model ({max_seats_per_model})")
        assigned[seat.seat_id] = by_model[model]
        use_counts[model] += 1
        domain_models.setdefault(seat.domain, set()).add(model)
    for seat in profile.seats:
        if seat.seat_id in assigned:
            continue
        eligible = [candidate for candidate in pool if use_counts[candidate.model] < max_seats_per_model]
        if not eligible:
            raise CourtError("model pool capacity is smaller than the court seat count")
        candidate = min(
            eligible,
            key=lambda item: (
                item.model in domain_models.get(seat.domain, set()),
                use_counts[item.model],
                next(index for index, row in enumerate(pool) if row.model == item.model),
            ),
        )
        assigned[seat.seat_id] = candidate
        use_counts[candidate.model] += 1
        domain_models.setdefault(seat.domain, set()).add(candidate.model)
    return assigned


def _load_role_cards(
    profile: CourtProfile,
    *,
    agent_spec_root: str | Path | None,
) -> dict[str, tuple[str, str, str]]:
    role_ids = sorted({seat.role_id for seat in profile.seats if seat.role_id})
    if not role_ids:
        return {}
    if not agent_spec_root:
        raise CourtError("--agent-spec-root is required for a Pi court profile with Soul roles")
    root = Path(agent_spec_root).expanduser().resolve()
    try:
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CourtError(f"cannot read agent-spec index from {root}: {exc}") from exc
    rows = index.get("roles") if isinstance(index, Mapping) else None
    if not isinstance(rows, list):
        raise CourtError("agent-spec index roles must be an array")
    known = {str(row.get("id") or "").strip() for row in rows if isinstance(row, Mapping)}
    missing = [role_id for role_id in role_ids if role_id not in known]
    if missing:
        raise CourtError("unknown agent-spec roles: " + ", ".join(missing))
    cards: dict[str, tuple[str, str, str]] = {}
    for role_id in role_ids:
        path = root / "roles" / f"{role_id}.min.md"
        try:
            card = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise CourtError(f"missing agent-spec min role card: {path}") from exc
        digest = hashlib.sha256(card.encode("utf-8")).hexdigest()
        cards[role_id] = (card, f"agent-spec:roles/{role_id}.min.md", digest)
    return cards


def _member_from_seat(
    seat: SeatTemplate,
    candidate: mms_pi_committee.ModelCandidate,
    *,
    required_domains: Sequence[str],
    role_card: tuple[str, str, str] | None,
) -> mms_pi_committee.MemberSpec:
    card, source, digest = role_card or ("", "", "")
    return mms_pi_committee.MemberSpec(
        member_id=seat.seat_id,
        lens=seat.lens,
        candidate=candidate,
        domain=seat.domain,
        role_id=seat.role_id,
        role_card=card,
        role_card_source=source,
        role_card_sha256=digest,
        required_domain=seat.domain in set(required_domains),
    )


def _safe_id(value: Any, *, field: str, allow_empty: bool = False) -> str:
    text = str(value or "").strip().lower()
    if not text and allow_empty:
        return ""
    if not _SAFE_ID.fullmatch(text):
        raise CourtError(f"{field} must use lowercase letters, digits, and hyphens")
    return text


def _safe_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 200 or "\x00" in text:
        raise CourtError(f"{field} must be non-empty and at most 200 characters")
    return text


def _positive_int(value: Any, *, default: int) -> int:
    try:
        number = int(value if value is not None else default)
    except (TypeError, ValueError) as exc:
        raise CourtError("max_seats_per_model must be an integer") from exc
    if number < 1:
        raise CourtError("max_seats_per_model must be at least 1")
    return number


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


__all__ = [
    "BUILTIN_PROFILES",
    "CourtError",
    "CourtProfile",
    "DEFAULT_PROFILE",
    "PROFILE_SCHEMA",
    "PLAN_SCHEMA",
    "SeatTemplate",
    "load_profile",
    "plan_court",
    "run_court",
]
