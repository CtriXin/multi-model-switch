"""Parent-facing adapter for the opt-in Pi committee runtime.

The adapter is deterministic: it preserves member responses, flattens evidence,
and defines a synthesis contract. Semantic consensus remains the responsibility
of the current Codex or Claude parent; this module never launches a synthesizer.
"""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import mms_pi_committee


RESULT_SCHEMA = "mms.pi_committee.result.v1"
PARENT_PACKET_SCHEMA = "mms.pi_committee.parent_packet.v1"


class ParentPacketError(ValueError):
    """Raised when a committee result cannot become a safe parent packet."""


def build_parent_packet(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a lossless, synthesis-ready packet from a committee result."""
    if not isinstance(result, Mapping) or result.get("schema") != RESULT_SCHEMA:
        raise ParentPacketError(f"expected {RESULT_SCHEMA}")
    if not isinstance(result.get("plan"), Mapping):
        raise ParentPacketError("committee result plan must be an object")
    plan = _mapping(result.get("plan"))
    result_status = str(result.get("status") or "unknown").strip().lower()
    raw_planned_rows = plan.get("members")
    if not isinstance(raw_planned_rows, list) or not all(isinstance(item, Mapping) for item in raw_planned_rows):
        raise ParentPacketError("committee result plan.members must be an array of objects")
    planned_rows = list(raw_planned_rows)
    planned_by_id = {
        str(item.get("member_id") or "").strip(): item
        for item in planned_rows
        if str(item.get("member_id") or "").strip()
    }
    raw_result_rows = result.get("results")
    if not isinstance(raw_result_rows, list) or not all(isinstance(item, Mapping) for item in raw_result_rows):
        raise ParentPacketError("committee result results must be an array of objects")
    result_rows = list(raw_result_rows)

    opinions: list[dict[str, Any]] = []
    evidence_index: list[dict[str, Any]] = []
    route_health: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    returned_ids: set[str] = set()
    structured_count = 0
    raw_count = 0
    fallback_count = 0

    for row_index, row in enumerate(result_rows, start=1):
        member_id = str(row.get("member_id") or f"unidentified-{row_index:02d}").strip()
        returned_ids.add(member_id)
        planned = _mapping(planned_by_id.get(member_id))
        status = str(row.get("status") or "unknown").strip().lower()
        model = str(row.get("model") or planned.get("model") or "").strip()
        family = str(row.get("family") or planned.get("family") or "Other").strip() or "Other"
        lens = str(row.get("lens") or planned.get("lens") or "").strip()
        response = _response_object(row.get("response"))
        response_format = _response_format(response)
        if response_format == "structured_json":
            structured_count += 1
        elif response_format == "raw_text":
            raw_count += 1
        if bool(row.get("fallback_used")):
            fallback_count += 1

        normalized_findings = _normalize_findings(
            response.get("findings"),
            member_id=member_id,
            model=model,
            evidence_index=evidence_index,
        )
        opinion = {
            "member_id": member_id,
            "model": model,
            "family": family,
            "lens": lens,
            "status": status,
            "response_format": response_format,
            "verdict": str(response.get("verdict") or "").strip(),
            "confidence": _confidence(response.get("confidence")),
            "findings": normalized_findings,
            "risks": _string_list(response.get("risks")),
            "recommendation": str(response.get("recommendation") or "").strip(),
            "response": copy.deepcopy(response),
            "fallback_used": bool(row.get("fallback_used")),
            "fallback_reason": str(row.get("fallback_reason") or "").strip(),
        }
        if row.get("error"):
            opinion["error"] = str(row.get("error"))
        opinions.append(opinion)
        status_counts[status] += 1
        family_counts[family] += 1

        health = _route_health(row, planned=planned, member_id=member_id, model=model, status=status)
        route_health.append(health)
        if status != "success":
            failures.append(
                {
                    "member_id": member_id,
                    "model": model,
                    "status": status,
                    "error": str(row.get("error") or "").strip(),
                    "attempts": copy.deepcopy(health["attempts"]),
                }
            )

    if result_status != "dry_run":
        for member_id, planned in planned_by_id.items():
            if member_id in returned_ids:
                continue
            model = str(planned.get("model") or "").strip()
            failures.append(
                {
                    "member_id": member_id,
                    "model": model,
                    "status": "missing_result",
                    "error": "planned member returned no result",
                    "attempts": [],
                }
            )
            status_counts["missing_result"] += 1
    succeeded = status_counts.get("success", 0)
    ready_for_synthesis = result_status != "dry_run" and succeeded > 0
    mission_id = str(result.get("mission_id") or plan.get("mission_id") or "").strip()
    return {
        "schema": PARENT_PACKET_SCHEMA,
        "status": result_status,
        "ready_for_synthesis": ready_for_synthesis,
        "mission": {
            "mission_id": mission_id,
            "task": str(plan.get("task") or "").strip(),
            "route_source": str(plan.get("route_source") or "").strip(),
            "elapsed_ms": _non_negative_int(result.get("elapsed_ms")),
            "selection": copy.deepcopy(_mapping(plan.get("selection"))),
        },
        "committee_plan": copy.deepcopy(plan),
        "committee_health": {
            "planned_members": len(planned_rows),
            "returned_members": len(result_rows),
            "succeeded": succeeded,
            "failed_or_missing": len(failures),
            "structured_responses": structured_count,
            "raw_responses": raw_count,
            "fallback_members": fallback_count,
            "status_counts": dict(sorted(status_counts.items())),
            "family_counts": dict(sorted(family_counts.items())),
        },
        "opinions": opinions,
        "evidence_index": evidence_index,
        "route_health": route_health,
        "failures": failures,
        "synthesis_contract": _synthesis_contract(),
        "source_result_schema": RESULT_SCHEMA,
    }


def run_parent_committee(
    *,
    config_root: str | Path,
    task: str,
    cwd: str | Path,
    count: int | None = None,
    min_families: int = mms_pi_committee.DEFAULT_MIN_FAMILIES,
    explicit_models: Sequence[str] = (),
    selection_profile: str = mms_pi_committee.DEFAULT_SELECTION_PROFILE,
    frontier_families: Sequence[str] = mms_pi_committee.DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    required_capabilities: Sequence[str] = ("text",),
    lenses: Sequence[str] = mms_pi_committee.DEFAULT_LENSES,
    max_concurrency: int = mms_pi_committee.DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = mms_pi_committee.DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the existing committee runtime and return a parent packet."""
    result = mms_pi_committee.run_committee(
        config_root=config_root,
        task=task,
        cwd=cwd,
        count=count,
        min_families=min_families,
        explicit_models=explicit_models,
        selection_profile=selection_profile,
        frontier_families=frontier_families,
        additional_models=additional_models,
        required_capabilities=required_capabilities,
        lenses=lenses,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )
    return build_parent_packet(result)


def _normalize_findings(
    raw: Any,
    *,
    member_id: str,
    model: str,
    evidence_index: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rows = raw if isinstance(raw, list) else []
    for finding_index, item in enumerate(rows, start=1):
        row = item if isinstance(item, Mapping) else {"claim": str(item)}
        claim = str(row.get("claim") or row.get("finding") or "").strip()
        evidence = _string_list(row.get("evidence"))
        severity = str(row.get("severity") or "").strip().lower()
        evidence_id = f"{member_id}-finding-{finding_index:02d}"
        normalized = {
            "evidence_id": evidence_id,
            "claim": claim,
            "evidence": evidence,
            "severity": severity,
            "original": copy.deepcopy(dict(row)),
        }
        findings.append(normalized)
        evidence_index.append(
            {
                "evidence_id": evidence_id,
                "member_id": member_id,
                "model": model,
                "claim": claim,
                "evidence": evidence,
                "severity": severity,
            }
        )
    return findings


def _route_health(
    row: Mapping[str, Any],
    *,
    planned: Mapping[str, Any],
    member_id: str,
    model: str,
    status: str,
) -> dict[str, Any]:
    attempts = []
    for attempt in row.get("attempts") or []:
        if not isinstance(attempt, Mapping):
            continue
        evidence = _mapping(attempt.get("cache_transport_evidence"))
        attempts.append(
            {
                "provider_id": str(attempt.get("provider_id") or evidence.get("provider_id") or "").strip(),
                "status": str(attempt.get("status") or "unknown").strip().lower(),
                "error": str(attempt.get("error") or "").strip(),
                "protocol": str(evidence.get("protocol") or "").strip(),
                "request_path": str(evidence.get("request_path") or "").strip(),
                "fallback_used": bool(evidence.get("fallback_used")),
            }
        )
    if not attempts and isinstance(row.get("cache_transport_evidence"), Mapping):
        evidence = _mapping(row.get("cache_transport_evidence"))
        attempts.append(
            {
                "provider_id": str(row.get("provider_id") or evidence.get("provider_id") or "").strip(),
                "status": status,
                "error": str(row.get("error") or "").strip(),
                "protocol": str(evidence.get("protocol") or row.get("protocol") or "").strip(),
                "request_path": str(evidence.get("request_path") or "").strip(),
                "fallback_used": bool(evidence.get("fallback_used")),
            }
        )
    return {
        "member_id": member_id,
        "model": model,
        "status": status,
        "planned_routes": len(planned.get("route_chain") or []),
        "fallback_used": bool(row.get("fallback_used")),
        "attempts": attempts,
    }


def _synthesis_contract() -> dict[str, Any]:
    return {
        "owner": "current_parent",
        "semantic_grouping": "parent_reasoning_required",
        "required_sections": [
            "committee_health",
            "consensus",
            "dissent",
            "unique_findings",
            "risks",
            "recommendation",
            "confidence",
        ],
        "rules": [
            "Inspect every opinion, including raw_text and failed members.",
            "Call a claim consensus only when at least two independent members support it.",
            "Cite member_id and evidence_id for synthesized claims.",
            "Keep factual evidence separate from parent inference.",
            "Preserve minority dissent; do not reduce the committee to majority voting.",
            "Lower confidence when failures, raw responses, or unsupported claims materially affect coverage.",
        ],
        "output_shape": {
            "committee_health": "short health summary",
            "consensus": [{"claim": "...", "supported_by": ["member-01"], "evidence_ids": []}],
            "dissent": [{"topic": "...", "positions": [{"member_id": "member-01", "position": "..."}]}],
            "unique_findings": [{"claim": "...", "member_id": "member-01", "evidence_ids": []}],
            "risks": ["..."],
            "recommendation": "parent decision",
            "confidence": 0.0,
        },
    }


def _response_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if value is None:
        return {}
    return {"raw_text": str(value)}


def _response_format(response: Mapping[str, Any]) -> str:
    if response.get("raw_text") is not None:
        return "raw_text"
    return "structured_json" if response else "none"


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    rows = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in rows if str(item).strip()]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "PARENT_PACKET_SCHEMA",
    "ParentPacketError",
    "build_parent_packet",
    "run_parent_committee",
]
