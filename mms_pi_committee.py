"""Opt-in dynamic Pi committee runtime.

This module is deliberately separate from the MMS launcher and OpenCode paths.
It consumes an explicitly selected, hash-verified latest-approved bundle and
spawns isolated, read-only Pi workers with runtime-bound model routes.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

import mms_consumer_bundle


DEFAULT_MEMBER_COUNT = 4
DEFAULT_MIN_FAMILIES = 3
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_SELECTION_PROFILE = "frontier"
DEFAULT_FRONTIER_FAMILIES = (
    "MiniMax",
    "GPT",
    "Kimi",
    "Gemini",
    "Qwen",
    "DeepSeek",
    "GLM",
)
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

    def public(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "lens": self.lens,
            "model": self.candidate.model,
            "family": self.candidate.family,
            "context_window_tokens": self.candidate.context_window_tokens,
            "route_chain": [binding.public() for binding in self.candidate.route_chain],
        }


@dataclass(frozen=True)
class PreparedAttempt:
    binding: RouteBinding
    models_payload: Mapping[str, Any]
    provider_ref: str
    selected_model: str


def load_catalog(config_root: str | os.PathLike[str]) -> dict[str, Any]:
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
) -> list[MemberSpec]:
    if count is not None and count < 1:
        raise CommitteeError("member count must be at least 1")
    if not lenses:
        raise CommitteeError("at least one review lens is required")
    by_model = {candidate.model: candidate for candidate in candidates}
    if explicit_models:
        requested = _dedupe(explicit_models)
        missing = [model for model in requested if model not in by_model]
        if missing:
            raise CommitteeError("requested models are unavailable: " + ", ".join(missing))
        effective_count = count if count is not None else len(requested)
        selected = [by_model[model] for model in requested[:effective_count]]
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
        elif profile == "balanced":
            if additional_models:
                raise CommitteeError("additional models require the frontier selection profile")
            effective_count = count if count is not None else DEFAULT_MEMBER_COUNT
            selected = _select_diverse(candidates, count=effective_count, min_families=min_families)
        else:
            raise CommitteeError(f"unknown selection profile: {selection_profile}")
    if len(selected) < effective_count:
        raise CommitteeError(f"only {len(selected)} eligible models are available for {effective_count} members")
    return [
        MemberSpec(member_id=f"member-{index:02d}", lens=lenses[(index - 1) % len(lenses)], candidate=candidate)
        for index, candidate in enumerate(selected, start=1)
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
) -> tuple[dict[str, Any], list[MemberSpec], dict[str, Any]]:
    task_text = str(task or "").strip()
    if not task_text:
        raise CommitteeError("task must not be empty")
    if explicit_models and additional_models:
        raise CommitteeError("--model cannot be combined with additional models")
    bundle = load_catalog(config_root)
    bundle_root = Path(str(bundle.get("config_root") or config_root)).expanduser()
    with _scoped_mms_config_root(bundle_root):
        candidates, excluded = build_candidates(bundle, required_capabilities=required_capabilities)
    members = select_members(
        candidates,
        count=count,
        min_families=min_families,
        explicit_models=explicit_models,
        selection_profile=selection_profile,
        frontier_families=frontier_families,
        additional_models=additional_models,
        lenses=lenses,
    )
    effective_count = len(members)
    manifest = bundle.get("manifest") if isinstance(bundle.get("manifest"), Mapping) else {}
    selected_families = sorted({member.candidate.family for member in members})
    effective_profile = "explicit" if explicit_models else str(selection_profile).strip().lower()
    effective_frontier_families = list(_dedupe(_canonical_family(family) for family in frontier_families))
    plan = {
        "schema": "mms.pi_committee.plan.v1",
        "mission_id": mission_id or f"pi-{uuid.uuid4().hex[:12]}",
        "task": task_text,
        "route_source": f"mms:latest-approved:{manifest.get('bundle_revision') or ''}",
        "component_revisions": dict(bundle.get("component_revisions") or {}),
        "selection": {
            "requested_count": effective_count,
            "profile": effective_profile,
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
    dry_run: bool = False,
) -> dict[str, Any]:
    target_cwd = Path(cwd).expanduser().resolve()
    if not target_cwd.is_dir():
        raise CommitteeError(f"worker cwd is not a directory: {target_cwd}")
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
    )
    if dry_run:
        return {
            "schema": "mms.pi_committee.result.v1",
            "mission_id": plan["mission_id"],
            "status": "dry_run",
            "plan": plan,
            "results": [],
        }
    if max_concurrency < 1:
        raise CommitteeError("max concurrency must be at least 1")
    if timeout_seconds < 1:
        raise CommitteeError("timeout must be at least 1 second")

    prepared = _prepare_members(members, config_root=Path(config_root).expanduser())
    worker_count = min(max_concurrency, len(members))
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(
                _run_member,
                member,
                prepared[member.member_id],
                task=str(task).strip(),
                cwd=target_cwd,
                timeout_seconds=timeout_seconds,
                route_source=plan["route_source"],
            ): member.member_id
            for member in members
        }
        for future in concurrent.futures.as_completed(futures):
            member_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(
                    {
                        "member_id": member_id,
                        "status": "worker_error",
                        "error": _redact_text(str(exc), _all_api_keys(members)),
                    }
                )
    results.sort(key=lambda item: str(item.get("member_id") or ""))
    succeeded = sum(1 for item in results if item.get("status") == "success")
    return {
        "schema": "mms.pi_committee.result.v1",
        "mission_id": plan["mission_id"],
        "status": "success" if succeeded == len(results) else ("partial" if succeeded else "failed"),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "summary": {"members": len(results), "succeeded": succeeded, "failed": len(results) - succeeded},
        "plan": plan,
        "results": results,
    }


def _prepare_members(members: Sequence[MemberSpec], *, config_root: Path) -> dict[str, tuple[PreparedAttempt, ...]]:
    prepared: dict[str, tuple[PreparedAttempt, ...]] = {}
    with _scoped_mms_config_root(config_root):
        for member in members:
            attempts = tuple(_prepare_attempt(member, binding) for binding in member.candidate.route_chain)
            prepared[member.member_id] = attempts
    return prepared


def _prepare_attempt(member: MemberSpec, binding: RouteBinding) -> PreparedAttempt:
    import mms_pi_support

    runtime: dict[str, Any] = {
        "id": binding.provider_id,
        "provider_id": binding.provider_id,
        "name": binding.provider_id,
        "api_key": binding.api_key,
        "model": member.candidate.model,
        "provider_profile": binding.provider_profile,
        "_launch_prefetched_probe": {"models": [member.candidate.model]},
    }
    if binding.protocol == "anthropic_messages":
        runtime["anthropic_base_url"] = binding.base_url
    else:
        runtime["openai_base_url"] = binding.base_url
    try:
        payload, provider_ref = mms_pi_support._pi_build_models_payload(runtime, member.candidate.model)
    except RuntimeError as exc:
        raise CommitteeError(f"Pi payload preparation failed for {member.candidate.model}: {exc}") from exc
    payload = json.loads(json.dumps(payload))
    provider = payload.get("providers", {}).get(provider_ref)
    if not isinstance(provider, dict):
        raise CommitteeError(f"Pi payload did not contain selected provider {provider_ref}")
    configured_protocol = _pi_api_protocol(provider.get("api"))
    if configured_protocol != binding.protocol:
        raise CommitteeError(
            f"Pi payload protocol drift for {member.candidate.model}: "
            f"planned {binding.protocol}, configured {configured_protocol or 'unknown'}"
        )
    configured_url, configured_path = _request_target(str(provider.get("baseUrl") or ""), configured_protocol)
    if configured_url != binding.request_url or configured_path != binding.request_path:
        raise CommitteeError(
            f"Pi payload request target drift for {member.candidate.model}: "
            f"planned {binding.request_path}, configured {configured_path}"
        )
    env_name = _credential_env_name(member.member_id, binding.fallback_position)
    provider["apiKey"] = f"${env_name}"
    selected_model = _patch_wire_model(provider, member.candidate.model, binding.wire_model)
    return PreparedAttempt(
        binding=binding,
        models_payload=payload,
        provider_ref=provider_ref,
        selected_model=selected_model,
    )


def _pi_api_protocol(api: Any) -> str:
    return {
        "anthropic-messages": "anthropic_messages",
        "openai-responses": "openai_responses",
        "openai-completions": "openai_chat_completions",
    }.get(str(api or "").strip(), "")


def _run_member(
    member: MemberSpec,
    attempts: Sequence[PreparedAttempt],
    *,
    task: str,
    cwd: Path,
    timeout_seconds: int,
    route_source: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    errors: list[str] = []
    attempt_records: list[dict[str, Any]] = []
    all_keys = [attempt.binding.api_key for attempt in attempts]
    for index, attempt in enumerate(attempts):
        remaining = max(1, int(deadline - time.monotonic()))
        result = _run_attempt(member, attempt, task=task, cwd=cwd, timeout_seconds=remaining)
        route_fallback = index > 0
        fallback_reason = "; ".join(errors) if route_fallback else ""
        if attempt.binding.protocol_fallback_reason:
            fallback_reason = "; ".join(
                item for item in (fallback_reason, attempt.binding.protocol_fallback_reason) if item
            )
        evidence = _transport_evidence(
            member,
            attempt.binding,
            route_source=route_source,
            fallback_used=route_fallback or bool(attempt.binding.protocol_fallback_reason),
            fallback_reason=fallback_reason,
            usage=result.get("_usage", {}),
        )
        attempt_records.append(
            {
                "provider_id": attempt.binding.provider_id,
                "status": result.get("status"),
                "error": result.get("error", ""),
                "cache_transport_evidence": evidence,
            }
        )
        if result["status"] == "success":
            result.pop("_usage", None)
            result["fallback_used"] = evidence["fallback_used"]
            result["fallback_reason"] = evidence["fallback_reason"]
            result["cache_transport_evidence"] = evidence
            result["attempts"] = attempt_records
            return _redact_object(result, all_keys)
        errors.append(f"{attempt.binding.provider_id}:{result.get('status')}")
        if time.monotonic() >= deadline:
            break
    return _redact_object(
        {
            "member_id": member.member_id,
            "model": member.candidate.model,
            "family": member.candidate.family,
            "lens": member.lens,
            "status": "failed",
            "error": "; ".join(errors) or "no route attempts were available",
            "fallback_used": len(errors) > 1,
            "fallback_reason": "; ".join(errors[:-1]),
            "attempts": attempt_records,
        },
        all_keys,
    )


def _run_attempt(
    member: MemberSpec,
    attempt: PreparedAttempt,
    *,
    task: str,
    cwd: Path,
    timeout_seconds: int,
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
            "--thinking",
            "off",
            "-p",
            prompt,
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "elapsed_ms": int((time.monotonic() - started) * 1000)}
    message, parse_error = _parse_pi_stream(completed.stdout)
    text = _message_text(message)
    if completed.returncode != 0:
        return {
            "status": "launch_error",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(message.get("errorMessage") or completed.stderr[-800:] or parse_error or "Pi exited non-zero"),
        }
    if str(message.get("stopReason") or "").strip().lower() == "error":
        return {
            "status": "request_error",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(message.get("errorMessage") or "Pi request failed"),
        }
    if not text:
        return {"status": "empty_response", "elapsed_ms": int((time.monotonic() - started) * 1000)}
    parsed = _parse_response_object(text)
    return {
        "member_id": member.member_id,
        "model": member.candidate.model,
        "family": member.candidate.family,
        "lens": member.lens,
        "status": "success",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "provider_id": attempt.binding.provider_id,
        "protocol": attempt.binding.protocol,
        "response": parsed if parsed is not None else {"raw_text": text},
        "_usage": _normalize_usage(message.get("usage")),
    }


def _worker_prompt(task: str, member: MemberSpec) -> str:
    return f"""You are an independent read-only committee member.

