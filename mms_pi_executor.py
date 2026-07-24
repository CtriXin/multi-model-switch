"""Bounded writable Pi executor using disposable git worktrees.

The executor is an opt-in sidecar.  It consumes an explicit verified MMS model
bundle and a durable ``executor.pack.v1``.  A Pi worker may edit only a
disposable worktree; the host audits the resulting diff, reruns validation, and
emits a patch artifact.  Nothing is applied to the user's checkout.
"""

from __future__ import annotations

import concurrent.futures
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

import mms_pi_committee
import mms_pi_watchdog


PACK_SCHEMA = "executor.pack.v1"
PLAN_SCHEMA = "mms.pi_executor.plan.v1"
RESULT_SCHEMA = "mms.pi_executor.result.v1"
WRITABLE_TOOLS = "read,grep,find,ls,edit,write"
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_IDLE_TIMEOUT_SECONDS = 300
DEFAULT_VALIDATION_TIMEOUT_SECONDS = 180
DEFAULT_MAX_OUTPUT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REPEATED_EVENTS = 32
DEFAULT_MAX_PATCH_BYTES = 2 * 1024 * 1024
DEFAULT_EXECUTOR_TIMEOUT_SECONDS = 0
DEFAULT_EXECUTOR_TIMEOUT_GRACE_SECONDS = 90
INVARIANT_FORBIDDEN = (".git", ".git/**")
_WORKTREE_LOCK = threading.Lock()
_SAFE_TASK_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class ExecutorError(RuntimeError):
    """Raised when the executor cannot plan or operate safely."""


