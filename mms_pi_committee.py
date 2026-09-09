"""Opt-in dynamic Pi committee runtime.

This module is deliberately separate from the MMS launcher and OpenCode paths.
It consumes an explicitly selected, hash-verified latest-approved bundle and
spawns isolated, read-only Pi workers with runtime-bound model routes.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import mms_consumer_bundle
import mms_pi_watchdog


DEFAULT_MEMBER_COUNT = 4
DEFAULT_MIN_FAMILIES = 3
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS = 300
DEFAULT_MAX_BUNDLE_AGE_DAYS = 30
DEFAULT_IDLE_TIMEOUT_SECONDS = 300
DEFAULT_MAX_OUTPUT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REPEATED_EVENTS = 32
DEFAULT_COMMITTEE_TIMEOUT_SECONDS = 0
DEFAULT_COMMITTEE_TIMEOUT_GRACE_SECONDS = 60
DEFAULT_QUORUM_SUCCESSES = 0
DEFAULT_QUORUM_GRACE_SECONDS = 30
DEFAULT_SELECTION_PROFILE = "balanced"
DEFAULT_GPT_MODEL = "gpt-5.5"
DEFAULT_FRONTIER_FAMILIES = (
    "MiniMax",
    "GPT",
    "Kimi",
    "Qwen",
    "DeepSeek",
    "GLM",
)
# Prefer proven lower-cost models for ordinary reviews when they are available.
BALANCED_SECONDARY_MODEL_PREFERENCES = {
    "Qwen": ("qwen3.6-plus",),
    "GLM": ("glm-5.1",),
    "Kimi": ("kimi-for-coding",),
}
DEFAULT_LENSES = (
    "architecture",
    "failure-risk",
    "implementation",
    "verification",
    "counterexample",
    "maintainability",
)
READ_ONLY_TOOLS = "read,grep,find,ls"
_OPENAI_FAMILY_PREFIXES = ("gpt-", "o1", "o3", "o4", "codex-")
_TOKYO_PROVIDER_KEYWORD = "tokyo"
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{12,}\b"),
)


class CommitteeError(RuntimeError):
    """Raised when the committee cannot be planned or run safely."""


@dataclass(frozen=True)
class RouteBinding:
    model: str
    wire_model: str
    provider_id: str
    protocol: str
    base_url: str
    request_url: str
    request_path: str
    api_key: str = field(repr=False)
    provider_profile: str = ""
    protocol_fallback_reason: str = ""
    fallback_position: int = 0

    def public(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "wire_model": self.wire_model,
            "protocol": self.protocol,
            "request_url": _redact_url(self.request_url),
            "request_path": self.request_path,
            "provider_profile": self.provider_profile,
            "protocol_fallback_reason": self.protocol_fallback_reason,
            "fallback_position": self.fallback_position,
        }


@dataclass(frozen=True)
class ModelCandidate:
    model: str
    family: str
    capabilities: Mapping[str, Any]
    context_window_tokens: int
    favorite: bool
    tier: str
    route_chain: tuple[RouteBinding, ...]


@dataclass(frozen=True)
class MemberSpec:
    member_id: str
    lens: str
    candidate: ModelCandidate
    selection_tier: str = "primary"
    fallback_candidate: ModelCandidate | None = None
    domain: str = ""
    role_id: str = ""
    role_card: str = field(default="", repr=False)
    role_card_source: str = ""
    role_card_sha256: str = ""
    required_domain: bool = False

    def public(self) -> dict[str, Any]:
        payload = {
            "member_id": self.member_id,
            "lens": self.lens,
            "model": self.candidate.model,
            "family": self.candidate.family,
            "selection_tier": self.selection_tier,
            "context_window_tokens": self.candidate.context_window_tokens,
            "route_chain": [binding.public() for binding in self.candidate.route_chain],
            "fallback_model": self.fallback_candidate.model if self.fallback_candidate else "",
        }
        if self.domain:
            payload["domain"] = self.domain
        if self.role_id:
            payload["role_id"] = self.role_id
        if self.role_card_source:
            payload["role_card_source"] = self.role_card_source
        if self.role_card_sha256:
            payload["role_card_sha256"] = self.role_card_sha256
        if self.domain:
            payload["required_domain"] = self.required_domain
        return payload


@dataclass(frozen=True)
class PreparedAttempt:
    candidate: ModelCandidate
    binding: RouteBinding
    models_payload: Mapping[str, Any]
    provider_ref: str
    selected_model: str
    thinking_level: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bundle_timestamp(manifest: Mapping[str, Any]) -> datetime | None:
    raw = str(manifest.get("generated_at") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    revision = str(manifest.get("bundle_revision") or "").strip()
    match = re.search(r"(?:^|_)bundle_(\d{14})(?:_|$)", f"_{revision}")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _bundle_freshness(bundle: Mapping[str, Any], *, max_bundle_age_days: int) -> dict[str, Any]:
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), Mapping) else {}
    revision = str(manifest.get("bundle_revision") or "").strip()
    generated_at = _bundle_timestamp(manifest)
    payload: dict[str, Any] = {
        "status": "unknown",
        "bundle_revision": revision,
        "generated_at": "",
        "age_seconds": 0,
        "age_days": 0.0,
        "max_age_days": max_bundle_age_days,
    }
    if generated_at is None:
        return payload
    age_seconds = max(0, int((_utc_now() - generated_at).total_seconds()))
    payload.update(
        {
            "status": (
                "freshness_disabled"
                if max_bundle_age_days == 0
                else ("stale" if age_seconds > max_bundle_age_days * 86400 else "fresh")
            ),
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "age_seconds": age_seconds,
            "age_days": round(age_seconds / 86400, 3),
        }
    )
    return payload


def public_bundle_metadata(bundle: Mapping[str, Any]) -> dict[str, Any]:
    freshness = bundle.get("freshness") if isinstance(bundle.get("freshness"), Mapping) else {}
    return {
        "config_root": str(bundle.get("config_root") or ""),
        "manifest_path": str(bundle.get("manifest_path") or ""),
        "revision": str(freshness.get("bundle_revision") or ""),
        "freshness": dict(freshness),
    }


def load_catalog(
    config_root: str | os.PathLike[str],
    *,
    max_bundle_age_days: int = DEFAULT_MAX_BUNDLE_AGE_DAYS,
) -> dict[str, Any]:
    if max_bundle_age_days < 0:
        raise CommitteeError("max bundle age must be zero (disabled) or greater")
    root = Path(config_root).expanduser()
    try:
        bundle = mms_consumer_bundle.load_verified_consumer_bundle(
            config_root=root,
            include_secret=True,
            env={},
            allow_default_root=False,
        )
    except mms_consumer_bundle.ConsumerBundleError as exc:
        raise CommitteeError(str(exc)) from exc
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), dict) else {}
    router = payloads.get("router") if isinstance(payloads.get("router"), dict) else {}
    if not isinstance(router.get("routes"), dict) or not router["routes"]:
        raise CommitteeError("verified latest-approved Router has no model routes")
    freshness = _bundle_freshness(bundle, max_bundle_age_days=max_bundle_age_days)
    bundle["freshness"] = freshness
    if freshness["status"] == "stale":
        raise CommitteeError(
            "latest-approved bundle is stale: "
            f"{freshness['bundle_revision']} is {freshness['age_days']:.1f} days old "
            f"(limit {max_bundle_age_days} days); select a current explicit config root"
        )
    return bundle


def build_candidates(
    bundle: Mapping[str, Any],
    *,
    required_capabilities: Sequence[str] = ("text",),
) -> tuple[list[ModelCandidate], dict[str, str]]:
    payloads = bundle.get("payloads") if isinstance(bundle.get("payloads"), Mapping) else {}
    router = payloads.get("router") if isinstance(payloads.get("router"), Mapping) else {}
    lineup = payloads.get("lineup") if isinstance(payloads.get("lineup"), Mapping) else {}
    policy = payloads.get("policy") if isinstance(payloads.get("policy"), Mapping) else {}
    capabilities = payloads.get("capabilities") if isinstance(payloads.get("capabilities"), Mapping) else {}
    profile = payloads.get("profile") if isinstance(payloads.get("profile"), Mapping) else {}
    routes = router.get("routes") if isinstance(router.get("routes"), Mapping) else {}

    candidates: list[ModelCandidate] = []
    excluded: dict[str, str] = {}
    for raw_model in sorted(routes):
        model = str(raw_model or "").strip()
        route_group = routes.get(raw_model)
        if not model or not isinstance(route_group, Mapping):
            continue
        visible, reason = _policy_visibility(model, policy)
        if not visible:
            excluded[model] = reason
            continue
        try:
            route_chain = _build_route_chain(model, route_group, profile)
        except CommitteeError as exc:
            excluded[model] = str(exc)
            continue
        model_caps = _model_capabilities(model, lineup, policy, capabilities)
        model_caps = _merge_pi_capabilities(model, route_chain[0], model_caps)
        missing = [name for name in required_capabilities if not _capability_enabled(model_caps, name)]
        if missing:
            excluded[model] = "missing capabilities: " + ", ".join(missing)
            continue
        policy_row = _mapping_at(policy, "models", model)
        candidates.append(
            ModelCandidate(
                model=model,
                family=_infer_family(model),
                capabilities=model_caps,
                context_window_tokens=_positive_int(model_caps.get("context_window_tokens")),
                favorite=bool(policy_row.get("favorite")),
                tier=str(policy_row.get("tier") or "").strip().lower(),
                route_chain=route_chain,
            )
        )
    return candidates, excluded


def load_candidates(
    config_root: str | os.PathLike[str],
    *,
    required_capabilities: Sequence[str] = ("text",),
    max_bundle_age_days: int = DEFAULT_MAX_BUNDLE_AGE_DAYS,
) -> tuple[dict[str, Any], list[ModelCandidate], dict[str, str]]:
    bundle = load_catalog(config_root, max_bundle_age_days=max_bundle_age_days)
    bundle_root = Path(str(bundle.get("config_root") or config_root)).expanduser()
    with _scoped_mms_config_root(bundle_root):
        candidates, excluded = build_candidates(bundle, required_capabilities=required_capabilities)
    return bundle, candidates, excluded


def select_members(
    candidates: Sequence[ModelCandidate],
    *,
    count: int | None = None,
    min_families: int = DEFAULT_MIN_FAMILIES,
    explicit_models: Sequence[str] = (),
    selection_profile: str = DEFAULT_SELECTION_PROFILE,
    frontier_families: Sequence[str] = DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    lenses: Sequence[str] = DEFAULT_LENSES,
    selection_seed: str = "",
) -> list[MemberSpec]:
    if count is not None and count < 1:
        raise CommitteeError("member count must be at least 1")
    if not lenses:
        raise CommitteeError("at least one review lens is required")
    by_model = {candidate.model: candidate for candidate in candidates}
    selected_rows: list[tuple[ModelCandidate, ModelCandidate | None, str]]
    if explicit_models:
        requested = _dedupe(explicit_models)
        missing = [model for model in requested if model not in by_model]
        if missing:
            raise CommitteeError("requested models are unavailable: " + ", ".join(missing))
        effective_count = count if count is not None else len(requested)
        selected_rows = [(by_model[model], None, "explicit") for model in requested[:effective_count]]
    else:
        profile = str(selection_profile or "").strip().lower()
        if profile == "frontier":
            selected = _select_frontier(
                candidates,
                families=frontier_families,
                additional_models=additional_models,
                count=count,
            )
            effective_count = count if count is not None else len(selected)
            selected_rows = [(candidate, None, "primary") for candidate in selected]
        elif profile == "balanced":
            if additional_models:
                raise CommitteeError("additional models require the frontier selection profile")
            effective_count = count if count is not None else DEFAULT_MEMBER_COUNT
            selected_rows = _select_balanced_tiers(
                candidates,
                count=effective_count,
                min_families=min_families,
                seed=selection_seed,
            )
        else:
            raise CommitteeError(f"unknown selection profile: {selection_profile}")
    if len(selected_rows) < effective_count:
        raise CommitteeError(f"only {len(selected_rows)} eligible models are available for {effective_count} members")
    return [
        MemberSpec(
            member_id=f"member-{index:02d}",
            lens=lenses[(index - 1) % len(lenses)],
            candidate=candidate,
            fallback_candidate=fallback_candidate,
            selection_tier=selection_tier,
        )
        for index, (candidate, fallback_candidate, selection_tier) in enumerate(selected_rows, start=1)
    ]


def plan_committee(
    *,
    config_root: str | os.PathLike[str],
    task: str,
    count: int | None = None,
    min_families: int = DEFAULT_MIN_FAMILIES,
    explicit_models: Sequence[str] = (),
    selection_profile: str = DEFAULT_SELECTION_PROFILE,
    frontier_families: Sequence[str] = DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    required_capabilities: Sequence[str] = ("text",),
    lenses: Sequence[str] = DEFAULT_LENSES,
    mission_id: str | None = None,
    max_bundle_age_days: int = DEFAULT_MAX_BUNDLE_AGE_DAYS,
) -> tuple[dict[str, Any], list[MemberSpec], dict[str, Any]]:
    task_text = str(task or "").strip()
    if not task_text:
        raise CommitteeError("task must not be empty")
    if explicit_models and additional_models:
        raise CommitteeError("--model cannot be combined with additional models")
    bundle, candidates, excluded = load_candidates(
        config_root,
        required_capabilities=required_capabilities,
        max_bundle_age_days=max_bundle_age_days,
    )
    effective_mission_id = mission_id or f"pi-{uuid.uuid4().hex[:12]}"
    members = select_members(
        candidates,
        count=count,
        min_families=min_families,
        explicit_models=explicit_models,
        selection_profile=selection_profile,
        frontier_families=frontier_families,
        additional_models=additional_models,
        lenses=lenses,
        selection_seed=effective_mission_id,
    )
    effective_count = len(members)
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), Mapping) else {}
    selected_families = sorted({member.candidate.family for member in members})
    effective_profile = "explicit" if explicit_models else str(selection_profile).strip().lower()
    effective_frontier_families = list(_dedupe(_canonical_family(family) for family in frontier_families))
    plan = {
        "schema": "mms.pi_committee.plan.v1",
        "mission_id": effective_mission_id,
        "task": task_text,
        "route_source": f"mms:latest-approved:{manifest.get('bundle_revision') or ''}",
        "component_revisions": dict(bundle.get("component_revisions") or {}),
        "bundle": public_bundle_metadata(bundle),
        "selection": {
            "requested_count": effective_count,
            "profile": effective_profile,
            "seed": effective_mission_id if effective_profile == "balanced" else "",
            "min_families": min_families,
            "selected_families": selected_families,
            "eligible_models": len(candidates),
            "excluded_models": excluded,
            "explicit_models": list(_dedupe(explicit_models)),
            "target_families": effective_frontier_families if effective_profile == "frontier" else [],
            "family_champions": {
                member.candidate.family: member.candidate.model
                for member in members
                if effective_profile == "frontier" and member.candidate.family in set(effective_frontier_families)
            },
            "additional_models": list(_dedupe(additional_models)),
        },
        "members": [member.public() for member in members],
        "isolation": {
            "global_config_writes": False,
            "global_oauth_fallback": False,
            "opencode_dependency": False,
            "worker_tools": READ_ONLY_TOOLS,
        },
    }
    return plan, members, bundle


def run_committee(
    *,
    config_root: str | os.PathLike[str],
    task: str,
    cwd: str | os.PathLike[str],
    count: int | None = None,
    min_families: int = DEFAULT_MIN_FAMILIES,
    explicit_models: Sequence[str] = (),
    selection_profile: str = DEFAULT_SELECTION_PROFILE,
    frontier_families: Sequence[str] = DEFAULT_FRONTIER_FAMILIES,
    additional_models: Sequence[str] = (),
    required_capabilities: Sequence[str] = ("text",),
    lenses: Sequence[str] = DEFAULT_LENSES,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    kimi_attempt_timeout_seconds: int = DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
    max_bundle_age_days: int = DEFAULT_MAX_BUNDLE_AGE_DAYS,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = DEFAULT_MAX_REPEATED_EVENTS,
    committee_timeout_seconds: int = DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
    quorum_successes: int = DEFAULT_QUORUM_SUCCESSES,
    quorum_grace_seconds: int = DEFAULT_QUORUM_GRACE_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan, members, _bundle = plan_committee(
        config_root=config_root,
        task=task,
        count=count,
        min_families=min_families,
        explicit_models=explicit_models,
        selection_profile=selection_profile,
        frontier_families=frontier_families,
        additional_models=additional_models,
        required_capabilities=required_capabilities,
        lenses=lenses,
        max_bundle_age_days=max_bundle_age_days,
    )
    return run_preplanned_committee(
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


def run_preplanned_committee(
    *,
    config_root: str | os.PathLike[str],
    plan: Mapping[str, Any],
    members: Sequence[MemberSpec],
    cwd: str | os.PathLike[str],
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    kimi_attempt_timeout_seconds: int = DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = DEFAULT_MAX_REPEATED_EVENTS,
    committee_timeout_seconds: int = DEFAULT_COMMITTEE_TIMEOUT_SECONDS,
    quorum_successes: int = DEFAULT_QUORUM_SUCCESSES,
    quorum_grace_seconds: int = DEFAULT_QUORUM_GRACE_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    target_cwd = Path(cwd).expanduser().resolve()
    if not target_cwd.is_dir():
        raise CommitteeError(f"worker cwd is not a directory: {target_cwd}")
    if not members:
        raise CommitteeError("preplanned committee must contain at least one member")
    member_ids = [str(member.member_id).strip() for member in members]
    if any(not member_id for member_id in member_ids) or len(set(member_ids)) != len(member_ids):
        raise CommitteeError("preplanned committee member ids must be non-empty and unique")
    effective_plan = dict(plan)
    task = str(effective_plan.get("task") or "").strip()
    if not task:
        raise CommitteeError("preplanned committee task must not be empty")
    if not str(effective_plan.get("mission_id") or "").strip():
        raise CommitteeError("preplanned committee mission id must not be empty")
    if not str(effective_plan.get("route_source") or "").strip():
        raise CommitteeError("preplanned committee route source must not be empty")
    effective_plan["members"] = [member.public() for member in members]
    if max_concurrency < 1:
        raise CommitteeError("max concurrency must be at least 1")
    if timeout_seconds < 1:
        raise CommitteeError("timeout must be at least 1 second")
    if kimi_attempt_timeout_seconds < 0:
        raise CommitteeError("Kimi attempt timeout must be zero (disabled) or greater")
    if idle_timeout_seconds < 1:
        raise CommitteeError("idle timeout must be at least 1 second")
    if max_output_bytes < 1:
        raise CommitteeError("max output bytes must be at least 1")
    if max_repeated_events < 2:
        raise CommitteeError("max repeated events must be at least 2")
    if committee_timeout_seconds < 0:
        raise CommitteeError("committee timeout must be zero (auto) or greater")
    if quorum_successes < 0 or quorum_successes > len(members):
        raise CommitteeError("quorum successes must be zero or no greater than member count")
    if quorum_grace_seconds < 0:
        raise CommitteeError("quorum grace must not be negative")

    worker_count = min(max_concurrency, len(members))
    wave_count = (len(members) + worker_count - 1) // worker_count
    effective_committee_timeout = committee_timeout_seconds or (
        timeout_seconds * wave_count + DEFAULT_COMMITTEE_TIMEOUT_GRACE_SECONDS
    )
    watchdog_config = {
        "member_wall_timeout_seconds": timeout_seconds,
        "kimi_attempt_timeout_seconds": kimi_attempt_timeout_seconds,
        "idle_timeout_seconds": idle_timeout_seconds,
        "max_output_bytes": max_output_bytes,
        "max_repeated_events": max_repeated_events,
        "committee_timeout_seconds": effective_committee_timeout,
        "committee_timeout_mode": "explicit" if committee_timeout_seconds else "auto_by_concurrency_waves",
        "quorum_successes": quorum_successes,
        "quorum_grace_seconds": quorum_grace_seconds,
    }
    effective_plan["watchdog"] = watchdog_config
    if dry_run:
        return {
            "schema": "mms.pi_committee.result.v1",
            "mission_id": effective_plan["mission_id"],
            "status": "dry_run",
            "watchdog": {**watchdog_config, "committee_stop_reason": "not_started"},
            "plan": effective_plan,
            "results": [],
        }

    prepared = _prepare_members(members, config_root=Path(config_root).expanduser())
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    cancellation = mms_pi_watchdog.CancellationController()
    committee_deadline = started + effective_committee_timeout
    quorum_deadline: float | None = None
    succeeded = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="pi-committee") as pool:
        future_to_member = {
            pool.submit(
                _run_member,
                member,
                prepared[member.member_id],
                task=task,
                cwd=target_cwd,
                timeout_seconds=timeout_seconds,
                kimi_attempt_timeout_seconds=kimi_attempt_timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
                max_output_bytes=max_output_bytes,
                max_repeated_events=max_repeated_events,
                cancellation=cancellation,
                route_source=effective_plan["route_source"],
            ): member
            for member in members
        }
        pending = set(future_to_member)
        while pending:
            now = time.monotonic()
            if not cancellation.is_cancelled():
                if now >= committee_deadline:
                    cancellation.cancel("committee_timeout")
                elif quorum_deadline is not None and now >= quorum_deadline:
                    cancellation.cancel("quorum_reached")
            if cancellation.is_cancelled():
                for future in pending:
                    future.cancel()
            next_deadline = committee_deadline
            if quorum_deadline is not None:
                next_deadline = min(next_deadline, quorum_deadline)
            wait_seconds = min(0.1, max(0.001, next_deadline - time.monotonic()))
            done, pending = concurrent.futures.wait(
                pending,
                timeout=wait_seconds,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                member = future_to_member[future]
                if future.cancelled():
                    result = _cancelled_member_result(member, cancellation.reason or "cancelled")
                else:
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            **_member_identity(member),
                            "status": "worker_error",
                            "terminal_reason": "worker_error",
                            "error": _redact_text(str(exc), _all_api_keys(members)),
                        }
                results.append(result)
                if result.get("status") == "success":
                    succeeded += 1
                    if quorum_successes and succeeded >= quorum_successes and quorum_deadline is None:
                        quorum_deadline = time.monotonic() + quorum_grace_seconds
    results.sort(key=lambda item: str(item.get("member_id") or ""))
    succeeded = sum(1 for item in results if item.get("status") == "success")
    stop_reason = cancellation.reason or "completed"
    return {
        "schema": "mms.pi_committee.result.v1",
        "mission_id": effective_plan["mission_id"],
        "status": "success" if succeeded == len(results) else ("partial" if succeeded else "failed"),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "summary": {"members": len(results), "succeeded": succeeded, "failed": len(results) - succeeded},
        "watchdog": {**watchdog_config, "committee_stop_reason": stop_reason},
        "plan": effective_plan,
        "results": results,
    }


def _prepare_members(members: Sequence[MemberSpec], *, config_root: Path) -> dict[str, tuple[PreparedAttempt, ...]]:
    prepared: dict[str, tuple[PreparedAttempt, ...]] = {}
    with _scoped_mms_config_root(config_root):
        for member in members:
            candidate_chain = [member.candidate]
            if member.fallback_candidate is not None:
                candidate_chain.append(member.fallback_candidate)
            attempts = tuple(
                _prepare_attempt(member, candidate, binding)
                for candidate in candidate_chain
                for binding in candidate.route_chain
            )
            prepared[member.member_id] = attempts
    return prepared


def _prepare_attempt(member: MemberSpec, candidate: ModelCandidate, binding: RouteBinding) -> PreparedAttempt:
    import mms_pi_support

    runtime: dict[str, Any] = {
        "id": binding.provider_id,
        "provider_id": binding.provider_id,
        "name": binding.provider_id,
        "api_key": binding.api_key,
        "model": candidate.model,
        "provider_profile": binding.provider_profile,
        "_launch_prefetched_probe": {"models": [candidate.model]},
    }
    if binding.protocol == "anthropic_messages":
        runtime["anthropic_base_url"] = binding.base_url
    else:
        runtime["openai_base_url"] = binding.base_url
    try:
        payload, provider_ref = mms_pi_support._pi_build_models_payload(runtime, candidate.model)
    except RuntimeError as exc:
        raise CommitteeError(f"Pi payload preparation failed for {candidate.model}: {exc}") from exc
    payload = json.loads(json.dumps(payload))
    provider = payload.get("providers", {}).get(provider_ref)
    if not isinstance(provider, dict):
        raise CommitteeError(f"Pi payload did not contain selected provider {provider_ref}")
    configured_protocol = _pi_api_protocol(provider.get("api"))
    if configured_protocol != binding.protocol:
        raise CommitteeError(
            f"Pi payload protocol drift for {candidate.model}: "
            f"planned {binding.protocol}, configured {configured_protocol or 'unknown'}"
        )
    configured_url, configured_path = _request_target(str(provider.get("baseUrl") or ""), configured_protocol)
    if configured_url != binding.request_url or configured_path != binding.request_path:
        raise CommitteeError(
            f"Pi payload request target drift for {candidate.model}: "
            f"planned {binding.request_path}, configured {configured_path}"
        )
    env_name = _credential_env_name(member.member_id, binding.fallback_position)
    provider["apiKey"] = f"${env_name}"
    selected_model = _patch_wire_model(provider, candidate.model, binding.wire_model)
    return PreparedAttempt(
        candidate=candidate,
        binding=binding,
        models_payload=payload,
        provider_ref=provider_ref,
        selected_model=selected_model,
        thinking_level=_highest_thinking_level(provider, candidate.model, selected_model),
    )


def _pi_api_protocol(api: Any) -> str:
    return {
        "anthropic-messages": "anthropic_messages",
        "openai-responses": "openai_responses",
        "openai-completions": "openai_chat_completions",
    }.get(str(api or "").strip(), "")


def _highest_thinking_level(provider: Mapping[str, Any], logical_model: str, wire_model: str) -> str:
    models = provider.get("models") if isinstance(provider.get("models"), list) else []
    for row in models:
        if not isinstance(row, Mapping):
            continue
        names = {str(row.get("name") or ""), str(row.get("id") or "")}
        if not names.intersection({logical_model, wire_model}):
            continue
        level_map = row.get("thinkingLevelMap") if isinstance(row.get("thinkingLevelMap"), Mapping) else {}
        for level in ("max", "xhigh", "high", "medium", "low", "minimal"):
            mapped = str(level_map.get(level) or "").strip()
            if mapped:
                return level
    return ""


def _run_member(
    member: MemberSpec,
    attempts: Sequence[PreparedAttempt],
    *,
    task: str,
    cwd: Path,
    timeout_seconds: int,
    idle_timeout_seconds: int,
    max_output_bytes: int,
    max_repeated_events: int,
    cancellation: mms_pi_watchdog.CancellationController,
    route_source: str,
    kimi_attempt_timeout_seconds: int = DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    errors: list[str] = []
    attempt_records: list[dict[str, Any]] = []
    fallback_used = False
    fallback_skipped_reason = ""
    last_terminal_reason = "no_route_attempts"
    all_keys = [attempt.binding.api_key for attempt in attempts]
    for index, attempt in enumerate(attempts):
        if cancellation.is_cancelled():
            return _redact_object(_cancelled_member_result(member, cancellation.reason), all_keys)
        remaining_float = deadline - time.monotonic()
        if remaining_float < 1:
            fallback_skipped_reason = "no_budget_remaining" if index > 0 else ""
            attempt_records.extend(_skipped_attempt_records(attempts[index:], "no_budget_remaining"))
            break
        remaining = int(remaining_float)
        attempt_timeout = _attempt_timeout_seconds(
            member,
            remaining_seconds=remaining,
            attempts_left=len(attempts) - index,
            kimi_attempt_timeout_seconds=kimi_attempt_timeout_seconds,
        )
        has_model_backup = any(
            next_attempt.candidate.model != member.candidate.model
            for next_attempt in attempts[index + 1:]
        )
        if has_model_backup:
            attempt_timeout = min(attempt_timeout, max(1, remaining // 2))
        model_fallback = attempt.candidate.model != member.candidate.model
        route_fallback = attempt.binding.fallback_position > 0
        fallback_used = fallback_used or route_fallback or model_fallback or bool(attempt.binding.protocol_fallback_reason)
        active_member = member if not model_fallback else MemberSpec(
            member_id=member.member_id,
            lens=member.lens,
            candidate=attempt.candidate,
            selection_tier="backup",
        )
        result = _run_attempt(
            active_member,
            attempt,
            task=task,
            cwd=cwd,
            timeout_seconds=attempt_timeout,
            idle_timeout_seconds=idle_timeout_seconds,
            max_output_bytes=max_output_bytes,
            max_repeated_events=max_repeated_events,
            cancellation=cancellation,
        )
        fallback_reason = "; ".join(errors) if route_fallback else ""
        if attempt.binding.protocol_fallback_reason:
            fallback_reason = "; ".join(
                item for item in (fallback_reason, attempt.binding.protocol_fallback_reason) if item
            )
        evidence = _transport_evidence(
            active_member,
            attempt.binding,
            route_source=route_source,
            fallback_used=model_fallback or route_fallback or bool(attempt.binding.protocol_fallback_reason),
            fallback_reason=fallback_reason,
            usage=result.get("_usage", {}),
        )
        attempt_records.append(
            {
                "provider_id": attempt.binding.provider_id,
                "model": attempt.candidate.model,
                "model_fallback": model_fallback,
                "fallback_position": attempt.binding.fallback_position,
                "started": True,
                "budget_seconds": attempt_timeout,
                "status": result.get("status"),
                "terminal_reason": result.get("terminal_reason", result.get("status")),
                "error": result.get("error", ""),
                "watchdog": result.get("watchdog", {}),
                "cache_transport_evidence": evidence,
            }
        )
        last_terminal_reason = str(result.get("terminal_reason") or result.get("status") or "unknown")
        if result["status"] == "success":
            result.pop("_usage", None)
            result.update(_member_identity(member))
            result["executed_model"] = attempt.candidate.model
            result["fallback_used"] = evidence["fallback_used"]
            result["fallback_reason"] = evidence["fallback_reason"]
            result["cache_transport_evidence"] = evidence
            result["attempts"] = attempt_records
            return _redact_object(result, all_keys)
        errors.append(f"{attempt.binding.provider_id}:{result.get('status')}")
        if cancellation.is_cancelled():
            break
        if time.monotonic() >= deadline:
            if index + 1 < len(attempts):
                fallback_skipped_reason = "no_budget_remaining"
                attempt_records.extend(_skipped_attempt_records(attempts[index + 1 :], "no_budget_remaining"))
            break
    return _redact_object(
        {
            **_member_identity(member),
            "status": "failed",
            "terminal_reason": last_terminal_reason,
            "error": "; ".join(errors) or "no route attempts were available",
            "fallback_used": fallback_used,
            "fallback_reason": "; ".join(errors[:-1]) if fallback_used else "",
            "fallback_skipped_reason": fallback_skipped_reason,
            "attempts": attempt_records,
        },
        all_keys,
    )


def _attempt_timeout_seconds(
    member: MemberSpec,
    *,
    remaining_seconds: int,
    attempts_left: int,
    kimi_attempt_timeout_seconds: int,
) -> int:
    remaining = max(1, int(remaining_seconds))
    if member.candidate.family != "Kimi" or kimi_attempt_timeout_seconds == 0:
        return remaining
    fair_share = max(1, remaining // max(1, attempts_left))
    return max(1, min(remaining, kimi_attempt_timeout_seconds, fair_share))


def _skipped_attempt_records(
    attempts: Sequence[PreparedAttempt],
    terminal_reason: str,
) -> list[dict[str, Any]]:
    return [
        {
            "provider_id": attempt.binding.provider_id,
            "fallback_position": attempt.binding.fallback_position,
            "started": False,
            "budget_seconds": 0,
            "status": "skipped",
            "terminal_reason": terminal_reason,
            "error": "",
            "watchdog": {},
        }
        for attempt in attempts
    ]


def _run_attempt(
    member: MemberSpec,
    attempt: PreparedAttempt,
    *,
    task: str,
    cwd: Path,
    timeout_seconds: int,
    idle_timeout_seconds: int,
    max_output_bytes: int,
    max_repeated_events: int,
    cancellation: mms_pi_watchdog.CancellationController,
) -> dict[str, Any]:
    started = time.monotonic()
    root = Path(__file__).resolve().parent
    wrapper = root / "scripts" / "pi-cli-wrapper.sh"
    if not wrapper.is_file():
        raise CommitteeError(f"repo-local Pi wrapper is missing: {wrapper}")
    prompt = _worker_prompt(task, member)
    with tempfile.TemporaryDirectory(prefix=f"mms-pi-{member.member_id}-") as temp_dir:
        temp_root = Path(temp_dir)
        agent_dir = temp_root / ".pi" / "agent"
        session_dir = agent_dir / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        _write_private_json(agent_dir / "models.json", attempt.models_payload)
        _write_private_json(agent_dir / "settings.json", {})
        role_prompt_path: Path | None = None
        if member.role_card:
            role_prompt_path = temp_root / "court-role.md"
            _write_private_text(role_prompt_path, _role_system_prompt(member))
        env_name = _credential_env_name(member.member_id, attempt.binding.fallback_position)
        env = _isolated_env(temp_root)
        env.update(
            {
                "PI_CODING_AGENT_DIR": str(agent_dir),
                "PI_CODING_AGENT_SESSION_DIR": str(session_dir),
                "PI_TELEMETRY": "0",
                "PI_SKIP_VERSION_CHECK": "1",
                "MMS_PI_NPX_CACHE": str(root / ".ai" / "cache" / "pi-npx"),
                env_name: attempt.binding.api_key,
            }
        )
        cmd = [
            str(wrapper),
            "--provider",
            attempt.provider_ref,
            "--model",
            attempt.selected_model,
            "--mode",
            "json",
            "--no-session",
            "--no-context-files",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--tools",
            READ_ONLY_TOOLS,
        ]
        if attempt.thinking_level:
            cmd.extend(["--thinking", attempt.thinking_level])
        if role_prompt_path is not None:
            cmd.extend(["--append-system-prompt", str(role_prompt_path)])
        cmd.extend(["-p", prompt])
        outcome = mms_pi_watchdog.run_process(
            cmd,
            cwd=cwd,
            env=env,
            policy=mms_pi_watchdog.WatchdogPolicy(
                wall_timeout_seconds=timeout_seconds,
                idle_timeout_seconds=min(idle_timeout_seconds, timeout_seconds),
                max_output_bytes=max_output_bytes,
                max_repeated_events=max_repeated_events,
            ),
            cancellation=cancellation,
        )
    watchdog = outcome.public()
    if outcome.terminal_reason != "completed":
        return {
            "status": outcome.terminal_reason,
            "terminal_reason": outcome.terminal_reason,
            "elapsed_ms": outcome.elapsed_ms,
            "error": outcome.stderr[-800:] if outcome.terminal_reason == "launch_error" else "",
            "watchdog": watchdog,
        }
    message, parse_error = _parse_pi_stream(outcome.stdout)
    text = _message_text(message)
    if outcome.returncode != 0:
        return {
            "status": "launch_error",
            "terminal_reason": "launch_error",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(message.get("errorMessage") or outcome.stderr[-800:] or parse_error or "Pi exited non-zero"),
            "watchdog": watchdog,
        }
    if str(message.get("stopReason") or "").strip().lower() == "error":
        return {
            "status": "request_error",
            "terminal_reason": "request_error",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(message.get("errorMessage") or "Pi request failed"),
            "watchdog": watchdog,
        }
    if not text:
        return {
            "status": "empty_response",
            "terminal_reason": "empty_response",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "watchdog": watchdog,
        }
    parsed = _parse_response_object(text)
    return {
        **_member_identity(member),
        "status": "success",
        "terminal_reason": "completed",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "provider_id": attempt.binding.provider_id,
        "protocol": attempt.binding.protocol,
        "response": parsed if parsed is not None else {"raw_text": text},
        "watchdog": watchdog,
        "_usage": _normalize_usage(message.get("usage")),
    }


def _cancelled_member_result(member: MemberSpec, reason: str) -> dict[str, Any]:
    terminal_reason = str(reason or "cancelled").strip() or "cancelled"
    return {
        **_member_identity(member),
        "status": "failed",
        "terminal_reason": terminal_reason,
        "error": terminal_reason,
        "fallback_used": False,
        "fallback_reason": "",
        "attempts": [],
    }


def _worker_prompt(task: str, member: MemberSpec) -> str:
    assignments = [f"Your assigned lens: {member.lens}"]
    if member.domain:
        assignments.append(f"Your assigned domain: {member.domain}")
    if member.role_id:
        assignments.append(f"Your assigned role: {member.role_id}")
    assignment_text = "\n".join(assignments)
    return f"""You are an independent read-only committee member.