Mission:
{task}

Your assigned lens: {member.lens}

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
  "recommendation": "..."
}}
""".strip()


def _build_route_chain(model: str, route_group: Mapping[str, Any], profile: Mapping[str, Any]) -> tuple[RouteBinding, ...]:
    primary = route_group.get("primary")
    if not isinstance(primary, Mapping):
        raise CommitteeError("route primary is missing")
    chain_rows: list[Mapping[str, Any]] = [primary]
    chain_rows.extend(item for item in route_group.get("fallbacks") or [] if isinstance(item, Mapping))
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

    selected = [
        sorted(by_family[family], key=_frontier_model_sort_key)[0]
        for family in target_families
    ]
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
            channel_rank = 0
        elif lower == "kimi-for-code":
            channel_rank = 1
        else:
            channel_rank = 2
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
    family_rank = (channel_rank, version, variant_rank) if candidate.family in {"Kimi", "Gemini"} else (version, variant_rank, channel_rank)
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
    families = (
        ("Claude", ("claude",)),
        ("GPT", ("gpt", "codex", "o1", "o3", "o4")),
        ("Gemini", ("gemini",)),
        ("DeepSeek", ("deepseek",)),
        ("Qwen", ("qwen",)),
        ("Kimi", ("kimi", "k2.6")),
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
    "DEFAULT_LENSES",
    "ModelCandidate",
    "RouteBinding",
    "build_candidates",
    "load_catalog",
    "plan_committee",
    "run_committee",
    "select_members",
]