def load_pack(pack_path: str | os.PathLike[str], *, target_repo: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(pack_path).expanduser().resolve()
    repo = _git_root(Path(target_repo).expanduser().resolve())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutorError(f"cannot read executor pack: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ExecutorError("executor pack must be a JSON object")
    pack = dict(raw)
    if pack.get("schema") != PACK_SCHEMA:
        raise ExecutorError(f"unsupported pack schema: {pack.get('schema')!r}")
    task_id = str(pack.get("task_id") or "").strip()
    if not _SAFE_TASK_ID.fullmatch(task_id):
        raise ExecutorError("pack task_id must use letters, digits, '.', '_' or '-' only")
    if pack.get("allowed") is False or int(pack.get("blocking_count") or 0) > 0:
        raise ExecutorError("executor pack is blocked by its own pack builder")
    objective = str(pack.get("objective") or "").strip()
    if not objective:
        raise ExecutorError("pack objective is required")
    commit = str(pack.get("commit") or "").strip()
    if not commit:
        raise ExecutorError("pack commit is required")
    base_commit = _git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    writable = _scope_list(pack.get("writable_files"), field="writable_files")
    read_only = _scope_list(pack.get("read_only_files"), field="read_only_files")
    forbidden = _scope_list(pack.get("forbidden_files"), field="forbidden_files")
    if not writable:
        raise ExecutorError("pack writable_files must not be empty")
    overlap = sorted(set(writable) & (set(read_only) | set(forbidden) | set(INVARIANT_FORBIDDEN)))
    if overlap:
        raise ExecutorError("writable scope directly overlaps protected scope: " + ", ".join(overlap))
    validations = _validation_commands(pack.get("validation_commands"))
    criteria = [str(item).strip() for item in pack.get("success_criteria") or [] if str(item).strip()]
    if not criteria:
        raise ExecutorError("pack success_criteria must not be empty")
    normalized = dict(pack)
    normalized.update(
        {
            "pack_path": str(path),
            "target_repo": str(repo),
            "base_commit": base_commit,
            "task_id": task_id,
            "objective": objective,
            "writable_files": writable,
            "read_only_files": read_only,
            "forbidden_files": forbidden,
            "success_criteria": criteria,
            "validation_commands": validations,
        }
    )
    return normalized


def plan_executor(
    *,
    config_root: str | os.PathLike[str],
    pack_path: str | os.PathLike[str],
    target_repo: str | os.PathLike[str],
    explicit_models: Sequence[str],
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    validation_timeout_seconds: int = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = DEFAULT_MAX_REPEATED_EVENTS,
    max_patch_bytes: int = DEFAULT_MAX_PATCH_BYTES,
    executor_timeout_seconds: int = DEFAULT_EXECUTOR_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], list[mms_pi_committee.MemberSpec], dict[str, tuple[mms_pi_committee.PreparedAttempt, ...]], dict[str, Any]]:
    pack = load_pack(pack_path, target_repo=target_repo)
    models = _dedupe(explicit_models)
    if not models:
        raise ExecutorError("at least one explicit --model is required")
    _validate_limits(
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        validation_timeout_seconds=validation_timeout_seconds,
        max_output_bytes=max_output_bytes,
        max_repeated_events=max_repeated_events,
        max_patch_bytes=max_patch_bytes,
        executor_timeout_seconds=executor_timeout_seconds,
    )
    try:
        committee_plan, selected, _bundle = mms_pi_committee.plan_committee(
            config_root=config_root,
            task=pack["objective"],
            count=len(models),
            explicit_models=models,
            required_capabilities=("text",),
            lenses=("implementation",),
        )
    except mms_pi_committee.CommitteeError as exc:
        raise ExecutorError(str(exc)) from exc
    members = [replace(row, member_id=f"executor-{index:02d}", lens="implementation") for index, row in enumerate(selected, 1)]
    prepared = mms_pi_committee._prepare_members(members, config_root=Path(config_root).expanduser())
    waves = (len(members) + min(max_concurrency, len(members)) - 1) // min(max_concurrency, len(members))
    effective_total = executor_timeout_seconds or (timeout_seconds * waves + DEFAULT_EXECUTOR_TIMEOUT_GRACE_SECONDS)
    plan = {
        "schema": PLAN_SCHEMA,
        "run_id": f"pi-exec-{uuid.uuid4().hex[:12]}",
        "task_id": pack["task_id"],
        "pack": _public_pack(pack),
        "route_source": committee_plan["route_source"],
        "component_revisions": committee_plan.get("component_revisions", {}),
        "selection": {
            "mode": "explicit_per_invocation",
            "models": models,
            "members": [row.public() for row in members],
        },
        "isolation": {
            "target_checkout_writes": False,
            "disposable_detached_worktree_per_attempt": True,
            "os_write_sandbox_required": True,
            "global_config_writes": False,
            "global_oauth_fallback": False,
            "opencode_dependency": False,
            "worker_tools": WRITABLE_TOOLS,
            "bash_enabled": False,
            "auto_apply": False,
        },
        "watchdog": {
            "member_wall_timeout_seconds": timeout_seconds,
            "idle_timeout_seconds": idle_timeout_seconds,
            "max_output_bytes": max_output_bytes,
            "max_repeated_events": max_repeated_events,
            "validation_timeout_seconds": validation_timeout_seconds,
            "executor_timeout_seconds": effective_total,
            "executor_timeout_mode": "explicit" if executor_timeout_seconds else "auto_by_concurrency_waves",
        },
        "intake": {
            "max_patch_bytes": max_patch_bytes,
            "scope_source": "pack.writable_files",
            "host_validation_required": True,
            "out_of_scope_policy": "reject_candidate",
            "validation_failure_policy": "reject_candidate",
        },
    }
    return plan, members, prepared, pack


def run_executor(
    *,
    config_root: str | os.PathLike[str],
    pack_path: str | os.PathLike[str],
    target_repo: str | os.PathLike[str],
    explicit_models: Sequence[str],
    artifact_dir: str | os.PathLike[str] | None = None,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    validation_timeout_seconds: int = DEFAULT_VALIDATION_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_repeated_events: int = DEFAULT_MAX_REPEATED_EVENTS,
    max_patch_bytes: int = DEFAULT_MAX_PATCH_BYTES,
    executor_timeout_seconds: int = DEFAULT_EXECUTOR_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan, members, prepared, pack = plan_executor(
        config_root=config_root,
        pack_path=pack_path,
        target_repo=target_repo,
        explicit_models=explicit_models,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        validation_timeout_seconds=validation_timeout_seconds,
        max_output_bytes=max_output_bytes,
        max_repeated_events=max_repeated_events,
        max_patch_bytes=max_patch_bytes,
        executor_timeout_seconds=executor_timeout_seconds,
    )
    if dry_run:
        return {
            "schema": RESULT_SCHEMA,
            "run_id": plan["run_id"],
            "task_id": pack["task_id"],
            "status": "dry_run",
            "plan": plan,
            "summary": {"candidates": len(members), "admissible": 0, "rejected": 0, "failed": 0},
            "results": [],
        }
    if artifact_dir is None:
        raise ExecutorError("artifact_dir is required for live execution")
    sandbox = shutil.which("sandbox-exec")
    if not sandbox:
        raise ExecutorError("sandbox-exec is required; live writable execution fails closed without it")
    artifacts = Path(artifact_dir).expanduser().resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    worker_count = min(max_concurrency, len(members))
    deadline = time.monotonic() + float(plan["watchdog"]["executor_timeout_seconds"])
    cancellation = mms_pi_watchdog.CancellationController()
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="pi-executor") as pool:
        future_to_member = {
            pool.submit(
                _run_candidate,
                member,
                prepared[member.member_id],
                pack=pack,
                target_repo=Path(pack["target_repo"]),
                artifact_dir=artifacts,
                route_source=plan["route_source"],
                timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
                validation_timeout_seconds=validation_timeout_seconds,
                max_output_bytes=max_output_bytes,
                max_repeated_events=max_repeated_events,
                max_patch_bytes=max_patch_bytes,
                cancellation=cancellation,
                sandbox_executable=sandbox,
            ): member
            for member in members
        }
        pending = set(future_to_member)
        while pending:
            if time.monotonic() >= deadline and not cancellation.is_cancelled():
                cancellation.cancel("executor_timeout")
            if cancellation.is_cancelled():
                for future in pending:
                    future.cancel()
            done, pending = concurrent.futures.wait(
                pending,
                timeout=0.1,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for future in done:
                member = future_to_member[future]
                if future.cancelled():
                    results.append(_cancelled_result(member, cancellation.reason or "cancelled"))
                    continue
                try:
                    results.append(future.result())
                except Exception as exc:  # fail closed and retain candidate identity
                    results.append(
                        {
                            "candidate_id": member.member_id,
                            "model": member.candidate.model,
                            "family": member.candidate.family,
                            "status": "worker_error",
                            "terminal_reason": "worker_error",
                            "admissible": False,
                            "error": str(exc),
                        }
                    )
    results.sort(key=lambda row: str(row.get("candidate_id") or ""))
    keys = [binding.api_key for member in members for binding in member.candidate.route_chain]
    results = mms_pi_committee._redact_object(results, keys)
    admissible = sum(bool(row.get("admissible")) for row in results)
    rejected = sum(row.get("status") == "rejected" for row in results)
    failed = len(results) - admissible - rejected
    status = "success" if admissible == len(results) else ("partial" if admissible else "failed")
    return {
        "schema": RESULT_SCHEMA,
        "run_id": plan["run_id"],
        "task_id": pack["task_id"],
        "status": status,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "summary": {"candidates": len(results), "admissible": admissible, "rejected": rejected, "failed": failed},
        "plan": plan,
        "results": results,
        "adoption": {"auto_apply": False, "host_must_select_patch": True, "target_checkout_unchanged_by_executor": True},
    }


def _run_candidate(
    member: mms_pi_committee.MemberSpec,
    attempts: Sequence[mms_pi_committee.PreparedAttempt],
    *,
    pack: Mapping[str, Any],
    target_repo: Path,
    artifact_dir: Path,
    route_source: str,
    timeout_seconds: int,
    idle_timeout_seconds: int,
    validation_timeout_seconds: int,
    max_output_bytes: int,
    max_repeated_events: int,
    max_patch_bytes: int,
    cancellation: mms_pi_watchdog.CancellationController,
    sandbox_executable: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempt_records: list[dict[str, Any]] = []
    errors: list[str] = []
    keys = [attempt.binding.api_key for attempt in attempts]
    for index, attempt in enumerate(attempts):
        if cancellation.is_cancelled():
            return mms_pi_committee._redact_object(_cancelled_result(member, cancellation.reason), keys)
        remaining = max(1, int(deadline - time.monotonic()))
        row = _run_attempt(
            member,
            attempt,
            pack=pack,
            target_repo=target_repo,
            artifact_dir=artifact_dir,
            timeout_seconds=remaining,
            idle_timeout_seconds=idle_timeout_seconds,
            validation_timeout_seconds=validation_timeout_seconds,
            max_output_bytes=max_output_bytes,
            max_repeated_events=max_repeated_events,
            max_patch_bytes=max_patch_bytes,
            cancellation=cancellation,
            sandbox_executable=sandbox_executable,
        )
        fallback_used = index > 0 or bool(attempt.binding.protocol_fallback_reason)
        fallback_reason = "; ".join(errors)
        if attempt.binding.protocol_fallback_reason:
            fallback_reason = "; ".join(filter(None, (fallback_reason, attempt.binding.protocol_fallback_reason)))
        transport = mms_pi_committee._transport_evidence(
            member,
            attempt.binding,
            route_source=route_source,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            usage=row.pop("_usage", {}),
        )
        attempt_records.append(
            {
                "provider_id": attempt.binding.provider_id,
                "status": row.get("status"),
                "terminal_reason": row.get("terminal_reason"),
                "error": row.get("error", ""),
                "watchdog": row.get("watchdog", {}),
                "cache_transport_evidence": transport,
            }
        )
        if row.get("status") in {"success", "rejected"}:
            row.update(
                {
                    "fallback_used": fallback_used,
                    "fallback_reason": fallback_reason,
                    "cache_transport_evidence": transport,
                    "attempts": attempt_records,
                }
            )
            return mms_pi_committee._redact_object(row, keys)
        errors.append(f"{attempt.binding.provider_id}:{row.get('status')}")
        if time.monotonic() >= deadline:
            break
    return mms_pi_committee._redact_object(
        {
            "candidate_id": member.member_id,
            "model": member.candidate.model,
            "family": member.candidate.family,
            "status": "failed",
            "terminal_reason": attempt_records[-1]["terminal_reason"] if attempt_records else "no_route_attempts",
            "admissible": False,
            "error": "; ".join(errors) or "no route attempts were available",
            "fallback_used": len(attempt_records) > 1,
            "fallback_reason": "; ".join(errors[:-1]),
            "attempts": attempt_records,
        },
        keys,
    )


def _run_attempt(
    member: mms_pi_committee.MemberSpec,
    attempt: mms_pi_committee.PreparedAttempt,
    *,
    pack: Mapping[str, Any],
    target_repo: Path,
    artifact_dir: Path,
    timeout_seconds: int,
    idle_timeout_seconds: int,
    validation_timeout_seconds: int,
    max_output_bytes: int,
    max_repeated_events: int,
    max_patch_bytes: int,
    cancellation: mms_pi_watchdog.CancellationController,
    sandbox_executable: str,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    wrapper = root / "scripts" / "pi-cli-wrapper.sh"
    if not wrapper.is_file():
        raise ExecutorError(f"repo-local Pi wrapper is missing: {wrapper}")
    temp_root = Path(tempfile.mkdtemp(prefix=f"mms-pi-executor-{member.member_id}-"))
    worktree = temp_root / "worktree"
    started = time.monotonic()
    try:
        _add_worktree(target_repo, worktree, str(pack["base_commit"]))
        agent_dir = temp_root / ".pi" / "agent"
        session_dir = agent_dir / "sessions"
        temp_tmp = temp_root / "tmp"
        session_dir.mkdir(parents=True, exist_ok=True)
        temp_tmp.mkdir(parents=True, exist_ok=True)
        mms_pi_committee._write_private_json(agent_dir / "models.json", attempt.models_payload)
        mms_pi_committee._write_private_json(agent_dir / "settings.json", {})
        env_name = mms_pi_committee._credential_env_name(member.member_id, attempt.binding.fallback_position)
        env = mms_pi_committee._isolated_env(temp_root)
        private_pi_cache = temp_root / ".cache" / "pi-npx"
        env.update(
            {
                "TMPDIR": str(temp_tmp),
                "PI_CODING_AGENT_DIR": str(agent_dir),
                "PI_CODING_AGENT_SESSION_DIR": str(session_dir),
                "PI_TELEMETRY": "0",
                "PI_SKIP_VERSION_CHECK": "1",
                "MMS_PI_NPX_CACHE": str(private_pi_cache),
                env_name: attempt.binding.api_key,
            }
        )
        cached_pi = _cached_pi_executable(root / ".ai" / "cache" / "pi-npx")
        if cached_pi is not None:
            env["MMS_PI_EXECUTABLE"] = str(cached_pi)
        profile = _sandbox_profile(temp_root=temp_root, worktree=worktree)
        cmd = [
            sandbox_executable,
            "-p",
            profile,
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
            WRITABLE_TOOLS,
            "--thinking",
            "off",
            "-p",
            _worker_prompt(pack, member),
        ]
        outcome = mms_pi_watchdog.run_process(
            cmd,
            cwd=worktree,
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
                "candidate_id": member.member_id,
                "model": member.candidate.model,
                "family": member.candidate.family,
                "status": outcome.terminal_reason,
                "terminal_reason": outcome.terminal_reason,
                "admissible": False,
                "error": outcome.stderr[-1200:] if outcome.terminal_reason == "launch_error" else "",
                "watchdog": watchdog,
            }
        message, parse_error = mms_pi_committee._parse_pi_stream(outcome.stdout)
        response_text = mms_pi_committee._message_text(message)
        if outcome.returncode != 0:
            return {
                "candidate_id": member.member_id,
                "model": member.candidate.model,
                "family": member.candidate.family,
                "status": "launch_error",
                "terminal_reason": "launch_error",
                "admissible": False,
                "error": str(message.get("errorMessage") or outcome.stderr[-1200:] or parse_error or "Pi exited non-zero"),
                "watchdog": watchdog,
            }
        if str(message.get("stopReason") or "").strip().lower() == "error":
            return {
                "candidate_id": member.member_id,
                "model": member.candidate.model,
                "family": member.candidate.family,
                "status": "request_error",
                "terminal_reason": "request_error",
                "admissible": False,
                "error": str(message.get("errorMessage") or "Pi request failed"),
                "watchdog": watchdog,
            }
        if not response_text:
            return {
                "candidate_id": member.member_id,
                "model": member.candidate.model,
                "family": member.candidate.family,
                "status": "empty_response",
                "terminal_reason": "empty_response",
                "admissible": False,
                "watchdog": watchdog,
            }
        before = _capture_change_set(worktree, str(pack["base_commit"]))
        violations = _scope_violations(before["changed_files"], pack)
        patch_bytes = before["patch"].encode("utf-8")
        validations: list[dict[str, Any]] = []
        validation_mutated = False
        if not violations and before["changed_files"] and len(patch_bytes) <= max_patch_bytes:
            validations = _run_validations(
                pack["validation_commands"],
                worktree=worktree,
                temp_root=temp_root,
                sandbox_executable=sandbox_executable,
                timeout_seconds=validation_timeout_seconds,
                max_output_bytes=max_output_bytes,
                max_repeated_events=max_repeated_events,
                cancellation=cancellation,
            )
            after = _capture_change_set(worktree, str(pack["base_commit"]))
            validation_mutated = after["patch_sha256"] != before["patch_sha256"]
        reasons: list[str] = []
        if not before["changed_files"]:
            reasons.append("no_changes")
        if violations:
            reasons.append("scope_violation")
        if len(patch_bytes) > max_patch_bytes:
            reasons.append("patch_limit")
        if any(row["status"] != "passed" for row in validations):
            reasons.append("validation_failed")
        if validation_mutated:
            reasons.append("validation_mutated_worktree")
        patch_info: dict[str, Any] = {}
        if before["changed_files"] and len(patch_bytes) <= max_patch_bytes:
            patch_path = artifact_dir / f"{member.member_id}.patch"
            patch_path.write_text(before["patch"], encoding="utf-8")
            patch_info = {
                "path": str(patch_path),
                "sha256": before["patch_sha256"],
                "bytes": len(patch_bytes),
            }
        parsed = mms_pi_committee._parse_response_object(response_text)
        admissible = not reasons
        return {
            "candidate_id": member.member_id,
            "model": member.candidate.model,
            "family": member.candidate.family,
            "status": "success" if admissible else "rejected",
            "terminal_reason": "completed" if admissible else reasons[0],
            "admissible": admissible,
            "rejection_reasons": reasons,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "provider_id": attempt.binding.provider_id,
            "protocol": attempt.binding.protocol,
            "changed_files": before["changed_files"],
            "scope_violations": violations,
            "validation": validations,
            "validation_mutated_worktree": validation_mutated,
            "patch": patch_info,
            "response": parsed if parsed is not None else {"raw_text": response_text},
            "watchdog": watchdog,
            "_usage": mms_pi_committee._normalize_usage(message.get("usage")),
        }
    finally:
        _remove_worktree(target_repo, worktree)
        shutil.rmtree(temp_root, ignore_errors=True)


def _run_validations(
    commands: Sequence[Sequence[str]],
    *,
    worktree: Path,
    temp_root: Path,
    sandbox_executable: str,
    timeout_seconds: int,
    max_output_bytes: int,
    max_repeated_events: int,
    cancellation: mms_pi_watchdog.CancellationController,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    env = mms_pi_committee._isolated_env(temp_root)
    env["TMPDIR"] = str(temp_root / "tmp")
    validation_cache = temp_root / ".cache" / "validation-npm"
    env["NPM_CONFIG_CACHE"] = str(validation_cache)
    env["npm_config_cache"] = str(validation_cache)
    profile = _sandbox_profile(temp_root=temp_root, worktree=worktree)
    for argv in commands:
        if cancellation.is_cancelled():
            rows.append({"argv": list(argv), "status": "cancelled", "terminal_reason": cancellation.reason})
            break
        outcome = mms_pi_watchdog.run_process(
            [sandbox_executable, "-p", profile, *argv],
            cwd=worktree,
            env=env,
            policy=mms_pi_watchdog.WatchdogPolicy(
                wall_timeout_seconds=timeout_seconds,
                idle_timeout_seconds=timeout_seconds,
                max_output_bytes=max_output_bytes,
                max_repeated_events=max_repeated_events,
            ),
            cancellation=cancellation,
        )
        passed = outcome.terminal_reason == "completed" and outcome.returncode == 0
        rows.append(
            {
                "argv": list(argv),
                "status": "passed" if passed else "failed",
                "terminal_reason": outcome.terminal_reason,
                "returncode": outcome.returncode,
                "elapsed_ms": outcome.elapsed_ms,
                "stdout_tail": outcome.stdout[-4000:],
                "stderr_tail": outcome.stderr[-4000:],
                "watchdog": outcome.public(),
            }
        )
        if not passed:
            break
    return rows


def _capture_change_set(worktree: Path, base_commit: str) -> dict[str, Any]:
    tracked = _git_bytes(worktree, "diff", "--name-only", "-z", base_commit, "--").split(b"\0")
    untracked = _git_bytes(worktree, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    changed = sorted({_decode_git_path(item) for item in (*tracked, *untracked) if item})
    tracked_patch = _git_bytes(worktree, "diff", "--binary", "--no-ext-diff", base_commit, "--")
    chunks = [tracked_patch]
    for path in sorted(_decode_git_path(item) for item in untracked if item):
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "--", "/dev/null", path],
            cwd=worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode not in {0, 1}:
            raise ExecutorError(f"cannot capture untracked patch for {path}: {proc.stderr.decode(errors='replace')}")
        chunks.append(proc.stdout)
    patch = b"".join(chunks).decode("utf-8", errors="replace")
    return {
        "changed_files": changed,
        "patch": patch,
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
    }


def _scope_violations(changed_files: Sequence[str], pack: Mapping[str, Any]) -> list[dict[str, str]]:
    violations: list[dict[str, str]] = []
    forbidden = [*INVARIANT_FORBIDDEN, *pack["forbidden_files"]]
    read_only = pack["read_only_files"]
    writable = pack["writable_files"]
    for path in changed_files:
        if _matches_any(path, forbidden):
            reason = "forbidden"
        elif _matches_any(path, read_only):
            reason = "read_only"
        elif not _matches_any(path, writable):
            reason = "outside_writable_scope"
        else:
            continue
        violations.append({"path": path, "reason": reason})
    return violations


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    normalized = _normalize_repo_path(path, field="changed path", allow_glob=False)
    for pattern in patterns:
        if pattern.endswith("/**") and (normalized == pattern[:-3] or normalized.startswith(pattern[:-2])):
            return True
        if fnmatch.fnmatchcase(normalized, pattern):
            return True
    return False


def _sandbox_profile(*, temp_root: Path, worktree: Path) -> str:
    writable = (temp_root, worktree)
    clauses = ["(version 1)", "(allow default)", "(deny file-write*)"]
    for path in writable:
        clauses.append(f'(allow file-write* (subpath "{_sbpl(path)}"))')
    host_home = Path.home()
    for relative in (".ssh", ".aws", ".gnupg", ".kube", ".claude", ".codex", ".config"):
        sensitive = host_home / relative
        if sensitive.exists() and not _is_within(sensitive, temp_root):
            clauses.append(f'(deny file-read* (subpath "{_sbpl(sensitive)}"))')
    return "".join(clauses)


def _cached_pi_executable(cache_root: Path) -> Path | None:
    """Return a pre-primed Pi binary for read-only execution, if available."""
    candidates = sorted(
        cache_root.glob("_npx/*/node_modules/.bin/pi"),
        key=lambda path: path.lstat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(cache_root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return candidate.resolve()
    return None


def _worker_prompt(pack: Mapping[str, Any], member: mms_pi_committee.MemberSpec) -> str:
    contract = {
        "task_id": pack["task_id"],
        "title": pack.get("title", ""),
        "objective": pack["objective"],
        "task_kind": pack.get("task_kind", "implement"),
        "difficulty": pack.get("difficulty", "D2"),
        "base_commit": pack["base_commit"],
        "writable_files": pack["writable_files"],
        "read_only_files": pack["read_only_files"],
        "forbidden_files": [*INVARIANT_FORBIDDEN, *pack["forbidden_files"]],
        "success_criteria": pack["success_criteria"],
        "non_goals": pack.get("non_goals", []),
    }
    return f"""You are executor {member.member_id}, an independent coding agent in a disposable git worktree.

Executor pack:
{json.dumps(contract, ensure_ascii=False, indent=2)}

Rules:
- Perform the implementation now. You may use read/grep/find/ls/edit/write only; Host owns validation.
- Modify only writable_files. Never touch read_only_files, forbidden_files, .git, credentials, accounts, or global config.
- Do not commit, merge, deploy, send messages, invoke agents, or write outside this worktree.
- Work independently and do not assume another model will repair your result.
- When edits are complete, return one JSON object and no Markdown fence.

Required JSON shape:
{{
  "verdict": "implemented|blocked",
  "summary": "what changed",
  "changed_files": ["repo-relative path"],
  "criteria": [{{"criterion": "...", "status": "met|unmet", "evidence": "..."}}],
  "self_assessment": {{"confidence": 0, "completion": 0, "risk": "low|medium|high"}},
  "residual_risks": ["..."]
}}
""".strip()


def _add_worktree(repo: Path, worktree: Path, commit: str) -> None:
    with _WORKTREE_LOCK:
        proc = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(worktree), commit],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        raise ExecutorError(f"cannot create executor worktree: {proc.stderr.strip()}")


def _remove_worktree(repo: Path, worktree: Path) -> None:
    if not worktree.exists():
        return
    with _WORKTREE_LOCK:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(worktree)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def _git_root(path: Path) -> Path:
    if not path.is_dir():
        raise ExecutorError(f"target repo is not a directory: {path}")
    proc = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ExecutorError(f"target is not a git repository: {path}")
    return Path(proc.stdout.strip()).resolve()


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ExecutorError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _git_bytes(cwd: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise ExecutorError(proc.stderr.decode(errors="replace").strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _scope_list(raw: Any, *, field: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ExecutorError(f"pack {field} must be a list")
    return _dedupe(_normalize_repo_path(str(item), field=field, allow_glob=True) for item in raw)


def _normalize_repo_path(value: str, *, field: str, allow_glob: bool) -> str:
    text = value.strip()
    if text.startswith("./"):
        text = text[2:]
    if not text or "\\" in text or text.startswith("/"):
        raise ExecutorError(f"{field} contains an unsafe path: {value!r}")
    parts = PurePosixPath(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ExecutorError(f"{field} contains an unsafe path: {value!r}")
    if not allow_glob and any(char in text for char in "*?["):
        raise ExecutorError(f"{field} unexpectedly contains a glob: {value!r}")
    return text


def _validation_commands(raw: Any) -> list[list[str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ExecutorError("pack validation_commands must be a list")
    result: list[list[str]] = []
    for item in raw:
        if isinstance(item, str):
            try:
                argv = shlex.split(item)
            except ValueError as exc:
                raise ExecutorError(f"invalid validation command: {exc}") from exc
        elif isinstance(item, list) and all(isinstance(arg, str) for arg in item):
            argv = list(item)
        else:
            raise ExecutorError("validation command must be a shell-like string or argv list")
        if not argv:
            raise ExecutorError("validation command must not be empty")
        result.append(argv)
    return result


def _validate_limits(**values: int) -> None:
    for name, value in values.items():
        minimum = 0 if name == "executor_timeout_seconds" else (2 if name == "max_repeated_events" else 1)
        if value < minimum:
            raise ExecutorError(f"{name} must be at least {minimum}")


def _public_pack(pack: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "schema",
        "task_id",
        "title",
        "objective",
        "task_kind",
        "difficulty",
        "base_commit",
        "writable_files",
        "read_only_files",
        "forbidden_files",
        "success_criteria",
        "validation_commands",
        "non_goals",
        "pack_path",
        "target_repo",
    )
    return {field: pack.get(field) for field in fields}


def _cancelled_result(member: mms_pi_committee.MemberSpec, reason: str) -> dict[str, Any]:
    terminal = str(reason or "cancelled")
    return {
        "candidate_id": member.member_id,
        "model": member.candidate.model,
        "family": member.candidate.family,
        "status": "failed",
        "terminal_reason": terminal,
        "admissible": False,
        "error": terminal,
        "attempts": [],
    }


def _decode_git_path(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def _sbpl(path: Path) -> str:
    return str(path.expanduser().resolve()).replace("\\", "\\\\").replace('"', '\\"')


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _dedupe(values: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