Mission:
{task}

{assignment_text}

Rules:
- Inspect only. Do not edit files, run shell commands, or invoke other agents.
- Work independently; do not assume other committee opinions.
- Separate inspected facts from inference.
- Return one JSON object and no Markdown fence.

Required JSON shape:
{{
  "verdict": "short conclusion",
  "confidence": 0.0,
  "findings": [{{"claim": "...", "evidence": ["path or fact"], "severity": "low|medium|high"}}],
  "risks": ["..."],
  "recommendation": "...",
  "role_payload": {{}}
}}
""".strip()


def _member_identity(member: MemberSpec) -> dict[str, Any]:
    identity = {
        "member_id": member.member_id,
        "model": member.candidate.model,
        "family": member.candidate.family,
        "lens": member.lens,
    }
    if member.domain:
        identity["domain"] = member.domain
        identity["required_domain"] = member.required_domain
    if member.role_id:
        identity["role_id"] = member.role_id
    if member.role_card_sha256:
        identity["role_card_sha256"] = member.role_card_sha256
    return identity


def _role_system_prompt(member: MemberSpec) -> str:
    return f"""Canonical role card ({member.role_id}):

{member.role_card.strip()}

Pi Court adapter contract:
- Apply the role card's method, gates, and evidence discipline only within the assigned domain and mission.
- Remain an independent read-only court seat. Do not edit files, run shell commands, or invoke other agents.
- The committee JSON envelope requested by the user prompt has precedence over any role-specific output shape.
- Put useful role-specific fields under top-level role_payload; keep verdict, confidence, findings, risks, and recommendation populated.
- Do not claim domain expertise, testing, or evidence that was not actually inspected.
""".strip()


def _build_route_chain(model: str, route_group: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[RouteBinding, ...]:
    primary = route_group.get("primary")
    if not isinstance(primary, Mapping):
        raise CommitteeError("route primary is missing")
    chain_rows: list[Mapping[str, Any]] = [primary]
    chain_rows.extend(item for item in route_group.get("fallbacks") or [] if isinstance(item, Mapping))
    chain_rows = _order_route_rows(model, chain_rows)
    bindings: list[RouteBinding] = []
    for position, row in enumerate(chain_rows):
        try:
            binding = _route_binding(model, row, profile, fallback_position=position)
            block_reason = _pi_binding_block_reason(model, binding)
            if block_reason:
                raise CommitteeError(f"Pi route is blocked: {block_reason}")
            bindings.append(binding)
        except CommitteeError:
            if position == 0:
                raise
    return tuple(bindings)


def _order_route_rows(model: str, rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not _requires_tokyo_route(model):
        return list(rows)
    tokyo_routes = [row for row in rows if _TOKYO_PROVIDER_KEYWORD in str(row.get("provider_id") or "").lower()]
    if not tokyo_routes:
        raise CommitteeError(f"Tokyo route is required for non-GPT model {model}")
    return tokyo_routes


def _requires_tokyo_route(model: str) -> bool:
    return not str(model or "").strip().lower().startswith(_OPENAI_FAMILY_PREFIXES)


def _pi_binding_block_reason(model: str, binding: RouteBinding) -> str:
    import mms_pi_support

    if not mms_pi_support._pi_model_supported(model):
        return "model is not a conversational Pi model"
    runtime = {
        "id": binding.provider_id,
        "provider_id": binding.provider_id,
        "model": model,
        "_launch_prefetched_probe": {"models": [model, binding.wire_model]},
    }
    return str(mms_pi_support._pi_model_block_reason(runtime, model) or "").strip()


def _route_binding(
    model: str,
    route: Mapping[str, Any],
    profile_payload: Mapping[str, Any],
    *,
    fallback_position: int,
) -> RouteBinding:
    provider_id = str(route.get("provider_id") or "").strip()
    api_key = str(route.get("api_key") or "").strip()
    wire_model = str(route.get("model_id") or model).strip()
    anthropic_url = str(route.get("anthropic_base_url") or "").strip()
    openai_url = str(route.get("openai_base_url") or "").strip()
    if not provider_id:
        raise CommitteeError("route provider_id is missing")
    if not api_key:
        raise CommitteeError(f"route {provider_id} has no API key")
    protocol, base_url, protocol_fallback_reason = _select_protocol(
        model,
        anthropic_url=anthropic_url,
        openai_url=openai_url,
    )
    request_url, request_path = _request_target(base_url, protocol)
    return RouteBinding(
        model=model,
        wire_model=wire_model,
        provider_id=provider_id,
        protocol=protocol,
        base_url=base_url,
        request_url=request_url,
        request_path=request_path,
        api_key=api_key,
        provider_profile=_provider_profile_id(provider_id, route, profile_payload),
        protocol_fallback_reason=protocol_fallback_reason,
        fallback_position=fallback_position,
    )


def _select_protocol(model: str, *, anthropic_url: str, openai_url: str) -> tuple[str, str, str]:
    normalized = model.strip().lower()
    if normalized.startswith(_OPENAI_FAMILY_PREFIXES) and openai_url:
        return "openai_responses", openai_url, ""
    if anthropic_url:
        return "anthropic_messages", anthropic_url, ""
    if openai_url:
        protocol = "openai_responses" if normalized.startswith(_OPENAI_FAMILY_PREFIXES) else "openai_chat_completions"
        fallback_reason = ""
        if protocol == "openai_chat_completions":
            fallback_reason = "route has no Anthropic endpoint; using explicit OpenAI-compatible route"
        return protocol, openai_url, fallback_reason
    raise CommitteeError("route has neither Anthropic nor OpenAI base URL")


def _request_target(base_url: str, protocol: str) -> tuple[str, str]:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CommitteeError("route base URL must be an absolute http(s) URL")
    path = parsed.path.rstrip("/")
    if protocol == "anthropic_messages":
        if path.endswith("/v1/messages"):
            request_path = path
        elif path.endswith("/v1"):
            request_path = f"{path}/messages"
        else:
            request_path = f"{path}/v1/messages" if path else "/v1/messages"
    else:
        suffix = "/responses" if protocol == "openai_responses" else "/chat/completions"
        if path.endswith(suffix):
            request_path = path
        elif path.endswith("/v1"):
            request_path = f"{path}{suffix}"
        else:
            request_path = f"{path}/v1{suffix}" if path else f"/v1{suffix}"
    return urlunsplit((parsed.scheme, parsed.netloc, request_path, "", "")), request_path


def _provider_profile_id(provider_id: str, route: Mapping[str, Any], profile_payload: Mapping[str, Any]) -> str:
    explicit = str(route.get("provider_profile") or route.get("profile") or "").strip()
    if explicit:
        return explicit
    profiles = profile_payload.get("profiles") if isinstance(profile_payload.get("profiles"), Mapping) else {}
    return provider_id if provider_id in profiles else ""


def _model_capabilities(
    model: str,
    lineup: Mapping[str, Any],
    policy: Mapping[str, Any],
    approved: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    approved_row = _approved_model_row(approved, model)
    if isinstance(approved_row.get("capabilities"), Mapping):
        result.update(approved_row["capabilities"])
    result.update({key: value for key, value in approved_row.items() if key not in {"capabilities", "sources"}})
    policy_row = _mapping_at(policy, "models", model)
    if isinstance(policy_row.get("capabilities"), Mapping):
        result.update(policy_row["capabilities"])
    lineup_primary = _mapping_at(lineup, "routes", model, "primary")
    context = _positive_int(
        result.get("context_window_tokens")
        or result.get("official_context_window_tokens")
        or result.get("provider_top_context_window_tokens")
        or lineup_primary.get("max_context_tokens")
        or lineup_primary.get("context_window_tokens")
    )
    if context:
        result["context_window_tokens"] = context
    result.setdefault("text", True)
    return result


def _merge_pi_capabilities(
    model: str,
    binding: RouteBinding,
    configured: Mapping[str, Any],
) -> dict[str, Any]:
    """Fill missing bundle facts with the same resolver used by the Pi payload."""
    import mms_pi_support

    runtime: dict[str, Any] = {
        "id": binding.provider_id,
        "provider_id": binding.provider_id,
        "model": model,
        "provider_profile": binding.provider_profile,
        "_launch_prefetched_probe": {"models": [model, binding.wire_model]},
    }
    if binding.protocol == "anthropic_messages":
        runtime["anthropic_base_url"] = binding.base_url
    else:
        runtime["openai_base_url"] = binding.base_url
    try:
        resolved = mms_pi_support._pi_model_capabilities(runtime, model)
    except (OSError, RuntimeError, TypeError, ValueError):
        return dict(configured)
    if not isinstance(resolved, Mapping):
        return dict(configured)

    result = dict(configured)
    adopted: set[str] = set()
    for key, value in resolved.items():
        if key == "sources":
            continue
        current = result.get(key)
        missing = key not in result or current is None or current == ""
        if isinstance(current, (int, float)) and not isinstance(current, bool) and current <= 0:
            missing = True
        if missing:
            result[key] = value
            adopted.add(str(key))
    configured_sources = result.get("sources") if isinstance(result.get("sources"), Mapping) else {}
    resolved_sources = resolved.get("sources") if isinstance(resolved.get("sources"), Mapping) else {}
    if configured_sources or resolved_sources:
        sources = dict(configured_sources)
        for key in adopted:
            if key in resolved_sources:
                sources[key] = resolved_sources[key]
        result["sources"] = sources
    return result


def _approved_model_row(approved: Mapping[str, Any], model: str) -> dict[str, Any]:
    rows = approved.get("models")
    if isinstance(rows, Mapping):
        row = rows.get(model)
        return dict(row) if isinstance(row, Mapping) else {}
    if not isinstance(rows, list):
        return {}
    normalized = model.strip().lower()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        identities = (
            row.get("alias"),
            row.get("model"),
            row.get("model_name"),
            row.get("model_id"),
            row.get("canonical_model_id"),
        )
        if any(str(value or "").strip().lower() == normalized for value in identities):
            return dict(row)
    return {}


def _policy_visibility(model: str, policy: Mapping[str, Any]) -> tuple[bool, str]:
    row = _mapping_at(policy, "models", model)
    if row.get("visible") is False:
        return False, "policy visible=false"
    capabilities = row.get("capabilities") if isinstance(row.get("capabilities"), Mapping) else {}
    if capabilities.get("text") is False:
        return False, "policy capabilities.text=false"
    hidden_in = {str(item).strip().lower() for item in row.get("hide_in") or []}
    if hidden_in.intersection({"pi-committee", "pi_committee"}):
        return False, "policy hide_in includes pi-committee"
    project = _mapping_at(policy, "projects", "pi-committee") or _mapping_at(policy, "projects", "pi_committee")
    allowed = {str(item).strip() for item in project.get("allowed_models") or []}
    hidden = {str(item).strip() for item in (project.get("hidden_models") or []) + (project.get("disabled_models") or [])}
    if model in hidden:
        return False, "pi-committee project policy denies model"
    if project.get("default_visible") is False and model not in allowed:
        return False, "pi-committee project policy does not allow model"
    return True, ""


def _select_diverse(candidates: Sequence[ModelCandidate], *, count: int, min_families: int) -> list[ModelCandidate]:
    ranked = sorted(candidates, key=_candidate_sort_key)
    if len(ranked) < count:
        return ranked
    family_best: dict[str, ModelCandidate] = {}
    for candidate in ranked:
        family_best.setdefault(candidate.family, candidate)
    diversity_target = min(count, max(1, min_families), len(family_best))
    representatives = sorted(family_best.values(), key=_candidate_sort_key)[:diversity_target]
    selected = list(representatives)
    selected_models = {item.model for item in selected}
    for candidate in ranked:
        if len(selected) >= count:
            break
        if candidate.model not in selected_models:
            selected.append(candidate)
            selected_models.add(candidate.model)
    return selected


def _select_balanced_tiers(
    candidates: Sequence[ModelCandidate],
    *,
    count: int,
    min_families: int,
    seed: str,
) -> list[tuple[ModelCandidate, ModelCandidate | None, str]]:
    # Gemini is explicitly excluded from the ordinary balanced profile.
    eligible = [candidate for candidate in candidates if candidate.family != "Gemini"]
    by_family: dict[str, list[ModelCandidate]] = {}
    for candidate in eligible:
        by_family.setdefault(candidate.family, []).append(candidate)
    if len(by_family) < min_families:
        raise CommitteeError(f"only {len(by_family)} eligible families are available for {min_families} required")

    # Select distinct families first; the mission seed makes the lineup reproducible.
    family_names = sorted(
        by_family,
        key=lambda family: hashlib.sha256(f"{seed}:family:{family}".encode("utf-8")).digest(),
    )[:count]
    selected = []
    for family in family_names:
        ranked = sorted(by_family[family], key=_frontier_model_sort_key)
        primary = ranked[0]
        secondary = _balanced_secondary_candidate(primary.family, ranked)
        if secondary is None or secondary.model == primary.model:
            selected.append((primary, None, "primary"))
            continue
        digest = hashlib.sha256(f"{seed}:{primary.family}".encode("utf-8")).digest()
        use_secondary = bool(digest[0] & 1)
        selected.append(
            (secondary, primary, "secondary") if use_secondary else (primary, secondary, "primary")
        )
    return selected


def _balanced_secondary_candidate(family: str, ranked: Sequence[ModelCandidate]) -> ModelCandidate | None:
    if not ranked:
        return None
    by_model = {candidate.model.lower(): candidate for candidate in ranked}
    for preferred in BALANCED_SECONDARY_MODEL_PREFERENCES.get(family, ()):
        candidate = by_model.get(preferred.lower())
        if candidate is not None:
            return candidate
    for candidate in ranked[1:]:
        # Highspeed Kimi is intentionally excluded from ordinary cost-balanced work.
        if candidate.family == "Kimi" and "highspeed" in candidate.model.lower():
            continue
        return candidate
    return None


def _select_frontier(
    candidates: Sequence[ModelCandidate],
    *,
    families: Sequence[str],
    additional_models: Sequence[str],
    count: int | None,
) -> list[ModelCandidate]:
    target_families = _dedupe(_canonical_family(family) for family in families)
    if not target_families:
        raise CommitteeError("frontier profile requires at least one target family")
    by_family: dict[str, list[ModelCandidate]] = {}
    by_model = {candidate.model: candidate for candidate in candidates}
    for candidate in candidates:
        by_family.setdefault(candidate.family, []).append(candidate)
    missing_families = [family for family in target_families if not by_family.get(family)]
    if missing_families:
        raise CommitteeError("frontier families are unavailable: " + ", ".join(missing_families))

    selected = []
    for family in target_families:
        if family == "GPT":
            gpt = by_model.get(DEFAULT_GPT_MODEL)
            if gpt is None:
                raise CommitteeError(f"frontier GPT model is unavailable: {DEFAULT_GPT_MODEL}")
            selected.append(gpt)
        else:
            selected.append(sorted(by_family[family], key=_frontier_model_sort_key)[0])
    extra_names = _dedupe(additional_models)
    missing_models = [model for model in extra_names if model not in by_model]
    if missing_models:
        raise CommitteeError("additional models are unavailable: " + ", ".join(missing_models))
    selected_models = {candidate.model for candidate in selected}
    for model in extra_names:
        if model not in selected_models:
            selected.append(by_model[model])
            selected_models.add(model)

    effective_count = count if count is not None else len(selected)
    if effective_count <= len(selected):
        return selected[:effective_count]
    for candidate in sorted(candidates, key=_candidate_sort_key):
        if len(selected) >= effective_count:
            break
        if candidate.model not in selected_models:
            selected.append(candidate)
            selected_models.add(candidate.model)
    return selected


def _frontier_model_sort_key(candidate: ModelCandidate) -> tuple[Any, ...]:
    lower = candidate.model.strip().lower()
    version = _model_version_sort_key(lower)
    variant_rank = 5
    channel_rank = 1
    if candidate.family == "Kimi":
        if lower == "kimi-for-coding":
            channel_rank = 1
        elif lower == "kimi-for-code":
            channel_rank = 2
        elif "code" in lower or "coding" in lower:
            channel_rank = 0
        else:
            channel_rank = 3
    elif candidate.family == "Gemini":
        if re.fullmatch(r"gemini-\d+(?:\.\d+)?-flash-agent\(high\)", lower):
            channel_rank = 0
        elif "agent(high)" in lower:
            channel_rank = 1
        else:
            channel_rank = 2
    elif candidate.family == "Qwen":
        variant_rank = 0 if "max" in lower else (1 if "plus" in lower else (2 if "flash" in lower else 3))
    elif candidate.family == "DeepSeek":
        variant_rank = 0 if "flash" in lower else (1 if "pro" in lower else 2)
    elif candidate.family == "GPT":
        variant_rank = 0 if lower.startswith("gpt-") else (1 if lower.startswith("codex-") else 2)
    tier_rank = {"primary": 0, "preferred": 0, "secondary": 1, "fallback": 2}.get(candidate.tier, 1)
    if candidate.family == "Gemini":
        family_rank = (channel_rank, version, variant_rank)
    else:
        family_rank = (version, channel_rank, variant_rank) if candidate.family == "Kimi" else (version, variant_rank, channel_rank)
    return (
        *family_rank,
        0 if candidate.favorite else 1,
        tier_rank,
        -candidate.context_window_tokens,
        -len(candidate.route_chain),
        lower,
    )


def _model_version_sort_key(model: str) -> tuple[int, int, int, int]:
    match = re.search(r"\d+(?:\.\d+){0,3}", model)
    parts = [int(part) for part in match.group(0).split(".")] if match else []
    parts = (parts + [0, 0, 0, 0])[:4]
    return -parts[0], -parts[1], -parts[2], -parts[3]


def _canonical_family(value: str) -> str:
    text = str(value or "").strip()
    known = {family.lower(): family for family in DEFAULT_FRONTIER_FAMILIES}
    known.update({"claude": "Claude", "mimo": "MiMo", "stepfun": "StepFun", "other": "Other"})
    return known.get(text.lower(), text)


def _candidate_sort_key(candidate: ModelCandidate) -> tuple[Any, ...]:
    tier_rank = {"primary": 0, "preferred": 0, "secondary": 1, "fallback": 2}.get(candidate.tier, 1)
    return (
        0 if candidate.favorite else 1,
        tier_rank,
        0 if _capability_enabled(candidate.capabilities, "reasoning") else 1,
        -candidate.context_window_tokens,
        candidate.family.lower(),
        candidate.model.lower(),
    )


def _infer_family(model: str) -> str:
    normalized = model.lower()
    if re.fullmatch(r"k\d+(?:\.\d+)*(?:-[a-z0-9-]+)?", normalized):
        return "Kimi"
    families = (
        ("Claude", ("claude",)),
        ("GPT", ("gpt", "codex", "o1", "o3", "o4")),
        ("Gemini", ("gemini",)),
        ("DeepSeek", ("deepseek",)),
        ("Qwen", ("qwen",)),
        ("Kimi", ("kimi",)),
        ("MiMo", ("mimo",)),
        ("MiniMax", ("minimax",)),
        ("GLM", ("glm",)),
        ("StepFun", ("stepfun", "step-")),
    )
    for family, keywords in families:
        if any(keyword in normalized for keyword in keywords):
            return family
    return "Other"


def _transport_evidence(
    member: MemberSpec,
    binding: RouteBinding,
    *,
    route_source: str,
    fallback_used: bool,
    fallback_reason: str,
    usage: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "cache_transport_evidence.v1",
        "model": member.candidate.model,
        "provider_id": binding.provider_id,
        "protocol": binding.protocol,
        "request_url": _redact_url(binding.request_url),
        "request_path": binding.request_path,
        "route_source": route_source,
        "provider_profile": binding.provider_profile,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "usage": dict(usage),
    }


def _normalize_usage(raw: Any) -> dict[str, int]:
    usage = raw if isinstance(raw, Mapping) else {}
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), Mapping) else {}
    return {
        "input_tokens": _positive_int(usage.get("input") or usage.get("input_tokens") or usage.get("prompt_tokens")),
        "output_tokens": _positive_int(usage.get("output") or usage.get("output_tokens") or usage.get("completion_tokens")),
        "cache_read_input_tokens": _positive_int(usage.get("cacheRead") or usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens")),
        "cache_creation_input_tokens": _positive_int(usage.get("cacheWrite") or usage.get("cache_creation_input_tokens")),
        "cached_tokens": _positive_int(usage.get("cached_tokens") or prompt_details.get("cached_tokens")),
    }


def _parse_pi_stream(stdout: str) -> tuple[dict[str, Any], str]:
    last_message: dict[str, Any] = {}
    turn_end: dict[str, Any] = {}
    parse_error = ""
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").strip()
        message = event.get("message")
        if event_type == "message_end" and isinstance(message, dict) and message.get("role") == "assistant":
            last_message = message
        elif event_type == "turn_end" and isinstance(message, dict):
            turn_end = message
    return turn_end or last_message, parse_error


def _message_text(message: Mapping[str, Any]) -> str:
    chunks = []
    for item in message.get("content") or []:
        if isinstance(item, Mapping) and item.get("type") == "text" and item.get("text"):
            chunks.append(str(item["text"]))
    return "".join(chunks).strip()


def _parse_response_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _isolated_env(temp_root: Path) -> dict[str, str]:
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SHELL",
        "TERM",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed and value}
    env.update(
        {
            "HOME": str(temp_root),
            "XDG_CONFIG_HOME": str(temp_root / ".config"),
            "XDG_CACHE_HOME": str(temp_root / ".cache"),
            "XDG_DATA_HOME": str(temp_root / ".local" / "share"),
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        }
    )
    return env


@contextlib.contextmanager
def _scoped_mms_config_root(config_root: Path) -> Iterable[None]:
    keys = ("MMS_CONFIG_ROOT", "MMS_CONFIG_DIR")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ[key] = str(config_root)
        _clear_mms_resolution_caches()
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _clear_mms_resolution_caches()


def _clear_mms_resolution_caches() -> None:
    try:
        import mms_capability_resolver
        import mms_provider_profiles

        mms_provider_profiles.load_provider_profiles.cache_clear()
        mms_capability_resolver.clear_capability_cache()
    except (AttributeError, ImportError):
        pass


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _write_private_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")
    path.chmod(0o600)


def _patch_wire_model(provider: dict[str, Any], logical_model: str, wire_model: str) -> str:
    models = provider.get("models") if isinstance(provider.get("models"), list) else []
    if not models:
        raise CommitteeError("Pi provider payload has no models")
    target = None
    for row in models:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "") == logical_model or str(row.get("name") or "") == logical_model:
            target = row
            break
    if target is None:
        target = models[0] if isinstance(models[0], dict) else None
    if target is None:
        raise CommitteeError("Pi provider payload has no usable model entry")
    target["id"] = wire_model
    target["name"] = logical_model
    return wire_model


def _credential_env_name(member_id: str, fallback_position: int) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "_", member_id).upper()
    return f"MMS_PI_COMMITTEE_KEY_{suffix}_{fallback_position}"


def _redact_object(value: Any, secrets: Sequence[str]) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_object(item, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_object(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [_redact_object(item, secrets) for item in value]
    if isinstance(value, str):
        return _redact_text(value, secrets)
    return value


def _redact_text(value: str, secrets: Sequence[str]) -> str:
    text = value
    for secret in sorted({item for item in secrets if item}, key=len, reverse=True):
        text = text.replace(secret, "<redacted>")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text


def _redact_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def _all_api_keys(members: Sequence[MemberSpec]) -> list[str]:
    return [binding.api_key for member in members for binding in member.candidate.route_chain]


def _mapping_at(payload: Mapping[str, Any], *path: str) -> dict[str, Any]:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(part)
    return dict(current) if isinstance(current, Mapping) else {}


def _capability_enabled(capabilities: Mapping[str, Any], name: str) -> bool:
    key = str(name or "").strip().lower()
    aliases = {
        "vision": ("vision", "supports_vision"),
        "thinking": ("thinking", "supports_thinking"),
        "reasoning": ("reasoning", "supports_reasoning"),
        "tool_use": ("tool_use", "tools", "supports_tools"),
        "text": ("text",),
    }
    keys = aliases.get(key, (key,))
    return any(capabilities.get(candidate) is True for candidate in keys)


def _positive_int(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


__all__ = [
    "CommitteeError",
    "DEFAULT_KIMI_ATTEMPT_TIMEOUT_SECONDS",
    "DEFAULT_LENSES",
    "DEFAULT_MAX_BUNDLE_AGE_DAYS",
    "ModelCandidate",
    "RouteBinding",
    "build_candidates",
    "load_candidates",
    "load_catalog",
    "plan_committee",
    "public_bundle_metadata",
    "run_committee",
    "run_preplanned_committee",
    "select_members",
]
