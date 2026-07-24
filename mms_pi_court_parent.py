"""Parent packet adapter for role-aware Pi court results."""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any, Mapping, Sequence

import mms_pi_court
import mms_pi_parent


PARENT_PACKET_SCHEMA = "mms.pi_court.parent_packet.v1"


class CourtParentError(mms_pi_parent.ParentPacketError):
    """Raised when a Pi court result cannot become a safe parent packet."""


def build_parent_packet(result: Mapping[str, Any]) -> dict[str, Any]:
    plan = result.get("plan") if isinstance(result, Mapping) else None
    if not isinstance(plan, Mapping) or plan.get("schema") != mms_pi_court.PLAN_SCHEMA:
        raise CourtParentError(f"expected result plan {mms_pi_court.PLAN_SCHEMA}")
    packet = mms_pi_parent.build_parent_packet(result)
    court = plan.get("court") if isinstance(plan.get("court"), Mapping) else {}
    required_domains = _string_list(court.get("required_domains"))
    planned_members = [row for row in plan.get("members") or [] if isinstance(row, Mapping)]
    successful_opinions = [row for row in packet.get("opinions") or [] if row.get("status") == "success"]
    role_coverage = _role_coverage(
        planned_members,
        successful_opinions,
        required_domains=required_domains,
    )
    member_coverage_met = bool(packet.get("synthesis_readiness", {}).get("coverage_met"))
    domain_coverage_met = not role_coverage["missing_required_domains"]
    ready = bool(packet.get("status") != "dry_run" and member_coverage_met and domain_coverage_met)
    if packet.get("status") == "dry_run":
        reason = "dry_run"
    elif not member_coverage_met:
        reason = "insufficient_member_coverage"
    elif not domain_coverage_met:
        reason = "insufficient_domain_coverage"
    else:
        reason = "sufficient_member_and_domain_coverage"
    packet["schema"] = PARENT_PACKET_SCHEMA
    packet["ready_for_synthesis"] = ready
    packet["court"] = copy.deepcopy(dict(court))
    packet["role_coverage"] = role_coverage
    packet["independence"] = _independence(planned_members, successful_opinions)
    packet["synthesis_readiness"].update(
        {
            "reason": reason,
            "member_coverage_met": member_coverage_met,
            "domain_coverage_met": domain_coverage_met,
            "required_domains": required_domains,
            "missing_required_domains": role_coverage["missing_required_domains"],
        }
    )
    packet["committee_health"].update(
        {
            "required_domains": required_domains,
            "successful_domains": role_coverage["successful_domains"],
            "missing_required_domains": role_coverage["missing_required_domains"],
            "domain_coverage_met": domain_coverage_met,
        }
    )
    packet["synthesis_contract"] = _court_synthesis_contract()
    return packet


def run_parent_court(**kwargs: Any) -> dict[str, Any]:
    return build_parent_packet(mms_pi_court.run_court(**kwargs))


def _role_coverage(
    planned: Sequence[Mapping[str, Any]],
    successful: Sequence[Mapping[str, Any]],
    *,
    required_domains: Sequence[str],
) -> dict[str, Any]:
    planned_by_domain: dict[str, list[str]] = {}
    success_by_domain: dict[str, list[str]] = {}
    roles_by_domain: dict[str, set[str]] = {}
    for row in planned:
        domain = str(row.get("domain") or "independent").strip() or "independent"
        planned_by_domain.setdefault(domain, []).append(str(row.get("member_id") or "").strip())
        role_id = str(row.get("role_id") or "").strip()
        if role_id:
            roles_by_domain.setdefault(domain, set()).add(role_id)
    for row in successful:
        domain = str(row.get("domain") or "independent").strip() or "independent"
        success_by_domain.setdefault(domain, []).append(str(row.get("member_id") or "").strip())
    successful_domains = sorted(domain for domain, seats in success_by_domain.items() if seats)
    missing = sorted(set(required_domains) - set(successful_domains))
    return {
        "required_domains": list(required_domains),
        "successful_domains": successful_domains,
        "missing_required_domains": missing,
        "domains": {
            domain: {
                "planned_seats": seats,
                "successful_seats": success_by_domain.get(domain, []),
                "roles": sorted(roles_by_domain.get(domain, set())),
                "covered": bool(success_by_domain.get(domain)),
                "required": domain in set(required_domains),
            }
            for domain, seats in sorted(planned_by_domain.items())
        },
    }


def _independence(
    planned: Sequence[Mapping[str, Any]],
    successful: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    model_seats: dict[str, list[str]] = {}
    family_seats: dict[str, list[str]] = {}
    role_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    for row in planned:
        seat_id = str(row.get("member_id") or "").strip()
        model_seats.setdefault(str(row.get("model") or "").strip(), []).append(seat_id)
        family_seats.setdefault(str(row.get("family") or "Other").strip(), []).append(seat_id)
    for row in successful:
        role_counts[str(row.get("role_id") or "unassigned").strip() or "unassigned"] += 1
        domain_counts[str(row.get("domain") or "independent").strip() or "independent"] += 1
    return {
        "same_model_multi_seat": {
            model: seats for model, seats in sorted(model_seats.items()) if model and len(seats) > 1
        },
        "same_family_multi_seat": {
            family: seats for family, seats in sorted(family_seats.items()) if family and len(seats) > 1
        },
        "successful_role_counts": dict(sorted(role_counts.items())),
        "successful_domain_counts": dict(sorted(domain_counts.items())),
        "consensus_classes": {
            "model_corroboration": "same role or domain supported by different model families",
            "perspective_corroboration": "different roles or domains supported by the same model; correlated model prior remains",
            "cross_role_model_corroboration": "different roles or domains and different model families; strongest court support",
        },
    }


def _court_synthesis_contract() -> dict[str, Any]:
    contract = copy.deepcopy(mms_pi_parent.synthesis_contract())
    contract["required_sections"] = [
        "committee_health",
        "domain_coverage",
        "cross_role_consensus",
        "dissent",
        "unique_findings",
        "same_model_correlation",
        "risks",
        "recommendation",
        "confidence",
    ]
    contract["rules"].extend(
        [
            "Do not synthesize when any required court domain has zero successful seats.",
            "Classify support by both role/domain diversity and model-family diversity.",
            "Do not present two seats using the same model as independent model corroboration.",
            "Keep free-seat findings separate from required-domain coverage.",
            "Cite seat id, domain, role id, model, and evidence id for cross-role claims.",
        ]
    )
    contract["output_shape"].update(
        {
            "domain_coverage": {"design": "covered|missing"},
            "cross_role_consensus": [
                {
                    "claim": "...",
                    "support_class": "model_corroboration|perspective_corroboration|cross_role_model_corroboration",
                    "seat_ids": [],
                    "evidence_ids": [],
                }
            ],
            "same_model_correlation": [{"model": "...", "seat_ids": []}],
        }
    )
    return contract


def _string_list(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else []
    return [str(item).strip() for item in rows if str(item).strip()]


__all__ = [
    "CourtParentError",
    "PARENT_PACKET_SCHEMA",
    "build_parent_packet",
    "run_parent_court",
]
